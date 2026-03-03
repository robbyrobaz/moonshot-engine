# Moonshot v2 — Crypto Big-Move Detection Engine

Self-improving tournament-based engine that detects large price moves (30%+) across all Blofin USDT perpetual swap pairs. Models compete continuously — winners get promoted, losers get retired.

## Quick Start

```bash
# Setup
cd /home/rob/.openclaw/workspace/moonshot-engine
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Initialize database
.venv/bin/python -c "from src.db.schema import init_db; init_db(); print('DB OK')"

# Run one cycle manually
.venv/bin/python orchestration/run_cycle.py

# Run social collection
.venv/bin/python orchestration/run_cycle.py --social

# Start dashboard
.venv/bin/python dashboard/app.py
# → http://localhost:8893

# Install systemd timers (4h cycle + 1h social + dashboard)
chmod +x install_services.sh
./install_services.sh
```

## Architecture

```
4h Cycle: Discovery → Candles → Features → Labels → Execution → Tournament
1h Timer: Social data collection (Fear/Greed, trending, RSS, Reddit, GitHub)
Always-on: Flask dashboard on port 8893
```

### Tournament Flow
1. **Challengers** generated hourly (random model params + feature subsets)
2. **Backtest gate**: 3-fold walk-forward, PF≥2.0, precision≥40%, trades≥50, bootstrap CI≥1.0
3. **Forward test**: max 15 models competing on live data, paper positions
4. **Champion**: best ft_pnl with ≥20 FT trades (separate long/short champions)
5. **Demotion**: ft_pf < 1.3 after 20 trades → retired

### Key Design Rules
- Single `compute_features()` function used for training, scoring, and exit re-scoring
- Features stored as JSON blobs (no schema migrations needed)
- Path-dependent labels: did price hit +30% before -10%?
- PnL-weighted training: TP=1.0, SL=0.5
- Per-model entry_threshold and invalidation_threshold
- Paper trading only — no live orders

## Project Structure

```
orchestration/run_cycle.py     Main 4h cycle + social collection entry point
src/data/discovery.py          Blofin coin discovery (all USDT swap pairs)
src/data/candles.py            Candle fetch + historical backfill
src/data/extended.py           Funding rates, OI, mark prices, tickers
src/data/social.py             Fear/Greed, CoinGecko trending, RSS, Reddit, GitHub
src/features/registry.py       FEATURE_REGISTRY — all 50 registered features
src/features/compute.py        compute_features() — THE single function
src/labels/generate.py         Path-dependent label generation
src/tournament/challenger.py   Random variant generation
src/tournament/backtest.py     Walk-forward 3-fold backtest + bootstrap CI
src/tournament/forward_test.py FT arena — per-model PnL tracking
src/tournament/champion.py     Demotion + promotion logic
src/execution/entry.py         Champion model entry logic
src/execution/exit.py          TP/SL/trail/time/invalidation/regime exits
src/regime/classify.py         BTC-based market regime classification
src/db/schema.py               Database schema + init_db()
dashboard/app.py               Flask dashboard (port 8893)
config.py                      All constants (env-overridable)
```

## Configuration

All config values in `config.py` are overridable via environment variables with `MOONSHOT_` prefix:

```bash
export MOONSHOT_TP_PCT=0.25        # Override take profit %
export MOONSHOT_MAX_FT_MODELS=20   # Override max forward test models
export MOONSHOT_DASHBOARD_PORT=9000
```

## Data Sources

- **Price/Market**: Blofin API only (candles, funding rates, OI, mark prices, tickers)
- **Social (Tier 1, free)**: Fear & Greed Index, CoinGecko trending, RSS feeds, Reddit, GitHub
- **No external paid sources** for price or volume data
