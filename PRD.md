# Moonshot v2 — Product Requirements Document

**Status:** AWAITING ROB APPROVAL  
**Branch:** `moonshot-v2-plan`  
**Date:** 2026-03-02  
**Author:** Jarvis (synthesized from 72h sessions + audit)

---

## Vision

A persistent, self-improving engine that finds large price moves (≥30%) on any of Blofin's 342 USDT pairs — long or short, new coins or established ones. New ideas compete continuously. Winners survive. Losers get retired. The system never stops improving.

---

## Core Principles

1. **Competition drives quality.** Every model proves itself on real forward-test PnL before it touches champion.
2. **PF and precision only.** AUC is dead. A model must make money, not just classify correctly.
3. **Entry and exit use identical features.** No more regime feature mismatch crashes.
4. **Path-dependent labels.** Did price hit +30% *before* hitting -10%? That's the real question.
5. **Blofin-native only.** Zero external data providers. Everything from Blofin's own API.
6. **All 342 pairs.** Dynamic discovery. New listings auto-detected. No static lists ever.
7. **Paper first.** System never touches live money without Rob's explicit approval.

---

## What We Keep from v1

- Existing downloaded Blofin candle data (4h, up to 4 years where available)
- SQLite DB approach (familiar, works, no infra needed)
- 4h cycle cadence
- Systemd timer deployment pattern
- TOURNAMENT.md graduation gates: bt_pf ≥ 2.0, precision ≥ 40%, trades ≥ 50
- Demotion gate: ft_pf < 1.3 after 20 FT trades
- Champion: best ft_pnl with ≥20 FT trades

**Everything else is new code.**

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                 │
│  Blofin API → candles (4h, 1m) → SQLite                          │
│  Dynamic discovery: all 342 pairs, new listings auto-added        │
│  Historical: use existing data + backfill gaps to 2-4 years      │
└──────────────────┬───────────────────────────────────────────────┘
                   │ every 4h
┌──────────────────▼───────────────────────────────────────────────┐
│                    FEATURE PIPELINE                                │
│  Compute 20+ features per coin from raw candles                   │
│  SAME function used for training, scoring, and exit               │
│  Regime features computed from BTC                                │
└──────────────────┬───────────────────────────────────────────────┘
                   │
          ┌────────┴────────┐
          │                 │
┌─────────▼──────┐  ┌───────▼──────────────────────────────────────┐
│ LABEL GENERATOR│  │              TOURNAMENT ENGINE                 │
│ (training only)│  │                                                │
│                │  │  ┌──────────────────────────────────────────┐ │
│ Path-dependent │  │  │ Challenger Generator (hourly)            │ │
│ labels:        │  │  │  • 10 random variants (params + features) │ │
│ Long: hit +30% │  │  │  • Backtest on 100K samples               │ │
│ before -10%    │  │  │  • Gate: PF≥2.0, prec≥40%, trades≥50     │ │
│ Short: hit -30%│  │  │  → Graduate to Forward Test               │ │
│ before +10%    │  │  └──────────────────────────────────────────┘ │
└────────────────┘  │  ┌──────────────────────────────────────────┐ │
                    │  │ Forward Test Arena (max 15 models)       │ │
                    │  │  • All models score coins every 4h        │ │
                    │  │  • Paper positions opened per model       │ │
                    │  │  • ft_pnl, ft_trades, ft_pf tracked       │ │
                    │  │  • Demotion: ft_pf < 1.3 after 20 trades  │ │
                    │  └──────────────────────────────────────────┘ │
                    │  ┌──────────────────────────────────────────┐ │
                    │  │ Champion Selection (daily re-eval)       │ │
                    │  │  • Best ft_pnl with ≥20 FT trades        │ │
                    │  │  • Separate long champion + short champ   │ │
                    │  │  → Saved to champion_long.pkl / _short.pkl│ │
                    │  └──────────────────────────────────────────┘ │
                    └───────────────────┬──────────────────────────┘
                                        │ champion model
┌───────────────────────────────────────▼──────────────────────────┐
│                      EXECUTION ENGINE                              │
│                                                                    │
│  Score all 342 coins with champion model                          │
│  Enter: top-N long signals + top-N short signals                  │
│  Manage positions: TP=30%, SL=10%, trail@20%, TIME=7d             │
│  INVALIDATION: re-score at each cycle, exit if score < threshold  │
│                                                                    │
│  ⚠️  PAPER ONLY until Rob approves live                           │
└───────────────────────────────────────┬──────────────────────────┘
                                        │
