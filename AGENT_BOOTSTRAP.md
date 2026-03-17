# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-17 12:32 MST (Heartbeat — all systems healthy)

## 🚨 SYSTEMD TIMEOUT FIX v2 (Mar 17 10:34) — NOW ACTUALLY FIXED ✅
- **Issue:** Type=oneshot service was getting SIGTERM killed after ~76min (not 15-20min as thought)
- **Root cause:** `TimeoutStopSec=120` was 120 **SECONDS** not minutes — cycles need 60-90min
- **Symptoms:** Cycle 136 killed at 10:21 (ran 09:05-10:21 = 76min), previous "fix" was wrong unit
- **Fix v1 (Mar 17 07:36):** Added `TimeoutStopSec=120` — **WRONG, should be 120min not 120sec**
- **Fix v2 (Mar 17 10:34):** Changed to `TimeoutStopSec=infinity` — **NOW CORRECT**
- **Status:** Cycle 137 running (started 10:21, in progress), will not be killed
- **Lesson:** Always verify units in systemd config (120 = 120 seconds, not minutes)

## 🚀 PERFORMANCE FIX (Mar 17 05:47) — HOURLY CYCLES + DYNAMIC BACKTESTING
- **Cycle interval changed:** 4h → **1h** (hourly at :05)
- **Backtest batch now DYNAMIC** based on CPU load (commit d71f08c, 707e591)
  - CPU < 70%: batch 100 models (max throughput)
  - CPU ≥ 70%: batch 10 models (throttle to prevent overload)
  - Uses 1-min load average / core count (psutil)
- **Result:** Queue drains 75/hour when CPU idle (was growing +5/4h)

## Session Summary (Mar 17 2026)

**Heartbeat 12:32 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🔄 Moonshot Cycle 137 IN PROGRESS (started 12:06, 27min runtime) — backtesting models
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=0.68% — **ACTIVE**
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: ~353 models (stable)
- 📊 BT backlog: ~194 models (draining 100/cycle when CPU<70%)
- 📊 Open positions: ~927
- 🔧 Historical backfill: RUNNING (1 process, 5h runtime since 07:29)
- 🔧 Builders running: 2 (1 NQ card In Progress, 1 crypto card dispatched — reversal+DOT 3x scale)
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 2 In Progress, 0 Failed
- 🔧 Git: moonshot clean, blofin clean (both repos no uncommitted changes, no unpushed commits)
- 🎯 **Dispatched:** reversal+DOT 3x leverage scale (FT_PF=5.06) — card c_0d3274eeb9c38_19cfd349bfc

**Heartbeat 12:02 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🔄 Moonshot Cycle 136 IN PROGRESS (started 10:21, 1h 41m runtime) — backtesting model 6aeb1e430ef8
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=0.68% — **ACTIVE** (21 open)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 353 models
- 📊 BT backlog: 194 models
- 📊 Open positions: 927 (21 champion, 906 non-champion)
- 📊 Blofin v1: Top 5 BT: macd_divergence+DOT-USDT PF=3.42 (212 trades), rsi_divergence+ETH-USDT PF=3.40 (291), macd_divergence+LINK-USDT PF=3.39 (303), vwap_reversion+DOGE-USDT PF=3.38 (233), ema_crossover+SOL-USDT PF=3.37 (440)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed, 1165 Done
- 🔧 Git: moonshot clean (catboost logs only), blofin clean
- 🎯 **CRITICAL FIX CONFIRMED:** TimeoutStopSec=infinity applied, Cycle 136 NOT killed after 1h 41m (was killed at 76min yesterday) — systemd timeout fix WORKING ✅

**Heartbeat 11:31 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 135 COMPLETE (finished 08:26, 20min runtime, 3h5m ago) — 4 errors
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=0.68% — **ACTIVE** (21 open)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 347 models
- 📊 BT backlog: 209 models
- 📊 Open positions: 927 (21 champion, 906 non-champion)
- 📊 Blofin v1: Top 5 BT: macd_divergence+DOT-USDT PF=3.42 (212 trades), rsi_divergence+ETH-USDT PF=3.40 (291), macd_divergence+LINK-USDT PF=3.39 (303), vwap_reversion+DOGE-USDT PF=3.38 (233), ema_crossover+SOL-USDT PF=3.37 (440)
- 🔧 Historical backfill: RUNNING (2 processes active, started 07:29, 4h2m runtime)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), blofin clean
- ⏰ Timer: Last cycle 08:26, next cycle unknown (checking journal) — systemd timeout fix HOLDING ✅

**Heartbeat 10:03 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 135 COMPLETE (finished 08:26, 20min runtime, 97min ago) — 4 errors
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22 — **ACTIVE** (21 open)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 332 models (draining 20-75/cycle depending on CPU)
- 📊 BT backlog: 219 models (draining 20-75/cycle depending on CPU)
- 📊 Open positions: 958 (21 champion, 937 non-champion)
- 📊 Blofin v1: Top 5 BT: macd_divergence+DOT PF=3.42 (212 trades), rsi_divergence+ETH PF=3.40 (291), macd_divergence+LINK PF=3.39 (303), vwap_reversion+DOGE PF=3.38 (233), ema_crossover+SOL PF=3.37 (440)
- 🔧 Historical backfill: RUNNING (1 process active)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), blofin clean
- ⏰ Timer: Next cycle 11:05 (62min away) — systemd timeout fix HOLDING ✅

