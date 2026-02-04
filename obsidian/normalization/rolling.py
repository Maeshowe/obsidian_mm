"""
Rolling window calculations for normalization.

Maintains historical data and computes rolling statistics.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np
from numpy.typing import NDArray


logger = logging.getLogger(__name__)


@dataclass
class RollingStats:
    """Container for rolling window statistics."""

    mean: float
    std: float
    min: float
    max: float
    median: float
    mad: float  # Median Absolute Deviation
    count: int

    @classmethod
    def empty(cls) -> "RollingStats":
        """Create empty stats object."""
        return cls(
            mean=np.nan,
            std=np.nan,
            min=np.nan,
            max=np.nan,
            median=np.nan,
            mad=np.nan,
            count=0,
        )

    @property
    def is_valid(self) -> bool:
        """Check if stats are valid (have enough data)."""
        return self.count > 0 and not np.isnan(self.mean)


class RollingWindowCalculator:
    """
    Calculates rolling window statistics for normalization.

    Maintains a sliding window of historical values and computes
    statistics efficiently.
    """

    def __init__(
        self,
        window: int = 63,
        min_observations: int = 21,
    ) -> None:
        """
        Initialize rolling window calculator.

        Args:
            window: Size of rolling window (trading days)
            min_observations: Minimum observations before stats are valid
        """
        self.window = window
        self.min_observations = min_observations
        self._values: Deque[float] = deque(maxlen=window)

    def add(self, value: float) -> None:
        """
        Add a value to the rolling window.

        Args:
            value: Value to add (NaN values are skipped)
        """
        if not np.isnan(value):
            self._values.append(value)

    def add_batch(self, values: list[float]) -> None:
        """
        Add multiple values to the rolling window.

        Args:
            values: List of values to add
        """
        for v in values:
            self.add(v)

    @property
    def values(self) -> NDArray[np.float64]:
        """Get current window values as numpy array."""
        return np.array(self._values, dtype=np.float64)

    @property
    def count(self) -> int:
        """Number of values in window."""
        return len(self._values)

    @property
    def is_ready(self) -> bool:
        """Check if window has minimum required observations."""
        return self.count >= self.min_observations

    def compute_stats(self) -> RollingStats:
        """
        Compute rolling statistics from current window.

        Returns:
            RollingStats with computed statistics
        """
        if self.count == 0:
            return RollingStats.empty()

        arr = self.values

        # Basic stats
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if self.count > 1 else 0.0
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        median = float(np.median(arr))

        # MAD (Median Absolute Deviation)
        mad = float(np.median(np.abs(arr - median)))

        return RollingStats(
            mean=mean,
            std=std,
            min=min_val,
            max=max_val,
            median=median,
            mad=mad,
            count=self.count,
        )

    def clear(self) -> None:
        """Clear all values from window."""
        self._values.clear()


class MultiFeatureRollingCalculator:
    """
    Manages rolling windows for multiple features.

    Each feature has its own window with potentially different sizes.
    """

    def __init__(
        self,
        feature_configs: dict[str, dict],
        default_window: int = 63,
        min_observations: int = 21,
    ) -> None:
        """
        Initialize multi-feature calculator.

        Args:
            feature_configs: Dictionary mapping feature names to configs
            default_window: Default window size
            min_observations: Default minimum observations
        """
        self.default_window = default_window
        self.min_observations = min_observations
        self._calculators: dict[str, RollingWindowCalculator] = {}

        # Initialize calculators for each feature
        for feature, config in feature_configs.items():
            window = config.get("window", default_window)
            self._calculators[feature] = RollingWindowCalculator(
                window=window,
                min_observations=min_observations,
            )

    def add(self, feature: str, value: float) -> None:
        """
        Add value for a specific feature.

        Args:
            feature: Feature name
            value: Value to add
        """
        if feature not in self._calculators:
            # Create calculator with default settings
            self._calculators[feature] = RollingWindowCalculator(
                window=self.default_window,
                min_observations=self.min_observations,
            )
        self._calculators[feature].add(value)

    def add_all(self, feature_values: dict[str, float]) -> None:
        """
        Add values for multiple features.

        Args:
            feature_values: Dictionary mapping feature names to values
        """
        for feature, value in feature_values.items():
            if value is not None:
                self.add(feature, value)

    def get_stats(self, feature: str) -> RollingStats:
        """
        Get rolling stats for a feature.

        Args:
            feature: Feature name

        Returns:
            RollingStats for the feature
        """
        if feature not in self._calculators:
            return RollingStats.empty()
        return self._calculators[feature].compute_stats()

    def get_values(self, feature: str) -> NDArray[np.float64]:
        """
        Get historical values for a feature.

        Args:
            feature: Feature name

        Returns:
            Array of historical values
        """
        if feature not in self._calculators:
            return np.array([], dtype=np.float64)
        return self._calculators[feature].values

    def is_ready(self, feature: str) -> bool:
        """
        Check if feature has enough observations.

        Args:
            feature: Feature name

        Returns:
            True if minimum observations met
        """
        if feature not in self._calculators:
            return False
        return self._calculators[feature].is_ready

    def get_ready_features(self) -> list[str]:
        """Get list of features with enough observations."""
        return [f for f in self._calculators if self.is_ready(f)]
