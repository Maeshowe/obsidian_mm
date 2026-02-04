"""
Caching for API responses.

Two-layer caching:
1. File cache (persistent) - Parquet files for raw data
2. Memory cache (session) - LRU cache for repeated reads
"""

import hashlib
import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from obsidian.core.exceptions import CacheError


class CacheManager:
    """
    Manages file-based caching of API responses.

    Stores data as Parquet files organized by source/ticker/date.
    """

    def __init__(
        self,
        cache_dir: Path,
        ttl_hours: int = 24,
    ) -> None:
        """
        Initialize cache manager.

        Args:
            cache_dir: Root directory for cache files
            ttl_hours: Time-to-live for cache entries (hours)
        """
        self.cache_dir = Path(cache_dir)
        self.ttl = timedelta(hours=ttl_hours)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create cache directory structure."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(
        self,
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
        suffix: str = "parquet",
    ) -> Path:
        """
        Generate cache file path.

        Pattern: {cache_dir}/{source}/{endpoint}/{ticker}/{date}.{suffix}
        """
        parts = [source, endpoint]
        if ticker:
            parts.append(ticker)
        parts.append(f"{trade_date.isoformat()}.{suffix}")

        path = self.cache_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _get_json_path(
        self,
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
    ) -> Path:
        """Generate path for JSON cache file."""
        return self._get_path(source, endpoint, ticker, trade_date, suffix="json")

    def exists(
        self,
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
    ) -> bool:
        """
        Check if cache entry exists and is valid.

        Args:
            source: API source name
            endpoint: API endpoint name
            ticker: Ticker symbol (optional)
            trade_date: Date of the data

        Returns:
            True if valid cache exists
        """
        path = self._get_path(source, endpoint, ticker, trade_date)
        if not path.exists():
            # Also check JSON fallback
            json_path = self._get_json_path(source, endpoint, ticker, trade_date)
            if not json_path.exists():
                return False
            path = json_path

        # Check TTL (skip for historical data)
        if trade_date < date.today():
            return True  # Historical data doesn't expire

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime < self.ttl

    def save_dataframe(
        self,
        df: pd.DataFrame,
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
    ) -> Path:
        """
        Save DataFrame to cache.

        Args:
            df: DataFrame to cache
            source: API source name
            endpoint: API endpoint name
            ticker: Ticker symbol (optional)
            trade_date: Date of the data

        Returns:
            Path to cached file
        """
        path = self._get_path(source, endpoint, ticker, trade_date)
        try:
            df.to_parquet(path, index=False)
            return path
        except Exception as e:
            raise CacheError(f"Failed to save cache: {e}") from e

    def load_dataframe(
        self,
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
    ) -> pd.DataFrame | None:
        """
        Load DataFrame from cache.

        Args:
            source: API source name
            endpoint: API endpoint name
            ticker: Ticker symbol (optional)
            trade_date: Date of the data

        Returns:
            Cached DataFrame or None if not found
        """
        path = self._get_path(source, endpoint, ticker, trade_date)
        if not path.exists():
            return None

        try:
            return pd.read_parquet(path)
        except Exception as e:
            # Corrupted cache - delete and return None
            path.unlink(missing_ok=True)
            return None

    def save_json(
        self,
        data: dict[str, Any],
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
    ) -> Path:
        """
        Save JSON data to cache.

        Args:
            data: Dictionary to cache
            source: API source name
            endpoint: API endpoint name
            ticker: Ticker symbol (optional)
            trade_date: Date of the data

        Returns:
            Path to cached file
        """
        path = self._get_json_path(source, endpoint, ticker, trade_date)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            return path
        except Exception as e:
            raise CacheError(f"Failed to save JSON cache: {e}") from e

    def load_json(
        self,
        source: str,
        endpoint: str,
        ticker: str | None,
        trade_date: date,
    ) -> dict[str, Any] | None:
        """
        Load JSON data from cache.

        Args:
            source: API source name
            endpoint: API endpoint name
            ticker: Ticker symbol (optional)
            trade_date: Date of the data

        Returns:
            Cached data or None if not found
        """
        path = self._get_json_path(source, endpoint, ticker, trade_date)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            # Corrupted cache - delete and return None
            path.unlink(missing_ok=True)
            return None

    def clear(
        self,
        source: str | None = None,
        older_than_days: int | None = None,
    ) -> int:
        """
        Clear cache entries.

        Args:
            source: Only clear entries for this source (optional)
            older_than_days: Only clear entries older than this (optional)

        Returns:
            Number of entries cleared
        """
        count = 0
        cutoff = None
        if older_than_days:
            cutoff = datetime.now() - timedelta(days=older_than_days)

        search_path = self.cache_dir / source if source else self.cache_dir

        for path in search_path.rglob("*"):
            if path.is_file():
                if cutoff:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if mtime >= cutoff:
                        continue
                path.unlink()
                count += 1

        return count


def cache_key(*args: Any, **kwargs: Any) -> str:
    """
    Generate a cache key from arguments.

    Useful for memory caching with lru_cache.
    """
    key_data = json.dumps(
        {"args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    return hashlib.md5(key_data.encode()).hexdigest()
