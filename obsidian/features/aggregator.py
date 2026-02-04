"""
Feature aggregator.

Combines features from all sources into a unified FeatureSet.
"""

import logging
from datetime import date
from typing import Any

from obsidian.core.types import FeatureSet
from obsidian.features.darkpool import DarkPoolFeatures, DarkPoolMetrics
from obsidian.features.greeks import GreeksFeatures, GreeksMetrics
from obsidian.features.price_context import PriceContextFeatures, PriceMetrics


logger = logging.getLogger(__name__)


class FeatureAggregator:
    """
    Aggregates features from all extractors into a unified FeatureSet.

    Coordinates feature extraction from:
    - Dark pool data
    - Greek exposure data
    - Price context data
    """

    def __init__(self) -> None:
        """Initialize feature extractors."""
        self.darkpool = DarkPoolFeatures()
        self.greeks = GreeksFeatures()
        self.price_context = PriceContextFeatures()

    def aggregate(
        self,
        ticker: str,
        trade_date: date,
        darkpool_metrics: DarkPoolMetrics | None = None,
        greeks_metrics: GreeksMetrics | None = None,
        price_metrics: PriceMetrics | None = None,
    ) -> FeatureSet:
        """
        Aggregate all features into a FeatureSet.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date of the features
            darkpool_metrics: Extracted dark pool metrics
            greeks_metrics: Extracted Greek exposure metrics
            price_metrics: Extracted price context metrics

        Returns:
            FeatureSet with all available features
        """
        feature_set = FeatureSet(
            ticker=ticker,
            trade_date=trade_date,
        )

        # Dark pool features
        if darkpool_metrics:
            feature_set.dark_pool_volume = darkpool_metrics.dark_pool_volume
            feature_set.dark_pool_ratio = darkpool_metrics.dark_pool_ratio
            feature_set.block_trade_count = darkpool_metrics.block_trade_count
            feature_set.block_trade_size_avg = darkpool_metrics.avg_block_size
            feature_set.block_premium = darkpool_metrics.block_premium
            feature_set.venue_shift = darkpool_metrics.venue_shift

        # Greek exposure features
        if greeks_metrics:
            feature_set.gex = greeks_metrics.gex
            feature_set.dex = greeks_metrics.dex
            feature_set.vanna = greeks_metrics.vanna
            feature_set.charm = greeks_metrics.charm
            feature_set.iv_atm = greeks_metrics.iv_atm
            feature_set.iv_rank = greeks_metrics.iv_rank
            feature_set.iv_skew = greeks_metrics.iv_skew

        # Price context features
        if price_metrics:
            feature_set.open_price = price_metrics.open_price
            feature_set.high_price = price_metrics.high_price
            feature_set.low_price = price_metrics.low_price
            feature_set.close_price = price_metrics.close_price
            feature_set.volume = price_metrics.volume
            feature_set.price_change_pct = price_metrics.price_change_pct
            feature_set.daily_range_pct = price_metrics.daily_range_pct
            feature_set.volume_vs_avg = price_metrics.volume_vs_avg
            feature_set.price_efficiency = price_metrics.price_efficiency
            feature_set.impact_per_vol = price_metrics.impact_per_vol

        return feature_set

    def from_raw_data(
        self,
        ticker: str,
        trade_date: date,
        darkpool_trades: Any | None = None,  # pd.DataFrame
        greek_data: dict[str, Any] | None = None,
        iv_data: dict[str, Any] | None = None,
        ohlcv: dict[str, Any] | None = None,
        total_volume: int | None = None,
        previous_dark_ratio: float | None = None,
        avg_volume: float | None = None,
    ) -> FeatureSet:
        """
        Extract and aggregate features from raw data.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date of the data
            darkpool_trades: DataFrame with dark pool trades
            greek_data: Dictionary with Greek exposure
            iv_data: Dictionary with IV term structure
            ohlcv: Dictionary with OHLCV data
            total_volume: Total market volume (for dark pool ratio)
            previous_dark_ratio: Previous day's dark pool ratio
            avg_volume: Average volume (for volume_vs_avg)

        Returns:
            FeatureSet with all extracted features
        """
        # Extract dark pool metrics
        darkpool_metrics = None
        if darkpool_trades is not None:
            darkpool_metrics = self.darkpool.extract(
                darkpool_trades,
                total_volume=total_volume,
                previous_ratio=previous_dark_ratio,
            )

        # Extract Greek metrics
        greeks_metrics = None
        if greek_data:
            greeks_metrics = self.greeks.extract(greek_data, iv_data)

        # Extract price metrics
        price_metrics = None
        if ohlcv:
            price_metrics = self.price_context.extract(ohlcv, avg_volume)

        return self.aggregate(
            ticker=ticker,
            trade_date=trade_date,
            darkpool_metrics=darkpool_metrics,
            greeks_metrics=greeks_metrics,
            price_metrics=price_metrics,
        )

    def validate_features(self, features: FeatureSet) -> list[str]:
        """
        Validate feature set for completeness.

        Args:
            features: FeatureSet to validate

        Returns:
            List of missing or invalid features
        """
        issues = []

        # Check required features for regime classification
        if features.gex is None:
            issues.append("Missing GEX")
        if features.dex is None:
            issues.append("Missing DEX")
        if features.dark_pool_ratio is None:
            issues.append("Missing dark pool ratio")
        if features.price_change_pct is None:
            issues.append("Missing price change")

        # Check gamma context features
        if features.price_efficiency is None:
            issues.append("Missing price_efficiency (needed for Gamma+ validation)")
        if features.impact_per_vol is None:
            issues.append("Missing impact_per_vol (needed for Gamma- validation)")

        return issues

    def get_feature_summary(self, features: FeatureSet) -> dict[str, Any]:
        """
        Generate summary of feature values.

        Args:
            features: FeatureSet to summarize

        Returns:
            Dictionary with feature summary
        """
        return {
            "ticker": features.ticker,
            "date": features.trade_date.isoformat(),
            "dark_pool": {
                "ratio": features.dark_pool_ratio,
                "volume": features.dark_pool_volume,
                "block_count": features.block_trade_count,
            },
            "greeks": {
                "gex": features.gex,
                "dex": features.dex,
                "vanna": features.vanna,
                "charm": features.charm,
            },
            "iv": {
                "atm": features.iv_atm,
                "rank": features.iv_rank,
                "skew": features.iv_skew,
            },
            "price": {
                "change_pct": features.price_change_pct,
                "range_pct": features.daily_range_pct,
                "volume_vs_avg": features.volume_vs_avg,
            },
            "gamma_context": {
                "price_efficiency": features.price_efficiency,
                "impact_per_vol": features.impact_per_vol,
            },
        }
