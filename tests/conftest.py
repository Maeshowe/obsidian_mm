"""
Pytest configuration and fixtures.
"""

import pytest
import pandas as pd
from datetime import date

from obsidian.core.types import FeatureSet


@pytest.fixture
def sample_features() -> pd.Series:
    """Sample normalized features for testing."""
    return pd.Series({
        # Normalized z-scores
        "gex_zscore": 2.1,
        "dex_zscore": -0.3,
        "dark_pool_ratio_zscore": 0.8,
        "block_trade_count_zscore": 1.2,
        "venue_shift_zscore": 0.5,
        "iv_skew_zscore": 0.9,

        # Raw/percentile values
        "dark_pool_ratio_pct": 45.0,
        "price_change_pct": -0.3,
        "price_efficiency_pct": 35.0,
        "impact_per_vol_pct": 42.0,
    })


@pytest.fixture
def gamma_positive_features() -> pd.Series:
    """Features that should classify as Gamma+ Control."""
    return pd.Series({
        "gex_zscore": 2.0,
        "dex_zscore": 0.5,
        "dark_pool_ratio_pct": 45.0,
        "block_trade_count_zscore": 0.3,
        "price_change_pct": 0.2,
        "price_efficiency_pct": 30.0,
        "impact_per_vol_pct": 40.0,
    })


@pytest.fixture
def gamma_negative_features() -> pd.Series:
    """Features that should classify as Gamma- Liquidity Vacuum."""
    return pd.Series({
        "gex_zscore": -2.0,
        "dex_zscore": -0.5,
        "dark_pool_ratio_pct": 50.0,
        "block_trade_count_zscore": 0.5,
        "price_change_pct": -1.5,
        "price_efficiency_pct": 60.0,
        "impact_per_vol_pct": 70.0,
    })


@pytest.fixture
def dark_dominant_features() -> pd.Series:
    """Features that should classify as Dark-Dominant Accumulation."""
    return pd.Series({
        "gex_zscore": 0.5,
        "dex_zscore": 0.0,
        "dark_pool_ratio_pct": 75.0,
        "block_trade_count_zscore": 1.5,
        "price_change_pct": 0.0,
        "price_efficiency_pct": 50.0,
        "impact_per_vol_pct": 50.0,
    })


@pytest.fixture
def neutral_features() -> pd.Series:
    """Features that should classify as Neutral."""
    return pd.Series({
        "gex_zscore": 0.3,
        "dex_zscore": -0.2,
        "dark_pool_ratio_pct": 42.0,
        "block_trade_count_zscore": 0.1,
        "price_change_pct": 0.1,
        "price_efficiency_pct": 50.0,
        "impact_per_vol_pct": 50.0,
    })


@pytest.fixture
def sample_darkpool_df() -> pd.DataFrame:
    """Sample dark pool trades DataFrame."""
    return pd.DataFrame({
        "executed_at": ["2024-01-15T10:00:00", "2024-01-15T11:00:00", "2024-01-15T12:00:00"],
        "ticker": ["SPY", "SPY", "SPY"],
        "size": [5000, 15000, 25000],
        "price": [475.50, 475.75, 476.00],
        "premium": [2377500.0, 7136250.0, 11900000.0],
        "nbbo_bid": [475.45, 475.70, 475.95],
        "nbbo_ask": [475.55, 475.80, 476.05],
        "market_center": ["XADF", "XADF", "FADF"],
    })


@pytest.fixture
def sample_trade_date() -> date:
    """Sample trade date for testing."""
    return date(2024, 1, 15)
