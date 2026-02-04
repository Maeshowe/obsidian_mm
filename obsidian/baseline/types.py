"""
Baseline type definitions for OBSIDIAN MM.

Defines the schema for ticker-specific baseline profiles that establish
what "normal" looks like for each instrument.

DESIGN PRINCIPLE:
    "You cannot call something unusual without knowing what normal is."
    Every deviation metric must reference a stored baseline.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TypeAlias


class BaselineUpdatePolicy(str, Enum):
    """
    Determines how and when a baseline metric should be updated.

    LOCKED: Structural property - updated quarterly or manually only.
            Represents the instrument's fundamental characteristics.

    DYNAMIC: State-dependent - updated daily via rolling windows.
             Represents current deviations from structural norms.
    """

    LOCKED = "locked"
    DYNAMIC = "dynamic"


@dataclass(frozen=True)
class DistributionStats:
    """
    Statistical summary of a metric's distribution.

    Used for establishing normal ranges and detecting deviations.
    """

    mean: float
    std: float
    median: float
    mad: float  # Median Absolute Deviation - robust to outliers
    p25: float  # 25th percentile
    p75: float  # 75th percentile
    p90: float  # 90th percentile
    p95: float  # 95th percentile
    min_val: float
    max_val: float
    n_observations: int

    @property
    def iqr(self) -> float:
        """Interquartile range."""
        return self.p75 - self.p25

    @property
    def normal_range_low(self) -> float:
        """Lower bound of normal range (mean - 1.5σ)."""
        return self.mean - 1.5 * self.std

    @property
    def normal_range_high(self) -> float:
        """Upper bound of normal range (mean + 1.5σ)."""
        return self.mean + 1.5 * self.std

    def zscore(self, value: float) -> float:
        """Calculate z-score for a value against this distribution."""
        if self.std == 0:
            return 0.0
        return (value - self.mean) / self.std

    def percentile_rank(self, value: float) -> float:
        """Estimate percentile rank for a value (linear interpolation)."""
        if value <= self.min_val:
            return 0.0
        if value >= self.max_val:
            return 100.0
        if value <= self.median:
            # Linear interpolation in lower half
            return 50.0 * (value - self.min_val) / (self.median - self.min_val + 1e-10)
        else:
            # Linear interpolation in upper half
            return 50.0 + 50.0 * (value - self.median) / (self.max_val - self.median + 1e-10)


@dataclass(frozen=True)
class DarkPoolBaseline:
    """
    Baseline metrics for dark pool / off-exchange activity.

    Answers: "How dark is this instrument normally?"
    """

    # Volume share
    dark_share: DistributionStats  # dark_volume / total_volume (percentage)
    dark_share_typical_range: tuple[float, float]  # (low, high) bounds

    # Block activity
    daily_block_count: DistributionStats  # Number of blocks per day
    block_size: DistributionStats  # Average block size distribution
    block_premium: DistributionStats  # Notional value of blocks

    # Venue concentration
    venue_shift: DistributionStats  # Day-over-day change in dark share

    # Absolute volume (optional - may not be available in all baselines)
    dark_volume: DistributionStats | None = None

    # Update policy
    policy: BaselineUpdatePolicy = BaselineUpdatePolicy.LOCKED


@dataclass(frozen=True)
class GreeksBaseline:
    """
    Baseline metrics for options Greeks and dealer exposure.

    Answers: "How sensitive is this instrument to dealer hedging normally?"
    """

    # Gamma exposure
    gex: DistributionStats
    gex_positive_pct: float  # % of days with positive gamma
    gex_negative_pct: float  # % of days with negative gamma

    # Delta exposure
    dex: DistributionStats

    # Higher-order Greeks (may have limited data)
    vanna: DistributionStats | None = None
    charm: DistributionStats | None = None

    # IV metrics
    iv_atm: DistributionStats | None = None
    iv_atm_daily_change: DistributionStats | None = None
    iv_skew: DistributionStats | None = None
    iv_rank: DistributionStats | None = None

    # Update policy
    policy: BaselineUpdatePolicy = BaselineUpdatePolicy.LOCKED


@dataclass(frozen=True)
class PriceEfficiencyBaseline:
    """
    Baseline metrics for price impact and market efficiency.

    Answers: "How efficiently does price usually respond to volume?"
    """

    # Range vs Volume
    range_per_volume: DistributionStats  # daily_range / volume
    range_per_volume_pct: DistributionStats  # daily_range_pct / volume (normalized)

    # Impact metrics
    impact_per_volume: DistributionStats  # |close - open| / volume
    price_efficiency: DistributionStats  # How controlled the price movement is

    # Volatility context
    daily_range_pct: DistributionStats
    close_position: DistributionStats  # Where close falls in daily range

    # Update policy
    policy: BaselineUpdatePolicy = BaselineUpdatePolicy.LOCKED


@dataclass
class TickerBaseline:
    """
    Complete baseline profile for a single ticker.

    This is the master reference for what "normal" looks like.
    All normalization and deviation calculations must use this baseline.

    CRITICAL DESIGN RULE:
        You cannot classify anything as "unusual" without this baseline existing.
    """

    # Identification
    ticker: str
    baseline_date: date  # When this baseline was computed
    lookback_days: int  # Number of trading days used (typically 63)
    data_start_date: date  # First observation date
    data_end_date: date  # Last observation date

    # Baseline components
    dark_pool: DarkPoolBaseline
    greeks: GreeksBaseline
    price_efficiency: PriceEfficiencyBaseline

    # Quality metrics
    observation_count: int
    missing_data_pct: float  # % of expected data points that were missing

    # Version tracking
    schema_version: str = "1.0"

    def is_valid(self) -> bool:
        """Check if baseline has sufficient data quality."""
        return (
            self.observation_count >= 21  # Minimum 1 month
            and self.missing_data_pct < 30.0  # Max 30% missing data
        )

    def days_since_update(self, as_of: date) -> int:
        """Days since baseline was last computed."""
        return (as_of - self.baseline_date).days

    def needs_refresh(self, as_of: date, max_age_days: int = 63) -> bool:
        """Check if baseline needs to be recomputed."""
        return self.days_since_update(as_of) > max_age_days


@dataclass
class DynamicState:
    """
    Dynamic (rolling) state metrics computed daily.

    These are computed against the LOCKED baseline and updated each day.
    """

    ticker: str
    trade_date: date
    rolling_window: int  # Typically 21 or 63 days

    # Current z-scores (vs baseline)
    dark_share_zscore: float | None = None
    block_intensity_zscore: float | None = None  # block_count * avg_size
    gex_zscore: float | None = None
    dex_zscore: float | None = None
    iv_zscore: float | None = None
    iv_skew_zscore: float | None = None
    price_efficiency_zscore: float | None = None

    # Current percentiles (vs baseline)
    dark_share_pct: float | None = None
    gex_pct: float | None = None
    iv_rank_pct: float | None = None

    # Directional indicators
    gex_sign: int = 0  # 1 = positive, -1 = negative, 0 = neutral
    dex_sign: int = 0


# Type aliases
BaselineProfile: TypeAlias = TickerBaseline
