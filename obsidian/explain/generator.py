"""
Explanation generator.

Produces human-readable explanations for diagnostic results.
"""

from typing import Any

from obsidian.core.types import RegimeLabel, RegimeResult, TopDriver, UnusualnessResult


class ExplanationGenerator:
    """
    Generates detailed explanations for diagnostic results.

    Combines regime classification and unusualness score into
    a comprehensive, human-readable summary.
    """

    def generate_full_explanation(
        self,
        regime_result: RegimeResult,
        unusualness_result: UnusualnessResult,
    ) -> str:
        """
        Generate comprehensive explanation combining regime and score.

        Args:
            regime_result: Regime classification result
            unusualness_result: Unusualness score result

        Returns:
            Full human-readable explanation
        """
        lines = []

        # Header
        lines.append(f"=== {regime_result.ticker} - {regime_result.trade_date} ===")
        lines.append("")

        # Unusualness summary
        lines.append(f"UNUSUALNESS: {unusualness_result.score}/100 ({unusualness_result.level.value})")
        lines.append(unusualness_result.explanation)
        lines.append("")

        # Regime summary
        lines.append(f"REGIME: {regime_result.label.value}")
        lines.append(f"Confidence: {regime_result.confidence:.0%}")
        lines.append(regime_result.explanation)
        lines.append("")

        # Top drivers
        lines.append("TOP DRIVERS:")
        for driver in regime_result.top_drivers[:3]:
            direction = "↑" if driver.direction == "elevated" else "↓"
            lines.append(
                f"  {direction} {driver.feature}: {driver.zscore:+.2f}σ "
                f"({driver.contribution_pct:.0f}% contribution)"
            )

        return "\n".join(lines)

    def generate_short_summary(
        self,
        regime_result: RegimeResult,
        unusualness_result: UnusualnessResult,
    ) -> str:
        """
        Generate one-line summary.

        Args:
            regime_result: Regime classification result
            unusualness_result: Unusualness score result

        Returns:
            Short summary string
        """
        top_driver = regime_result.top_drivers[0] if regime_result.top_drivers else None
        driver_text = f", top: {top_driver.feature} {top_driver.zscore:+.1f}σ" if top_driver else ""

        return (
            f"{regime_result.ticker}: {regime_result.label.value} "
            f"(score={unusualness_result.score}{driver_text})"
        )

    def generate_regime_detail(self, regime_result: RegimeResult) -> dict[str, Any]:
        """
        Generate detailed regime breakdown.

        Args:
            regime_result: Regime classification result

        Returns:
            Dictionary with detailed regime information
        """
        return {
            "regime": regime_result.label.value,
            "confidence": f"{regime_result.confidence:.0%}",
            "explanation": regime_result.explanation,
            "interpretation": self._get_regime_interpretation(regime_result.label),
            "implications": self._get_regime_implications(regime_result.label),
            "drivers": [
                {
                    "feature": d.feature,
                    "zscore": f"{d.zscore:+.2f}σ",
                    "direction": d.direction,
                    "contribution": f"{d.contribution_pct:.0f}%",
                }
                for d in regime_result.top_drivers
            ],
        }

    def _get_regime_interpretation(self, label: RegimeLabel) -> str:
        """Get interpretation text for a regime."""
        interpretations = {
            RegimeLabel.GAMMA_POSITIVE_CONTROL: (
                "Dealers are net long gamma from options positioning. "
                "They profit from mean reversion and will sell rallies / buy dips, "
                "creating a stabilizing effect on price."
            ),
            RegimeLabel.GAMMA_NEGATIVE_VACUUM: (
                "Dealers are net short gamma from options positioning. "
                "They must chase price moves (buy highs / sell lows) to hedge, "
                "which can amplify volatility and cause rapid directional moves."
            ),
            RegimeLabel.DARK_DOMINANT_ACCUMULATION: (
                "Majority of volume is executing through dark pools with elevated "
                "block activity. This often indicates institutional positioning "
                "occurring away from lit exchanges."
            ),
            RegimeLabel.ABSORPTION_LIKE: (
                "Despite negative delta exposure indicating selling pressure, "
                "price remains stable. This suggests passive buyers are absorbing "
                "the sell flow without moving price."
            ),
            RegimeLabel.DISTRIBUTION_LIKE: (
                "Positive delta exposure indicates buying activity, yet price "
                "is not appreciating. This suggests distribution - selling "
                "into the bid support."
            ),
            RegimeLabel.NEUTRAL: (
                "No dominant market microstructure pattern detected. "
                "Metrics are within normal historical ranges."
            ),
        }
        return interpretations.get(label, "No interpretation available.")

    def _get_regime_implications(self, label: RegimeLabel) -> list[str]:
        """Get behavioral implications for a regime."""
        implications = {
            RegimeLabel.GAMMA_POSITIVE_CONTROL: [
                "Expect dampened intraday volatility",
                "Price may pin near high-gamma strikes at expiration",
                "Mean reversion strategies historically favored",
            ],
            RegimeLabel.GAMMA_NEGATIVE_VACUUM: [
                "Elevated risk of rapid directional moves",
                "Stop-loss cascades more likely",
                "Volatility expansion possible",
            ],
            RegimeLabel.DARK_DOMINANT_ACCUMULATION: [
                "Institutional activity likely occurring",
                "True positioning may not be reflected in lit market",
                "Watch for eventual reversion to normal venue mix",
            ],
            RegimeLabel.ABSORPTION_LIKE: [
                "Hidden support may be present",
                "Accumulation phase possible",
                "Monitor for exhaustion of buyers",
            ],
            RegimeLabel.DISTRIBUTION_LIKE: [
                "Hidden selling pressure present",
                "Distribution phase possible",
                "Monitor for exhaustion of sellers",
            ],
            RegimeLabel.NEUTRAL: [
                "No strong directional microstructure bias",
                "Market operating in typical conditions",
                "Other factors may dominate price action",
            ],
        }
        return implications.get(label, ["No implications available."])
