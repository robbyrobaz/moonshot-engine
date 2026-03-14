# Tournament Philosophy — Moonshot v2

> **Core Principle:** We are NOT trying to make all models profitable. We're running a tournament to FIND the rare models that work.

## The Goal

**Find the 0.5% of models that are gold. Let the other 99.5% fail.**

- Generate 100+ model variants per day (random params + feature subsets)
- Let them compete in forward test (20-50 trades minimum to prove themselves)
- Promote the top 0.5% by FT PnL to champion
- Retire the bottom 95% — **this is expected and good**

## What Success Looks Like

✅ **GOOD:** 95% of models fail, 5% make it to FT, 0.5% become champion  
❌ **BAD:** Trying to optimize every model, micromanaging exits, preventing failures

## Tournament Stages

### 1. Challenger Generation (100/day)
- Random hyperparameters (model type, depth, learning rate, class weights)
- Random feature subsets (see Feature Diversity below)
- Goal: Maximum diversity = more lottery tickets

### 2. Backtest Gate (Strict)
- 3-fold walk-forward (60/20/10/10 expanding windows)
- Fold 3 (most recent 10% of data) MUST pass:
  - PF ≥ 1.0 (was 2.0, lowered to let more models through)
  - Precision ≥ 0.20 (was 0.40)
  - Trades ≥ 50
  - Bootstrap CI lower bound ≥ 1.0
- Folds 1-2 are soft (crypto regimes shift — older data can underperform)
- **Pass rate target: 10-20% of challengers**

### 3. Forward Test (Max 15 models)
- Paper trading on live data
- **Goal: Let models prove profitability over 20-50 trades**
- Track: ft_pnl (total PnL %), ft_pf (profit factor), ft_trades
- Demotion: ONLY if catastrophic (PF < 0.5 after 150 trades)
- **Invalidation should NOT kill models early** — see Invalidation Philosophy below

### 4. Champion Promotion
- Best FT PnL with ≥20 trades (separate long/short)
- Must beat current champion's ft_pnl by 10% margin
- Must ALSO pass backtest gates (dual validation — prevents regime-shift bugs)
- Old champion demoted back to FT (keeps running, doesn't retire)

## Feature Diversity Strategy

**Current (4 presets):**
- `core_only` (25 features)
- `price_volume` (core + volume)
- `no_social` (core + extended, 39 features)
- `all` (core + extended + social, 52 features)

**New (random subsets):**
- `price_heavy` (80% price action, 20% other)
- `volume_heavy` (80% volume, 20% other)
- `volatility_heavy` (80% volatility, 20% other)
- `regime_aware` (50% regime, 50% price/volume)
- `social_boost` (core + social only, skip extended)
- `minimal` (10-15 features only — test if simpler is better)
- `maximal` (all 52 features)

**Implementation:** 50% of challengers use presets, 50% use random subsets → 10x more feature combinations tested

## Invalidation Philosophy (Updated Mar 14 2026)

**Problem:** 76% invalidation rate is killing models before they can prove profitability.

**Root cause:** Models are re-scored every cycle. If features drift (social signals change, regime shifts), score drops, position exits prematurely.

**Wrong solution:** "Fix invalidation to work for all models"  
**Right solution:** "Let models run long enough to prove they're profitable, THEN judge them"

**Three options:**

### Option A: Lock Features at Entry (RECOMMENDED)
- Store `entry_features` JSON at position open
- NEVER recompute features during invalidation check
- Use stored features for re-scoring
- **Pro:** No feature drift, models compete on consistent data
- **Con:** Requires DB migration (but entry_features column already exists!)

### Option B: Raise Invalidation Grace Period
- Current: 2 bars (8 hours)
- New: 10 bars (40 hours) or 20 trades (whichever comes first)
- **Pro:** Easy change, one line in config
- **Con:** Still allows drift, just delays it

### Option C: Disable Invalidation for First 50 Trades
- Let models run 50 trades BEFORE invalidation kicks in
- After 50 trades, re-enable invalidation
- **Pro:** Models get a fair chance to prove profitability
- **Con:** Bad models stay open longer (but who cares? It's paper trading)

**Recommendation:** Option A (lock features) + Option C (50-trade grace period)

## Metrics That Matter

### Model-Level
- **ft_pnl** (primary) — total PnL % over all FT trades
- **ft_pf** (secondary) — profit factor (wins / abs(losses))
- **ft_trades** (tiebreaker) — more trades = more confidence

### System-Level
- **Champion PnL** — is the current champion profitable?
- **Promotion rate** — % of FT models promoted to champion (target: 0.5-1%)
- **Invalidation rate** — % of exits due to invalidation (target: <30%, currently 76%)
- **Feature subset winners** — which feature combinations produce champions?

## Anti-Patterns to Avoid

❌ **Trying to make all models work** — this isn't the goal  
❌ **Micromanaging exits** — let TP/SL/trail/time do their job  
❌ **Preventing failures** — failures are DATA, they tell us what doesn't work  
❌ **Lowering gates to let more models through** — gates exist to filter garbage  
❌ **Optimizing for aggregate metrics** — only the TOP MODEL matters

## What Rob Wants

> "The goal isn't to make them all profitable!! It's to find models that are profitable."

> "Each model should also test a handful of tuning to see if it can be improved. New features to test. Pick combinations of features, etc. make that part of the normal pipeline too."

**Translation:**
1. Generate WAY more model variants (100+/day with random feature subsets)
2. Let them compete fairly (fix invalidation so models run 50+ trades)
3. Promote ONLY the winners (top 0.5% by ft_pnl)
4. Don't try to save failing models — retire them and try new variants

## Implementation Checklist

- [x] Lower BT gates (PF 2.0→1.0, prec 0.40→0.20) to let more models through
- [x] FT demotion: only PF<0.5 after 150 trades (not early kills)
- [ ] Fix invalidation (lock features at entry OR 50-trade grace period)
- [ ] Add random feature subset generator to challenger.py
- [ ] Update Auto Card Generator to include feature experimentation cards
- [ ] Track which feature subsets produce champions (dashboard metric)
