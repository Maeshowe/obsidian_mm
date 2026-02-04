"""
Tests for regime classification.
"""

import pytest
import pandas as pd

from obsidian.core.types import RegimeLabel
from obsidian.regimes.classifier import RegimeClassifier


@pytest.fixture
def classifier():
    """Create regime classifier."""
    return RegimeClassifier()


class TestGammaPositiveControl:
    """Tests for Gamma+ Control regime detection."""

    def test_detects_gamma_positive_when_conditions_met(
        self,
        classifier: RegimeClassifier,
        gamma_positive_features: pd.Series,
    ):
        """Should classify as Gamma+ when GEX > 1.5 and price efficiency low."""
        result = classifier.classify(gamma_positive_features)

        assert result.label == RegimeLabel.GAMMA_POSITIVE_CONTROL
        assert result.confidence > 0.5
        assert "long gamma" in result.explanation.lower()

    def test_not_gamma_positive_when_gex_low(
        self,
        classifier: RegimeClassifier,
        gamma_positive_features: pd.Series,
    ):
        """Should NOT classify as Gamma+ when GEX below threshold."""
        features = gamma_positive_features.copy()
        features["gex_zscore"] = 1.0  # Below threshold

        result = classifier.classify(features)

        assert result.label != RegimeLabel.GAMMA_POSITIVE_CONTROL

    def test_not_gamma_positive_when_dark_pool_high(
        self,
        classifier: RegimeClassifier,
        gamma_positive_features: pd.Series,
    ):
        """Should NOT classify as Gamma+ when dark pool > 60%."""
        features = gamma_positive_features.copy()
        features["dark_pool_ratio_pct"] = 65.0  # Above threshold

        result = classifier.classify(features)

        # Should fall through to another regime or neutral
        assert result.label != RegimeLabel.GAMMA_POSITIVE_CONTROL


class TestGammaNegativeVacuum:
    """Tests for Gamma- Liquidity Vacuum regime."""

    def test_detects_gamma_negative_when_conditions_met(
        self,
        classifier: RegimeClassifier,
        gamma_negative_features: pd.Series,
    ):
        """Should classify as Gamma- when GEX < -1.5 and impact high."""
        result = classifier.classify(gamma_negative_features)

        assert result.label == RegimeLabel.GAMMA_NEGATIVE_VACUUM
        assert "short gamma" in result.explanation.lower()

    def test_not_gamma_negative_when_gex_not_extreme(
        self,
        classifier: RegimeClassifier,
        gamma_negative_features: pd.Series,
    ):
        """Should NOT classify as Gamma- when GEX not extreme."""
        features = gamma_negative_features.copy()
        features["gex_zscore"] = -1.0  # Not extreme enough

        result = classifier.classify(features)

        assert result.label != RegimeLabel.GAMMA_NEGATIVE_VACUUM


class TestDarkDominantAccumulation:
    """Tests for Dark-Dominant Accumulation regime."""

    def test_detects_dark_dominant_when_conditions_met(
        self,
        classifier: RegimeClassifier,
        dark_dominant_features: pd.Series,
    ):
        """Should classify as Dark-Dominant when dark pool > 70% and blocks elevated."""
        result = classifier.classify(dark_dominant_features)

        assert result.label == RegimeLabel.DARK_DOMINANT_ACCUMULATION
        assert "dark pool" in result.explanation.lower()

    def test_not_dark_dominant_when_dark_pool_low(
        self,
        classifier: RegimeClassifier,
        dark_dominant_features: pd.Series,
    ):
        """Should NOT classify as Dark-Dominant when dark pool < 70%."""
        features = dark_dominant_features.copy()
        features["dark_pool_ratio_pct"] = 60.0

        result = classifier.classify(features)

        assert result.label != RegimeLabel.DARK_DOMINANT_ACCUMULATION


class TestNeutralFallback:
    """Tests for Neutral fallback regime."""

    def test_neutral_when_no_conditions_met(
        self,
        classifier: RegimeClassifier,
        neutral_features: pd.Series,
    ):
        """Should classify as Neutral when no strong signals."""
        result = classifier.classify(neutral_features)

        assert result.label == RegimeLabel.NEUTRAL
        assert "normal" in result.explanation.lower()


class TestRegimePriority:
    """Tests for correct regime priority ordering."""

    def test_gamma_takes_priority_over_dark_pool(
        self,
        classifier: RegimeClassifier,
    ):
        """Gamma extremes should win over dark pool signals."""
        features = pd.Series({
            "gex_zscore": -2.5,  # Extreme negative
            "dex_zscore": 0.0,
            "dark_pool_ratio_pct": 80.0,  # Also high
            "block_trade_count_zscore": 2.0,  # Also high
            "price_change_pct": 0.0,
            "price_efficiency_pct": 50.0,
            "impact_per_vol_pct": 70.0,  # High impact
        })

        result = classifier.classify(features)

        # Gamma- should win due to priority
        assert result.label == RegimeLabel.GAMMA_NEGATIVE_VACUUM


class TestTopDrivers:
    """Tests for top driver extraction."""

    def test_top_drivers_extracted(
        self,
        classifier: RegimeClassifier,
        sample_features: pd.Series,
    ):
        """Should extract top drivers sorted by magnitude."""
        result = classifier.classify(sample_features)

        assert len(result.top_drivers) > 0
        # First driver should have highest magnitude
        magnitudes = [abs(d.zscore) for d in result.top_drivers]
        assert magnitudes == sorted(magnitudes, reverse=True)
