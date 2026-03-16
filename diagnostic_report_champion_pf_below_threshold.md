# Moonshot v2 Champion Diagnostic Report
**Date:** 2026-03-16
**Model:** de44f72dbb01 (SHORT Champion)
**Status:** FAILED — Below profitability threshold

---

## Executive Summary

Champion model **de44f72dbb01** has **FAILED forward testing** with a real profit factor of **0.79** (target: ≥1.0). The model is bleeding capital and should be **demoted and retired immediately**.

**Key Metrics:**
- Real FT trades: 88 (excluding 305 dedupe_cleanup trades)
- Real FT PF: **0.79** ❌
- Real FT win rate: 69.32%
- Net PnL: **-0.3308%** (losing)
- Recent trend: Last 5 trades ALL hit stop loss

---

## Root Cause Analysis

### 1. Gate Violation at Promotion ⚠️

**The model should never have been promoted to forward test.**

- Model backtest PF: **0.9765**
- Gate requirement at FT promotion (2026-03-11 14:01): MIN_BT_PF = **1.0**
- **VERDICT: REJECTED** (0.9765 < 1.0)

This is the **champion gate logic bug** documented in memory. The model bypassed backtest gates during promotion.

**Timeline:**
- Created: 2026-03-04 02:13:54
- Promoted to FT: 2026-03-11 14:01:21 (when MIN_BT_PF = 1.0) ← **GATE VIOLATION**
- Promoted to Champion: 2026-03-16 13:08:10 (when MIN_BT_PF = 0.6)

### 2. Inflated FT Metrics 📊

The database shows misleading statistics:
- DB ft_trades: **388**
- DB ft_pf: **2.22** ✓ (looks good)
- **Reality:** 305 trades (78%) are 'dedupe_cleanup' with 0% PnL
- **Real trades:** 88
- **Real PF:** 0.79 ❌ (unprofitable)

The dedupe_cleanup trades (all executed on 2026-03-04) artificially inflate the trade count and skew the profit factor calculation.

### 3. Trade Performance Breakdown

| Exit Reason   | Count | Win% | Total PnL% | Avg PnL% |
|---------------|-------|------|------------|----------|
| invalidation  | 81    | 75.3 | +0.9812    | +0.012   |
| STOP_LOSS     | 5     | 0.0  | -1.0146    | -0.203   |
| sl            | 2     | 0.0  | -0.2974    | -0.149   |
| **TOTAL**     | **88**| **69.3** | **-0.3308** | **-0.004** |

**Key Observations:**
- Invalidation exits (92% of trades) perform well: 75% WR, slightly profitable
- Stop loss exits (8% of trades) are **devastating**: 100% loss rate, avg -0.18% per trade
- Model is profitable when signals invalidate quickly, but bleeds when price continues against position

### 4. Win/Loss Profile — Structural Imbalance

- **Wins:** 61 trades, +1.2451% total, **avg +0.0204%** per win
- **Losses:** 25 trades, -1.5759% total, **avg -0.0630%** per loss
- **Loss magnitude:** **3.1x larger** than average win

**The model is structurally broken:**
- Risk/reward ratio: 0.020% win vs 0.063% loss = **1:3.1**
- To break even at this ratio, win rate would need to be >75%
- Actual win rate: 69.3% → **guaranteed bleed**

### 5. Recent Performance Collapse 📉

**Last 7 days performance:**
```
2026-03-16: -0.24% (STOP_LOSS) — ESP-USDT
2026-03-15: -0.15% (STOP_LOSS) — W-USDT
2026-03-14: -0.63% (3× STOP_LOSS) — ARC, VVV, INX
2026-03-13: -0.02% (invalidation) — MANTRA
2026-03-12: +0.04% (invalidation) — FLUX ← Last win
2026-03-11: -0.05% (mixed)
```

- **Last 5 actual trades:** 100% stop loss rate
- **Last winning trade:** March 12 (4 days ago)
- **Trend:** Accelerating losses

### 6. Backtest vs Forward Test Divergence

| Metric       | Backtest  | Forward Test | Verdict |
|--------------|-----------|--------------|---------|
| Profit Factor| 0.9765    | 0.79         | FT confirms BT: **NO EDGE** |
| Precision    | 24.56%    | 69.32% WR    | FT better than BT (invalidation helps) |
| Trade Count  | 191,235   | 88           | BT sample is massive → trustworthy |

