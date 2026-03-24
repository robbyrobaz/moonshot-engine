# Feature Shape Mismatch Fix — 2026-03-24

## Bug Report
**Error:** `FT scoring failed: Feature shape mismatch, expected: 25, got 5`

**When:** Occurred at 15:31:54 during Moonshot cycle 186, after successful FT opens at 15:02

**Impact:** FT scoring was crashing, preventing position management and stats updates

## Root Cause
The `_get_feature_values()` function in `src/tournament/forward_test.py` was returning `None` when any requested feature was missing from the stored feature data, instead of using neutral values from the feature registry.

### Why This Happened
With the new sparse feature storage format (storing only 25 core features instead of all 50), when models requested features that weren't in the stored dict, the function would:

1. Look up `val = name_to_val.get(fn)` 
2. Find `val == None` for missing features
3. Return `None` immediately, abandoning the feature vector build

This caused downstream code to receive incomplete or empty feature vectors, leading to shape mismatches when models expected 25 features but got fewer (or zero).

### The Specific Code Bug

**BEFORE (buggy):**
```python
else:
    val = name_to_val.get(fn)
if val is None:
    return None  # ← BUG: Returns None, causing empty feature vector
```

**AFTER (fixed):**
```python
else:
    val = name_to_val.get(fn)
    # Use neutral value from registry if feature is missing
    if val is None:
        if reg and "neutral" in reg:
            val = reg["neutral"]
        else:
            # Feature not in registry and not in stored data — can't proceed
            log.warning("_get_feature_values: missing feature '%s' for %s (not in registry or stored data)", fn, symbol)
            return None
```

## Fix Details

### 1. Core Fix: Use Neutral Values for Missing Features
Modified `_get_feature_values()` to:
- Check if a requested feature is missing from stored data
- Look up its neutral value from `FEATURE_REGISTRY`
- Use the neutral value instead of failing
- Only return `None` if a feature is missing AND not in the registry (should never happen)

### 2. Enhanced Error Logging
Added comprehensive error tracking to catch future issues:

- **In `_get_feature_values()`**: Warn when features are missing or invalid
- **In `_score_symbols()`**: Catch prediction errors with detailed context (symbol, vec length, expected count)
- **In invalidation check**: Catch shape mismatches with model_id, symbol, position id
- **In `run_cycle.py`**: Added traceback logging when FT scoring fails

### 3. Try/Except Blocks
Wrapped prediction calls in try/except to catch `ValueError` from shape mismatches and log:
- Which symbol/model caused the error
- Expected vs actual feature count
- Full traceback for debugging

## Testing

Created test scripts to verify:
1. ✓ Feature extraction with full storage (50 features)
2. ✓ Feature extraction with sparse storage (25 features)
3. ✓ Missing features use correct neutral values
4. ✓ Feature count matches model expectation

All tests passed.

## Files Changed
- `src/tournament/forward_test.py` — Core fix + enhanced logging
- `orchestration/run_cycle.py` — Added traceback logging for FT errors

## Commit
```
fix: FT scoring feature shape mismatch (use neutral values for missing features)
Commit: 075e836
Branch: feature/moonshot-2x-leverage
```

## Verification Plan
Monitor next Moonshot cycle (cycle 187+) to confirm:
- [ ] No "Feature shape mismatch" errors
- [ ] FT scoring completes successfully
- [ ] Position opens/closes work normally
- [ ] Stats updates proceed without crashes

## Prevention
This fix enables proper sparse feature storage:
- Old positions with 50 features continue to work
- New positions with 25 features work correctly
- Missing features automatically filled with neutral values
- No need to store redundant zero/neutral values

## Related Issues
- Sparse storage introduced in recent commits to reduce DB size
- Original error suggested "got 5" features, likely from incomplete vector build
- Invalidation check already had neutral value logic, but entry scoring did not
