# OBSIDIAN MM Operational Guardrails

## Why OBSIDIAN Refuses to Guess

> "False negatives are acceptable. False confidence is not."

OBSIDIAN is a **diagnostic system**. It observes and describes market microstructure states. It does NOT:
- Predict future price movements
- Recommend trades or entries
- Backtest or optimize parameters
- Use machine learning

When facing ambiguity, OBSIDIAN defaults to:
- **NOT labeling** (UNDETERMINED)
- **Doing less** rather than more
- **Explicit uncertainty** rather than hidden assumptions

---

## Guardrail Summary

| # | Guardrail | Purpose | Location |
|---|-----------|---------|----------|
| 1 | Baseline Drift Detection | Prevent silent invalidation of "normal" | `guardrails/validators.py` |
| 2 | Incomplete Data Handling | Explicit uncertainty, no guessing | `regimes/classifier.py` |
| 3 | Instrument Type Separation | Prevent meaningless cross-type comparison | `guardrails/types.py` |
| 4 | Greeks Sign Convention Lock | Prevent silent regime inversion | `guardrails/conventions.py` |
| 5 | Z-Score vs Percentile Discipline | Preserve statistical meaning | `guardrails/validators.py` |
| 6 | Regime Priority Short-Circuit | One day = one state | `regimes/classifier.py` |
| 7 | Explainability Standards | Human-readable outputs | `explain/generator.py` |
| 8 | Dashboard Visual Discipline | Diagnostics > aesthetics | `dashboard/` |
| 9 | Scope Enforcement | Prevent feature creep | Documentation |
| 10 | Psychological Guardrail | Descriptive, not actionable | All outputs |

---

## Guardrail 1: Baseline Drift Detection

### Purpose
Baselines define "normal". If baselines drift silently, unusualness calculations become meaningless.

### Implementation

```python
from obsidian.guardrails import check_baseline_drift

warnings = check_baseline_drift(
    old_baseline=previous_baseline_dict,
    new_baseline=new_baseline_dict,
    threshold_pct=15.0  # Configurable
)

for warning in warnings:
    logger.warning(str(warning))
    # Output: BASELINE_DRIFT_WARNING: SPY Dark Pool Share Mean increased by 18.5% (threshold: 15%)
```

### Threshold
Default: 15% change triggers warning. This is configurable but should not be silent.

### Behavior
- **Logged**: All drift warnings are logged
- **Not Blocking**: Processing continues but operator is alerted
- **Reviewable**: Drift history can be tracked

---

## Guardrail 2: Incomplete Data Handling

### Purpose
When required data is missing, OBSIDIAN must be honest about uncertainty.

### Rules

❌ **NEVER:**
- Fill missing values with zeros
- Interpolate from adjacent days
- Use averages or defaults
- Guess

✅ **ALWAYS:**
- Set regime = `UNDETERMINED`
- Set unusualness score = `NaN`
- Record reason in logs
- Explain in output

### Implementation

```python
# In RegimeClassifier.classify()
missing = self._check_data_completeness(features)
if missing:
    return RegimeResult(
        label=RegimeLabel.UNDETERMINED,
        confidence=0.0,
        explanation="Critical data missing: gex_zscore, dex_zscore. "
                    "OBSIDIAN refuses to guess."
    )
```

### Required Features

**Minimum (will cause UNDETERMINED if missing):**
- `gex_zscore`
- `dex_zscore`

**Secondary (logged warning, reduced confidence):**
- `dark_pool_ratio`
- `block_trade_count`
- `price_change_pct`

---

## Guardrail 3: Instrument Type Separation

### Purpose
Different instrument types have fundamentally different structural properties. Mixing them destroys meaning.

### Types

| Type | Examples | Characteristics |
|------|----------|-----------------|
| `STOCK` | AAPL, TSLA, NVDA | Single issuer, earnings events |
| `INDEX_ETF` | SPY, QQQ, IWM | Basket, continuous hedging |

### Rules

1. Baselines are computed per-ticker
2. Cross-type normalization is an error
3. Index ETFs have their own "normal"

### Implementation

```python
from obsidian.guardrails import InstrumentType, validate_instrument_type

# Get instrument type
inst_type = InstrumentType.from_ticker("SPY")  # Returns INDEX_ETF

# Validate against baseline
current_type, violation = validate_instrument_type(
    ticker="SPY",
    baseline_instrument_type=baseline.instrument_type
)

if violation:
    raise ValueError(violation.message)
```

---

## Guardrail 4: Greeks Sign Convention Lock

### Purpose
A flipped sign silently inverts all regime classifications.

### OBSIDIAN Convention (Dealer Perspective)

| Greek | Positive | Negative |
|-------|----------|----------|
| **GEX** | Dealers long gamma → stabilizing, vol suppression | Dealers short gamma → destabilizing, vol amplification |
| **DEX** | Dealers long delta → net long directional | Dealers short delta → net short directional |
| **Vanna** | Delta increases with vol | Delta decreases with vol |
| **Charm** | Delta increases with time | Delta decreases with time |

### Implementation

