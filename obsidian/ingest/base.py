"""
Base API client with rate limiting and retry logic.

All API clients inherit from this base class.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, TypeVar

import httpx

from obsidian.core.exceptions import DataFetchError, RateLimitError
from obsidian.ingest.cache import CacheManager
from obsidian.ingest.rate_limiter import TokenBucketLimiter


logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseAPIClient(ABC):
    """
    Abstract base class for API clients.

    Provides:
    - Async HTTP requests with httpx
    - Rate limiting via token bucket
    - Automatic retry with exponential backoff
    - File-based caching
    """

    SOURCE_NAME: str = "base"  # Override in subclasses

    def __init__(
        self,
        api_key: str,
        base_url: str,
        rate_limiter: TokenBucketLimiter,
        cache: CacheManager,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize API client.

        Args:
            api_key: API authentication key
            base_url: Base URL for API requests
            rate_limiter: Rate limiter instance
            cache: Cache manager instance
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    def _auth_headers(self) -> dict[str, str]:
        """Return authentication headers. Override in subclasses."""
        ...

    @abstractmethod
    def _auth_params(self) -> dict[str, str]:
        """Return authentication query parameters. Override in subclasses."""
        ...

    async def __aenter__(self) -> "BaseAPIClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Accept": "application/json",
                **self._auth_headers(),
            },
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        cache_key_parts: tuple[str, str | None, date] | None = None,
    ) -> dict[str, Any]:
        """
        Make an API request with rate limiting and retry.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            cache_key_parts: Tuple of (endpoint, ticker, date) for caching

        Returns:
            JSON response data
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        # Check cache first
        if cache_key_parts:
            endpoint_name, ticker, trade_date = cache_key_parts
            cached = self.cache.load_json(
                self.SOURCE_NAME, endpoint_name, ticker, trade_date
            )
            if cached is not None:
                logger.debug(f"Cache hit: {self.SOURCE_NAME}/{endpoint_name}/{ticker}/{trade_date}")
                return cached

        # Add auth params
        all_params = {**(params or {}), **self._auth_params()}

        # Rate limit and request with retry
        for attempt in range(self.max_retries):
            await self.rate_limiter.acquire()

            try:
                response = await self._client.request(
                    method,
                    endpoint,
                    params=all_params,
                )
                response.raise_for_status()
                data = response.json()

                # Cache successful response
                if cache_key_parts:
                    endpoint_name, ticker, trade_date = cache_key_parts
                    self.cache.save_json(
                        data,
                        self.SOURCE_NAME,
                        endpoint_name,
                        ticker,
                        trade_date,
                    )

                return data

            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                if status == 429:  # Rate limited
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    logger.warning(
                        f"Rate limited by {self.SOURCE_NAME}, "
                        f"waiting {retry_after}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                elif status >= 500:  # Server error
                    wait = 2 ** attempt
                    logger.warning(
                        f"Server error from {self.SOURCE_NAME}: {status}, "
                        f"retrying in {wait}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(wait)
                    continue

                else:  # Client error - don't retry
                    raise DataFetchError(
                        f"API request failed: {e}",
                        source=self.SOURCE_NAME,
                        status_code=status,
                    ) from e

            except httpx.RequestError as e:
                wait = 2 ** attempt
                logger.warning(
                    f"Request error to {self.SOURCE_NAME}: {e}, "
                    f"retrying in {wait}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(wait)
                continue

        # All retries exhausted
        raise DataFetchError(
            f"Max retries ({self.max_retries}) exceeded for {endpoint}",
            source=self.SOURCE_NAME,
        )

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        cache_key_parts: tuple[str, str | None, date] | None = None,
    ) -> dict[str, Any]:
        """Convenience method for GET requests."""
        return await self._request("GET", endpoint, params, cache_key_parts)
