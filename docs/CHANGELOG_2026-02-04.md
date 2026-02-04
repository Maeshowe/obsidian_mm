# OBSIDIAN MM - Change Log 2026-02-04

## Summary

This update:
1. Fixes critical API integration issues
2. Introduces the Baseline System for instrument-specific normalization
3. Implements Operational Guardrails for system integrity

---

## 1. API Integration Fixes

### 1.1 Greek Exposure (GEX/DEX) - FIXED

**Problem:** GEX and DEX values were always 0.

**Root Cause:** The Unusual Whales API returns separate components (`call_gamma`, `put_gamma`, `call_delta`, `put_delta`) instead of pre-calculated net values.

**Solution:** Calculate net exposure from components.

**File:** `obsidian/ingest/unusual_whales.py`

```python
# Before (incorrect)
gex = self._safe_float(exposure.get("gex"))  # Always None

# After (correct)
call_gamma = self._safe_float(exposure.get("call_gamma"))
put_gamma = self._safe_float(exposure.get("put_gamma"))
gex = call_gamma + put_gamma  # Net gamma exposure

call_delta = self._safe_float(exposure.get("call_delta"))
put_delta = self._safe_float(exposure.get("put_delta"))
dex = call_delta + put_delta  # Net delta exposure
```

---

### 1.2 IV Term Structure - FIXED

**Problem:** IV term structure data was always empty.

**Root Cause:** Wrong API endpoint path.

**Solution:** Use correct endpoint.

**File:** `obsidian/ingest/unusual_whales.py`

```python
# Before (incorrect)
endpoint = f"/stock/{ticker}/iv-term-structure"

# After (correct)
endpoint = f"/stock/{ticker}/volatility/term-structure"
```

---

### 1.3 VWAP Data - FIXED

**Problem:** VWAP was always None.

**Root Cause:** Polygon v1 open-close endpoint doesn't reliably return VWAP.

**Solution:** Use v2 aggregates endpoint.

**File:** `obsidian/ingest/polygon.py`

```python
# Before (v1 endpoint)
endpoint = f"/v1/open-close/{ticker}/{date_str}"

# After (v2 aggregates)
endpoint = f"/v2/aggs/ticker/{ticker}/range/1/day/{date_str}/{date_str}"
```

---

### 1.4 Dark Pool Pagination - FIXED

**Problem:** Dark pool ratio was extremely low (1.36% instead of ~30%).

**Root Cause:** API has 500 trade limit per request. SPY has 40,000+ trades/day.

**Solution:** Implement pagination using `older_than` parameter.

**File:** `obsidian/ingest/unusual_whales.py`

```python
async def get_darkpool_trades(self, ticker: str, trade_date: date) -> list[dict]:
    """Fetch ALL dark pool trades with pagination."""
    all_trades = []
    older_than = None

    while True:
        params = {"date": trade_date.isoformat(), "limit": 500}
        if older_than:
            params["older_than"] = older_than

        response = await self._get(endpoint, params)
        trades = response.get("data", [])

        if not trades:
            break

        all_trades.extend(trades)
        older_than = trades[-1].get("executed_at")

        if len(trades) < 500:
            break

    return all_trades
```

**Result:** SPY now correctly shows ~30% dark pool ratio (49,000+ trades captured).

---

## 2. Baseline System - NEW

### 2.1 Core Concept

> "You cannot call something unusual without knowing what normal is."

The baseline system establishes instrument-specific "normal" levels for all features. Z-scores are computed against these locked baselines, not universal values.

### 2.2 New Files

| File | Purpose |
|------|---------|
| `obsidian/baseline/__init__.py` | Module exports |
| `obsidian/baseline/types.py` | `DistributionStats`, `TickerBaseline`, baseline component types |
| `obsidian/baseline/calculator.py` | `BaselineCalculator` - computes baselines from historical data |
| `obsidian/baseline/storage.py` | JSON storage, `format_baseline_report()` |
| `scripts/compute_baseline.py` | CLI for baseline computation |
| `docs/BASELINE_SYSTEM.md` | Full documentation |

### 2.3 Baseline Components

