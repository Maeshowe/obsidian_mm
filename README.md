# OBSIDIAN MM

**Daily Market-Maker Regime & Unusualness Engine**

| | |
|---|---|
| **Version** | 1.0 |
| **Classification** | Internal Technical Reference |
| **Scope** | Market Microstructure Diagnostic System — Regime Classification & Unusualness Scoring |
| **Instrument Universe** | US Single Stocks, Index ETFs (SPY, QQQ, IWM) |
| **Temporal Resolution** | Daily Aggregation (T+0 close) |

---

## 1. System Definition

OBSIDIAN MM is a deterministic, rule-based diagnostic engine that measures the degree of deviation of an instrument's daily market microstructure state from its own empirical norm. The system produces two outputs per instrument per trading day:

| Output | Type | Domain |
|--------|------|--------|
| **MM Unusualness Score** | Continuous | U ∈ [0, 100] |
| **MM Regime Label** | Categorical | R ∈ {Γ⁺, Γ⁻, DD, ABS, DIST, NEU, UND} |

Both outputs are accompanied by a mandatory explainability vector identifying the top contributing features.

**Scope exclusions.** The system does not generate signals, forecasts, alpha estimates, or actionable trade recommendations. All outputs are descriptive and diagnostic. Formally, for any output O at time t:

    O(t) ⇏ E[ΔP(t+1)]

---

## 2. Data Sources

The system consumes daily-aggregated data from three authoritative providers. No derived proxies are used where a direct source metric exists.

| Domain | Provider | Endpoint Category |
|--------|----------|-------------------|
| Dark pool / off-exchange volume, block prints | Unusual Whales API | Dark pool flow |
| Options Greeks: GEX, DEX, Vanna, Charm | Unusual Whales API | Options exposure |
| IV surface, skew, term structure | Unusual Whales API | Volatility data |
| Daily OHLCV, index ETF context | Polygon.io API | Price & volume |
| ETF flows, sector performance | FMP Ultimate API | Macro overlay |

**Data quality rule.** If a source field is missing or flagged as stale on a given day, it is recorded as `NaN`. No interpolation, imputation, or forward-fill is applied. The downstream pipeline treats `NaN` as an explicit exclusion trigger.

---

## 3. Baseline Framework

### 3.1 Definition

For instrument *i* and daily feature *X*, the baseline is a tuple of rolling statistics:

    B_i(X) = { μ_X , σ_X , Q_X }

where:

- **μ_X** = rolling arithmetic mean of X
- **σ_X** = rolling sample standard deviation of X
- **Q_X** = empirical quantile function of X (used for percentile ranking)

All statistics are computed over a fixed rolling window:

    W = 63 trading days  (≈ 1 calendar quarter)

### 3.2 Minimum Observation Threshold

A baseline is valid if and only if:

    n_X ≥ N_min = 21 trading days

where n_X is the count of non-NaN observations of feature X within the current window. If this condition is not met, the feature is excluded from all downstream computation. No approximation or relaxation of N_min is permitted.

### 3.3 Baseline States

Each instrument is assigned exactly one baseline state:

| State | Condition | System Behavior |
|-------|-----------|-----------------|
| **BASELINE_EMPTY** | ∀X : n_X < 21 | No diagnosis. Output = UND. |
| **BASELINE_PARTIAL** | ∃X₁,X₂ : n_X₁ ≥ 21 ∧ n_X₂ < 21 | Conditional diagnosis. Excluded features listed. |
| **BASELINE_COMPLETE** | ∀X ∈ F : n_X ≥ 21 | Full diagnostic confidence. |

### 3.4 Expansion Phase (Cold Start)

For the first 63 trading days after onboarding, the baseline uses an expanding window:

    t ≤ 63 :  μ_X(t) = (1/t) × Σ_{k=1}^{t} X_k
              σ_X(t) = sqrt( (1/(t-1)) × Σ_{k=1}^{t} (X_k − μ_X(t))² )

    t > 63 :  transition to fixed rolling window W = 63

The first valid z-score is emitted at t = 21 (per-feature).

### 3.5 Instrument Isolation

Baselines are strictly instrument-specific:

    B_i ≠ B_j   for i ≠ j

Cross-sectional pooling, averaging, or proxy-borrowing across instruments is prohibited.

### 3.6 Baseline Drift Detection

If the rolling mean changes by more than a relative threshold δ between consecutive trading days:

    | (μ_{X,t} − μ_{X,t−1}) / μ_{X,t−1} | > δ

