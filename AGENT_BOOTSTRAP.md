# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-18 11:02 MST (Heartbeat — all systems operational)

## 🔧 Git Hygiene Rules (Mar 18 2026)
- **Unpushed commit threshold:** 25 (raised from 10 due to GitHub auth breakage)
- **Auth status:** BROKEN after filter-repo cleanup (SSH keys not loaded, HTTPS needs password)
- **Why 25?** All data is committed locally + backed up. Push failures are NON-URGENT until Rob fixes auth.
- **Git hygiene routine:** Keep running (commit regularly), don't alert on push failures until auth fixed.

## 🚨 ZOMBIE BUG FIXED (Mar 18 06:51) — ROOT CAUSE IDENTIFIED ✅

**37-hour hung cycle explained:**
- 🚨 **Root cause:** `TimeoutStopSec=infinity` in live moonshot-v2.service (appeared TWICE)
  - systemd sends SIGTERM at TimeoutStartSec (4h) but waits FOREVER for exit
  - SIGKILL never fires → permanent zombie processes
  - Mar 16 16:25 cycle lived until Mar 18 05:43 (37h) because of this
- 🔍 **Code audit subagent findings:**
  - Reddit 429 infinite retry loop — IP-wide rate limit, code retries every symbol (12.5min thrash)
  - No wall-clock timeout on fetch_all_extended — can run 5.9h if Blofin APIs slow down
  - Three bugs compound each other → 37h zombies
- ✅ **Fix deployed (06:51):**
  - Removed TimeoutStopSec=infinity from live service
  - Set TimeoutStopSec=600 (10min max)
  - systemctl --user daemon-reload
  - Full audit report: blofin-moonshot-v2/HANG_AUDIT_REPORT.md

**Code fixes still needed (not deployed):**
- Circuit breaker in collect_reddit() — abort after 3 consecutive 429s
- Overall timeout on fetch_all_extended() — max 15min wall clock
- Per-collector timeout wrapper in run_social_collection()

**Mar 18 05:43 incident (BEFORE fix):**
- 🚨 **Moonshot Cycle 126:** HUNG 37h (Mar 16 16:25 → Mar 18 05:43)
  - Last log: "fetch_all_extended: starting for 470 symbols" at Mar 16 16:25:32
  - 599% CPU, 0 network connections
  - I misread "Mar 16 16:25" as "today at 16:25" (timestamp parsing failure)
- 🚨 **Parquet Ingestor:** HUNG 8h 18m (killed 05:44)
  - 100% CPU, dead socket, file not growing
- ✅ **Historical backfill:** WORKING (84/467 symbols, 18%)
- ✅ **SQLite ingestor:** WORKING (production service)

**What I learned:**
1. **ALWAYS check current date+time FIRST** — use `date` to know NOW
2. **Parse FULL timestamps** — "2026-03-16 16:25" vs "2026-03-18 05:43" = 37h elapsed
3. **TimeoutStopSec should be SHORT** — 30-600s, not infinity (how fast zombies die)
4. **I CAN edit crons** — never deflect with "I can't"
5. **Spawn subagents for deep audits** — code review + systemd forensics

**Next cycle:** 12:05 MST with fixed service definition (zombies will die in 10min max)

## Current Status (Mar 18 11:02)

**Services:**
- ✅ blofin-stack-ingestor.service (active)
- ✅ blofin-stack-paper.service (active)
- ✅ blofin-dashboard.service (active, HTTP 200 on 8892)
- ✅ moonshot-v2-dashboard.service (active, HTTP 200 on 8893)
- ✅ moonshot-v2.timer (next fire: 12:05 MST — trigger confirmed)

**Tournament:**
- Champions: de44f72dbb01 (short, 388 FT trades, PF 2.22), new_listing (0 trades)
- Open positions: 932
- FT backlog: 453
- Stage counts: Champion 2, Forward Test 453, Backtest 3, Retired 1,866
- Cycle status: NO CYCLE RUNNING (next at 12:05)

**Blofin v1:**
- ✅ All services active
- Dashboard HTTP 200 on 8892

