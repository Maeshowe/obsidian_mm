# OBSIDIAN MM Baseline System

## Why Measure Deviation from Normal, Not Absolute Values

OBSIDIAN is a **diagnostic system**, not a predictive one. To diagnose whether the current market state is unusual, we must first establish what "normal" looks like.

### The Problem with Absolute Values

Consider these two scenarios:

| Metric | SPY | MEME Stock |
|--------|-----|------------|
| Dark Pool Ratio | 35% | 35% |
| Daily GEX | -2M | -2M |
| Daily Range | 1.5% | 1.5% |

**Question:** Is anything unusual here?

**Answer:** We cannot tell without knowing what's normal for each instrument.

- SPY typically has 25-40% dark pool → 35% is **normal**
- MEME stock typically has 5-15% dark pool → 35% is **highly unusual**

The same absolute value means completely different things depending on the instrument.

### The Solution: Instrument-Specific Baselines

Every metric in OBSIDIAN is compared against its own baseline:

```
Z-score = (current_value - baseline_mean) / baseline_std
```

This ensures:
1. **Comparability**: A z-score of +2 means the same level of unusualness for any instrument
2. **Context**: Each instrument is judged by its own standards
3. **Explainability**: "Dark pool is 1.8σ above normal" is meaningful

---

## Baseline Architecture

### Part 1: Baseline Checklist (Run-Once per Ticker)

When a new ticker is onboarded, we compute a complete baseline profile using 63 trading days of historical data.

#### A) Dark Pool / Venue Baselines

| Metric | Description | Purpose |
|--------|-------------|---------|
| `dark_share` | Distribution of daily dark pool % | "How dark is this normally?" |
| `dark_share_typical_range` | mean ± 1.5σ bounds | Define "normal" range |
| `daily_block_count` | Distribution of block trades/day | Block activity baseline |
| `block_size` | Distribution (p75, p90) | What's a "big" block? |
| `venue_shift` | Distribution of day-over-day changes | Venue migration baseline |

#### B) Options / Greeks Baselines

| Metric | Description | Purpose |
|--------|-------------|---------|
| `gex` | GEX distribution (mean, std, MAD) | "How gamma-sensitive normally?" |
| `gex_positive_pct` | % days with positive gamma | Structural gamma bias |
| `gex_negative_pct` | % days with negative gamma | Structural gamma bias |
| `dex` | DEX distribution | Delta exposure baseline |
| `iv_atm` | ATM IV distribution | Normal volatility levels |
| `iv_atm_daily_change` | Daily IV change distribution | Normal IV movement |
| `iv_skew` | Skew distribution | Normal skew levels |

#### C) Price Impact / Efficiency Baselines

| Metric | Description | Purpose |
|--------|-------------|---------|
| `range_per_volume` | Daily range / volume | "How much does volume move price?" |
| `impact_per_volume` | |close - open| / volume | Price impact efficiency |
| `price_efficiency` | Range efficiency score | How controlled is price? |
| `daily_range_pct` | Daily range distribution | Normal volatility |

---

### Part 2: Locked vs Dynamic Baselines

#### 🔒 LOCKED BASELINES (Structural)

Updated: **Quarterly or manually**

These represent the instrument's fundamental characteristics that don't change day-to-day:

| Category | Metrics |
|----------|---------|
| Dark Pool Profile | Typical dark share range, block size distribution |
| Gamma Structure | Typical GEX range, positive/negative gamma bias |
| Liquidity Profile | Normal price efficiency, impact characteristics |

**Rationale:** SPY's structural dark pool percentage doesn't fundamentally change in a week. It takes regulatory changes, market structure shifts, or fundamental changes to alter these.

#### 🔄 DYNAMIC BASELINES (State-Dependent)

Updated: **Daily via rolling windows**

These are computed each day against the locked baseline:

