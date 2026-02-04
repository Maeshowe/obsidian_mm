#!/usr/bin/env python3
"""
Batch pipeline runner for OBSIDIAN MM.

Fetches data for all tickers in the config file.
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from obsidian.core.config import load_config
from obsidian.pipeline.daily import DailyPipeline


async def run_batch(
    trade_date: date | None = None,
    tickers: list[str] | None = None,
    skip_existing: bool = True,
) -> dict[str, str]:
    """
    Run pipeline for multiple tickers.

    Args:
        trade_date: Date to process (default: today)
        tickers: List of tickers (default: from config)
        skip_existing: Skip tickers that already have data

    Returns:
        Dict mapping ticker to status ("success", "skipped", or error message)
    """
    if trade_date is None:
        trade_date = date.today()

    # Load tickers from config if not provided
    if tickers is None:
        sources_config = load_config("sources")
        tickers = sources_config.default_tickers

    pipeline = DailyPipeline()
    results = {}

    print(f"\n{'='*60}")
    print(f"OBSIDIAN MM - Batch Pipeline")
    print(f"Date: {trade_date}")
    print(f"Tickers: {len(tickers)}")
    print(f"Skip existing: {skip_existing}")
    print(f"{'='*60}\n")

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Processing {ticker}...", end=" ", flush=True)

        # Check if data exists
        if skip_existing:
            data_file = (
                PROJECT_ROOT
                / "data"
                / "processed"
                / "regimes"
                / ticker
                / f"{trade_date.isoformat()}.parquet"
            )
            if data_file.exists():
                print("SKIPPED (exists)")
                results[ticker] = "skipped"
                continue

        try:
            result = await pipeline.run(ticker, trade_date)
            pipeline.save_result(result)
            print(f"OK (score: {result.unusualness.score:.0f}, regime: {result.regime.label.value})")
            results[ticker] = "success"
        except Exception as e:
            error_msg = str(e)[:50]
            print(f"FAILED: {error_msg}")
            results[ticker] = f"error: {error_msg}"

    # Summary
    success = sum(1 for v in results.values() if v == "success")
    skipped = sum(1 for v in results.values() if v == "skipped")
    failed = sum(1 for v in results.values() if v.startswith("error"))

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Success: {success}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed:  {failed}")
    print(f"{'='*60}\n")

    return results


def get_us_market_holidays(year: int) -> set[date]:
    """Get US market holidays for a given year."""
    holidays = set()

    # New Year's Day (Jan 1, or observed on Monday if Sunday)
    ny = date(year, 1, 1)
    if ny.weekday() == 6:  # Sunday
        holidays.add(date(year, 1, 2))
    else:
        holidays.add(ny)

    # MLK Day (3rd Monday of January)
    jan1 = date(year, 1, 1)
    first_monday = jan1 + timedelta(days=(7 - jan1.weekday()) % 7)
    if first_monday.month != 1:
        first_monday = date(year, 1, 1) + timedelta(days=(7 - jan1.weekday()) % 7)
    mlk = first_monday + timedelta(weeks=2)
    if mlk.day < 15:
        mlk += timedelta(weeks=1)
    holidays.add(mlk)

    # Presidents Day (3rd Monday of February)
    feb1 = date(year, 2, 1)
    first_monday = feb1 + timedelta(days=(7 - feb1.weekday()) % 7)
    pres = first_monday + timedelta(weeks=2)
    if pres.day < 15:
        pres += timedelta(weeks=1)
    holidays.add(pres)

    # Good Friday (varies - approximate)
    # Memorial Day (last Monday of May)
    may31 = date(year, 5, 31)
    memorial = may31 - timedelta(days=(may31.weekday()))
    holidays.add(memorial)

    # Juneteenth (June 19)
    june19 = date(year, 6, 19)
    if june19.weekday() == 5:  # Saturday
        holidays.add(date(year, 6, 18))
    elif june19.weekday() == 6:  # Sunday
        holidays.add(date(year, 6, 20))
    else:
        holidays.add(june19)

    # Independence Day (July 4)
    july4 = date(year, 7, 4)
    if july4.weekday() == 5:
        holidays.add(date(year, 7, 3))
    elif july4.weekday() == 6:
        holidays.add(date(year, 7, 5))
    else:
        holidays.add(july4)

    # Labor Day (1st Monday of September)
    sep1 = date(year, 9, 1)
    labor = sep1 + timedelta(days=(7 - sep1.weekday()) % 7)
    holidays.add(labor)

    # Thanksgiving (4th Thursday of November)
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    thanksgiving = first_thu + timedelta(weeks=3)
    holidays.add(thanksgiving)

    # Christmas (Dec 25)
    xmas = date(year, 12, 25)
    if xmas.weekday() == 5:
        holidays.add(date(year, 12, 24))
    elif xmas.weekday() == 6:
        holidays.add(date(year, 12, 26))
    else:
        holidays.add(xmas)

    return holidays


def generate_date_range(start_date: date, end_date: date) -> list[date]:
    """Generate list of trading dates between start and end (inclusive)."""
    # Collect holidays for all years in range
    holidays = set()
    for year in range(start_date.year, end_date.year + 1):
        holidays.update(get_us_market_holidays(year))

    dates = []
    current = start_date
    while current <= end_date:
        # Skip weekends (Saturday=5, Sunday=6) and holidays
        if current.weekday() < 5 and current not in holidays:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run OBSIDIAN MM pipeline for multiple tickers")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Trade date (YYYY-MM-DD format, default: today)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        default=None,
        help="Start date for range (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=str,
        default=None,
        help="End date for range (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        nargs="+",
        default=None,
        help="Specific tickers to process (default: all from config)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if data exists",
    )

    args = parser.parse_args()

    # Determine dates to process
    if args.from_date and args.to_date:
        # Date range mode
        start = date.fromisoformat(args.from_date)
        end = date.fromisoformat(args.to_date)
        dates = generate_date_range(start, end)

        # Count skipped days
        total_days = (end - start).days + 1
        skipped_days = total_days - len(dates)

        print(f"\n📅 Date range: {start} to {end}")
        print(f"   Total calendar days: {total_days}")
        print(f"   Trading days: {len(dates)}")
        print(f"   Skipped (weekends + holidays): {skipped_days}\n")
    elif args.date:
        # Single date mode
        dates = [date.fromisoformat(args.date)]
    else:
        # Default to today
        dates = [date.today()]

    # Run batch for each date
    total_success = 0
    total_skipped = 0
    total_failed = 0

    for trade_date in dates:
        results = asyncio.run(
            run_batch(
                trade_date=trade_date,
                tickers=args.tickers,
                skip_existing=not args.force,
            )
        )
        total_success += sum(1 for v in results.values() if v == "success")
        total_skipped += sum(1 for v in results.values() if v == "skipped")
        total_failed += sum(1 for v in results.values() if v.startswith("error"))

    # Final summary for date range
    if len(dates) > 1:
        print(f"\n{'='*60}")
        print(f"GRAND TOTAL ({len(dates)} days)")
        print(f"  Success: {total_success}")
        print(f"  Skipped: {total_skipped}")
        print(f"  Failed:  {total_failed}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
