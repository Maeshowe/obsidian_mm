"""
Constants for OBSIDIAN MM.

Central location for magic numbers, default values, and configuration constants.
These values are documented and intentionally chosen - not optimized.
"""

# ============================================================
# NORMALIZATION CONSTANTS
# ============================================================

# Default rolling window for normalization (trading days)
# 63 days ≈ 3 months, balances statistical stability with regime sensitivity
DEFAULT_ROLLING_WINDOW = 63

# Minimum observations required before normalization is valid
# 21 days ≈ 1 month, ensures statistical significance
MIN_OBSERVATIONS = 21

# Number of standard deviations for outlier clipping
OUTLIER_STD_THRESHOLD = 3.0

# ============================================================
# UNUSUALNESS SCORE WEIGHTS
# ============================================================
# These are DIAGNOSTIC weights based on market microstructure relevance.
# They are NOT optimized, NOT backtested. They reflect conceptual importance.

SCORE_WEIGHTS = {
    "dark_pool_activity": 0.25,   # Dark pool as % of total
    "gamma_exposure": 0.25,       # Net gamma of dealers
    "venue_shift": 0.20,          # Day-over-day venue mix change
    "block_activity": 0.15,       # Institutional block trades
    "iv_skew": 0.15,              # Put/call IV skew
}

# Verify weights sum to 1.0
assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 0.001, "Weights must sum to 1.0"

# ============================================================
# REGIME CLASSIFICATION THRESHOLDS
# ============================================================
# These define the boundaries for regime classification.
# Documented, deterministic, not ML-derived.

# Gamma exposure thresholds (z-score)
GEX_EXTREME_POSITIVE = 1.5   # Above this = dealers long gamma
GEX_EXTREME_NEGATIVE = -1.5  # Below this = dealers short gamma

# Delta exposure threshold (z-score)
DEX_ELEVATED = 1.0           # |z| above this = significant delta exposure

# Dark pool thresholds (percentage of total volume)
DARK_POOL_DOMINANT = 70      # Above this = dark-dominant
DARK_POOL_ELEVATED = 50      # Above this = elevated dark activity

# Block activity threshold (z-score)
BLOCK_ACTIVITY_ELEVATED = 1.0  # Above this = elevated block prints

# Price stability range (percentage)
PRICE_STABLE_LOW = -0.5      # Above this = not falling
PRICE_STABLE_HIGH = 0.5      # Below this = not rising

# Gamma context validation (percentile thresholds)
PRICE_EFFICIENCY_LOW = 50    # Below median = controlled
IMPACT_PER_VOL_HIGH = 50     # Above median = vacuum-like

# ============================================================
# SCORE LEVEL BOUNDARIES
# ============================================================

SCORE_LEVELS = {
    "very_normal": (0, 20),
    "normal": (20, 40),
    "slightly_unusual": (40, 60),
    "unusual": (60, 80),
    "highly_unusual": (80, 100),
}

# ============================================================
# BLOCK TRADE DEFINITIONS
# ============================================================

# Minimum shares for a trade to be considered a "block"
BLOCK_TRADE_MIN_SHARES = 10_000

# ============================================================
# API RATE LIMITS (requests per minute)
# ============================================================
# Conservative defaults - override in config for your plan tier

DEFAULT_RATE_LIMITS = {
    "unusual_whales": 60,
    "polygon": 5,       # Free tier
    "fmp": 300,
}

# ============================================================
# TIMEFRAMES
# ============================================================

# Trading days in various periods
TRADING_DAYS_PER_WEEK = 5
TRADING_DAYS_PER_MONTH = 21
TRADING_DAYS_PER_QUARTER = 63
TRADING_DAYS_PER_YEAR = 252

# ============================================================
# FEATURE NAMES
# ============================================================

# Features required for regime classification
REGIME_REQUIRED_FEATURES = [
    "gex_zscore",
    "dex_zscore",
    "dark_pool_ratio_pct",
    "block_trade_count_zscore",
    "price_change_pct",
    "price_efficiency_pct",
    "impact_per_vol_pct",
]

# Features used in unusualness score
SCORE_FEATURES = [
    "dark_pool_ratio_zscore",
    "gex_zscore",
    "venue_shift_zscore",
    "block_trade_count_zscore",
    "iv_skew_zscore",
]
