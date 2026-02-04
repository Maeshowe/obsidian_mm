"""
Baseline Storage for OBSIDIAN MM.

Persists and retrieves ticker-specific baseline profiles.
Baselines are stored as JSON files for human readability and easy inspection.

Storage structure:
    data/baselines/
    ├── SPY.json
    ├── QQQ.json
    └── ...
"""

import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from obsidian.baseline.types import (
    BaselineUpdatePolicy,
    DarkPoolBaseline,
    DistributionStats,
    GreeksBaseline,
    PriceEfficiencyBaseline,
    TickerBaseline,
)


logger = logging.getLogger(__name__)


class BaselineStorage:
    """
    Persistent storage for ticker baselines.

    Baselines are stored as JSON files for:
    - Human readability (can inspect what "normal" means)
    - Easy version control
    - Simple debugging
    """

    def __init__(self, base_dir: Path | str = "data/baselines"):
        """
        Initialize baseline storage.

        Args:
            base_dir: Directory to store baseline files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _baseline_path(self, ticker: str) -> Path:
        """Get path for a ticker's baseline file."""
        return self.base_dir / f"{ticker.upper()}.json"

    def exists(self, ticker: str) -> bool:
        """Check if baseline exists for ticker."""
        return self._baseline_path(ticker).exists()

    def save(self, baseline: TickerBaseline) -> bool:
        """
        Save baseline to disk.

        Args:
            baseline: TickerBaseline to save

        Returns:
            True if successful
        """
        path = self._baseline_path(baseline.ticker)

        try:
            data = self._serialize_baseline(baseline)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved baseline for {baseline.ticker} to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save baseline for {baseline.ticker}: {e}")
            return False

    def load(self, ticker: str) -> TickerBaseline | None:
        """
        Load baseline from disk.

        Args:
            ticker: Stock ticker symbol

        Returns:
            TickerBaseline or None if not found
        """
        path = self._baseline_path(ticker)

        if not path.exists():
            logger.debug(f"No baseline found for {ticker}")
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._deserialize_baseline(data)
        except Exception as e:
            logger.error(f"Failed to load baseline for {ticker}: {e}")
            return None

    def delete(self, ticker: str) -> bool:
        """Delete baseline for ticker."""
        path = self._baseline_path(ticker)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted baseline for {ticker}")
            return True
        return False

    def list_tickers(self) -> list[str]:
        """List all tickers with stored baselines."""
        return [p.stem for p in self.base_dir.glob("*.json")]

    def get_baseline_age(self, ticker: str) -> int | None:
        """Get age of baseline in days."""
        baseline = self.load(ticker)
        if baseline is None:
            return None
        return (date.today() - baseline.baseline_date).days

    def _serialize_baseline(self, baseline: TickerBaseline) -> dict[str, Any]:
        """Convert baseline to JSON-serializable dict."""
        return {
            "ticker": baseline.ticker,
            "baseline_date": baseline.baseline_date.isoformat(),
            "lookback_days": baseline.lookback_days,
            "data_start_date": baseline.data_start_date.isoformat(),
            "data_end_date": baseline.data_end_date.isoformat(),
            "observation_count": baseline.observation_count,
            "missing_data_pct": baseline.missing_data_pct,
            "schema_version": baseline.schema_version,
            "dark_pool": self._serialize_dark_pool(baseline.dark_pool),
            "greeks": self._serialize_greeks(baseline.greeks),
            "price_efficiency": self._serialize_price_efficiency(baseline.price_efficiency),
        }

    def _serialize_distribution(self, dist: DistributionStats | None) -> dict | None:
        """Serialize DistributionStats."""
        if dist is None:
            return None
        return {
            "mean": dist.mean,
            "std": dist.std,
            "median": dist.median,
            "mad": dist.mad,
            "p25": dist.p25,
            "p75": dist.p75,
            "p90": dist.p90,
            "p95": dist.p95,
            "min_val": dist.min_val,
            "max_val": dist.max_val,
            "n_observations": dist.n_observations,
        }

    def _serialize_dark_pool(self, dp: DarkPoolBaseline) -> dict:
        """Serialize DarkPoolBaseline."""
        return {
            "dark_share": self._serialize_distribution(dp.dark_share),
            "dark_share_typical_range": list(dp.dark_share_typical_range),
            "dark_volume": self._serialize_distribution(dp.dark_volume),
            "daily_block_count": self._serialize_distribution(dp.daily_block_count),
            "block_size": self._serialize_distribution(dp.block_size),
            "block_premium": self._serialize_distribution(dp.block_premium),
            "venue_shift": self._serialize_distribution(dp.venue_shift),
            "policy": dp.policy.value,
        }

    def _serialize_greeks(self, greeks: GreeksBaseline) -> dict:
        """Serialize GreeksBaseline."""
        return {
            "gex": self._serialize_distribution(greeks.gex),
            "gex_positive_pct": greeks.gex_positive_pct,
            "gex_negative_pct": greeks.gex_negative_pct,
            "dex": self._serialize_distribution(greeks.dex),
            "vanna": self._serialize_distribution(greeks.vanna),
            "charm": self._serialize_distribution(greeks.charm),
            "iv_atm": self._serialize_distribution(greeks.iv_atm),
            "iv_atm_daily_change": self._serialize_distribution(greeks.iv_atm_daily_change),
            "iv_skew": self._serialize_distribution(greeks.iv_skew),
            "iv_rank": self._serialize_distribution(greeks.iv_rank),
            "policy": greeks.policy.value,
        }

    def _serialize_price_efficiency(self, pe: PriceEfficiencyBaseline) -> dict:
        """Serialize PriceEfficiencyBaseline."""
        return {
            "range_per_volume": self._serialize_distribution(pe.range_per_volume),
            "range_per_volume_pct": self._serialize_distribution(pe.range_per_volume_pct),
            "impact_per_volume": self._serialize_distribution(pe.impact_per_volume),
            "price_efficiency": self._serialize_distribution(pe.price_efficiency),
            "daily_range_pct": self._serialize_distribution(pe.daily_range_pct),
            "close_position": self._serialize_distribution(pe.close_position),
            "policy": pe.policy.value,
        }

    def _deserialize_baseline(self, data: dict) -> TickerBaseline:
        """Convert JSON dict back to TickerBaseline."""
        return TickerBaseline(
            ticker=data["ticker"],
            baseline_date=date.fromisoformat(data["baseline_date"]),
            lookback_days=data["lookback_days"],
            data_start_date=date.fromisoformat(data["data_start_date"]),
            data_end_date=date.fromisoformat(data["data_end_date"]),
            observation_count=data["observation_count"],
            missing_data_pct=data["missing_data_pct"],
            schema_version=data.get("schema_version", "1.0"),
            dark_pool=self._deserialize_dark_pool(data["dark_pool"]),
            greeks=self._deserialize_greeks(data["greeks"]),
            price_efficiency=self._deserialize_price_efficiency(data["price_efficiency"]),
        )

    def _deserialize_distribution(self, data: dict | None) -> DistributionStats | None:
        """Deserialize DistributionStats."""
        if data is None:
            return None
        return DistributionStats(
            mean=data["mean"],
            std=data["std"],
            median=data["median"],
            mad=data["mad"],
            p25=data["p25"],
            p75=data["p75"],
            p90=data["p90"],
            p95=data["p95"],
            min_val=data["min_val"],
            max_val=data["max_val"],
            n_observations=data["n_observations"],
        )

    def _deserialize_dark_pool(self, data: dict) -> DarkPoolBaseline:
        """Deserialize DarkPoolBaseline."""
        return DarkPoolBaseline(
            dark_share=self._deserialize_distribution(data["dark_share"]),
            dark_share_typical_range=tuple(data["dark_share_typical_range"]),
            dark_volume=self._deserialize_distribution(data.get("dark_volume")),
            daily_block_count=self._deserialize_distribution(data["daily_block_count"]),
            block_size=self._deserialize_distribution(data["block_size"]),
            block_premium=self._deserialize_distribution(data["block_premium"]),
            venue_shift=self._deserialize_distribution(data["venue_shift"]),
            policy=BaselineUpdatePolicy(data["policy"]),
        )

    def _deserialize_greeks(self, data: dict) -> GreeksBaseline:
        """Deserialize GreeksBaseline."""
        return GreeksBaseline(
            gex=self._deserialize_distribution(data["gex"]),
            gex_positive_pct=data["gex_positive_pct"],
            gex_negative_pct=data["gex_negative_pct"],
            dex=self._deserialize_distribution(data["dex"]),
            vanna=self._deserialize_distribution(data.get("vanna")),
            charm=self._deserialize_distribution(data.get("charm")),
            iv_atm=self._deserialize_distribution(data.get("iv_atm")),
            iv_atm_daily_change=self._deserialize_distribution(data.get("iv_atm_daily_change")),
            iv_skew=self._deserialize_distribution(data.get("iv_skew")),
            iv_rank=self._deserialize_distribution(data.get("iv_rank")),
            policy=BaselineUpdatePolicy(data["policy"]),
        )

    def _deserialize_price_efficiency(self, data: dict) -> PriceEfficiencyBaseline:
        """Deserialize PriceEfficiencyBaseline."""
        return PriceEfficiencyBaseline(
            range_per_volume=self._deserialize_distribution(data["range_per_volume"]),
            range_per_volume_pct=self._deserialize_distribution(data["range_per_volume_pct"]),
            impact_per_volume=self._deserialize_distribution(data["impact_per_volume"]),
            price_efficiency=self._deserialize_distribution(data["price_efficiency"]),
            daily_range_pct=self._deserialize_distribution(data["daily_range_pct"]),
            close_position=self._deserialize_distribution(data["close_position"]),
            policy=BaselineUpdatePolicy(data["policy"]),
        )