┌───────────────────────────────────────▼──────────────────────────┐
│                        DASHBOARD                                   │
│  • Tournament leaderboard (models ranked by FT PnL)               │
│  • Champion history                                                │
│  • Position monitor (open + closed)                               │
│  • Feature importance per champion                                 │
│  • Regime indicator                                                │
└──────────────────────────────────────────────────────────────────┘
```

---

## Module 1: Data Layer

### 1.1 Coin Discovery
```python
# Every 4h cycle, fetch all active USDT pairs from Blofin
GET /api/v1/market/instruments?instType=SWAP
→ filter: quoteCurrency=USDT, state=live
→ compare to known coins in DB
→ auto-add new listings, flag with is_new_listing=1
```

**New listing detection:** Any coin seen for the first time gets `new_listing_ts` recorded. Features include a `days_since_listing` field. New listings get an optional position size boost (configurable, default 1.5x).

### 1.2 Candle Ingestion
- **Interval:** 4h primary (all models trained on 4h)
- **Lookback for training:** 2-4 years where available (use existing downloaded data + backfill gaps)
- **Live feed:** latest 200 bars per coin per cycle (API call batched)
- **Storage:** `candles` table: `(symbol, ts, open, high, low, close, volume)`
- **Deduplication:** `INSERT OR IGNORE` on `(symbol, ts)`

### 1.3 Historical Backfill
- On first run: attempt 4-year backfill for each coin (paginate until data runs out)
- Track `oldest_candle_ts` per coin in `coins` table
- Periodic gap-fill: detect and fill any gaps in candle history
- Use existing downloaded data from `blofin-moonshot/data/` as starting point

### 1.4 Additional Blofin Data Sources

These are fetched each cycle and stored. Not all coins have full history — that's fine. Features degrade gracefully: if a data source isn't available for a coin, that feature is NULL and the model either skips it or uses a neutral fill value (tracked per model in the feature registry).

#### Funding Rate History — `GET /api/v1/market/funding-rate-history`
- Fetch last 90 funding periods per coin (funding settles every 8h on Blofin)
- That's 90 × 8h = 30 days of history per coin
- Store in `funding_rates` table: `(symbol, ts, funding_rate)`
- **Availability:** most coins have this from ~30 days after listing

#### Open Interest — `GET /api/v1/market/open-interest`
- Fetch current OI per coin each cycle
- Store in `open_interest` table: `(symbol, ts, oi_contracts, oi_currency)`
- Track history by inserting each cycle's snapshot
- **Availability:** available for all active coins

#### Mark Price / Index Price — `GET /api/v1/market/mark-price`
- Fetch current mark and index price per coin each cycle
- Store in `mark_prices` table: `(symbol, ts, mark_price, index_price)`
- **Availability:** all active coins

#### 24h Tickers — `GET /api/v1/market/tickers?instType=SWAP`
- Single API call returns ALL coins' 24h stats (high, low, vol, change)
- Free data at zero extra API cost
- Store in `tickers` table: `(symbol, ts, high_24h, low_24h, vol_24h, price_change_pct)`
- **Availability:** all active coins, always

#### API Rate Management
- Batch requests where possible (tickers = 1 call for all 342 coins)
- Per-coin calls: throttle to 10 req/sec max
- Store raw data first, compute features after — never block the cycle on feature computation

---

## Module 2: Feature Pipeline

**Critical rule:** One function `compute_features(symbol, ts_ms, db)` is used for ALL of:
- Training label generation
- Backtest scoring
- Live scoring (entry)
- Exit re-scoring (INVALIDATION check)

**No separate feature paths. No drift between training and inference. Ever.**

### 2.1 Extensible Feature Registry

Features are registered, not hardcoded. Any new feature can be added without changing the tournament or execution code. The model's `feature_version` tag tracks which set it was trained on.

```python
# src/features/registry.py
FEATURE_REGISTRY = {
    # name: (compute_fn, requires_history_bars, data_sources, availability)
    "price_vs_52w_high":    (fn_52w_high,    365,  ["candles"],          "all_coins"),
    "funding_rate":         (fn_funding,       1,  ["funding_api"],      "has_history_30d+"),
    "oi_change_24h":        (fn_oi_change,     7,  ["oi_api"],           "has_history_30d+"),
    ...
}

# Models declare which features they use at training time:
# model.feature_set = ["price_vs_52w_high", "bb_squeeze_pct", "funding_rate"]
# compute_features() returns ONLY that model's declared features
# → guaranteed consistency between training and inference
```

This means new features can be added to the registry and will automatically be included in new challengers' random param sampling — without touching existing champions.

### 2.2 Feature Set — Core (always available, from candles)

These are available for ALL coins, from day 1 of listing.

#### Price Action (6 features)
| Feature | Description |
|---------|-------------|
| `price_vs_52w_high` | current price / 52-week high (0=at high, lower = compressed) |
| `price_vs_52w_low` | current price / 52-week low |
| `momentum_4w` | 28-day price return (normalized -1 to +1) |
| `momentum_8w` | 56-day price return |
| `bb_squeeze_pct` | Bollinger Band width / 20-period average width (compression signal) |
| `bb_position` | where price sits within BB (0=lower band, 1=upper band) |

#### Volume (5 features)
| Feature | Description |
|---------|-------------|
| `volume_ratio_7d` | 7-day avg volume / 30-day avg volume (volume expansion/contraction) |
| `volume_ratio_3d` | 3-day avg / 14-day avg (shorter-term surge) |
| `obv_slope` | OBV 14-period linear regression slope, normalized by price |
| `volume_spike` | current bar volume / 14-period avg (single-bar event detection) |
| `volume_trend` | linear regression slope of volume over 30 bars (accumulation/distribution trend) |

#### Volatility (4 features)
| Feature | Description |
|---------|-------------|
| `atr_percentile` | current ATR vs 90-day ATR history, as percentile (0-100) |
| `atr_compression` | ATR 7-period avg / ATR 28-period avg (volatility coiling) |
| `high_low_range_pct` | current bar (high-low)/low — single bar range |
| `realized_vol_ratio` | 7-day realized vol / 30-day realized vol (vol regime shift) |

#### Price Structure (5 features)
| Feature | Description |
|---------|-------------|
| `distance_from_support` | % distance from nearest significant low in past 30 days |
| `distance_from_resistance` | % distance below nearest significant high in past 30 days |
| `consec_down_bars` | consecutive 4h bars closing lower (mean-reversion / momentum signal) |
| `consec_up_bars` | consecutive 4h bars closing higher |
| `higher_highs` | count of higher-highs in past 14 bars (trend structure) |

#### Market Regime (3 features — computed from BTC)
| Feature | Description |
|---------|-------------|
| `btc_30d_return` | BTC 30-day price return (proxy for altcoin cycle phase) |
| `btc_vol_percentile` | BTC current ATR vs 90-day history |
| `market_breadth` | % of top-20 coins (by OI) above their 30-day moving average |

#### Coin Metadata (2 features)
| Feature | Description |
|---------|-------------|
| `days_since_listing` | days since coin first appeared on Blofin (capped at 730) |
| `is_new_listing` | 1 if listed within 30 days, else 0 |

**Core total: 25 features.** Always available, from candle data only.

---

### 2.3 Feature Set — Extended (requires additional Blofin API data)

These unlock additional signal. Available once a coin has been on Blofin long enough for the APIs to have history (typically 30+ days). New coins start with core features only and graduate to extended features automatically.

#### Funding Rate (3 features) — `GET /api/v1/market/funding-rate-history`
Funding rate is the most unique signal available on perp futures. Extreme funding = crowded trade = mean reversion setup. These are powerful signals unavailable to spot traders.

| Feature | Description | Signal |
|---------|-------------|--------|
| `funding_rate_current` | current 8h funding rate (raw, -0.001 to +0.001 typical range) | positive = longs paying = long crowded |
| `funding_rate_7d_avg` | 7-day average funding rate | sustained positioning |
| `funding_rate_extreme` | 1 if abs(funding) > 2× 30-day avg, else 0 | crowded trade alert |

**Why this matters for moonshots:** Coins with extreme negative funding often have suppressed longs ready to rocket when shorts cover. Extreme positive funding = short squeeze setup.

#### Open Interest (4 features) — `GET /api/v1/market/open-interest`
OI measures total outstanding contracts. Rising OI + rising price = new money entering (conviction). Falling OI + rising price = shorts covering (less reliable).

| Feature | Description | Signal |
|---------|-------------|--------|
| `oi_change_24h` | OI change over last 24h, normalized by 30-day avg OI | money flowing in/out |
| `oi_change_7d` | OI change over last 7 days | sustained accumulation |
| `oi_price_divergence` | OI trend vs price trend (rising price + falling OI = weak move) | conviction filter |
| `oi_percentile_90d` | current OI vs 90-day history, as percentile | OI at extremes |

#### Mark Price vs Index Price (1 feature) — `GET /api/v1/market/mark-price`
| Feature | Description | Signal |
|---------|-------------|--------|
| `mark_index_spread` | (mark_price - index_price) / index_price | premium/discount, forced liquidation risk |

#### 24h Ticker Data (4 features) — `GET /api/v1/market/tickers`
Available per-cycle at zero extra API cost (single call for all coins).

| Feature | Description | Signal |
|---------|-------------|--------|
| `price_vs_24h_high` | current price / 24h high | intraday strength |
| `price_vs_24h_low` | current price / 24h low | intraday support holding |
| `vol_24h_vs_7d_avg` | 24h volume vs 7-day avg 24h volume | today's interest vs normal |
| `price_change_24h_pct` | 24h price change as % | momentum on current day |

**Extended total: 12 additional features.** Total with core: **37 features.**

---

### 2.4 Feature Set — Social & News Signals

Social/news signals are often **leading indicators** for crypto pumps — a coin gets talked about before it moves, not after. These are collected separately and featurized the same way as price data. They compete in the tournament: if they add alpha, models using them win. If not, they get dropped naturally.

**The key insight:** A coin with rising social mentions + rising OI + funding rate extreme is telling you something is happening *before* the price move. That's the edge.

#### Tier 1 — Free, No Auth Required

**Fear & Greed Index** — `https://api.alternative.me/fng/`
Single daily score 0-100 for the whole crypto market. Simple but effective regime modifier.
| Feature | Description | Use |
|---------|-------------|-----|
| `fear_greed_score` | 0=extreme fear, 100=extreme greed | Regime gate: extreme fear = potential long setups, extreme greed = short setups |
| `fear_greed_7d_change` | change over last 7 days | Momentum in sentiment |

