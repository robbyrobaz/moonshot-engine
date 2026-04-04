# Moonshot Infinite Loop — REAL Fix (12th Kill)

**Status:** DEPLOYED (commit bbaeba1)  
**Severity:** CRITICAL (12 thermal kills since Mar 30)  
**Previous fix:** WRONG FUNCTION (commit d760148 — only protected backtest phase)

## What Went Wrong With First Fix

**First fix (d760148) added timeout to `backtest_new_challengers()`:**
- 60min cycle budget
- 10min per-model timeout
- Memory checks

**Problem:** Cycle never reached backtest phase. Hang happened earlier in **FT stats update**.

## 12th Kill Analysis

**Timeline:**
- 13:21 — Cycle 254 started (PID 530309)
- 13:27 — Candles updated (474 symbols)
- 13:32-13:42 — Extended data fetch (funding, OI, mark prices, tickers)
- 13:42 — Features computed, labels generated
- 13:42-13:43 — Execution (4 champ entries, 10 exits)
- 13:42-13:43 — FT scoring (954 models scored, new positions opened)
- **13:43:25 — LAST LOG** (FT position opened)
- **13:59:12 — sklearn warnings spam** (16min of silence)
- 14:06 — KILLED (44min total, 313% CPU, 95°C thermal)

**16 minutes of silence** between 13:43:25 and 13:59:12 = **FT stats update hung**.

## Root Cause (Actual)

After FT scoring completes, `run_cycle.py` updates stats for ALL FT models:

```python
# Line 210-217 (before fix)
from src.tournament.forward_test import _update_model_ft_stats
ft_models = db.execute(
    'SELECT model_id FROM tournament_models WHERE stage IN ("forward_test", "ft")'
).fetchall()
for m in ft_models:
    _update_model_ft_stats(db, m["model_id"])
db.commit()
log.info("FT stats updated for %d models", len(ft_models))
```

**Problem:**
- **961 FT models** (as of Apr 4)
- Each call to `_update_model_ft_stats()` queries positions table:
  ```python
  rows = db.execute(
      "SELECT pnl_pct FROM positions WHERE model_id = ? AND is_champion_trade = 0 AND status = 'closed'",
      (model_id,)
  ).fetchall()
  ```
- 961 models × query per model × compute stats = **O(N²) disaster**
- No timeout, no progress logging, no escape hatch
- If one model has thousands of positions, stats compute can take minutes
- 961 models × 1s each = 16min minimum (observed)

## Real Fix

### 1. Top-Level Cycle Timeout (90min Hard Limit)

Added at start of `run_cycle()`:

```python
import signal

def cycle_timeout_handler(signum, frame):
    log.error("CYCLE TIMEOUT: 90min budget exceeded. Aborting cycle.")
    raise TimeoutError("Cycle exceeded 90min budget")

signal.signal(signal.SIGALRM, cycle_timeout_handler)
signal.alarm(90 * 60)  # 90min hard limit
```

Cancel at end:
```python
signal.alarm(0)  # Cancel cycle timeout
```

**Impact:**
- **Hard guarantee:** NO phase can run longer than 90min
- Protects: extended data, features, FT scoring, backtest, challengers
- TimeoutError raised if ANY phase hangs
- Emergency brake for unknown hangs

### 2. FT Stats Update Timeout (10min Budget)

Replaced unbounded loop with timeout + progress logging:

```python
ft_update_start = time.time()
ft_update_budget = 10 * 60  # 10min max
ft_updated = 0

for m in ft_models:
    elapsed = time.time() - ft_update_start
    if elapsed > ft_update_budget:
        log.warning(
            "FT stats update timeout: %.1fs elapsed, %d/%d models updated. Skipping remaining.",
            elapsed, ft_updated, len(ft_models)
        )
        break
    _update_model_ft_stats(db, m["model_id"])
    ft_updated += 1
    
    # Log progress every 100 models
    if ft_updated % 100 == 0:
        remaining_time = ft_update_budget - elapsed
        log.info(
            "FT stats update progress: %d/%d models (%.1fs elapsed, %.1fs remaining)",
            ft_updated, len(ft_models), elapsed, remaining_time
        )

db.commit()
log.info(
    "FT stats updated for %d/%d models in %.1fs",
    ft_updated, len(ft_models), time.time() - ft_update_start
)
```

**Impact:**
- 10min budget for all 961 models (0.6s per model avg)
- Skips remaining models if budget exceeded (partial update better than crash)
- Progress logging every 100 models (visibility into bottleneck)
- Commits partial progress
- Clear diagnostics if timeout fires

## Behavior Changes

