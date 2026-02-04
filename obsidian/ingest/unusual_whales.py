"""
Unusual Whales API client.

Fetches dark pool data, Greek exposure, and options flow.
Primary source for market microstructure data.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from obsidian.core.constants import BLOCK_TRADE_MIN_SHARES
from obsidian.core.exceptions import DataFetchError
from obsidian.ingest.base import BaseAPIClient
from obsidian.ingest.cache import CacheManager
from obsidian.ingest.rate_limiter import TokenBucketLimiter


logger = logging.getLogger(__name__)


@dataclass
class DarkPoolTrade:
    """Schema for a dark pool trade."""

    executed_at: str
    ticker: str
    size: int
    price: float
    premium: float
    nbbo_bid: float
    nbbo_ask: float
    market_center: str
    sale_cond_codes: str | None = None
    trade_code: str | None = None
    canceled: bool = False


@dataclass
class GreekExposure:
    """Schema for Greek exposure data."""

    date: str
    gex: float  # Gamma exposure
    dex: float  # Delta exposure
    vanna: float | None = None
    charm: float | None = None


class UnusualWhalesClient(BaseAPIClient):
    """
    Client for Unusual Whales API.

    Endpoints:
    - Dark pool trades
    - Greek exposure (GEX, DEX, vanna, charm)
    - Options flow
    - IV term structure
    """

    SOURCE_NAME = "unusual_whales"

    def __init__(
        self,
        api_key: str,
        cache: CacheManager,
        rate_limit_rpm: int = 60,
    ) -> None:
        """
        Initialize Unusual Whales client.

        Args:
            api_key: UW API key
            cache: Cache manager
            rate_limit_rpm: Requests per minute limit
        """
        rate_limiter = TokenBucketLimiter.from_rpm(rate_limit_rpm)
        super().__init__(
            api_key=api_key,
            base_url="https://api.unusualwhales.com/api",
            rate_limiter=rate_limiter,
            cache=cache,
        )

    def _auth_headers(self) -> dict[str, str]:
        """Bearer token authentication."""
        return {"Authorization": f"Bearer {self.api_key}"}

    def _auth_params(self) -> dict[str, str]:
        """No query param auth for UW."""
        return {}

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float, handling strings and None."""
        if value is None:
            return default
        try:
            if isinstance(value, str):
                value = value.strip().strip("'\"")
            return float(value)
        except (ValueError, TypeError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        """Safely convert value to int, handling strings and None."""
        if value is None:
            return default
        try:
            if isinstance(value, str):
                value = value.strip().strip("'\"")
            return int(float(value))
        except (ValueError, TypeError):
            return default

    async def get_darkpool_trades(
        self,
        ticker: str,
        trade_date: date,
        include_avg_price_trades: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch ALL dark pool trades for a ticker on a date (with pagination).

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to fetch trades for
            include_avg_price_trades: Include VWAP/TWAP orders (default True)

        Returns:
            DataFrame with dark pool trades
        """
        # Check DataFrame cache first
        cached_df = self.cache.load_dataframe(
            self.SOURCE_NAME, "darkpool", ticker, trade_date
        )
        if cached_df is not None:
            return cached_df

        endpoint = f"/darkpool/{ticker}"
        all_trades: list[dict] = []
        older_than: str | None = None
        max_pages = 100  # Safety limit

        # Paginate through all trades (API limit is 500 per request)
        # Don't cache individual pages - only cache final processed DataFrame
        for page in range(max_pages):
            params = {"date": trade_date.isoformat(), "limit": 500}
            if older_than:
                params["older_than"] = older_than

            try:
                data = await self._get(
                    endpoint,
                    params,
                    cache_key_parts=None,  # Skip raw cache for paginated requests
                )
            except DataFetchError:
                logger.warning(f"Failed to fetch dark pool data for {ticker} on {trade_date}")
                break

            trades_data = data.get("data", [])
            if not trades_data:
                break

            all_trades.extend(trades_data)

            # Check if we got less than limit (no more pages)
            if len(trades_data) < 500:
                break

            # Get oldest timestamp for next page
            oldest_trade = min(trades_data, key=lambda t: t.get("executed_at", ""))
            older_than = oldest_trade.get("executed_at")

            logger.debug(f"Dark pool page {page + 1}: {len(trades_data)} trades, total: {len(all_trades)}")

        if not all_trades:
            return pd.DataFrame()

        logger.info(f"Fetched {len(all_trades)} total dark pool trades for {ticker} on {trade_date}")

        # Filter trades
        valid_trades = []
        for t in all_trades:
            # Skip canceled trades
            if t.get("canceled", False):
                continue
            # Optionally skip average price trades (VWAP/TWAP)
            if not include_avg_price_trades and t.get("sale_cond_codes") == "average_price_trade":
                continue
            # Skip qualified contingent trades (linked to other transactions)
            if t.get("trade_code") == "qualified_contingent_trade":
                continue

            valid_trades.append({
                "executed_at": t.get("executed_at"),
                "ticker": t.get("ticker", ticker),
                "size": self._safe_int(t.get("size")),
                "price": self._safe_float(t.get("price")),
                "premium": self._safe_float(t.get("premium")),
                "nbbo_bid": self._safe_float(t.get("nbbo_bid")),
                "nbbo_ask": self._safe_float(t.get("nbbo_ask")),
                "market_center": t.get("market_center", ""),
                "sale_cond_codes": t.get("sale_cond_codes"),
            })

        df = pd.DataFrame(valid_trades)

        # Cache the processed DataFrame
        if not df.empty:
            self.cache.save_dataframe(df, self.SOURCE_NAME, "darkpool", ticker, trade_date)

        return df

    async def get_greek_exposure(
        self,
        ticker: str,
        trade_date: date,
    ) -> dict[str, Any]:
        """
        Fetch Greek exposure (GEX, DEX, vanna, charm) for a ticker.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to fetch exposure for

        Returns:
            Dictionary with Greek exposure values
        """
        endpoint = f"/stock/{ticker}/greek-exposure"
        params = {"date": trade_date.isoformat()}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("greek_exposure", ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch Greek exposure for {ticker} on {trade_date}")
            return {}

        # Extract relevant fields - handle both list and dict responses
        raw_data = data.get("data", {})

        # If API returns a list, take the first item or empty dict
        if isinstance(raw_data, list):
            exposure = raw_data[0] if raw_data else {}
        else:
            exposure = raw_data

        # API returns separate call/put components - calculate net exposure
        # GEX = call_gamma + put_gamma (put_gamma is negative in API response)
        # DEX = call_delta + put_delta (put_delta is negative in API response)
        call_gamma = self._safe_float(exposure.get("call_gamma"))
        put_gamma = self._safe_float(exposure.get("put_gamma"))
        call_delta = self._safe_float(exposure.get("call_delta"))
        put_delta = self._safe_float(exposure.get("put_delta"))
        call_vanna = self._safe_float(exposure.get("call_vanna"))
        put_vanna = self._safe_float(exposure.get("put_vanna"))
        call_charm = self._safe_float(exposure.get("call_charm"))
        put_charm = self._safe_float(exposure.get("put_charm"))

        gex = call_gamma + put_gamma
        dex = call_delta + put_delta
        vanna = call_vanna + put_vanna if (call_vanna or put_vanna) else None
        charm = call_charm + put_charm if (call_charm or put_charm) else None

        return {
            "gex": gex,
            "dex": dex,
            "vanna": vanna,
            "charm": charm,
            "date": trade_date.isoformat(),
            # Keep raw components for debugging
            "call_gamma": call_gamma,
            "put_gamma": put_gamma,
            "call_delta": call_delta,
            "put_delta": put_delta,
        }

    async def get_market_greeks(
        self,
        trade_date: date,
    ) -> dict[str, Any]:
        """
        Fetch market-wide Greek metrics.

        Args:
            trade_date: Date to fetch data for

        Returns:
            Dictionary with market Greek exposure
        """
        endpoint = "/market/greeks"
        params = {"date": trade_date.isoformat()}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("market_greeks", None, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch market Greeks for {trade_date}")
            return {}

        raw_data = data.get("data", {})
        if isinstance(raw_data, list):
            return raw_data[0] if raw_data else {}
        return raw_data

    async def get_options_flow(
        self,
        ticker: str,
        trade_date: date,
    ) -> pd.DataFrame:
        """
        Fetch options flow for a ticker.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to fetch flow for

        Returns:
            DataFrame with options flow data
        """
        endpoint = f"/stock/{ticker}/flow"
        params = {"date": trade_date.isoformat()}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("flow", ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch options flow for {ticker} on {trade_date}")
            return pd.DataFrame()

        flow_data = data.get("data", [])
        if not flow_data:
            return pd.DataFrame()

        return pd.DataFrame(flow_data)

    async def get_iv_term_structure(
        self,
        ticker: str,
        trade_date: date,
    ) -> dict[str, Any]:
        """
        Fetch IV term structure for a ticker.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date to fetch structure for

        Returns:
            Dictionary with IV at various expirations
        """
        # API endpoint: /api/stock/{ticker}/volatility/term-structure
        endpoint = f"/stock/{ticker}/volatility/term-structure"
        params = {"date": trade_date.isoformat()}

        try:
            data = await self._get(
                endpoint,
                params,
                cache_key_parts=("iv_term", ticker, trade_date),
            )
        except DataFetchError:
            logger.warning(f"Failed to fetch IV term structure for {ticker} on {trade_date}")
            return {}

        raw_data = data.get("data", {})
        if isinstance(raw_data, list):
            return raw_data[0] if raw_data else {}
        return raw_data

    def aggregate_darkpool_daily(
        self,
        trades_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """
        Aggregate dark pool trades to daily metrics.

        Args:
            trades_df: DataFrame of individual trades

        Returns:
            Dictionary with daily aggregates
        """
        if trades_df.empty:
            return {
                "dark_pool_volume": 0,
                "dark_pool_notional": 0.0,
                "trade_count": 0,
                "block_trade_count": 0,
                "block_trade_volume": 0,
                "avg_trade_size": 0.0,
                "avg_block_size": 0.0,
            }

        # Total dark pool metrics
        total_volume = trades_df["size"].sum()
        total_notional = trades_df["premium"].sum()
        trade_count = len(trades_df)

        # Block trades (> 10k shares)
        blocks = trades_df[trades_df["size"] >= BLOCK_TRADE_MIN_SHARES]
        block_count = len(blocks)
        block_volume = blocks["size"].sum() if not blocks.empty else 0

        return {
            "dark_pool_volume": int(total_volume),
            "dark_pool_notional": float(total_notional),
            "trade_count": trade_count,
            "block_trade_count": block_count,
            "block_trade_volume": int(block_volume),
            "avg_trade_size": float(total_volume / trade_count) if trade_count > 0 else 0.0,
            "avg_block_size": float(block_volume / block_count) if block_count > 0 else 0.0,
        }