```
TickerBaseline
├── dark_pool: DarkPoolBaseline
│   ├── dark_share (DistributionStats)
│   ├── daily_block_count (DistributionStats)
│   ├── block_size (DistributionStats)
│   ├── block_premium (DistributionStats)
│   └── venue_shift (DistributionStats)
├── greeks: GreeksBaseline
│   ├── gex (DistributionStats)
│   ├── dex (DistributionStats)
│   ├── vanna, charm (DistributionStats | None)
│   └── iv_atm, iv_skew, iv_rank (DistributionStats | None)
└── price_efficiency: PriceEfficiencyBaseline
    ├── daily_range_pct (DistributionStats)
    ├── price_efficiency (DistributionStats)
    └── impact_per_volume (DistributionStats)
```

### 2.4 DistributionStats

Each feature's distribution is captured with:
- `mean`, `std` - for z-score calculation
- `median`, `mad` - robust statistics
- `p25`, `p75`, `p90`, `p95` - percentiles
- `min_val`, `max_val` - range
- `n_observations` - sample size

### 2.5 Usage

```bash
# Compute baseline (required before daily processing)
python scripts/compute_baseline.py SPY --days 63 --verbose

# Baselines stored in: data/baselines/{TICKER}.json
```

### 2.6 Pipeline Integration

**File:** `obsidian/pipeline/daily.py`

```python
class DailyPipeline:
    def __init__(self, require_baseline: bool = False):
        self.baseline_storage = BaselineStorage(base_dir=...)

    async def run(self, ticker: str, trade_date: date):
        # Step 1: Load baseline
        baseline = self._load_baseline(ticker)

        # Step 4: Normalize with baseline
        normalization = NormalizationPipeline(baseline=baseline)
        features = normalization.normalize(features)
```

**File:** `obsidian/normalization/pipeline.py`

```python
class NormalizationPipeline:
    def __init__(self, baseline: TickerBaseline | None = None):
        self.baseline = baseline

    def _normalize_feature(self, feature: str, value: float):
        if self.baseline is not None:
            stats = self._get_baseline_stats(feature)
            return zscore_normalize(value, stats.mean, stats.std)
        # Fallback to rolling window
```

---

## 3. Updated Documentation

### 3.1 CLAUDE.md Updates

- Added Baseline System section
- Added regime classification rules (priority order)
- Added key files reference
- Updated commands with `compute_baseline.py`

### 3.2 New: docs/BASELINE_SYSTEM.md

Comprehensive documentation covering:
- Philosophy ("deviation from normal, not absolute values")
- Baseline checklist schema
- Locked vs Dynamic classification
- Pipeline integration
- Refresh policy

---

## 4. Verification Results

### SPY Baseline (30 days)

| Category | Metric | Value |
|----------|--------|-------|
| Dark Pool Share | Mean ± Std | 8.3% ± 15.9% |
| Block Trades | Daily Count | 0-137 |
| GEX | Mean | -386,694 |
| DEX | Mean | 6,944,033 |
| Daily Range | Mean | 3.88% |
| Impact/Volume | Mean | 0.0047 |

Baseline saved: `data/baselines/SPY.json`

---

## 5. Breaking Changes

None. The baseline system is opt-in:
- `require_baseline=False` (default): Falls back to rolling window
- `require_baseline=True`: Enforces baseline existence

---

## 6. Migration Guide

1. Compute baselines for existing tickers:
   ```bash
   python scripts/compute_baseline.py SPY QQQ AAPL --days 63
   ```

2. (Optional) Enable strict baseline mode:
   ```python
   pipeline = DailyPipeline(require_baseline=True)
   ```

3. Schedule quarterly baseline refresh (recommended 63 trading days lookback).

---

## 7. Operational Guardrails - NEW

### 7.1 Purpose

Ensure the system remains:
- Diagnostic (not predictive)
- Stable across regimes
- Honest under incomplete data
- Resistant to silent drift
- Interpretable by humans

### 7.2 New Files

| File | Purpose |
|------|---------|
| `obsidian/guardrails/__init__.py` | Module exports |
| `obsidian/guardrails/types.py` | `InstrumentType`, `DataCompleteness`, `GuardrailViolation` |
| `obsidian/guardrails/conventions.py` | Greeks sign convention (SINGLE SOURCE OF TRUTH) |
| `obsidian/guardrails/validators.py` | Validation functions for all guardrails |
| `docs/GUARDRAILS.md` | Full documentation |

### 7.3 Guardrails Implemented

