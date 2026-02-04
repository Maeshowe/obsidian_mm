"""
Price context feature extraction.

Extracts features from OHLCV data:
- Price change metrics
- Range metrics
- Volume metrics
- Gamma context features (price_efficiency, impact_per_vol)
"""

import logging
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class PriceMetrics:
    """Container for price-based metrics."""

    # Raw OHLCV
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int

    # Derived metrics
    price_change: float  # close - open
    price_change_pct: float  # percentage change
    daily_range: float  # high - low
    daily_range_pct: float  # range as % of open

    # Position metrics
    close_position: float  # where close is within range (0-1)

    # Gamma context metrics (for regime validation)
    price_efficiency: float | None = None  # range / volume (lower = controlled)
    impact_per_vol: float | None = None  # |change| / volume (higher = vacuum)

    # Volume context
    volume_vs_avg: float | None = None  # current / 20d average

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "price_change": self.price_change,
            "price_change_pct": self.price_change_pct,
            "daily_range": self.daily_range,
            "daily_range_pct": self.daily_range_pct,
            "close_position": self.close_position,
            "price_efficiency": self.price_efficiency,
            "impact_per_vol": self.impact_per_vol,
            "volume_vs_avg": self.volume_vs_avg,
        }


class PriceContextFeatures:
    """
    Extract features from OHLCV data.

    Source data: Polygon daily OHLCV
    Output: Price context metrics including gamma validation features
    """

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return default
        try:
            if isinstance(value, str):
                value = value.strip().strip("'\"")
            return float(value)
        except (ValueError, TypeError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        """Safely convert value to int."""
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return default
        try:
            if isinstance(value, str):
                value = value.strip().strip("'\"")
            return int(float(value))
        except (ValueError, TypeError):
            return default

    def extract(
        self,
        ohlcv: dict[str, Any],
        avg_volume: float | None = None,
    ) -> PriceMetrics:
        """
        Extract price context features.

        Args:
            ohlcv: Dictionary with OHLCV data
            avg_volume: Historical average volume (for volume_vs_avg)

        Returns:
            PriceMetrics with extracted features
        """
        # Extract raw values
        open_price = self._safe_float(ohlcv.get("open"))
        high_price = self._safe_float(ohlcv.get("high"))
        low_price = self._safe_float(ohlcv.get("low"))
        close_price = self._safe_float(ohlcv.get("close"))
        volume = self._safe_int(ohlcv.get("volume"))

        # Calculate derived metrics
        price_change = close_price - open_price
        price_change_pct = (price_change / open_price * 100) if open_price > 0 else 0.0
        daily_range = high_price - low_price
        daily_range_pct = (daily_range / open_price * 100) if open_price > 0 else 0.0

        # Close position within range (0 = at low, 1 = at high)
        close_position = 0.5
        if daily_range > 0:
            close_position = (close_price - low_price) / daily_range

        # Gamma context metrics
        # These are used to validate Gamma+ and Gamma- regimes
        price_efficiency = None
        impact_per_vol = None

        if volume > 0:
            # Price efficiency: lower = more controlled (Gamma+ validation)
            # Range relative to volume - low range with high volume = controlled
            price_efficiency = daily_range / (volume / 1_000_000)  # Normalize volume to millions

            # Impact per volume: higher = more vacuum-like (Gamma- validation)
            # Price move relative to volume - big move with low volume = vacuum
            impact_per_vol = abs(price_change) / (volume / 1_000_000)

        # Volume vs average
        volume_vs_avg = None
        if avg_volume and avg_volume > 0:
            volume_vs_avg = volume / avg_volume

        return PriceMetrics(
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
            price_change=price_change,
            price_change_pct=price_change_pct,
            daily_range=daily_range,
            daily_range_pct=daily_range_pct,
            close_position=close_position,
            price_efficiency=price_efficiency,
            impact_per_vol=impact_per_vol,
            volume_vs_avg=volume_vs_avg,
        )

    def calculate_average_volume(
        self,
        volume_history: list[int],
        window: int = 20,
    ) -> float:
        """
        Calculate average volume over a window.

        Args:
            volume_history: List of historical volumes
            window: Number of days for average

        Returns:
            Average volume
        """
        if not volume_history:
            return 0.0

        recent = volume_history[-window:] if len(volume_history) >= window else volume_history
        return sum(recent) / len(recent) if recent else 0.0

    def interpret_price_action(
        self,
        price_change_pct: float,
        daily_range_pct: float,
        close_position: float,
    ) -> str:
        """
        Generate interpretation of price action.

        Args:
            price_change_pct: Percentage price change
            daily_range_pct: Daily range as percentage
            close_position: Where close is within range

        Returns:
            Human-readable interpretation
        """
        # Determine direction
        if price_change_pct > 0.5:
            direction = "up"
        elif price_change_pct < -0.5:
            direction = "down"
        else:
            direction = "flat"

        # Determine conviction (close position)
        if close_position > 0.7:
            conviction = "strong buying conviction (closed near high)"
        elif close_position < 0.3:
            conviction = "strong selling conviction (closed near low)"
        else:
            conviction = "indecisive (closed mid-range)"

        # Determine volatility
        if daily_range_pct > 2.0:
            volatility = "high volatility"
        elif daily_range_pct < 0.5:
            volatility = "low volatility"
        else:
            volatility = "normal volatility"

        return f"Price {direction} {price_change_pct:+.2f}% with {volatility}. {conviction.capitalize()}."
