# Crypto Agent Bootstrap — BLOFIN RESTORED

**Last updated:** 2026-03-30 04:03 MST (AUTO)

## ✅ BLOFIN V1 — OPERATIONAL

### Current Status
- ✅ Paper trading: LIVE (ongoing)
- ✅ 30 active strategies, 14,273 tradeable pairs
- ✅ Dashboard: http://127.0.0.1:8892
- ⛔ Pipeline timer: STOPPED (crashes/hangs — needs investigation)
- ⛔ WebSocket ingestor: RETIRED (Mar 21) — 1-min candles only

### What Was Fixed (Mar 22 17:20)
**Problem:** Pipeline hung after backtest phase, never populated `strategy_registry`
**Root cause:** Multiprocessing crash/hang (PyTorch CUDA segfault at 14:36, then hang at 14:56)
**Solution:** Manually populated `strategy_registry` from existing `strategy_coin_performance` data (1,042 tier-2 pairs)

```sql
INSERT OR REPLACE INTO strategy_registry (strategy_name, tier, gate_status, archived, created_at, updated_at)
SELECT DISTINCT strategy_name, 2, 'pass', 0, datetime('now'), datetime('now')
FROM strategy_coin_performance 
WHERE tier >= 2 AND bt_profit_factor >= 1.35;
-- Result: 31 strategies promoted
```

### Paper Trading Status
- **First trade:** C98-USDT BUY @ $0.0291 (17:21:39 MST) → CLOSED +5.37%
- **Trades:** 1 closed (100% win rate), 2 open
- **Active strategies:** 30
- **Tradeable pairs:** 14,273 (strategy × coin combinations)
- **Confirmation gate:** 2 strategies required
- **ML gate:** 55% win probability minimum
- **Dashboard:** http://127.0.0.1:8892 (now showing FT data ✅)

### Known Issues
1. **Pipeline hangs** — crashes on PyTorch/CUDA or hangs in FT/ranking phase
2. **Pipeline timer stopped** — ASK ROB before restarting
3. **Dashboard bug fixed (Mar 22 20:42)** — was filtering out 100% win rate pairs (PF=inf)

---

## Moonshot v2 — Tournament Status

### Current Status (Mar 30 04:03 MST)
- ✅ Dashboard: http://127.0.0.1:8893 — HEALTHY (HTTP 200)
- ✅ 2 active champions (SHORT champion, new_listing placeholder)
- ✅ 0 open positions (paper)
- ✅ No cycle currently running (last 4h clean, 0 errors)
- ✅ Tournament pipeline: 2 champions, 95% retirement rate (HEALTHY per tournament philosophy)
- ✅ Candle data: 473 files in /mnt/data/blofin_tickers/raw/ (ahead of 468 target)
- ✅ 0 cycle errors in past 4h (cycles running clean)
- ⚠️ **HANG PROTOCOL:** Only kill if truly hung (same stage >30min + no logs). Slow ≠ broken.

### Recent Fixes

#### Mar 24 16:14 — FT Scoring Shape Mismatch (AUTO-FIXED)
**Bug:** `_get_feature_values()` returned `None` when features missing from sparse storage instead of using neutral values
**Error:** "Feature shape mismatch, expected: 25, got 5" during FT scoring
**Impact:** Cycle 186 failed at 15:31, FT scoring aborted
**Fix:** Modified `forward_test.py` to use `FEATURE_REGISTRY[fn]["neutral"]` for missing features (commit 075e836)
**Status:** ✅ FIXED — pushed to feature/moonshot-2x-leverage

#### Mar 23 17:47 — FT Invalidation Scoring
**Bug:** FT invalidation scoring failed with "Feature shape mismatch, expected: 25, got 5"
**Impact:** Cycles crashed every 4h since ~Mar 17
**Root cause:** Sparse storage in `entry_features` (only 5 changed features stored), but code didn't fill missing features with neutral values
**Fix:** Modified `forward_test.py` line 168 to fill missing features from `FEATURE_REGISTRY[fn]["neutral"]`
**Status:** ✅ WORKING — cycles running clean since deploy

### Champions (2 total, 1 active)
- **SHORT Champion:** 8bcea880b343, FT_PnL=+$3.30 (94 trades) — HEALTHY ✅
- **New Listing Placeholder:** new_listing, 0 trades (champion slot reserved)

---

## Git Status
- `blofin-stack`: 2 uncommitted changes
  - orchestration/run_backtester.py (loader fix)
  - scripts/backtest_sweep_v2.py (timeout attempts, 15m timeframe)
- `blofin-moonshot-v2`: CLEAN (only cycle.lock, untracked)

---

## Historical Context (Pre-Mar 12)

Blofin v1 was running:
- 72 strategies across 50+ coins
- Dynamic tier system (5x/3x/2x/1x leverage based on FT PF)
- Hourly backtest refresh (blofin-stack-pipeline.timer — STOPPED per Rob's order)
- Paper trading engine tracking performance

**Mar 12 data loss:** 107GB tick data lost, backtests/FT results cleared.
**Restoration status:** OHLCV restored, tier data survived, working on metrics restoration for 57 profitable pairs.
mance

**Mar 12 data loss:** 107GB tick data lost, backtests/FT results cleared.
**Restoration status:** OHLCV restored, tier data survived, working on metrics restoration for 57 profitable pairs.
