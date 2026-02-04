"""Core module containing types, configuration, and shared utilities."""

from obsidian.core.types import (
    RegimeLabel,
    RegimeResult,
    UnusualnessResult,
    FeatureSet,
    NormalizationMethod,
)
from obsidian.core.config import Settings, load_config
from obsidian.core.exceptions import (
    ObsidianError,
    ConfigurationError,
    DataFetchError,
    InsufficientDataError,
    ValidationError,
)

__all__ = [
    # Types
    "RegimeLabel",
    "RegimeResult",
    "UnusualnessResult",
    "FeatureSet",
    "NormalizationMethod",
    # Config
    "Settings",
    "load_config",
    # Exceptions
    "ObsidianError",
    "ConfigurationError",
    "DataFetchError",
    "InsufficientDataError",
    "ValidationError",
]
