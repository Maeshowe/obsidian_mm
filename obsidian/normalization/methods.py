"""
Normalization methods.

Implements z-score, percentile, and min-max normalization.
"""

import numpy as np
from numpy.typing import NDArray


def zscore_normalize(
    value: float,
    mean: float,
    std: float,
    clip_std: float | None = 3.0,
) -> float:
    """
    Z-score normalization.

    Formula: (value - mean) / std

    Args:
        value: Value to normalize
        mean: Rolling mean
        std: Rolling standard deviation
        clip_std: Clip result to +/- this many std (default 3.0)

    Returns:
        Z-score normalized value
    """
    if std == 0 or np.isnan(std):
        return 0.0

    zscore = (value - mean) / std

    if clip_std is not None:
        zscore = np.clip(zscore, -clip_std, clip_std)

    return float(zscore)


def percentile_normalize(
    value: float,
    history: NDArray[np.float64],
) -> float:
    """
    Percentile normalization.

    Formula: (rank of value in history) / len(history) * 100

    Args:
        value: Value to normalize
        history: Historical values for ranking

    Returns:
        Percentile rank (0-100)
    """
    if len(history) == 0:
        return 50.0  # Default to median

    # Remove NaN values
    valid_history = history[~np.isnan(history)]
    if len(valid_history) == 0:
        return 50.0

    # Calculate percentile rank
    rank = np.sum(valid_history < value)
    percentile = (rank / len(valid_history)) * 100

    return float(percentile)


def minmax_normalize(
    value: float,
    min_val: float,
    max_val: float,
) -> float:
    """
    Min-max normalization.

    Formula: (value - min) / (max - min)

    Args:
        value: Value to normalize
        min_val: Rolling minimum
        max_val: Rolling maximum

    Returns:
        Normalized value (0-1)
    """
    range_val = max_val - min_val
    if range_val == 0 or np.isnan(range_val):
        return 0.5  # Default to middle

    normalized = (value - min_val) / range_val
    return float(np.clip(normalized, 0.0, 1.0))


def robust_zscore(
    value: float,
    median: float,
    mad: float,
    clip_std: float | None = 3.0,
) -> float:
    """
    Robust z-score using median and MAD.

    More resistant to outliers than standard z-score.
    MAD = Median Absolute Deviation

    Formula: (value - median) / (1.4826 * MAD)

    Args:
        value: Value to normalize
        median: Rolling median
        mad: Median Absolute Deviation
        clip_std: Clip result to +/- this many std (default 3.0)

    Returns:
        Robust z-score
    """
    # 1.4826 is the scale factor to make MAD comparable to std for normal distribution
    scaled_mad = 1.4826 * mad

    if scaled_mad == 0 or np.isnan(scaled_mad):
        return 0.0

    zscore = (value - median) / scaled_mad

    if clip_std is not None:
        zscore = np.clip(zscore, -clip_std, clip_std)

    return float(zscore)


def log_transform(value: float, offset: float = 1.0) -> float:
    """
    Log transformation for skewed distributions.

    Args:
        value: Value to transform
        offset: Offset to add before log (for handling zeros)

    Returns:
        Log-transformed value
    """
    if value + offset <= 0:
        return 0.0
    return float(np.log(value + offset))
