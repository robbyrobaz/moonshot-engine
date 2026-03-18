# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-17 19:03 MST (Heartbeat — CYCLE 140 RUNNING, TIMER BROKEN)

## 🚨 HEARTBEAT STATUS (Mar 17 19:03) — CRITICAL: TIMER MISCONFIGURED
- ✅ **All services active:** blofin-stack-ingestor, blofin-stack-paper (activating), blofin-dashboard, moonshot-v2-dashboard
- 🔄 **Moonshot Cycle 140:** Started 18:03, running 60min (backtesting 25/75 done) — HEALTHY
- ✅ **SHORT champion:** de44f72dbb01 (388 trades, PF=2.22) — HEALTHY
- ⚠️ **LONG champion MISSING:** no profitable LONG models (by design)
- 📊 **Backtest queue:** 75 models (stable)
- 📊 **FT queue:** 410 models (+7 from last heartbeat)
- ✅ **Git status:** moonshot clean (catboost logs), blofin-stack 12 unpushed commits (>10 threshold, PUSH NEEDED)
- ✅ **Kanban:** 0 Planned, 0 In Progress, 0 Failed — no work needed
- ✅ **Critical alerts:** None
- 🔧 **Historical backfill:** PID 643188 running (started 18:58, 1-worker mode)
- 🚨 **CRITICAL ISSUE:** Timer has dual OnCalendar (hourly + *:05:00) — systemd disabled it (Trigger: n/a)

## 🚨 TIMER MISCONFIGURATION (Mar 17 19:03) — DUAL OnCalendar BREAKS SYSTEMD
- **Root cause:** Timer has TWO OnCalendar directives (hourly + *-*-* *:05:00)
- **Systemd behavior:** Multiple OnCalendar = systemd disables timer (shows "Trigger: n/a")
- **Result:** No automatic cycles fire — Cycle 140 only started because timer was restarted at 18:03
- **Fix needed:** Remove `OnCalendar=hourly`, keep only `OnCalendar=*-*-* 00/4:05:00` (4-hour schedule)
- **Current state:** Cycle 140 running manually, will NOT restart when it finishes
- **Timer file:** `/home/rob/.config/systemd/user/moonshot-v2.timer`
- **Previous issue (RESOLVED):** Cycles take 195+ min, hourly timer killed them — now timer just doesn't fire at all

## 🚀 PERFORMANCE FIX (Mar 17 05:47) — HOURLY CYCLES + DYNAMIC BACKTESTING
- **Cycle interval changed:** 4h → **1h** (hourly at :05)
- **Backtest batch now DYNAMIC** based on CPU load (commit d71f08c, 707e591)
  - CPU < 70%: batch 100 models (max throughput)
  - CPU ≥ 70%: batch 10 models (throttle to prevent overload)
  - Uses 1-min load average / core count (psutil)
- **Result:** Queue drains 75/hour when CPU idle (was growing +5/4h)
- **CRITICAL:** Timer schedule was NOT updated until Mar 17 18:03 (ca4700a)

## Session Summary (Mar 17 2026)

**Heartbeat 17:33 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🚨 Moonshot Cycle 139: KILLED at 17:06 (195min runtime, threshold was 180min)
- 🔧 **Watchdog fix deployed:** Threshold raised 180min → 240min (commit 88ff10d)
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=68.37% — **ACTIVE**
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 402 models (+1 from last heartbeat)
- 📊 BT backlog: 75 models (draining, -2 from last heartbeat)
- 🔧 Historical backfill: PID 451926 running (started 17:08, 25min, parquet work)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot pushed (88ff10d), blofin 8 unpushed commits (<10 threshold)
- 📊 Blofin v1 Top 5 BT: reversal+BTC PF=2.23 (395), high_volume_reversal+ETH PF=1.26 (118), reversal+MATIC PF=1.85 (364), mtf_ensemble+LINK PF=3.28 (455), macd_divergence+DOGE PF=1.83 (286)
- 🎯 **Lesson:** Cycle duration grows with queue size (75 BT models × 2-3min = 150-225min). Next cycle at 20:05 with 240min threshold.

**Heartbeat 17:03 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🔄 Moonshot Cycle 139 IN PROGRESS (started 13:51, 3h 12min runtime) — backtesting model 1dcda8e22eae, normal progress
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22, PnL=68.37% — **ACTIVE**
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 401 models (+9 from last heartbeat)
- 📊 BT backlog: 77 models (draining well, -31 from last heartbeat)
- 🔧 Historical backfill: PID 406340 running (started 16:38, 27min, parquet work)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), blofin 8 unpushed commits (<10 threshold)
- 🎯 **Cycle 139 proving watchdog fix:** 192min runtime (3h 12min), no kill → threshold increase VERIFIED ✅

