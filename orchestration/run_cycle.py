#!/usr/bin/env python3
"""Moonshot v2 — Main 4h orchestration cycle.

This is the heartbeat of the system. Every 4 hours:
1. Discover new coins on Blofin
2. Fetch latest candles + extended data
3. Compute features for all coins
4. Generate labels for newly completed bars
5. Execution: champion model scores → entries + exits
6. Tournament: challengers → backtest → FT scoring → demotions → promotions
7. Log results
"""

import sys
import time
import traceback
from pathlib import Path
import fcntl

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from config import log
from src.db.schema import init_db, get_db


def run_cycle():
    """Execute one complete 4h cycle."""
    lock_path = Path(config.DB_PATH).with_suffix('.cycle.lock')
    lock_fh = open(lock_path, 'w')
    try:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("Another moonshot cycle is already running; skipping this trigger")
        lock_fh.close()
        return False

    db = get_db()
    ts_ms = int(time.time() * 1000)
    errors = []

    # ── 0. Log cycle start ───────────────────────────────────────────────
    cur = db.execute(
        "INSERT INTO runs (started_at) VALUES (?)", (ts_ms,)
    )
    run_id = cur.lastrowid
    db.commit()
    log.info("═══ Cycle %d started ═══", run_id)

    # ── 1. Discovery ─────────────────────────────────────────────────────
    try:
        from src.data.discovery import discover_coins, update_days_since_listing
        all_symbols = discover_coins(db)
        log.info("Discovery: %d active coins", len(all_symbols))
        update_days_since_listing(db)
    except Exception as e:
        log.error("Discovery failed: %s", e)
        errors.append(f"discovery: {e}")
        # Fall back to known coins
        rows = db.execute("SELECT symbol FROM coins WHERE is_active=1").fetchall()
        all_symbols = [r["symbol"] for r in rows]

    # ── 2. Candle update ─────────────────────────────────────────────────
    try:
        from src.data.candles import fetch_latest_candles
        fetch_latest_candles(db, all_symbols, bars=config.CANDLE_LOOKBACK_BARS)
        log.info("Candles updated for %d coins", len(all_symbols))
    except Exception as e:
        log.error("Candle fetch failed: %s", e)
        errors.append(f"candles: {e}")

    # ── 2b. Opportunistic backfill — new coins lacking full history ───────
    try:
        from src.data.candles import backfill_candles
        import config as _cfg
        target_ms = int(time.time() * 1000) - int(
            _cfg.BACKFILL_TARGET_YEARS * 365.25 * 24 * 3600 * 1000
        )
        needs_backfill = db.execute(
            """SELECT symbol FROM coins
               WHERE is_active = 1
               AND (oldest_candle_ts IS NULL OR oldest_candle_ts > ?)
               LIMIT 5""",
            (target_ms,),
        ).fetchall()
        for row in needs_backfill:
            backfill_candles(db, row["symbol"])
        if needs_backfill:
            log.info("Opportunistic backfill: %d coins", len(needs_backfill))
    except Exception as e:
        log.warning("Opportunistic backfill failed: %s", e)

    # ── 3. Extended data (funding, OI, mark price, tickers) ──────────────
    try:
        from src.data.extended import fetch_all_extended
        fetch_all_extended(db, all_symbols)
        log.info("Extended data fetched")
    except Exception as e:
        log.error("Extended data failed: %s", e)
        errors.append(f"extended: {e}")

    # ── 4. Feature computation ───────────────────────────────────────────
    try:
        from src.features.compute import compute_all_features
        compute_all_features(db, all_symbols, ts_ms)
        log.info("Features computed for %d coins", len(all_symbols))
    except Exception as e:
        log.error("Feature computation failed: %s", e)
        errors.append(f"features: {e}")

    # ── 5. Label generation (incremental — only newly completed bars) ────
    try:
        from src.labels.generate import generate_labels
        generate_labels(
            db,
            symbols=all_symbols,
            tp=config.TP_PCT,
            sl=config.SL_PCT,
            horizon=config.LABEL_HORIZON_BARS,
        )
        log.info("Labels generated")
    except Exception as e:
        log.error("Label generation failed: %s", e)
        errors.append(f"labels: {e}")

    # ── 6. Execution — trades ────────────────────────────────────────────
    entries_long = 0
    entries_short = 0
    entries_new_listing = 0
    exits_tp = exits_sl = exits_time = exits_trail = 0
    exits_invalidation = exits_regime = 0
    regime = "neutral"
    champion_long_id = None
    champion_short_id = None

    try:
        from src.regime.classify import classify_regime
        regime = classify_regime(db, ts_ms)
        log.info("Regime: %s", regime)
    except Exception as e:
        log.error("Regime classification failed: %s", e)
        errors.append(f"regime: {e}")

    # ── 6a. New Listing Rule-Based Entry (before champion ML) ────────────
    try:
        from src.execution.new_listing_entry import process_new_listings
        before_count = db.execute(
            "SELECT COUNT(*) as cnt FROM positions WHERE status = 'open' AND model_id = 'new_listing'"
        ).fetchone()["cnt"]
        process_new_listings(db)
        after_count = db.execute(
            "SELECT COUNT(*) as cnt FROM positions WHERE status = 'open' AND model_id = 'new_listing'"
        ).fetchone()["cnt"]
        entries_new_listing = after_count - before_count
        log.info("New listings: %d entries", entries_new_listing)
    except Exception as e:
        log.error("New listing entry failed: %s", e)
        errors.append(f"new_listings: {e}")

    try:
        from src.tournament.champion import load_champions
        long_champ, short_champ = load_champions(db)
        champion_long_id = long_champ["model_id"] if long_champ else None
        champion_short_id = short_champ["model_id"] if short_champ else None
        log.info(
            "Champions: long=%s short=%s",
            champion_long_id or "none",
            champion_short_id or "none",
        )

        if long_champ or short_champ:
            from src.execution.entry import score_and_enter
            entry_result = score_and_enter(
                db, long_champ, short_champ, regime, ts_ms
            )
            entries_long = entry_result.get("entries_long", 0)
            entries_short = entry_result.get("entries_short", 0)
            log.info("Champion entries: %d long, %d short", entries_long, entries_short)

            from src.execution.exit import check_exits
            exit_result = check_exits(
                db, long_champ, short_champ, regime, ts_ms
            )
            exits_tp = exit_result.get("exits_tp", 0)
            exits_sl = exit_result.get("exits_sl", 0)
            exits_trail = exit_result.get("exits_trail", 0)
            exits_time = exit_result.get("exits_time", 0)
            exits_invalidation = exit_result.get("exits_invalidation", 0)
            exits_regime = exit_result.get("exits_regime", 0)
            log.info(
                "Exits: TP=%d SL=%d trail=%d time=%d invalidation=%d regime=%d",
                exits_tp, exits_sl, exits_trail, exits_time,
                exits_invalidation, exits_regime,
            )
    except Exception as e:
        log.error("Execution failed: %s", e)
        errors.append(f"execution: {e}")
        traceback.print_exc()

    # ── 7. Tournament — challengers compete ──────────────────────────────
    try:
        from src.tournament.challenger import generate_challengers
        new_challengers = generate_challengers(
            db, n=config.CHALLENGER_COUNT_PER_HOUR
        )
        log.info("Generated %d new challengers", len(new_challengers))
    except Exception as e:
        log.error("Challenger generation failed: %s", e)
        errors.append(f"challengers: {e}")

    try:
        from src.tournament.backtest import backtest_new_challengers
        backtest_new_challengers(db)
        log.info("Backtest round complete")
    except Exception as e:
        log.error("Backtest failed: %s", e)
        errors.append(f"backtest: {e}")

    try:
        from src.tournament.forward_test import score_forward_test_models
        score_forward_test_models(db, all_symbols, ts_ms)
        log.info("Forward test scoring complete")

        # BUG FIX 2026-03-16: Update ft_stats for ALL FT models after each cycle
        # Previously only updated when positions closed in that specific cycle,
        # causing stats to be stale if cycles were interrupted or crashed.
        from src.tournament.forward_test import _update_model_ft_stats
        ft_models = db.execute(
            'SELECT model_id FROM tournament_models WHERE stage IN ("forward_test", "ft")'
        ).fetchall()
        for m in ft_models:
            _update_model_ft_stats(db, m["model_id"])
        db.commit()
        log.info("FT stats updated for %d models", len(ft_models))
    except Exception as e:
        log.error("FT scoring failed: %s", e)
        errors.append(f"ft_scoring: {e}")

    try:
        from src.tournament.champion import demote_underperformers
        demote_underperformers(db)
    except Exception as e:
        log.error("Demotion failed: %s", e)
        errors.append(f"demotion: {e}")

    try:
        from src.tournament.champion import crown_champion_if_ready
        crown_champion_if_ready(db)
    except Exception as e:
        log.error("Champion promotion failed: %s", e)
        errors.append(f"promotion: {e}")

    # ── 8. Log cycle end ─────────────────────────────────────────────────
    end_ts = int(time.time() * 1000)
    duration_s = (end_ts - ts_ms) / 1000
    db.execute(
        """UPDATE runs SET
            ended_at=?, regime=?, coins_scored=?,
            champion_long_model=?, champion_short_model=?,
            entries_long=?, entries_short=?,
            exits_tp=?, exits_sl=?, exits_time=?, exits_trail=?,
            exits_invalidation=?, exits_regime=?,
            errors=?
        WHERE run_id=?""",
        (
            end_ts, regime, len(all_symbols),
            champion_long_id, champion_short_id,
            entries_long, entries_short,
            exits_tp, exits_sl, exits_time, exits_trail,
            exits_invalidation, exits_regime,
            "; ".join(errors) if errors else None,
            run_id,
        ),
    )
    db.commit()
    db.close()

    log.info(
        "═══ Cycle %d done in %.1fs — %d errors ═══",
        run_id, duration_s, len(errors),
    )
    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
    lock_fh.close()
    return len(errors) == 0


def run_social_collection():
    """Run social data collection (separate 1h timer)."""
    db = get_db()
    try:
        from src.data.social import run_social_collection as collect
        collect(db)
        log.info("Social collection complete")
    except Exception as e:
        log.error("Social collection failed: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    # Initialize DB on first run
    init_db()

    if len(sys.argv) > 1 and sys.argv[1] == "--social":
        run_social_collection()
    else:
        success = run_cycle()
        sys.exit(0 if success else 1)
