# 2026-04-01 Moonshot Tournament Analysis

## PHASE 1 — TOURNAMENT STATE

### Current Champions (2)
| Model ID | Direction | Type | FT PnL | FT PF | FT Trades | Win Rate | Features |
|----------|-----------|------|--------|-------|-----------|----------|----------|
| 8bcea880b343 | SHORT | lightgbm | 3.30 | 3.12 | 94 | 71.3% | no_social (15 features) |
| new_listing | - | rule_based | 0.0 | 0.0 | 0 | - | None (price action rules) |

**Champion feature set (8bcea880b343):**
- price_vs_52w_high, price_vs_52w_low
- momentum_4w, momentum_8w
- bb_squeeze_pct, bb_position
- volume_ratio_7d, volume_ratio_3d
- obv_slope, volume_spike, volume_trend
- btc_30d_return, btc_vol_percentile
- market_breadth, days_since_listing, is_new_listing

### Tournament Pipeline Health
| Stage | Count |
|-------|-------|
| Retired | 3032 |
| Forward Test | 933 |
| Backtest | 411 |
| Backtest Queue | 26 |
| Backtest Pending | 17 |
| Seeded | 10 |
| Champion | 2 |

**Total models tested:** 4,431

### Retirement Analysis (3032 retired)
| Reason | Count | % |
|--------|-------|---|
| backtest_failed | 2888 | 95.3% |
| ft_unprofitable_pf_below_0.9_after_50_trades | 73 | 2.4% |
| ft_pf_below_1.3_after_20_trades | 20 | 0.7% |
| backtest_error: 'direction' | 20 | 0.7% |
| ft_catastrophic_pf_below_0.5_after_150_trades | 10 | 0.3% |
| Other errors | 20 | 0.7% |

**Key insight:** 95% fail at backtest stage (PF < 0.6 SHORT, PF < 1.5 LONG). Only 5% reach FT. Of FT models, ~10% survive to promotion consideration.

### FT Performance Trends (last 30 days, ≥20 trades)
| Direction | Models Tested | Avg PnL | Avg PF | Profitable Count |
|-----------|---------------|---------|--------|------------------|
| LONG | 18 | -1.72 | 0.45 | 1 (5.6%) |
| SHORT | 101 | -5.45 | 0.57 | 5 (5.0%) |

**Reality check:** Only ~5% of FT models are profitable. Tournament working as designed (95% failure rate is GOOD).

### Top Feature Sets (BT PF > 1.3)
1. **no_social (15 features)** — 7 models, avg BT PF 1.87
2. **full_social (37 features)** — 7 models, avg BT PF 1.58  
3. **full_features + social (48 features)** — 7 models, avg BT PF 1.65
4. **minimal_social (25 features)** — 4 models, avg BT PF 1.70
5. **price_volume_only (16 features)** — 1 model, avg BT PF 1.84

## PHASE 2 — GAPS & OPPORTUNITIES

### Underutilized Features
**Never tested or rarely used:**
- momentum_1d, momentum_3d (short-term momentum)
- atr_compression, atr_percentile (volatility regime)
- high_low_range_pct, realized_vol_ratio
- consec_down_bars, consec_up_bars, higher_highs (microstructure)
- distance_from_support, distance_from_resistance
- price_vs_24h_high, price_vs_24h_low (intraday levels)
- vol_24h_vs_7d_avg (volume regime)

### Feature Combinations Not Tested
1. **Volatility regime filter** — atr_compression + realized_vol_ratio + high_low_range_pct
2. **Intraday microstructure** — consec_bars + price_vs_24h levels + vol_24h_vs_7d
3. **Short-term momentum** — momentum_1d + momentum_3d (vs 4w/8w only)
4. **Support/resistance levels** — distance_from_support/resistance (never tested)

### Algo Diversity Gap
- **Current champion:** LightGBM (1 model)
- **FT pipeline:** Heavy XGBoost/CatBoost bias
- **Missing:** Pure CatBoost champions, minimal RandomForest/ExtraTrees

### Lookback Window Gap
- All features use **4H candles** as primary timeframe
- No multi-timeframe features (1H aggression vs 1D trend alignment)
- Opportunity: Add 1H momentum for fast reversals, 1D trend for filtering

### Recent Insights (Mar 28-31)
1. **Mar 28:** Deployed 87033f5ca7fe (CatBoost SHORT, FT PF 2.63) to live trading
2. **Mar 29:** 8 variants added (price-volume focus, CatBoost depth tests)
3. **Mar 30:** 7 variants added (funding contrarian, momentum extremes, minimal core)
4. **Mar 31:** 8 variants added (volume sniper, fast trader)
5. **Current live position:** 2 shorts underwater (XCU -9.4%, 1000LUNC -6.1%), drawdown -6.15%

