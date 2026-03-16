# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-16 12:05 MST

## Moonshot v2 — Tournament Status

### Champion
- **Model:** 2321094c8072 (short)
- **FT PF:** 1.42, 407 trades, +0.40% FT PnL
- **Updated:** 2026-03-16 11:24 MST

### Tournament Numbers
| Stage | Count |
|-------|-------|
| Champion | 1 |
| Forward Test | 280 (⚠️ backlog, threshold 50) |
| Backtest | 243 |
| Retired | 1,363 |
| **Total** | **1,889** |

### Coins
- 471 total, 3 ≤7 days old
- 668 open positions (1 new_listing auto-entry)
- `days_since_listing` now computed each cycle (fixed Mar 16)

### Direction-Specific Gates (Mar 14 2026)
- SHORT: PF ≥ 1.0, precision ≥ 0.20, bootstrap CI ≥ 0.8
- LONG (relaxed): PF ≥ 0.7, precision ≥ 0.22, bootstrap CI ≥ 0.6

### New Listing Auto-Entry (Mar 16 — NOW WORKING)
- Coins ≤7 days old auto-entered with 2% position, 2x leverage
- `model_id='new_listing'` in tournament_models (rule-based)
- `days_since_listing` computed at start of each cycle via `update_days_since_listing()`
- FK constraint required dummy model entry in tournament_models

### Services
- `moonshot-v2.timer` — 4h cycle (running normally, 2500MB RAM backtest load)
- `moonshot-v2-social.timer` — 1h social signals
- `moonshot-v2-dashboard.service` — ACTIVE (port 8893)
- Dashboard: http://127.0.0.1:8893/ (HTTP 200)

### Cycle Performance (Mar 16 12:15 MST)

**Current cycle:** 122 (started 12:03, in progress — extended data fetch stage)
**Expected completion:** ~12:20 (15-20 min normal for 470 symbols)

**Recent fixes:**
1. FT backlog reduction: Two-tier retirement (PF<0.9 at 50 trades) — commit c7c71b3
2. Extended data fetch: 10+ min/cycle expected (470 symbols × rate limits)
3. Batch limit: 20 models/cycle for backtest (prevents RAM overload)

**Lesson:** LET CYCLES COMPLETE. They're slow (15-20 min) but not broken.

## Blofin v1 Stack

### Status
- Paper trading active (86K+ trades)
- **Pipeline timer STOPPED** per Rob's order — do not restart without approval
- Services: ingestor, paper engine, dashboard all ACTIVE

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
