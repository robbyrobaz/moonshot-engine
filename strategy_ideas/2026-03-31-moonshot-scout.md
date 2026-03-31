# Moonshot Strategy Scout — 2026-03-31

## Tournament Analysis

### Current State (10:00 AM MST)
- **Backtest queue:** 431 models (207 long, 224 short)
- **Forward test:** 931 models (19 long, 912 short) — 98% short bias
- **Champions:** 1 short (8bcea880b343, LightGBM no_social, FT PF 3.12, 94 trades)
- **Position performance (7d):** 
  - Long: 992 positions, 26% win rate, -1.7% avg PnL (BROKEN)
  - Short: 995 positions, 66% win rate, +2.7% avg PnL (WORKING)

### Key Insights from Data Analysis

#### What's Working (FT models with 20+ trades)
1. **CatBoost dominance:** 3 models, 67% profitable, avg PF 1.39
2. **price_volume feature set:** 1 model, PF 1.99 (BEST among 50+ trade models)
3. **no_social feature set:** Champion uses this (simpler = better)

#### What's Failing
1. **LightGBM in FT:** 1 model, avg PF 0.19 (despite champion being LightGBM — overfitted?)
2. **XGBoost in FT:** 4 models, 0% profitable, avg PF 0.55
3. **Long direction:** 98% of FT models are short — long gate is too restrictive

#### Feature Set Performance (50+ trades, PF > 1.0)
- **price_volume:** 1 model, PF 1.99 ⭐ TOP PERFORMER
- **no_social:** 1 model (champion), PF 1.33

### Gaps & Opportunities

1. **CatBoost underutilized:** Only 3 FT models vs 100s of XGBoost/LightGBM — expand CatBoost variants
2. **price_volume feature set is GOLD:** Only 1 model uses it, but PF 1.99 — seed more variants here
3. **Short momentum features:** Champion uses momentum_4w/8w — test 1d/3d for faster signals
4. **Volatility compression:** atr_compression + bb_squeeze_pct combo untested
5. **Funding rate extremes:** funding_rate_extreme + oi_price_divergence = contrarian signals
6. **Volume-only models:** No pure volume models in top performers
7. **Long direction dead:** Need lottery ticket logic (high precision, low recall)
8. **Ensemble stacking:** No models test feature importance-based subsets

## Strategy Variants (8 models)

### Variant 1: CatBoost Price-Volume Champion (SHORT)
**Hypothesis:** CatBoost + price_volume = winning combo (PF 1.99 proven)
- **Model:** catboost
- **Features:** price_volume (["price_vs_52w_high", "price_vs_52w_low", "momentum_4w", "volume_ratio_7d", "volume_ratio_3d", "obv_slope", "volume_spike"])
- **Hyperparams:** 
  ```json
  {
    "learning_rate": 0.05,
    "depth": 6,
    "n_estimators": 250,
    "l2_leaf_reg": 5,
    "neg_class_weight": 4
  }
  ```
- **Entry threshold:** 0.55
- **Invalidation threshold:** 0.35
- **Confidence:** HIGH (proven feature set, proven model type)

