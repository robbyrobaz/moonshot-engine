# LONG Champion Investigation - Summary & Fixes

**Date:** 2026-03-16 17:30
**Status:** ✅ RESOLVED (with monitoring required)

---

## TL;DR

**User's Issue:** "LONG champion never fires (0 trades)"

**Root Causes Found:**
1. ✅ **ft_stats bug** - Counters not updating → FIXED
2. ⏳ **Champion too new** - Promoted 2.5h ago, hasn't completed a cycle yet → Will resolve naturally
3. 🔴 **LONG models unprofitable** - Systemic market issue → Requires monitoring

**Action Taken:**
- Fixed ft_stats for all 259 FT models
- Implemented permanent fix in run_cycle.py
- Champion will score in next cycle (~30-60 min)

---

## Detailed Findings

### Finding #1: ft_stats Counter Bug ✅ FIXED

**Problem:**
- All LONG FT models showed `ft_trades=0` despite having 400+ open positions
- Counter only updated when positions closed IN THAT CYCLE
- If cycle interrupted (cycle 125 was killed), stats never updated

**Example:**
- Model `9b842069b20d` had 438 total positions (33 closed)
- DB showed: `ft_trades=0, ft_pf=NULL`
- Should show: `ft_trades=33, ft_pf=0.27`

**Fix Applied:**

1. **Immediate:** Ran `fix_ft_stats.py` to update all 259 FT models
   - 34 models had closed trades and got stats updated
   - Only 2 LONG models have any closed trades (vs 32 SHORT models)

2. **Permanent:** Modified `orchestration/run_cycle.py` (line 222-236)
   - Now updates ALL FT models' stats after each cycle
   - Prevents stale stats from missed/interrupted cycles

**Code Change:**
```python
# After FT scoring, update stats for ALL models (not just models with exits)
from src.tournament.forward_test import _update_model_ft_stats
ft_models = db.execute(
    'SELECT model_id FROM tournament_models WHERE stage IN ("forward_test", "ft")'
).fetchall()
for m in ft_models:
    _update_model_ft_stats(db, m["model_id"])
db.commit()
```

---

### Finding #2: Current Champion Too New ⏳

**Timeline:**
- **14:09:** Old LONG champion `6409feee2207` retired (reason: "0_features_no_viable_replacement")
- **14:54:** New LONG champion `6b3cef1bb7e4` promoted
- **16:06:** Cycle 125 started
- **16:19:** Cycle 125 KILLED (status=15/TERM) before reaching scoring phase
- **16:20:** Cycle 126 started (still running at time of investigation)

**Why Champion Has 0 Trades:**
- Only promoted 2.5 hours ago
- Hasn't had a complete cycle since promotion
- **Expected:** Will score when cycle 126 completes

**Champion Details:**
- Model: `6b3cef1bb7e4` (CatBoost)
- BT_PF: 0.58 (passes LONG gate of 0.3)
- Entry threshold: 0.70 → **Effective: 0.30** (capped by ENTRY_THRESHOLD_FLOOR)
- **Will score coins with probability >= 0.30**

**Old Champion (for context):**
- Model: `6409feee2207`
- Opened 9 champion positions (still open)
- Retired due to feature computation issue
- BT_PF: 1.26 (good backtest!)

---

### Finding #3: LONG Models Systematically Unprofitable 🔴

**Data:**
- LONG FT models: 26 total
- LONG models with closed trades: **2** (7.7%)
- SHORT models with closed trades: **32** (13.7%)

**Performance of LONG models with data:**
| Model | Trades | PF | 7d PnL | Status |
|-------|--------|-----|--------|--------|
| 9b842069b20d | 33 | 0.27 | -1.56% | Losing |
| 76e603ce80ba | 3 | 0.00 | -0.41% | Losing |

**Why LONG is struggling:**
- Altcoin longs struggle in neutral/bear regime (Q3-Q4 2025 market)
- TP=30%, SL=5% → need 40%+ precision for breakeven
- LONG gates already lowered: PF>=0.3, Precision>=8% (vs SHORT: PF>=0.6, Prec>=12%)
- Even with very low gates, can't find profitable LONG edges

**Champion Promotion Logic:**
- Requires ft_trades >= 20 AND beating current champion by 10%
- Only 1 LONG model has ft_trades >= 20: model `9b842069b20d`
- That model has ft_pnl_last_7d = -1.56% (losing)
- Current champion has ft_pnl_last_7d = 0.0% (no data)
- -1.56% < 0.0%, so no promotion happens
- **Result:** Current champion stays (correct behavior)

---

## Files Modified

### 1. `orchestration/run_cycle.py` (PERMANENT FIX)
- Added ft_stats update for ALL FT models after each cycle
- Prevents stale stats from interrupted cycles
- **Will take effect starting next cycle** (no restart needed, service runs every 4h)

