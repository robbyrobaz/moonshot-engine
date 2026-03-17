# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-16 21:15 MST (Heartbeat Scan)

## Session Summary (Mar 16 2026)

**Heartbeat 21:15:**
- ✅ All services healthy (Blofin stack, Moonshot dashboard, kanban)
- ✅ Moonshot Cycle 129 COMPLETE (finished 20:35, 61min runtime, 0 errors)
- ✅ SHORT champion: de44f72dbb01 | BT_PF=0.98, FT: 388 trades, PF=2.22, PnL=68.37% — **HEALTHY ✅**
- 🚨 **LONG champion RETIRED:** 9b842069b20d retired at 18:45 (20k% drawdown, PF=0.22) — **NO REPLACEMENT**
- 🚨 **LONG pipeline DEAD:** Only 29 LONG models in FT, best has 3 trades (PF=0.00, PnL=-41%)
- ✅ New listing: 0 trades (waiting for next ≤7d coin)
- 📊 FT backlog: 269 models (draining 20/cycle)
- 📊 Open positions: 963
- 📊 Blofin v1: 0 FT trades with ≥10 completed (paper engine running, very early)
- 📊 Blofin v1: 0 ready for promotion (need ≥100 trades + PF≥1.35)
- 🔧 Builders running: 1 (Moonshot LONG recovery card dispatched, PID 2990906)
- ✅ No critical alerts from monitor
- ✅ Kanban: 0 Planned, 1 In Progress (LONG recovery)

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

## Moonshot v2 — Tournament Status

### Champions (2 active — SHORT + new_listing only)
- **SHORT Champion:** de44f72dbb01 (XGBoost), BT_PF=0.98, BT_precision=0.246, FT_trades=388, FT_PF=2.22, FT_PnL=68.37%
  - Promoted: 2026-03-16 18:51 (Cycle 127) — **HEALTHY ✅** (best FT performer)
  - Status: Excellent performance, no action needed
- **LONG Champion:** **NONE** (9b842069b20d retired at 18:45 after 20,062% drawdown)
  - Status: **PIPELINE DEAD** — only 29 LONG models in FT, best has 3 trades
  - **RECOVERY DISPATCHED:** Builder c_03cb53ba2a54_19cfa03e44f investigating (21:15)
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
