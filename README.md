# OBSIDIAN MM

**Daily Market-Maker Regime & Unusualness Engine**

---

## Baseline Definition

**Formal Reference Framework**

---

### 0. Why Baselines Exist

OBSIDIAN MM does not measure absolute market quantities.
It measures **deviations from what is normal**.

Formally:

> No observation is meaningful without a reference state.
> The baseline defines that reference.

Without an explicit baseline:
- "high" volume is meaningless
- "large" dark pool activity is ambiguous
- "extreme" gamma exposure cannot be evaluated

**Every output of OBSIDIAN MM is therefore conditional on a baseline.**

---

### 1. What a Baseline Is (Formal Definition)

For a given instrument i, a baseline is a collection of statistical reference distributions describing normal market-maker-relevant behavior.

Let X_{i,t} be a daily metric (e.g. dark pool share, GEX, price impact).

The baseline for X is defined as:

```
B_i(X) = {μ_X, σ_X, Q_X}
```

where:
- μ_X = rolling mean
- σ_X = rolling dispersion (std or MAD)
- Q_X = empirical quantiles

computed over a rolling window:

```
W = 63 trading days
```

---

### 2. Instrument-Specific Nature of Baselines

Baselines are always instrument-specific.

Formally:

```
B_i ≠ B_j  for i ≠ j
```

Even within the same sector or index:
- liquidity structure differs
- options open interest differs
- dark pool participation differs

**Consequence:** Baselines must never be:
- pooled across instruments
- averaged cross-sectionally
- borrowed from proxies

---

### 3. Minimum Observation Requirement

A baseline is considered valid only if sufficient historical observations exist.

Let n_X be the number of stored observations for feature X.

```
n_X ≥ N_min = 21
```

If this condition is not met:
- the feature is excluded
- no inference is made
- no approximation is allowed

---

### 4. Baseline States

Each instrument has an explicit baseline state:

#### 4.1 BASELINE_EMPTY

```
∀X: n_X < N_min
```

No diagnosis is possible.

#### 4.2 BASELINE_PARTIAL

```
∃X₁, X₂: n_X₁ ≥ N_min ∧ n_X₂ < N_min
```

Diagnosis is conditional and excludes missing features.

#### 4.3 BASELINE_COMPLETE

```
∀X ∈ F: n_X ≥ N_min
```

Full diagnostic confidence.

---

### 5. Locked vs Dynamic Baselines

Baselines are split into structural and state-dependent components.

#### 5.1 Locked Baselines (Structural)

Updated infrequently (quarterly or manual review):
- typical dark pool share range
- block size distribution
- instrument liquidity profile
- long-run Greek characteristics

These represent structural properties of the instrument.

#### 5.2 Dynamic Baselines (Rolling)

Updated daily via rolling windows:
- z-scores of dark share
- z-scores of GEX / DEX
- price impact / efficiency
- IV and skew deviations

These represent current deviation from structure.

---

### 6. What Baselines Are NOT

Baselines are not:
- forecasts
- regime predictors
- adaptive learning models
- optimization targets

Formally:

```
B_i(X) ⇏ E[X_{i,t+1}]
```

They exist solely to contextualize observations.

---

### 7. Baseline Drift Control

Baselines are monitored for structural drift.

If a baseline parameter changes by more than a predefined threshold:

```
|( μ_{X,t} - μ_{X,t-1} ) / μ_{X,t-1}| > δ
```

a baseline drift warning is raised.

This prevents silent redefinition of "normal."

---

### 8. Baselines and Unusualness

All normalized metrics in OBSIDIAN MM are defined as:

```
Z_{X,i,t} = (X_{i,t} - μ_X) / σ_X
```

Unusualness is therefore **relative**, not absolute.

---

### 9. Governing Principle

> OBSIDIAN MM never asks "Is this big?"
> It asks "Is this unusual **for this instrument**?"

**Baselines are the answer to that question.**

---

### Summary

The baseline framework is the foundation of OBSIDIAN MM.

If the baseline is missing:
- the system refuses to guess
- the output is explicitly marked as incomplete

**This is a deliberate design choice.**

---

### Worked Baseline Example

**Building SPY's baseline over the first 30 trading days (cold start)**

This example illustrates how OBSIDIAN MM constructs baselines forward in time using daily pipeline runs, and how it behaves before the minimum observation threshold is reached.

---

#### 1. Setup

- Instrument: SPY
- Rolling baseline window: W = 63
- Minimum observations: N_min = 21
- Baseline states: EMPTY → PARTIAL → COMPLETE