```python
from obsidian.guardrails.conventions import (
    GREEKS_SIGN_CONVENTION,
    normalize_greek_sign,
    GreeksSource,
)

# Normalize from source to OBSIDIAN convention
normalized_gex = normalize_greek_sign(
    value=raw_gex,
    greek="gex",
    source=GreeksSource.UNUSUAL_WHALES
)
```

### Single Source of Truth

`obsidian/guardrails/conventions.py` is the ONLY place where sign conventions are defined.

---

## Guardrail 5: Z-Score vs Percentile Discipline

### Purpose
Z-scores and percentiles have different statistical meanings. Mixing them destroys interpretability.

### Rules

| Metric Type | Use In | Example |
|-------------|--------|---------|
| **Z-Score** | Regime classification | `if gex_zscore > 1.5: regime = GAMMA_POSITIVE` |
| **Percentile** | Unusualness score (0-100) | `score = weighted_avg(percentiles)` |
| **Percentile** | Dashboard visualization | Charts, gauges |

### Enforcement

```python
from obsidian.guardrails import validate_zscore_usage

# This would return a warning
violation = validate_zscore_usage(
    feature_name="gex_zscore",
    context="scoring"  # Should use percentile for scoring
)
```

---

## Guardrail 6: Regime Priority Short-Circuit

### Purpose
One day = one state. No secondary labels, no ambiguity.

### Priority Order

```
1. Gamma+ Control       (priority: 1)
2. Gamma- Vacuum        (priority: 2)
3. Dark-Dominant        (priority: 3)
4. Absorption-like      (priority: 4)
5. Distribution-like    (priority: 5)
6. Neutral              (priority: 99)
7. UNDETERMINED         (priority: 100 - never matched by rules)
```

### Behavior

1. Rules evaluated in priority order
2. **FIRST MATCH WINS**
3. Evaluation stops immediately
4. No "also matches" or secondary labels
5. Exactly one regime per day (or UNDETERMINED)

### Implementation

```python
# In RegimeClassifier.classify()
for rule in self.rules:  # Sorted by priority
    if rule.check(features):
        return RegimeResult(label=rule.label, ...)  # STOP HERE
```

---

## Guardrail 7: Explainability Standards

### Purpose
Humans reason in language, not vectors.

### Rules

❌ **NOT:**
```
gex_zscore: 2.34, dex_zscore: -0.87, dark_pool_ratio: 45.2
```

✅ **MUST:**
```
Dealer gamma was extremely positive (2.3σ above normal) while price efficiency
remained low, indicating volatility suppression. Expect price pinning near
major option strikes.
```

### Requirements

- Human-readable sentences
- Describe WHY regime was assigned
- Reference top 2-3 drivers
- Use plain language

---

## Guardrail 8: Dashboard Visual Discipline

### Purpose
Diagnostics > aesthetics. Every visual element must earn its place.

### Rules

| Rule | Rationale |
|------|-----------|
| Max 5 visual elements per page | Cognitive load |
| Each element answers ONE question | Clarity |
| No indicator stacking | Reduces confusion |
| No decorative charts | Information density |

### Recommended Pages

1. **Daily State**: Current regime + score
2. **Historical Regimes**: Regime timeline
3. **Drivers & Contributors**: What moved today

---

## Guardrail 9: Scope Enforcement

### Purpose
Discipline preserves system integrity.

### Explicitly Rejected

- New features (unless approved)
- New signals
- Predictive logic
- Backtesting
- ML or optimization
- "Enhancements" not specified

### Response to Scope Creep

> "Out of scope. Implement as specified."

---

## Guardrail 10: Psychological Guardrail

### Purpose
OBSIDIAN observes. It does not act.

### Rules

❌ **NEVER imply:**
- Entry points
- Direction (bullish/bearish)
- Trade ideas
- Timing recommendations

✅ **ALWAYS remain:**
- Descriptive
- Observational
- Neutral
- Diagnostic

### Language Examples

| ❌ Bad | ✅ Good |
|--------|--------|
| "This is bullish" | "Dealers are long gamma" |
| "Consider buying" | "Volatility is suppressed" |
| "Expect price increase" | "Dark pool activity elevated" |

---

## Error Handling Summary

| Situation | Action | Regime | Score |
|-----------|--------|--------|-------|
| Missing critical data | Log + UNDETERMINED | `UNDETERMINED` | `NaN` |
| Missing secondary data | Log + reduce confidence | Continue | Partial |
| Baseline drift > threshold | Log warning | Continue | Continue |
| Sign convention error | Raise error | Block | Block |
| Instrument type mismatch | Raise error | Block | Block |

---

## Logging Standards

```
# Critical - blocks processing
[ERROR] INSTRUMENT_TYPE_MISMATCH: SPY baseline is stock, current is index_etf

# Warning - continues with caution
[WARNING] BASELINE_DRIFT_WARNING: SPY Dark Pool Share Mean increased by 18.5%
[WARNING] INCOMPLETE_DATA: SPY 2024-01-15 missing: gex_zscore. Regime = UNDETERMINED

# Info - operational notes
[INFO] PARTIAL_DATA: SPY 2024-01-15 missing secondary: block_trade_count
```

---

## Final Rule

> When any ambiguity arises:
> - Default to NOT labeling
> - Default to UNDETERMINED
> - Default to doing less
>
> **False negatives are acceptable. False confidence is not.**