| Metric | Description |
|--------|-------------|
| `dark_share_zscore` | Today's dark pool vs baseline |
| `block_intensity_zscore` | Block activity intensity vs baseline |
| `gex_zscore` | Today's GEX vs baseline |
| `dex_zscore` | Today's DEX vs baseline |
| `iv_zscore` | Today's IV vs baseline |
| `price_efficiency_zscore` | Today's efficiency vs baseline |

**Rationale:** These change daily based on market conditions. A z-score of +2 today means "this is unusual compared to what's normal for this instrument."

---

## Pipeline Integration

### Where Baselines are Computed

```
┌─────────────────────────────────────────────────────────────┐
│                    TICKER ONBOARDING                        │
├─────────────────────────────────────────────────────────────┤
│ 1. Fetch 63 days of historical data (dark pool, Greeks,     │
│    price context)                                           │
│ 2. Run BaselineCalculator.compute_baseline()                │
│ 3. Store via BaselineStorage.save()                         │
│ 4. Log baseline report for human review                     │
└─────────────────────────────────────────────────────────────┘
```

### Where Baselines are Applied

```
┌─────────────────────────────────────────────────────────────┐
│                    DAILY PIPELINE                           │
├─────────────────────────────────────────────────────────────┤
│ 1. Load baseline: BaselineStorage.load(ticker)              │
│    ↳ FAIL if no baseline exists (cannot proceed!)           │
│                                                             │
│ 2. Fetch today's raw features                               │
│                                                             │
│ 3. Compute z-scores against baseline:                       │
│    - dark_share_zscore = (today - baseline.mean) / std      │
│    - gex_zscore = (today - baseline.mean) / std             │
│    - etc.                                                   │
│                                                             │
│ 4. Use z-scores for:                                        │
│    - Regime classification thresholds                       │
│    - Unusualness score calculation                          │
│    - Explanation generation                                 │
└─────────────────────────────────────────────────────────────┘
```

### Critical Design Rule

```python
baseline = storage.load(ticker)
if baseline is None:
    raise BaselineNotFoundError(
        f"Cannot process {ticker} without baseline. "
        f"Run baseline computation first."
    )
```

**You cannot call something unusual without a baseline.**

---

## Baseline Checklist Table Schema

```json
{
  "ticker": "SPY",
  "baseline_date": "2024-01-15",
  "lookback_days": 63,
  "data_start_date": "2023-10-15",
  "data_end_date": "2024-01-15",
  "observation_count": 63,
  "missing_data_pct": 2.5,

  "dark_pool": {
    "dark_share": {
      "mean": 32.5,
      "std": 4.2,
      "median": 31.8,
      "p75": 35.2,
      "p90": 38.1,
      "n_observations": 63
    },
    "dark_share_typical_range": [26.2, 38.8],
    "daily_block_count": { ... },
    "block_size": { ... },
    "policy": "locked"
  },

  "greeks": {
    "gex": {
      "mean": -1250000,
      "std": 2800000,
      "mad": 1900000,
      "n_observations": 63
    },
    "gex_positive_pct": 42.0,
    "gex_negative_pct": 58.0,
    "dex": { ... },
    "iv_atm": { ... },
    "policy": "locked"
  },

  "price_efficiency": {
    "daily_range_pct": { ... },
    "price_efficiency": { ... },
    "policy": "locked"
  }
}
```

---

## Usage Examples

### Computing a New Baseline

```python
from obsidian.baseline import BaselineCalculator, BaselineStorage

# Load historical data
historical_df = load_historical_features("SPY", days=63)

# Compute baseline
calculator = BaselineCalculator(lookback_days=63)
baseline = calculator.compute_baseline("SPY", historical_df)

# Validate and store
if baseline.is_valid():
    storage = BaselineStorage()
    storage.save(baseline)
    print(f"Baseline saved for SPY")
else:
    print(f"Insufficient data quality for baseline")
```

### Using Baseline in Daily Pipeline

