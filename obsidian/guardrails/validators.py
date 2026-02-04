"""
Guardrail validators.

Validation functions for operational guardrails.
"""

import logging
from datetime import date
from typing import Any

from obsidian.guardrails.types import (
    InstrumentType,
    DataCompleteness,
    GuardrailViolation,
    BaselineDriftWarning,
    MissingDataRecord,
)
from obsidian.guardrails.conventions import (
    GreeksSource,
    normalize_greek_sign,
)

logger = logging.getLogger(__name__)


# ============================================================
# GUARDRAIL 1: BASELINE DRIFT DETECTION
# ============================================================

# Default drift threshold (percentage change that triggers warning)
DEFAULT_DRIFT_THRESHOLD_PCT = 15.0


def check_baseline_drift(
    old_baseline: dict[str, Any],
    new_baseline: dict[str, Any],
    threshold_pct: float = DEFAULT_DRIFT_THRESHOLD_PCT,
) -> list[BaselineDriftWarning]:
    """
    Check for significant baseline drift between updates.

    GUARDRAIL: Drift must never occur silently.

    Args:
        old_baseline: Previous baseline data
        new_baseline: New baseline data
        threshold_pct: Percentage change threshold for warning

    Returns:
        List of drift warnings (empty if no significant drift)
    """
    warnings = []

    ticker = new_baseline.get("ticker", "UNKNOWN")
    baseline_date = date.fromisoformat(new_baseline.get("baseline_date", date.today().isoformat()))

    # Metrics to check for drift
    metrics_to_check = [
        ("dark_pool.dark_share.mean", "Dark Pool Share Mean"),
        ("dark_pool.dark_share.std", "Dark Pool Share Std"),
        ("greeks.gex.mean", "GEX Mean"),
        ("greeks.gex.std", "GEX Std"),
        ("greeks.dex.mean", "DEX Mean"),
        ("price_efficiency.daily_range_pct.mean", "Daily Range Mean"),
    ]

    for path, metric_name in metrics_to_check:
        old_value = _get_nested_value(old_baseline, path)
        new_value = _get_nested_value(new_baseline, path)

        if old_value is None or new_value is None:
            continue

        if old_value == 0:
            # Can't calculate percentage change from zero
            if new_value != 0:
                logger.warning(
                    f"BASELINE_DRIFT: {ticker} {metric_name} changed from 0 to {new_value}"
                )
            continue

        change_pct = ((new_value - old_value) / abs(old_value)) * 100

        if abs(change_pct) > threshold_pct:
            warning = BaselineDriftWarning(
                ticker=ticker,
                metric=metric_name,
                old_value=old_value,
                new_value=new_value,
                change_pct=change_pct,
                threshold_pct=threshold_pct,
                baseline_date=baseline_date,
            )
            warnings.append(warning)
            logger.warning(str(warning))

    return warnings


def _get_nested_value(data: dict, path: str) -> Any:
    """Get value from nested dict using dot notation."""
    keys = path.split(".")
    value = data

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None

    return value


# ============================================================
# GUARDRAIL 2: INCOMPLETE DATA HANDLING
# ============================================================

# Features required for regime classification (minimum set)
REQUIRED_FEATURES_MINIMUM = [
    "gex",
    "dex",
    "dark_pool_ratio",
]

# Features required for full classification
REQUIRED_FEATURES_FULL = [
    "gex",
    "dex",
    "dark_pool_ratio",
    "block_trade_count",
    "price_change_pct",
]


def validate_data_completeness(
    features: dict[str, Any],
    ticker: str,
    trade_date: date,
) -> tuple[DataCompleteness, MissingDataRecord | None]:
    """
    Validate data completeness for regime classification.

    GUARDRAIL: If required data is missing:
    - DO NOT fill with zeros
    - DO NOT interpolate
    - DO NOT guess
    - Set regime = UNDETERMINED

    Args:
        features: Feature dictionary
        ticker: Stock ticker
        trade_date: Date of observation

    Returns:
        Tuple of (completeness status, missing data record if incomplete)
    """
    missing_minimum = []
    missing_full = []

    # Check minimum required features
    for feature in REQUIRED_FEATURES_MINIMUM:
        value = features.get(feature)
        if value is None:
            missing_minimum.append(feature)

    # Check full required features
    for feature in REQUIRED_FEATURES_FULL:
        value = features.get(feature)
        if value is None:
            missing_full.append(feature)

    # Determine completeness level
    if not missing_minimum and not missing_full:
        return DataCompleteness.COMPLETE, None

    elif missing_minimum:
        # Cannot determine regime at all
        record = MissingDataRecord(
            ticker=ticker,
            trade_date=trade_date,
            missing_features=missing_minimum,
            reason="Critical features missing - regime cannot be determined.",
        )
        logger.warning(
            f"INCOMPLETE_DATA: {ticker} {trade_date} missing critical features: "
            f"{', '.join(missing_minimum)}"
        )
        return DataCompleteness.INSUFFICIENT, record

    else:
        # Can determine regime but with reduced confidence
        record = MissingDataRecord(
            ticker=ticker,
            trade_date=trade_date,
            missing_features=missing_full,
            reason="Secondary features missing - classification may have reduced accuracy.",
        )
        logger.info(
            f"PARTIAL_DATA: {ticker} {trade_date} missing secondary features: "
            f"{', '.join(missing_full)}"
        )
        return DataCompleteness.PARTIAL, record


