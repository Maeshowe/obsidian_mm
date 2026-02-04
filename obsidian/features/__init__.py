"""
Feature engineering module for OBSIDIAN MM.

Extracts diagnostic features from raw API data.
All features are source-data-first with minimal computation.
"""

from obsidian.features.darkpool import DarkPoolFeatures
from obsidian.features.greeks import GreeksFeatures
from obsidian.features.price_context import PriceContextFeatures
from obsidian.features.aggregator import FeatureAggregator

__all__ = [
    "DarkPoolFeatures",
    "GreeksFeatures",
    "PriceContextFeatures",
    "FeatureAggregator",
]
