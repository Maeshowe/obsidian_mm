"""
Daily pipeline orchestrator.

Coordinates the full diagnostic flow:
Ingest → Features → Normalize → Classify → Score → Explain

BASELINE INTEGRATION:
    The pipeline now loads and uses ticker-specific baselines for
    normalization. Without a baseline, the system cannot determine
    what is "normal" for an instrument.

    Set require_baseline=True (recommended) to enforce baseline existence.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian.core.config import Settings, get_settings
from obsidian.core.types import FeatureSet, RegimeResult, UnusualnessResult
from obsidian.explain.generator import ExplanationGenerator
from obsidian.features.aggregator import FeatureAggregator
from obsidian.ingest.cache import CacheManager
from obsidian.ingest.fmp import FMPClient
from obsidian.ingest.polygon import PolygonClient
from obsidian.ingest.unusual_whales import UnusualWhalesClient
from obsidian.normalization.pipeline import NormalizationPipeline
from obsidian.regimes.classifier import RegimeClassifier
from obsidian.scoring.unusualness import UnusualnessEngine


logger = logging.getLogger(__name__)


# Try to import baseline components
try:
    from obsidian.baseline import BaselineStorage, TickerBaseline, FeatureHistoryStorage
    BASELINE_AVAILABLE = True
except ImportError:
    BASELINE_AVAILABLE = False
    BaselineStorage = None
    TickerBaseline = None
    FeatureHistoryStorage = None


@dataclass
class DailyResult:
    """Result of daily pipeline for a single ticker."""

    ticker: str
    trade_date: date
    features: FeatureSet
    regime: RegimeResult
    unusualness: UnusualnessResult
    full_explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ticker": self.ticker,
            "date": self.trade_date.isoformat(),
            "regime": self.regime.to_dict(),
            "unusualness": self.unusualness.to_dict(),
            "features": self.features.to_dict(),
            "explanation": self.full_explanation,
        }


class DailyPipeline:
    """
    Orchestrates the daily diagnostic pipeline.

    Flow:
    1. Load baseline for ticker (if available)
    2. Fetch data from APIs (Unusual Whales, Polygon, FMP)
    3. Extract features from raw data
    4. Normalize features against baseline/historical distribution
    5. Classify into MM regime
    6. Calculate unusualness score
    7. Generate explanation

    BASELINE MODE:
        When baselines are available, normalization uses the ticker's
        locked baseline statistics. This ensures deviations are measured
        against the instrument's established "normal" levels.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        require_baseline: bool = False,
    ) -> None:
        """
        Initialize daily pipeline.

        Args:
            settings: Application settings
            require_baseline: If True, fail when baseline is not available
        """
        self.settings = settings or get_settings()
        self.require_baseline = require_baseline

        # Initialize cache
        self.cache = CacheManager(
            cache_dir=self.settings.raw_data_dir,
            ttl_hours=24,
        )

        # Initialize baseline storage
        self.baseline_storage = None
        self.feature_history = None
        if BASELINE_AVAILABLE:
            self.baseline_storage = BaselineStorage(
                base_dir=self.settings.baselines_dir
            )
            # Feature history for incremental baseline computation
            self.feature_history = FeatureHistoryStorage(
                base_dir=self.settings.processed_data_dir / "feature_history"
            )

        # Initialize components (normalization initialized per-ticker)
        self.feature_aggregator = FeatureAggregator()
        self.classifier = RegimeClassifier()
        self.scorer = UnusualnessEngine()
        self.explainer = ExplanationGenerator()

        # Track loaded baselines
        self._baselines: dict[str, "TickerBaseline"] = {}

    async def run(
        self,
        ticker: str,
        trade_date: date | None = None,
    ) -> DailyResult:
        """
        Run the daily pipeline for a single ticker.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to analyze (defaults to today)

        Returns:
            DailyResult with regime, score, and explanation

        Raises:
            ValueError: If require_baseline=True and no baseline exists
        """
        trade_date = trade_date or date.today()
        logger.info(f"Running daily pipeline for {ticker} on {trade_date}")

        # Step 1: Load baseline
        baseline = self._load_baseline(ticker)

        if baseline is None and self.require_baseline:
            raise ValueError(
                f"No baseline found for {ticker}. "
                f"Run 'python scripts/compute_baseline.py {ticker}' first."
            )

        if baseline is not None:
            logger.info(f"Using baseline from {baseline.baseline_date} for {ticker}")

        # Step 2: Fetch data
        raw_data = await self._fetch_data(ticker, trade_date)

        # Step 3: Extract features
        features = self._extract_features(ticker, trade_date, raw_data)

        # Step 3.5: Save raw features to history (for incremental baseline)
        self._save_feature_history(ticker, trade_date, features, raw_data)

        # Step 4: Normalize (with baseline if available)
        normalization = NormalizationPipeline(
            history_dir=self.settings.processed_data_dir,
            baseline=baseline,
        )

        try:
            features = normalization.normalize(features, require_history=False)
        except Exception as e:
            logger.warning(f"Normalization failed: {e}")

        # Step 5: Classify regime
        regime = self.classifier.classify(
            features.to_series(),
            ticker=ticker,
            trade_date=trade_date,
        )

        # Step 6: Calculate unusualness score
        unusualness = self.scorer.calculate(
            features.normalized,
            ticker=ticker,
            trade_date=trade_date,
        )

        # Step 7: Generate explanation
        full_explanation = self.explainer.generate_full_explanation(
            regime, unusualness
        )

        return DailyResult(
            ticker=ticker,
            trade_date=trade_date,
            features=features,
            regime=regime,
            unusualness=unusualness,
            full_explanation=full_explanation,
        )

    def _load_baseline(self, ticker: str) -> "TickerBaseline | None":
        """
        Load baseline for ticker.

        Caches baselines to avoid repeated disk reads.
        """
        if not BASELINE_AVAILABLE or self.baseline_storage is None:
            return None

        # Check cache first
        if ticker in self._baselines:
            return self._baselines[ticker]

        # Load from storage
        baseline = self.baseline_storage.load(ticker)

        if baseline is not None:
            # Check if baseline needs refresh
            if baseline.needs_refresh(date.today()):
                logger.warning(
                    f"Baseline for {ticker} is {baseline.days_since_update(date.today())} days old. "
                    f"Consider refreshing."
                )

            # Cache it
            self._baselines[ticker] = baseline

        return baseline

    async def _fetch_data(
        self,
        ticker: str,
        trade_date: date,
    ) -> dict[str, Any]:
        """Fetch all required data from APIs."""
        data = {
            "darkpool_trades": None,
            "greek_data": None,
            "ohlcv": None,
            "iv_data": None,
        }

        # Unusual Whales
        async with UnusualWhalesClient(
            api_key=self.settings.unusual_whales_api_key,
            cache=self.cache,
        ) as uw:
            try:
                data["darkpool_trades"] = await uw.get_darkpool_trades(ticker, trade_date)
                data["greek_data"] = await uw.get_greek_exposure(ticker, trade_date)
                data["iv_data"] = await uw.get_iv_term_structure(ticker, trade_date)
            except Exception as e:
                logger.error(f"UW fetch failed: {e}")

        # Polygon
        async with PolygonClient(
            api_key=self.settings.polygon_api_key,
            cache=self.cache,
        ) as polygon:
            try:
                data["ohlcv"] = await polygon.get_daily_ohlcv(ticker, trade_date)
            except Exception as e:
                logger.error(f"Polygon fetch failed: {e}")

        return data

    def _extract_features(
        self,
        ticker: str,
        trade_date: date,
        raw_data: dict[str, Any],
    ) -> FeatureSet:
        """Extract features from raw data."""
        # Get total volume for dark pool ratio
        total_volume = None
        if raw_data.get("ohlcv"):
            total_volume = raw_data["ohlcv"].get("volume")

        return self.feature_aggregator.from_raw_data(
            ticker=ticker,
            trade_date=trade_date,
            darkpool_trades=raw_data.get("darkpool_trades"),
            greek_data=raw_data.get("greek_data"),
            iv_data=raw_data.get("iv_data"),
            ohlcv=raw_data.get("ohlcv"),
            total_volume=total_volume,
        )

    def _save_feature_history(
        self,
        ticker: str,
        trade_date: date,
        features: FeatureSet,
        raw_data: dict[str, Any],
    ) -> None:
        """
        Save raw features to history for incremental baseline computation.

        This enables building baselines from locally collected data,
        overcoming API limitations on historical access.
        """
        if self.feature_history is None:
            return

        try:
            # Extract raw values needed for baseline computation
            ohlcv = raw_data.get("ohlcv") or {}
            greek_data = raw_data.get("greek_data") or {}
            darkpool_trades = raw_data.get("darkpool_trades")

            # Get dark pool notional from raw trades
            block_premium = 0.0
            if darkpool_trades is not None:
                try:
                    if hasattr(darkpool_trades, 'empty') and not darkpool_trades.empty:
                        if "premium" in darkpool_trades.columns:
                            block_premium = float(darkpool_trades["premium"].sum())
                except Exception:
                    pass

            # Calculate derived metrics
            total_volume = ohlcv.get("volume", 0)
            open_price = ohlcv.get("open", 0)
            high_price = ohlcv.get("high", 0)
            low_price = ohlcv.get("low", 0)
            close_price = ohlcv.get("close", 0)

            daily_range = high_price - low_price
            daily_range_pct = (daily_range / open_price * 100) if open_price > 0 else 0
            price_change_pct = ((close_price - open_price) / open_price * 100) if open_price > 0 else 0

            # Price efficiency
            price_efficiency = 0
            if total_volume > 0 and daily_range > 0:
                price_efficiency = (daily_range_pct / (total_volume / 1e6)) * 100

            # Impact per volume
            impact_per_vol = 0
            if total_volume > 0:
                impact_per_vol = abs(price_change_pct) / (total_volume / 1e6)

            feature_record = {
                # Dark pool
                "dark_pool_volume": features.dark_pool_volume,
                "total_volume": total_volume,
                "dark_pool_ratio": features.dark_pool_ratio,
                "block_trade_count": features.block_trade_count,
                "block_trade_size_avg": features.block_trade_size_avg,
                "block_premium": block_premium,
                "venue_shift": features.venue_shift,
                # Greeks (including vanna/charm for future baseline)
                "gex": features.gex,
                "dex": features.dex,
                "vanna": greek_data.get("vanna"),
                "charm": greek_data.get("charm"),
                # IV
                "iv_atm": features.iv_atm,
                "iv_skew": features.iv_skew,
                # Price
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "close_price": close_price,
                "volume": total_volume,
                "price_change_pct": price_change_pct,
                "daily_range_pct": daily_range_pct,
                "price_efficiency": price_efficiency,
                "impact_per_vol": impact_per_vol,
            }

            self.feature_history.save(ticker, trade_date, feature_record)
            logger.debug(f"Saved feature history for {ticker} on {trade_date}")

        except Exception as e:
            logger.warning(f"Failed to save feature history: {e}")

    async def run_batch(
        self,
        tickers: list[str],
        trade_date: date | None = None,
    ) -> list[DailyResult]:
        """
        Run the daily pipeline for multiple tickers.

        Args:
            tickers: List of ticker symbols
            trade_date: Date to analyze

        Returns:
            List of DailyResult objects
        """
        trade_date = trade_date or date.today()
        results = []

        for ticker in tickers:
            try:
                result = await self.run(ticker, trade_date)
                results.append(result)
            except Exception as e:
                logger.error(f"Pipeline failed for {ticker}: {e}")
                continue

        return results

    def save_result(
        self,
        result: DailyResult,
        output_dir: Path | None = None,
    ) -> Path:
        """
        Save pipeline result to disk.

        Args:
            result: DailyResult to save
            output_dir: Output directory (defaults to processed_data_dir)

        Returns:
            Path to saved file
        """
        output_dir = output_dir or self.settings.processed_data_dir / "regimes" / result.ticker
        output_dir.mkdir(parents=True, exist_ok=True)

        path = output_dir / f"{result.trade_date.isoformat()}.parquet"

        # Convert to DataFrame and save
        df = pd.DataFrame([result.to_dict()])
        df.to_parquet(path, index=False)

        logger.info(f"Saved result to {path}")
        return path