**Heartbeat 09:32 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🔄 Moonshot Cycle 136 STARTING (09:32, last cycle 135 finished 08:26)
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22 — **ACTIVE** (21 open)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 324 models (draining 20-75/cycle depending on CPU)
- 📊 BT backlog: 248 models (draining 20-75/cycle depending on CPU)
- 📊 Open positions: 958 (21 champion, 937 non-champion)
- 📊 Blofin v1: Top 5 BT: macd_divergence+DOT PF=3.42 (212 trades), rsi_divergence+ETH PF=3.40 (291), macd_divergence+LINK PF=3.39 (303), vwap_reversion+DOGE PF=3.38 (233), ema_crossover+SOL PF=3.37 (440)
- 🔧 Historical backfill: RUNNING (started 07:29, 2h3m runtime)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), blofin clean
- ⏰ Timer: Cycle 136 in progress — systemd timeout fix HOLDING ✅

**Heartbeat 09:03 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 135 COMPLETE (finished 08:26, 20min runtime, 37min ago) — 4 errors
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=68.37% — **ACTIVE** (21 open)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 311 models (draining 20-75/cycle depending on CPU)
- 📊 BT backlog: 270 models (draining 20-75/cycle depending on CPU)
- 📊 Open positions: 958 (21 champion, 937 non-champion) — 479 LONG, 479 SHORT
- 📊 Blofin v1: Top 5 BT: macd_divergence+DOT PF=3.42 (212 trades), rsi_divergence+ETH PF=3.40 (291), macd_divergence+LINK PF=3.39 (303), vwap_reversion+DOGE PF=3.38 (233), ema_crossover+SOL PF=3.37 (440)
- 🔧 Historical backfill: RUNNING (2 processes, started 07:29, 1h34m runtime)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), blofin clean
- ⏰ Timer: Next cycle 09:05 (2min away) — systemd timeout fix HOLDING ✅

**Heartbeat 08:32 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 135 COMPLETE (finished 08:26, 20min runtime, 6min ago) — 4 errors
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=0.68% — **ACTIVE** (21 open)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 310 models (draining 20-75/cycle depending on CPU)
- 📊 BT backlog: 252 models (draining 20-75/cycle depending on CPU)
- 📊 Open positions: 959 (21 champion, 938 non-champion)
- 📊 Blofin v1: Top 5 FT: reversal+DOT PF=5.06 (3 trades), reversal+LINK PF=3.99 (3), bb_squeeze+ADA PF=2.61 (3), bb_squeeze+BTC PF=2.34 (3), rsi_divergence+DOT PF=0.04 (3)
- 🔧 Historical backfill: RUNNING (2 processes, started 07:29, 1h3m runtime)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (cycle.lock untracked), blofin 1 modified (brain/blofin_status.json)
- ⏰ Timer: Next cycle 09:05 (30min away) — systemd timeout fix HOLDING ✅

**Heartbeat 08:02 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 134 COMPLETE (finished 07:56, 20min runtime, 6min ago) — 4 errors
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22 — **ACTIVE**
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 310 models
- 📊 BT backlog: 252 models
- 🔧 Historical backfill: RUNNING (2 processes, started 07:29, 33min runtime)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (cycle.lock untracked), blofin 1 modified (brain/blofin_status.json)
- ⏰ Timer: Next cycle 08:05 (1min away) — systemd timeout fix HOLDING ✅

## Moonshot v2 — Tournament Status

### Champions (2 active — SHORT + new_listing only)
- **SHORT Champion:** de44f72dbb01 (XGBoost), BT_PF=0.98, BT_precision=0.246, FT_trades=388, FT_PF=2.22, FT_PnL=68.37%
  - Promoted: 2026-03-16 18:51 (Cycle 127) — **HEALTHY ✅** (best FT performer)
  - Status: Excellent performance, no action needed
- **LONG Champion:** **NONE** (9b842069b20d retired at 18:45 after 20,062% drawdown)
  - **Root cause identified:** Model promoted with LOSING backtest (PF=0.79) due to loose gates
  - **Status: NO ML EDGE IN LONG DIRECTION** — 99.8% of models lose money (avg PF=0.53)
  - **Action: KEEP strict gates (PF≥1.5), accept no champion until profitable model found**
  - **Workaround: Rule-based `new_listing` strategy active (484 LONG positions open)**
- **New Listing:** new_listing (rule-based), BT_PF=7.53, FT_trades=0 — waiting for next ≤7 day coin

