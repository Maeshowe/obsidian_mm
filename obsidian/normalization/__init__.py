"""
Normalization module for OBSIDIAN MM.

Provides rolling window normalization of features.
All features must be normalized - absolute values are meaningless without context.
"""

from obsidian.normalization.methods import (
    zscore_normalize,
    percentile_normalize,
    minmax_normalize,
)
from obsidian.normalization.rolling import RollingWindowCalculator
from obsidian.normalization.pipeline import NormalizationPipeline

__all__ = [
    "zscore_normalize",
    "percentile_normalize",
    "minmax_normalize",
    "RollingWindowCalculator",
    "NormalizationPipeline",
]
