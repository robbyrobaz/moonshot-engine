# Moonshot Strategy Scout — 2026-04-04

## Tournament Analysis

**Current Champions:**
- 1 LightGBM short: PF 3.12, 71.3% win rate, $3.30 PnL (model 8bcea880b343)
- 1 rule-based new_listing: no trades yet

**Backtest Queue:** 669 models waiting
**Total Retired:** 3,171 models
- 3,019 failed backtest (95.2%)
- 81 retired for unprofitable FT (PF < 0.9 after 50 trades)
- 20 retired for low PF after 20 trades

**Model Distribution:**
- LightGBM: 237 backtest, 1 champion
- CatBoost: 220 backtest
- XGBoost: 212 backtest
- Balanced across types, no clear winner yet

## Identified Gaps

1. **Extended features underutilized**
   - Champion uses "no_social" feature set (core only)
   - 12 extended features available: funding rates, OI, mark prices, 24h tickers
   - Potential: funding rate extremes may predict reversals, OI divergence can signal tops

2. **Minimal feature sets untested**
   - Do we need 27 features or can 4-5 high-signal features work?
   - Simpler models = faster training, less overfitting risk
   - Test: pure momentum (4 features), pure volume (5 features)

3. **Regime-specific models missing**
   - atr_percentile can segment high-vol vs low-vol markets
   - High-vol (atr > 70): mean reversion opportunity
   - Low-vol (atr < 30): compression before breakout
   - Current models treat all regimes equally

4. **Hyperparameter exploration limited**
   - Most models: max_depth=4-5, n_estimators=100-150
   - Test extremes: deep trees (depth=8) vs shallow fast (depth=3)
   - CatBoost can handle depth=8 without overfitting (built-in regularization)

5. **Long models underrepresented**
   - Only 1 rule-based new_listing champion (0 ML longs)
   - Primary mission: hunt new coin spikes (TP=30%, NEW_LISTING_BOOST=5x)
   - Need longs optimized for: new_listing metadata, volume accumulation, support bounces

## Generated Variants (8 models)

### 1. Extended Features Short (ea5eefb0afb5)
- **Type:** LightGBM short, 24 features
- **Strategy:** Core features + funding rates + OI + mark prices + 24h tickers
- **Hypothesis:** Funding extremes and OI divergence predict tops better than price/volume alone
- **Features added:** funding_rate_current, funding_rate_7d_avg, funding_rate_extreme, oi_change_24h, oi_change_7d, oi_price_divergence, mark_index_spread, price_vs_24h_high, price_vs_24h_low, vol_24h_vs_7d_avg

### 2. Extended Features Long (9298c69ff7f0)
- **Type:** LightGBM long, 26 features
- **Strategy:** Extended features + new_listing metadata
- **Hypothesis:** Same as #1 but for longs, plus days_since_listing/is_new_listing for moonshot hunting
- **Target:** New coins showing accumulation + funding shifts

### 3. Minimal Momentum (be6bccb0924d)
- **Type:** XGBoost short, 4 features
- **Strategy:** momentum_1d, momentum_3d, momentum_4w, momentum_8w
- **Hypothesis:** Multi-timeframe momentum divergence alone predicts reversals
- **Test:** Can 4 simple signals beat 27-feature models?

### 4. Minimal Volume (b94dbcba5fd4)
- **Type:** XGBoost long, 5 features
- **Strategy:** volume_ratio_7d, volume_ratio_3d, obv_slope, volume_spike, volume_trend
- **Hypothesis:** Pure volume accumulation signals breakouts (volume leads price)
- **Target:** Coins with rising OBV + volume spikes before moonshots

### 5. High Volatility Regime (7d8522e267ab)
- **Type:** CatBoost short, 8 features
- **Strategy:** Volatility features (atr_percentile, atr_compression, realized_vol_ratio, high_low_range_pct, bb_squeeze) + momentum_1d + volume_spike + btc_vol_percentile
- **Hypothesis:** In high-vol regimes (atr > 70), extreme moves mean-revert
- **Target:** Parabolic runs that exhaust (short after +50% 1d move in high-vol environment)