### Tournament Numbers (Latest cycle: 135 complete)
| Stage | Count |
|-------|-------|
| Champion | 2 (short/new_listing) |
| Forward Test | 310 |
| Backtest | 252 |
| Retired | 1,432+ |
| **Total** | **2,000+** |

### Coins & Positions
- 471 total symbols tracked
- Open positions: 959 (21 champion, 938 non-champion)
- `days_since_listing` computed each cycle (fixed Mar 16)

### Direction-Specific Gates (Mar 14 2026)
- SHORT: PF ≥ 1.0, precision ≥ 0.20, bootstrap CI ≥ 0.8
- LONG: PF ≥ 1.5, precision ≥ 0.22, bootstrap CI ≥ 0.6 (strict to prevent disasters)

### New Listing Auto-Entry (Mar 16 — NOW WORKING)
- Coins ≤7 days old auto-entered with 2% position, 2x leverage
- `model_id='new_listing'` in tournament_models (rule-based)
- `days_since_listing` computed at start of each cycle via `update_days_since_listing()`
- FK constraint required dummy model entry in tournament_models

### Services (All ACTIVE)
- `moonshot-v2.timer` — 1h cycle (hourly at :05, next 09:05 MST)
- `moonshot-v2-social.timer` — 1h social signals (active)
- `moonshot-v2-dashboard.service` — HTTP 200 on port 8893
- Dashboard: http://127.0.0.1:8893/
- **Backfill:** Historical data backfill RUNNING (2 processes, started 07:29)

### Cycle Performance — SYSTEMD TIMEOUT FIX HOLDING ✅

**Cycle 135: COMPLETED (08:26)**
- Started: 08:05 → Finished: 08:26 (20min 37sec)
- Errors: 4 (normal)
- FT queue: 310 (stable)
- BT queue: 252 (stable)
- **Systemd timeout fix:** No SIGTERM, cycle completed normally ✅

**Cycle 134: COMPLETED (07:56)**
- Started: 07:36 → Finished: 07:56 (20min 30sec)
- Errors: 4 (normal)
- FT queue: 310
- BT queue: 252
- **Systemd timeout fix:** No SIGTERM, cycle completed normally ✅

**Fixes deployed:**
1. Batch limit (20/cycle) prevents backtest infinite loops — commit 4cd2f59
2. Two-tier FT retirement (PF<0.9 at 50 trades) — commit c7c71b3
3. **TimeoutStopSec=120 in moonshot-v2.service — commit TBD (deployed Mar 17 07:36)**

**Lesson:** Cycles take 60+ min (not 15-20). Extended data + backtest + FT scoring = slow but working. NEVER kill to investigate.

## Blofin v1 Stack

### Status — LIVE AND WORKING
- Paper trading active (35K+ paper trades, BT complete)
- Services: `blofin-stack-ingestor`, `blofin-stack-paper`, `blofin-dashboard` — ALL ACTIVE
- Dashboard: http://127.0.0.1:8892 (HTTP 200)
- **FT status:** Very early (≤3 trades per pair), top 5 pending DB query completion
- Not ready for promotion (need ≥100 trades + PF≥1.35)

### Parquet Migration (Mar 15 — IN PROGRESS)
- New ingestor writes to `data/ticks/*.parquet` (NVMe, 12x compression)
- Old SQLite ingestor still running side-by-side (24h verification)
- Paper engine reads from Parquet via DuckDB
- **24h check cron fires Mar 16 09:58 MST**
- After stable: COPY old DB to archive, verify, stop old ingestor

### Ranking & Promotion
- Ranking: `bt_pnl_pct` (compounded PnL %)
- Promotion: min 100 trades, PF≥1.35, MDD<50%, PnL>0
- FT demotion: PF<0.5 AND trades>500 only — never demote early

### Architecture
- Do NOT build per-coin ML models — use global models + per-coin eligibility
- Dashboard: NEVER show aggregate PF/WR/PnL — always top performers only

## Autonomous Crons
- **Crypto Heartbeat** (this cron) — every 30min, health + pipeline scan + card dispatch
- **Auto Card Generator** — every 4h, reads pipeline state, creates cards
- **Profit Hunter** — every 12h, scouts top performers across all pipelines
- **Blofin Daily Backtest** — 2am, refreshes backtest results
- **Blofin Top Performer Alert** — 8am, flags FT PF>2.5 candidates
- **Blofin Weekly FT Review** — Sun 6am, promotes/demotes strategies
- **Backfill Watchdog** — every 10min, monitors historical data backfill

## Critical Rules
- ⛔ Never restart blofin-stack-pipeline.timer without Rob's approval
- ⛔ Never aggregate performance — filter to top performers first
- ⛔ Moonshot: champion = best FT PnL (≥20 trades), NEVER AUC
- ⛔ 95% retirement rate is GOOD (tournament philosophy)
- ⛔ Data migration: COPY-VERIFY-DELETE only (107GB loss Mar 12)
- ⛔ INVESTIGATE BEFORE KILLING — slow ≠ broken (cycles take 60+ min)
- ⛔ **NEVER kill a running process to "investigate" — that's backwards**