## PHASE 3 — NEW VARIANTS (10 models)

### Variant 1: Volatility Regime Filter (SHORT)
**Hypothesis:** Low volatility compression predicts explosive moves  
**Features:** atr_compression, atr_percentile, high_low_range_pct, realized_vol_ratio, bb_squeeze_pct, price_vs_52w_high, momentum_4w, volume_spike  
**Model:** CatBoost (depth=5, lr=0.03, n_estimators=300)  
**Entry:** 0.60 (stricter — wait for strong compression signal)

### Variant 2: Intraday Microstructure (SHORT)
**Hypothesis:** Consecutive bars + intraday levels reveal exhaustion  
**Features:** consec_down_bars, consec_up_bars, higher_highs, price_vs_24h_high, price_vs_24h_low, vol_24h_vs_7d_avg, volume_spike, momentum_1d, momentum_3d  
**Model:** LightGBM (num_leaves=31, lr=0.05, n_estimators=200)  
**Entry:** 0.55

### Variant 3: Short-Term Momentum Burst (SHORT)
**Hypothesis:** 1d/3d momentum captures fast reversals better than 4w/8w  
**Features:** momentum_1d, momentum_3d, momentum_4w, price_vs_52w_high, volume_ratio_3d, volume_spike, obv_slope, btc_30d_return  
**Model:** XGBoost (max_depth=4, lr=0.05, n_estimators=250, scale_pos_weight=3)  
**Entry:** 0.50

### Variant 4: Support/Resistance Levels (SHORT)
**Hypothesis:** Distance from S/R levels predicts reversals  
**Features:** distance_from_support, distance_from_resistance, price_vs_52w_high, price_vs_52w_low, momentum_4w, volume_ratio_7d, obv_slope  
**Model:** CatBoost (depth=6, lr=0.05, n_estimators=200)  
**Entry:** 0.60

### Variant 5: Ultra-Minimal (SHORT)
**Hypothesis:** 5 best features outperform 15+ feature sets  
**Features:** price_vs_52w_high, momentum_4w, volume_spike, obv_slope, btc_30d_return  
**Model:** CatBoost (depth=4, lr=0.08, n_estimators=150)  
**Entry:** 0.50

### Variant 6: Deep CatBoost (SHORT)
**Hypothesis:** Deeper trees capture complex interactions  
**Features:** Champion feature set (15 features from 8bcea880b343)  
**Model:** CatBoost (depth=8, lr=0.02, n_estimators=400, l2_leaf_reg=7)  
**Entry:** 0.55

### Variant 7: Fast XGBoost (SHORT)
**Hypothesis:** Shallow, fast trees with high learning rate  
**Features:** price_vs_52w_high, momentum_4w, momentum_1d, volume_ratio_7d, volume_spike, market_breadth  
**Model:** XGBoost (max_depth=3, lr=0.15, n_estimators=100, scale_pos_weight=4)  
**Entry:** 0.50

### Variant 8: Long Lottery v2 (LONG)
**Hypothesis:** New listing momentum + volatility spike  
**Features:** is_new_listing, days_since_listing, momentum_1d, momentum_3d, volume_spike, atr_percentile, price_vs_52w_low, btc_30d_return  
**Model:** LightGBM (num_leaves=15, lr=0.10, n_estimators=150)  
**Entry:** 0.50

### Variant 9: Funding Rate Contrarian v2 (SHORT)
**Hypothesis:** Extreme funding + price divergence predicts reversals  
**Features:** funding_rate_extreme, funding_rate_7d_avg, oi_price_divergence, oi_percentile_90d, price_vs_52w_high, momentum_4w, volume_ratio_7d  
**Model:** CatBoost (depth=5, lr=0.05, n_estimators=250)  
**Entry:** 0.60

### Variant 10: Hybrid Timeframe (SHORT)
**Hypothesis:** 1d momentum filter + 4w trend alignment  
**Features:** momentum_1d, momentum_3d, momentum_4w, momentum_8w, price_vs_52w_high, volume_ratio_3d, volume_spike, btc_30d_return  
**Model:** LightGBM (num_leaves=31, lr=0.05, n_estimators=250)  
**Entry:** 0.55

## Implementation Notes
- All variants target SHORT (where current champion lives)
- 1 LONG variant (v8) to test lottery ticket hypothesis
- Feature sets range from 5 (minimal) to 10 (focused)
- Mix of CatBoost (4), LightGBM (3), XGBoost (2), RandomForest (1)
- Entry thresholds 0.50-0.60 based on selectivity hypothesis
- NO modifications to core pipeline (all use existing features)
