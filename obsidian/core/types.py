"""
Core type definitions for OBSIDIAN MM.

Defines enums, dataclasses, and type aliases used throughout the system.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TypeAlias

import pandas as pd


class RegimeLabel(str, Enum):
    """
    Market-maker regime labels.

    Ordered by classification priority (lower = higher priority).

    GUARDRAIL: UNDETERMINED is assigned when data is insufficient.
    This is preferable to guessing - false negatives over false confidence.
    """

    GAMMA_POSITIVE_CONTROL = "Gamma+ Control"
    GAMMA_NEGATIVE_VACUUM = "Gamma- Liquidity Vacuum"
    DARK_DOMINANT_ACCUMULATION = "Dark-Dominant Accumulation"
    ABSORPTION_LIKE = "Absorption-like"
    DISTRIBUTION_LIKE = "Distribution-like"
    NEUTRAL = "Neutral / Mixed"
    UNDETERMINED = "Undetermined"  # GUARDRAIL: Assigned when data insufficient

    @property
    def priority(self) -> int:
        """Return classification priority (lower = checked first)."""
        priorities = {
            RegimeLabel.GAMMA_POSITIVE_CONTROL: 1,
            RegimeLabel.GAMMA_NEGATIVE_VACUUM: 2,
            RegimeLabel.DARK_DOMINANT_ACCUMULATION: 3,
            RegimeLabel.ABSORPTION_LIKE: 4,
            RegimeLabel.DISTRIBUTION_LIKE: 5,
            RegimeLabel.NEUTRAL: 99,
            RegimeLabel.UNDETERMINED: 100,  # Never matched by rules
        }
        return priorities[self]

    @property
    def is_determinable(self) -> bool:
        """Whether this regime represents a determined state."""
        return self != RegimeLabel.UNDETERMINED


class NormalizationMethod(str, Enum):
    """Available normalization methods."""

    ZSCORE = "zscore"
    PERCENTILE = "percentile"
    MINMAX = "minmax"
    PASSTHROUGH = "passthrough"


class UnusualnessLevel(str, Enum):
    """Human-readable unusualness levels."""

    VERY_NORMAL = "Very Normal"
    NORMAL = "Normal"
    SLIGHTLY_UNUSUAL = "Slightly Unusual"
    UNUSUAL = "Unusual"
    HIGHLY_UNUSUAL = "Highly Unusual"

    @classmethod
    def from_score(cls, score: float) -> "UnusualnessLevel":
        """Convert numeric score to level."""
        if score < 20:
            return cls.VERY_NORMAL
        elif score < 40:
            return cls.NORMAL
        elif score < 60:
            return cls.SLIGHTLY_UNUSUAL
        elif score < 80:
            return cls.UNUSUAL
        else:
            return cls.HIGHLY_UNUSUAL


@dataclass(frozen=True)
class TopDriver:
    """A top contributing feature to a score or regime."""

    feature: str
    zscore: float
    contribution_pct: float
    direction: str  # "elevated" or "depressed"

    @property
    def magnitude(self) -> float:
        """Absolute z-score magnitude."""
        return abs(self.zscore)


@dataclass(frozen=True)
class RegimeResult:
    """Result of regime classification for a single observation."""

    ticker: str
    trade_date: date
    label: RegimeLabel
    confidence: float  # 0.0 to 1.0
    explanation: str
    top_drivers: tuple[TopDriver, ...]
    raw_features: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "date": self.trade_date.isoformat(),
            "regime": self.label.value,
            "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
            "top_drivers": [
                {
                    "feature": d.feature,
                    "zscore": round(d.zscore, 2),
                    "contribution_pct": round(d.contribution_pct, 1),
                    "direction": d.direction,
                }
                for d in self.top_drivers
            ],
        }


@dataclass(frozen=True)
class ScoreComponent:
    """A component of the unusualness score."""

    name: str
    weight: float
    zscore: float
    contribution: float  # weight * |zscore|

    @property
    def contribution_pct(self) -> float:
        """Contribution as percentage of total score."""
        return self.contribution * 100


@dataclass(frozen=True)
class UnusualnessResult:
    """Result of unusualness score calculation."""

    ticker: str
    trade_date: date
    score: float  # 0-100
    raw_score: float  # Pre-normalized
    level: UnusualnessLevel
    explanation: str
    components: tuple[ScoreComponent, ...]
    top_drivers: tuple[TopDriver, ...]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "date": self.trade_date.isoformat(),
            "score": round(self.score, 1),
            "raw_score": round(self.raw_score, 4),
            "level": self.level.value,
            "explanation": self.explanation,
            "components": [
                {
                    "name": c.name,
                    "weight": c.weight,
                    "zscore": round(c.zscore, 2),
                    "contribution": round(c.contribution, 4),
                }
                for c in self.components
            ],
            "top_drivers": [
                {
                    "feature": d.feature,
                    "zscore": round(d.zscore, 2),
                    "direction": d.direction,
                }
                for d in self.top_drivers
            ],
        }


@dataclass
class FeatureSet:
    """
    Complete feature set for a ticker on a given date.

    Contains both raw and normalized features.
    """

    ticker: str
    trade_date: date

    # Dark pool features
    dark_pool_volume: float | None = None
    dark_pool_ratio: float | None = None  # 0-100 percentage
    block_trade_count: int | None = None
    block_trade_size_avg: float | None = None
    block_premium: float | None = None

    # Greek exposure features
    gex: float | None = None
    dex: float | None = None
    vanna: float | None = None
    charm: float | None = None

    # IV features
    iv_atm: float | None = None
    iv_rank: float | None = None
    iv_skew: float | None = None
    iv_term_slope: float | None = None

    # Flow features
    call_volume: float | None = None
    put_volume: float | None = None
    call_put_ratio: float | None = None
    net_premium: float | None = None

    # Price context features
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    volume: float | None = None
    price_change_pct: float | None = None
    daily_range_pct: float | None = None
    volume_vs_avg: float | None = None

    # Gamma context features (for regime validation)
    price_efficiency: float | None = None
    impact_per_vol: float | None = None

    # Venue mix features
    venue_shift: float | None = None

    # Normalized versions (suffixed with _zscore or _pct)
    normalized: dict[str, float] = field(default_factory=dict)

    def to_series(self) -> pd.Series:
        """Convert to pandas Series for classification."""
        data = {
            # Raw features needed for regime classification
            "dark_pool_ratio_pct": self.dark_pool_ratio,
            "price_change_pct": self.price_change_pct,
            # Normalized features
            **{k: v for k, v in self.normalized.items()},
        }
        return pd.Series(data)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "ticker": self.ticker,
            "date": self.trade_date.isoformat(),
            "dark_pool_volume": self.dark_pool_volume,
            "dark_pool_ratio": self.dark_pool_ratio,
            "block_trade_count": self.block_trade_count,
            "block_trade_size_avg": self.block_trade_size_avg,
            "gex": self.gex,
            "dex": self.dex,
            "vanna": self.vanna,
            "charm": self.charm,
            "iv_atm": self.iv_atm,
            "iv_rank": self.iv_rank,
            "iv_skew": self.iv_skew,
            "price_change_pct": self.price_change_pct,
            "daily_range_pct": self.daily_range_pct,
            "price_efficiency": self.price_efficiency,
            "impact_per_vol": self.impact_per_vol,
            "venue_shift": self.venue_shift,
            "normalized": self.normalized,
        }


# Type aliases for clarity
Ticker: TypeAlias = str
TradeDate: TypeAlias = date
ZScore: TypeAlias = float
Percentile: TypeAlias = float  # 0-100
