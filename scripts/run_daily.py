#!/usr/bin/env python3
"""
OBSIDIAN MM - Daily Pipeline Runner

Usage:
    python scripts/run_daily.py SPY
    python scripts/run_daily.py SPY QQQ AAPL NVDA
    python scripts/run_daily.py --date 2024-01-15 SPY
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian.pipeline.daily import DailyPipeline


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="OBSIDIAN MM - Daily Market Microstructure Diagnostic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/run_daily.py SPY
    python scripts/run_daily.py SPY QQQ AAPL --date 2024-01-15
    python scripts/run_daily.py --verbose SPY

Note: This tool is for DIAGNOSTIC purposes only.
      It does NOT generate trading signals.
        """,
    )

    parser.add_argument(
        "tickers",
        nargs="+",
        help="Stock ticker symbol(s) to analyze",
    )

    parser.add_argument(
        "--date", "-d",
        type=str,
        default=None,
        help="Date to analyze (YYYY-MM-DD format, defaults to today)",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory for results",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to disk",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    setup_logging("DEBUG" if args.verbose else "INFO")
    logger = logging.getLogger(__name__)

    # Parse date
    trade_date = date.today()
    if args.date:
        try:
            trade_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            return 1

    logger.info("=" * 60)
    logger.info("OBSIDIAN MM - Market Microstructure Diagnostic")
    logger.info("=" * 60)
    logger.info(f"Tickers: {', '.join(args.tickers)}")
    logger.info(f"Date: {trade_date}")
    logger.info("=" * 60)

    # Initialize pipeline
    try:
        pipeline = DailyPipeline()
    except Exception as e:
        logger.error(f"Failed to initialize pipeline: {e}")
        logger.error("Make sure .env file exists with API keys")
        return 1

    # Run for each ticker
    results = []
    for ticker in args.tickers:
        logger.info(f"\n--- Processing {ticker} ---")

        try:
            result = await pipeline.run(ticker, trade_date)
            results.append(result)

            # Print summary
            print(f"\n{result.full_explanation}\n")

            # Save if requested
            if not args.no_save:
                output_dir = Path(args.output) if args.output else None
                pipeline.save_result(result, output_dir)

        except Exception as e:
            logger.error(f"Failed to process {ticker}: {e}")
            continue

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    for result in results:
        print(
            f"{result.ticker}: {result.regime.label.value} | "
            f"Score: {result.unusualness.score} ({result.unusualness.level.value})"
        )

    return 0


def main_sync() -> int:
    """Synchronous wrapper for main."""
    return asyncio.run(main())


if __name__ == "__main__":
    sys.exit(main_sync())
