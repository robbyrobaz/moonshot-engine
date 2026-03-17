# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-17 00:33 MST (Heartbeat — All Systems Healthy)

## Session Summary (Mar 17 2026)

**Heartbeat 00:33 (Mar 17):**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 130 COMPLETE (finished 21:53, 51min runtime, 0 errors, 2h40min ago)
- ✅ SHORT champion: de44f72dbb01 | FT: 388 trades, PF=2.22 — **ACTIVE** (15 open, 1 new in last 4h)
- 🚨 **LONG champion:** NONE (by design — 99.8% of LONG models lose money, avg PF=0.53)
- ✅ New listing champion: active, 0 FT trades (waiting for next ≤7d coin)
- 📊 FT backlog: 283 models (draining 20/cycle)
- 📊 BT backlog: 295 models (draining 20/cycle)
- 📊 Open positions: 962 (15 champion, 947 non-champion)
- 📊 Blofin v1: paper engine running, FT data accumulating (very early stage)
- 🔧 Historical backfill: batch 122, ~176K candles (ongoing since Mar 15)
- 🔧 Builders running: 0
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 0 In Progress, 0 Failed, 0 crypto builders active

**Heartbeat 00:02 (Mar 17):**
- ✅ All systems healthy (same status as 00:33, pre-batch-122)

**Heartbeat 23:32 (Mar 16):**
- ✅ All systems healthy (same status as above, pre-cycle-130 completion)

**Major fixes deployed:**
1. ✅ Moonshot cycle hangs RESOLVED — batch limit (20 models/cycle) prevents backtest infinite loops
2. ✅ New listing auto-entry WORKING — `days_since_listing` computation fixed, CFG-USDT entered
3. ✅ Cycle 122 completed: 64min, 0 errors, champion promoted (de44f72dbb01 PF 2.22)
4. ✅ Historical backfill running: 107/469 symbols (22.8%), ~60h remaining
5. ✅ Agent context persistence: all 5 files × 3 agents symlinked to repos (edits persist, git-tracked)

**Critical lessons learned:**
- ⛔ **INVESTIGATE BEFORE KILLING** — slow ≠ broken. Moonshot cycles take 60+ min by design.
- ⛔ Blofin v1 is LIVE — never claim "pipeline stopped" without checking services first
- ⛔ Always verify current state before making claims about what's running/broken

## LONG Pipeline Investigation (Mar 16 22:30) — ROOT CAUSE FOUND

**TL;DR: LONG ML models fundamentally don't work. Only 0.2% profitable (2/1,013). Keep strict gates, accept no champion.**

### Why Champion 9b842069b20d Failed
- **Promoted with LOSING backtest:** BT PF=0.79 (loses $1.27 per $1 won)
- **Gates too loose at promotion time:** MIN_BT_PF_LONG=0.3 (commit 905b3bf, Mar 16)
- **Catastrophic FT failure:** PF=0.22, 39 trades, 20k% drawdown
- **Fix deployed:** Gates tightened to MIN_BT_PF_LONG=1.5 (commit 03609b1, Mar 16)

### Why 0% Pass Rate (0/1,013 Models)
**Current gates (config.py):**
- MIN_BT_PF_LONG = 1.5 (require profitable backtest)
- MIN_BT_PRECISION_LONG = 0.20
- BOOTSTRAP_PF_LOWER_BOUND_LONG = 0.7

**PF Distribution across 1,013 LONG models:**
- PF ≥ 1.5 (current gate): **0 models (0.0%)**
- PF 1.0-1.5 (marginal profit): **2 models (0.2%)** — best is 1.26
- PF 0.7-1.0 (losing): 24 models (2.4%)
- PF 0.5-0.7 (bad): 615 models (60.7%)
- PF < 0.5 (catastrophic): 202 models (19.9%)
- **Average PF: 0.53** (lose $1.88 per $1 won)
- **Max PF: 1.26** (only one model, already retired)