```python
from obsidian.baseline import BaselineStorage, BaselineCalculator

storage = BaselineStorage()
baseline = storage.load("SPY")

if baseline is None:
    raise ValueError("No baseline for SPY - run onboarding first!")

# Compute z-scores for today's features
calculator = BaselineCalculator()
dynamic_state = calculator.compute_dynamic_state(
    ticker="SPY",
    current_features=today_features,
    baseline=baseline,
    trade_date=today,
)

# Use z-scores for classification
if dynamic_state.gex_zscore > 1.5:
    # GEX is elevated relative to SPY's normal
    pass
```

### Checking Baseline Health

```python
storage = BaselineStorage()

for ticker in storage.list_tickers():
    baseline = storage.load(ticker)
    age = baseline.days_since_update(date.today())

    if baseline.needs_refresh(date.today()):
        print(f"{ticker}: Baseline is {age} days old - needs refresh")
```

---

## Summary

| Aspect | Design Decision | Rationale |
|--------|-----------------|-----------|
| **Reference** | Instrument-specific | Same value means different things for different instruments |
| **Storage** | JSON files | Human-readable, version-controllable |
| **Locked metrics** | Quarterly refresh | Structural properties don't change daily |
| **Dynamic metrics** | Daily computation | State deviations are computed fresh |
| **Minimum data** | 21 observations | Statistical significance requirement |
| **No ML** | Explicit rules only | Must be explainable |

**Core Principle:** OBSIDIAN measures deviation from normal, not absolute values, because "unusual" only has meaning relative to what's normal for that specific instrument.

---

## Incremental Feature History (Added 2026-02-04)

### The API Limitation Problem

The Unusual Whales API has different historical data availability:

| Data Type | Historical Availability |
|-----------|------------------------|
| Darkpool, GEX, DEX | ~30 days |
| **Vanna, Charm** | **~7 days only** |

Since baselines require MIN_OBSERVATIONS = 21, we cannot compute vanna/charm baselines from API alone.

### The Solution: Incremental Collection

The daily pipeline now saves raw features locally, including vanna/charm. After 21+ days of collection, baselines can be computed from local data.

```
Daily Pipeline Run → Save Features → Accumulate Data → Compute Baseline
     (Day 1)           (JSON file)     (21+ days)      (with vanna/charm!)
```

### Storage Location

```
data/processed/feature_history/
├── SPY/
│   ├── 2026-02-03.json
│   ├── 2026-02-04.json
│   └── ...
└── QQQ/
    └── ...
```

### Feature History Schema

```json
{
  "ticker": "SPY",
  "date": "2026-02-03",
  "features": {
    "dark_pool_volume": 31335708,
    "dark_pool_ratio": 29.04,
    "gex": -1602019.22,
    "dex": 28768137.54,
    "vanna": -564694389.44,
    "charm": 25589267.99,
    "price_change_pct": -0.96,
    ...
  },
  "saved_at": "2026-02-04"
}
```

### Usage Commands

```bash
# Check data collection status
python scripts/compute_baseline.py SPY --status

# Output:
# Status for SPY
# ==================================================
# Local Feature History:
#   Observations: 15
#   Date range: 2026-01-20 to 2026-02-03
#   Has vanna: ✓
#   Has charm: ✓
#   Status: Need 6 more days of data

# Compute baseline from local data only (enables vanna/charm!)
python scripts/compute_baseline.py SPY --local-only --force

# Normal baseline computation (local + API fallback)
python scripts/compute_baseline.py SPY --force
```

### Timeline to Vanna/Charm Baselines

| Day | Action |
|-----|--------|
| 0 | Start running daily pipeline |
| 1-20 | Accumulate feature history |
| 21+ | Run `--local-only` for vanna/charm baseline |

### Crontab Setup for Automated Collection

```bash
# Run daily at 5 PM EST on trading days
0 17 * * 1-5 cd /path/to/obsidian_mm && python scripts/run_daily.py SPY QQQ >> logs/daily.log 2>&1
```

### Key Files

| File | Purpose |
|------|---------|
| `obsidian/baseline/history.py` | `FeatureHistoryStorage` class |
| `obsidian/pipeline/daily.py` | Saves features via `_save_feature_history()` |
| `scripts/compute_baseline.py` | `--status`, `--local-only` flags |
