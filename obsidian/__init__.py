"""
OBSIDIAN MM - Market-Maker Diagnostic Platform

Observational Behavioral System for Institutional & Dealer-Informed Anomaly Networks

This package provides daily market microstructure diagnostics including:
- MM Unusualness Score: Normalized measure of microstructure deviation
- MM Regime Classification: Deterministic regime labels with explanations

NOT a trading system. NOT a signal generator. Diagnostic only.
"""

__version__ = "0.1.0"
__author__ = "OBSIDIAN MM Team"

from obsidian.core.types import RegimeLabel, RegimeResult, UnusualnessResult

__all__ = [
    "RegimeLabel",
    "RegimeResult",
    "UnusualnessResult",
]
