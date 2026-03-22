# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-22 00:48 MST (Autonomous restoration mode - Rob asleep)

## 🚨 ACTIVE MISSION: RESTORE BLOFIN PIPELINE (Mar 22 00:48)

**What I broke:** Lost 107GB tick database on Mar 12 during migration
**What I've restored:** 2GB OHLCV 1-min candle data (459 parquet files)
**What's still broken:** Backtest pipeline (strategy loader broken, only loads 2/72 strategies)
**Rob's expectation:** SYSTEM FULLY RESTORED WHEN HE WAKES UP (8 hours)

### Autonomous Restoration Cron (Every 30min)
- **Cron ID:** 6ab0d78e-04ea-4d66-881c-d551490726c5
- **Next run:** 01:15 AM, then 01:45, 02:15, etc.
- **Mission:** Check progress, fix issues, restore pipeline
- **NO WAITING:** Fix problems immediately, don't wait for Rob

### Current Status (00:48 Mar 22)

**✅ WORKING (DON'T TOUCH):**
- `blofin-ohlcv-ingestor.service` — WebSocket candles (ACTIVE, 459 files)
- Historical backfill — 36/182 symbols (slow but working)
- Moonshot v2 — HEALTHY (unaffected)

**🔄 IN PROGRESS:**
- Backtest sweep v2 — RUNNING (96 tasks = 2 strategies × 48 symbols)
- Started: 00:46, ETA: 00:47 (< 1 min)
- Output: /tmp/backtest_sweep_v2_output.log

**❌ BROKEN (FIXING TONIGHT):**
- Strategy loader — only loads 2/72 strategies (relative import issue)
- Paper trading — STOPPED (will restart after backtests complete)
- Dashboard — EMPTY (waiting for backtest results)

### Restoration Checklist

- [x] Restore OHLCV data (2GB parquet)
- [x] Deploy WebSocket ingestor
- [x] Start backtest sweep
- [ ] Fix strategy loader (load all 72 strategies)
- [ ] Re-run backtests with full strategy set
- [ ] Populate database (strategy_backtest_results)
- [ ] Start paper trading engine
- [ ] Verify dashboard shows data
- [ ] System profitable again

## Moonshot v2 — Tournament Status (HEALTHY)

### Champions (3 active)
- **SHORT:** de44f72dbb01 (XGBoost), FT PF=2.22, 388 trades ✅
- **LONG:** 9b842069b20d (CatBoost), FT PF=0.22, 39 trades ⚠️
- **New Listing:** waiting for next ≤7 day coin

### Services
- `moonshot-v2.timer` — 4h cycle (ACTIVE)
- `moonshot-v2-dashboard.service` — port 8893 (ACTIVE)

## Blofin v1 Stack (RESTORING)

### Services
- 🟢 `blofin-ohlcv-ingestor.service` — WebSocket candles (ACTIVE)
- 🟢 `blofin-dashboard.service` — port 8892 (ACTIVE, empty)
- 🔴 `blofin-stack-paper.service` — Paper trading (STOPPED, will restart)

### Data Pipeline
- Candles: WebSocket → /mnt/data/blofin_ohlcv/1m/*.parquet (LIVE)
- Backtests: Running → strategy_backtest_results (IN PROGRESS)
- Paper trades: Waiting → paper_trades (NOT STARTED)

### Architecture
- 72 strategies in repo (all code intact)
- Strategy loader BROKEN (only loads 2)
- Fix location: orchestration/run_backtester.py load_all_strategies()
- Issue: relative imports fail with importlib.util.spec_from_file_location

## Critical Rules
- ⛔ Investigate before killing (check logs, CPU, progress first)
- ⛔ Never wait for Rob - fix issues immediately
- ⛔ System was PROFITABLE - restore to that state
- ✅ All code exists in repo - find it, read it, use it