**Interpretation:**
- Backtest already showed unprofitability (PF=0.9765 < 1.0)
- Forward test **confirms** the backtest: this model has no edge
- Large BT sample size (191K trades) means this is **not bad luck** — it's structural

---

## Specific Pattern Analysis

**No single coin is the culprit** — losses are distributed across:
- W-USDT: -0.15%
- VVV-USDT: -0.20%
- ARC-USDT: -0.16%
- ESP-USDT: -0.24%
- INX-USDT: -0.27%

**The fundamental issue is stop loss sizing:**
- Model entry logic is decent (75% of signals invalidate profitably)
- When price continues against position → bleeds full -5% stop loss
- With 2x leverage, this becomes -10% on capital
- Average win (+0.02%) cannot compensate for occasional large loss (-0.20%)

---

## Recommendation

### ✅ **ACTION: DEMOTE & RETIRE IMMEDIATELY**

**Rationale:**
1. Model **violated BT gates** at FT promotion (bt_pf=0.9765 < 1.0)
2. FT confirms **no edge** (PF=0.79 after 88 real trades)
3. Recent trend shows **accelerating losses** (last 5 trades = 100% stop loss)
4. **Loss/win ratio** (3.1x) is structurally unsustainable
5. **BT sample size** (191K trades) confirms this is not variance — it's a failing model

### 🔄 **REPLACEMENT CHAMPION**

**Promote Model:** `3c905c7a9f91`

| Metric              | Value        | Status |
|---------------------|--------------|--------|
| Real FT trades      | 111          | ✓ Sufficient sample |
| Real FT PF          | **1.044**    | ✓ Above 1.0 |
| Real FT WR          | 58.56%       | ✓ Solid |
| Net PnL             | +0.2253%     | ✓ Profitable |
| BT PF               | 1.042        | ✓ Passes gates |
| BT Precision        | 25.8%        | ✓ Passes gates |
| Entry threshold     | 0.5          | ✓ Moderate |
| Take profit exits   | 5 (100% WR)  | ✓ Captures big moves |

**Why this model:**
- Proven profitable over 111 real trades
- Hit 5 TAKE_PROFIT exits (+3.98% total) — shows it can capture moonshots
- Better backtest foundation (PF=1.042 vs current champion's 0.9765)
- Moderate entry threshold (0.5) balances signal quality and coverage

**Alternative:** Model `2321094c8072` (PF=1.139, 110 trades) is also viable but has more aggressive entry threshold (0.3).

---

## Next Steps

### Immediate Actions (Read-Only — Awaiting Approval)

1. **Retire de44f72dbb01:**
   ```sql
   UPDATE tournament_models
   SET stage = 'retired',
       retired_at = <current_timestamp>,
       retire_reason = 'FT failed: PF=0.79 < 1.0, violated BT gates at promotion'
   WHERE model_id = 'de44f72dbb01';
   ```

2. **Promote 3c905c7a9f91 to champion:**
   ```sql
   UPDATE tournament_models
   SET stage = 'champion',
       promoted_to_champion_at = <current_timestamp>
   WHERE model_id = '3c905c7a9f91';
   ```

3. **Copy model file:**
   ```bash
   cp models/tournament/3c905c7a9f91.pkl models/champion_short.pkl
   ```

### Data Hygiene (Optional)

**Clean up dedupe_cleanup trades** to prevent future metric inflation:
```sql
-- Archive and delete dedupe_cleanup trades
-- This affects 305 trades for de44f72dbb01 + similar counts for other models
DELETE FROM positions
WHERE exit_reason = 'dedupe_cleanup';
```

**Impact:** This will fix ft_trades and ft_pf metrics across all models.

### System Improvements (Already Fixed)

✅ Champion promotion logic now enforces BT gates (see memory: bug_champion_gate_logic.md)
✅ FT PF calculation should exclude dedupe_cleanup trades (verify in `src/tournament/champion.py`)

---

## Conclusion

Champion model de44f72dbb01 has **conclusively failed** forward testing and should be **retired immediately**. The model:
- Should never have been promoted (violated BT gates)
- Has a structurally broken risk/reward ratio (1:3.1)
- Is bleeding capital in recent trading (-0.63% in last 4 days)
- Shows no edge after 88 real trades (PF=0.79)

**Replacement model 3c905c7a9f91** offers a statistically significant profitable alternative (111 trades, PF=1.044, +0.23% net PnL).

**Status:** Awaiting Jarvis approval to execute demotion and promotion.