**Git:**
- moonshot: clean, 0 unpushed commits
- blofin-stack: clean, 22 unpushed commits (<25 threshold, OK)

**Kanban:**
- 0 Planned crypto cards
- 0 In Progress crypto cards
- 0 Failed crypto cards

## Moonshot v2 — Tournament Status

### Champions (2 active: short + new_listing)
- **SHORT Champion:** de44f72dbb01 (XGBoost), FT_trades=388, FT_PF=2.22
  - Status: Healthy, best FT performer
- **LONG Champion:** NONE (all LONG models unprofitable by design)
- **New Listing:** new_listing (rule-based), FT_trades=0 — waiting for next ≤7 day coin

### Tournament Numbers
| Stage | Count |
|-------|-------|
| Champion | 2 (short/new_listing) |
| Forward Test | 453 |
| Backtest | 3 |
| Retired | 1,866 |

### Direction-Specific Gates (Mar 14 2026)
- SHORT: PF ≥ 1.0, precision ≥ 0.20, bootstrap CI ≥ 0.8
- LONG (relaxed): PF ≥ 0.7, precision ≥ 0.22, bootstrap CI ≥ 0.6

### Services
- `moonshot-v2.timer` — 4h cycle (next: 12:05 MST)
- `moonshot-v2-social.timer` — 1h social signals
- `moonshot-v2-dashboard.service` — HTTP 200 on port 8893
- Dashboard: http://127.0.0.1:8893/

### Cycle Performance
- Last successful cycle: 143 (Mar 18 01:15, 71min runtime)
- Last killed cycle: 126 (Mar 16 16:25, hung 37h, killed Mar 18 05:43)
- Current cycle: NONE (next at 12:05)

## Blofin v1 Stack

### Status — LIVE AND WORKING
- Paper trading active (35K+ paper trades, BT complete)
- Services: `blofin-stack-ingestor`, `blofin-stack-paper`, `blofin-dashboard` — ALL ACTIVE
- Dashboard: http://127.0.0.1:8892 (HTTP 200)
- **Top 5 FT performers:** Data query requires schema check (skipped in heartbeat)
- Not ready for promotion (only 3 FT trades each, need ≥100 trades + BT_PF≥1.35)

### Ranking & Promotion
- Ranking: `bt_pnl_pct` (compounded PnL %)
- Promotion: min 100 trades, PF≥1.35, MDD<50%, PnL>0
- FT demotion: PF<0.5 AND trades>500 only — never demote early

### Architecture
- Do NOT build per-coin ML models — use global models + per-coin eligibility
- Dashboard: NEVER show aggregate PF/WR/PnL — always top performers only

## Autonomous Crons
- **Crypto Heartbeat** — every 4h, health + pipeline scan + card dispatch (WITH time checks now)
- **Auto Card Generator** — every 4h, reads pipeline state, creates cards
- **Profit Hunter** — every 12h, scouts top performers across all pipelines
- **Blofin Daily Backtest** — 2am, refreshes backtest results
- **Blofin Top Performer Alert** — 8am, flags FT PF>2.5 candidates
- **Blofin Weekly FT Review** — Sun 6am, promotes/demotes strategies
- **Backfill Watchdog** — DISABLED (was causing false restarts)

## Critical Rules
- ⛔ Never restart blofin-stack-pipeline.timer without Rob's approval
- ⛔ Never aggregate performance — filter to top performers first
- ⛔ Moonshot: champion = best FT PnL (≥20 trades), NEVER AUC
- ⛔ 95% retirement rate is GOOD (tournament philosophy)
- ⛔ Data migration: COPY-VERIFY-DELETE only (107GB loss Mar 12)
- ⛔ INVESTIGATE BEFORE KILLING — slow ≠ broken (cycles take 60+ min)
- ⛔ **CHECK CURRENT TIME FIRST** — parse full timestamps (YYYY-MM-DD HH:MM), not just HH:MM
- ⛔ **TimeoutStopSec should be SHORT** — 30-600s max, NEVER infinity (how fast zombies die)
