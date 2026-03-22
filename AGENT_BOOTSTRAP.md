# Crypto Agent Bootstrap

> This file is symlinked to `~/.openclaw/agents/crypto/agent/BOOTSTRAP.md`.
> **UPDATE THIS FILE** (not the symlink) when state changes. It auto-loads every session.
> Last updated: 2026-03-21 06:37 MST (Tick ingestor retired)

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

## Current Status (Mar 21 20:03 MST)

### 🚨 ACTIVE WORK IN PROGRESS — DO NOT DISRUPT

**1. THREE PARALLEL OHLCV BACKFILLS RUNNING:**
All output to `/mnt/data/blofin_ohlcv/1m/{SYMBOL}.parquet` (same schema, same dir)
No symbol overlap between sources — each handles unique coins only.
- **Binance.US** (`scripts/ohlcv_backfill_binanceus.py`): ✅ 137/146 DONE, finishing last 9
  - 16 req/sec (1 weight/req, 1200 weight/min limit). Log: `tail -f logs/ohlcv_backfill_binanceus.log`
- **OKX** (`scripts/ohlcv_backfill_okx.py`): ~55/121, ETA ~midnight tonight
  - ~3.5 req/sec (network latency bottleneck). Log: `tail -f logs/ohlcv_backfill_okx.log`
- **Blofin** (`scripts/ohlcv_backfill_v3.py`): ~17/182, Blofin-exclusive coins only, ETA ~Monday
  - 0.3 req/sec (strict rate limit). Reads `scripts/symbols_blofin_only.txt`. Log: `tail -f logs/ohlcv_backfill.log`
- **~244 symbols completed, 1.4GB total so far**
- Check: `ls /mnt/data/blofin_ohlcv/1m/ | wc -l` and `ps aux | grep ohlcv`
- Validate: `python3 scripts/validate_ohlcv_data.py`
- **DO NOT start additional API processes — each source at its rate limit**

**2. BACKTEST SWEEP RUNNING (PID 1385735):**
- Script: `scripts/run_full_backtest_sweep.py`
- **720 tasks:** 16 strategies × 45 top symbols × 365 days of OHLCV data
- 12 CPU workers at ~90% each
- Writing to `strategy_backtest_results` + `strategy_coin_performance` in `/mnt/data/blofin_monitor.db`
- Promotion gates: PF≥1.35, ≥100 trades, MDD<50%, PnL>0
- Log: `tail -f logs/backtest_run.log`
- ETA: ~8 PM MST (1-2 hours)
- **After complete:** Top performers need manual review, then ML training on GPU

**3. Monitoring Cron:** `Blofin Recovery Monitor` (every 30 min, Opus, webchat)
- Cron ID: `389c6fbd-d986-4fff-843c-49ffc1bb4d32`

### Heartbeat (Mar 22 00:03)
- ✅ Moonshot dashboard: HTTP 200
- ✅ Services healthy
- ✅ No cycle running (last likely completed normally)
- 🏆 Champion: de44f72dbb01 (short) — 388 FT trades, PF 2.22, $0.68 PnL
- 🧪 FT backlog: 0 models
- 📊 Open positions: 938
- 📂 Candles: In DB (938,674 rows)

### Blofin v1 Pipeline Status
- ❌ Tick ingestor RETIRED (no proven value, 48% CPU, 650GB/mo)
- ❌ All tick databases DELETED (55GB freed)
- ✅ blofin-dashboard.service RUNNING (port 8892) — DB has restored strategy data but no live trades yet
- ❌ blofin-stack-ingestor.service DISABLED (needs new 1-min candle poller, not built yet)
- ❌ blofin-stack-paper.service DISABLED (code updated, waiting for backtests to identify tier≥2 pairs)
- ✅ Strategy code + ML models intact in git

### Code Changes Deployed (Mar 21):
- ✅ DuckDB adapter reads OHLCV from `/mnt/data/blofin_ohlcv/1m/` (commit e9bd5bc)
- ✅ Backtester reads 1-min OHLCV directly (no tick aggregation)
- ✅ **Per-coin BT gate fix** — paper engine ONLY trades tier≥2 symbols
- ✅ 3 backfill scripts + validator committed (commit 8e1ff05)
- ✅ Full backtest sweep script (commit by builder)
- 📋 Refs: `TASK_COMPLETION_OHLCV_MIGRATION.md`, `BACKTEST_SWEEP_STATUS_2026_03_21.md`

