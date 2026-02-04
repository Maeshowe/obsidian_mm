# OBSIDIAN MM

**Observational Behavioral System for Institutional & Dealer-Informed Anomaly Networks**

*Daily Market-Maker Regime & Unusualness Diagnostic Engine*

---

## Philosophy

OBSIDIAN is a **diagnostic system**, not a predictive one.

Like obsidian glass—black, sharp, and reflective—this system observes and describes the current state of market microstructure. It does not predict, recommend, or optimize.

**Core principles:**
- **Observe, don't predict** — We describe what IS, not what WILL BE
- **Source data first** — Raw API data > derived proxies > computed estimates
- **Normalize everything** — Absolute values are meaningless without context
- **Explain everything** — Every label must have a human-readable justification

---

## What This System Does

### 1. MM Unusualness Engine

Computes a daily score (0-100) measuring how unusual the current market microstructure state is from a market-maker perspective.

**Inputs:**
- Dark pool volume and venue mix
- Dealer gamma/delta exposure (GEX, DEX)
- Block trade activity
- IV skew and term structure

**Output:**
```
Score: 72 (Unusual)
Top drivers: GEX +2.1σ, Dark Pool Ratio +1.8σ
```

### 2. MM Regime Classifier

Assigns a daily regime label to each instrument based on deterministic, rule-based logic.

**Regimes:**
| Regime | Meaning |
|--------|---------|
| Gamma+ Control | Dealers long gamma → volatility suppressed |
| Gamma- Liquidity Vacuum | Dealers short gamma → volatility amplified |
| Dark-Dominant Accumulation | High off-exchange activity with block prints |
| Absorption-like | Passive buying absorbing sell flow |
| Distribution-like | Selling into strength |
| Neutral / Mixed | No dominant pattern |

**Output:**
```
Regime: Gamma+ Control
Explanation: GEX z-score is +2.1 (above +1.5 threshold) with low price
efficiency, indicating dealers are significantly long gamma. Expect
volatility suppression.
```

---

## What This System Does NOT Do

| Prohibited | Why |
|------------|-----|
| Generate buy/sell signals | This is diagnostics, not trading |
| Backtest strategies | No alpha research |
| Use machine learning | Must be explainable |
| Predict future prices | Describes present state only |
| Optimize parameters | Weights are conceptual, not fitted |

**The unusualness score weights (0.25, 0.25, 0.20, 0.15, 0.15) are diagnostic weights based on market microstructure relevance. They are NOT optimized parameters, NOT backtest results. They reflect conceptual importance, not predictive power.**

---

## Data Sources

| Source | Data | Purpose |
|--------|------|---------|
| [Unusual Whales](https://unusualwhales.com/api) | Dark pool trades, Greeks (GEX, DEX, vanna, charm), options flow | Primary microstructure data |
| [Polygon.io](https://polygon.io) | Daily OHLCV, index ETF context | Price context |
| [FMP](https://financialmodelingprep.com) | ETF flows, sector performance | Macro overlay |

---

## Architecture

```
API Sources → Ingest → Features → Normalize → Score + Classify → Explain → Dashboard
     │            │         │          │              │              │          │
  UW/Polygon/   Cache    Extract    63-day      Weighted       Top 2-3     Streamlit
    FMP         (file)   metrics   z-score/     formula +     drivers +      UI
                          from     percentile   decision       human
                          raw                    tree          text
```

**Key design decisions:**
- **Streamlit** for dashboard — Chosen deliberately as a diagnostic UI, not a trading frontend
- **Parquet** for storage — Columnar efficiency for time-series data
- **Async in ingest only** — Concurrent API fetching; sync everywhere else
- **63-day rolling window** — Balances statistical stability with regime sensitivity

---

## Project Structure

```
obsidian_mm/
├── config/
│   ├── sources.yaml          # API endpoints, rate limits
│   ├── normalization.yaml    # Rolling windows, z-score params
│   └── regimes.yaml          # Human-readable regime rules
├── data/
│   ├── raw/                  # Immutable API responses
│   └── processed/            # Daily aggregates
├── obsidian/
│   ├── core/                 # Types, config, exceptions
│   ├── ingest/               # API clients, rate limiter, cache
│   ├── features/             # Feature extraction from raw data
│   ├── normalization/        # Rolling z-score, percentile
│   ├── regimes/              # Rule-based classifier
│   ├── scoring/              # Unusualness engine
│   ├── explain/              # Human-readable explanations
│   ├── dashboard/            # Streamlit UI
│   └── pipeline/             # Daily orchestration
├── tests/
├── scripts/
└── notebooks/
```

---

## Quick Start

### 1. Install

```bash
# Clone and install
cd obsidian_mm
pip install -e ".[dev]"

# Configure API keys
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run Daily Pipeline

```bash
# Single ticker
python scripts/run_daily.py SPY

# Multiple tickers
python scripts/run_daily.py SPY QQQ AAPL NVDA
```

### 3. Launch Dashboard

```bash
streamlit run obsidian/dashboard/app.py
```

---

## Regime Classification Logic

Regimes are evaluated in **priority order** (first match wins):

```
1. Gamma+ Control
   IF gex_zscore > +1.5 AND price_efficiency < median

2. Gamma- Liquidity Vacuum
   IF gex_zscore < -1.5 AND impact_per_vol > median

3. Dark-Dominant Accumulation
   IF dark_pool_ratio > 70% AND block_trade_zscore > 1.0

4. Absorption-like
   IF dex_zscore < -1.0 AND price_change >= -0.5% AND dark_pool > 50%

5. Distribution-like
   IF dex_zscore > +1.0 AND price_change <= +0.5%

6. Neutral / Mixed
   ELSE (fallback)
```

**Critical note:** Gamma regimes require price/impact context validation, not GEX z-score alone. This prevents over-labeling.

---

## Unusualness Score Formula

```
raw_score = 0.25 × |dark_pool_zscore|
          + 0.25 × |gex_zscore|
          + 0.20 × |venue_shift_zscore|
          + 0.15 × |block_activity_zscore|
          + 0.15 × |iv_skew_zscore|

final_score = percentile_rank(raw_score, 63-day history) → 0-100
```

| Score | Level | Interpretation |
|-------|-------|----------------|
| 0-20 | Very Normal | Metrics at historical baseline |
| 20-40 | Normal | Minor deviations |
| 40-60 | Slightly Unusual | Some metrics elevated |
| 60-80 | Unusual | Multiple significant deviations |
| 80-100 | Highly Unusual | Extreme readings |

---

## Tech Stack

- Python 3.12
- httpx (async HTTP client)
- pandas / polars (data manipulation)
- pydantic (config validation)
- streamlit + plotly (dashboard)
- pyarrow (parquet I/O)
- pytest (testing)

---

## License

MIT

---

## Disclaimer

This software is provided for **educational and diagnostic purposes only**. It is not financial advice, does not generate trading signals, and should not be used to make investment decisions. Past market microstructure patterns do not predict future outcomes.