a **BASELINE_DRIFT** warning is raised. Recommended default: δ = 0.10 (10%). This prevents silent redefinition of "normal" and flags structural breaks.

### 3.7 Locked vs. Dynamic Components

| Component | Update Frequency | Examples |
|-----------|-----------------|----------|
| **Locked (Structural)** | Quarterly / manual review | Typical dark pool share range, block size distribution, instrument liquidity profile |
| **Dynamic (Rolling)** | Daily, via W=63 window | Z-scores of all features, percentile ranks |

Locked components represent the instrument's structural identity. Dynamic components measure deviation from that identity.

---

## 4. Feature Definitions

### 4.1 Dark Pool Share

Let V^dark_t = aggregate dark pool / off-exchange volume on day t, and V^total_t = total consolidated volume.

    DarkShare_t = V^dark_t / V^total_t

Normalized form:

    Z_dark(t) = ( DarkShare_t − μ_dark ) / σ_dark

**Domain:** DarkShare_t ∈ [0, 1]. Values outside this range indicate data error.

### 4.2 Block Trade Intensity

Block trades are defined as prints exceeding a size threshold (source: Unusual Whales block detection). Block intensity is quantified via upper-tail frequency analysis.

Let B_t = count or volume of block-classified prints on day t.

    Z_block(t) = ( B_t − μ_block ) / σ_block

Alternatively, block intensity can be measured as the proportion of volume above the 75th or 90th percentile of historical print sizes for that instrument.

### 4.3 Dealer Gamma Exposure (GEX)

GEX_t = net dealer gamma exposure on day t, sourced directly from Unusual Whales.

    Z_GEX(t) = ( GEX_t − μ_GEX ) / σ_GEX

**Sign convention (fixed, non-negotiable):**

- GEX > 0 → dealers are long gamma → hedging activity dampens price moves (stabilizing)
- GEX < 0 → dealers are short gamma → hedging amplifies price moves (destabilizing)

### 4.4 Dealer Delta Exposure (DEX)

DEX_t = net dealer delta exposure on day t.

    Z_DEX(t) = ( DEX_t − μ_DEX ) / σ_DEX

DEX is a contextual feature used exclusively for absorption/distribution classification. It is never used as a standalone diagnostic.

### 4.5 Venue Mix

Z_venue(t) captures the distributional shift in execution venue allocation (lit exchanges, dark pools, ATS venues) relative to the instrument's baseline. Computed as a composite z-score across venue-share features.

### 4.6 IV Skew and Term Structure

Z_IV(t) captures deviations in the implied volatility surface:

- Put-call skew deviation from rolling baseline
- Near-term vs. far-term IV ratio deviation

    Z_IV(t) = ( IVSkew_t − μ_IV ) / σ_IV

### 4.7 Price Efficiency (Control Proxy)

Let R_t = High_t − Low_t (intraday range) and V^total_t = total volume.

    Efficiency_t = R_t / V^total_t

Low Efficiency_t → price is being controlled / absorbed (small range per unit volume).

### 4.8 Price Impact (Vacuum Proxy)

Let ΔP_t = |Close_t − Open_t| (absolute open-to-close move).

    Impact_t = ΔP_t / V^total_t

High Impact_t → small flows causing large directional moves (liquidity vacuum).

**Both Efficiency and Impact are evaluated relative to the instrument's own baseline, not in absolute terms.**

### 4.9 Vanna & Charm (Conditional)

Vanna and Charm exposures are sourced from Unusual Whales when available. Due to API lookback limitations (often ~7 days at onboarding), these features typically require ~3 weeks of daily pipeline runs before reaching N_min = 21.

Until valid:

    n_Vanna < 21  →  feature excluded, noted in explainability output

---

## 5. MM Unusualness Score

### 5.1 Raw Composite Score

The raw unusualness score is a weighted sum of absolute z-scores across the eligible feature set F_t (features with valid baseline at time t):

    S_t = Σ_{k ∈ F_t}  w_k × |Z_k(t)|

**Fixed diagnostic weights:**

| Feature k | Weight w_k | Rationale |
|-----------|-----------|-----------|
| Z_dark (Dark Pool Share) | 0.25 | Primary institutional flow signal |
| Z_GEX (Gamma Exposure) | 0.25 | Primary dealer positioning signal |
| Z_venue (Venue Mix) | 0.20 | Execution structure deviation |
| Z_block (Block Intensity) | 0.15 | Large-print institutional activity |
| Z_IV (IV Skew) | 0.15 | Options market stress indicator |

