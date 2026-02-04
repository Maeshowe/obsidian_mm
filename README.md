# OBSIDIAN MM

**Daily Market-Maker Regime & Unusualness Engine**

## Quantitative Specification

---

### 1. Purpose and Scope

OBSIDIAN MM is a diagnostic market microstructure system, not a trading strategy.

Its sole purpose is to measure and classify how unusual the current market state is, from a market-maker and institutional liquidity perspective, using daily-aggregated, source-data-first inputs.

The system explicitly does **NOT**:
- generate buy/sell signals
- make price predictions
- optimize parameters for returns
- perform backtesting or alpha estimation

All outputs are descriptive and diagnostic, not actionable.

---

### 2. Instruments and Timeframe

- **Instrument scope:**
  - Single stocks (US equities)
  - Index ETFs (e.g. SPY, QQQ, IWM)
- **Timeframe:**
  - Daily aggregation only

Intraday microstructure is intentionally out of scope.

---

### 3. Data Sources (Authoritative)

The system prioritizes authoritative source data and minimizes derived proxies.

| Domain | Primary Source |
|--------|----------------|
| Dark pool / off-exchange trades | Unusual Whales API |
| Options Greeks (GEX, DEX, vanna, charm) | Unusual Whales API |
| Price & volume (OHLCV) | Polygon API |
| Index / ETF context | Polygon Indices |
| Macro / sector overlay | FMP Ultimate |

All derived metrics are computed only when no reliable source metric exists.

---

### 4. Baseline Framework

#### 4.1 Instrument-Specific Baseline

All measurements are evaluated relative to each instrument's own historical norm.

Let X_t be a daily metric at time t.

Baseline statistics are computed over a rolling window of:

```
W = 63 trading days
```

Minimum required observations:

```
N_min = 21
```

#### 4.2 Baseline States

Each instrument has an explicit baseline state:
- **BASELINE_EMPTY**: insufficient history
- **BASELINE_PARTIAL**: history exists, but some features unavailable
- **BASELINE_COMPLETE**: all required features meet N_min

Features with insufficient history are excluded, never estimated or backfilled.

---

### 5. Core Feature Definitions

#### 5.1 Dark Pool Metrics

Let:
- V^dark_t = dark pool volume
- V^total_t = total volume

```
DarkShare_t = V^dark_t / V^total_t
```

Normalization:

```
Z_dark(t) = (DarkShare_t - μ_dark) / σ_dark
```

Block activity is measured via upper-tail event frequency (e.g. 75th / 90th percentile sizes).

#### 5.2 Dealer Gamma Exposure (GEX)

Let GEX_t denote net dealer gamma exposure for day t.

Normalized form:

```
Z_GEX(t) = (GEX_t - μ_GEX) / σ_GEX
```

Sign convention (locked):
- GEX > 0: dealers long gamma (stabilizing)
- GEX < 0: dealers short gamma (destabilizing)

#### 5.3 Delta Exposure (DEX)

Normalized delta pressure:

```
Z_DEX(t) = (DEX_t - μ_DEX) / σ_DEX
```

DEX is used only for absorption / distribution context, never alone.

#### 5.4 Price Impact and Efficiency

Let:
- R_t = High_t - Low_t
- ΔP_t = |Close_t - Open_t|

Price efficiency (control proxy):

```
Efficiency_t = R_t / V^total_t
```

Low values → controlled / absorbed price action.

Impact per volume (vacuum proxy):

```
Impact_t = ΔP_t / V^total_t
```

High values → liquidity vacuum.

Both metrics are evaluated relative to the instrument baseline, not in absolute terms.

---

### 6. MM Regime Classification (Deterministic)

Exactly one regime per day is assigned, using priority-ordered rules.

#### 6.1 Priority Order

1. Gamma+ Control
2. Gamma− Liquidity Vacuum
3. Dark-Dominant Accumulation
4. Absorption-Like
5. Distribution-Like
6. Neutral / Mixed

Once a rule matches, evaluation stops (short-circuit logic).

#### 6.2 Regime Definitions

**Gamma+ Control**
```
Z_GEX > +1.5  AND  Efficiency_t < median baseline
```
Interpretation: dealer hedging dampens price movement.

**Gamma− Liquidity Vacuum**
```
Z_GEX < -1.5  AND  Impact_t > median baseline
```
Interpretation: small flows cause large moves.

**Dark-Dominant Accumulation**
```
DarkShare_t > 70%  AND  Z_Block > 1.0
```
Interpretation: institutional positioning via off-exchange liquidity.

**Absorption-Like**
```
Z_DEX < -1.0  AND  ΔP_t >= -0.5%  AND  DarkShare_t > 50%
```
Interpretation: aggressive flow absorbed without downside follow-through.

**Distribution-Like**
```
Z_DEX > +1.0  AND  ΔP_t <= +0.5%
```
Interpretation: supply present despite positive pressure.

---

### 7. MM Unusualness Score

The MM Unusualness Score measures magnitude of deviation, not direction.

#### 7.1 Raw Score

```
S_t = 0.25 × |Z_dark(t)|
    + 0.25 × |Z_GEX(t)|
    + 0.20 × |Z_venue(t)|
    + 0.15 × |Z_block(t)|
    + 0.15 × |Z_IV/skew(t)|
```

Weights are conceptual, not optimized.

#### 7.2 Final Score

The raw score is mapped to a bounded scale via percentile rank:

```
Unusualness_t = PercentileRank(S_t | S_{t-W:t}) ∈ [0, 100]
```

Interpretation:
- 0–30: normal
- 30–60: elevated
- 60–80: unusual
- 80–100: extreme microstructure deviation

---

### 8. Explainability Requirement