### 2. `fix_ft_stats.py` (ONE-TIME FIX)
- Script to manually recompute ft_stats for all FT models
- Already executed successfully
- Can be deleted after verification

### 3. `DIAGNOSIS_LONG_CHAMPION.md` (DOCUMENTATION)
- Detailed investigation report
- Timeline of events
- Root cause analysis
- Recommendations

---

## Expected Outcome

### Next 1 Hour (Cycle 126 Completes)
- Champion loads successfully
- Scores all 470 symbols
- **Expected: Opens 5-20 new LONG positions** (threshold=0.30 is low)
- ft_stats will be updated for all models (including champion)

### Next 24 Hours (6 Cycles)
- Champion accumulates trades
- Can evaluate champion performance
- ft_stats stay up-to-date (permanent fix in place)

### If Champion Opens 0 Positions
**Investigate:**
1. Feature computation errors (old champion retired due to "0_features")
2. Model pickle loading issues
3. Model generating all probabilities < 0.30

**Debug Commands:**
```bash
# Check champion scoring logs
journalctl --user -u moonshot-v2.service --since "1 hour ago" | grep -i "champion.*long"

# Check if model loaded
journalctl --user -u moonshot-v2.service --since "1 hour ago" | grep -i "load_champions"

# Check for feature errors
journalctl --user -u moonshot-v2.service --since "1 hour ago" | grep -i "features failed"
```

---

## Recommendations

### Immediate (Done)
- ✅ Fixed ft_stats bug (both immediate and permanent fix)
- ✅ Verified champion promotion logic
- ✅ Documented findings

### Monitor (Next 4-8 Hours)
- ⏳ Wait for cycle 126 to complete
- 📊 Verify champion opens >= 1 position
- 🔍 Check for feature computation errors
- 📈 Monitor ft_stats updates in next cycles

### Long-term (If LONG Remains Unprofitable)

**Option A: Accept Asymmetry**
- Run SHORT-only strategy (current champion: PF=1.48, working well)
- Pause LONG challenger generation to save resources
- Revisit LONG when market regime changes

**Option B: Adapt LONG Strategy**
- Train on recent data only (6 months) for regime adaptation
- Focus on new listings (momentum/spike hunting)
- Lower TP to 15% (from 30%) for faster wins
- Add regime filter: LONG only in bull regime

**Option C: Lottery Ticket Approach** (Current)
- Keep gates very low (PF>=0.3, Prec>=8%)
- Generate many LONG models hoping for rare edge
- Accept 95% failure rate for asymmetric payoff
- **Already implemented** - Monitor for 7 days before adjusting

---

## Success Criteria

### ✅ Immediate Success (Achieved)
- [x] Diagnosed root cause of 0 trades
- [x] Fixed ft_stats bug
- [x] Implemented permanent fix

### ⏳ Short-term Success (Next 8 Hours)
- [ ] Cycle 126 completes successfully
- [ ] Champion opens >= 1 position
- [ ] No feature computation errors
- [ ] ft_stats update correctly in next cycle

### 📊 Medium-term Success (Next 7 Days)
- [ ] Champion accumulates 20+ trades
- [ ] Can evaluate champion PF (target: >= 1.0)
- [ ] LONG FT models generate more closed trades
- [ ] Decide on LONG strategy (continue/pause/adapt)

---

## Questions for User

1. **Old Champion Retirement:**
   - Old champion `6409feee2207` was retired for "0_features_no_viable_replacement"
   - Was this a manual retirement or did it happen automatically?
   - What caused the feature computation failure?

2. **Cycle 125 Killed:**
   - Cycle 125 was killed (TERM signal) at 16:19
   - Was this a manual restart or systemd timeout?
   - Do cycles normally complete, or do they often get killed?

3. **LONG Strategy:**
   - Given all LONG models are unprofitable (PF < 1.0), continue or pause?
   - Accept SHORT-only strategy for now?
   - Or invest in LONG strategy adaptation (retrain, new features, etc.)?

---

## Next Steps

### User Should:
1. ⏳ **Wait 30-60 minutes** for cycle 126 to complete
2. 📊 **Check champion positions:** `python3 check_champion.py`
3. 📝 **Review logs:** `journalctl --user -u moonshot-v2.service --since "1 hour ago" | grep -i champion`
4. ✅ **Verify fix worked:** ft_stats should update in next cycle
5. 🤔 **Decide on LONG strategy** after 7 days of data

### Developer Should (If Needed):
1. Add champion health check on load (verify features, probabilities)
2. Add alerting for interrupted cycles
3. Investigate old champion's "0_features" retirement
4. Consider LONG strategy adaptation (if keeping LONG)

---

**END OF REPORT**
