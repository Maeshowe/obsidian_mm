"""
Configuration management for OBSIDIAN MM.

Loads settings from environment variables, Streamlit secrets, and YAML config files.
Uses pydantic for validation.

Priority order:
1. Streamlit secrets (for cloud deployment)
2. Environment variables
3. .env file
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from obsidian.core.exceptions import ConfigurationError


def _load_streamlit_secrets() -> None:
    """
    Load Streamlit secrets into environment variables.

    This allows the app to work both locally (with .env) and
    on Streamlit Cloud (with secrets).
    """
    try:
        import streamlit as st

        # Check if running in Streamlit and secrets are available
        if hasattr(st, "secrets") and len(st.secrets) > 0:
            for key in ["UNUSUAL_WHALES_API_KEY", "POLYGON_API_KEY", "FMP_API_KEY"]:
                if key in st.secrets and key not in os.environ:
                    os.environ[key] = st.secrets[key]
    except Exception:
        # Not running in Streamlit or secrets not available
        pass


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    API keys and paths are loaded from .env file or environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys
    unusual_whales_api_key: str = Field(
        ...,
        description="Unusual Whales API key",
    )
    polygon_api_key: str = Field(
        ...,
        description="Polygon.io API key",
    )
    fmp_api_key: str = Field(
        ...,
        description="Financial Modeling Prep API key",
    )

    # Paths
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for data storage",
    )
    config_dir: Path = Field(
        default=Path("config"),
        description="Directory containing YAML config files",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    @field_validator("data_dir", "config_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Convert string to Path and resolve."""
        return Path(v).resolve()

    @field_validator("log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        """Ensure log level is uppercase."""
        return v.upper()

    @property
    def raw_data_dir(self) -> Path:
        """Directory for raw API responses."""
        return self.data_dir / "raw"

    @property
    def processed_data_dir(self) -> Path:
        """Directory for processed data."""
        return self.data_dir / "processed"

    @property
    def baselines_dir(self) -> Path:
        """Directory for ticker baselines."""
        return self.data_dir / "baselines"


class SourcesConfig:
    """Configuration for API sources loaded from sources.yaml."""

    def __init__(self, config_path: Path):
        self._config = self._load_yaml(config_path)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        """Load and parse YAML file."""
        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")

        with open(path) as f:
            return yaml.safe_load(f)

    @property
    def unusual_whales(self) -> dict[str, Any]:
        """Unusual Whales API configuration."""
        return self._config.get("api_sources", {}).get("unusual_whales", {})

    @property
    def polygon(self) -> dict[str, Any]:
        """Polygon API configuration."""
        return self._config.get("api_sources", {}).get("polygon", {})

    @property
    def fmp(self) -> dict[str, Any]:
        """FMP API configuration."""
        return self._config.get("api_sources", {}).get("fmp", {})

    @property
    def index_etfs(self) -> list[dict[str, str]]:
        """List of index ETFs for context."""
        return self._config.get("index_etfs", [])

    @property
    def default_tickers(self) -> list[str]:
        """Default ticker universe."""
        return self._config.get("default_tickers", [])

    @property
    def cache_config(self) -> dict[str, Any]:
        """Cache configuration."""
        return self._config.get("cache", {})


class NormalizationConfig:
    """Configuration for normalization loaded from normalization.yaml."""

    def __init__(self, config_path: Path):
        self._config = self._load_yaml(config_path)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        """Load and parse YAML file."""
        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")

        with open(path) as f:
            return yaml.safe_load(f)

    @property
    def default_window(self) -> int:
        """Default rolling window size."""
        return self._config.get("normalization", {}).get("default_window", 63)

    @property
    def min_observations(self) -> int:
        """Minimum observations required."""
        return self._config.get("normalization", {}).get("min_observations", 21)

    def get_feature_config(self, feature: str) -> dict[str, Any]:
        """Get configuration for a specific feature."""
        features = self._config.get("normalization", {}).get("features", {})
        default = {
            "method": "zscore",
            "window": self.default_window,
        }
        return features.get(feature, default)


class RegimesConfig:
    """Configuration for regime classification loaded from regimes.yaml."""

    def __init__(self, config_path: Path):
        self._config = self._load_yaml(config_path)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        """Load and parse YAML file."""
        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")

        with open(path) as f:
            return yaml.safe_load(f)

    @property
    def thresholds(self) -> dict[str, float]:
        """Threshold values for regime classification."""
        return self._config.get("thresholds", {})

    @property
    def regimes(self) -> dict[str, dict[str, Any]]:
        """Regime definitions."""
        return self._config.get("regimes", {})

    @property
    def required_features(self) -> list[str]:
        """Features required for classification."""
        return self._config.get("required_features", [])

    def get_threshold(self, name: str) -> float:
        """Get a specific threshold value."""
        if name not in self.thresholds:
            raise ConfigurationError(f"Unknown threshold: {name}")
        return self.thresholds[name]

    def get_regime(self, name: str) -> dict[str, Any]:
        """Get a specific regime definition."""
        if name not in self.regimes:
            raise ConfigurationError(f"Unknown regime: {name}")
        return self.regimes[name]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached application settings.

    Loads Streamlit secrets first (if available) to support cloud deployment.
    """
    _load_streamlit_secrets()
    return Settings()


def load_config(config_type: str) -> SourcesConfig | NormalizationConfig | RegimesConfig:
    """
    Load a specific configuration file.

    Args:
        config_type: One of "sources", "normalization", "regimes"

    Returns:
        Appropriate config object
    """
    settings = get_settings()
    config_map = {
        "sources": (settings.config_dir / "sources.yaml", SourcesConfig),
        "normalization": (settings.config_dir / "normalization.yaml", NormalizationConfig),
        "regimes": (settings.config_dir / "regimes.yaml", RegimesConfig),
    }

    if config_type not in config_map:
        raise ConfigurationError(
            f"Unknown config type: {config_type}. "
            f"Valid types: {list(config_map.keys())}"
        )

    path, config_class = config_map[config_type]
    return config_class(path)
