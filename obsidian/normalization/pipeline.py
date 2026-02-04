"""
Normalization pipeline.

Orchestrates normalization of all features using configured methods.

BASELINE INTEGRATION:
    The pipeline now supports two normalization modes:
    1. BASELINE MODE: Uses locked baseline statistics (recommended)
    2. ROLLING MODE: Uses rolling window statistics (legacy)

    Baseline mode ensures all deviations are measured against
    instrument-specific "normal" levels.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian.core.config import NormalizationConfig, load_config
from obsidian.core.constants import DEFAULT_ROLLING_WINDOW, MIN_OBSERVATIONS
from obsidian.core.exceptions import InsufficientDataError, NormalizationError
from obsidian.core.types import FeatureSet, NormalizationMethod
from obsidian.normalization.methods import (
    log_transform,
    minmax_normalize,
    percentile_normalize,
    zscore_normalize,
)
from obsidian.normalization.rolling import MultiFeatureRollingCalculator, RollingStats


logger = logging.getLogger(__name__)


# Try to import baseline types (may not be available in all installations)
try:
    from obsidian.baseline.types import TickerBaseline, DistributionStats
    BASELINE_AVAILABLE = True
except ImportError:
    BASELINE_AVAILABLE = False
    TickerBaseline = None
    DistributionStats = None


class NormalizationPipeline:
    """
    Pipeline for normalizing features.

    Loads configuration from YAML and applies appropriate normalization
    method to each feature based on its config.

    BASELINE MODE:
        When a baseline is provided, normalization uses the baseline's
        locked statistics instead of rolling window calculations.
        This ensures all deviations are measured against the instrument's
        established "normal" levels.

    ROLLING MODE (legacy):
        Uses rolling window statistics computed from recent history.
        Still available for backwards compatibility.
    """

    def __init__(
        self,
        config: NormalizationConfig | None = None,
        history_dir: Path | None = None,
        baseline: "TickerBaseline | None" = None,
    ) -> None:
        """
        Initialize normalization pipeline.

        Args:
            config: Normalization configuration (loaded from YAML if not provided)
            history_dir: Directory containing historical processed data
            baseline: Ticker baseline for baseline-based normalization (recommended)
        """
        self.config = config or load_config("normalization")
        self.history_dir = history_dir
        self.baseline = baseline

        # Initialize rolling calculators (used as fallback or in rolling mode)
        self._rolling = MultiFeatureRollingCalculator(
            feature_configs=self.config._config.get("normalization", {}).get("features", {}),
            default_window=self.config.default_window,
            min_observations=self.config.min_observations,
        )

        # Track whether history has been loaded
        self._history_loaded = False

        # Log mode
        if baseline is not None:
            logger.info(f"Normalization pipeline using BASELINE mode for {baseline.ticker}")
        else:
            logger.info("Normalization pipeline using ROLLING mode (no baseline provided)")

    def load_history(
        self,
        ticker: str,
        up_to_date: date,
        days: int | None = None,
    ) -> int:
        """
        Load historical feature data for normalization.

        Args:
            ticker: Stock ticker symbol
            up_to_date: Load history up to (but not including) this date
            days: Number of days to load (defaults to config window)

        Returns:
            Number of days loaded
        """
        if self.history_dir is None:
            logger.warning("No history directory configured")
            return 0

        days = days or self.config.default_window

        # Find historical feature files
        features_dir = self.history_dir / "features" / ticker
        if not features_dir.exists():
            logger.warning(f"No historical features for {ticker}")
            return 0

        # Load parquet files
        files = sorted(features_dir.glob("*.parquet"))
        loaded = 0

        for f in files[-days:]:
            try:
                file_date = date.fromisoformat(f.stem)
                if file_date >= up_to_date:
                    continue

                df = pd.read_parquet(f)
                if df.empty:
                    continue

                # Add each feature value to rolling calculator
                row = df.iloc[0]
                feature_values = self._extract_feature_values(row.to_dict())
                self._rolling.add_all(feature_values)
                loaded += 1

            except Exception as e:
                logger.warning(f"Failed to load {f}: {e}")
                continue

        self._history_loaded = loaded > 0
        logger.info(f"Loaded {loaded} days of history for {ticker}")
        return loaded

    def _extract_feature_values(self, data: dict[str, Any]) -> dict[str, float]:
        """Extract raw feature values from data dict."""
        return {
            "dark_pool_ratio": data.get("dark_pool_ratio"),
            "dark_pool_volume": data.get("dark_pool_volume"),
            "block_trade_count": data.get("block_trade_count"),
            "gex": data.get("gex"),
            "dex": data.get("dex"),
            "vanna": data.get("vanna"),
            "charm": data.get("charm"),
            "iv_atm": data.get("iv_atm"),
            "iv_skew": data.get("iv_skew"),
            "price_change_pct": data.get("price_change_pct"),
            "daily_range_pct": data.get("daily_range_pct"),
            "price_efficiency": data.get("price_efficiency"),
            "impact_per_vol": data.get("impact_per_vol"),
            "venue_shift": data.get("venue_shift"),
        }

    def normalize(
        self,
        features: FeatureSet,
        require_history: bool = True,
    ) -> FeatureSet:
        """
        Normalize all features in a FeatureSet.

        Args:
            features: FeatureSet with raw features
            require_history: Raise error if insufficient history

        Returns:
            FeatureSet with normalized values added to .normalized dict
        """
        # Extract raw values
        raw_values = self._extract_feature_values(features.to_dict())

        # Add to rolling calculators
        self._rolling.add_all(raw_values)

        # Check if we have enough history
        ready_features = self._rolling.get_ready_features()
        if require_history and len(ready_features) == 0:
            raise InsufficientDataError(
                f"Insufficient history for normalization",
                required=self.config.min_observations,
                available=0,
            )

        # Normalize each feature
        normalized = {}

        for feature, raw_value in raw_values.items():
            if raw_value is None:
                continue

            try:
                norm_value = self._normalize_feature(feature, raw_value)
                if norm_value is not None:
                    # Store with appropriate suffix
                    config = self.config.get_feature_config(feature)
                    method = config.get("method", "zscore")

                    if method == "zscore":
                        normalized[f"{feature}_zscore"] = norm_value
                    elif method == "percentile":
                        normalized[f"{feature}_pct"] = norm_value
                    elif method == "minmax":
                        normalized[f"{feature}_norm"] = norm_value
                    elif method == "passthrough":
                        normalized[feature] = norm_value

            except Exception as e:
                logger.warning(f"Failed to normalize {feature}: {e}")
                continue

        # Update feature set
        features.normalized = normalized
        return features

    def _normalize_feature(
        self,
        feature: str,
        value: float,
    ) -> float | None:
        """
        Normalize a single feature value.

        Uses BASELINE statistics if available, otherwise falls back to
        rolling window statistics.

        Args:
            feature: Feature name
            value: Raw value

        Returns:
            Normalized value or None if insufficient data
        """
        config = self.config.get_feature_config(feature)
        method = config.get("method", "zscore")

        # Check if log transform needed
        if config.get("log_transform", False):
            value = log_transform(value)

        # Try baseline normalization first
        if self.baseline is not None and BASELINE_AVAILABLE:
            baseline_stats = self._get_baseline_stats(feature)
            if baseline_stats is not None:
                return self._normalize_with_baseline(value, baseline_stats, method, config)

        # Fall back to rolling stats
        stats = self._rolling.get_stats(feature)
        if not stats.is_valid:
            return None

        # Apply normalization method
        if method == NormalizationMethod.ZSCORE.value:
            clip = config.get("clip_outliers", True)
            clip_std = config.get("outlier_std", 3.0) if clip else None
            return zscore_normalize(value, stats.mean, stats.std, clip_std)

        elif method == NormalizationMethod.PERCENTILE.value:
            history = self._rolling.get_values(feature)
            return percentile_normalize(value, history)

        elif method == NormalizationMethod.MINMAX.value:
            return minmax_normalize(value, stats.min, stats.max)

        elif method == NormalizationMethod.PASSTHROUGH.value:
            return value

        else:
            logger.warning(f"Unknown normalization method: {method}")
            return None

    def _get_baseline_stats(self, feature: str) -> "DistributionStats | None":
        """
        Get baseline statistics for a feature.

        Maps feature names to baseline distribution stats.
        """
        if self.baseline is None:
            return None

        # Feature -> Baseline mapping
        mapping = {
            # Dark pool features
            "dark_pool_ratio": self.baseline.dark_pool.dark_share,
            "dark_pool_volume": self.baseline.dark_pool.dark_volume,
            "block_trade_count": self.baseline.dark_pool.daily_block_count,
            "block_trade_size_avg": self.baseline.dark_pool.block_size,
            "block_premium": self.baseline.dark_pool.block_premium,
            "venue_shift": self.baseline.dark_pool.venue_shift,
            # Greek features
            "gex": self.baseline.greeks.gex,
            "dex": self.baseline.greeks.dex,
            "vanna": self.baseline.greeks.vanna,
            "charm": self.baseline.greeks.charm,
            "iv_atm": self.baseline.greeks.iv_atm,
            "iv_skew": self.baseline.greeks.iv_skew,
            "iv_rank": self.baseline.greeks.iv_rank,
            # Price efficiency features
            "daily_range_pct": self.baseline.price_efficiency.daily_range_pct,
            "price_efficiency": self.baseline.price_efficiency.price_efficiency,
            "impact_per_vol": self.baseline.price_efficiency.impact_per_volume,
        }

        return mapping.get(feature)

    def _normalize_with_baseline(
        self,
        value: float,
        stats: "DistributionStats",
        method: str,
        config: dict,
    ) -> float | None:
        """
        Normalize using baseline statistics.

        Args:
            value: Raw value to normalize
            stats: Baseline distribution statistics
            method: Normalization method
            config: Feature configuration

        Returns:
            Normalized value
        """
        if method == NormalizationMethod.ZSCORE.value:
            clip = config.get("clip_outliers", True)
            clip_std = config.get("outlier_std", 3.0) if clip else None
            return zscore_normalize(value, stats.mean, stats.std, clip_std)

        elif method == NormalizationMethod.PERCENTILE.value:
            # Use baseline's percentile estimation
            return stats.percentile_rank(value)

        elif method == NormalizationMethod.MINMAX.value:
            return minmax_normalize(value, stats.min_val, stats.max_val)

        elif method == NormalizationMethod.PASSTHROUGH.value:
            return value

        return None

    def get_normalization_summary(self) -> dict[str, Any]:
        """
        Get summary of normalization state.

        Returns:
            Dictionary with normalization status per feature
        """
        summary = {
            "mode": "baseline" if self.baseline is not None else "rolling",
            "ready_features": self._rolling.get_ready_features(),
            "history_loaded": self._history_loaded,
            "feature_status": {},
        }

        # Add baseline info if available
        if self.baseline is not None:
            summary["baseline"] = {
                "ticker": self.baseline.ticker,
                "baseline_date": self.baseline.baseline_date.isoformat(),
                "observation_count": self.baseline.observation_count,
                "valid": self.baseline.is_valid(),
            }

        for feature in self._extract_feature_values({}).keys():
            # Check baseline first
            baseline_stats = self._get_baseline_stats(feature) if self.baseline else None

            if baseline_stats is not None:
                summary["feature_status"][feature] = {
                    "source": "baseline",
                    "ready": True,
                    "mean": baseline_stats.mean,
                    "std": baseline_stats.std,
                    "n_observations": baseline_stats.n_observations,
                }
            else:
                stats = self._rolling.get_stats(feature)
                summary["feature_status"][feature] = {
                    "source": "rolling",
                    "count": stats.count,
                    "ready": self._rolling.is_ready(feature),
                    "mean": stats.mean if stats.is_valid else None,
                    "std": stats.std if stats.is_valid else None,
                }

        return summary
