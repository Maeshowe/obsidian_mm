#!/usr/bin/env python3
"""
Compute baseline profile for a ticker.

This script onboards a new ticker by computing its baseline profile
from historical data. The baseline establishes what "normal" looks like
for this instrument.

INCREMENTAL DATA MODE:
    The script first checks for locally stored feature history
    (collected by daily pipeline runs). If sufficient data exists,
    it uses local history instead of API calls.

    This enables:
    - Computing baselines for vanna/charm (API only has 7 days)
    - Reducing API usage
    - Building baselines from accumulated daily data

Usage:
    python scripts/compute_baseline.py SPY
    python scripts/compute_baseline.py SPY --days 63 --verbose
    python scripts/compute_baseline.py SPY QQQ AAPL  # Multiple tickers
    python scripts/compute_baseline.py SPY --local-only  # Only use local data
    python scripts/compute_baseline.py SPY --status  # Check data availability
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from dotenv import load_dotenv

from obsidian.baseline import (
    BaselineCalculator,
    BaselineStorage,
    FeatureHistoryStorage,
    format_baseline_report,
)
from obsidian.ingest.unusual_whales import UnusualWhalesClient
from obsidian.ingest.polygon import PolygonClient
from obsidian.ingest.cache import CacheManager

# Load environment
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# Minimum observations for baseline
MIN_OBSERVATIONS = 21


def load_from_local_history(
    ticker: str,
    history_storage: FeatureHistoryStorage,
    days: int,
) -> pd.DataFrame:
    """
    Load historical data from local feature history.

    Args:
        ticker: Stock ticker symbol
        history_storage: Feature history storage
        days: Number of days to load

    Returns:
        DataFrame with features, or empty DataFrame if insufficient data
    """
    try:
        df = history_storage.load_dataframe(ticker, min_days=0)

        if df.empty:
            return df

        # Take only the most recent N days
        if len(df) > days:
            df = df.tail(days)

        # Calculate venue shift if not present
        if "venue_shift" not in df.columns or df["venue_shift"].isna().all():
            if "dark_pool_ratio" in df.columns:
                df = df.sort_values("date")
                df["venue_shift"] = df["dark_pool_ratio"].diff()

        return df

    except Exception as e:
        logger.warning(f"Failed to load local history: {e}")
        return pd.DataFrame()


async def fetch_historical_data(
    ticker: str,
    days: int,
    uw_client: UnusualWhalesClient,
    poly_client: PolygonClient,
    skip_dates: set[date] | None = None,
) -> pd.DataFrame:
    """
    Fetch historical data needed for baseline computation.

    Args:
        ticker: Stock ticker symbol
        days: Number of days to fetch
        uw_client: Unusual Whales client
        poly_client: Polygon client
        skip_dates: Dates to skip (already have local data)

    Returns:
        DataFrame with all features for baseline computation
    """
    skip_dates = skip_dates or set()
    end_date = date.today() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=int(days * 1.5))  # Buffer for weekends

    records = []
    current_date = start_date

    while current_date <= end_date:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        # Skip dates we already have
        if current_date in skip_dates:
            current_date += timedelta(days=1)
            continue

        try:
            # Fetch dark pool data
            dp_trades = await uw_client.get_darkpool_trades(ticker, current_date)
            dp_agg = uw_client.aggregate_darkpool_daily(dp_trades)

            # Fetch Greeks
            greeks = await uw_client.get_greek_exposure(ticker, current_date)

            # Fetch OHLCV
            ohlcv = await poly_client.get_daily_ohlcv(ticker, current_date)

            if not ohlcv:
                current_date += timedelta(days=1)
                continue

            # Calculate derived metrics
            total_volume = ohlcv.get("volume", 0)
            dark_volume = dp_agg.get("dark_pool_volume", 0)
            dark_ratio = (dark_volume / total_volume * 100) if total_volume > 0 else 0

            open_price = ohlcv.get("open", 0)
            high_price = ohlcv.get("high", 0)
            low_price = ohlcv.get("low", 0)
            close_price = ohlcv.get("close", 0)

            daily_range = high_price - low_price
            daily_range_pct = (daily_range / open_price * 100) if open_price > 0 else 0
            price_change_pct = ((close_price - open_price) / open_price * 100) if open_price > 0 else 0

            # Price efficiency (lower = more controlled)
            price_efficiency = 0
            if total_volume > 0 and daily_range > 0:
                price_efficiency = (daily_range_pct / (total_volume / 1e6)) * 100

            # Impact per volume
            impact_per_vol = 0
            if total_volume > 0:
                impact_per_vol = abs(price_change_pct) / (total_volume / 1e6)

            record = {
                "date": current_date,
                "ticker": ticker,
                # Dark pool
                "dark_pool_volume": dark_volume,
                "total_volume": total_volume,
                "dark_pool_ratio": dark_ratio,
                "block_trade_count": dp_agg.get("block_trade_count", 0),
                "block_trade_size_avg": dp_agg.get("avg_block_size", 0),
                "block_premium": dp_agg.get("dark_pool_notional", 0),
                "venue_shift": 0,  # Would need previous day
                # Greeks
                "gex": greeks.get("gex", 0),
                "dex": greeks.get("dex", 0),
                "vanna": greeks.get("vanna"),
                "charm": greeks.get("charm"),
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
            records.append(record)
            logger.debug(f"Fetched data for {ticker} {current_date}")

        except Exception as e:
            logger.warning(f"Failed to fetch data for {ticker} {current_date}: {e}")

        current_date += timedelta(days=1)

    # Calculate venue shift (day-over-day dark ratio change)
    df = pd.DataFrame(records)
    if not df.empty and "dark_pool_ratio" in df.columns:
        df = df.sort_values("date")
        df["venue_shift"] = df["dark_pool_ratio"].diff()

    return df


async def compute_baseline_for_ticker(
    ticker: str,
    days: int,
    storage: BaselineStorage,
    history_storage: FeatureHistoryStorage,
    verbose: bool = False,
    local_only: bool = False,
) -> bool:
    """
    Compute and store baseline for a single ticker.

    Strategy:
    1. First check local feature history
    2. If sufficient data locally, use it (enables vanna/charm baselines!)
    3. If not enough local data, supplement with API calls

    Returns True if successful.
    """
    logger.info(f"Computing baseline for {ticker} with {days} days lookback")

    # Step 1: Check local history
    print(f"Checking local feature history for {ticker}...")
    local_df = load_from_local_history(ticker, history_storage, days)
    local_count = len(local_df)

    if local_count > 0:
        print(f"  Found {local_count} days of local history")
        summary = history_storage.get_summary(ticker)
        if summary.get("has_vanna"):
            print(f"  ✓ Local data includes vanna")
        if summary.get("has_charm"):
            print(f"  ✓ Local data includes charm")

    # Step 2: Decide data source
    if local_count >= MIN_OBSERVATIONS:
        print(f"  Using local history (sufficient: {local_count} >= {MIN_OBSERVATIONS})")
        historical_df = local_df
    elif local_only:
        if local_count < MIN_OBSERVATIONS:
            print(f"  ✗ Insufficient local data: {local_count} < {MIN_OBSERVATIONS} required")
            print(f"    Run daily pipeline for {MIN_OBSERVATIONS - local_count} more days")
            return False
        historical_df = local_df
    else:
        # Supplement with API
        print(f"  Supplementing with API data...")

        cache = CacheManager(PROJECT_ROOT / "data" / "raw")
        uw_key = os.getenv("UNUSUAL_WHALES_API_KEY", "")
        poly_key = os.getenv("POLYGON_API_KEY", "")

        if not uw_key or not poly_key:
            logger.error("Missing API keys!")
            return False

        # Skip dates we already have
        existing_dates = set(history_storage.list_dates(ticker))

        uw_client = UnusualWhalesClient(uw_key, cache)
        poly_client = PolygonClient(poly_key, cache)

        async with uw_client, poly_client:
            api_df = await fetch_historical_data(
                ticker, days, uw_client, poly_client,
                skip_dates=existing_dates
            )

        if not api_df.empty:
            print(f"  Fetched {len(api_df)} days from API")

        # Combine local and API data
        if not local_df.empty and not api_df.empty:
            historical_df = pd.concat([local_df, api_df], ignore_index=True)
            historical_df = historical_df.drop_duplicates(subset=["date"])
            historical_df = historical_df.sort_values("date").tail(days)
            # Recalculate venue shift for combined data
            historical_df["venue_shift"] = historical_df["dark_pool_ratio"].diff()
        elif not local_df.empty:
            historical_df = local_df
        else:
            historical_df = api_df

    if historical_df.empty:
        logger.error(f"No data available for {ticker}")
        return False

    print(f"Total: {len(historical_df)} days of data for baseline")

    # Step 3: Compute baseline
    calculator = BaselineCalculator(lookback_days=days)
    baseline = calculator.compute_baseline(ticker, historical_df)

    if baseline is None:
        logger.error(f"Failed to compute baseline for {ticker}")
        return False

    if not baseline.is_valid():
        logger.warning(
            f"Baseline for {ticker} has quality issues: "
            f"{baseline.observation_count} obs, {baseline.missing_data_pct:.1f}% missing"
        )

    # Step 4: Store baseline
    storage.save(baseline)
    print(f"✓ Baseline saved for {ticker}")

    # Report on vanna/charm availability
    if baseline.greeks.vanna is not None:
        print(f"  ✓ Vanna baseline computed ({baseline.greeks.vanna.n_observations} obs)")
    else:
        print(f"  ○ Vanna: insufficient data (need {MIN_OBSERVATIONS}+ days with vanna values)")

    if baseline.greeks.charm is not None:
        print(f"  ✓ Charm baseline computed ({baseline.greeks.charm.n_observations} obs)")
    else:
        print(f"  ○ Charm: insufficient data (need {MIN_OBSERVATIONS}+ days with charm values)")

    # Print report if verbose
    if verbose:
        print()
        print(format_baseline_report(baseline))

    return True


def show_status(ticker: str, history_storage: FeatureHistoryStorage, storage: BaselineStorage) -> None:
    """Show data availability status for a ticker."""
    print(f"\n{'='*50}")
    print(f"Status for {ticker}")
    print(f"{'='*50}")

    # Feature history
    summary = history_storage.get_summary(ticker)
    print(f"\nLocal Feature History:")
    if summary.get("has_data"):
        print(f"  Observations: {summary['observation_count']}")
        print(f"  Date range: {summary['earliest_date']} to {summary['latest_date']}")
        print(f"  Has vanna: {'✓' if summary.get('has_vanna') else '✗'}")
        print(f"  Has charm: {'✓' if summary.get('has_charm') else '✗'}")

        if summary['observation_count'] >= MIN_OBSERVATIONS:
            print(f"  Status: ✓ Ready for baseline computation")
        else:
            needed = MIN_OBSERVATIONS - summary['observation_count']
            print(f"  Status: Need {needed} more days of data")
    else:
        print(f"  No local data collected yet")
        print(f"  Run daily pipeline to start collecting")

    # Baseline status
    print(f"\nBaseline:")
    if storage.exists(ticker):
        baseline = storage.load(ticker)
        age = baseline.days_since_update(date.today())
        print(f"  Exists: ✓ (computed {baseline.baseline_date}, {age} days ago)")
        print(f"  Observations: {baseline.observation_count}")
        print(f"  Has vanna: {'✓' if baseline.greeks.vanna else '✗'}")
        print(f"  Has charm: {'✓' if baseline.greeks.charm else '✗'}")
        if baseline.needs_refresh(date.today()):
            print(f"  Status: Consider refreshing (>63 days old)")
    else:
        print(f"  Exists: ✗")

    print()


async def main():
    parser = argparse.ArgumentParser(
        description="Compute baseline profiles for tickers"
    )
    parser.add_argument(
        "tickers",
        nargs="+",
        help="Ticker symbols to compute baselines for"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=63,
        help="Number of trading days for baseline (default: 63)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed baseline report"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing baselines"
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only use local feature history (no API calls)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show data availability status instead of computing"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    storage = BaselineStorage(PROJECT_ROOT / "data" / "baselines")
    history_storage = FeatureHistoryStorage(
        PROJECT_ROOT / "data" / "processed" / "feature_history"
    )

    # Status mode
    if args.status:
        for ticker in args.tickers:
            show_status(ticker.upper(), history_storage, storage)
        return

    print(f"{'='*60}")
    print("OBSIDIAN MM - Baseline Computation")
    print(f"{'='*60}")
    print(f"Tickers: {', '.join(args.tickers)}")
    print(f"Lookback: {args.days} trading days")
    print(f"Mode: {'Local only' if args.local_only else 'Local + API fallback'}")
    print()

    success_count = 0
    for ticker in args.tickers:
        ticker = ticker.upper()

        # Check if baseline exists
        if storage.exists(ticker) and not args.force:
            existing = storage.load(ticker)
            age = existing.days_since_update(date.today())
            print(f"⏭ {ticker}: Baseline exists ({age} days old). Use --force to overwrite.")
            continue

        try:
            success = await compute_baseline_for_ticker(
                ticker, args.days, storage, history_storage,
                args.verbose, args.local_only
            )
            if success:
                success_count += 1
        except Exception as e:
            logger.error(f"Error computing baseline for {ticker}: {e}")

    print()
    print(f"{'='*60}")
    print(f"Completed: {success_count}/{len(args.tickers)} baselines computed")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
