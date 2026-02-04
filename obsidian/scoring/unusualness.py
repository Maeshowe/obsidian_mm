"""
MM Unusualness Score Engine.

Computes a normalized score (0-100) indicating how unusual the current
market microstructure state is compared to historical norms.

The score is diagnostic, not predictive.
"""

import logging
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from obsidian.core.constants import SCORE_WEIGHTS
from obsidian.core.types import (
    ScoreComponent,
    TopDriver,
    UnusualnessLevel,
    UnusualnessResult,
)


logger = logging.getLogger(__name__)


# Score component definitions
# These map features to their weights in the final score
# zscore_col is preferred, but pct_col is used as fallback (converted to pseudo z-score)
SCORE_COMPONENTS = [
    {
        "name": "dark_pool_activity",
        "weight": SCORE_WEIGHTS["dark_pool_activity"],
        "zscore_col": "dark_pool_ratio_zscore",
        "pct_col": "dark_pool_ratio_pct",  # fallback: percentile
        "description": "Dark pool volume as % of total",
    },
    {
        "name": "gamma_exposure",
        "weight": SCORE_WEIGHTS["gamma_exposure"],
        "zscore_col": "gex_zscore",
        "pct_col": None,
        "description": "Net gamma exposure of market makers",
    },
    {
        "name": "venue_shift",
        "weight": SCORE_WEIGHTS["venue_shift"],
        "zscore_col": "venue_shift_zscore",
        "pct_col": None,
        "description": "Day-over-day change in lit/dark ratio",
    },
    {
        "name": "block_activity",
        "weight": SCORE_WEIGHTS["block_activity"],
        "zscore_col": "block_trade_count_zscore",
        "pct_col": "block_trade_count_pct",  # fallback: percentile
        "description": "Institutional block trade frequency",
    },
    {
        "name": "iv_skew",
        "weight": SCORE_WEIGHTS["iv_skew"],
        "zscore_col": "iv_skew_zscore",
        "pct_col": None,
        "description": "Put-call IV skew (fear indicator)",
    },
]


def _percentile_to_zscore(pct: float) -> float:
    """Convert percentile (0-100) to pseudo z-score."""
    # 50th percentile = 0, 2.5th = -2, 97.5th = +2
    return (pct - 50) / 25