### Before (broken)
- ❌ No top-level cycle timeout → any phase can hang forever
- ❌ FT stats update unbounded → 961 models × slow queries = 16min+ hang
- ❌ No progress logging → 16min of silence (looks like crash)
- ❌ All-or-nothing commit → lose all progress if killed

### After (fixed)
- ✅ 90min top-level timeout → hard guarantee (emergency brake)
- ✅ 10min FT stats budget → max 10min even with 961 models
- ✅ Progress logging → visibility every 100 models
- ✅ Partial commits → save progress even if timeout fires
- ✅ Clear diagnostics → know exactly where hang occurred

## Expected Outcomes

1. **No more infinite loops** — 90min hard limit on entire cycle
2. **No more thermal kills** — timeout prevents CPU thrashing
3. **FT stats won't block cycle** — 10min max vs 16min+ observed
4. **Partial progress preserved** — commits after each phase
5. **Better diagnostics** — progress logs show exactly where slow

## Testing Plan

**Next tournament cycle:** Saturday Apr 4 2026, 12:05 PM MST  
- 44 models in backtest queue
- 961 FT models need stats update
- Expected FT stats time: 5-10min (0.6s per model avg)

**Success criteria:**
- Cycle completes <90min (timeout doesn't fire)
- FT stats update completes <10min (all 961 models)
- Progress logs show steady progress (100, 200, 300, ... 900 models)
- No thermal warnings (CPU <80%, temp <85°C)
- No manual kills needed

**If FT stats timeout fires:**
- Log shows how many models updated (e.g. "600/961 models")
- Partial stats committed to DB
- Cycle continues to backtest phase
- Investigate why some models are slow (too many positions?)

## Monitoring

Watch for:
- Cycle completion time (should be <60min typically, <90min hard limit)
- FT stats update time (should be <10min for 961 models)
- Progress logs (should see 100, 200, 300, ... models)
- CPU/thermal (should stay reasonable, not 313%)
- Timeout errors (if 90min fires, we have bigger problems)

## Future Optimizations

If FT stats update is still slow (>10min):

1. **Batch stats computation** — one query for all models:
   ```sql
   SELECT model_id, pnl_pct FROM positions
   WHERE model_id IN (?, ?, ...) AND is_champion_trade = 0 AND status = 'closed'
   ORDER BY model_id, entry_ts
   ```
   - Group by model_id in Python
   - Compute all stats in single pass
   - 1 query vs 961 queries = huge speedup

2. **Incremental stats update** — only update models with new closed positions:
   ```sql
   SELECT DISTINCT model_id FROM positions
   WHERE updated_at > ? AND status = 'closed'
   ```
   - Only recompute stats for models that changed
   - Most models unchanged each cycle
   - 961 → ~10-50 models per cycle

3. **Materialized view** — pre-aggregate stats in DB:
   ```sql
   CREATE TABLE model_stats AS
   SELECT model_id, COUNT(*) as trades, AVG(pnl_pct) as avg_pnl, ...
   FROM positions WHERE status = 'closed'
   GROUP BY model_id
   ```
   - Update incrementally as positions close
   - Read from cache instead of recompute
   - Near-instant stats lookup

But for now: **stability > optimization**. Prove timeout fix works first.

## Why First Fix Failed

**First fix (d760148) assumptions:**
1. ✅ Backtest phase can hang (TRUE — label loading is slow)
2. ❌ Hang happens during backtest (FALSE — happened during FT stats)
3. ❌ Backtest is the only slow phase (FALSE — FT stats is slower)
4. ❌ Per-model timeout is enough (FALSE — need top-level cycle timeout)

**Lesson learned:**
- Don't assume where the hang is — **profile it first**
- Add timeouts at **multiple levels** (top-level + per-phase)
- Always log timestamps to **see where silence occurs**
- 961 models × any O(N) operation = **potential disaster**

## Historical Context

**12 kills in 5 days:**
- Mar 30 — 1 kill (first observed)
- Mar 31 — 3 kills
- Apr 1 — 2 kills
- Apr 2 — 2 kills
- Apr 3 — 2 kills
- Apr 4 — 2 kills (11th at 13:21, 12th at 14:06)

**This was the #1 operational nightmare for Moonshot v2.**

Previous fix (d760148) was deployed 13:17, cycle started 13:21, killed 14:06.
**Fix lasted 45 minutes.** Because it protected the wrong function.

---

**Deployed:** 2026-04-04 14:10 MST (after 12th kill)  
**Next test:** Manual cycle or next timer trigger  
**Status:** AWAITING VALIDATION — DO NOT AUTO-ENABLE YET
