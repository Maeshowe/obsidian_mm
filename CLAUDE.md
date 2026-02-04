# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OBSIDIAN MM is a **diagnostic system** (not predictive) for market microstructure analysis. It classifies daily market-maker regimes and computes an unusualness score (0-100) based on dark pool activity, dealer gamma/delta exposure, and options flow. Core philosophy: "Observe, don't predict."

**Python 3.12+ required.**

## Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run daily pipeline
python scripts/run_daily.py SPY                    # Single ticker
python scripts/run_daily.py SPY QQQ AAPL           # Multiple tickers
python scripts/run_daily.py --date 2024-01-15 SPY  # Specific date

# Run tests
pytest tests/                      # All tests
pytest tests/unit/test_regimes.py  # Single test file
pytest -k "test_gamma"             # Tests matching pattern

# Linting and formatting
ruff check .                       # Lint
ruff format .                      # Format
mypy obsidian/ --strict            # Type check

# Dashboard
streamlit run obsidian/dashboard/app.py
```

## Architecture

```
API Sources → Ingest → Features → Normalize → Score + Classify → Explain
     │           │         │          │              │              │
  UW/Polygon   Cache    Extract    63-day       Weighted        Top drivers
    /FMP      (parquet)  metrics   z-score/     formula +       + human text
                                  percentile   decision tree
```

**Data flow through `DailyPipeline.run(ticker, date)`:**
1. Fetch data async from Unusual Whales + Polygon APIs (with caching)
2. Extract features via `FeatureAggregator` (dark pool, Greeks, price context)
3. Normalize features against 63-day rolling window
4. Classify regime using priority-ordered rules in `RegimeClassifier`
5. Calculate unusualness score via `UnusualnessEngine`
6. Generate human-readable explanation
7. Save to `data/processed/regimes/{ticker}/{date}.parquet`

## Key Design Patterns

- **Async only in ingest layer** - API clients use `httpx.AsyncClient` with rate limiting and retry; everything else is sync
- **Pydantic throughout** - Types in `obsidian/core/types.py` (FeatureSet, RegimeResult, UnusualnessResult)
- **YAML-driven configuration** - Thresholds, normalization methods, and regime rules in `config/`
- **Priority-ordered classification** - First matching regime rule wins (see rules below)
- **Baseline-first normalization** - All z-scores computed against ticker-specific baselines, not universal values

## Baseline System

**Core Principle:** "You cannot call something unusual without knowing what normal is."

```bash
# Compute baseline for new ticker (required before daily processing)
python scripts/compute_baseline.py SPY --verbose

# Diagnose API connections
python scripts/diagnose_api.py --ticker SPY --date 2024-01-15
```

**Baseline Components:**
- `obsidian/baseline/types.py` - TickerBaseline, DistributionStats
- `obsidian/baseline/calculator.py` - BaselineCalculator
- `obsidian/baseline/storage.py` - JSON storage in `data/baselines/`

**Locked vs Dynamic:**
- 🔒 **LOCKED** (quarterly): dark_share range, block size distribution, GEX structure
- 🔄 **DYNAMIC** (daily): z-scores computed against locked baseline

See `docs/BASELINE_SYSTEM.md` for full documentation.

## Regime Classification Rules (Priority Order)

```
0. UNDETERMINED:        Critical data missing (gex_zscore, dex_zscore)
1. Gamma+ Control:      gex_zscore > +1.5 AND price_efficiency < median
2. Gamma- Vacuum:       gex_zscore < -1.5 AND impact_per_vol > median
3. Dark-Dominant:       dark_pool_ratio > 70% AND block_trade_zscore > 1.0
4. Absorption-like:     dex_zscore < -1.0 AND price_change >= -0.5% AND dark_pool > 50%
5. Distribution-like:   dex_zscore > +1.0 AND price_change <= +0.5%
6. Neutral:             fallback (no conditions match)
```

**GUARDRAIL:** First match wins. Exactly one regime per day. If data is incomplete, UNDETERMINED is returned (not guessed).

## Important Thresholds (from `obsidian/core/constants.py`)

- GEX extreme: ±1.5σ
- DEX elevated: ±1.0σ
- Dark pool dominant: 70%
- Dark pool elevated: 50%
- Price stable range: ±0.5%

## Score Weights (Diagnostic, NOT Optimized)

```python
SCORE_WEIGHTS = {
    "dark_pool_activity": 0.25,
    "gamma_exposure": 0.25,
    "venue_shift": 0.20,
    "block_activity": 0.15,
    "iv_skew": 0.15,
}
```

## API Keys Required

Set in `.env` file:
- `UNUSUAL_WHALES_API_KEY` - Primary microstructure data
- `POLYGON_API_KEY` - OHLCV price data
- `FMP_API_KEY` - ETF flows and sector data

## Testing

Tests use pytest with async support. Key fixtures in `tests/conftest.py`:
- `sample_features` - General normalized features
- `gamma_positive_features`, `gamma_negative_features` - Regime-specific fixtures
- `sample_darkpool_df` - Mock dark pool trades

## Operational Guardrails

OBSIDIAN enforces strict operational guardrails. See `docs/GUARDRAILS.md` for full documentation.

| Guardrail | Purpose |
|-----------|---------|
| Baseline Drift Detection | Prevent silent invalidation of "normal" |
| Incomplete Data → UNDETERMINED | No guessing, explicit uncertainty |
| Instrument Type Separation | No cross-type normalization |
| Greeks Sign Convention Lock | Prevent silent regime inversion |
| Z-Score/Percentile Discipline | Z-scores for classification, percentiles for scoring |
| Priority Short-Circuit | One day = one state |

**Final Rule:** When in doubt → UNDETERMINED. False negatives over false confidence.

## Key Files

- `obsidian/core/types.py` - Pydantic models (FeatureSet, RegimeResult, UnusualnessResult, TopDriver)
- `obsidian/core/constants.py` - All thresholds and weights
- `obsidian/pipeline/daily.py` - Main entry point (DailyPipeline)
- `obsidian/baseline/` - Baseline system (types, calculator, storage)
- `obsidian/guardrails/` - Operational guardrails (types, validators, conventions)
- `obsidian/regimes/classifier.py` - RegimeClassifier with priority rules
- `obsidian/scoring/unusualness.py` - UnusualnessEngine
- `config/regimes.yaml` - Regime rule thresholds
- `config/normalization.yaml` - Per-feature normalization methods
- `docs/BASELINE_SYSTEM.md` - Baseline system documentation
- `docs/GUARDRAILS.md` - Operational guardrails documentation