**These weights are conceptual allocations reflecting market microstructure relevance. They are NOT optimized, NOT fitted to historical data, and NOT the product of backtesting. They must not be treated as tunable parameters.**

If some features are excluded (BASELINE_PARTIAL), weights are not renormalized. The score reflects only the available feature set.

### 5.2 Percentile Mapping

The raw score is mapped to a bounded [0, 100] scale via percentile rank over the available history:

    U_t = PercentileRank( S_t | { S_τ : τ ∈ [t−W, t] } )

where W = 63 (or the expanding window during cold start).

### 5.3 Interpretation Bands

| U_t Range | Label | Interpretation |
|-----------|-------|---------------|
| 0–30 | Normal | Microstructure within historical norms |
| 30–60 | Elevated | Measurable deviation; monitoring warranted |
| 60–80 | Unusual | Significant departure from baseline |
| 80–100 | Extreme | Rare microstructure configuration |

These bands are heuristic labels for human consumption. They do not carry statistical significance thresholds (e.g., they are not p-values).

---

## 6. MM Regime Classification

### 6.1 Design Principles

- **Deterministic:** All rules are explicit conditional logic; no ML, no probabilistic classifiers.
- **Mutually exclusive:** Exactly one regime per instrument per day.
- **Priority-ordered:** Rules are evaluated top-to-bottom. First match wins (short-circuit).
- **Explainable:** Every classification is accompanied by the triggering conditions in human-readable form.

### 6.2 Regime Definitions

Regimes are evaluated in the following strict priority order. All thresholds reference z-scores or percentiles computed against the instrument's own baseline.

---

**Priority 1 — Γ⁺ (Gamma-Positive Control)**

    Z_GEX(t) > +1.5   AND   Efficiency_t < median(Efficiency_baseline)

Interpretation: Dealers are significantly long gamma. Their hedging activity compresses the intraday range, resulting in below-normal price efficiency. Volatility suppression regime.

---

**Priority 2 — Γ⁻ (Gamma-Negative Liquidity Vacuum)**

    Z_GEX(t) < −1.5   AND   Impact_t > median(Impact_baseline)

Interpretation: Dealers are significantly short gamma. Their hedging amplifies directional moves. Above-normal price impact per unit volume signals a liquidity vacuum.

---

**Priority 3 — DD (Dark-Dominant Accumulation)**

    DarkShare_t > 0.70   AND   Z_block(t) > +1.0

Interpretation: More than 70% of volume is executing off-exchange, with block-print intensity elevated above +1σ. Consistent with institutional positioning via dark liquidity.

---

**Priority 4 — ABS (Absorption-Like)**

    Z_DEX(t) < −1.0   AND   ΔP_t / Close_{t−1} ≥ −0.005   AND   DarkShare_t > 0.50

Interpretation: Net delta exposure is significantly negative (sell pressure), but the daily close-to-close move is no worse than −0.5%, and dark pool participation exceeds 50%. Passive buying is absorbing the sell flow.

---

**Priority 5 — DIST (Distribution-Like)**

    Z_DEX(t) > +1.0   AND   ΔP_t / Close_{t−1} ≤ +0.005

Interpretation: Net delta exposure is significantly positive (buy pressure), but the daily move is no better than +0.5%. Supply is being distributed into strength without upside follow-through.

---

**Priority 6 — NEU (Neutral / Mixed)**

    No prior rule matched.

Interpretation: No single microstructure pattern dominates. The instrument is in a balanced or ambiguous state.

---

**Priority 7 — UND (Undetermined)**

    Baseline state = BASELINE_EMPTY   OR   insufficient features for any rule

Interpretation: System cannot classify. Diagnosis withheld.

---

### 6.3 Threshold Summary

| Parameter | Value | Context |
|-----------|-------|---------|
| Z_GEX threshold (Γ⁺ / Γ⁻) | ±1.5 | ~93rd percentile under normality |
| DarkShare threshold (DD) | 0.70 | Absolute proportion |
| Z_block threshold (DD) | +1.0 | ~84th percentile under normality |
| Z_DEX threshold (ABS / DIST) | ±1.0 | ~84th percentile under normality |
| Price move cap (ABS) | ≥ −0.5% | Close-to-close return |
| Price move cap (DIST) | ≤ +0.5% | Close-to-close return |
| DarkShare floor (ABS) | 0.50 | Absolute proportion |
| Efficiency benchmark (Γ⁺) | < median | Rolling 63d median |
| Impact benchmark (Γ⁻) | > median | Rolling 63d median |

