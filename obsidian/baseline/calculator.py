"""
Baseline Calculator for OBSIDIAN MM.

Computes ticker-specific baseline profiles from historical data.
This is the foundation for all normalization and deviation detection.

USAGE:
    calculator = BaselineCalculator(data_loader)
    baseline = await calculator.compute_baseline("SPY", lookback_days=63)
    storage.save(baseline)
"""

import logging
from datetime import date, timedelta
from typing import Sequence

import numpy as np
import pandas as pd

from obsidian.baseline.types import (
    BaselineUpdatePolicy,
    DarkPoolBaseline,
    DistributionStats,
    DynamicState,
    GreeksBaseline,
    PriceEfficiencyBaseline,
    TickerBaseline,
)
from obsidian.core.constants import DEFAULT_ROLLING_WINDOW, MIN_OBSERVATIONS


logger = logging.getLogger(__name__)


def compute_distribution_stats(
    values: Sequence[float],
    remove_outliers: bool = False,
    outlier_std: float = 3.0,
) -> DistributionStats | None:
    """
    Compute distribution statistics for a series of values.

    Args:
        values: Sequence of numeric values
        remove_outliers: Whether to remove outliers before computing stats
        outlier_std: Number of standard deviations for outlier detection

    Returns:
        DistributionStats or None if insufficient data
    """
    arr = np.array([v for v in values if v is not None and not np.isnan(v)])

    if len(arr) < MIN_OBSERVATIONS:
        return None

    if remove_outliers and len(arr) > MIN_OBSERVATIONS:
        mean = np.mean(arr)
        std = np.std(arr)
        if std > 0:
            mask = np.abs(arr - mean) <= outlier_std * std
            arr = arr[mask]
            if len(arr) < MIN_OBSERVATIONS:
                return None

    return DistributionStats(
        mean=float(np.mean(arr)),
        std=float(np.std(arr)),
        median=float(np.median(arr)),
        mad=float(np.median(np.abs(arr - np.median(arr)))),
        p25=float(np.percentile(arr, 25)),
        p75=float(np.percentile(arr, 75)),
        p90=float(np.percentile(arr, 90)),
        p95=float(np.percentile(arr, 95)),
        min_val=float(np.min(arr)),
        max_val=float(np.max(arr)),
        n_observations=len(arr),
    )