class UnusualnessEngine:
    """
    MM Unusualness Score Engine.

    Computes a 0-100 score indicating how unusual market microstructure
    is compared to historical norms.

    Formula:
        raw_score = Σ(weight_i * |zscore_i|)
        final_score = percentile_rank(raw_score) over 63-day window

    Higher score = more unusual = further from historical norms.

    IMPORTANT: Weights are diagnostic, not optimized.
    They reflect conceptual importance of each component to market-maker
    microstructure, NOT predictive power or backtest results.
    """

    def __init__(
        self,
        history_window: int = 63,
        score_history: list[float] | None = None,
    ) -> None:
        """
        Initialize unusualness engine.

        Args:
            history_window: Rolling window for percentile ranking
            score_history: Previous raw scores for percentile calculation
        """
        self.history_window = history_window
        self._score_history: list[float] = score_history or []

        # Verify weights sum to 1.0
        total_weight = sum(c["weight"] for c in SCORE_COMPONENTS)
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Score weights must sum to 1.0, got {total_weight}")

    def calculate(
        self,
        features: pd.Series | dict[str, float],
        ticker: str = "",
        trade_date: date | None = None,
    ) -> UnusualnessResult:
        """
        Calculate unusualness score for a single observation.

        Args:
            features: Normalized features (as Series or dict)
            ticker: Stock ticker (for result)
            trade_date: Date of calculation (for result)

        Returns:
            UnusualnessResult with score, components, and explanation
        """
        trade_date = trade_date or date.today()

        if isinstance(features, dict):
            features = pd.Series(features)

        # Step 1: Calculate component scores
        components = []
        for comp_def in SCORE_COMPONENTS:
            # Try zscore first, then percentile fallback
            zscore = features.get(comp_def["zscore_col"])

            if zscore is None or pd.isna(zscore):
                # Try percentile fallback
                pct_col = comp_def.get("pct_col")
                if pct_col:
                    pct_value = features.get(pct_col)
                    if pct_value is not None and not pd.isna(pct_value):
                        zscore = _percentile_to_zscore(pct_value)
                    else:
                        zscore = 0.0
                else:
                    zscore = 0.0

            component = ScoreComponent(
                name=comp_def["name"],
                weight=comp_def["weight"],
                zscore=float(zscore),
                contribution=comp_def["weight"] * abs(float(zscore)),
            )
            components.append(component)

        # Step 2: Calculate raw score (weighted sum of absolute z-scores)
        raw_score = sum(c.contribution for c in components)

        # Step 3: Add to history
        self._score_history.append(raw_score)
        if len(self._score_history) > self.history_window:
            self._score_history = self._score_history[-self.history_window:]

        # Step 4: Convert to 0-100 scale
        if len(self._score_history) >= 10:
            # Percentile rank against history
            history_array = np.array(self._score_history[:-1])  # Exclude current
            percentile = (np.sum(history_array < raw_score) / len(history_array)) * 100
            final_score = round(percentile, 1)
        else:
            # Fallback: sigmoid scaling
            # Raw score typically ranges 0-3 for reasonable z-scores
            final_score = round(self._sigmoid_scale(raw_score) * 100, 1)

        # Step 5: Determine level
        level = UnusualnessLevel.from_score(final_score)

        # Step 6: Get top drivers
        top_drivers = self._get_top_drivers(components)

        # Step 7: Generate explanation
        explanation = self._generate_explanation(final_score, level, components)

        return UnusualnessResult(
            ticker=ticker,
            trade_date=trade_date,
            score=final_score,
            raw_score=round(raw_score, 4),
            level=level,
            explanation=explanation,
            components=tuple(components),
            top_drivers=top_drivers,
        )

    def _sigmoid_scale(self, x: float) -> float:
        """
        Scale raw score to 0-1 using sigmoid.

        Tuned so that z-score sum of 1.5 maps to ~0.5
        """
        return 1 / (1 + np.exp(-1.5 * (x - 1.5)))

    def _get_top_drivers(
        self,
        components: list[ScoreComponent],
        n: int = 3,
    ) -> tuple[TopDriver, ...]:
        """Get top N contributing components."""
        # Sort by absolute z-score
        sorted_comps = sorted(
            components,
            key=lambda c: abs(c.zscore),
            reverse=True,
        )

        total_contribution = sum(c.contribution for c in components)

        drivers = []
        for comp in sorted_comps[:n]:
            if total_contribution > 0:
                contribution_pct = (comp.contribution / total_contribution) * 100
            else:
                contribution_pct = 0.0

            drivers.append(
                TopDriver(
                    feature=comp.name,
                    zscore=comp.zscore,
                    contribution_pct=contribution_pct,
                    direction="above" if comp.zscore > 0 else "below",
                )
            )

        return tuple(drivers)

    def _generate_explanation(
        self,
        score: float,
        level: UnusualnessLevel,
        components: list[ScoreComponent],
    ) -> str:
        """Generate human-readable explanation."""
        # Get top 2 drivers
        sorted_comps = sorted(
            components,
            key=lambda c: abs(c.zscore),
            reverse=True,
        )[:2]

        if not sorted_comps:
            return f"Unusualness score: {score} ({level.value}). All metrics normal."

        drivers_text = " and ".join(
            [
                f"{c.name.replace('_', ' ')} "
                f"({c.zscore:+.1f}σ {'above' if c.zscore > 0 else 'below'} average)"
                for c in sorted_comps
            ]
        )

        return f"Unusualness score: {score} ({level.value}). Primary drivers: {drivers_text}."

    def add_historical_score(self, raw_score: float) -> None:
        """
        Add a historical score for percentile calculation.

        Args:
            raw_score: Raw score value to add to history
        """
        self._score_history.append(raw_score)
        if len(self._score_history) > self.history_window:
            self._score_history = self._score_history[-self.history_window:]

    def get_score_summary(self) -> dict[str, Any]:
        """
        Get summary of score engine state.

        Returns:
            Dictionary with score statistics
        """
        if not self._score_history:
            return {
                "history_count": 0,
                "ready": False,
            }

        return {
            "history_count": len(self._score_history),
            "ready": len(self._score_history) >= 10,
            "mean_raw_score": float(np.mean(self._score_history)),
            "std_raw_score": float(np.std(self._score_history)),
            "min_raw_score": float(np.min(self._score_history)),
            "max_raw_score": float(np.max(self._score_history)),
        }
