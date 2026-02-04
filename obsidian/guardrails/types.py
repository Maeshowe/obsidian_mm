"""
Guardrail type definitions.

Core types for operational guardrails and validation.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class InstrumentType(str, Enum):
    """
    Instrument type classification.

    CRITICAL: Baselines must NEVER mix instrument types.
    Different structural properties make cross-type comparison meaningless.
    """

    STOCK = "stock"
    INDEX_ETF = "index_etf"

    @classmethod
    def from_ticker(cls, ticker: str) -> "InstrumentType":
        """
        Classify ticker into instrument type.

        Known index ETFs (expand as needed):
        - SPY, QQQ, IWM, DIA - Major index ETFs
        - XLF, XLE, etc. - Sector ETFs
        """
        INDEX_ETFS = {
            # Major indices
            "SPY", "SPX", "QQQ", "IWM", "DIA", "VOO", "VTI",
            # Sector ETFs
            "XLF", "XLE", "XLK", "XLV", "XLI", "XLU", "XLB", "XLY", "XLP",
            # Volatility
            "VXX", "UVXY", "SVXY",
            # Leveraged index
            "TQQQ", "SQQQ", "SPXU", "SPXL", "UPRO",
        }

        ticker_upper = ticker.upper()

        if ticker_upper in INDEX_ETFS:
            return cls.INDEX_ETF

        # Default to stock
        return cls.STOCK


class DataCompleteness(str, Enum):
    """
    Data completeness status for a given observation.

    GUARDRAIL: Missing data must be explicit, not hidden.
    """

    COMPLETE = "complete"  # All required features present
    PARTIAL = "partial"    # Some features missing but regime determinable
    INSUFFICIENT = "insufficient"  # Cannot determine regime

    @property
    def allows_regime_classification(self) -> bool:
        """Whether this completeness level allows regime classification."""
        return self in (DataCompleteness.COMPLETE, DataCompleteness.PARTIAL)


@dataclass(frozen=True)
class GuardrailViolation:
    """
    Record of a guardrail violation.

    Violations are logged but may not block processing depending on severity.
    """

    guardrail: str
    severity: str  # "warning", "error", "critical"
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.guardrail}: {self.message}"


@dataclass(frozen=True)
class BaselineDriftWarning:
    """
    Warning for baseline drift detection.

    Triggered when baseline update changes metrics beyond threshold.
    GUARDRAIL: Drift must never occur silently.
    """

    ticker: str
    metric: str
    old_value: float
    new_value: float
    change_pct: float
    threshold_pct: float
    baseline_date: date

    @property
    def is_significant(self) -> bool:
        """Whether drift exceeds threshold."""
        return abs(self.change_pct) > self.threshold_pct

    def __str__(self) -> str:
        direction = "increased" if self.change_pct > 0 else "decreased"
        return (
            f"BASELINE_DRIFT_WARNING: {self.ticker} {self.metric} "
            f"{direction} by {abs(self.change_pct):.1f}% "
            f"(threshold: {self.threshold_pct}%)"
        )


@dataclass
class MissingDataRecord:
    """
    Record of missing data for a given observation.

    Used to explain why UNDETERMINED was assigned.
    """

    ticker: str
    trade_date: date
    missing_features: list[str]
    reason: str

    def to_explanation(self) -> str:
        """Generate human-readable explanation."""
        features = ", ".join(self.missing_features[:3])
        if len(self.missing_features) > 3:
            features += f" (+{len(self.missing_features) - 3} more)"

        return (
            f"Regime classification could not be determined due to "
            f"missing data: {features}. {self.reason}"
        )
