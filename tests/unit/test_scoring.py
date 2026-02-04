"""
Tests for unusualness scoring.
"""

import pytest
import pandas as pd

from obsidian.core.types import UnusualnessLevel
from obsidian.scoring.unusualness import UnusualnessEngine


@pytest.fixture
def engine():
    """Create unusualness engine."""
    return UnusualnessEngine()


@pytest.fixture
def engine_with_history():
    """Create engine with some history."""
    # Generate some historical scores
    history = [0.5, 0.8, 1.0, 1.2, 0.9, 0.7, 1.1, 1.3, 0.6, 1.0]
    return UnusualnessEngine(score_history=history)


class TestScoreCalculation:
    """Tests for score calculation."""

    def test_calculates_score_from_features(
        self,
        engine: UnusualnessEngine,
        sample_features: pd.Series,
    ):
        """Should calculate valid score from features."""
        result = engine.calculate(sample_features)

        assert 0 <= result.score <= 100
        assert result.raw_score > 0
        assert result.level is not None

    def test_higher_zscores_give_higher_raw_score(
        self,
        engine: UnusualnessEngine,
    ):
        """Features with higher z-scores should produce higher raw scores."""
        low_features = pd.Series({
            "dark_pool_ratio_zscore": 0.5,
            "gex_zscore": 0.5,
            "venue_shift_zscore": 0.5,
            "block_trade_count_zscore": 0.5,
            "iv_skew_zscore": 0.5,
        })

        high_features = pd.Series({
            "dark_pool_ratio_zscore": 2.0,
            "gex_zscore": 2.0,
            "venue_shift_zscore": 2.0,
            "block_trade_count_zscore": 2.0,
            "iv_skew_zscore": 2.0,
        })

        low_result = engine.calculate(low_features)
        high_result = engine.calculate(high_features)

        assert high_result.raw_score > low_result.raw_score

    def test_negative_zscores_contribute_magnitude(
        self,
        engine: UnusualnessEngine,
    ):
        """Negative z-scores should contribute by absolute value."""
        features = pd.Series({
            "dark_pool_ratio_zscore": -2.0,
            "gex_zscore": -2.0,
            "venue_shift_zscore": -2.0,
            "block_trade_count_zscore": -2.0,
            "iv_skew_zscore": -2.0,
        })

        result = engine.calculate(features)

        # Should have significant raw score despite negative z-scores
        assert result.raw_score > 1.5


class TestScoreLevels:
    """Tests for score level classification."""

    def test_very_normal_level(self, engine: UnusualnessEngine):
        """Low scores should be 'Very Normal'."""
        assert UnusualnessLevel.from_score(10) == UnusualnessLevel.VERY_NORMAL

    def test_normal_level(self, engine: UnusualnessEngine):
        """Moderate low scores should be 'Normal'."""
        assert UnusualnessLevel.from_score(30) == UnusualnessLevel.NORMAL

    def test_slightly_unusual_level(self, engine: UnusualnessEngine):
        """Mid scores should be 'Slightly Unusual'."""
        assert UnusualnessLevel.from_score(50) == UnusualnessLevel.SLIGHTLY_UNUSUAL

    def test_unusual_level(self, engine: UnusualnessEngine):
        """High scores should be 'Unusual'."""
        assert UnusualnessLevel.from_score(70) == UnusualnessLevel.UNUSUAL

    def test_highly_unusual_level(self, engine: UnusualnessEngine):
        """Very high scores should be 'Highly Unusual'."""
        assert UnusualnessLevel.from_score(90) == UnusualnessLevel.HIGHLY_UNUSUAL


class TestPercentileRanking:
    """Tests for percentile-based scoring with history."""

    def test_uses_history_for_percentile(
        self,
        engine_with_history: UnusualnessEngine,
    ):
        """Should use historical scores for percentile calculation."""
        features = pd.Series({
            "dark_pool_ratio_zscore": 1.5,
            "gex_zscore": 1.5,
            "venue_shift_zscore": 1.5,
            "block_trade_count_zscore": 1.5,
            "iv_skew_zscore": 1.5,
        })

        result = engine_with_history.calculate(features)

        # With history, score should be based on percentile
        assert 0 <= result.score <= 100

    def test_adds_to_history(self, engine: UnusualnessEngine):
        """Should add each calculation to history."""
        features = pd.Series({
            "dark_pool_ratio_zscore": 1.0,
            "gex_zscore": 1.0,
            "venue_shift_zscore": 1.0,
            "block_trade_count_zscore": 1.0,
            "iv_skew_zscore": 1.0,
        })

        engine.calculate(features)
        engine.calculate(features)
        engine.calculate(features)

        summary = engine.get_score_summary()
        assert summary["history_count"] == 3


class TestTopDrivers:
    """Tests for top driver extraction."""

    def test_extracts_top_drivers(
        self,
        engine: UnusualnessEngine,
        sample_features: pd.Series,
    ):
        """Should extract top contributing drivers."""
        result = engine.calculate(sample_features)

        assert len(result.top_drivers) > 0
        assert len(result.top_drivers) <= 3  # Default is top 3

    def test_drivers_sorted_by_magnitude(
        self,
        engine: UnusualnessEngine,
    ):
        """Top drivers should be sorted by absolute z-score."""
        features = pd.Series({
            "dark_pool_ratio_zscore": 0.5,
            "gex_zscore": 2.5,  # Highest
            "venue_shift_zscore": 1.0,
            "block_trade_count_zscore": 0.3,
            "iv_skew_zscore": 1.8,  # Second highest
        })

        result = engine.calculate(features)

        # First driver should be gex (highest magnitude)
        assert result.top_drivers[0].feature == "gamma_exposure"


class TestExplanation:
    """Tests for explanation generation."""

    def test_generates_explanation(
        self,
        engine: UnusualnessEngine,
        sample_features: pd.Series,
    ):
        """Should generate human-readable explanation."""
        result = engine.calculate(sample_features)

        assert result.explanation
        assert "score" in result.explanation.lower()
        assert "driver" in result.explanation.lower()
