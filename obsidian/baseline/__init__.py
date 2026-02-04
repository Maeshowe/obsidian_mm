"""
OBSIDIAN MM Baseline System.

Establishes what "normal" looks like for each instrument.
All normalization and deviation detection references these baselines.

CORE PRINCIPLE:
    You cannot call something "unusual" without knowing what "normal" is.
    Every metric must be compared against a stored, instrument-specific baseline.

COMPONENTS:
    - TickerBaseline: Complete baseline profile for a ticker
    - BaselineCalculator: Computes baselines from historical data
    - BaselineStorage: Persists baselines to disk

USAGE:
    from obsidian.baseline import BaselineCalculator, BaselineStorage

    # Compute baseline for new ticker
    calculator = BaselineCalculator(lookback_days=63)
    baseline = calculator.compute_baseline("SPY", historical_df)

    # Store baseline
    storage = BaselineStorage()
    storage.save(baseline)

    # Load baseline for daily processing
    baseline = storage.load("SPY")
    if baseline is None:
        raise ValueError("Cannot process SPY without baseline!")
"""

from obsidian.baseline.types import (
    BaselineUpdatePolicy,
    DarkPoolBaseline,
    DistributionStats,
    DynamicState,
    GreeksBaseline,
    PriceEfficiencyBaseline,
    TickerBaseline,
)
from obsidian.baseline.calculator import BaselineCalculator, compute_distribution_stats
from obsidian.baseline.storage import BaselineStorage, format_baseline_report
from obsidian.baseline.history import FeatureHistoryStorage


__all__ = [
    # Types
    "BaselineUpdatePolicy",
    "DistributionStats",
    "DarkPoolBaseline",
    "GreeksBaseline",
    "PriceEfficiencyBaseline",
    "TickerBaseline",
    "DynamicState",
    # Calculator
    "BaselineCalculator",
    "compute_distribution_stats",
    # Storage
    "BaselineStorage",
    "format_baseline_report",
    # History
    "FeatureHistoryStorage",
]
