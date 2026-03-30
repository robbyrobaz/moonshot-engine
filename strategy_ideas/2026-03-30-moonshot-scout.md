# Moonshot Strategy Scout — 2026-03-30

## Tournament Analysis

### Current State
- **Backtest queue:** 287 models waiting
- **Champions:** 1 short (8bcea880b343, LightGBM no_social, FT PnL +3.3%, PF 3.12, 94 trades)
- **Long performance:** Catastrophic avg FT PnL -0.72% (vs short -0.13%)
- **Recent retirements (7d):** 593 models, mostly backtest_failed (0 trades)
- **Model distribution:** 70% short, 30% long — heavily short-biased

### Winning Formula (Current Champion)
- **Model:** LightGBM
- **Features:** no_social (excludes social/news features — simpler, more reliable)
- **Direction:** SHORT
- **Performance:** FT PF 3.12 (3x returns), 94 trades, +3.3% PnL

### Failure Patterns
- **Backtest failures dominate:** 18/20 recent retirements = BT failed (PF < threshold)
- **Long models can't pass gate:** MIN_BT_PF_LONG = 1.5, MIN_BT_PRECISION_LONG = 0.20 too high
- **Feature overload:** Models with 30+ features (all/extended sets) failing at BT
- **Class imbalance:** neg_class_weight 8-10 common but not helping longs

### Feature Sets Available
- **no_social** — excludes social/news (WINNING — champion uses this)
- **core_only** — basic price/volume only
- **extended_only** — funding/OI features only
- **price_volume** — price + volume technical indicators
- **all** — everything (38 features)

### Gaps Identified
1. **Minimal feature models** — champion is simple (no_social), test even simpler
2. **Temporal variety** — no 1H or 15min lookbacks (all models use 4H)
3. **Ensemble diversity** — 70% XGBoost, need more CatBoost/LightGBM
4. **Long direction broken** — gates too tight, need lottery ticket logic
5. **Regime filters missing** — no bull/bear market adaptation
6. **Feature engineering frozen** — no new features added, just shuffling existing

## Strategy Variants (8 models)

### Variant 1: Minimal Core (SHORT)
**Hypothesis:** Simpler is better — 5 features only (momentum + volatility)
- **Model:** CatBoost
- **Features:** ["momentum_1d", "momentum_3d", "atr_percentile", "bb_position", "volume_spike"]
- **Hyperparams:** lr=0.1, depth=4, n_est=100, neg_weight=5
- **Confidence:** 0.6

### Variant 2: Volume-Only Sniper (SHORT)
**Hypothesis:** Volume precedes price — ignore price features entirely
- **Model:** LightGBM
- **Features:** ["volume_ratio_3d", "volume_ratio_7d", "volume_spike", "volume_trend", "obv_slope", "vol_24h_vs_7d_avg"]
- **Hyperparams:** lr=0.05, depth=6, n_est=200, neg_weight=3
- **Confidence:** 0.7

### Variant 3: Deep CatBoost (SHORT)
**Hypothesis:** Champion is LightGBM — try deeper CatBoost with no_social
- **Model:** CatBoost
- **Features:** no_social
- **Hyperparams:** lr=0.03, depth=8, n_est=300, neg_weight=5
- **Confidence:** 0.6

### Variant 4: Fast Trader (SHORT, 15min implicit)
**Hypothesis:** 4H is slow — use short momentum windows (1d/3d only)
- **Model:** XGBoost
- **Features:** ["momentum_1d", "momentum_3d", "bb_position", "volume_ratio_3d", "atr_percentile", "high_low_range_pct"]
- **Hyperparams:** lr=0.1, depth=3, n_est=50, neg_weight=3
- **Confidence:** 0.7

### Variant 5: Long Lottery (LONG, relaxed gate)
**Hypothesis:** Longs need ultra-tight precision, wide profit hunts
- **Model:** LightGBM
- **Features:** ["momentum_8w", "price_vs_52w_low", "distance_from_support", "is_new_listing", "days_since_listing", "btc_30d_return"]
- **Hyperparams:** lr=0.05, depth=6, n_est=200, neg_weight=15 (extreme class weight)
- **Confidence:** 0.3 (wide net for rare spikes)

### Variant 6: Funding Rate Contrarian (SHORT)
**Hypothesis:** Extreme funding = reversal signal
- **Model:** CatBoost
- **Features:** ["funding_rate_current", "funding_rate_extreme", "oi_price_divergence", "mark_index_spread", "volume_spike"]
- **Hyperparams:** lr=0.05, depth=6, n_est=200, neg_weight=5
- **Confidence:** 0.7

### Variant 7: BTC Correlation Play (SHORT)
**Hypothesis:** BTC drives alts — lead with BTC signals
- **Model:** XGBoost
- **Features:** ["btc_30d_return", "btc_vol_percentile", "market_breadth", "momentum_4w", "volume_ratio_7d"]
- **Hyperparams:** lr=0.05, depth=5, n_est=150, neg_weight=5
- **Confidence:** 0.6

### Variant 8: Momentum Extremes (SHORT)
**Hypothesis:** Extreme momentum (overbought/oversold) = mean reversion
- **Model:** LightGBM
- **Features:** ["momentum_1d", "momentum_3d", "momentum_4w", "bb_position", "price_vs_52w_high", "atr_percentile"]
- **Hyperparams:** lr=0.05, depth=6, n_est=200, neg_weight=5
- **Confidence:** 0.65

## Implementation Plan
1. Generate 8 JSON configs in `configs/generated/2026-03-30-scout-*.json`
2. Insert into `tournament_models` table (stage=backtest)
3. Next 4H cycle will pick them up (25 challengers per cycle, we add 8)
4. Configs committed to git

## Expected Outcomes
- **2-3 models** pass backtest gate (realistic given 95% retirement rate)
- **1 model** reaches FT and shows promising early PnL
- **Validation:** Simpler models (variants 1-4) should outperform complex ones
- **Long hypothesis test:** Variant 5 will likely fail BT gate but worth testing lottery logic