**CoinGecko Trending** — `https://api.coingecko.com/api/v3/search/trending`
Free, no API key. Returns top 15 coins by search volume on CoinGecko updated hourly. This is a **strong moonshot signal** — coins appearing on the trending list often pump within 24-48h.
| Feature | Description | Use |
|---------|-------------|-----|
| `is_coingecko_trending` | 1 if coin in top-15 trending right now | Pre-pump retail attention signal |
| `trending_rank` | 1-15 (1=hottest), 0 if not trending | Recency/intensity |
| `hours_on_trending` | how long coin has been on trending list | Sustained vs flash attention |

**RSS News Feeds** — CoinTelegraph, Decrypt, The Block (all free, no auth)
Parse headlines every 4h. Extract coin tickers mentioned.
| Feature | Description | Use |
|---------|-------------|-----|
| `news_mentions_24h` | count of headlines mentioning this coin in last 24h | News velocity |
| `news_mentions_7d_avg` | 7-day average daily mentions | Baseline — normalize velocity |
| `news_velocity_ratio` | `mentions_24h / mentions_7d_avg` (spike = event) | >3× = something happening |

**Reddit** — free public API, no auth for read access
Target: r/CryptoCurrency (10M subs), r/CryptoMoonShots (2.3M), r/SatoshiStreetBets (758K), plus each coin's own subreddit.
| Feature | Description | Use |
|---------|-------------|-----|
| `reddit_mentions_24h` | posts + comments mentioning coin symbol across top subreddits | Social interest |
| `reddit_score_24h` | sum of upvotes on those posts | Quality-weighted attention |
| `reddit_velocity_ratio` | `mentions_24h / mentions_7d_avg` | Acceleration signal |

**GitHub** — free with token, unlimited public repo reads
Only meaningful for coins with active development (DeFi protocols, L1/L2s). Skip for memecoins.
| Feature | Description | Use |
|---------|-------------|-----|
| `github_commits_7d` | commits to the coin's main repo in last 7 days | Dev activity proxy |
| `github_commit_spike` | `commits_7d / commits_30d_avg` | Unusual dev activity = potential release |

---

#### Tier 2 — Low Cost, High Value ($29/mo)

**CryptoPanic Developer Plan** — `https://cryptopanic.com/api/v1/`
$29/mo for 10,000 requests/day. Per-coin news feed from 100+ sources. Each article has user votes: bullish 👍 / bearish 👎. This is the most **directly useful** paid source.
| Feature | Description | Use |
|---------|-------------|-----|
| `cryptopanic_bullish_24h` | count of bullish votes on this coin's articles (24h) | Crowd sentiment |
| `cryptopanic_bearish_24h` | count of bearish votes (24h) | Short setup signal |
| `cryptopanic_sentiment` | `bullish / (bullish + bearish)` ratio | Net sentiment score |
| `cryptopanic_article_count_24h` | articles about this coin in last 24h | News coverage depth |
| `cryptopanic_important_flag` | any article flagged "important" by editors in 24h | High-impact news |

*Note: Start without this. Add if free signals prove valuable.*

---

#### Tier 3 — Expensive, Evaluate Later

| Service | Cost | What it has | Worth it? |
|---------|------|-------------|-----------|
| **LunarCrush** | $29-99/mo | Social dominance, alt rank, galaxy score | Maybe — after v1 is profitable |
| **Santiment** | $$$+ | Social volume, dev activity, on-chain | Best in class, expensive |
| **X/Twitter API** | $100-5000/mo | Raw tweet volume, sentiment | Too expensive unless system is profitable |
| **Messari** | Free tier limited | Research, metrics | Check free tier first |

*Rule: Don't spend money on data until the free signals have proven they add alpha in the tournament.*

---

#### Social Data Architecture

```
Collection (every 1h, lightweight):
  → fetch fear/greed score
  → fetch CoinGecko trending list
  → parse RSS feeds (3 sources × ~20 articles)
  → Reddit search for top movers (top 50 coins by OI change)
  → GitHub: weekly commit counts for known repos

Storage:
  social_events table: (symbol, source, ts, event_type, raw_value)
  → append-only, never overwrite

Feature computation (at 4h cycle time, from stored events):
  → compute windowed aggregates (24h, 7d) from social_events
  → join into features table like any other feature
  → NULL-safe: coins with no social history get neutral fills
```

