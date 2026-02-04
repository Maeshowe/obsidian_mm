"""
Financial Modeling Prep (FMP) API client.

Fetches ETF flows, sector performance, and macro context.
Used as overlay/context data, not primary microstructure source.
"""

import logging
from datetime import date
from typing import Any

import pandas as pd

from obsidian.core.exceptions import DataFetchError
from obsidian.ingest.base import BaseAPIClient
from obsidian.ingest.cache import CacheManager
from obsidian.ingest.rate_limiter import TokenBucketLimiter


logger = logging.getLogger(__name__)


class FMPClient(BaseAPIClient):
    """
    Client for Financial Modeling Prep API.

    Endpoints:
    - ETF holdings
    - ETF sector weights
    - Sector performance
    - Institutional ownership
    """

    SOURCE_NAME = "fmp"

    def __init__(
        self,
        api_key: str,
        cache: CacheManager,
        rate_limit_rpm: int = 300,
    ) -> None:
        """
        Initialize FMP client.

        Args:
            api_key: FMP API key
            cache: Cache manager
            rate_limit_rpm: Requests per minute limit
        """
        rate_limiter = TokenBucketLimiter.from_rpm(rate_limit_rpm)
        super().__init__(
            api_key=api_key,
            base_url="https://financialmodelingprep.com/stable",
            rate_limiter=rate_limiter,
            cache=cache,
        )

    def _auth_headers(self) -> dict[str, str]:
        """No header auth for FMP."""
        return {}

    def _auth_params(self) -> dict[str, str]:
        """API key as query parameter."""
        return {"apikey": self.api_key}

    async def get_etf_holdings(
        self,
        etf_ticker: str,
        trade_date: date,
    ) -> pd.DataFrame:
        """
        Fetch ETF holdings.

        Args:
            etf_ticker: ETF ticker symbol (e.g., SPY)
            trade_date: Date for caching purposes

        Returns:
            DataFrame with ETF holdings
        """
        endpoint = "/etf/holdings"
        params = {"symbol": etf_ticker}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("etf_holdings", etf_ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch ETF holdings for {etf_ticker}")
            return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        # Handle both list and dict responses
        holdings = data if isinstance(data, list) else data.get("data", [])
        if not holdings:
            return pd.DataFrame()

        return pd.DataFrame(holdings)

    async def get_etf_sector_weights(
        self,
        etf_ticker: str,
        trade_date: date,
    ) -> dict[str, float]:
        """
        Fetch ETF sector weightings.

        Args:
            etf_ticker: ETF ticker symbol
            trade_date: Date for caching purposes

        Returns:
            Dictionary mapping sector names to weights
        """
        endpoint = "/etf/sector-weightings"
        params = {"symbol": etf_ticker}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("sector_weights", etf_ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch sector weights for {etf_ticker}")
            return {}

        if not data:
            return {}

        # Handle response format
        weights = data if isinstance(data, list) else data.get("data", [])

        return {
            w.get("sector", ""): w.get("weightPercentage", 0.0)
            for w in weights
            if w.get("sector")
        }

    async def get_sector_performance(
        self,
        trade_date: date,
    ) -> dict[str, float]:
        """
        Fetch sector performance snapshot.

        Args:
            trade_date: Date to fetch data for

        Returns:
            Dictionary mapping sector names to performance
        """
        endpoint = "/sector-performance-snapshot"

        try:
            data = await self._get(
                endpoint,
                cache_key_parts=("sector_performance", None, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch sector performance for {trade_date}")
            return {}

        if not data:
            return {}

        # Handle response format
        performance = data if isinstance(data, list) else data.get("data", [])

        return {
            p.get("sector", ""): p.get("changesPercentage", 0.0)
            for p in performance
            if p.get("sector")
        }

    async def get_institutional_ownership(
        self,
        ticker: str,
        trade_date: date,
    ) -> dict[str, Any]:
        """
        Fetch institutional ownership data.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date for caching purposes

        Returns:
            Dictionary with institutional ownership metrics
        """
        endpoint = "/institutional-ownership/extract"
        params = {"symbol": ticker}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("institutional", ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch institutional ownership for {ticker}")
            return {}

        if not data:
            return {}

        # Extract most recent data
        records = data if isinstance(data, list) else data.get("data", [])
        if not records:
            return {}

        # Get most recent record
        latest = records[0] if records else {}

        return {
            "holders_count": latest.get("holdersCount"),
            "shares_held": latest.get("totalShares"),
            "pct_outstanding": latest.get("percentageOwnership"),
            "change_in_shares": latest.get("changeInShares"),
        }

    async def get_market_overview(
        self,
        trade_date: date,
    ) -> dict[str, Any]:
        """
        Fetch general market overview.

        Args:
            trade_date: Date for caching purposes

        Returns:
            Dictionary with market overview data
        """
        endpoint = "/market-overview"

        try:
            data = await self._get(
                endpoint,
                cache_key_parts=("market_overview", None, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch market overview for {trade_date}")
            return {}

        return data if isinstance(data, dict) else {}