Let t = 1,2,...,30 denote the first 30 trading days since onboarding SPY.

---

#### 2. What Gets Stored Each Day (Canonical History)

Each day t, OBSIDIAN MM persists a feature row:

```
X_t = (DarkShare_t, GEX_t, DEX_t, BlockIntensity_t, IVSkew_t,
       Efficiency_t, Impact_t, (optional: Vanna_t, Charm_t))
```

**Key point:** Some features may be unavailable due to provider lookback limits. For example:
- Vanna/Charm may be present only for the last ~7 days from the API, therefore baseline must be built incrementally from stored history.

If a feature is missing on day t, it is recorded as missing, not replaced.

---

#### 3. Days 1–20: Baseline Not Yet Valid (BASELINE_EMPTY / PARTIAL)

For t < 21:

```
n_X(t) < N_min
```

where n_X(t) is the count of stored observations for feature X up to day t.

**System behavior:**
- Unusualness score: not computed (or shown as NaN / unavailable)
- Regime label: UNDETERMINED (or computed only from features with sufficient baseline)
- Explainability text must state baseline status:

> "Baseline insufficient (<21 observations). Diagnosis withheld."

This prevents false confidence during cold start.

---

#### 4. Day 21: Baseline Becomes Usable for Eligible Features

At day t = 21, for any feature X with complete history:

```
n_X(21) ≥ 21
```

OBSIDIAN MM can now compute baseline parameters:

```
μ_X(21) = (1/21) × Σ_{k=1}^{21} X_k
σ_X(21) = sqrt((1/20) × Σ_{k=1}^{21} (X_k - μ_X(21))²)
```

and quantiles Q_X if needed.

From this point:
- DarkShare baseline ✓
- GEX baseline ✓
- DEX baseline ✓
- Efficiency/Impact baseline ✓
- Anything with missing history may still be excluded

Therefore baseline state is typically: **BASELINE_PARTIAL**

---

#### 5. Z-Scores Start on Day 21 (Feature-by-Feature)

For each eligible feature X, the normalized value becomes:

```
Z_X(t) = (X_t - μ_X(t)) / σ_X(t)   for n_X(t) ≥ 21
```

**Important:** If n_X(t) < 21, then Z_X(t) is undefined and must not be used.

---

#### 6. Days 22–30: Baseline Strengthens, But Remains Short-Window

During t = 22...30:
- Baseline uses the first t observations until it reaches W = 63
- Parameters update with each day (rolling expansion phase)

For t ≤ 63:

```
μ_X(t) = (1/t) × Σ_{k=1}^{t} X_k
σ_X(t) = sqrt((1/(t-1)) × Σ_{k=1}^{t} (X_k - μ_X(t))²)
```

After t > 63, the system transitions to a rolling window.

---

#### 7. What About Vanna/Charm with Short API Lookback?

Suppose Vanna is available only from day 24 onward (because the API only offers ~7 days history at onboarding).

Then:

```
n_Vanna(30) = 7 < 21
```

So:
- Vanna baseline is not computed
- Vanna is excluded from scoring/classification
- Explainability includes: *"Vanna/Charm excluded due to insufficient stored history."*

After ~3 weeks of running daily: n_Vanna ≥ 21 and Vanna/Charm becomes eligible for inclusion.

---

#### 8. What the User Should See on Day 30

By day 30:
- **Many baselines are valid:** DarkShare, GEX, DEX, price efficiency/impact
- **Some may remain invalid:** Vanna/Charm (often), depending on availability

So the baseline state is commonly: **BASELINE_PARTIAL**

And outputs should look like:
- **Regime:** computed only if regime rules rely on eligible features (otherwise UNDETERMINED)
- **Unusualness score:** computed from the subset of available normalized components:

```
S_t = Σ_{k ∈ F_t} w_k |Z_{k,t}|
```

where F_t is the set of features with valid baseline at time t.

Score is then mapped to percentile rank over available history:

```
U_t = PercentileRank(S_t | S_{1:t})
```

with the understanding that percentile meaning stabilizes as t grows.

---

#### 9. Key Takeaways (Why This Matters)

- Baselines are **built forward, never backfilled**
- The system is allowed to say: *"I don't know yet."*
- A baseline is not "born complete"; it **matures**
- Early days are for **data accumulation**, not diagnosis

**This is a deliberate design choice to prevent false confidence.**

---
---

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

## Regime Transition Matrix