**Rate limits (free tier budget):**
- Fear & Greed: 1 req/day (needed)
- CoinGecko trending: 5 req/hour max (need 1/hour)
- Reddit search: ~60 req/min (plenty — 1 req/coin/day for top 50 is fine)
- RSS feeds: unlimited (3 sources, parse every 4h)
- GitHub: 5,000 req/hour with token (plenty)

**Important:** Social collection runs on its own lightweight timer (every 1h). It writes to `social_events`. The main 4h cycle reads from `social_events` and computes features. They're decoupled — a Reddit API hiccup doesn't break the trading cycle.

---

These go in the registry but are OFF by default. When a new challenger is generated, it randomly samples whether to include experimental features. If a model with experimental features passes the backtest gate and wins in forward test, the feature is proven. If not, it stays experimental.

| Feature | Data Source | Hypothesis |
|---------|-------------|------------|
| `ask_bid_spread_pct` | order book API | wide spread = low liquidity = volatile move |
| `book_imbalance_5` | order book (top 5 levels) | buy/sell pressure imbalance predicts direction |
| `consecutive_funding_sign` | funding history | 5+ consecutive same-sign fundings = crowded |
| `btc_dominance_7d_change` | compute from BTC OI vs total OI | alt season indicator |
| `price_vs_ath` | compute from max(close) in history | distance from all-time high on Blofin |
| `vol_concentration` | tick data if available | % of 24h volume in last 2h |
| `listing_age_bucket` | coins table | 0-30d, 30-90d, 90-180d, 180d+ buckets |

New experimental features can be added to the registry at any time by editing `src/features/registry.py` — no other code changes needed. The tournament will naturally test them.

---

### 2.5 Feature Versioning

```python
# feature_version = hash of sorted feature names
# e.g., "v1_a3f2c" = set {price_vs_52w_high, bb_squeeze, volume_ratio_7d, ...}
feature_version = sha256(sorted(feature_names)).hexdigest()[:8]
```

When a model's feature set changes (new feature added, old one removed), its `feature_version` changes. Models with mismatched feature versions cannot be compared and won't be loaded for exit re-scoring. This prevents the v1 INVALIDATION crash class permanently.

---

## Module 2b: Ideas Borrowed from NQ Pipeline

The NQ pipeline is working well. These are the concepts worth bringing over, adapted for crypto 4h timeframes.

### 1. PnL-Weighted Training

From NQ's `walk_forward.py`: instead of treating all training samples equally, weight them by their outcome PnL. Big wins matter more than marginal wins.

```python
# At training time:
# Label=1 (TP hit, +30%): weight = 1.0
# Label=0 (SL hit, -10%): weight = (SL/TP ratio) × penalty_factor
#   = (0.10 / 0.30) × 1.5 = 0.50
# Effect: model learns to avoid false positives, not just maximize accuracy
```

This makes models more conservative — fewer but higher-quality signals. Directly improves precision.

### 2. Bootstrap Confidence Intervals on PF

From NQ's `walk_forward.py`: don't just compute one profit factor from OOS trades — bootstrap it 1,000 times and get the 95% CI lower bound.

```python
# Gate: CI lower bound on PF must be ≥ 1.0
# (not just the point estimate ≥ 2.0)
# If PF is 2.5 but the CI is [0.8, 4.2] → high variance → reject
# If PF is 2.1 and CI is [1.5, 2.7] → consistent → accept
```

Catches models that got lucky on a small OOS set. Only models with statistically robust PF pass.

### 3. Per-Coin Confidence Tracking with Recovery Path

From NQ's coin/strategy confidence concept: track each coin's recent accuracy per model. If a model has been wrong on a coin 3+ times in a row, reduce position size or skip that coin — but don't permanently blacklist it.

```python
# coin_model_performance table:
# (symbol, model_id, last_10_trades_pf, consecutive_losses, confidence_multiplier)
#
# confidence_multiplier:
#   default: 1.0
#   after 3 consecutive losses: 0.5 (half position size)
#   after 5 consecutive losses: 0.0 (skip, don't enter)
#   after 2 consecutive wins: recover back toward 1.0
#   recovery rate: +0.25 per winning trade
```

This is NOT a permanent blacklist. Every coin gets a second chance. It just reduces exposure when the model is misfiring on a specific coin.

### 4. Drawdown Circuit Breaker

From NQ's `dd_circuit_breaker` in strategy_registry: if a model's paper account drawdown exceeds a threshold, pause it temporarily.

```python
# Per forward-test model:
# if ft_max_drawdown_pct > 30%: pause model for 48h (no new entries)
# Champion model:
# if champion_drawdown_7d > 20%: alert Rob, reduce position size to 50%
# if champion_drawdown_7d > 35%: pause ALL entries, alert Rob immediately
```

The system keeps running but protects from runaway loss during model failure.

### 5. ML-Driven Exit Engine (v2+, after champion is proven)

From NQ's `exit_ml_engine.py`: a separate ML model that learns WHEN to exit an open position, trained on historical trade PnL curves.

For each in-trade bar, this model predicts P(now is the optimal exit). Trained on features:
- `bars_since_entry` — how long we've been in
- `pnl_pct` — current unrealized PnL
- `pnl_delta_1`, `pnl_delta_3` — PnL momentum
- `pnl_drawdown_from_peak` — how far from the high-water mark
- `current_bar_range` — current volatility
- `vol_ratio` — current vol vs entry bar vol
- `funding_rate_current` — are longs/shorts now paying more?

**This is a v2+ feature** — only build after the entry model is proven profitable. NQ's exit ML improved final PnL by roughly 20% vs fixed TP/SL.

### 6. Walk-Forward with Expanding Train Window

From NQ: use an expanding train window (more data = better), not a rolling fixed window.

```
Fold 1: Train on oldest 60% of data  → Test on next 20%
Fold 2: Train on oldest 80% of data  → Test on next 10%
Fold 3: Train on oldest 90% of data  → Test on final 10%
```

All 3 folds must pass the backtest gate AND bootstrap CI. The Fold 3 model (trained on the most data) is the one saved for forward test.

---

## Module 3: Label Generation

**This is the most critical module.** Getting labels wrong poisons every downstream model.

### 3.1 Path-Dependent Labels

For each historical bar at time `t`, the label asks:

**Long label:**
> Starting from close price at `t`, does price hit `+30%` (TP) before hitting `-10%` (SL) within the next 42 bars (7 days)?