---

## 7. Explainability Protocol

Every output tuple (U_t, R_t) must be accompanied by:

1. **The assigned regime label and its triggering condition values** (e.g., "Z_GEX = +2.14, Efficiency = 0.0032 < median 0.0041")
2. **The top 2–3 features contributing to U_t**, ranked by w_k × |Z_k(t)|
3. **A list of any excluded features** with reason (e.g., "Vanna excluded: n = 14 < N_min = 21")
4. **The baseline state** (EMPTY / PARTIAL / COMPLETE)

Example output:

> **Regime: Γ⁻ (Gamma-Negative Liquidity Vacuum)**  
> Z_GEX = −2.31 (threshold: < −1.5) ✓  
> Impact = 0.0087 > median 0.0052 ✓  
> **Unusualness: 78 (Unusual)**  
> Top drivers: GEX |Z| = 2.31 × 0.25 = 0.58; Dark |Z| = 1.84 × 0.25 = 0.46  
> Excluded: Charm (n = 9 < 21)  
> Baseline: PARTIAL

---

## 8. Regime Transition Matrix (RTM)

### 8.1 Purpose

The RTM provides second-order diagnostics: not what regime are we in, but how stable is this regime historically. It is descriptive, not predictive.

### 8.2 Construction

For instrument *i* over window T, the empirical transition count matrix is:

    C_jk = #{ t ∈ T : R_{t−1} = j ∧ R_t = k }

The row-normalized transition probability matrix:

    P_jk = C_jk / Σ_{k'} C_{jk'}

Each row sums to 1.

### 8.3 Derived Diagnostics

**Self-transition probability (persistence):**

    π_j = P_jj

High π_j → structurally stable regime. Low π_j → fragile / transitional.

**Transition entropy:**

    H_j = − Σ_k  P_jk × log(P_jk)

Low H_j → deterministic transitions from state j. High H_j → unpredictable / mixed behavior.

### 8.4 Constraints

- **No Markov assumption.** The matrix is empirical; stationarity and time-homogeneity are not assumed.
- **No predictive use.** P(R_{t+1} | R_t) ⇏ E[ΔP_{t+1}].
- **Instrument-specific.** RTMs must never be pooled or averaged across instruments.
- **Optional conditioning.** Transitions may be conditioned on unusualness threshold θ:

        P^(U>θ)_jk = P( R_t = k | R_{t−1} = j, U_t > θ )

    This distinguishes routine regime changes from stress-driven transitions.

---

## 9. Dashboard Specification

The dashboard is a structured projection of the system state space. Each page answers exactly one question.

| Page | Question | Mathematical Role | Displayed Quantities |
|------|----------|-------------------|---------------------|
| **Daily State** | What is the MM state today? | Point estimate | U_t, R_t, top drivers, baseline state |
| **Historical Regimes** | How has the regime evolved? | State trajectory | {R_t}, {U_t} over [T₀, T] |
| **Drivers & Contributors** | What is driving the score? | Score decomposition | w_k × \|Z_k(t)\| for each feature |
| **Baseline Status** | How reliable is this diagnosis? | Confidence constraint | n_f per feature, baseline state badge |

**Explicitly excluded from the dashboard:** price forecasts, trade entries/exits, directional probability, backtested performance, signal confidence metrics.

---

## 10. Failure Modes & Uncertainty Handling

| Condition | System Response |
|-----------|----------------|
| Feature data missing (NaN) | Feature excluded. No imputation. |
| n_X < N_min = 21 | Feature excluded from scoring and classification. |
| All features below N_min | Regime = UND. Score = N/A. |
| Baseline drift detected | BASELINE_DRIFT warning raised. |
| API provider outage | Day skipped. No partial inference. |

**Governing principle:** False negatives (missing a diagnosis) are acceptable. False confidence (diagnosing without adequate data) is not.

---

## 11. Parameter Registry

All system parameters in one place. None are optimized or fitted.

