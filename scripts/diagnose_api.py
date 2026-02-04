#!/usr/bin/env python3
"""
API Diagnostic Script for OBSIDIAN MM.

Tests each API endpoint to verify data is being returned correctly.
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from obsidian.core.config import load_config
from obsidian.ingest.unusual_whales import UnusualWhalesClient
from obsidian.ingest.polygon import PolygonClient
from obsidian.ingest.cache import CacheManager

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")


async def diagnose_apis(ticker: str = "SPY", trade_date: date | None = None):
    """Run diagnostic tests on all APIs."""

    if trade_date is None:
        # Use yesterday to ensure market was open
        trade_date = date.today() - timedelta(days=1)
        # Skip to Friday if weekend
        if trade_date.weekday() == 6:  # Sunday
            trade_date -= timedelta(days=2)
        elif trade_date.weekday() == 5:  # Saturday
            trade_date -= timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"OBSIDIAN MM - API Diagnostics")
    print(f"Ticker: {ticker}")
    print(f"Date: {trade_date}")
    print(f"{'='*60}\n")

    # Load configs
    sources_config = load_config("sources")

    # Initialize cache
    cache = CacheManager(PROJECT_ROOT / "data" / "raw")

    # Get API keys
    uw_api_key = os.getenv("UNUSUAL_WHALES_API_KEY", "")
    polygon_api_key = os.getenv("POLYGON_API_KEY", "")

    print(f"API Keys:")
    print(f"  Unusual Whales: {'***' + uw_api_key[-4:] if len(uw_api_key) > 4 else 'MISSING'}")
    print(f"  Polygon: {'***' + polygon_api_key[-4:] if len(polygon_api_key) > 4 else 'MISSING'}")
    print()

    # Test 1: Unusual Whales - Dark Pool
    print("1. UNUSUAL WHALES - Dark Pool Trades")
    print("-" * 40)
    uw_client = UnusualWhalesClient(uw_api_key, cache)
    aggregated = {}  # Initialize for later use
    async with uw_client:
        try:
            trades = await uw_client.get_darkpool_trades(ticker, trade_date)
            print(f"   Status: OK")
            print(f"   Trades: {len(trades)}")
            if len(trades) > 0:
                print(f"   Sample: {trades.iloc[0].to_dict()}")
                aggregated = uw_client.aggregate_darkpool_daily(trades)
                print(f"   Aggregated: {aggregated}")
            else:
                print("   WARNING: No trades returned!")
        except Exception as e:
            print(f"   Status: FAILED")
            print(f"   Error: {e}")
        print()

        # Test 2: Unusual Whales - Greek Exposure
        print("2. UNUSUAL WHALES - Greek Exposure")
        print("-" * 40)
        try:
            greeks = await uw_client.get_greek_exposure(ticker, trade_date)
            print(f"   Status: OK" if greeks else "   Status: EMPTY")
            if greeks:
                print(f"   GEX (net gamma): {greeks.get('gex'):,.2f}")
                print(f"   DEX (net delta): {greeks.get('dex'):,.2f}")
                print(f"   Vanna: {greeks.get('vanna')}")
                print(f"   Charm: {greeks.get('charm')}")
                print(f"   Components: call_gamma={greeks.get('call_gamma'):,.2f}, put_gamma={greeks.get('put_gamma'):,.2f}")
                print(f"              call_delta={greeks.get('call_delta'):,.2f}, put_delta={greeks.get('put_delta'):,.2f}")
            if greeks.get("gex") == 0 and greeks.get("dex") == 0:
                print("   WARNING: GEX and DEX are both 0 - check if API returned data!")
        except Exception as e:
            print(f"   Status: FAILED")
            print(f"   Error: {e}")
        print()

        # Test 3: Unusual Whales - IV Term Structure
        print("3. UNUSUAL WHALES - IV Term Structure")
        print("-" * 40)
        try:
            iv_data = await uw_client.get_iv_term_structure(ticker, trade_date)
            print(f"   Status: OK" if iv_data else "   Status: EMPTY")
            print(f"   Data: {iv_data}")
        except Exception as e:
            print(f"   Status: FAILED")
            print(f"   Error: {e}")
        print()

    # Test 4: Polygon - Daily OHLCV
    print("4. POLYGON - Daily OHLCV")
    print("-" * 40)
    poly_client = PolygonClient(polygon_api_key, cache)
    async with poly_client:
        try:
            ohlcv = await poly_client.get_daily_ohlcv(ticker, trade_date)
            print(f"   Status: OK" if ohlcv else "   Status: EMPTY")
            print(f"   Data: {ohlcv}")
            if not ohlcv:
                print("   WARNING: No OHLCV data returned!")

            # Calculate dark pool ratio if we have both data points
            if ohlcv and aggregated and ohlcv.get("volume"):
                dp_ratio = aggregated.get("dark_pool_volume", 0) / ohlcv["volume"] * 100
                print(f"\n   === DARK POOL RATIO ===")
                print(f"   Dark Pool Volume: {aggregated.get('dark_pool_volume', 0):,}")
                print(f"   Total Volume: {ohlcv['volume']:,.0f}")
                print(f"   Dark Pool Ratio: {dp_ratio:.1f}%")
        except Exception as e:
            print(f"   Status: FAILED")
            print(f"   Error: {e}")
    print()

    print(f"{'='*60}")
    print("DIAGNOSTICS COMPLETE")
    print(f"{'='*60}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose OBSIDIAN MM API connections")
    parser.add_argument("--ticker", type=str, default="SPY", help="Ticker to test")
    parser.add_argument("--date", type=str, default=None, help="Date to test (YYYY-MM-DD)")

    args = parser.parse_args()

    trade_date = date.fromisoformat(args.date) if args.date else None

    asyncio.run(diagnose_apis(args.ticker, trade_date))


if __name__ == "__main__":
    main()