**Short label:**
> Starting from close price at `t`, does price hit `-30%` (TP) before hitting `+10%` (SL) within the next 42 bars (7 days)?

```python
def compute_label(symbol, ts_idx, direction, candles, tp=0.30, sl=0.10, horizon=42):
    entry_price = candles[ts_idx]['close']
    for i in range(1, horizon + 1):
        if ts_idx + i >= len(candles):
            return None  # incomplete, skip
        high = candles[ts_idx + i]['high']
        low = candles[ts_idx + i]['low']
        if direction == 'long':
            if high >= entry_price * (1 + tp): return 1   # TP hit first
            if low <= entry_price * (1 - sl):  return 0   # SL hit first
        else:  # short
            if low <= entry_price * (1 - tp):  return 1   # TP hit first
            if high >= entry_price * (1 + sl): return 0   # SL hit first
    return 0  # neither hit within horizon → no win
```

### 3.2 Label Imbalance
Big moves are rare. Expect ~5-15% positive labels. This is handled via:
- Class weights in model training (weight positives 5-10x negatives)
- Stratified sampling in train/val splits
- Precision-focused threshold tuning (we want high precision, not recall)

### 3.3 Label Storage
```sql
CREATE TABLE labels (
    symbol TEXT,
    ts INTEGER,
    direction TEXT,   -- 'long' or 'short'
    label INTEGER,    -- 1 = big move happened, 0 = didn't
    tp_pct REAL,      -- the TP used (allows recomputing with different targets)
    sl_pct REAL,
    horizon_bars INTEGER,
    computed_at INTEGER,
    PRIMARY KEY (symbol, ts, direction, tp_pct, sl_pct)
);
```

---

## Module 4: Tournament Engine

### 4.1 Model Variants (Challenger Generator)

Every hour, generate 10 random challengers. Each variant randomly samples:

```python
PARAM_SPACE = {
    'model_type': ['lightgbm', 'xgboost', 'random_forest'],
    'n_estimators': [100, 200, 500],
    'learning_rate': [0.01, 0.05, 0.1],     # LGB/XGB only
    'num_leaves': [31, 63, 127],              # LGB only
    'max_depth': [4, 6, 8, 10],
    'neg_class_weight': [3, 5, 8, 10],       # penalize false positives
    'confidence_threshold': [0.30, 0.40, 0.50, 0.60, 0.70],
    'feature_subset': [ALL_FEATURES, NO_REGIME, PRICE_ONLY, VOLUME_HEAVY],
    'direction': ['long', 'short'],
}
```

Each challenger has a unique `model_id = sha256(params)[:12]`.

### 4.2 Backtest Gate

Run each challenger on the last 100K label samples (walk-forward: train on first 80%, test on last 20%):

```
PASS if ALL of:
  bt_trades ≥ 50
  bt_pf ≥ 2.0
  bt_precision ≥ 0.40  (40%+ of signals are actually big moves)

FAIL → retire immediately, log reason
PASS → promote to forward_test
```

### 4.3 Walk-Forward Validation (3 folds)

Don't use a single train/test split. Use 3 expanding folds:
- Fold 1: train on 60% of data, test on next 20%
- Fold 2: train on 80%, test on next 10%
- Fold 3: train on 90%, test on final 10%

All 3 folds must pass the gate. Champion candidate uses Fold 3 model (most training data).

### 4.4 Forward Test Arena

Max 15 models compete simultaneously on live data:

```
Every 4h cycle:
  For each model in forward_test:
    1. Score all 342 coins with this model
    2. If signal ≥ threshold AND position not already open → open paper position
    3. Check all open positions for this model → apply exit rules
    4. Update tournament_models: ft_trades, ft_wins, ft_pnl, ft_pf
```

**Key: each forward_test model operates independently.** They share the same coins and candles, but each model's positions, PnL, and trade history are tracked separately.

### 4.5 Demotion

After 20 FT trades:
- If `ft_pf < 1.3` → `stage = 'retired'`, free slot for new challenger

After 50 FT trades:
- If `ft_pf < 1.5` → `stage = 'retired'`

### 4.6 Champion Selection (daily)

```sql
SELECT model_id, ft_pnl, ft_pf, ft_trades
FROM tournament_models
WHERE stage = 'forward_test'
  AND ft_trades >= 20
ORDER BY ft_pnl DESC
LIMIT 1
```

If this model has 10% more FT PnL than current champion → promote. Copy pickle to `champion_long.pkl` or `champion_short.pkl`. Update `stage = 'champion'` (demote old champion back to `forward_test`).

**Separate champions for long and short.** The best long model and best short model may be completely different architectures.

---

## Module 5: Execution Engine

### 5.1 Scoring (every 4h)

```
1. Load champion_long.pkl and champion_short.pkl
2. compute_features(symbol, now_ms, db) for all 342 coins
3. Score each coin with both models
4. Rank by score descending
5. Apply regime gate: if btc_30d_return < -20%, skip ALL long entries
6. Apply regime gate: if btc_30d_return > +20%, reduce short entries
```

### 5.2 Entry Rules

```
Enter LONG if:
  ml_score_long ≥ entry_threshold AND
  rank_long ≤ 5 (top 5 long signals only) AND
  open_long_positions < MAX_LONG_POSITIONS (default 5) AND
  coin not already in open position

Enter SHORT if:
  ml_score_short ≥ entry_threshold AND
  rank_short ≤ 5 AND
  open_short_positions < MAX_SHORT_POSITIONS (default 5)
```

Entry threshold is **model-specific** — stored in `tournament_models.threshold` and copied to champion metadata at promotion time. Not a global constant.

### 5.3 Exit Rules (checked every 4h, in order)

```
1. TAKE_PROFIT:    current_price >= entry * 1.30 (long) or <= entry * 0.70 (short)
2. STOP_LOSS:      current_price <= entry * 0.90 (long) or >= entry * 1.10 (short)
3. TRAILING_STOP:  if PnL ever hit +20%, trail with 10% distance
4. TIME_STOP:      position > 7 days old
5. INVALIDATION:   re-score coin with SAME champion model used at entry
                   if score < model.invalidation_threshold → exit
                   *** uses IDENTICAL feature function as entry ***
6. REGIME_EXIT:    if regime shifts to bear AND direction=long → exit all longs
```

**The INVALIDATION threshold is set per-model at training time from the validation set:**
```python
val_scores_positive = scores[y_val == 1]  # scores on true positive examples
invalidation_threshold = np.percentile(val_scores_positive, 25)
# = "exit if score falls below 25th percentile of what the model considered a real signal"
```

