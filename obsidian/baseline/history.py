"""
Feature History Storage for OBSIDIAN MM.

Stores daily feature values for incremental baseline computation.
This allows baselines to be computed from locally collected data
even when the API doesn't provide long historical access.

Storage structure:
    data/feature_history/
    ├── SPY/
    │   ├── 2026-01-15.json
    │   ├── 2026-01-16.json
    │   └── ...
    └── QQQ/
        └── ...

DESIGN PRINCIPLE:
    Collect data daily → Build history over time → Compute baseline from history
    This overcomes API limitations on historical data access.
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class FeatureHistoryStorage:
    """
    Persistent storage for daily feature snapshots.

    Used to accumulate data over time for baseline computation,
    especially for metrics like vanna/charm where API only provides
    limited historical access.
    """

    def __init__(self, base_dir: Path | str = "data/feature_history"):
        """
        Initialize feature history storage.

        Args:
            base_dir: Directory to store feature history files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _ticker_dir(self, ticker: str) -> Path:
        """Get directory for a ticker's history."""
        path = self.base_dir / ticker.upper()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _date_path(self, ticker: str, trade_date: date) -> Path:
        """Get path for a specific date's features."""
        return self._ticker_dir(ticker) / f"{trade_date.isoformat()}.json"

    def save(
        self,
        ticker: str,
        trade_date: date,
        features: dict[str, Any],
    ) -> bool:
        """
        Save features for a specific date.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date of the features
            features: Dictionary of feature values

        Returns:
            True if successful
        """
        path = self._date_path(ticker, trade_date)

        try:
            data = {
                "ticker": ticker.upper(),
                "date": trade_date.isoformat(),
                "features": features,
                "saved_at": date.today().isoformat(),
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(f"Saved feature history for {ticker} on {trade_date}")
            return True

        except Exception as e:
            logger.error(f"Failed to save feature history: {e}")
            return False

    def load(self, ticker: str, trade_date: date) -> dict[str, Any] | None:
        """
        Load features for a specific date.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to load

        Returns:
            Feature dictionary or None if not found
        """
        path = self._date_path(ticker, trade_date)

        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("features")
        except Exception as e:
            logger.error(f"Failed to load feature history: {e}")
            return None

    def exists(self, ticker: str, trade_date: date) -> bool:
        """Check if features exist for a date."""
        return self._date_path(ticker, trade_date).exists()

    def list_dates(self, ticker: str) -> list[date]:
        """
        List all available dates for a ticker.

        Returns:
            Sorted list of dates with stored features
        """
        ticker_dir = self._ticker_dir(ticker)
        dates = []

        for f in ticker_dir.glob("*.json"):
            try:
                d = date.fromisoformat(f.stem)
                dates.append(d)
            except ValueError:
                continue

        return sorted(dates)

    def get_date_range(self, ticker: str) -> tuple[date | None, date | None]:
        """
        Get the date range of stored history.

        Returns:
            (earliest_date, latest_date) or (None, None) if no data
        """
        dates = self.list_dates(ticker)
        if not dates:
            return None, None
        return dates[0], dates[-1]

    def count_observations(self, ticker: str) -> int:
        """Count number of stored observations for a ticker."""
        return len(self.list_dates(ticker))

    def load_dataframe(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        min_days: int = 0,
    ) -> pd.DataFrame:
        """
        Load feature history as a DataFrame.

        Args:
            ticker: Stock ticker symbol
            start_date: Earliest date to include (optional)
            end_date: Latest date to include (optional)
            min_days: Minimum days required (raises if not met)

        Returns:
            DataFrame with one row per date

        Raises:
            ValueError: If insufficient data
        """
        dates = self.list_dates(ticker)

        if not dates:
            if min_days > 0:
                raise ValueError(f"No feature history for {ticker}")
            return pd.DataFrame()

        # Filter by date range
        if start_date:
            dates = [d for d in dates if d >= start_date]
        if end_date:
            dates = [d for d in dates if d <= end_date]

        if len(dates) < min_days:
            raise ValueError(
                f"Insufficient feature history for {ticker}: "
                f"have {len(dates)} days, need {min_days}"
            )

        # Load all features
        records = []
        for d in dates:
            features = self.load(ticker, d)
            if features:
                features["date"] = d
                features["ticker"] = ticker.upper()
                records.append(features)

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)

        return df

    def get_missing_dates(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """
        Get list of missing trading dates in a range.

        Args:
            ticker: Stock ticker symbol
            start_date: Start of range
            end_date: End of range

        Returns:
            List of dates that are missing (excluding weekends)
        """
        existing = set(self.list_dates(ticker))
        missing = []

        current = start_date
        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5 and current not in existing:
                missing.append(current)
            current += timedelta(days=1)

        return missing

    def cleanup_old(self, ticker: str, keep_days: int = 365) -> int:
        """
        Remove feature history older than keep_days.

        Args:
            ticker: Stock ticker symbol
            keep_days: Number of days to keep

        Returns:
            Number of files removed
        """
        cutoff = date.today() - timedelta(days=keep_days)
        removed = 0

        for d in self.list_dates(ticker):
            if d < cutoff:
                path = self._date_path(ticker, d)
                path.unlink()
                removed += 1

        if removed > 0:
            logger.info(f"Removed {removed} old feature files for {ticker}")

        return removed

    def get_summary(self, ticker: str) -> dict[str, Any]:
        """
        Get summary of stored feature history.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Summary dictionary
        """
        dates = self.list_dates(ticker)

        if not dates:
            return {
                "ticker": ticker.upper(),
                "observation_count": 0,
                "has_data": False,
            }

        # Check what features are available
        sample = self.load(ticker, dates[-1]) or {}
        available_features = list(sample.keys())

        return {
            "ticker": ticker.upper(),
            "observation_count": len(dates),
            "has_data": True,
            "earliest_date": dates[0].isoformat(),
            "latest_date": dates[-1].isoformat(),
            "available_features": available_features,
            "has_vanna": "vanna" in available_features and sample.get("vanna") is not None,
            "has_charm": "charm" in available_features and sample.get("charm") is not None,
        }
