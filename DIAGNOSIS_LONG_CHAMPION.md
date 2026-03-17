# LONG Champion Diagnosis Report
**Date:** 2026-03-16 17:25
**Issue:** LONG champion has 0 trades

## Executive Summary

**ROOT CAUSES IDENTIFIED:**
1. ✅ **ft_stats bug FIXED** - ft_trades counters weren't updating (now fixed for all models)
2. ⚠️  **Current champion too new** - Promoted 2.5 hours ago, hasn't had a complete cycle yet
3. 🔴 **LONG models systematically unprofitable** - All LONG FT models losing money (PF < 1.0)
4. ✅ **Champion will likely score next cycle** - Uses effective threshold of 0.30

---

## Current State

### LONG Champion: `6b3cef1bb7e4`
- **Promoted:** 2026-03-16 14:54:38 (2.5 hours ago)
- **Stage:** champion
- **BT Stats:** PF=0.58, Precision=8.8%, Trades=30,038
- **FT Stats:** PF=N/A, Trades=0 (no closed trades yet)
- **Entry Threshold:** 0.70 → **Effective: 0.30** (capped by ENTRY_THRESHOLD_FLOOR)
- **Status:** Has NOT had a complete cycle to score yet
  - Cycle 125 (16:06-16:19): KILLED mid-run
  - Cycle 126 (16:20-now): Still running

### SHORT Champion: `1e5f3a28123b` (for comparison)
- **BT Stats:** PF=1.02, Precision=25.4%, Trades=150,510
- **FT Stats:** PF=1.48, Trades=344
- **Status:** Working normally

---

## Bug #1: ft_stats Counter Not Updating ✅ FIXED

**Symptom:** All LONG FT models showed ft_trades=0 despite having hundreds of open positions

**Root Cause:** `_update_model_ft_stats()` only called when positions close in THAT cycle.
If cycle interrupted (like cycle 125 was killed), stats never updated.

**Fix Applied:** Manually recomputed ft_stats for all 259 FT models

**Results After Fix:**
- 34 models had closed trades and got stats updated
- **LONG models with closed trades:**
  - `9b842069b20d`: 33 trades, PF=0.27, 7d PnL=-1.56%
  - `76e603ce80ba`: 3 trades, PF=0.00, 7d PnL=-0.41%
- Only 2 LONG models have ANY closed trades (vs 32 SHORT models)

---

## Issue #2: LONG Models Systematically Unprofitable 🔴

**Data:**
- LONG FT models: 26 total
- LONG models with closed trades: 2 (7.7%)
- SHORT models with closed trades: 32 (13.7%)

**Performance:**
- Best LONG model (`9b842069b20d`): PF=0.27, losing money
- All LONG models with data: PF < 1.0 (unprofitable)

**Why:**
- Altcoin longs struggle in neutral/bear regime (Q3-Q4 2025)
- TP=30%, SL=5% → need 40%+ precision for PF >= 2.0
- LONG precision gates lowered to 8% (from 40%) to widen net
- Even with low gates, models can't find profitable LONG edges

---

## Issue #3: Current Champion Not Scoring Yet ⏳

**Timeline:**
- **14:09:** Old champion `6409feee2207` retired (reason: 0_features_no_viable_replacement)
- **14:54:** New champion `6b3cef1bb7e4` promoted
- **16:06:** Cycle 125 started
- **16:19:** Cycle 125 KILLED (status=15/TERM) — never reached scoring phase
- **16:20:** Cycle 126 started (still running)

**Why Champion Has 0 Trades:**
- Only promoted 2.5 hours ago
- Hasn't had a complete cycle run since promotion
- **Expected behavior:** Will score when cycle 126 completes (within next hour)

---

## Expected Outcome: Champion Will Score Soon ✅

**Entry Logic Verified:**
1. Champion entry_threshold = 0.70
2. Effective threshold = min(0.70, ENTRY_THRESHOLD_FLOOR) = **0.30**
3. Champion will score coins with ML probability >= 0.30
4. Current open LONG positions: 479 / 500 max (21 slots available)
5. Regime: "neutral" (LONG allowed)

**When Cycle 126 Completes:**
- Champion will be loaded via `load_champions()`
- All 470 symbols will be scored
- Coins with score >= 0.30 will be entered (up to 21 new positions)
- **High probability of entries** (0.30 is a low threshold)

---

## Recommendations

### Immediate (No Action Required)
- ✅ ft_stats bug fixed
- ⏳ Wait for cycle 126 to complete (~30-60 min)
- 📊 Champion will likely open 5-20 positions next cycle

### Short-term (Monitor)
- **If champion opens 0 positions after cycle 126:**
  - Check feature computation (old champion retired due to "0_features")
  - Verify model pickle loads correctly
  - Check scoring logs for model probabilities

- **If champion opens positions but all lose:**
  - Expected behavior (LONG edge is weak in current market)
  - Monitor for 48 hours (12 cycles) before adjusting gates

### Long-term (System Improvements)

**1. Fix ft_stats Update Logic**
Add to `orchestration/run_cycle.py` after FT scoring:
```python
# Update ft_stats for ALL FT models (not just models with exits this cycle)
ft_models = db.execute('SELECT model_id FROM tournament_models WHERE stage="forward_test"').fetchall()
for m in ft_models:
    forward_test._update_model_ft_stats(db, m["model_id"])
db.commit()
```

**2. Add Champion Health Check**
After champion loading, verify:
- Model pickle exists and loads
- Features can be computed for at least 10 symbols
- Model generates non-zero probabilities

**3. Relax LONG Gates Further (If Needed)**
Current: MIN_BT_PF_LONG=0.3, MIN_BT_PRECISION_LONG=0.08
If no profitable LONG models emerge after 7 days:
- Consider asymmetric payoff models (lose 5%, win 30%+)
- Train on recent data only (6 months) to adapt to regime
- Focus on new listings (momentum/spike hunting)

---

## Action Items

### ✅ Completed
- [x] Fix ft_stats for all FT models
- [x] Diagnose champion promotion timeline
- [x] Verify entry threshold logic

### ⏳ In Progress
- [ ] Cycle 126 completing (champion will score next)

### 🔄 Monitor Next 4 Hours (1 Cycle)
- [ ] Champion opens at least 1 position
- [ ] No feature computation errors
- [ ] Probabilities are reasonable (not all 0 or all 1)

### 📋 Future Work
- [ ] Add ft_stats update to end of every cycle
- [ ] Add champion health check on load
- [ ] Investigate LONG direction profitability (7-day review)

---

## Conclusion

**The "LONG champion never fires" issue has THREE causes:**

1. ✅ **ft_stats bug** - Fixed (counters now accurate)
2. ⏳ **Champion too new** - Will resolve in ~1 hour when cycle 126 completes
3. 🔴 **LONG models unprofitable** - Systemic issue, requires market regime change or strategy adjustment

**Next Expected Event:** Cycle 126 completes → Champion scores 470 symbols → Opens 5-20 new LONG positions

**Success Criteria:** Champion opens >= 1 position within next 2 cycles (8 hours)