### 5.4 Position Sizing (paper)

```
base_size = account_size * 0.02  (2% per position)
new_listing_boost = 1.5x if days_since_listing < 30
max_exposure = 20% of account (10 open positions × 2%)
```

### 5.5 Critical Anti-Regression Rules

- **Model entry tracking:** Every position records which `model_id` opened it (for FT tracking)
- **Feature snapshot:** At entry, save feature vector to DB. Exit re-scoring must produce consistent results.
- **No champion changes mid-cycle.** Champion promotion only happens between cycles.

---

## Module 5b: Per-Coin Confidence & Circuit Breakers

### Per-Coin Confidence Tracking (borrowed from NQ)

```sql
CREATE TABLE coin_model_confidence (
    symbol TEXT,
    model_id TEXT,
    consecutive_losses INTEGER DEFAULT 0,
    consecutive_wins INTEGER DEFAULT 0,
    last_10_trades_pf REAL,
    confidence_multiplier REAL DEFAULT 1.0,  -- 0.0=skip, 0.5=half size, 1.0=full
    last_updated INTEGER,
    PRIMARY KEY (symbol, model_id)
);
```

Rules:
- 3 consecutive losses → `confidence_multiplier = 0.5`
- 5 consecutive losses → `confidence_multiplier = 0.0` (skip coin)
- Each win recovers +0.25 (never permanent blacklist)

### Drawdown Circuit Breaker (borrowed from NQ)

```sql
-- Stored in tournament_models:
ALTER TABLE tournament_models ADD COLUMN ft_max_drawdown_pct REAL DEFAULT 0.0;
ALTER TABLE tournament_models ADD COLUMN is_paused INTEGER DEFAULT 0;
ALTER TABLE tournament_models ADD COLUMN paused_until INTEGER;  -- ts, NULL=not paused
```

Rules (checked every cycle):
- FT model drawdown > 30% → pause 48h, no new entries
- Champion drawdown > 20% → alert, reduce size to 50%
- Champion drawdown > 35% → pause ALL entries, alert Rob

---

## Module 6: Database Schema

```sql
-- Discovered coins
CREATE TABLE coins (
    symbol TEXT PRIMARY KEY,
    first_seen_ts INTEGER,
    is_active INTEGER DEFAULT 1,
    days_since_listing INTEGER,
    oldest_candle_ts INTEGER
);

-- Social / news events (append-only, never overwrite)
CREATE TABLE social_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,             -- NULL if market-wide (fear/greed, trending list)
    source TEXT,             -- 'fear_greed', 'coingecko_trending', 'reddit', 'rss_cointelegraph', 'rss_decrypt', 'github', 'cryptopanic'
    ts INTEGER,              -- when this event was collected
    event_type TEXT,         -- 'mention', 'article', 'trending', 'commit', 'vote_bullish', 'vote_bearish', 'fear_greed_score'
    numeric_value REAL,      -- score, count, rank, etc.
    text_snippet TEXT        -- headline, post title (first 280 chars)
);
CREATE INDEX idx_social_events_symbol_ts ON social_events(symbol, ts);
CREATE INDEX idx_social_events_source_ts ON social_events(source, ts);

-- Extended market data
CREATE TABLE funding_rates (
    symbol TEXT,
    ts INTEGER,               -- funding settlement timestamp
    funding_rate REAL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE open_interest (
    symbol TEXT,
    ts INTEGER,               -- snapshot timestamp (each cycle)
    oi_contracts REAL,
    oi_usd REAL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE mark_prices (
    symbol TEXT,
    ts INTEGER,
    mark_price REAL,
    index_price REAL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE tickers_24h (
    symbol TEXT,
    ts INTEGER,
    high_24h REAL,
    low_24h REAL,
    vol_24h REAL,
    price_change_pct REAL,
    PRIMARY KEY (symbol, ts)
);

-- Raw candles (immutable)
CREATE TABLE candles (
    symbol TEXT,
    ts INTEGER,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, ts)
);

-- Computed features (JSON blob — flexible, schema-free, version-tagged)
-- Storing as JSON means adding new features never requires a schema migration
CREATE TABLE features (
    symbol TEXT,
    ts INTEGER,
    feature_version TEXT,   -- sha256 hash of feature names used
    feature_names TEXT,     -- JSON array: ["price_vs_52w_high", "bb_squeeze_pct", ...]
    feature_values TEXT,    -- JSON object: {"price_vs_52w_high": 0.72, ...}
    computed_at INTEGER,
    PRIMARY KEY (symbol, ts, feature_version)
);
-- Note: JSON storage means we never need a schema migration when adding features.
-- Model-specific feature lookup: load feature_values JSON, extract model.feature_set keys.

-- Path-dependent labels
CREATE TABLE labels (
    symbol TEXT,
    ts INTEGER,
    direction TEXT,
    label INTEGER,
    tp_pct REAL, sl_pct REAL, horizon_bars INTEGER,
    computed_at INTEGER,
    PRIMARY KEY (symbol, ts, direction, tp_pct, sl_pct)
);

-- Tournament model registry
CREATE TABLE tournament_models (
    model_id TEXT PRIMARY KEY,
    direction TEXT,              -- 'long' or 'short'
    stage TEXT,                  -- 'backtest', 'forward_test', 'champion', 'retired'
    params TEXT,                 -- JSON: all hyperparams used
    feature_version TEXT,        -- which feature set this model was trained on
    entry_threshold REAL,        -- model-specific entry threshold
    invalidation_threshold REAL, -- model-specific invalidation threshold
    bt_trades INTEGER, bt_pf REAL, bt_precision REAL, bt_pnl REAL,
    ft_trades INTEGER DEFAULT 0, ft_wins INTEGER DEFAULT 0,
    ft_pnl REAL DEFAULT 0.0, ft_pf REAL DEFAULT 0.0,
    created_at INTEGER,
    promoted_to_ft_at INTEGER,
    promoted_to_champion_at INTEGER,
    retired_at INTEGER,
    retire_reason TEXT
);

-- All positions (one record per trade, linked to model)
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    direction TEXT,
    model_id TEXT,               -- which tournament model opened this
    is_champion_trade INTEGER,   -- 1 if opened by champion model
    entry_ts INTEGER,
    entry_price REAL,
    entry_ml_score REAL,
    entry_features TEXT,         -- JSON snapshot of features at entry
    exit_ts INTEGER,
    exit_price REAL,
    exit_reason TEXT,
    pnl_pct REAL,
    high_water_price REAL,
    trailing_active INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',  -- 'open', 'closed'
    FOREIGN KEY (model_id) REFERENCES tournament_models(model_id)
);

-- Cycle run log
CREATE TABLE runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER,
    ended_at INTEGER,
    regime TEXT,
    coins_scored INTEGER,
    champion_long_model TEXT,
    champion_short_model TEXT,
    entries_long INTEGER, entries_short INTEGER,
    exits_tp INTEGER, exits_sl INTEGER, exits_time INTEGER,
    exits_invalidation INTEGER, exits_regime INTEGER,
    errors TEXT
);
```

