# 2026-04-05 Moonshot Strategy Scout

## Tournament Status Analysis

**Current Champions:**
- **SHORT:** 8bcea880b343 (LightGBM, no_social features, FT PnL: +3.30, PF: 3.12, 94 trades, 71.3% WR)
- **LONG:** None (vacancy — major opportunity gap)
- **NEW_LISTING:** Rule-based placeholder (0 performance)

**Backtest Queue:** 729 models waiting

**Recent Retirement Patterns (last 7 days):**
- 2,079 LONG models failed backtest
- 968 SHORT models failed backtest
- FT failures: mostly PF <0.9 or <1.3 thresholds

**Champion Profile (8bcea880b343):**
- Conservative: LR 0.01, depth 4, neg_class_weight 8
- Feature set: no_social (37 core+extended features)
- Entry threshold: 0.4
- Model type: LightGBM

## Gap Analysis

**Critical Gaps:**
1. **LONG direction completely vacant** — 2,000+ failed backtests suggest wrong feature combinations or hyperparameters
2. **NEW_LISTING has no ML model** — rule-based placeholder only
3. **Feature exploration underutilized:**
   - Volume-heavy subsets (10 volume/OI features)
   - Volatility squeeze patterns (compression breakout signals)
   - Regime-aware minimal sets (BTC correlation)
   - Ultra-minimal (5 features) vs current champion's 37

**Underexplored Hyperparameters:**
- Aggressive LR (0.08-0.1) vs champion's 0.01
- Deep trees (8-10) vs champion's 4
- Lower neg_class_weight (3-5) vs champion's 8
- XGBoost/CatBoost vs LightGBM dominance

## Generated Variants (8 models)

### LONG Direction (4 models — filling vacancy)

**1. variant-01-long-minimal-regime (1331328908d0)**
- **Model:** CatBoost, 10 features
- **Hypothesis:** BTC correlation signals drive LONG entries better than coin-specific features
- **Features:** price_vs_52w_high, momentum_4w, btc_30d_return, btc_vol_percentile, market_breadth, volume_spike, obv_slope, atr_percentile, bb_position, days_since_listing
- **Params:** LR 0.05, depth 5, n_est 200, neg_weight 5
- **Entry:** 0.45, Invalidation: 0.25

**2. variant-02-long-aggressive-price (3a04d642a4df)**
- **Model:** XGBoost, 12 features
- **Hypothesis:** Oversold bounce signals require aggressive hyperparameters (deep trees, high LR)
- **Features:** price_vs_52w_low, momentum_8w, bb_squeeze_pct, distance_from_support, consec_down_bars, volume_ratio_7d, atr_compression, realized_vol_ratio, btc_30d_return, funding_rate_7d_avg, oi_change_7d, mark_index_spread
- **Params:** LR 0.1, depth 8, n_est 150, neg_weight 3
- **Entry:** 0.55, Invalidation: 0.35

**3. variant-05-long-volatility-squeeze (7759da1c11d6)**
- **Model:** LightGBM, 11 features
- **Hypothesis:** Volatility compression breakouts are more predictable than general LONG signals
- **Features:** atr_compression, bb_squeeze_pct, realized_vol_ratio, high_low_range_pct, funding_rate_extreme, mark_index_spread, btc_vol_percentile, price_vs_52w_low, distance_from_support, volume_ratio_3d, oi_percentile_90d
- **Params:** LR 0.05, depth 6, n_est 200, leaves 63, neg_weight 5
- **Entry:** 0.50, Invalidation: 0.30

**4. variant-07-long-new-listing-focus (c628288c8fd7)**
- **Model:** CatBoost, 12 features
- **Hypothesis:** Early momentum on freshly listed coins is a distinct edge
- **Features:** is_new_listing, days_since_listing, volume_spike, volume_trend, vol_24h_vs_7d_avg, price_change_24h_pct, momentum_4w, bb_squeeze_pct, funding_rate_current, oi_change_24h, btc_30d_return, market_breadth
- **Params:** LR 0.08, depth 5, n_est 150, neg_weight 4
- **Entry:** 0.50, Invalidation: 0.30

### SHORT Direction (4 models — diversify from champion)