### What Blofin v1 Found (PROFITABLE — don't dismiss!)
Top performers from Mar 1 report (20+ FT trades each):
- cross_asset_correlation / INJ-USDT: PF 4.41, 26.56% PnL, 5x leverage
- orderflow_imbalance / AAVE-USDT: PF 3.91, 11.19% PnL, 5x leverage  
- momentum / JTO-USDT: PF 3.80, 42.42% PnL, 5x leverage
- cross_asset_correlation / JUP-USDT: PF 3.24, 10.14% PnL, 3x leverage
Full report: `blofin-stack/STRATEGY_RECOVERY_REPORT.md`

### Recovery Plan
1. ✅ OHLCV backfill: 244/473 done (3 parallel sources), Binance.US nearly complete
2. ✅ Pipeline code updated for OHLCV (adapter, backtester, eligibility)
3. ⏳ Backtest sweep RUNNING (720 tasks, 12 workers, ETA ~8 PM)
4. ⏸️ After backtests: GPU ML training (XGBoost/CatBoost on RTX 2080 Super)
5. ⏸️ Build new 1-min candle poller (replaces tick ingestor) for live data
6. ⏸️ Start paper engine → accumulate FT trades → dashboard shows winners
7. 📋 Key plans: `brain/DATA_ARCHITECTURE_FINAL.md`, `docs/FT_PIPELINE_DIAGNOSIS_2026_03_16.md`

### GPU Available
- NVIDIA RTX 2080 Super (8GB VRAM)
- XGBoost GPU: `{'tree_method': 'hist', 'device': 'cuda'}` ✅
- CatBoost GPU: `task_type='GPU'` ✅
- PyTorch 2.10.0 + CUDA 13.1 ✅

### Data Inventory
- `/mnt/data/blofin_ohlcv/1m/` — NEW proper OHLCV parquet (backfill in progress)
- `/mnt/data/blofin_tickers/raw/` — OLD ticker snapshots (last_price only, NOT OHLCV, 3.5GB, 473 symbols)
- `/mnt/data/blofin_monitor.db` — EMPTY (fresh DB, no historical data)

### Moonshot v2
- ✅ moonshot-v2-dashboard.service (active, HTTP 200 on 8893)
- ✅ moonshot-v2.timer (4h cycle)
- ✅ Incremental feature computation FIX deployed (64min → <10min cycles)
- **Timeframe: 4-HOUR candles** (`CANDLE_INTERVAL = "4H"`) — NOT 1-min, NOT ticks

**Tournament:**
- Champions: 2 (short + new_listing)
- FT Backlog: 0
- Open positions: 943

**Blofin v1:**
- ❌ All services RETIRED (Mar 21)

**Candle Data:**
- 938,674 rows across 472 symbols in DB
- Coverage: Jul 2024 - Mar 2026 (current)

**Git:**
- moonshot: clean, 0 unpushed commits

## Moonshot v2 — Tournament Status

### Champions (2 active: short + new_listing)
- **SHORT Champion:** de44f72dbb01 (XGBoost), FT_trades=388, FT_PF=2.22
  - Status: Healthy, best FT performer
- **LONG Champion:** NONE (all LONG models unprofitable by design)
- **New Listing:** new_listing (rule-based), FT_trades=0 — waiting for next ≤7 day coin

### Tournament Numbers (Mar 21 20:03)
| Stage | Count |
|-------|-------|
| Champion | 2 (short + new_listing) |
| Forward Test | 609 |
| Open Positions | 943 |
| FT Backlog | 609 |

### Direction-Specific Gates (Mar 14 2026)
- SHORT: PF ≥ 1.0, precision ≥ 0.20, bootstrap CI ≥ 0.8
- LONG (relaxed): PF ≥ 0.7, precision ≥ 0.22, bootstrap CI ≥ 0.6

### Services
- `moonshot-v2.timer` — 4h cycle (next: 12:05 MST)
- `moonshot-v2-social.timer` — 1h social signals
- `moonshot-v2-dashboard.service` — HTTP 200 on port 8893
- Dashboard: http://127.0.0.1:8893/

### Cycle Performance
- Last cycle: Unknown (dashboard accessible, DB healthy)
- Current cycle: NONE (next at 12:05 MST)
- Tournament stable: 95.8% retirement rate, 2 champions

## Blofin v1 Stack

### Status — PIPELINE DEAD (Mar 20 21:43)
- **blofin-stack-pipeline.timer:** STOPPED since Mar 16 08:21 (4d ago)
- **blofin-stack-pipeline.service:** FAILED (timeout) on Mar 18 14:22
- Paper trading: Last trade 23h ago (limping on stale data)
- Dashboard: http://127.0.0.1:8892 (HTTP 200)
- **Last backtest update:** Mar 17 19:34 (3.1d ago)
- **Last FT update:** Mar 16 15:58 (4.2d ago)
- **Diagnosis:** Timer was stopped, Rob's approval required to restart (BOOTSTRAP rule)

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