---

## Module 7: Main Cycle (orchestration/run_cycle.py)

```python
def run_cycle():
    """Every 4 hours."""

    # 0. Log cycle start
    run_id = db.log_run_start()

    # 1. Discovery
    new_coins = discover_coins()               # poll Blofin API, add new USDT pairs

    # 2. Candle update
    fetch_latest_candles(all_coins, bars=200)  # last 200 bars per coin

    # 3. Feature computation
    compute_all_features(all_coins)            # writes to features table

    # 4. Label generation (training data, incremental)
    generate_new_labels(horizon_bars=42)       # only for newly completed bars

    # 5. Execution — champion model trades
    regime = classify_regime()
    long_champion, short_champion = load_champions()
    score_and_enter(long_champion, short_champion, regime)
    check_exits(long_champion, short_champion)

    # 6. Tournament — new challengers compete
    generate_challengers(n=10)                 # hourly: skip if run < 60m ago
    backtest_new_challengers()                 # gate: PF≥2, prec≥40%, trades≥50
    score_forward_test_models()                # all FT models score + trade
    check_ft_exits()                           # update ft_pnl, ft_trades per model
    demote_underperformers()                   # ft_pf < 1.3 after 20 trades
    crown_champion_if_ready()                  # best ft_pnl with ≥20 trades

    # 7. Log cycle end
    db.log_run_end(run_id, results)
```

---

## Module 8: Dashboard

Single-page Flask app on port 8893.

### Panels

**1. Tournament Leaderboard** (main view)
- Table: all forward_test + champion models, sorted by ft_pnl
- Columns: model_id, direction, bt_pf, bt_precision, ft_trades, ft_pnl, ft_pf, stage, age
- Color: champion = gold, active FT = green, retiring soon = yellow

**2. Champion History**
- Timeline of all past champions with their FT PnL during tenure
- Shows system is continuously improving (or not)

**3. Open Positions**
- Table: symbol, direction, model_id, entry_time, current_pnl%, exit_trigger distances
- Colored by PnL (green/red)

**4. Recent Closes (48h)**
- Table: symbol, direction, entry, exit, pnl%, exit_reason
- Summary: total PnL, win rate by exit reason

**5. Feature Importance**
- Top 10 features driving current champion's predictions
- Separate for long vs short champion

**6. Regime Monitor**
- BTC 30d return, market breadth, current regime (bull/neutral/bear)
- Historical regime chart

**7. Social Signals Monitor**
- Table: top 20 coins sorted by `news_velocity_ratio` (biggest spikes in news coverage)
- CoinGecko trending coins highlighted with rank badge
- Fear & Greed gauge (live score + 7d trend)
- Recent headlines per coin (hover to expand)

**8. Funding Rate Heatmap**
- Grid: coins × funding rate (current + 7d avg)
- Highlight extremes: deep red = very positive (longs paying big), deep blue = very negative (shorts paying)
- These are often where the next big move originates

**9. System Health**
- Last cycle time, next cycle time
- Coins discovered today
- DB size, candle coverage depth
- Feature coverage: % of coins with extended data (funding, OI) available

---

## Module 9: File Structure

```
moonshot-engine/
├── orchestration/
│   └── run_cycle.py          # main 4h cycle
├── src/
│   ├── data/
│   │   ├── discovery.py      # Blofin API coin discovery
│   │   ├── candles.py        # candle fetch + storage
│   │   └── backfill.py       # historical backfill
│   ├── features/
│   │   └── compute.py        # ONE function: compute_features(symbol, ts_ms, db)
│   ├── labels/
│   │   └── generate.py       # path-dependent label generation
│   ├── tournament/
│   │   ├── challenger.py     # random variant generation
│   │   ├── backtest.py       # backtest gate (walk-forward)
│   │   ├── forward_test.py   # FT arena: score, trade, track per model
│   │   └── champion.py       # demotion, promotion, champion selection
│   ├── execution/
│   │   ├── entry.py          # entry logic (uses champion model)
│   │   └── exit.py           # exit logic (TP/SL/trail/time/invalidation/regime)
│   ├── regime/
│   │   └── classify.py       # BTC-based regime (bull/neutral/bear)
│   └── db/
│       ├── schema.py         # CREATE TABLE statements + init
│       └── queries.py        # reusable query helpers
├── dashboard/
│   └── app.py                # Flask dashboard (port 8893)
├── models/
│   ├── champion_long.pkl
│   ├── champion_short.pkl
│   └── tournament/           # all FT model pickles by model_id
├── data/
│   └── moonshot_v2.db
├── config.py                 # all constants, env-overridable
├── .env                      # local overrides
└── TOURNAMENT.md             # kept, still accurate
```

---

## Module 10: Config (config.py)

All values overridable via environment variables:

```python
# Data
CANDLE_INTERVAL = "4h"
CANDLE_LOOKBACK_BARS = 200
BACKFILL_TARGET_YEARS = 4

# Labels
TP_PCT = 0.30           # long: +30% or short: -30%
SL_PCT = 0.10           # long: -10% or short: +10%
LABEL_HORIZON_BARS = 42 # 7 days at 4h

# Tournament
MIN_BT_TRADES = 50
MIN_BT_PF = 2.0
MIN_BT_PRECISION = 0.40
MAX_FT_MODELS = 15
MIN_FT_TRADES_EVAL = 20
MIN_FT_PF_KEEP = 1.3
CHALLENGER_COUNT_PER_HOUR = 10
CHAMPION_BEAT_MARGIN = 0.10    # must beat current champion ft_pnl by 10%

# Execution
MAX_LONG_POSITIONS = 5
MAX_SHORT_POSITIONS = 5
BASE_POSITION_PCT = 0.02
NEW_LISTING_BOOST = 1.5
TIME_STOP_DAYS = 7
TRAIL_ACTIVATE_PCT = 0.20
TRAIL_DISTANCE_PCT = 0.10
INVALIDATION_GRACE_BARS = 2    # don't check invalidation for first 2 bars

# Regime
BEAR_THRESHOLD = -0.20         # btc_30d_return < -20% = bear, pause longs
BULL_THRESHOLD = 0.20

# Dashboard
DASHBOARD_PORT = 8893
```