### Fundamental Problem: No Edge in LONG Direction
- **99.8% of LONG models lose money** (PF < 1.0)
- Best model ever: PF=1.26, precision=0.17, trades=2556 (retired)
- 29 LONG models in FT, best has only 3 trades
- Market condition: altcoin longs struggle in neutral/bear regime (Q3-Q4 2025)

### Recommendation: Accept Reality ✅
**KEEP current strict gates (MIN_BT_PF_LONG=1.5):**
- ✅ Prevents unprofitable champion disasters (like 9b842069b20d)
- ✅ Accept 0% promotion rate until market changes
- ✅ Keep generating LONG challengers (data collection for regime shifts)
- ✅ Rule-based `new_listing` strategy works (484 LONG positions open)
- ✅ Aligned with tournament philosophy: "find models that ARE profitable"

**DO NOT lower gates to allow losing models through:**
- ❌ Philosophy gates (PF≥0.7) only pass 2 models, both LOSE money (PF 0.79, 0.70)
- ❌ Lowering to PF≥1.0 allows 2 marginal models (PF 1.08, 1.26) — high failure risk
- ❌ Widening gates caused 9b842069b20d disaster (PF 0.79→0.22 catastrophic failure)

**Status:** LONG ML pipeline on hold (by design). No champion until profitable model found.

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

### Tournament Numbers (Cycle 122 complete, 13:08 MST)
| Stage | Count |
|-------|-------|
| Champion | 3 (short/long/new_listing) |
| Forward Test | 251 |
| Backtest | running (cycle 123) |
| Retired | 1,432+ |
| **Total** | **1,900+** |

### Coins & Positions
- 471 total symbols tracked
- Open positions: 928 (auto-entry active for ≤7 day coins)
- `days_since_listing` computed each cycle (fixed Mar 16)

### Direction-Specific Gates (Mar 14 2026)
- SHORT: PF ≥ 1.0, precision ≥ 0.20, bootstrap CI ≥ 0.8
- LONG (relaxed): PF ≥ 0.7, precision ≥ 0.22, bootstrap CI ≥ 0.6

### New Listing Auto-Entry (Mar 16 — NOW WORKING)
- Coins ≤7 days old auto-entered with 2% position, 2x leverage
- `model_id='new_listing'` in tournament_models (rule-based)
- `days_since_listing` computed at start of each cycle via `update_days_since_listing()`
- FK constraint required dummy model entry in tournament_models

### Services (All ACTIVE as of 14:15)
- `moonshot-v2.timer` — 4h cycle (cycle 123 running, started 13:54)
- `moonshot-v2-social.timer` — 1h social signals (active)
- `moonshot-v2-dashboard.service` — HTTP 200 on port 8893
- Dashboard: http://127.0.0.1:8893/
- **Backfill:** Historical data backfill completed or inactive (moonshot_v2.db is 5.7GB)

### Cycle Performance — RESOLVED (Mar 16 13:08 MST)

**Cycle 122: COMPLETED SUCCESSFULLY ✅**
- Started: 12:03:19 → Finished: 13:08:10 (64min 51sec)
- Errors: 0
- Champion promoted: de44f72dbb01 (PF 2.22, 388 trades)
- Backtest queue: 239 (draining 20/cycle)
- FT queue: 250 (down from 289)

**Cycle 123: IN PROGRESS (started 13:54)**
- 23min in, backtest stage
- 1 model passed (8115993d3977 → FT), 1 failed (c29ceb6f4acd → retired)

**Fixes deployed:**
1. Batch limit (20/cycle) prevents backtest infinite loops — commit 4cd2f59
2. Two-tier FT retirement (PF<0.9 at 50 trades) — commit c7c71b3

**Lesson:** Cycles take 60+ min (not 15-20). Extended data + backtest + FT scoring = slow but working. NEVER kill to investigate.

## Blofin v1 Stack

### Status — LIVE AND WORKING (14:15 Mar 16)
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
- **Crypto Heartbeat** (this cron) — every 4h, health + pipeline scan + card dispatch
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