**5. variant-03-short-volume-heavy (e9a85bb5d727)**
- **Model:** CatBoost, 14 features
- **Hypothesis:** Distribution patterns (volume/OI spikes) predict SHORT entries better than price alone
- **Features:** 10 volume/OI features + 4 core (price_vs_52w_high, momentum_4w, atr_percentile, btc_30d_return)
- **Params:** LR 0.08, depth 6, n_est 250, neg_weight 6
- **Entry:** 0.50, Invalidation: 0.30

**6. variant-04-short-ultra-minimal (15c752e31208)**
- **Model:** LightGBM, 5 features
- **Hypothesis:** Champion's 37 features may be overfitted — test if 5 strongest features are enough
- **Features:** price_vs_52w_high, momentum_4w, volume_spike, atr_percentile, btc_30d_return
- **Params:** LR 0.05, depth 4, n_est 100, leaves 31, neg_weight 8
- **Entry:** 0.55, Invalidation: 0.35

**7. variant-06-short-xgboost-deep (cbe034c66752)**
- **Model:** XGBoost, 15 features
- **Hypothesis:** Aggressive top reversal signals need deep trees to capture complex interactions
- **Features:** price_vs_52w_high, price_vs_24h_high, momentum_4w/8w, bb_position, distance_from_resistance, higher_highs, consec_up_bars, volume_spike, obv_slope, funding_rate_current/extreme, oi_change_24h, btc_30d_return, market_breadth
- **Params:** LR 0.1, depth 10, n_est 200, neg_weight 4
- **Entry:** 0.45, Invalidation: 0.25

**8. variant-08-short-conservative-proven (25f531a3ce39)**
- **Model:** LightGBM, 12 features
- **Hypothesis:** Champion-like conservative config but even higher selectivity (0.60 threshold, neg_weight 10)
- **Features:** price_vs_52w_high, price_vs_24h_high, momentum_4w, bb_position, volume_spike, obv_slope, atr_percentile, funding_rate_7d_avg, btc_30d_return, btc_vol_percentile, market_breadth, days_since_listing
- **Params:** LR 0.01, depth 4, n_est 150, leaves 127, neg_weight 10
- **Entry:** 0.60, Invalidation: 0.40

## Expected Outcomes

**HIGH CONFIDENCE:**
- variant-01 (LONG minimal regime) — BTC correlation often drives LONG entries
- variant-04 (SHORT ultra-minimal) — tests if champion is overfitted
- variant-08 (SHORT conservative) — refinement of proven champion config

**MEDIUM CONFIDENCE:**
- variant-03 (SHORT volume-heavy) — distribution detection is theoretically sound
- variant-05 (LONG volatility squeeze) — compression breakouts are well-studied
- variant-07 (LONG new listing) — early momentum is a known edge

**EXPERIMENTAL:**
- variant-02 (LONG aggressive) — may be too aggressive for LONG signals
- variant-06 (SHORT XGBoost deep) — depth 10 may overfit

## Next Steps

1. ✅ Configs written to `configs/generated/2026-04-05/variant-01..08.json`
2. ✅ Inserted into `tournament_models` table with `stage='backtest_queue'`
3. ⏳ Next 4h cycle (moonshot-v2.timer) will backtest all 8 variants
4. ⏳ Monitor for BT passes (expect 10-20% pass rate based on historical data)
5. ⏳ FT promotion for any BT winners (PF ≥ 2.0)

## Files Created

- `/home/rob/.openclaw/workspace/blofin-moonshot-v2/configs/generated/2026-04-05/variant-01..08.json`
- `/home/rob/.openclaw/workspace/blofin-moonshot-v2/insert_2026-04-05_scout_variants.py`
- `/home/rob/.openclaw/workspace/blofin-moonshot-v2/strategy_ideas/2026-04-05-moonshot-scout.md`

## Model IDs

```
1331328908d0  long   catboost      variant-01-long-minimal-regime
3a04d642a4df  long   xgboost       variant-02-long-aggressive-price
e9a85bb5d727  short  catboost      variant-03-short-volume-heavy
15c752e31208  short  lightgbm      variant-04-short-ultra-minimal
7759da1c11d6  long   lightgbm      variant-05-long-volatility-squeeze
cbe034c66752  short  xgboost       variant-06-short-xgboost-deep
c628288c8fd7  long   catboost      variant-07-long-new-listing-focus
25f531a3ce39  short  lightgbm      variant-08-short-conservative-proven
```