| # | Guardrail | Purpose |
|---|-----------|---------|
| 1 | Baseline Drift Detection | Log warning if baseline metrics change > 15% |
| 2 | Incomplete Data Handling | UNDETERMINED regime when critical data missing |
| 3 | Instrument Type Separation | No cross-type normalization (stock vs index_etf) |
| 4 | Greeks Sign Convention Lock | Centralized sign definition, prevents silent inversion |
| 5 | Z-Score vs Percentile Discipline | Z-scores for classification, percentiles for scoring |
| 6 | Regime Priority Short-Circuit | First match wins, exactly one regime |

### 7.4 Key Changes

**RegimeLabel Enum** - Added `UNDETERMINED`:
```python
class RegimeLabel(str, Enum):
    # ... existing labels ...
    UNDETERMINED = "Undetermined"  # Assigned when data insufficient
```

**RegimeClassifier** - Data completeness check:
```python
def classify(self, features, ticker, trade_date):
    # GUARDRAIL: Check for incomplete data
    missing = self._check_data_completeness(features)
    if missing:
        return RegimeResult(label=RegimeLabel.UNDETERMINED, ...)
```

**Greeks Sign Convention**:
```python
from obsidian.guardrails.conventions import GREEKS_SIGN_CONVENTION

# Positive GEX = dealers long gamma = stabilizing
# Negative GEX = dealers short gamma = destabilizing
```

### 7.5 Final Rule

> When any ambiguity arises:
> - Default to NOT labeling
> - Default to UNDETERMINED
> - Default to doing less
>
> **False negatives are acceptable. False confidence is not.**

---

## 8. Incremental Feature History - NEW (Session 2)

### 8.1 The Problem

The Unusual Whales API has different historical data limits:
- **Darkpool, GEX, DEX**: ~30 days available
- **Vanna, Charm**: Only ~7 days available

Since baselines require MIN_OBSERVATIONS = 21, we cannot compute vanna/charm baselines from API alone.

### 8.2 The Solution

Implemented incremental feature collection via daily pipeline runs.

**New File:** `obsidian/baseline/history.py`

```python
class FeatureHistoryStorage:
    """Stores daily feature snapshots for incremental baseline computation."""

    def save(self, ticker: str, trade_date: date, features: dict) -> bool
    def load(self, ticker: str, trade_date: date) -> dict | None
    def load_dataframe(self, ticker: str, min_days: int = 0) -> pd.DataFrame
    def get_summary(self, ticker: str) -> dict
    def list_dates(self, ticker: str) -> list[date]
```

### 8.3 Pipeline Integration

**File:** `obsidian/pipeline/daily.py`

The daily pipeline now automatically saves raw features:

```python
def _save_feature_history(self, ticker, trade_date, features, raw_data):
    """Save raw features including vanna/charm for future baseline."""
    feature_record = {
        "dark_pool_volume": features.dark_pool_volume,
        "gex": features.gex,
        "dex": features.dex,
        "vanna": greek_data.get("vanna"),  # Captured daily!
        "charm": greek_data.get("charm"),  # Captured daily!
        ...
    }
    self.feature_history.save(ticker, trade_date, feature_record)
```

### 8.4 Updated compute_baseline.py

**New Options:**
- `--status`: Check data availability without computing
- `--local-only`: Use only local feature history (no API calls)

**Strategy:**
1. Check local feature history first
2. If sufficient data (≥21 days), use local data (enables vanna/charm!)
3. If not enough local data, supplement with API

```bash
# Check status
python scripts/compute_baseline.py SPY --status

# Output:
# Local Feature History:
#   Observations: 1
#   Has vanna: ✓
#   Has charm: ✓
#   Status: Need 20 more days of data

# Compute with local data only
python scripts/compute_baseline.py SPY --local-only --force
```

### 8.5 Storage Structure

```
data/processed/feature_history/
├── SPY/
│   ├── 2026-02-03.json
│   ├── 2026-02-04.json
│   └── ...
└── QQQ/
    └── ...
```

### 8.6 Timeline

| Day | What Happens |
|-----|--------------|
| 0 | Start daily pipeline runs |
| 1-20 | Accumulate feature history with vanna/charm |
| 21+ | `--local-only` baseline includes vanna/charm |
| 63+ | Full 63-day baseline from local data |

---

## 9. Dashboard Fixes (Session 2)

### 9.1 Z-Score Display Fixed

**Problem:** Z-scores showed 0.00 even with valid baseline.

**Root Cause:** Parquet file created before baseline path fix.

**Solution:** Re-run pipeline after ensuring correct baseline path.

