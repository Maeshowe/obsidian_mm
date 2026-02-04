"""
Greek exposure feature extraction.

Extracts dealer positioning from options Greeks:
- GEX (Gamma Exposure)
- DEX (Delta Exposure)
- Vanna, Charm
- IV metrics
"""

import logging
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class GreeksMetrics:
    """Container for Greek exposure metrics."""

    # Core Greeks
    gex: float  # Gamma exposure
    dex: float  # Delta exposure
    vanna: float | None = None
    charm: float | None = None

    # IV metrics
    iv_atm: float | None = None  # At-the-money IV
    iv_rank: float | None = None  # IV rank (0-100)
    iv_skew: float | None = None  # Put-call skew
    iv_term_slope: float | None = None  # Term structure slope

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gex": self.gex,
            "dex": self.dex,
            "vanna": self.vanna,
            "charm": self.charm,
            "iv_atm": self.iv_atm,
            "iv_rank": self.iv_rank,
            "iv_skew": self.iv_skew,
            "iv_term_slope": self.iv_term_slope,
        }


class GreeksFeatures:
    """
    Extract features from Greek exposure data.

    Source data: Unusual Whales Greek exposure API
    Output: Daily Greek exposure metrics
    """

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float, handling strings, None, and invalid types."""
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

    def _safe_float_optional(self, value: Any) -> float | None:
        """Safely convert to float or return None."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return None
        try:
            if isinstance(value, str):
                value = value.strip().strip("'\"")
            return float(value)
        except (ValueError, TypeError):
            return None

    def extract(
        self,
        greek_data: dict[str, Any],
        iv_data: dict[str, Any] | None = None,
    ) -> GreeksMetrics:
        """
        Extract Greek exposure features.

        Args:
            greek_data: Dictionary with GEX, DEX, vanna, charm
            iv_data: Optional IV term structure data

        Returns:
            GreeksMetrics with extracted features
        """
        # Core Greeks - direct from API
        gex = self._safe_float(greek_data.get("gex"))
        dex = self._safe_float(greek_data.get("dex"))
        vanna = self._safe_float_optional(greek_data.get("vanna"))
        charm = self._safe_float_optional(greek_data.get("charm"))

        # IV metrics from term structure
        iv_atm = None
        iv_rank = None
        iv_skew = None
        iv_term_slope = None

        if iv_data:
            iv_atm = self._safe_float_optional(iv_data.get("iv_atm"))
            iv_rank = self._safe_float_optional(iv_data.get("iv_rank"))
            iv_skew = self._calculate_skew(iv_data)
            iv_term_slope = self._calculate_term_slope(iv_data)

        return GreeksMetrics(
            gex=gex,
            dex=dex,
            vanna=vanna,
            charm=charm,
            iv_atm=iv_atm,
            iv_rank=iv_rank,
            iv_skew=iv_skew,
            iv_term_slope=iv_term_slope,
        )

    def _calculate_skew(self, iv_data: dict[str, Any]) -> float | None:
        """
        Calculate put-call IV skew.

        Skew = 25-delta put IV - 25-delta call IV
        Positive skew = puts more expensive (fear)
        """
        put_iv = self._safe_float_optional(iv_data.get("iv_25d_put"))
        call_iv = self._safe_float_optional(iv_data.get("iv_25d_call"))

        if put_iv is not None and call_iv is not None:
            return put_iv - call_iv

        # Try alternate field names
        put_iv = self._safe_float_optional(iv_data.get("put_iv_25d"))
        call_iv = self._safe_float_optional(iv_data.get("call_iv_25d"))

        if put_iv is not None and call_iv is not None:
            return put_iv - call_iv

        return None

    def _calculate_term_slope(self, iv_data: dict[str, Any]) -> float | None:
        """
        Calculate IV term structure slope.

        Slope = 30-day IV - 7-day IV
        Positive slope = contango (normal)
        Negative slope = backwardation (near-term fear)
        """
        iv_30d = self._safe_float_optional(iv_data.get("iv_30d") or iv_data.get("iv_1m"))
        iv_7d = self._safe_float_optional(iv_data.get("iv_7d") or iv_data.get("iv_1w"))

        if iv_30d is not None and iv_7d is not None:
            return iv_30d - iv_7d

        return None

    def interpret_gex(self, gex: float, gex_zscore: float) -> str:
        """
        Generate interpretation of GEX level.

        Args:
            gex: Raw GEX value
            gex_zscore: Normalized GEX z-score

        Returns:
            Human-readable interpretation
        """
        if gex_zscore > 1.5:
            return (
                f"Dealers are significantly LONG gamma (z={gex_zscore:.1f}). "
                "Expect volatility suppression and potential price pinning."
            )
        elif gex_zscore < -1.5:
            return (
                f"Dealers are significantly SHORT gamma (z={gex_zscore:.1f}). "
                "This creates a liquidity vacuum - price moves may be amplified."
            )
        elif gex_zscore > 0.5:
            return (
                f"Dealers are moderately long gamma (z={gex_zscore:.1f}). "
                "Some volatility dampening expected."
            )
        elif gex_zscore < -0.5:
            return (
                f"Dealers are moderately short gamma (z={gex_zscore:.1f}). "
                "Slightly elevated volatility potential."
            )
        else:
            return (
                f"Dealer gamma positioning is neutral (z={gex_zscore:.1f}). "
                "No strong directional bias from options positioning."
            )

    def interpret_dex(self, dex: float, dex_zscore: float) -> str:
        """
        Generate interpretation of DEX level.

        Args:
            dex: Raw DEX value
            dex_zscore: Normalized DEX z-score

        Returns:
            Human-readable interpretation
        """
        if dex_zscore > 1.0:
            return (
                f"Elevated positive delta exposure (z={dex_zscore:.1f}). "
                "Dealers may need to sell to hedge."
            )
        elif dex_zscore < -1.0:
            return (
                f"Elevated negative delta exposure (z={dex_zscore:.1f}). "
                "Dealers may need to buy to hedge."
            )
        else:
            return (
                f"Delta exposure is within normal range (z={dex_zscore:.1f}). "
                "No significant hedging pressure indicated."
            )
