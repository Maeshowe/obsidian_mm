"""
Tests for feature extraction.
"""

import pytest
import pandas as pd

from obsidian.features.darkpool import DarkPoolFeatures, DarkPoolMetrics
from obsidian.features.greeks import GreeksFeatures, GreeksMetrics
from obsidian.features.price_context import PriceContextFeatures, PriceMetrics


class TestDarkPoolFeatures:
    """Tests for dark pool feature extraction."""

    @pytest.fixture
    def extractor(self):
        """Create dark pool extractor."""
        return DarkPoolFeatures()

    def test_extract_from_trades(
        self,
        extractor: DarkPoolFeatures,
        sample_darkpool_df: pd.DataFrame,
    ):
        """Should extract metrics from trade data."""
        metrics = extractor.extract(sample_darkpool_df)

        assert metrics.dark_pool_volume == 45000  # 5000 + 15000 + 25000
        assert metrics.trade_count == 3
        assert metrics.block_trade_count == 2  # 15000 and 25000 are blocks

    def test_empty_trades_returns_zeros(self, extractor: DarkPoolFeatures):
        """Empty DataFrame should return zero metrics."""
        metrics = extractor.extract(pd.DataFrame())

        assert metrics.dark_pool_volume == 0
        assert metrics.trade_count == 0
        assert metrics.block_trade_count == 0

    def test_calculates_dark_pool_ratio(
        self,
        extractor: DarkPoolFeatures,
        sample_darkpool_df: pd.DataFrame,
    ):
        """Should calculate dark pool ratio when total volume provided."""
        metrics = extractor.extract(
            sample_darkpool_df,
            total_volume=100000,
        )

        assert metrics.dark_pool_ratio == 45.0  # 45000 / 100000 * 100

    def test_calculates_venue_shift(
        self,
        extractor: DarkPoolFeatures,
        sample_darkpool_df: pd.DataFrame,
    ):
        """Should calculate venue shift when previous ratio provided."""
        metrics = extractor.extract(
            sample_darkpool_df,
            total_volume=100000,
            previous_ratio=40.0,
        )

        assert metrics.venue_shift == 5.0  # 45.0 - 40.0


class TestGreeksFeatures:
    """Tests for Greek exposure feature extraction."""

    @pytest.fixture
    def extractor(self):
        """Create Greeks extractor."""
        return GreeksFeatures()

    def test_extract_from_data(self, extractor: GreeksFeatures):
        """Should extract Greek metrics from data."""
        greek_data = {
            "gex": 1500000000,
            "dex": -500000000,
            "vanna": 100000,
            "charm": -50000,
        }

        metrics = extractor.extract(greek_data)

        assert metrics.gex == 1500000000
        assert metrics.dex == -500000000
        assert metrics.vanna == 100000
        assert metrics.charm == -50000

    def test_handles_missing_fields(self, extractor: GreeksFeatures):
        """Should handle missing optional fields."""
        greek_data = {
            "gex": 1000000,
            "dex": -500000,
        }

        metrics = extractor.extract(greek_data)

        assert metrics.gex == 1000000
        assert metrics.vanna is None
        assert metrics.charm is None

    def test_calculates_iv_skew(self, extractor: GreeksFeatures):
        """Should calculate IV skew from term structure."""
        greek_data = {"gex": 0, "dex": 0}
        iv_data = {
            "iv_25d_put": 0.25,
            "iv_25d_call": 0.20,
        }

        metrics = extractor.extract(greek_data, iv_data)

        assert metrics.iv_skew == pytest.approx(0.05)  # 0.25 - 0.20


class TestPriceContextFeatures:
    """Tests for price context feature extraction."""

    @pytest.fixture
    def extractor(self):
        """Create price context extractor."""
        return PriceContextFeatures()

    def test_extract_from_ohlcv(self, extractor: PriceContextFeatures):
        """Should extract price metrics from OHLCV."""
        ohlcv = {
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 103.0,
            "volume": 1000000,
        }

        metrics = extractor.extract(ohlcv)

        assert metrics.open_price == 100.0
        assert metrics.close_price == 103.0
        assert metrics.price_change == 3.0  # 103 - 100
        assert metrics.price_change_pct == 3.0  # 3%
        assert metrics.daily_range == 7.0  # 105 - 98

    def test_calculates_close_position(self, extractor: PriceContextFeatures):
        """Should calculate where close is within range."""
        ohlcv = {
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 100.0,  # Exactly middle
            "volume": 1000000,
        }

        metrics = extractor.extract(ohlcv)

        assert metrics.close_position == 0.5  # Middle of range

    def test_calculates_price_efficiency(self, extractor: PriceContextFeatures):
        """Should calculate price efficiency metric."""
        ohlcv = {
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1000000,
        }

        metrics = extractor.extract(ohlcv)

        # price_efficiency = range / (volume / 1M) = 3 / 1 = 3
        assert metrics.price_efficiency == 3.0

    def test_calculates_impact_per_vol(self, extractor: PriceContextFeatures):
        """Should calculate impact per volume metric."""
        ohlcv = {
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 102.0,  # +2 change
            "volume": 1000000,
        }

        metrics = extractor.extract(ohlcv)

        # impact_per_vol = |change| / (volume / 1M) = 2 / 1 = 2
        assert metrics.impact_per_vol == 2.0

    def test_volume_vs_average(self, extractor: PriceContextFeatures):
        """Should calculate volume relative to average."""
        ohlcv = {
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1500000,
        }

        metrics = extractor.extract(ohlcv, avg_volume=1000000)

        assert metrics.volume_vs_avg == 1.5  # 1.5x average