**Formal State-Space Description**

---

### 1. Purpose

The Regime Transition Matrix (RTM) describes how market-maker regimes evolve over time, without implying prediction or optimal action.

Its role is to:
- quantify structural persistence
- identify unstable vs stable market states
- distinguish temporary anomalies from true regime shifts

**The RTM is descriptive, not predictive.**

---

### 2. State Space Definition

Let the discrete regime state at day t be:

```
R_t ∈ S
```

where the finite state set is:

```
S = {Gamma+ Control, Gamma− Liquidity Vacuum, Dark-Dominant Accumulation,
     Absorption-Like, Distribution-Like, Neutral, Undetermined}
```

Each trading day has exactly one assigned state.

---

### 3. Transition Definition

A transition occurs when:

```
R_t ≠ R_{t-1}
```

The ordered pair (R_{t-1}, R_t) defines a state transition event.

---

### 4. Transition Matrix Construction

For a given instrument i over a time window T, define the empirical transition counts:

```
C_jk = #{t ∈ T : R_{t-1} = j ∧ R_t = k}
```

where j, k ∈ S.

The transition probability matrix is then:

```
P_jk = C_jk / Σ_k' C_jk'
```

Each row of P sums to 1.

---

### 5. Interpretation Constraints

#### 5.1 No Markov Assumption

Although the matrix resembles a Markov transition matrix P(R_t | R_{t-1}), OBSIDIAN MM does **NOT** assume:
- stationarity
- time-homogeneity
- predictive sufficiency

The matrix is empirical and descriptive only.

#### 5.2 Time-Scale Awareness

Transitions are evaluated at daily resolution. Therefore:
- intra-day regime oscillations are intentionally ignored
- only structural daily shifts are represented

---

### 6. Derived Diagnostics (Non-Predictive)

The RTM supports several secondary diagnostics.

#### 6.1 Self-Transition Probability (Persistence)

For state j:

```
π_j = P_jj
```

- High π_j implies regime stability, structural dominance
- Low π_j implies fragile or transitional regime

#### 6.2 Transition Entropy

Define the entropy of outgoing transitions from state j:

```
H_j = -Σ_k P_jk log P_jk
```

Interpretation:
- low entropy → deterministic regime behavior
- high entropy → unstable / mixed conditions

#### 6.3 Absorbing-Like States (Informal)

A regime is absorbing-like if:

```
P_jj >> P_jk  ∀k ≠ j
```

This does not imply permanence, only relative dominance in the observed window.

---

### 7. Transition Semantics (Qualitative)

The RTM allows interpretation of structural market mechanics, not price outcomes.

Examples:

| Transition | Interpretation |
|------------|----------------|
| Gamma+ Control → Neutral | Dealer hedging pressure relaxed, control diminishes without stress |
| Neutral → Gamma− Vacuum | Transition into liquidity stress, often coincides with volatility shocks |
| Dark-Dominant → Absorption-Like | Off-exchange positioning followed by visible flow absorption |
| Frequent Neutral ↔ Mixed | Indicates MM inventory balancing, no dominant regime |

These interpretations are **ex post descriptors**, not forecasts.

---

### 8. Conditioning on Unusualness

Optionally, transitions may be conditioned on unusualness magnitude.

Define a threshold θ:

```
U_t > θ
```

Construct a conditional transition matrix:

```
P^(U>θ)_jk = P(R_t = k | R_{t-1} = j, U_t > θ)
```

Purpose: distinguish routine regime changes from stress-driven transitions.

This remains descriptive.

---

### 9. Instrument-Specific Nature

Transition matrices are computed per instrument.

They must **never** be:
- pooled across tickers
- averaged across instrument types
- normalized cross-sectionally

Each RTM reflects that instrument's microstructure personality.

---

### 10. What the RTM Explicitly Does NOT Do

The Regime Transition Matrix does not:
- predict the next regime
- estimate expected returns
- optimize decision rules
- imply causal direction

Formally:

```
P(R_{t+1} | R_t) ⇏ E[ΔP_{t+1}]
```

---

### 11. Summary

The Regime Transition Matrix provides a **second-order diagnostic layer**:
- **First order**: What regime are we in?
- **Second order**: How stable is this regime historically?

It transforms OBSIDIAN MM from a snapshot tool into a structural state-space monitor, without crossing into prediction or strategy.

---

### Closing Principle

> Markets do not move from signal to signal.
> They evolve from state to state.
>
> **The RTM exists to observe that evolution, not to trade it.**

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
