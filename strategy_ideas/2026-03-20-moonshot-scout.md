# Moonshot Strategy Scout — 2026-03-20

**Generated:** 2026-03-20 17:33 MST  
**Cron Job:** Moonshot AI Strategy Scout

## Tournament State

### Champions
- **SHORT:** de44f72dbb01 (catboost, "all" features)
  - FT PnL: 0.6837 | Trades: 388 | WR: 15.72% | PF: 2.22
  - This is the ONLY profitable champion

- **LONG:** new_listing (rule_based placeholder)
  - FT PnL: 0.0000 | No trades yet

### Key Observations
1. **Tournament is SHORT-dominated** — only short models are working
2. **95%+ retirement rate** — backtest_failed is primary reason (expected)
3. **Backtest queue is EMPTY** — need fresh variants
4. **Feature set "all" won** — but most models with "all" fail (avg -5.69 FT PnL)
5. **Model diversity is good** — catboost(841), xgboost(921), lightgbm(911)
6. **558 models in FT stage** — but most are zero-trade or losing

### Recent FT Winners (30 days)
- Only 1: de44f72dbb01 (short, catboost, "all")
- This means **0.18% success rate** (1 winner / 558 FT models)
- Tournament philosophy is working: finding the 0.5% needles

## Gap Analysis

### What's Missing?
1. **Long models aren't working** — need new long variants with different approaches
2. **Feature subset exploration is shallow** — most models use preset groups (all, core_only, extended_only, no_social, price_volume)
3. **Minimal tactical features** — current features are broad regime/momentum, missing:
   - Short-term momentum (5min, 15min, 1h)
   - Mean reversion indicators (RSI, Stochastic)
   - Liquidity depth features (bid/ask imbalance, spread)
   - Order flow proxies (volume profile, delta)
4. **No ensemble models** — only single-model entries
5. **Conservative thresholds** — confidence_threshold mostly 0.5-0.6
6. **Fixed lookback windows** — 4w/8w momentum, 7d volume, etc. Not testing 1h/4h/1d variants

### Feature Usage Patterns
- **Most common features:** price_vs_52w_high/low, momentum_4w/8w, volume ratios, bb_squeeze
- **Underutilized:** Social features (13 features, rarely used alone)
- **Extended features:** Funding rate, OI, mark price spread — not tested in isolation

## Proposed Variants (10 models)

### 1. Short-Term Momentum SHORT (catboost)
**Hypothesis:** Winner uses "all" features — try isolating short-term price action only.
- **Features:** price_vs_24h_high, price_vs_24h_low, price_change_24h_pct, bb_position, consec_down_bars, consec_up_bars
- **Params:** depth=4, lr=0.01, estimators=500 (copy champion's architecture)
- **Direction:** short
- **Confidence:** 0.55

### 2. Funding Rate Extremes SHORT (xgboost)
**Hypothesis:** Extreme funding = mean reversion signal for shorts.
- **Features:** funding_rate_current, funding_rate_7d_avg, funding_rate_extreme, oi_change_24h, mark_index_spread
- **Params:** depth=6, lr=0.05, estimators=300
- **Direction:** short
- **Confidence:** 0.65

### 3. Volatility Compression LONG (lightgbm)
**Hypothesis:** Low vol → expansion (good for longs).
- **Features:** atr_compression, bb_squeeze_pct, realized_vol_ratio, atr_percentile, high_low_range_pct
- **Params:** depth=8, lr=0.01, estimators=200, num_leaves=31
- **Direction:** long
- **Confidence:** 0.60

### 4. Support Bounce LONG (catboost)
**Hypothesis:** Price near support + oversold momentum.
- **Features:** distance_from_support, consec_down_bars, price_vs_52w_low, momentum_4w, bb_position
- **Params:** depth=6, lr=0.05, estimators=300
- **Direction:** long
- **Confidence:** 0.55

### 5. Volume Spike Reversal LONG (xgboost)
**Hypothesis:** Volume spike + down bars = capitulation.
- **Features:** volume_spike, volume_ratio_3d, consec_down_bars, obv_slope, price_vs_24h_low
- **Params:** depth=4, lr=0.1, estimators=200
- **Direction:** long
- **Confidence:** 0.50

### 6. OI Divergence SHORT (lightgbm)
**Hypothesis:** OI up, price down = shorts winning.
- **Features:** oi_price_divergence, oi_change_24h, oi_change_7d, oi_percentile_90d, price_change_24h_pct
- **Params:** depth=10, lr=0.01, estimators=500, num_leaves=63
- **Direction:** short
- **Confidence:** 0.60

### 7. Social Hype Fade SHORT (catboost)
**Hypothesis:** Trending coins are overheated.
- **Features:** is_coingecko_trending, trending_rank, hours_on_trending, news_velocity_ratio, reddit_velocity_ratio, price_vs_52w_high
- **Params:** depth=4, lr=0.01, estimators=300
- **Direction:** short
- **Confidence:** 0.70

### 8. Minimal Core LONG (xgboost)
**Hypothesis:** Simpler = better for longs (avoid overfitting).
- **Features:** momentum_8w, volume_ratio_7d, btc_30d_return, market_breadth
- **Params:** depth=3, lr=0.05, estimators=100
- **Direction:** long
- **Confidence:** 0.50

### 9. High-Confidence SHORT (catboost)
**Hypothesis:** Clone champion architecture, raise threshold.
- **Features:** all
- **Params:** depth=4, lr=0.01, estimators=500 (same as de44f72dbb01)
- **Direction:** short
- **Confidence:** 0.75 (higher than default)

### 10. Regime Filter LONG (lightgbm)
**Hypothesis:** Only trade longs in bull regime.
- **Features:** btc_30d_return, btc_vol_percentile, market_breadth, momentum_8w, volume_ratio_7d, price_vs_52w_low
- **Params:** depth=6, lr=0.01, estimators=300, num_leaves=31
- **Direction:** long
- **Confidence:** 0.60

## Implementation Plan
1. Spawn coding subagent for each variant
2. Generate JSON configs in `blofin-moonshot-v2/configs/generated/2026-03-20-*.json`
3. Insert into backtest queue via SQL
4. Commit configs to git
5. Next tournament cycle (4h timer) will process them

## Success Criteria
- At least 5/10 variants pass backtest
- At least 1 long variant reaches FT stage
- Learn which feature subsets have signal vs noise