**Heartbeat 16:01 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🔄 Moonshot Cycle 139 IN PROGRESS (started 13:51, 2h 10min runtime) — backtesting model 37603ff3e4fd, normal progress
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22 — **ACTIVE**
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 392 models (stable)
- 📊 BT backlog: 108 models (draining)
- 🔧 Historical backfill: COMPLETE (processes ended)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), **blofin CORRUPTED INDEX** (escalated to Jarvis), 5 unpushed commits
- 📊 Blofin v1 Top 5 BT: macd_divergence+DOT PF=3.42 (212), rsi_divergence+ETH PF=3.40 (291), macd_divergence+LINK PF=3.39 (303), vwap_reversion+DOGE PF=3.38 (233), ema_crossover+SOL PF=3.37 (440)
- 📊 Blofin v1 Top 5 FT: reversal+DOT PF=5.06 (3), reversal+LINK PF=3.99 (3), bb_squeeze+ADA PF=2.61 (3), bb_squeeze+BTC PF=2.34 (3), rsi_divergence+DOT PF=0.04 (3)
- 🎯 **Cycle 139 proving watchdog fix:** 130min runtime, no kill → threshold increase WORKING ✅

**Heartbeat 15:33 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- 🔄 Moonshot Cycle 139 IN PROGRESS (started 13:51, 1h 43min runtime) — backtesting, normal progress
- ✅ **WATCHDOG FIX VERIFIED:** Cycle 139 survived 103min (old threshold=90min, new=180min) — fix WORKING ✅
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22 — **ACTIVE**
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 388 models (stable)
- 📊 BT backlog: 126 models (draining)
- 🔧 Historical backfill: COMPLETE (processes ended)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed
- 🔧 Git: moonshot clean (catboost logs only), blofin 1 modified (today's parquet), 4 unpushed commits
- 📊 Blofin v1 Top 5 BT: reversal+BTC PF=2.23 (395), high_volume_reversal+ETH PF=1.26 (118), reversal+MATIC PF=1.85 (364), mtf_ensemble+LINK PF=3.28 (455), macd_divergence+DOGE PF=1.83 (286)
- 📊 Blofin v1 Top 5 FT: reversal+DOT PF=5.06 (3), reversal+LINK PF=3.99 (3), bb_squeeze+ADA PF=2.61 (3), bb_squeeze+BTC PF=2.34 (3), rsi_divergence+DOT PF=0.04 (3)
- 🎯 **Cycle 138 resolution:** Killed at 13:51:48 by OLD watchdog threshold (105min runtime, threshold was 90min). Script updated 14:38 → new 180min threshold deployed. Cycle 139 is first to run under new threshold.

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

### Tournament Numbers (Latest cycle: 139 in progress)
| Stage | Count |
|-------|-------|
| Champion | 2 (short/new_listing) |
| Forward Test | 392 |
| Backtest | 108 |
| Retired | 1,432+ |
| **Total** | **2,000+** |

### Coins & Positions
- 471 total symbols tracked
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
- `moonshot-v2.timer` — 4h cycle (OnCalendar=*-*-* 00/4:05:00)
- `moonshot-v2-social.timer` — 1h social signals (active)
- `moonshot-v2-dashboard.service` — HTTP 200 on port 8893
- Dashboard: http://127.0.0.1:8893/
- **Backfill:** Historical data backfill IN PROGRESS (PID 406340, started 16:38)

### Cycle Performance — SYSTEMD TIMEOUT FIX HOLDING ✅

**Cycle 139: IN PROGRESS (started 13:51)**
- Runtime so far: 2h 10min (130min)
- Status: Actively backtesting (last log 16:00 — model 37603ff3e4fd)
- **Watchdog fix proven:** Survived past old 90min threshold, still running at 130min ✅
- FT queue: 392 (stable)
- BT queue: 108 (draining)

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
4. **Watchdog threshold 90min → 180min — commit 64584d1 (deployed Mar 17 14:38)**

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
gration: COPY-VERIFY-DELETE only (107GB loss Mar 12)
- ⛔ INVESTIGATE BEFORE KILLING — slow ≠ broken (cycles take 60+ min)
- ⛔ **NEVER kill a running process to "investigate" — that's backwards**
