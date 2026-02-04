"""
Polygon.io API client.

Fetches daily OHLCV data and market context.
"""

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from obsidian.core.exceptions import DataFetchError
from obsidian.ingest.base import BaseAPIClient
from obsidian.ingest.cache import CacheManager
from obsidian.ingest.rate_limiter import TokenBucketLimiter


logger = logging.getLogger(__name__)


class PolygonClient(BaseAPIClient):
    """
    Client for Polygon.io API.

    Endpoints:
    - Daily OHLCV aggregates
    - Previous close
    - Grouped daily (all tickers)
    """

    SOURCE_NAME = "polygon"

    def __init__(
        self,
        api_key: str,
        cache: CacheManager,
        rate_limit_rpm: int = 5,  # Free tier default
    ) -> None:
        """
        Initialize Polygon client.

        Args:
            api_key: Polygon API key
            cache: Cache manager
            rate_limit_rpm: Requests per minute limit (5 for free tier)
        """
        rate_limiter = TokenBucketLimiter.from_rpm(rate_limit_rpm)
        super().__init__(
            api_key=api_key,
            base_url="https://api.polygon.io",
            rate_limiter=rate_limiter,
            cache=cache,
        )

    def _auth_headers(self) -> dict[str, str]:
        """No header auth for Polygon."""
        return {}

    def _auth_params(self) -> dict[str, str]:
        """API key as query parameter."""
        return {"apiKey": self.api_key}

    async def get_daily_ohlcv(
        self,
        ticker: str,
        trade_date: date,
    ) -> dict[str, Any]:
        """
        Fetch daily OHLCV for a ticker using v2 aggregates endpoint.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to fetch data for

        Returns:
            Dictionary with OHLCV data including VWAP
        """
        # Use v2 aggregates endpoint for reliable VWAP
        date_str = trade_date.isoformat()
        endpoint = f"/v2/aggs/ticker/{ticker}/range/1/day/{date_str}/{date_str}"
        params = {"adjusted": "true"}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("daily_ohlcv", ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch OHLCV for {ticker} on {trade_date}")
            return {}

        results = data.get("results", [])
        if not results:
            logger.warning(f"No OHLCV data for {ticker} on {trade_date}")
            return {}

        r = results[0]
        return {
            "ticker": ticker,
            "date": trade_date.isoformat(),
            "open": r.get("o"),
            "high": r.get("h"),
            "low": r.get("l"),
            "close": r.get("c"),
            "volume": r.get("v"),
            "vwap": r.get("vw"),
            "transactions": r.get("n"),
        }

    async def get_aggregates(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> pd.DataFrame:
        """
        Fetch daily aggregates for a date range.

        Args:
            ticker: Stock ticker symbol
            from_date: Start date
            to_date: End date

        Returns:
            DataFrame with daily OHLCV data
        """
        endpoint = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date.isoformat()}/{to_date.isoformat()}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 5000,
        }

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("aggregates", ticker, to_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch aggregates for {ticker}")
            return pd.DataFrame()

        results = data.get("results", [])
        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # Rename columns to standard names
        column_map = {
            "t": "timestamp",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "vw": "vwap",
            "n": "transactions",
        }
        df = df.rename(columns=column_map)

        # Convert timestamp to date
        if "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.date
            df["ticker"] = ticker

        return df

    async def get_previous_close(
        self,
        ticker: str,
    ) -> dict[str, Any]:
        """
        Fetch previous trading day's close.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with previous close data
        """
        endpoint = f"/v2/aggs/ticker/{ticker}/prev"

        try:
            data = await self._get(endpoint)
        except DataFetchError:
            logger.warning(f"Failed to fetch previous close for {ticker}")
            return {}

        results = data.get("results", [])
        if not results:
            return {}

        r = results[0]
        return {
            "ticker": ticker,
            "close": r.get("c"),
            "volume": r.get("v"),
            "vwap": r.get("vw"),
            "date": date.fromtimestamp(r.get("t", 0) / 1000).isoformat() if r.get("t") else None,
        }

    async def get_grouped_daily(
        self,
        trade_date: date,
    ) -> pd.DataFrame:
        """
        Fetch daily data for all tickers on a date.

        Args:
            trade_date: Date to fetch data for

        Returns:
            DataFrame with all tickers' daily data
        """
        endpoint = f"/v2/aggs/grouped/locale/us/market/stocks/{trade_date.isoformat()}"
        params = {"adjusted": "true"}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("grouped_daily", None, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch grouped daily for {trade_date}")
            return pd.DataFrame()

        results = data.get("results", [])
        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # Rename columns
        column_map = {
            "T": "ticker",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "vw": "vwap",
            "n": "transactions",
        }
        df = df.rename(columns=column_map)
        df["date"] = trade_date

        return df

    def calculate_price_metrics(
        self,
        ohlcv: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Calculate derived price metrics from OHLCV.

        Args:
            ohlcv: Dictionary with OHLCV data

        Returns:
            Dictionary with calculated metrics
        """
        open_price = ohlcv.get("open")
        high = ohlcv.get("high")
        low = ohlcv.get("low")
        close = ohlcv.get("close")
        volume = ohlcv.get("volume")

        if not all([open_price, high, low, close]):
            return {}

        return {
            "price_change": close - open_price,
            "price_change_pct": ((close - open_price) / open_price) * 100 if open_price else 0,
            "daily_range": high - low,
            "daily_range_pct": ((high - low) / open_price) * 100 if open_price else 0,
            "close_position": (close - low) / (high - low) if high != low else 0.5,
        }