### 6. Low Volatility Regime (8126ad86e2bb)
- **Type:** CatBoost long, 8 features
- **Strategy:** Compression features (atr_compression, bb_squeeze_pct) + volume accumulation + support bounce + new_listing
- **Hypothesis:** In low-vol regimes (atr < 30), compression + accumulation + support = breakout
- **Target:** Quiet coins building bases before explosive moves

### 7. Deep CatBoost (4e113d70f43d)
- **Type:** CatBoost short, 14 features, depth=8
- **Strategy:** Deeper trees to capture complex feature interactions
- **Hypothesis:** Current models (depth 4-5) miss non-linear patterns; depth=8 can find them
- **Risk:** Overfitting, but CatBoost's built-in regularization should manage it

### 8. Fast LightGBM (c65a548c3160)
- **Type:** LightGBM long, 10 features, depth=3, n_estimators=50, lr=0.05
- **Strategy:** Shallow simple model optimized for speed
- **Hypothesis:** Simple patterns (support bounce + volume + new listing) don't need deep trees
- **Benefit:** 3x faster training than standard models

## Expected Outcomes

**Success Metrics:**
- Backtest PF > 1.5 (long) or PF > 0.6 (short)
- Backtest trades ≥ 30
- Bootstrap CI lower bound > 0.7 (long) or > 0.5 (short)

**Predictions:**
1. **Extended features (1, 2):** 40% chance of FT promotion
   - If funding/OI signals work, could beat champion
   - Risk: Too many features = overfitting on backtest

2. **Minimal models (3, 4):** 20% chance of FT promotion
   - High risk: too simple may underfit
   - High reward: if they work, incredibly robust (4-5 features can't overfit much)

3. **Regime models (5, 6):** 50% chance of FT promotion
   - Strong hypothesis: volatility regimes are real
   - May fail if regime shifts mid-trade (atr_percentile changes)

4. **Hyperparameter variants (7, 8):** 30% chance of FT promotion
   - Deep CatBoost: may find complex patterns or overfit
   - Fast LightGBM: may work if new listing signals are simple

**Tournament Philosophy Reminder:**
- 95% retirement rate is GOOD
- We only need 1-2 winners from 8 variants
- Failed models teach us what doesn't work (equally valuable)

## Next Steps

1. ✅ Generated 8 configs (configs/generated/2026-04-04/variant-*.json)
2. ✅ Inserted into tournament_models table (stage='backtest_queue')
3. ⏳ Next 4h cycle will backtest (run_cycle.py auto-picks stage='backtest_queue')
4. ⏳ Monitor backtest results in dashboard (http://127.0.0.1:8893)
5. ⏳ Successful models (pass gates) auto-promote to FT within 1-2 cycles
6. ⏳ Review FT performance after 50-150 trades

**Timeline:**
- First backtest results: within 4 hours
- FT promotion (if any pass gates): 4-8 hours
- FT evaluation (50 trades): 2-7 days depending on signal frequency

## Model IDs

| Model ID     | Direction | Type     | Features | Description                    |
|--------------|-----------|----------|----------|--------------------------------|
| ea5eefb0afb5 | short     | lightgbm | 24       | Extended Features Short        |
| 9298c69ff7f0 | long      | lightgbm | 26       | Extended Features Long         |
| be6bccb0924d | short     | xgboost  | 4        | Minimal Momentum               |
| b94dbcba5fd4 | long      | xgboost  | 5        | Minimal Volume                 |
| 7d8522e267ab | short     | catboost | 8        | High Volatility Regime         |
| 8126ad86e2bb | long      | catboost | 8        | Low Volatility Regime          |
| 4e113d70f43d | short     | catboost | 14       | Deep CatBoost                  |
| c65a548c3160 | long      | lightgbm | 10       | Fast LightGBM                  |

---

**Scout Run:** 2026-04-04 10:08 AM MST
**Backtest Queue Before:** 669 models
**Backtest Queue After:** 677 models (+8)
**Status:** ✅ Complete — variants ready for tournament cycle