class BaselineCalculator:
    """
    Calculates ticker-specific baseline profiles.

    The baseline is computed from historical data and represents
    what "normal" looks like for an instrument. All subsequent
    normalization and deviation detection references this baseline.

    DESIGN PRINCIPLES:
        1. Baselines are instrument-specific, not universal
        2. Sufficient history required (minimum 21 days)
        3. Missing data is tracked and reported
        4. No optimization or machine learning
    """

    def __init__(
        self,
        lookback_days: int = DEFAULT_ROLLING_WINDOW,
        min_observations: int = MIN_OBSERVATIONS,
    ):
        """
        Initialize baseline calculator.

        Args:
            lookback_days: Number of trading days for baseline (default 63)
            min_observations: Minimum observations required (default 21)
        """
        self.lookback_days = lookback_days
        self.min_observations = min_observations

    def compute_baseline(
        self,
        ticker: str,
        historical_data: pd.DataFrame,
        as_of_date: date | None = None,
    ) -> TickerBaseline | None:
        """
        Compute complete baseline profile for a ticker.

        Args:
            ticker: Stock ticker symbol
            historical_data: DataFrame with columns:
                - date: trading date
                - dark_pool_volume, total_volume, dark_pool_ratio
                - block_trade_count, block_trade_size_avg, block_premium
                - venue_shift
                - gex, dex, vanna, charm
                - iv_atm, iv_skew, iv_rank
                - price_change_pct, daily_range_pct
                - price_efficiency, impact_per_vol
            as_of_date: Reference date for baseline (default: latest in data)

        Returns:
            TickerBaseline or None if insufficient data
        """
        if historical_data.empty:
            logger.warning(f"No historical data for {ticker}")
            return None

        # Ensure date column
        if "date" not in historical_data.columns:
            logger.error(f"Historical data missing 'date' column for {ticker}")
            return None

        df = historical_data.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date

        # Filter to lookback window
        if as_of_date is None:
            as_of_date = df["date"].max()

        start_date = as_of_date - timedelta(days=int(self.lookback_days * 1.5))  # Buffer for weekends
        df = df[(df["date"] >= start_date) & (df["date"] <= as_of_date)]
        df = df.sort_values("date").tail(self.lookback_days)

        if len(df) < self.min_observations:
            logger.warning(
                f"Insufficient data for {ticker}: {len(df)} < {self.min_observations} observations"
            )
            return None

        # Compute baseline components
        dark_pool = self._compute_dark_pool_baseline(df)
        greeks = self._compute_greeks_baseline(df)
        price_eff = self._compute_price_efficiency_baseline(df)

        if dark_pool is None or greeks is None or price_eff is None:
            logger.warning(f"Failed to compute all baseline components for {ticker}")
            return None

        # Calculate data quality
        expected_fields = [
            "dark_pool_ratio", "gex", "dex", "price_efficiency",
            "daily_range_pct", "block_trade_count"
        ]
        missing_count = sum(
            df[col].isna().sum() if col in df.columns else len(df)
            for col in expected_fields
        )
        total_expected = len(expected_fields) * len(df)
        missing_pct = (missing_count / total_expected) * 100 if total_expected > 0 else 100.0

        return TickerBaseline(
            ticker=ticker,
            baseline_date=as_of_date,
            lookback_days=self.lookback_days,
            data_start_date=df["date"].min(),
            data_end_date=df["date"].max(),
            dark_pool=dark_pool,
            greeks=greeks,
            price_efficiency=price_eff,
            observation_count=len(df),
            missing_data_pct=missing_pct,
        )

    def _compute_dark_pool_baseline(self, df: pd.DataFrame) -> DarkPoolBaseline | None:
        """Compute dark pool baseline from historical data."""
        # Dark share
        dark_share = None
        if "dark_pool_ratio" in df.columns:
            dark_share = compute_distribution_stats(df["dark_pool_ratio"].tolist())

        if dark_share is None:
            # Try computing from volumes
            if "dark_pool_volume" in df.columns and "total_volume" in df.columns:
                ratios = df["dark_pool_volume"] / df["total_volume"].replace(0, np.nan) * 100
                dark_share = compute_distribution_stats(ratios.tolist())

        if dark_share is None:
            logger.warning("Cannot compute dark pool baseline: missing dark_pool_ratio")
            return None

        # Typical range (mean ± 1.5σ, bounded to 0-100)
        typical_low = max(0, dark_share.mean - 1.5 * dark_share.std)
        typical_high = min(100, dark_share.mean + 1.5 * dark_share.std)

        # Block activity
        block_count = None
        if "block_trade_count" in df.columns:
            block_count = compute_distribution_stats(df["block_trade_count"].tolist())

        if block_count is None:
            # Create default for instruments without block data
            block_count = DistributionStats(
                mean=0, std=0, median=0, mad=0,
                p25=0, p75=0, p90=0, p95=0,
                min_val=0, max_val=0, n_observations=len(df)
            )

        block_size = None
        if "block_trade_size_avg" in df.columns:
            block_size = compute_distribution_stats(
                df["block_trade_size_avg"].dropna().tolist(),
                remove_outliers=True
            )

        if block_size is None:
            block_size = DistributionStats(
                mean=0, std=0, median=0, mad=0,
                p25=0, p75=0, p90=0, p95=0,
                min_val=0, max_val=0, n_observations=len(df)
            )

        block_premium = None
        if "block_premium" in df.columns:
            block_premium = compute_distribution_stats(
                df["block_premium"].dropna().tolist(),
                remove_outliers=True
            )

        if block_premium is None:
            block_premium = DistributionStats(
                mean=0, std=0, median=0, mad=0,
                p25=0, p75=0, p90=0, p95=0,
                min_val=0, max_val=0, n_observations=len(df)
            )

        # Venue shift
        venue_shift = None
        if "venue_shift" in df.columns:
            venue_shift = compute_distribution_stats(df["venue_shift"].dropna().tolist())

        if venue_shift is None:
            venue_shift = DistributionStats(
                mean=0, std=1, median=0, mad=0,
                p25=-0.5, p75=0.5, p90=1, p95=1.5,
                min_val=-5, max_val=5, n_observations=len(df)
            )

        # Dark pool volume (absolute)
        dark_volume = None
        if "dark_pool_volume" in df.columns:
            dark_volume = compute_distribution_stats(
                df["dark_pool_volume"].dropna().tolist(),
                remove_outliers=True
            )

        return DarkPoolBaseline(
            dark_share=dark_share,
            dark_share_typical_range=(typical_low, typical_high),
            dark_volume=dark_volume,
            daily_block_count=block_count,
            block_size=block_size,
            block_premium=block_premium,
            venue_shift=venue_shift,
            policy=BaselineUpdatePolicy.LOCKED,
        )

    def _compute_greeks_baseline(self, df: pd.DataFrame) -> GreeksBaseline | None:
        """Compute Greeks baseline from historical data."""
        # GEX
        gex = None
        gex_positive_pct = 50.0
        gex_negative_pct = 50.0

        if "gex" in df.columns:
            gex_values = df["gex"].dropna()
            gex = compute_distribution_stats(gex_values.tolist())

            if len(gex_values) > 0:
                gex_positive_pct = (gex_values > 0).mean() * 100
                gex_negative_pct = (gex_values < 0).mean() * 100

        if gex is None:
            logger.warning("Cannot compute Greeks baseline: missing gex")
            return None

        # DEX
        dex = None
        if "dex" in df.columns:
            dex = compute_distribution_stats(df["dex"].dropna().tolist())

        if dex is None:
            # Default neutral DEX
            dex = DistributionStats(
                mean=0, std=1e6, median=0, mad=1e6,
                p25=-1e6, p75=1e6, p90=2e6, p95=3e6,
                min_val=-1e7, max_val=1e7, n_observations=len(df)
            )

        # Higher-order Greeks (optional)
        vanna = None
        if "vanna" in df.columns:
            vanna = compute_distribution_stats(df["vanna"].dropna().tolist())

        charm = None
        if "charm" in df.columns:
            charm = compute_distribution_stats(df["charm"].dropna().tolist())

        # IV metrics
        iv_atm = None
        if "iv_atm" in df.columns:
            iv_atm = compute_distribution_stats(df["iv_atm"].dropna().tolist())

        iv_atm_daily_change = None
        if "iv_atm" in df.columns:
            iv_changes = df["iv_atm"].diff().dropna()
            if len(iv_changes) >= self.min_observations:
                iv_atm_daily_change = compute_distribution_stats(iv_changes.tolist())

        iv_skew = None
        if "iv_skew" in df.columns:
            iv_skew = compute_distribution_stats(df["iv_skew"].dropna().tolist())

        iv_rank = None
        if "iv_rank" in df.columns:
            iv_rank = compute_distribution_stats(df["iv_rank"].dropna().tolist())

        return GreeksBaseline(
            gex=gex,
            gex_positive_pct=gex_positive_pct,
            gex_negative_pct=gex_negative_pct,
            dex=dex,
            vanna=vanna,
            charm=charm,
            iv_atm=iv_atm,
            iv_atm_daily_change=iv_atm_daily_change,
            iv_skew=iv_skew,
            iv_rank=iv_rank,
            policy=BaselineUpdatePolicy.LOCKED,
        )

    def _compute_price_efficiency_baseline(self, df: pd.DataFrame) -> PriceEfficiencyBaseline | None:
        """Compute price efficiency baseline from historical data."""
        # Range per volume
        range_per_volume = None
        if "daily_range_pct" in df.columns and "volume" in df.columns:
            # Normalize by volume (log scale for large volumes)
            with np.errstate(divide="ignore", invalid="ignore"):
                rpv = df["daily_range_pct"] / np.log1p(df["volume"])
                rpv = rpv.replace([np.inf, -np.inf], np.nan).dropna()
            if len(rpv) >= self.min_observations:
                range_per_volume = compute_distribution_stats(rpv.tolist())

        if range_per_volume is None:
            # Default
            range_per_volume = DistributionStats(
                mean=0, std=1, median=0, mad=0.5,
                p25=-0.5, p75=0.5, p90=1, p95=1.5,
                min_val=-5, max_val=5, n_observations=len(df)
            )

        # Impact per volume
        impact_per_volume = None
        if "impact_per_vol" in df.columns:
            impact_per_volume = compute_distribution_stats(
                df["impact_per_vol"].dropna().tolist()
            )

        if impact_per_volume is None:
            impact_per_volume = DistributionStats(
                mean=0, std=1, median=0, mad=0.5,
                p25=-0.5, p75=0.5, p90=1, p95=1.5,
                min_val=-5, max_val=5, n_observations=len(df)
            )

        # Price efficiency
        price_efficiency = None
        if "price_efficiency" in df.columns:
            price_efficiency = compute_distribution_stats(
                df["price_efficiency"].dropna().tolist()
            )

        if price_efficiency is None:
            price_efficiency = DistributionStats(
                mean=50, std=20, median=50, mad=15,
                p25=35, p75=65, p90=80, p95=90,
                min_val=0, max_val=100, n_observations=len(df)
            )

        # Daily range
        daily_range_pct = None
        if "daily_range_pct" in df.columns:
            daily_range_pct = compute_distribution_stats(
                df["daily_range_pct"].dropna().tolist()
            )

        if daily_range_pct is None:
            daily_range_pct = DistributionStats(
                mean=1.0, std=0.5, median=0.9, mad=0.3,
                p25=0.6, p75=1.3, p90=1.8, p95=2.2,
                min_val=0.1, max_val=5.0, n_observations=len(df)
            )

        # Close position (where close falls in daily range)
        close_position = None
        if all(c in df.columns for c in ["close_price", "low_price", "high_price"]):
            pos = (df["close_price"] - df["low_price"]) / (
                df["high_price"] - df["low_price"]
            ).replace(0, np.nan)
            pos = pos.dropna()
            if len(pos) >= self.min_observations:
                close_position = compute_distribution_stats(pos.tolist())

        if close_position is None:
            close_position = DistributionStats(
                mean=0.5, std=0.2, median=0.5, mad=0.15,
                p25=0.35, p75=0.65, p90=0.8, p95=0.9,
                min_val=0, max_val=1, n_observations=len(df)
            )

        return PriceEfficiencyBaseline(
            range_per_volume=range_per_volume,
            range_per_volume_pct=range_per_volume,  # Same metric, different name
            impact_per_volume=impact_per_volume,
            price_efficiency=price_efficiency,
            daily_range_pct=daily_range_pct,
            close_position=close_position,
            policy=BaselineUpdatePolicy.LOCKED,
        )

    def compute_dynamic_state(
        self,
        ticker: str,
        current_features: dict,
        baseline: TickerBaseline,
        trade_date: date,
    ) -> DynamicState:
        """
        Compute dynamic (rolling) state metrics against the locked baseline.

        This is computed daily and represents current deviation from normal.

        Args:
            ticker: Stock ticker symbol
            current_features: Today's feature values
            baseline: Locked baseline profile
            trade_date: Current trading date

        Returns:
            DynamicState with z-scores and percentiles
        """
        state = DynamicState(
            ticker=ticker,
            trade_date=trade_date,
            rolling_window=self.lookback_days,
        )

        # Dark share z-score
        dark_ratio = current_features.get("dark_pool_ratio")
        if dark_ratio is not None and baseline.dark_pool.dark_share:
            state = DynamicState(
                **{**state.__dict__, "dark_share_zscore": baseline.dark_pool.dark_share.zscore(dark_ratio)}
            )

        # Block intensity z-score
        block_count = current_features.get("block_trade_count", 0)
        block_size = current_features.get("block_trade_size_avg", 0)
        if block_count and block_size:
            block_intensity = block_count * block_size
            baseline_intensity = (
                baseline.dark_pool.daily_block_count.mean *
                baseline.dark_pool.block_size.mean
            )
            if baseline_intensity > 0:
                intensity_std = baseline_intensity * 0.5  # Rough estimate
                state = DynamicState(
                    **{**state.__dict__, "block_intensity_zscore": (block_intensity - baseline_intensity) / intensity_std}
                )

        # GEX z-score
        gex = current_features.get("gex")
        if gex is not None and baseline.greeks.gex:
            gex_z = baseline.greeks.gex.zscore(gex)
            gex_pct = baseline.greeks.gex.percentile_rank(gex)
            gex_sign = 1 if gex > 0 else (-1 if gex < 0 else 0)
            state = DynamicState(
                **{**state.__dict__,
                   "gex_zscore": gex_z,
                   "gex_pct": gex_pct,
                   "gex_sign": gex_sign}
            )

        # DEX z-score
        dex = current_features.get("dex")
        if dex is not None and baseline.greeks.dex:
            dex_z = baseline.greeks.dex.zscore(dex)
            dex_sign = 1 if dex > 0 else (-1 if dex < 0 else 0)
            state = DynamicState(
                **{**state.__dict__,
                   "dex_zscore": dex_z,
                   "dex_sign": dex_sign}
            )

        # IV z-score
        iv_atm = current_features.get("iv_atm")
        if iv_atm is not None and baseline.greeks.iv_atm:
            state = DynamicState(
                **{**state.__dict__, "iv_zscore": baseline.greeks.iv_atm.zscore(iv_atm)}
            )

        # IV skew z-score
        iv_skew = current_features.get("iv_skew")
        if iv_skew is not None and baseline.greeks.iv_skew:
            state = DynamicState(
                **{**state.__dict__, "iv_skew_zscore": baseline.greeks.iv_skew.zscore(iv_skew)}
            )

        # Price efficiency z-score
        price_eff = current_features.get("price_efficiency")
        if price_eff is not None and baseline.price_efficiency.price_efficiency:
            state = DynamicState(
                **{**state.__dict__,
                   "price_efficiency_zscore": baseline.price_efficiency.price_efficiency.zscore(price_eff)}
            )

        return state
