"""
Rate limiting for API requests.

Implements token bucket algorithm for smooth rate limiting.
"""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucketLimiter:
    """
    Token bucket rate limiter for async requests.

    Allows bursting up to `burst` requests, then limits to `rate` requests/second.
    Thread-safe through asyncio.Lock.
    """

    rate: float  # Tokens (requests) per second
    burst: int  # Maximum bucket size

    _tokens: float = field(init=False)
    _last_update: float = field(init=False)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        """Initialize token bucket to full."""
        self._tokens = float(self.burst)
        self._last_update = time.monotonic()

    @classmethod
    def from_rpm(cls, requests_per_minute: int, burst: int | None = None) -> "TokenBucketLimiter":
        """
        Create limiter from requests per minute.

        Args:
            requests_per_minute: Max requests per minute
            burst: Burst size (defaults to rpm/6 for 10-second burst)
        """
        rate = requests_per_minute / 60.0
        if burst is None:
            burst = max(1, requests_per_minute // 6)
        return cls(rate=rate, burst=burst)

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire (usually 1 per request)
        """
        async with self._lock:
            await self._wait_for_tokens(tokens)
            self._tokens -= tokens

    async def _wait_for_tokens(self, needed: int) -> None:
        """Wait until enough tokens are available."""
        while True:
            self._refill()
            if self._tokens >= needed:
                return

            # Calculate wait time for needed tokens
            deficit = needed - self._tokens
            wait_time = deficit / self.rate
            await asyncio.sleep(wait_time)

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_update = now

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (approximate)."""
        self._refill()
        return self._tokens


class MultiSourceRateLimiter:
    """
    Manages rate limiters for multiple API sources.

    Provides a simple interface to get the appropriate limiter for each source.
    """

    def __init__(self) -> None:
        self._limiters: dict[str, TokenBucketLimiter] = {}

    def register(
        self,
        source: str,
        requests_per_minute: int,
        burst: int | None = None,
    ) -> None:
        """
        Register a rate limiter for an API source.

        Args:
            source: Source name (e.g., "unusual_whales", "polygon")
            requests_per_minute: Max requests per minute
            burst: Burst size
        """
        self._limiters[source] = TokenBucketLimiter.from_rpm(
            requests_per_minute, burst
        )

    def get(self, source: str) -> TokenBucketLimiter:
        """
        Get the rate limiter for a source.

        Args:
            source: Source name

        Returns:
            Rate limiter for the source

        Raises:
            KeyError: If source not registered
        """
        if source not in self._limiters:
            raise KeyError(f"No rate limiter registered for source: {source}")
        return self._limiters[source]

    async def acquire(self, source: str, tokens: int = 1) -> None:
        """
        Acquire tokens from a source's rate limiter.

        Args:
            source: Source name
            tokens: Number of tokens to acquire
        """
        limiter = self.get(source)
        await limiter.acquire(tokens)