def format_baseline_report(baseline: TickerBaseline) -> str:
    """
    Format baseline as human-readable report.

    Used for diagnostics and documentation.
    """
    lines = [
        f"{'='*60}",
        f"BASELINE PROFILE: {baseline.ticker}",
        f"{'='*60}",
        f"",
        f"Generated: {baseline.baseline_date}",
        f"Lookback: {baseline.lookback_days} trading days",
        f"Data range: {baseline.data_start_date} to {baseline.data_end_date}",
        f"Observations: {baseline.observation_count}",
        f"Missing data: {baseline.missing_data_pct:.1f}%",
        f"",
        f"{'─'*60}",
        f"A) DARK POOL / VENUE BASELINES",
        f"{'─'*60}",
        f"",
    ]

    dp = baseline.dark_pool
    lines.extend([
        f"Dark Pool Share:",
        f"  Mean: {dp.dark_share.mean:.1f}%",
        f"  Std: {dp.dark_share.std:.1f}%",
        f"  Typical range: {dp.dark_share_typical_range[0]:.1f}% - {dp.dark_share_typical_range[1]:.1f}%",
        f"",
        f"Block Trades:",
        f"  Daily count (median): {dp.daily_block_count.median:.0f}",
        f"  Block size (75th %ile): {dp.block_size.p75:,.0f} shares",
        f"  Block size (90th %ile): {dp.block_size.p90:,.0f} shares",
        f"",
    ])

    lines.extend([
        f"{'─'*60}",
        f"B) OPTIONS / GREEKS BASELINES",
        f"{'─'*60}",
        f"",
    ])

    g = baseline.greeks
    lines.extend([
        f"Gamma Exposure (GEX):",
        f"  Mean: {g.gex.mean:,.0f}",
        f"  Std: {g.gex.std:,.0f}",
        f"  MAD: {g.gex.mad:,.0f}",
        f"  Positive days: {g.gex_positive_pct:.0f}%",
        f"  Negative days: {g.gex_negative_pct:.0f}%",
        f"",
        f"Delta Exposure (DEX):",
        f"  Mean: {g.dex.mean:,.0f}",
        f"  Std: {g.dex.std:,.0f}",
        f"",
    ])

    if g.iv_atm:
        lines.extend([
            f"ATM Implied Volatility:",
            f"  Mean: {g.iv_atm.mean:.1f}%",
            f"  Std: {g.iv_atm.std:.1f}%",
            f"",
        ])

    if g.iv_skew:
        lines.extend([
            f"IV Skew:",
            f"  Mean: {g.iv_skew.mean:.2f}",
            f"  Std: {g.iv_skew.std:.2f}",
            f"",
        ])

    lines.extend([
        f"{'─'*60}",
        f"C) PRICE IMPACT / EFFICIENCY BASELINES",
        f"{'─'*60}",
        f"",
    ])

    pe = baseline.price_efficiency
    lines.extend([
        f"Daily Range:",
        f"  Mean: {pe.daily_range_pct.mean:.2f}%",
        f"  Std: {pe.daily_range_pct.std:.2f}%",
        f"",
        f"Price Efficiency:",
        f"  Mean: {pe.price_efficiency.mean:.1f}",
        f"  Std: {pe.price_efficiency.std:.1f}",
        f"",
        f"Impact per Volume:",
        f"  Mean: {pe.impact_per_volume.mean:.4f}",
        f"  Std: {pe.impact_per_volume.std:.4f}",
        f"",
        f"{'='*60}",
    ])

    return "\n".join(lines)
