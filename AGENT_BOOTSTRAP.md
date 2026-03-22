# Crypto Agent Bootstrap — BLOFIN RESTORATION

**Last updated:** 2026-03-22 04:30 MST (Autonomous Fix Cycle #7)

## 🔧 ACTIVE RESTORATION (Mar 12 Data Loss)

### Current Status ⏳ IN PROGRESS
**RUNNING:** Full backtest sweep v4 (scripts/backtest_sweep_v4.py)
- Started: 04:28 MST
- Progress: 100/28,954 tasks (0.3%, 3.2 tasks/sec)
- ETA: ~7:00 MST (2.5 hours)
- Strategy: Sequential execution (no multiprocessing) — bypasses the relative import bugs that killed v2/v3
- Coverage: 62 strategies × 467 symbols = 28,954 backtests
- Timeframe: 15m candles, 90 days lookback

### What Was Fixed
1. **v2 issue:** Multiprocessing workers couldn't handle relative imports (`from .base_strategy`) — completed 2976 tasks but saved ZERO results
2. **v3 issue:** Tried to fix imports but only loaded 2/62 strategies
3. **v4 solution:** Sequential execution using existing `load_all_strategies()` from orchestration — loads all 62 strategies correctly

### After Backtest Completes
1. Verify results in database (expect ~1000-2000 strategy/coin pairs passing gates)
2. Review top performers (PF ≥ 1.35, trades ≥ 100, MDD < 50%)
3. Start paper trading: `systemctl --user start blofin-stack-paper.service`
4. Verify dashboard populated: http://127.0.0.1:8892
5. Monitor for 24h
6. **ASK ROB** before restarting pipeline timer

---

## System Status (as of Mar 22 04:30)
- ✅ WebSocket ingestor: blofin-ohlcv-ingestor.service (candles flowing)
- ✅ Historical data: 467 parquet files, 2.1GB
- ⏳ Backtest sweep: RUNNING (v4, 0.3% complete, ETA 7am)
- ⛔ Paper trading: STOPPED (waiting for backtest results)
- ✅ Dashboard: blofin-dashboard.service running (port 8892) — waiting for data
- ✅ Moonshot v2: HEALTHY, unaffected

---

## Moonshot v2 — Tournament Status (Mar 17 snapshot, unchanged)

### Champions (3 active)
- **SHORT Champion:** de44f72dbb01, FT_PF=2.22, FT_PnL=0.68% — HEALTHY ✅
- **LONG Champion:** 9b842069b20d, FT_PF=0.22, FT_PnL=-2.01% — needs investigation
- **New Listing:** new_listing, FT_trades=0 — waiting

### Tournament Numbers
| Stage | Count |
|-------|-------|
| Backtest | 32 models |
| FT | 423 models (393 SHORT, 30 LONG) |
| Retired | 1,792 models |
| Open positions | 884 |

---

## Git Status
- `blofin-stack`: 3 new files
  - scripts/backtest_sweep_v2.py (failed multiprocessing)
  - scripts/backtest_sweep_v3.py (failed imports)
  - scripts/backtest_sweep_v4.py (RUNNING - sequential solution)
- `blofin-moonshot-v2`: CLEAN

---

## Historical Context (Pre-Mar 12)

Blofin v1 was running:
- 72 strategies across 50+ coins
- Dynamic tier system (5x/3x/2x/1x leverage based on FT PF)
- Hourly backtest refresh (blofin-stack-pipeline.timer — STOPPED per Rob's order)
- Paper trading engine tracking performance

**Mar 12 data loss:** 107GB tick data lost, backtests/FT results cleared.
**Restoration status:** OHLCV restored (467 symbols), backtest sweep in progress.
