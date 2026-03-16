# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-16 13:45 MST (Heartbeat)

## Session Summary (Mar 16 2026)

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

### Champions (3 active, separate long/short/new_listing)
- **SHORT Champion:** de44f72dbb01, PF=2.22, 388 trades (active, promoted Cycle 122)
- **LONG Champion:** 6409feee2207, PF=0.00, 0 trades (promoted but never fired — under investigation)
- **New Listing:** new_listing (rule-based), PF=0.00, 0 trades

### Tournament Numbers (Cycle 122 complete, 13:08 MST)
| Stage | Count |
|-------|-------|
| Champion | 3 (short/long/new_listing) |
| Forward Test | 250 |
| Backtest | 239 (draining 20/cycle) |
| Retired | 1,432 |
| **Total** | **1,924** |

### Coins & Positions
- 471 total symbols tracked
- Open positions: 954 (auto-entry active for ≤7 day coins)
- `days_since_listing` computed each cycle (fixed Mar 16)

### Direction-Specific Gates (Mar 14 2026)
- SHORT: PF ≥ 1.0, precision ≥ 0.20, bootstrap CI ≥ 0.8
- LONG (relaxed): PF ≥ 0.7, precision ≥ 0.22, bootstrap CI ≥ 0.6

### New Listing Auto-Entry (Mar 16 — NOW WORKING)
- Coins ≤7 days old auto-entered with 2% position, 2x leverage
- `model_id='new_listing'` in tournament_models (rule-based)
- `days_since_listing` computed at start of each cycle via `update_days_since_listing()`
- FK constraint required dummy model entry in tournament_models

### Services (All ACTIVE as of 13:45)
- `moonshot-v2.timer` — 4h cycle (cycle 122 done 13:08, next ~17:08)
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

**Fixes deployed:**
1. Batch limit (20/cycle) prevents backtest infinite loops — commit 4cd2f59
2. Two-tier FT retirement (PF<0.9 at 50 trades) — commit c7c71b3

**Lesson:** Cycles take 60+ min (not 15-20). Extended data + backtest + FT scoring = slow but working. NEVER kill to investigate.

## Blofin v1 Stack

### Status — LIVE AND WORKING (13:45 Mar 16)
- Paper trading active (35K+ paper trades, BT complete)
- Services: `blofin-stack-ingestor`, `blofin-stack-paper`, `blofin-dashboard` — ALL ACTIVE
- Dashboard: http://127.0.0.1:8892 (HTTP 200)
- **FT status:** Very early (≤3 trades per pair), top 5: DOT-USDT reversal PF=5.06, LINK-USDT reversal PF=3.99, ADA-USDT bb_squeeze PF=2.61
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
t
- ⛔ Moonshot: champion = best FT PnL (≥20 trades), NEVER AUC
- ⛔ 95% retirement rate is GOOD (tournament philosophy)
- ⛔ Data migration: COPY-VERIFY-DELETE only (107GB loss Mar 12)
only (107GB loss Mar 12)
t
- ⛔ Moonshot: champion = best FT PnL (≥20 trades), NEVER AUC
- ⛔ 95% retirement rate is GOOD (tournament philosophy)
- ⛔ Data migration: COPY-VERIFY-DELETE only (107GB loss Mar 12)
12)