Every output includes a human-readable explanation, describing:
- the assigned regime
- the top 2–3 contributing factors
- any excluded features due to incomplete baselines

Example:

> "Dealer gamma was extremely negative while price moved sharply on below-average volume, indicating a liquidity vacuum. Vanna/charm excluded due to insufficient history."

---

### 9. Failure and Uncertainty Handling

- Missing or incomplete data ⇒ **UNDETERMINED**
- No interpolation, no backfilling, no inference
- False negatives are acceptable
- **False confidence is not**

---

### 10. Summary

OBSIDIAN MM does not predict markets.
It describes market states, using normalized deviations from instrument-specific norms, through a market-maker lens.

**Its value lies in context, not signals.**

---

## Dashboard Architecture & Mathematical Interpretation

This section defines the mathematical meaning and diagnostic intent of each dashboard page.
The dashboard is not a visualization of raw data, but a structured projection of the OBSIDIAN MM state space.

**Each page answers exactly one question.**

---

### 1. Daily State Page

*"What is the market-maker-relevant state today?"*

#### 1.1 Displayed Quantities

For instrument i on day t:

- **MM Unusualness Score**: U_{i,t} ∈ [0, 100]
- **MM Regime Label**: R_{i,t} ∈ {Gamma+ Control, Gamma− Vacuum, Dark-Dominant, Absorption, Distribution, Neutral, Undetermined}
- **Explainability Vector**: E_{i,t} = {f₁, f₂, f₃} where f_k are the top contributing normalized features

#### 1.2 Mathematical Interpretation

The Daily State Page represents a single point evaluation of the market microstructure:

```
State_{i,t} = (U_{i,t}, R_{i,t}, E_{i,t})
```

This page does not show history and does not imply dynamics.

#### 1.3 Diagnostic Meaning

- U_{i,t} measures magnitude of deviation from the instrument's baseline
- R_{i,t} classifies the structural regime dominating today
- E_{i,t} explains why this regime was assigned

**No directional inference is allowed.**

---

### 2. Historical Regimes Page

*"How has the market-maker regime evolved over time?"*

#### 2.1 Displayed Quantities

For a rolling window t ∈ [T₀, T]:
- Regime time series: {R_{i,t}} for t = T₀ to T
- Unusualness time series: {U_{i,t}} for t = T₀ to T

#### 2.2 Mathematical Interpretation

This page visualizes the state trajectory of the system:

```
Γ_i = {(U_{i,t}, R_{i,t})} for t = T₀ to T
```

The trajectory shows regime persistence, transitions, and clustering—not trend strength.

#### 2.3 Diagnostic Meaning

- Long runs of the same R_{i,t} ⇒ structural persistence
- Rapid switching ⇒ unstable or mixed conditions
- High U_{i,t} without regime change ⇒ intensity within a stable regime

This page answers "how often and how long", not "where price goes."

---

### 3. Drivers & Contributors Page

*"Which factors are responsible for the current state?"*

#### 3.1 Displayed Quantities

For day t, let the normalized feature vector be:

```
Z_{i,t} = (Z_dark, Z_GEX, Z_venue, Z_block, Z_IV/skew, ...)
```

The dashboard shows:
- Absolute contributions: |w_k × Z_{k,i,t}|
- Top k ∈ {1,2,3} contributors

#### 3.2 Mathematical Interpretation

The unusualness score is decomposed as:

```
U_{i,t} = PercentileRank(Σ_k w_k |Z_{k,i,t}|)
```

This page exposes the partial derivatives of the score with respect to each feature:

```
∂U/∂Z_k ∝ w_k |Z_{k,i,t}|
```

#### 3.3 Diagnostic Meaning

- Identifies dominant stressors
- Separates:
  - option-driven stress (Greeks)
  - liquidity stress (impact / dark pool)
  - structural positioning (blocks)

This page answers "what is driving the diagnosis."

---

### 4. Baseline Status Page (Implicit / Badge-Level)

*"How confident is this diagnosis?"*

#### 4.1 Displayed Quantities

For each feature f:
- Observation count: n_f
- Minimum required: n_f ≥ N_min = 21

Baseline state: B_i ∈ {EMPTY, PARTIAL, COMPLETE}

#### 4.2 Mathematical Interpretation

The effective feature set used is:

```
F_{i,t} = {f : n_f ≥ N_min}
```

Excluded features:

```
F^c_{i,t} = {f : n_f < N_min}
```

#### 4.3 Diagnostic Meaning

- **BASELINE_COMPLETE** ⇒ full confidence
- **BASELINE_PARTIAL** ⇒ conditional diagnosis
- **BASELINE_EMPTY** ⇒ no diagnosis

The system never extrapolates beyond available data.

---

### 5. What the Dashboard Explicitly Does NOT Show

To avoid misinterpretation, the dashboard intentionally excludes:
- price forecasts
- trade entries or exits
- probability of direction
- backtested performance
- signal confidence metrics

Formally:

```
∀t: Dashboard(t) ⇏ E[ΔP_{t+1}]
```

---

### 6. Information-Theoretic Summary

Each dashboard page projects the same underlying system state into a different information subspace:

| Page | Question | Mathematical Role |
|------|----------|-------------------|
| Daily State | What is today? | Point estimate |
| Historical Regimes | How did we get here? | State trajectory |
| Drivers | Why this state? | Score decomposition |
| Baseline Status | How reliable is this? | Confidence constraint |

---

### 7. Final Note

**The dashboard is a lens, not a lever.**

It allows the user to:
- observe regime structure
- assess deviation from normal
- understand dominant forces

It deliberately avoids telling the user what to do.

---
---

## Philosophy

*Observational Behavioral System for Institutional & Dealer-Informed Anomaly Networks*

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
