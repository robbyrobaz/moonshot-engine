# Moonshot Infinite Loop Bug Fix — Apr 4 2026

**Status:** DEPLOYED (commit d760148)  
**Severity:** CRITICAL (11 thermal kills since Mar 30, CPU 600%+, 91°C thermal)  
**Impact:** System stability, live trading service protection

## Problem

Moonshot v2 tournament cycles were entering infinite loops during backtest phase, causing:
- CPU usage 600-700% (all cores maxed)
- RAM exhaustion (30+ GB RSS)
- Thermal throttling (91°C reported)
- System instability
- **11 manual kills since Mar 30 2026**

## Root Cause

`backtest_new_challengers()` had **no resource limits**:

1. **No cycle time budget** — could run indefinitely
2. **No per-model timeout** — label loading + training could hang forever
3. **No memory checks** — would continue until OOM
4. **No graceful failure** — errors would crash without retiring models
5. **Batch commits only** — losing all progress if interrupted

With:
- 90M+ labeled rows (470 symbols × 2 years × 4H candles)
- 10 models per cycle (BACKTEST_BATCH_SIZE)
- Each model loading all data independently
- GPU training (CatBoost/LightGBM) can take 5-15min per model

**Worst case:** 10 models × 15min = 150min cycle time (2.5 hours)  
**Observed:** Cycles hanging at 600% CPU for 1+ hours before thermal kill

## Solution

Added **4 layers of safety** to `backtest_new_challengers()`:

### 1. Cycle Time Budget (60min default)
```python
cycle_budget_minutes = 60
cycle_start_time = time.time()

# Before each model:
elapsed = time.time() - cycle_start_time
if remaining < 60:  # <1min left
    log.warning("Cycle budget exhausted, stopping batch")
    break
```

If budget exhausted:
- Stop batch processing
- Log models processed vs remaining
- Exit gracefully
- Partial progress already saved

### 2. Per-Model Timeout (10min max)
```python
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(600)  # 10min

try:
    result = backtest_challenger(db, params)
finally:
    signal.alarm(0)  # Cancel
```

If model times out:
- Catch TimeoutError
- Retire model with reason 'timeout: X.Xs'
- Commit to DB
- Continue to next model

### 3. Memory Check (Stop if RSS >80% available)
```python
rss_mb = _get_rss_mb()
with open("/proc/meminfo") as f:
    mem_available_mb = parse_meminfo(f)
    if rss_mb > mem_available_mb * 0.8:
        log.warning("Memory exhaustion risk, stopping batch")
        return
```

If approaching OOM:
- Stop entire batch
- Preserve system stability
- Allow memory to be freed

### 4. Graceful Error Handling
```python
except TimeoutError:
    retire_model(db, model_id, "timeout: X.Xs")
    continue  # Next model
    
except MemoryError:
    retire_model(db, model_id, "oom")
    break  # Stop batch (system unstable)
    
except Exception as e:
    retire_model(db, model_id, f"backtest_error: {e}")
    continue  # Next model
```

All errors now:
- Retire the failing model
- Save to DB immediately
- Either continue batch (timeout/error) or stop (OOM)
- Never crash the entire cycle

### 5. Progress Tracking
```python
# After each model:
log.info(
    "Model %s done in %.1fs. Progress: %d/%d. "
    "Cycle elapsed: %.1fs, remaining: %.1fs",
    model_id, model_elapsed, processed, total,
    total_elapsed, remaining
)
```

Every model now logs:
- Model completion time
- Progress (N/M)
- Total cycle elapsed time
- Remaining time budget

## Behavior Changes

### Before (broken)
- ❌ No timeout → infinite loops
- ❌ No memory checks → OOM kills
- ❌ Errors crash cycle → lose all progress
- ❌ No visibility into time budget
- ❌ All-or-nothing batch commits

### After (fixed)
- ✅ 60min cycle budget → guaranteed completion
- ✅ 10min per-model timeout → no infinite hangs
- ✅ Memory safety → stop before OOM
- ✅ Graceful failures → partial progress saved
- ✅ Clear diagnostics → visibility into bottlenecks
- ✅ Per-model commits → never lose progress

## Expected Outcomes

1. **No more infinite loops** — cycle budget hard cap
2. **No more thermal kills** — timeout prevents CPU thrashing
3. **No more OOM** — memory checks prevent exhaustion
4. **Partial progress preserved** — DB commits per model
5. **Better diagnostics** — time budget logging shows bottlenecks

## Testing Plan

Next tournament cycle: **Saturday Apr 4 2026, 12:05 PM MST**
- 44 models in backtest queue
- 10 models per cycle (BACKTEST_BATCH_SIZE)
- 5 cycles total expected

**Success criteria:**
- Cycles complete within 60min budget
- No thermal warnings (CPU <80%, temp <85°C)
- Models retire gracefully on timeout (not crash)
- Progress logged clearly per model
- No manual kills needed

## Monitoring

Watch for:
- Cycle completion time (should be <60min)
- Per-model backtest time (should be <10min)
- Memory usage trend (should not grow unbounded)
- Timeout retirements (models failing 10min gate)
- CPU/thermal (should stay reasonable)

If timeouts are frequent:
- Consider reducing BACKTEST_BATCH_SIZE from 10 to 5
- Investigate slow label loading (optimize query?)
- Check if GPU is bottleneck (move to CPU?)

## Code Changes

**File:** `blofin-moonshot-v2/src/tournament/backtest.py`  
**Function:** `backtest_new_challengers()`  
**Lines changed:** +89, -4  
**Commit:** d760148  
**Branch:** feature/moonshot-2x-leverage

## Historical Context

**Infinite loop kills since Mar 30:**
1. Mar 30 — first observed, manually killed
2. Mar 31 — 3 kills
3. Apr 1 — 2 kills
4. Apr 2 — 2 kills
5. Apr 3 — 2 kills
6. Apr 4 — 1 kill (this fix deployed)

**Total:** 11 manual interventions in 5 days

This bug was the #1 operational pain point for Moonshot v2. System was unreliable and required constant babysitting.

## Future Work

1. **Optimize label loading** — currently loading all 90M+ rows per model
   - Cache labels once per cycle?
   - Memory-mapped file?
   - Lazy loading per fold?

2. **Parallelize backtest** — use joblib to run N models concurrently
   - Requires memory budget per worker
   - Watch for GPU contention

3. **Incremental backtesting** — only backtest new data since last run
   - Track last_backtest_ts per model
   - Only load labels after that timestamp

4. **Better feature caching** — avoid recomputing features for every model
   - Feature store per symbol+ts?
   - Shared feature matrix across models?

But for now: **stability > optimization**. Let's prove the timeout fix works first.

---

**Deployed:** 2026-04-04 13:17 MST  
**Next test:** 2026-04-04 12:05 PM MST (tournament cycle)  
**Status:** Monitoring