| Parameter | Symbol | Value | Justification |
|-----------|--------|-------|---------------|
| Rolling window | W | 63 trading days | ≈ 1 quarter; balances stability and sensitivity |
| Minimum observations | N_min | 21 trading days | ≈ 1 month; minimum for meaningful dispersion estimate |
| GEX z-threshold | — | ±1.5 | Captures ~top/bottom 7% of distribution |
| DEX z-threshold | — | ±1.0 | Captures ~top/bottom 16% of distribution |
| Block z-threshold | — | +1.0 | Upper-tail institutional activity |
| DarkShare threshold (DD) | — | 0.70 | Supermajority off-exchange execution |
| DarkShare floor (ABS) | — | 0.50 | Majority off-exchange execution |
| Price move cap (ABS) | — | −0.5% | Close-to-close return tolerance |
| Price move cap (DIST) | — | +0.5% | Close-to-close return tolerance |
| Baseline drift threshold | δ | 0.10 | 10% relative shift in rolling mean |
| Score weight: Z_dark | w₁ | 0.25 | Conceptual, not optimized |
| Score weight: Z_GEX | w₂ | 0.25 | Conceptual, not optimized |
| Score weight: Z_venue | w₃ | 0.20 | Conceptual, not optimized |
| Score weight: Z_block | w₄ | 0.15 | Conceptual, not optimized |
| Score weight: Z_IV | w₅ | 0.15 | Conceptual, not optimized |

---

## 12. Architecture Summary

```
Sources (UW / Polygon / FMP)
    │
    ▼
Async Ingest → Raw Cache (Parquet, immutable)
    │
    ▼
Feature Extraction (per-instrument, per-day)
    │
    ▼
Normalization (63d rolling z-score / percentile)
    │
    ▼
Scoring (weighted |Z| sum → percentile rank)  +  Classification (priority-ordered rules)
    │
    ▼
Explainability (top drivers + exclusions + baseline state)
    │
    ▼
Dashboard (Streamlit + Plotly)
```

**Stack:** Python 3.12, httpx (async ingest), pandas/polars, pydantic (config), pyarrow (Parquet I/O), Streamlit + Plotly (UI), pytest (testing).

---

## Appendix A: Notation Reference

| Symbol | Meaning |
|--------|---------|
| X_t | Daily value of feature X at time t |
| μ_X | Rolling mean of X over window W |
| σ_X | Rolling standard deviation of X over window W |
| Z_X(t) | Standardized z-score: (X_t − μ_X) / σ_X |
| B_i(X) | Baseline tuple {μ, σ, Q} for instrument i, feature X |
| F_t | Set of features with valid baseline at time t |
| S_t | Raw unusualness score (weighted absolute z-sum) |
| U_t | Final unusualness score ∈ [0, 100] (percentile rank of S_t) |
| R_t | Regime label at time t |
| W | Rolling window length = 63 trading days |
| N_min | Minimum observation count = 21 |
| C_jk | Transition count from regime j to regime k |
| P_jk | Transition probability: C_jk / Σ_k' C_jk' |
| π_j | Self-transition probability: P_jj |
| H_j | Transition entropy from state j |
| δ | Baseline drift detection threshold = 0.10 |

---

## Appendix B: Quick Start

### Installation

```bash
cd obsidian_mm
pip install -e ".[dev]"

# Configure API keys
cp .env.example .env
# Edit .env with your API keys
```

### Run Daily Pipeline

```bash
python scripts/run_daily.py SPY              # Single ticker
python scripts/run_daily.py SPY QQQ AAPL     # Multiple tickers
```

### Launch Dashboard

```bash
streamlit run obsidian/dashboard/app.py
```

---

## Appendix C: Project Structure

```
obsidian_mm/
├── config/                   # YAML configuration
│   ├── sources.yaml          # API endpoints, rate limits
│   ├── normalization.yaml    # Rolling windows, z-score params
│   └── regimes.yaml          # Regime classification rules
├── data/
│   ├── raw/                  # Immutable API responses
│   ├── processed/            # Daily aggregates + feature history
│   └── baselines/            # Instrument baselines (JSON)
├── obsidian/
│   ├── core/                 # Types, config, exceptions
│   ├── ingest/               # API clients, rate limiter, cache
│   ├── features/             # Feature extraction
│   ├── normalization/        # Rolling z-score, percentile
│   ├── baseline/             # Baseline calculator, storage, history
│   ├── regimes/              # Rule-based classifier
│   ├── scoring/              # Unusualness engine
│   ├── explain/              # Human-readable explanations
│   ├── dashboard/            # Streamlit UI
│   └── pipeline/             # Daily orchestration
├── tests/
├── scripts/
└── docs/
```

---

## License

MIT

---

## Disclaimer

This software is provided for **educational and diagnostic purposes only**. It is not financial advice, does not generate trading signals, and should not be used to make investment decisions. Past market microstructure patterns do not predict future outcomes.
