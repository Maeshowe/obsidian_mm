"""
OBSIDIAN MM Sign Conventions.

CRITICAL: Greeks sign conventions must be locked and consistent.
A flipped sign silently inverts regime classification.

This file is the SINGLE SOURCE OF TRUTH for sign conventions.
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class GreeksSignConvention:
    """
    Centralized Greeks sign convention definition.

    GUARDRAIL: This definition must be enforced across all Greek inputs.
    Any inconsistency will silently invert regime classifications.

    CONVENTION (Dealer Perspective):
    - We measure from the DEALER's perspective (market makers)
    - Positive exposure = dealers are LONG that Greek
    - Negative exposure = dealers are SHORT that Greek
    """

    # Gamma Exposure (GEX)
    # Positive GEX = dealers long gamma = they SELL into rallies, BUY into dips
    # This STABILIZES price (vol suppression, pinning)
    gex_positive_meaning: str = "Dealers long gamma → volatility suppression → price pinning"
    gex_negative_meaning: str = "Dealers short gamma → volatility amplification → liquidity vacuum"

    # Delta Exposure (DEX)
    # Positive DEX = dealers long delta = directional exposure long
    # Negative DEX = dealers short delta = directional exposure short
    dex_positive_meaning: str = "Dealers long delta → net positive directional exposure"
    dex_negative_meaning: str = "Dealers short delta → net negative directional exposure"

    # Vanna (dDelta/dVol)
    # Positive vanna = delta increases as vol increases
    vanna_positive_meaning: str = "Delta increases with vol → amplifies moves during vol spikes"
    vanna_negative_meaning: str = "Delta decreases with vol → dampens moves during vol spikes"

    # Charm (dDelta/dTime)
    # Positive charm = delta increases as time passes
    charm_positive_meaning: str = "Delta increases with time decay"
    charm_negative_meaning: str = "Delta decreases with time decay"


# LOCKED CONVENTION - DO NOT MODIFY WITHOUT UPDATING ALL CONSUMERS
GREEKS_SIGN_CONVENTION = GreeksSignConvention()


class GreeksSource(str, Enum):
    """
    Source of Greeks data.

    Different sources may have different sign conventions.
    All must be normalized to OBSIDIAN convention before use.
    """

    UNUSUAL_WHALES = "unusual_whales"
    ORATS = "orats"
    CBOE = "cboe"
    MANUAL = "manual"


# Sign flip multipliers for different sources
# 1 = same convention, -1 = opposite convention
SIGN_CONVENTION_MULTIPLIERS = {
    GreeksSource.UNUSUAL_WHALES: {
        "gex": 1,   # UW uses dealer perspective (same as us)
        "dex": 1,
        "vanna": 1,
        "charm": 1,
    },
    GreeksSource.ORATS: {
        "gex": 1,   # ORATS uses dealer perspective
        "dex": 1,
        "vanna": 1,
        "charm": 1,
    },
    GreeksSource.CBOE: {
        "gex": 1,   # Verify with CBOE documentation
        "dex": 1,
        "vanna": 1,
        "charm": 1,
    },
    GreeksSource.MANUAL: {
        "gex": 1,
        "dex": 1,
        "vanna": 1,
        "charm": 1,
    },
}


def normalize_greek_sign(
    value: float,
    greek: str,
    source: GreeksSource,
) -> float:
    """
    Normalize Greek value to OBSIDIAN convention.

    Args:
        value: Raw Greek value from source
        greek: Greek name (gex, dex, vanna, charm)
        source: Data source

    Returns:
        Value in OBSIDIAN sign convention

    Raises:
        ValueError: If greek name unknown
    """
    if source not in SIGN_CONVENTION_MULTIPLIERS:
        raise ValueError(f"Unknown Greeks source: {source}")

    multipliers = SIGN_CONVENTION_MULTIPLIERS[source]

    if greek not in multipliers:
        raise ValueError(f"Unknown Greek: {greek}")

    return value * multipliers[greek]


def validate_greek_value(
    greek: str,
    value: float,
    regime_expectation: str,
) -> bool:
    """
    Validate that a Greek value matches regime expectation.

    Used to catch sign convention errors at runtime.

    Args:
        greek: Greek name
        value: Greek value
        regime_expectation: Expected regime ("stabilizing" or "destabilizing")

    Returns:
        True if value is consistent with expectation
    """
    if greek == "gex":
        if regime_expectation == "stabilizing":
            return value > 0  # Positive GEX = stabilizing
        elif regime_expectation == "destabilizing":
            return value < 0  # Negative GEX = destabilizing

    # Default: cannot validate
    return True
