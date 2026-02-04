"""
Dark pool feature extraction.

Extracts features from dark pool trade data including:
- Volume metrics
- Block trade activity
- Venue mix
"""

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from obsidian.core.constants import BLOCK_TRADE_MIN_SHARES


logger = logging.getLogger(__name__)


@dataclass
class DarkPoolMetrics:
    """Container for dark pool metrics."""

    # Volume metrics
    dark_pool_volume: int
    dark_pool_notional: float
    trade_count: int

    # Block trade metrics
    block_trade_count: int
    block_trade_volume: int
    block_premium: float
    avg_trade_size: float
    avg_block_size: float

    # Ratios (requires total volume)
    dark_pool_ratio: float | None = None  # dark / total

    # Venue shift (requires previous day)
    venue_shift: float | None = None  # day-over-day change in ratio

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dark_pool_volume": self.dark_pool_volume,
            "dark_pool_notional": self.dark_pool_notional,
            "trade_count": self.trade_count,
            "block_trade_count": self.block_trade_count,
            "block_trade_volume": self.block_trade_volume,
            "block_premium": self.block_premium,
            "avg_trade_size": self.avg_trade_size,
            "avg_block_size": self.avg_block_size,
            "dark_pool_ratio": self.dark_pool_ratio,
            "venue_shift": self.venue_shift,
        }


class DarkPoolFeatures:
    """
    Extract features from dark pool trade data.

    Source data: Unusual Whales dark pool trades
    Output: Daily aggregated dark pool metrics
    """

    def __init__(self, block_threshold: int = BLOCK_TRADE_MIN_SHARES) -> None:
        """
        Initialize dark pool feature extractor.

        Args:
            block_threshold: Minimum shares for block trade classification
        """
        self.block_threshold = block_threshold

    def extract(
        self,
        trades_df: pd.DataFrame,
        total_volume: int | None = None,
        previous_ratio: float | None = None,
    ) -> DarkPoolMetrics:
        """
        Extract dark pool features from trade data.

        Args:
            trades_df: DataFrame with dark pool trades
            total_volume: Total market volume (for ratio calculation)
            previous_ratio: Previous day's dark pool ratio (for shift)

        Returns:
            DarkPoolMetrics with extracted features
        """
        if trades_df.empty:
            return DarkPoolMetrics(
                dark_pool_volume=0,
                dark_pool_notional=0.0,
                trade_count=0,
                block_trade_count=0,
                block_trade_volume=0,
                block_premium=0.0,
                avg_trade_size=0.0,
                avg_block_size=0.0,
            )

        # Ensure required columns exist
        if "size" not in trades_df.columns:
            logger.warning("Missing 'size' column in trades DataFrame")
            return self._empty_metrics()

        # Total dark pool metrics
        total_dark_volume = int(trades_df["size"].sum())
        total_notional = float(trades_df.get("premium", pd.Series([0])).sum())
        trade_count = len(trades_df)

        # Block trades (large institutional prints)
        blocks = trades_df[trades_df["size"] >= self.block_threshold]
        block_count = len(blocks)
        block_volume = int(blocks["size"].sum()) if not blocks.empty else 0
        block_premium = float(blocks.get("premium", pd.Series([0])).sum()) if not blocks.empty else 0.0

        # Averages
        avg_trade_size = float(total_dark_volume / trade_count) if trade_count > 0 else 0.0
        avg_block_size = float(block_volume / block_count) if block_count > 0 else 0.0

        # Calculate ratio if total volume provided
        dark_pool_ratio = None
        if total_volume and total_volume > 0:
            dark_pool_ratio = (total_dark_volume / total_volume) * 100  # As percentage

        # Calculate venue shift if previous ratio provided
        venue_shift = None
        if dark_pool_ratio is not None and previous_ratio is not None:
            venue_shift = dark_pool_ratio - previous_ratio

        return DarkPoolMetrics(
            dark_pool_volume=total_dark_volume,
            dark_pool_notional=total_notional,
            trade_count=trade_count,
            block_trade_count=block_count,
            block_trade_volume=block_volume,
            block_premium=block_premium,
            avg_trade_size=avg_trade_size,
            avg_block_size=avg_block_size,
            dark_pool_ratio=dark_pool_ratio,
            venue_shift=venue_shift,
        )

    def _empty_metrics(self) -> DarkPoolMetrics:
        """Return empty metrics object."""
        return DarkPoolMetrics(
            dark_pool_volume=0,
            dark_pool_notional=0.0,
            trade_count=0,
            block_trade_count=0,
            block_trade_volume=0,
            block_premium=0.0,
            avg_trade_size=0.0,
            avg_block_size=0.0,
        )

    def calculate_venue_concentration(
        self,
        trades_df: pd.DataFrame,
    ) -> dict[str, float]:
        """
        Calculate volume concentration by market center.

        Args:
            trades_df: DataFrame with dark pool trades

        Returns:
            Dictionary mapping market center to percentage of volume
        """
        if trades_df.empty or "market_center" not in trades_df.columns:
            return {}

        total_volume = trades_df["size"].sum()
        if total_volume == 0:
            return {}

        venue_volume = trades_df.groupby("market_center")["size"].sum()
        return (venue_volume / total_volume * 100).to_dict()

    def calculate_block_timing(
        self,
        trades_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """
        Analyze timing patterns of block trades.

        Args:
            trades_df: DataFrame with dark pool trades

        Returns:
            Dictionary with timing analysis
        """
        if trades_df.empty or "executed_at" not in trades_df.columns:
            return {}

        blocks = trades_df[trades_df["size"] >= self.block_threshold].copy()
        if blocks.empty:
            return {"block_count": 0}

        # Parse timestamps
        blocks["timestamp"] = pd.to_datetime(blocks["executed_at"])
        blocks["hour"] = blocks["timestamp"].dt.hour

        # Distribution by hour
        hourly_dist = blocks.groupby("hour")["size"].sum()

        return {
            "block_count": len(blocks),
            "total_block_volume": int(blocks["size"].sum()),
            "hourly_distribution": hourly_dist.to_dict(),
            "peak_hour": int(hourly_dist.idxmax()) if not hourly_dist.empty else None,
        }
