"""
Regime classifier.

Rule-based, deterministic classification of market microstructure regimes.
Evaluated in priority order - first matching regime wins.

GUARDRAILS ENFORCED:
1. Priority Short-Circuit: First matching rule wins, exactly one regime per day
2. Incomplete Data Handling: UNDETERMINED when critical data missing
3. Z-Score Discipline: Only z-scores used in regime classification conditions
4. No Secondary Labels: Once matched, evaluation stops

FINAL RULE: When in doubt, default to UNDETERMINED.
False negatives are acceptable. False confidence is not.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import pandas as pd

from obsidian.core.config import RegimesConfig, load_config
from obsidian.core.constants import (
    BLOCK_ACTIVITY_ELEVATED,
    DARK_POOL_DOMINANT,
    DARK_POOL_ELEVATED,
    DEX_ELEVATED,
    GEX_EXTREME_NEGATIVE,
    GEX_EXTREME_POSITIVE,
    IMPACT_PER_VOL_HIGH,
    PRICE_EFFICIENCY_LOW,
    PRICE_STABLE_HIGH,
    PRICE_STABLE_LOW,
)
from obsidian.core.types import RegimeLabel, RegimeResult, TopDriver


logger = logging.getLogger(__name__)


# GUARDRAIL: Minimum required features for classification
# If ANY of these are missing/None, regime = UNDETERMINED
MINIMUM_REQUIRED_FEATURES = ["gex_zscore", "dex_zscore"]


@dataclass
class RegimeRule:
    """A single rule for regime classification."""

    label: RegimeLabel
    priority: int
    check: Callable[[pd.Series], bool]
    explain: Callable[[pd.Series], str]
    description: str


class RegimeClassifier:
    """
    Rule-based regime classifier.

    Classifies market microstructure state into discrete regimes
    based on normalized features. Rules are evaluated in priority
    order - first matching rule wins.

    Regimes (in priority order):
    1. Gamma+ Control - dealers long gamma, volatility suppressed
    2. Gamma- Liquidity Vacuum - dealers short gamma, volatility amplified
    3. Dark-Dominant Accumulation - high off-exchange activity
    4. Absorption-like - passive buying absorbing sells
    5. Distribution-like - selling into strength
    6. Neutral - no dominant pattern (fallback)
    """

    def __init__(self, config: RegimesConfig | None = None) -> None:
        """
        Initialize regime classifier.

        Args:
            config: Regime configuration (loaded from YAML if not provided)
        """
        self.config = config or load_config("regimes")
        self.rules = self._build_rules()

    def _build_rules(self) -> list[RegimeRule]:
        """Build ordered list of regime rules."""
        rules = [
            RegimeRule(
                label=RegimeLabel.GAMMA_POSITIVE_CONTROL,
                priority=1,
                check=self._check_gamma_positive,
                explain=self._explain_gamma_positive,
                description="Dealers long gamma, volatility suppressed",
            ),
            RegimeRule(
                label=RegimeLabel.GAMMA_NEGATIVE_VACUUM,
                priority=2,
                check=self._check_gamma_negative,
                explain=self._explain_gamma_negative,
                description="Dealers short gamma, volatility amplified",
            ),
            RegimeRule(
                label=RegimeLabel.DARK_DOMINANT_ACCUMULATION,
                priority=3,
                check=self._check_dark_dominant,
                explain=self._explain_dark_dominant,
                description="High off-exchange activity with blocks",
            ),
            RegimeRule(
                label=RegimeLabel.ABSORPTION_LIKE,
                priority=4,
                check=self._check_absorption,
                explain=self._explain_absorption,
                description="Passive buying absorbing sell flow",
            ),
            RegimeRule(
                label=RegimeLabel.DISTRIBUTION_LIKE,
                priority=5,
                check=self._check_distribution,
                explain=self._explain_distribution,
                description="Selling into strength",
            ),
        ]
        return sorted(rules, key=lambda r: r.priority)

    def classify(
        self,
        features: pd.Series,
        ticker: str = "",
        trade_date: date | None = None,
    ) -> RegimeResult:
        """
        Classify features into a regime.

        GUARDRAILS ENFORCED:
        - Priority Short-Circuit: First match wins (rules sorted by priority)
        - Incomplete Data: UNDETERMINED if critical features missing
        - One Day = One State: Exactly one regime returned

        Decision tree logic (priority order):
        1. Check data completeness (UNDETERMINED if insufficient)
        2. Gamma extremes take priority (most market-impact)
        3. Dark pool dominance next (structural)
        4. Directional flow patterns last (interpretive)
        5. Neutral as fallback (all metrics within normal ranges)

        Args:
            features: Series with normalized feature values
            ticker: Stock ticker (for result)
            trade_date: Date of classification (for result)

        Returns:
            RegimeResult with label, confidence, and explanation
        """
        trade_date = trade_date or date.today()

        # GUARDRAIL: Check for incomplete data
        missing_features = self._check_data_completeness(features)
        if missing_features:
            logger.warning(
                f"INCOMPLETE_DATA: {ticker} {trade_date} missing critical features: "
                f"{', '.join(missing_features)}. Regime = UNDETERMINED"
            )
            return RegimeResult(
                ticker=ticker,
                trade_date=trade_date,
                label=RegimeLabel.UNDETERMINED,
                confidence=0.0,
                explanation=self._explain_undetermined(features, missing_features),
                top_drivers=(),
                raw_features=features.to_dict(),
            )

        # GUARDRAIL: Priority Short-Circuit
        # Evaluate rules in priority order - first match wins
        for rule in self.rules:
            try:
                if rule.check(features):
                    # GUARDRAIL: Stop evaluation immediately
                    # No secondary labels allowed
                    return RegimeResult(
                        ticker=ticker,
                        trade_date=trade_date,
                        label=rule.label,
                        confidence=self._calculate_confidence(rule.label, features),
                        explanation=rule.explain(features),
                        top_drivers=self._get_top_drivers(features),
                        raw_features=features.to_dict(),
                    )
            except KeyError as e:
                logger.warning(f"Missing feature for {rule.label}: {e}")
                continue

        # Default to neutral (all conditions checked, none matched)
        return RegimeResult(
            ticker=ticker,
            trade_date=trade_date,
            label=RegimeLabel.NEUTRAL,
            confidence=0.5,
            explanation=self._explain_neutral(features),
            top_drivers=self._get_top_drivers(features),
            raw_features=features.to_dict(),
        )

    def _check_data_completeness(self, features: pd.Series) -> list[str]:
        """
        Check if minimum required features are present.

        GUARDRAIL: If critical data is missing:
        - DO NOT fill with zeros
        - DO NOT interpolate
        - DO NOT guess
        - Return UNDETERMINED

        Returns:
            List of missing feature names (empty if complete)
        """
        missing = []
        for feature in MINIMUM_REQUIRED_FEATURES:
            value = features.get(feature)
            if value is None or pd.isna(value):
                missing.append(feature)
        return missing

    def _explain_undetermined(
        self, features: pd.Series, missing_features: list[str]
    ) -> str:
        """
        Generate explanation for UNDETERMINED regime.

        GUARDRAIL: Uncertainty must be explicit, not hidden.
        """
        feature_list = ", ".join(missing_features[:3])
        if len(missing_features) > 3:
            feature_list += f" (+{len(missing_features) - 3} more)"

        return (
            f"Regime classification could not be determined. "
            f"Critical data missing: {feature_list}. "
            f"OBSIDIAN refuses to guess - uncertainty is reported explicitly. "
            f"This is NOT a failure; it is honest observation."
        )

    # ========================================
    # Rule Check Functions
    # ========================================

    def _check_gamma_positive(self, f: pd.Series) -> bool:
        """
        Gamma+ Control: Dealers long gamma, volatility suppressed.

        Conditions:
        - GEX z-score > +1.5 (significantly positive)
        - Dark pool ratio < 60% (not dark-dominant, would conflict)
        - Price efficiency below median (confirms control)
        """
        gex_zscore = f.get("gex_zscore", 0)
        dark_pool_pct = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))
        price_eff_pct = f.get("price_efficiency_pct", 50)  # Default to median

        return (
            gex_zscore > GEX_EXTREME_POSITIVE
            and dark_pool_pct < 60
            and price_eff_pct < PRICE_EFFICIENCY_LOW
        )

    def _check_gamma_negative(self, f: pd.Series) -> bool:
        """
        Gamma- Liquidity Vacuum: Dealers short gamma, volatility amplified.

        Conditions:
        - GEX z-score < -1.5 (significantly negative)
        - Impact per volume above median (confirms vacuum)
        """
        gex_zscore = f.get("gex_zscore", 0)
        impact_pct = f.get("impact_per_vol_pct", 50)  # Default to median

        return (
            gex_zscore < GEX_EXTREME_NEGATIVE
            and impact_pct > IMPACT_PER_VOL_HIGH
        )

    def _check_dark_dominant(self, f: pd.Series) -> bool:
        """
        Dark-Dominant Accumulation: Institutional off-exchange activity.

        Conditions:
        - Dark pool ratio > 70%
        - Block trade count z-score > 1.0 (elevated block activity)
        """
        dark_pool_pct = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))
        block_zscore = f.get("block_trade_count_zscore", 0)

        return (
            dark_pool_pct > DARK_POOL_DOMINANT
            and block_zscore > BLOCK_ACTIVITY_ELEVATED
        )

    def _check_absorption(self, f: pd.Series) -> bool:
        """
        Absorption-like: Passive buying absorbing sell flow.

        Conditions:
        - DEX z-score < -1.0 (negative delta exposure)
        - Price change >= -0.5% (price not falling)
        - Dark pool ratio > 50% (some dark activity)
        """
        dex_zscore = f.get("dex_zscore", 0)
        price_change = f.get("price_change_pct", 0)
        dark_pool_pct = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))

        return (
            dex_zscore < -DEX_ELEVATED
            and price_change >= PRICE_STABLE_LOW
            and dark_pool_pct > DARK_POOL_ELEVATED
        )

    def _check_distribution(self, f: pd.Series) -> bool:
        """
        Distribution-like: Selling into strength.

        Conditions:
        - DEX z-score > +1.0 (positive delta exposure)
        - Price change <= +0.5% (price not rising significantly)
        """
        dex_zscore = f.get("dex_zscore", 0)
        price_change = f.get("price_change_pct", 0)

        return (
            dex_zscore > DEX_ELEVATED
            and price_change <= PRICE_STABLE_HIGH
        )

    # ========================================
    # Explanation Functions
    # ========================================

    def _explain_gamma_positive(self, f: pd.Series) -> str:
        gex = f.get("gex_zscore", 0)
        eff = f.get("price_efficiency_pct", 50)
        dark = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))

        return (
            f"GEX z-score is {gex:+.2f} (above +1.5 threshold), indicating "
            f"dealers are significantly long gamma. Price efficiency at "
            f"{eff:.0f}th percentile confirms volatility suppression. "
            f"Dark pool ratio at {dark:.1f}% suggests lit market activity. "
            f"Expect price pinning near major strikes."
        )

    def _explain_gamma_negative(self, f: pd.Series) -> str:
        gex = f.get("gex_zscore", 0)
        impact = f.get("impact_per_vol_pct", 50)

        return (
            f"GEX z-score is {gex:+.2f} (below -1.5 threshold), indicating "
            f"dealers are significantly short gamma. Impact-per-volume at "
            f"{impact:.0f}th percentile confirms liquidity vacuum. "
            f"This creates conditions where price moves may be amplified."
        )

    def _explain_dark_dominant(self, f: pd.Series) -> str:
        dark = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))
        block = f.get("block_trade_count_zscore", 0)

        return (
            f"Dark pool ratio is {dark:.1f}% (above 70% threshold) with "
            f"elevated block activity (z-score: {block:+.2f}). "
            f"This pattern suggests institutional accumulation occurring "
            f"primarily through off-exchange venues."
        )

    def _explain_absorption(self, f: pd.Series) -> str:
        dex = f.get("dex_zscore", 0)
        price = f.get("price_change_pct", 0)
        dark = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))

        return (
            f"Negative delta exposure (DEX z-score: {dex:+.2f}) combined with "
            f"stable price action ({price:+.2f}%) suggests passive buying "
            f"absorbing sell flow. Dark pool ratio: {dark:.1f}%."
        )

    def _explain_distribution(self, f: pd.Series) -> str:
        dex = f.get("dex_zscore", 0)
        price = f.get("price_change_pct", 0)

        return (
            f"Positive delta exposure (DEX z-score: {dex:+.2f}) with limited "
            f"price appreciation ({price:+.2f}%) suggests distribution. "
            f"Institutions may be selling into existing bid support."
        )

    def _explain_neutral(self, f: pd.Series) -> str:
        gex = f.get("gex_zscore", 0)
        dex = f.get("dex_zscore", 0)
        dark = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))

        return (
            f"No dominant regime pattern detected. "
            f"GEX: {gex:+.2f}σ, DEX: {dex:+.2f}σ, "
            f"Dark Pool: {dark:.1f}%. "
            f"All metrics within normal operating ranges."
        )

    # ========================================
    # Helper Functions
    # ========================================

    def _get_top_drivers(self, f: pd.Series, n: int = 3) -> tuple[TopDriver, ...]:
        """Get top N features by absolute z-score magnitude."""
        zscore_cols = [c for c in f.index if c.endswith("_zscore")]

        if not zscore_cols:
            return ()

        sorted_features = sorted(
            [(col, abs(f[col]), f[col]) for col in zscore_cols if pd.notna(f[col])],
            key=lambda x: x[1],
            reverse=True,
        )

        total_magnitude = sum(abs_val for _, abs_val, _ in sorted_features)

        drivers = []
        for col, abs_val, raw in sorted_features[:n]:
            feature_name = col.replace("_zscore", "")
            contribution = (abs_val / total_magnitude * 100) if total_magnitude > 0 else 0

            drivers.append(
                TopDriver(
                    feature=feature_name,
                    zscore=raw,
                    contribution_pct=contribution,
                    direction="elevated" if raw > 0 else "depressed",
                )
            )

        return tuple(drivers)

    def _calculate_confidence(self, label: RegimeLabel, f: pd.Series) -> float:
        """
        Calculate confidence score (0-1) for regime match.

        Based on how far past thresholds the conditions are.
        """
        base_confidence = 0.5

        if label == RegimeLabel.GAMMA_POSITIVE_CONTROL:
            gex = f.get("gex_zscore", 0)
            margin = (gex - GEX_EXTREME_POSITIVE) / GEX_EXTREME_POSITIVE
            return min(1.0, max(0.5, base_confidence + margin * 0.3))

        elif label == RegimeLabel.GAMMA_NEGATIVE_VACUUM:
            gex = f.get("gex_zscore", 0)
            margin = (-gex - abs(GEX_EXTREME_NEGATIVE)) / abs(GEX_EXTREME_NEGATIVE)
            return min(1.0, max(0.5, base_confidence + margin * 0.3))

        elif label == RegimeLabel.DARK_DOMINANT_ACCUMULATION:
            dark = f.get("dark_pool_ratio_pct", f.get("dark_pool_ratio", 0))
            margin = (dark - DARK_POOL_DOMINANT) / 30  # 30% above threshold = high confidence
            return min(1.0, max(0.5, base_confidence + margin * 0.3))

        elif label == RegimeLabel.ABSORPTION_LIKE:
            dex = f.get("dex_zscore", 0)
            margin = (-dex - DEX_ELEVATED) / DEX_ELEVATED
            return min(1.0, max(0.5, base_confidence + margin * 0.25))

        elif label == RegimeLabel.DISTRIBUTION_LIKE:
            dex = f.get("dex_zscore", 0)
            margin = (dex - DEX_ELEVATED) / DEX_ELEVATED
            return min(1.0, max(0.5, base_confidence + margin * 0.25))

        return 0.5  # Neutral default