---

## Agent Team Breakdown

This project is built by 5 agents working in parallel on separate modules. A lead agent integrates their work.

### Lead Agent (Orchestrator)
**Task:** Write `orchestration/run_cycle.py`, `src/db/schema.py`, `src/db/queries.py`, `config.py`. Define all interfaces (function signatures, DB schema) FIRST before teammates start. Write integration tests. Wire all modules together at the end.

### Agent 1: Data Layer
**Task:** `src/data/discovery.py`, `src/data/candles.py`, `src/data/backfill.py`, `src/data/extended.py`, `src/data/social.py`

**Blofin market data:**
- `GET /api/v1/market/instruments` for coin discovery
- `GET /api/v1/market/candles` for candle fetch, paginate backfill up to 4 years
- Use existing downloaded data as starting point (copy from `blofin-moonshot/data/`)
- `extended.py`: fetch and store funding rate history, OI snapshots, mark prices, 24h tickers each cycle
- Rate limit: 10 req/sec max, batch where possible (tickers = 1 call for all coins)

**Social/news data (`social.py`):**
- Runs on its own 1h timer (`blofin-moonshot-social.timer`), completely independent of main cycle
- Sources to collect every hour:
  - Fear & Greed: 1 call → insert to `social_events` as `fear_greed_score` for symbol=NULL
  - CoinGecko trending: 1 call → insert each trending coin as `trending` event with rank
  - RSS feeds (CoinTelegraph, Decrypt, The Block): parse headlines, extract coin tickers, insert as `mention` events
  - Reddit: search top 50 coins by 24h OI change for mentions across key subreddits
  - GitHub: weekly commit count for coins with known repos (maintain a static mapping file `data/github_repos.json`)
- All writes are append-only to `social_events` — never update, never delete
- Graceful failure: if Reddit is down, log warning and continue. Never crash.
- Tests: verify events are inserted, verify symbol extraction from RSS headlines, verify rate limits respected

### Agent 2: Features + Labels
**Task:** `src/features/registry.py`, `src/features/compute.py`, `src/labels/generate.py`
- Implement `FEATURE_REGISTRY` dict — all 37 features (25 core + 12 extended)
- Single function: `compute_features(symbol, ts_ms, db, feature_names=None) -> dict`
  - If `feature_names=None`: compute all available features
  - If list provided: compute only those features (for model-specific inference)
  - Returns dict with `feature_version` hash
- Must be callable identically from: training, live scoring, exit re-scoring
- Graceful NULL handling: if extended data not available for a coin, return neutral fill (0.0 or 0.5 depending on feature) — never crash
- Path-dependent label generation for both long and short
- PnL-weighted sample weights (from NQ): `weight = 1.0` for TP, `(SL/TP) × 1.5` for SL
- Tests: verify features bounded, verify labels correct on known examples, verify NULL handling

### Agent 3: Tournament Engine
**Task:** `src/tournament/challenger.py`, `src/tournament/backtest.py`, `src/tournament/forward_test.py`, `src/tournament/champion.py`
- Challenger generation: random sampling from param space + feature subsets from registry
- Walk-forward backtest with 3 expanding folds (NQ pattern): all 3 folds must pass gate
- Bootstrap CI on PF (1000 resamples, lower bound ≥ 1.0 required)
- PnL-weighted training (from NQ): TP=1.0 weight, SL=0.5 weight
- FT arena: score coins, open/close positions per model, track ft_pnl/ft_trades/ft_pf
- Per-coin confidence tracking per model (consecutive loss tracking, multiplier 0.0-1.0)
- Drawdown circuit breaker per FT model (pause if drawdown > 30%)
- Champion selection: best ft_pnl with ≥20 trades, 10% beat margin
- Tests: verify backtest gate filters correctly, verify bootstrap CI, verify ft_pnl accumulates, verify champion promotion

### Agent 4: Execution Engine
**Task:** `src/execution/entry.py`, `src/execution/exit.py`, `src/regime/classify.py`
- Entry: load champion pkl, score all coins, apply regime gate, open positions
- Exit: all 6 exit conditions in correct priority order
- CRITICAL: Exit INVALIDATION uses `compute_features()` — same function as entry. No shortcuts.
- Regime: BTC-based bull/neutral/bear classification
- Tests: verify TP/SL fire at correct prices, verify INVALIDATION uses correct threshold, verify regime gate blocks longs in bear

### Agent 5: Dashboard
**Task:** `dashboard/app.py`
- 7-panel Flask dashboard on port 8893
- Tournament leaderboard as main view
- Champion history timeline
- Position monitor, recent closes, feature importance, regime monitor, system health
- Auto-refreshes every 5 minutes
- Mobile-friendly layout

---

## Success Criteria

### Minimum Viable (Week 1)
- [ ] 342 coins discovered and candles fetching every 4h
- [ ] Labels generating correctly (path-dependent, both directions)
- [ ] Tournament generating challengers and running backtest gate
- [ ] Champion scoring and entering paper positions
- [ ] Exit logic firing correctly (TP/SL/TIME at minimum)
- [ ] FT models accumulating ft_trades and ft_pnl

### Full System (Week 2)
- [ ] First tournament champion crowned from FT competition (not manually set)
- [ ] Dashboard showing tournament leaderboard with live data
- [ ] INVALIDATION exit working correctly (no mass exits on model switch)
- [ ] New listings auto-detected and entering competition
- [ ] 20+ closed paper trades with clear exit reason attribution

### Proof of Life (Week 3+)
- [ ] Champion changes hands at least once (tournament actually promoting winners)
- [ ] System has been running continuously for 7 days without crashes
- [ ] avg_ft_pnl for champion > 0 (making money, not losing)
- [ ] Rob reviews results and decides on live capital

---

## What This Is NOT

- Not a high-frequency system (4h candles, 4h cycles)
- Not a leverage play (position sizing is conservative by default)
- Not a copy of the NQ pipeline (different asset class, different logic)
- Not dependent on CoinGecko, TradingView, or any external data source
- Not live until Rob explicitly approves

---

*This document is the complete spec. Agent teams build from this. No improvisation on core architecture. Questions go to Jarvis before coding.*
