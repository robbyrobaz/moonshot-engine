# Crypto Agent Memory — Learnings & Reference

> This file is symlinked to `~/.openclaw/agents/crypto/agent/MEMORY.md`.
> **UPDATE THIS FILE** when you learn something new. It persists across sessions.
> Last updated: 2026-03-17 05:39 MST

## Performance Tuning (Mar 17 2026)
- **Backtest batch was hardcoded at 20** — created bottleneck when GPU/CPU had headroom
- Always check `top` and `nvidia-smi` before claiming hardware limits
- RTX 2080 Ti (8GB) at 22% util = room for 4-5x more models in parallel
- Making constants configurable (BACKTEST_BATCH_SIZE env var) > hardcoded magic numbers
- 289-model backlog drained in 12h (was 58h) after increasing batch 20→100

## Blofin Architecture (Key Decisions)

### Per-Coin Strategy (Feb 25 2026)
- Do NOT build per-coin ML models. Global models stay trained on all coins.
- Use FT performance to find winning coin+strategy pairs. Enable only those.
- `strategy_coin_performance` — 32 coins × 26 strategies, BT + FT metrics per pair
- `strategy_coin_eligibility` — 1,112 rows, live per-coin performance with blacklist

### Ranking & Promotion
- Ranking: `bt_pnl_pct` (compounded PnL %). Not EEP (dead).
- Promotion: min 100 trades, PF≥1.35, MDD<50%, PnL>0
- FT demotion: PF<0.5 AND trades>500 only — never demote early, FT data is the goal
- Paper trading reality gap: slippage 0.052%/side (2.6x worse), fill rate 67%

## Moonshot v2 Architecture

### Non-negotiables
- Champion = best FT PnL (≥20 trades), NEVER AUC
- One `compute_features()` for train, score, AND exit
- Path-dependent labels: hit +30% BEFORE -10% (long), hit -30% BEFORE +10% (short)
- All 343→471 pairs dynamic — no static coin lists
- Backtest gate (relaxed): PF ≥ 0.5, precision ≥ 0.15, trades ≥ 50
- Bootstrap CI on PF: lower bound ≥ 1.0

### New Listing Auto-Entry (Mar 16 2026 — WORKING)
- `days_since_listing` must be computed each cycle (was NULL for all coins until Mar 16 fix)
- `update_days_since_listing()` in `src/data/discovery.py`
- `model_id='new_listing'` requires entry in `tournament_models` table (FK constraint)
- Coins ≤7 days: 2% position, 2x leverage, trailing stop
- **First successful entry:** CFG-USDT at $0.1890 (Mar 16 10:45 AM)
- Feature deployed Mar 16 07:55 but didn't work until 10:45 fix

### Backtest Queue Management (Mar 16 2026)
- **Root cause of cycle hangs:** 224 models in backtest queue, `backtest_new_challengers()` processed ALL serially
- **Fix:** Added batch limit (20 models/cycle) — commit 4cd2f59
- Queue drains at 20/cycle, prevents infinite backtest loops
- Backtest stage: 1-3 min per model × 20 = 20-60 min per cycle (expected)

### Why v1 Died
Entry/exit used different feature sets. exit.py called predict_proba() without symbol/ts_ms → regime features=0.0 → all scores 0.129 → 15 profitable positions killed. v2 prevents with feature_version hashing.

## Data Migration Catastrophe (Mar 12 2026)
- blofin_monitor.db hit 107GB + 56GB WAL → disk crisis
- `mv` across filesystems = copy+delete. Mid-transfer fail → corrupt + lost
- **107GB of 3 weeks Blofin tick data PERMANENTLY LOST**
- Rule: cp + checksum + verify + then rm. Stop service first. Never background.

## Parquet Migration (Mar 15 2026)
- DuckDB + Parquet replaces SQLite for tick storage
- NVMe for hot data (ticks/*.parquet), HDD for cold (backtest_results.db, archive)
- 12x compression, 880 ticks/sec, zero DB lock contention
- 24h side-by-side verification before cutover

## Lessons
- Haiku WILL hallucinate if not forced to call APIs explicitly
- Subagents die on heavy data tasks — multi-GB loads run in main session
- Volume column in Blofin ticks is tick count, not real volume (thresholds ≤0.8)
- pandas dropna() breaks index alignment — always reset_index(drop=True)
- **Always verify service status before claiming something is broken** — "pipeline stopped" claims need `systemctl is-active` proof
- **Read current README.md from repo before making architecture claims** — don't rely on stale context

## ⛔ Moonshot Cycle Investigation Anti-Pattern (Mar 16 2026)
**NEVER kill cycles to "investigate" — they're slow (60+ min) not broken**
- Extended data: 470 symbols × 2.5 req/sec = 10+ min just for funding/OI/tickers
- Backtest: 20 models/cycle × 1-3min each = 20-60 min
- Tournament + FT scoring: 10-15 min
- **Total cycle time: 60-65 minutes (not 15-20 as originally estimated)**
- Killing mid-cycle makes it LOOK like cycles never complete — because they don't (you killed them)
- **Correct approach:** Start cycle, check back in 60+ min, verify completion in logs
- If truly hung (same stage >90min with no progress), THEN investigate — not after 10min of normal work

**Cycle 122 proof:** 12:03:19 → 13:08:10 (64min 51sec), completed successfully with 0 errors after applying batch limit fix

## ⛔ Agent File Updates (Mar 16 2026)
- **Your BOOTSTRAP.md and MEMORY.md are symlinked from the repo**
- Update `blofin-moonshot-v2/AGENT_BOOTSTRAP.md` and `AGENT_MEMORY.md` directly
- These are the files that load at session boot — keep them current!