### Variant 2: Fast Momentum CatBoost (SHORT)
**Hypothesis:** 1d/3d momentum for quicker entries (vs champion's 4w/8w)
- **Model:** catboost
- **Features:** ["momentum_1d", "momentum_3d", "bb_position", "volume_ratio_3d", "atr_percentile", "high_low_range_pct", "consec_down_bars"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.08,
    "depth": 5,
    "n_estimators": 200,
    "l2_leaf_reg": 3,
    "neg_class_weight": 5
  }
  ```
- **Entry threshold:** 0.60
- **Invalidation threshold:** 0.40
- **Confidence:** MEDIUM (new lookback windows)

### Variant 3: Volatility Compression Sniper (SHORT)
**Hypothesis:** Low vol precedes breakouts — squeeze + compression combo
- **Model:** catboost
- **Features:** ["bb_squeeze_pct", "atr_compression", "atr_percentile", "realized_vol_ratio", "high_low_range_pct", "momentum_1d", "volume_spike"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.06,
    "depth": 6,
    "n_estimators": 300,
    "l2_leaf_reg": 4,
    "neg_class_weight": 5
  }
  ```
- **Entry threshold:** 0.58
- **Invalidation threshold:** 0.38
- **Confidence:** MEDIUM (untested feature combo)

### Variant 4: Funding Rate Contrarian (SHORT)
**Hypothesis:** Extreme funding + OI divergence = reversal signals
- **Model:** catboost
- **Features:** ["funding_rate_current", "funding_rate_extreme", "oi_price_divergence", "oi_change_24h", "mark_index_spread", "volume_spike", "momentum_1d"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.05,
    "depth": 7,
    "n_estimators": 250,
    "l2_leaf_reg": 6,
    "neg_class_weight": 4
  }
  ```
- **Entry threshold:** 0.62
- **Invalidation threshold:** 0.42
- **Confidence:** MEDIUM (contrarian logic needs validation)

### Variant 5: Volume-Only Sniper (SHORT)
**Hypothesis:** Volume precedes price — test pure volume model
- **Model:** lightgbm
- **Features:** ["volume_ratio_3d", "volume_ratio_7d", "volume_spike", "volume_trend", "obv_slope", "vol_24h_vs_7d_avg"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.06,
    "max_depth": 6,
    "n_estimators": 200,
    "min_child_samples": 20,
    "neg_class_weight": 3
  }
  ```
- **Entry threshold:** 0.65
- **Invalidation threshold:** 0.45
- **Confidence:** LOW (no price features = risky)

### Variant 6: Minimal Core (SHORT)
**Hypothesis:** Simpler is better — 5 features only
- **Model:** catboost
- **Features:** ["momentum_1d", "atr_percentile", "bb_position", "volume_spike", "consec_down_bars"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.10,
    "depth": 4,
    "n_estimators": 150,
    "l2_leaf_reg": 2,
    "neg_class_weight": 5
  }
  ```
- **Entry threshold:** 0.55
- **Invalidation threshold:** 0.35
- **Confidence:** MEDIUM (champion is simple, test even simpler)

### Variant 7: BTC Regime Filter (SHORT)
**Hypothesis:** BTC drives alts — use BTC signals as regime filter
- **Model:** catboost
- **Features:** ["btc_30d_return", "btc_vol_percentile", "market_breadth", "momentum_4w", "volume_ratio_7d", "bb_position"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.05,
    "depth": 6,
    "n_estimators": 250,
    "l2_leaf_reg": 5,
    "neg_class_weight": 4
  }
  ```
- **Entry threshold:** 0.58
- **Invalidation threshold:** 0.38
- **Confidence:** MEDIUM (macro context untested)

### Variant 8: Deep Structure Hunter (SHORT)
**Hypothesis:** Price structure features (support/resistance) = edge
- **Model:** catboost
- **Features:** ["distance_from_resistance", "distance_from_support", "consec_down_bars", "consec_up_bars", "higher_highs", "momentum_4w", "bb_position"]
- **Hyperparams:**
  ```json
  {
    "learning_rate": 0.05,
    "depth": 7,
    "n_estimators": 300,
    "l2_leaf_reg": 5,
    "neg_class_weight": 4
  }
  ```
- **Entry threshold:** 0.60
- **Invalidation threshold:** 0.40
- **Confidence:** MEDIUM (support/resistance features underutilized)

## Implementation Plan

### Phase 1: Generate Configs
Create 8 JSON files in `configs/generated/2026-03-31/variant-{1..8}.json`:
```json
{
  "direction": "short",
  "model_type": "catboost|lightgbm",
  "feature_set": [...],
  "params": {...},
  "entry_threshold": 0.55-0.65,
  "invalidation_threshold": 0.35-0.45,
  "description": "..."
}
```

### Phase 2: Insert into Queue
Run seeding script:
```python
# Create insert_2026-03-31_scout_variants.py
# Adapted from insert_scout_variants.py template
# Insert 8 models into backtest queue (stage='backtest')
```

### Phase 3: Git Commit
```bash
cd /home/rob/.openclaw/workspace/blofin-moonshot-v2
git add configs/generated/2026-03-31/*.json
git add strategy_ideas/2026-03-31-moonshot-scout.md
git commit -m "Moonshot Scout: 8 variants (7 CatBoost, 1 LightGBM) — price_volume expansion"
```

### Phase 4: Validation
- Check backtest queue size increased by 8
- Verify JSON configs are valid (run validation script if exists)
- Confirm next 4H cycle will pick them up

## Expected Outcomes

### Success Metrics (7 days)
- **2-3 models pass BT gate** (realistic given 95% retirement rate)
- **1 model reaches champion** (beats current PF 3.12)
- **Validation:** Variant 1 (CatBoost price_volume) should reach FT with PF > 1.5

### Hypothesis Tests
1. **CatBoost superiority:** 7/8 variants are CatBoost — should outperform XGBoost/LightGBM
2. **price_volume dominance:** Variant 1 should replicate PF 1.99 performance
3. **Fast momentum:** Variant 2 (1d/3d) should have faster entry/exit vs champion (4w/8w)
4. **Simplicity wins:** Variant 6 (5 features) should pass BT despite minimal feature set

### Risk Mitigation
- **No long models:** Long direction is broken (98% short bias, -1.7% avg PnL) — skip longs until Rob fixes gates
- **Conservative thresholds:** Entry 0.55-0.65 (vs 0.50 floor) to avoid low-quality signals
- **CatBoost focus:** Proven FT performance (PF 1.39 avg) vs XGBoost (PF 0.55)
- **Feature set reuse:** 6/8 models use proven features from top performers

## Notes for Next Scout Run (2026-04-01)
- Monitor Variant 1 (CatBoost price_volume) — if PF > 2.0 in FT, seed 5 more variants with same feature set
- If any variant passes BT with PF > 3.0, extract feature importances and seed focused variants
- If all 8 variants fail BT, revisit neg_class_weight tuning (try 6-10 range)