# ============================================================
# GUARDRAIL 3: INSTRUMENT TYPE SEPARATION
# ============================================================


def validate_instrument_type(
    ticker: str,
    baseline_instrument_type: InstrumentType | None = None,
) -> tuple[InstrumentType, GuardrailViolation | None]:
    """
    Validate and classify instrument type.

    GUARDRAIL: Baselines must never mix instrument types.

    Args:
        ticker: Stock ticker
        baseline_instrument_type: Instrument type from existing baseline (if any)

    Returns:
        Tuple of (instrument type, violation if type mismatch)
    """
    current_type = InstrumentType.from_ticker(ticker)

    if baseline_instrument_type is not None and current_type != baseline_instrument_type:
        violation = GuardrailViolation(
            guardrail="INSTRUMENT_TYPE_SEPARATION",
            severity="error",
            message=(
                f"Instrument type mismatch for {ticker}: "
                f"baseline is {baseline_instrument_type.value}, "
                f"current classification is {current_type.value}. "
                f"Baselines must not mix instrument types."
            ),
            context={
                "ticker": ticker,
                "baseline_type": baseline_instrument_type.value,
                "current_type": current_type.value,
            },
        )
        logger.error(str(violation))
        return current_type, violation

    return current_type, None


# ============================================================
# GUARDRAIL 4: GREEKS SIGN CONVENTION LOCK
# ============================================================


def validate_greeks_sign_convention(
    greeks: dict[str, float],
    source: GreeksSource = GreeksSource.UNUSUAL_WHALES,
) -> tuple[dict[str, float], list[GuardrailViolation]]:
    """
    Validate and normalize Greeks to OBSIDIAN sign convention.

    GUARDRAIL: Sign conventions must be locked and consistent.
    A flipped sign silently inverts regime classification.

    Args:
        greeks: Raw Greek values from source
        source: Data source for sign convention mapping

    Returns:
        Tuple of (normalized Greeks, list of violations)
    """
    normalized = {}
    violations = []

    greek_keys = ["gex", "dex", "vanna", "charm"]

    for key in greek_keys:
        if key not in greeks or greeks[key] is None:
            continue

        try:
            normalized[key] = normalize_greek_sign(greeks[key], key, source)
        except ValueError as e:
            violation = GuardrailViolation(
                guardrail="GREEKS_SIGN_CONVENTION",
                severity="error",
                message=str(e),
                context={"greek": key, "source": source.value},
            )
            violations.append(violation)
            logger.error(str(violation))

    return normalized, violations


# ============================================================
# GUARDRAIL 5: Z-SCORE VS PERCENTILE DISCIPLINE
# ============================================================


def validate_zscore_usage(
    feature_name: str,
    context: str,
) -> GuardrailViolation | None:
    """
    Validate that z-scores are only used in regime classification.

    GUARDRAIL: Z-scores for classification, percentiles for scoring/display.

    Args:
        feature_name: Name of feature being used
        context: Where it's being used ("classification", "scoring", "display")

    Returns:
        Violation if z-score used incorrectly
    """
    is_zscore = feature_name.endswith("_zscore")

    if is_zscore and context in ("scoring", "display"):
        return GuardrailViolation(
            guardrail="ZSCORE_PERCENTILE_DISCIPLINE",
            severity="warning",
            message=(
                f"Z-score feature '{feature_name}' used in {context}. "
                f"Z-scores should only be used for regime classification. "
                f"Use percentiles for scoring and display."
            ),
            context={"feature": feature_name, "context": context},
        )

    return None


def validate_percentile_usage(
    feature_name: str,
    context: str,
) -> GuardrailViolation | None:
    """
    Validate that percentiles are only used in scoring/display.

    GUARDRAIL: Z-scores for classification, percentiles for scoring/display.

    Args:
        feature_name: Name of feature being used
        context: Where it's being used ("classification", "scoring", "display")

    Returns:
        Violation if percentile used incorrectly
    """
    is_percentile = feature_name.endswith("_pct") or feature_name.endswith("_percentile")

    if is_percentile and context == "classification":
        # Percentiles in classification is allowed for context (e.g., price_efficiency_pct)
        # Only warn if it's the primary condition
        return GuardrailViolation(
            guardrail="ZSCORE_PERCENTILE_DISCIPLINE",
            severity="info",
            message=(
                f"Percentile feature '{feature_name}' used in classification. "
                f"This is acceptable for context validation but not primary conditions."
            ),
            context={"feature": feature_name, "context": context},
        )

    return None
