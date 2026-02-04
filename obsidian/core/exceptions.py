"""
Custom exceptions for OBSIDIAN MM.

All exceptions inherit from ObsidianError for easy catching.
"""


class ObsidianError(Exception):
    """Base exception for all OBSIDIAN MM errors."""

    pass


class ConfigurationError(ObsidianError):
    """Raised when configuration is invalid or missing."""

    pass


class DataFetchError(ObsidianError):
    """Raised when data cannot be fetched from an API."""

    def __init__(
        self,
        message: str,
        source: str | None = None,
        ticker: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.source = source
        self.ticker = ticker
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [self.args[0]]
        if self.source:
            parts.append(f"source={self.source}")
        if self.ticker:
            parts.append(f"ticker={self.ticker}")
        if self.status_code:
            parts.append(f"status={self.status_code}")
        return " | ".join(parts)


class RateLimitError(DataFetchError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        source: str,
        retry_after: int | None = None,
    ):
        super().__init__(
            f"Rate limit exceeded for {source}",
            source=source,
            status_code=429,
        )
        self.retry_after = retry_after


class InsufficientDataError(ObsidianError):
    """Raised when there's not enough data for computation."""

    def __init__(
        self,
        message: str,
        required: int,
        available: int,
        feature: str | None = None,
    ):
        super().__init__(message)
        self.required = required
        self.available = available
        self.feature = feature

    def __str__(self) -> str:
        return (
            f"{self.args[0]} | "
            f"required={self.required}, available={self.available}"
            + (f", feature={self.feature}" if self.feature else "")
        )


class ValidationError(ObsidianError):
    """Raised when data validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: object = None,
    ):
        super().__init__(message)
        self.field = field
        self.value = value

    def __str__(self) -> str:
        parts = [self.args[0]]
        if self.field:
            parts.append(f"field={self.field}")
        if self.value is not None:
            parts.append(f"value={self.value!r}")
        return " | ".join(parts)


class CacheError(ObsidianError):
    """Raised when cache operations fail."""

    pass


class FeatureExtractionError(ObsidianError):
    """Raised when feature extraction fails."""

    def __init__(
        self,
        message: str,
        feature: str | None = None,
        ticker: str | None = None,
    ):
        super().__init__(message)
        self.feature = feature
        self.ticker = ticker


class NormalizationError(ObsidianError):
    """Raised when normalization fails."""

    def __init__(
        self,
        message: str,
        method: str | None = None,
        feature: str | None = None,
    ):
        super().__init__(message)
        self.method = method
        self.feature = feature


class ClassificationError(ObsidianError):
    """Raised when regime classification fails."""

    pass
