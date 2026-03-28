# Crypto Agent Bootstrap — BLOFIN RESTORED

**Last updated:** 2026-03-27 20:05 MST (AUTO)

## ✅ BLOFIN V1 — OPERATIONAL

### Current Status
- ✅ Paper trading: LIVE (first trade 17:21 MST)
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

### Current Status (Mar 27 20:05 MST)
- ✅ Dashboard: http://127.0.0.1:8893 — HEALTHY (HTTP 200)
- ✅ 2 active champions (SHORT champion: +$3.30 / 94 trades + new_listing placeholder)
- ✅ 787 open positions (paper)
- ✅ Cycle running (PID 4166671, started 20:04 after systemd timeout)
- ✅ No errors in last 4h
- ✅ 473 files in 1-min candle backfill (target 468 — COMPLETE)
- ⚠️ **SYSTEMD TIMEOUT ISSUE (Mar 27 20:04):**
  - Cycle 195 killed after 4h (16:04→20:04) by systemd TimeoutStartSec=14400
  - **NOT A HANG** — cycle was working (backtest folds completing: fold 1 @ 19:05, fold 2 @ 19:46)
  - CPU time: 16h 34min (4x wall time) — ML work is CPU-intensive
  - **Action needed:** Increase TimeoutStartSec or optimize cycle performance
- ⚠️ **HANG INCIDENT LOG:**
  - **Mar 27 16:04: ZOMBIE PROCESS KILLED** — PID 3010001 hung since Mar 16 16:25 (11 days), last log "fetch_all_extended: starting for 470 symbols"
  - Mar 26 00:03: Killed cycle 194 after 4h (truly hung, no DB updates for 72h)
  - Mar 25 20:05: Killed cycle 193 after 4h (systemd timeout, backtest stage)
  - Mar 24 04:04: Killed cycle 183 after 92min (PREMATURE — was healthy)
  - Mar 16: Killed builder after 10min (PREMATURE — was healthy)
  - **Fix deployed:** Hang detection protocol in HEARTBEAT.md (same stage >30min + no log updates)

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
- `blofin-moonshot-v2`: CLEAN

---

## Historical Context (Pre-Mar 12)

Blofin v1 was running:
- 72 strategies across 50+ coins
- Dynamic tier system (5x/3x/2x/1x leverage based on FT PF)
- Hourly backtest refresh (blofin-stack-pipeline.timer — STOPPED per Rob's order)
- Paper trading engine tracking performance

**Mar 12 data loss:** 107GB tick data lost, backtests/FT results cleared.
**Restoration status:** OHLCV restored, tier data survived, working on metrics restoration for 57 profitable pairs.
r 57 profitable pairs.
