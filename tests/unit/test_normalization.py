"""
Tests for normalization methods and rolling window calculations.
"""

import pytest
import numpy as np

from obsidian.normalization.methods import (
    zscore_normalize,
    percentile_normalize,
    minmax_normalize,
    log_transform,
)
from obsidian.normalization.rolling import RollingWindowCalculator, RollingStats


class TestZscoreNormalization:
    """Tests for z-score normalization."""

    def test_zscore_at_mean_is_zero(self):
        """Value at mean should have z-score of 0."""
        result = zscore_normalize(value=10.0, mean=10.0, std=2.0)
        assert result == 0.0

    def test_zscore_one_std_above(self):
        """Value one std above mean should have z-score of 1."""
        result = zscore_normalize(value=12.0, mean=10.0, std=2.0)
        assert result == 1.0

    def test_zscore_one_std_below(self):
        """Value one std below mean should have z-score of -1."""
        result = zscore_normalize(value=8.0, mean=10.0, std=2.0)
        assert result == -1.0

    def test_zscore_clips_outliers(self):
        """Extreme values should be clipped."""
        result = zscore_normalize(value=100.0, mean=10.0, std=2.0, clip_std=3.0)
        assert result == 3.0  # Clipped to max

    def test_zscore_handles_zero_std(self):
        """Zero std should return 0."""
        result = zscore_normalize(value=15.0, mean=10.0, std=0.0)
        assert result == 0.0


class TestPercentileNormalization:
    """Tests for percentile normalization."""

    def test_minimum_is_zero_percentile(self):
        """Minimum value should be 0th percentile."""
        history = np.array([5.0, 10.0, 15.0, 20.0, 25.0])
        result = percentile_normalize(value=5.0, history=history)
        assert result == 0.0

    def test_maximum_is_high_percentile(self):
        """Maximum value should be high percentile."""
        history = np.array([5.0, 10.0, 15.0, 20.0, 25.0])
        result = percentile_normalize(value=25.0, history=history)
        assert result == 80.0  # 4 out of 5 values are below

    def test_median_is_around_fifty(self):
        """Median value should be around 50th percentile."""
        history = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = percentile_normalize(value=3.0, history=history)
        assert 40.0 <= result <= 60.0

    def test_empty_history_returns_fifty(self):
        """Empty history should return 50 (middle)."""
        result = percentile_normalize(value=10.0, history=np.array([]))
        assert result == 50.0


class TestMinmaxNormalization:
    """Tests for min-max normalization."""

    def test_minimum_is_zero(self):
        """Minimum value should normalize to 0."""
        result = minmax_normalize(value=5.0, min_val=5.0, max_val=10.0)
        assert result == 0.0

    def test_maximum_is_one(self):
        """Maximum value should normalize to 1."""
        result = minmax_normalize(value=10.0, min_val=5.0, max_val=10.0)
        assert result == 1.0

    def test_middle_is_half(self):
        """Middle value should normalize to 0.5."""
        result = minmax_normalize(value=7.5, min_val=5.0, max_val=10.0)
        assert result == 0.5

    def test_zero_range_returns_half(self):
        """Zero range (min==max) should return 0.5."""
        result = minmax_normalize(value=5.0, min_val=5.0, max_val=5.0)
        assert result == 0.5


class TestLogTransform:
    """Tests for log transformation."""

    def test_log_of_one_with_offset(self):
        """log(1 + 1) should be log(2)."""
        result = log_transform(value=1.0, offset=1.0)
        assert abs(result - np.log(2)) < 0.001

    def test_log_handles_zero(self):
        """Zero with offset should work."""
        result = log_transform(value=0.0, offset=1.0)
        assert result == 0.0  # log(1) = 0

    def test_log_negative_input(self):
        """Negative input that would be <= 0 after offset returns 0."""
        result = log_transform(value=-2.0, offset=1.0)
        assert result == 0.0


class TestRollingWindowCalculator:
    """Tests for rolling window statistics."""

    def test_add_values(self):
        """Should track added values."""
        calc = RollingWindowCalculator(window=10, min_observations=3)

        for i in range(5):
            calc.add(float(i))

        assert calc.count == 5

    def test_window_limit(self):
        """Should respect window size limit."""
        calc = RollingWindowCalculator(window=5, min_observations=3)

        for i in range(10):
            calc.add(float(i))

        assert calc.count == 5  # Limited to window

    def test_is_ready(self):
        """Should report ready when min observations met."""
        calc = RollingWindowCalculator(window=10, min_observations=5)

        for i in range(3):
            calc.add(float(i))
        assert not calc.is_ready

        for i in range(3):
            calc.add(float(i))
        assert calc.is_ready

    def test_compute_stats(self):
        """Should compute correct statistics."""
        calc = RollingWindowCalculator(window=10, min_observations=3)

        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for v in values:
            calc.add(v)

        stats = calc.compute_stats()

        assert stats.count == 5
        assert stats.mean == 3.0  # Mean of 1,2,3,4,5
        assert stats.min == 1.0
        assert stats.max == 5.0
        assert stats.median == 3.0

    def test_skips_nan_values(self):
        """Should skip NaN values."""
        calc = RollingWindowCalculator(window=10, min_observations=3)

        calc.add(1.0)
        calc.add(np.nan)
        calc.add(2.0)
        calc.add(np.nan)
        calc.add(3.0)

        assert calc.count == 3  # Only valid values


class TestRollingStats:
    """Tests for RollingStats dataclass."""

    def test_empty_stats(self):
        """Empty stats should have NaN values."""
        stats = RollingStats.empty()

        assert stats.count == 0
        assert np.isnan(stats.mean)
        assert not stats.is_valid

    def test_valid_stats(self):
        """Valid stats should report is_valid=True."""
        stats = RollingStats(
            mean=10.0,
            std=2.0,
            min=5.0,
            max=15.0,
            median=10.0,
            mad=1.5,
            count=100,
        )

        assert stats.is_valid