### 9.2 Percentile Features Added

**Problem:** Dashboard only showed z-score features, missing percentile-normalized features.

**Solution:** Added percentile feature display with pseudo z-score conversion.

**File:** `obsidian/dashboard/app.py`

```python
def render_feature_bars(features: dict) -> go.Figure:
    # Z-score features
    zscore_features = {k: v for k, v in features.items() if k.endswith("_zscore")}

    # Percentile features (convert to pseudo z-score)
    for k, v in features.items():
        if k.endswith("_pct"):
            pseudo_z = (v - 50) / 25  # 50th pct = 0, 97.5th = +2
            pct_features[f"{name} (pct)"] = pseudo_z
```

### 9.3 Score Drivers Fixed

**Problem:** Top Score Drivers showed 0% contribution.

**Root Cause:** `UnusualnessEngine` looked for `dark_pool_ratio_zscore` but data had `dark_pool_ratio_pct`.

**Solution:** Added percentile fallback in score components.

**File:** `obsidian/scoring/unusualness.py`

```python
SCORE_COMPONENTS = [
    {
        "name": "dark_pool_activity",
        "zscore_col": "dark_pool_ratio_zscore",
        "pct_col": "dark_pool_ratio_pct",  # Fallback
    },
    ...
]

def _percentile_to_zscore(pct: float) -> float:
    """Convert percentile (0-100) to pseudo z-score."""
    return (pct - 50) / 25
```

### 9.4 Baseline-Aware Messaging

**Problem:** Dashboard showed confusing warning when baseline existed but z-scores were 0.

**Solution:** Check baseline existence and show appropriate message.

```python
if not has_meaningful_zscores:
    if baseline_info and baseline_info.get("exists"):
        st.info("Z-scores near zero = metrics close to baseline mean")
    else:
        st.warning("No baseline found. Run compute_baseline.py first.")
```

---

## 10. dark_pool_volume Baseline Support (Session 2)

### 10.1 Type Addition

**File:** `obsidian/baseline/types.py`

```python
@dataclass(frozen=True)
class DarkPoolBaseline:
    dark_share: DistributionStats
    dark_share_typical_range: tuple[float, float]
    daily_block_count: DistributionStats
    block_size: DistributionStats
    block_premium: DistributionStats
    venue_shift: DistributionStats
    dark_volume: DistributionStats | None = None  # NEW
    policy: BaselineUpdatePolicy = BaselineUpdatePolicy.LOCKED
```

### 10.2 Calculator Update

**File:** `obsidian/baseline/calculator.py`

```python
def _compute_dark_pool_baseline(self, df):
    # Dark pool volume (absolute)
    dark_volume = None
    if "dark_pool_volume" in df.columns:
        dark_volume = compute_distribution_stats(
            df["dark_pool_volume"].dropna().tolist(),
            remove_outliers=True
        )

    return DarkPoolBaseline(..., dark_volume=dark_volume)
```

### 10.3 Storage Serialization

**File:** `obsidian/baseline/storage.py`

```python
def _serialize_dark_pool(self, dp):
    return {
        ...,
        "dark_volume": self._serialize_distribution(dp.dark_volume),
    }

def _deserialize_dark_pool(self, data):
    return DarkPoolBaseline(
        ...,
        dark_volume=self._deserialize_distribution(data.get("dark_volume")),
    )
```

### 10.4 Normalization Mapping

**File:** `obsidian/normalization/pipeline.py`

```python
mapping = {
    "dark_pool_ratio": self.baseline.dark_pool.dark_share,
    "dark_pool_volume": self.baseline.dark_pool.dark_volume,  # NEW
    ...
}
```

---

## Summary of Session 2 Changes

| Category | Change |
|----------|--------|
| **Feature History** | New `FeatureHistoryStorage` for incremental data collection |
| **Vanna/Charm** | Will be available in baselines after 21+ days of collection |
| **compute_baseline.py** | New `--status` and `--local-only` flags |
| **Dashboard** | Fixed z-scores, added percentiles, baseline-aware messages |
| **Scoring** | Percentile fallback in `UnusualnessEngine` |
| **dark_pool_volume** | Added to baseline types, calculator, storage, normalization |

**Next Steps:**
1. Set up crontab for daily pipeline execution
2. After 21 days: `python scripts/compute_baseline.py SPY --local-only --force`
3. Vanna/charm will be included in baseline
