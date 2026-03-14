#!/usr/bin/env python3
"""Replay retired FT models over the most recent historical window.

This script:
1. Replays each selected model independently over the last N days
2. Replaces that model's prior FT positions with the replayed trades
3. Updates ft_* stats in tournament_models
4. Optionally un-retires models whose recent replay is good enough
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from config import (
    INVALIDATION_GRACE_BARS,
    SL_PCT,
    TIME_STOP_BARS,
    TP_PCT,
    TRAIL_ACTIVATE_PCT,
    TRAIL_DISTANCE_PCT,
)
from src.db.schema import get_db
from src.scoring.thresholds import effective_entry_threshold
from src.tournament.challenger import FEATURE_SUBSETS
from src.tournament.forward_test import (
    _compute_exit_pnl,
    _get_feature_values,
    _load_model,
)

warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names, but LGBMClassifier was fitted with feature names",
    category=UserWarning,
)


def _resolve_feature_names(raw_feature_set):
    if not raw_feature_set:
        return FEATURE_SUBSETS["core_only"]
    try:
        parsed = json.loads(raw_feature_set)
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        return parsed
    return FEATURE_SUBSETS.get(raw_feature_set, FEATURE_SUBSETS["core_only"])


def _compute_stats(closed_positions):
    trades = len(closed_positions)
    if trades == 0:
        return {
            "ft_trades": 0,
            "ft_wins": 0,
            "ft_pnl": 0.0,
            "ft_pf": 0.0,
            "ft_max_drawdown_pct": 0.0,
        }

    pnls = [float(pos["pnl_pct"]) for pos in closed_positions]
    wins = sum(1 for pnl in pnls if pnl > 0)
    total_pnl = sum(pnls)
    win_pnl = sum(pnl for pnl in pnls if pnl > 0)
    loss_pnl = abs(sum(pnl for pnl in pnls if pnl < 0))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 999.0

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cum += pnl
        peak = max(peak, cum)
        dd = (peak - cum) / max(peak, 0.01)
        max_dd = max(max_dd, dd)

    return {
        "ft_trades": trades,
        "ft_wins": wins,
        "ft_pnl": total_pnl,
        "ft_pf": pf,
        "ft_max_drawdown_pct": max_dd,
    }


def _close_position(position, ts_ms, current_price, reason):
    pnl_pct = _compute_exit_pnl(
        position["direction"], position["entry_price"], current_price
    )
    position["status"] = "closed"
    position["exit_ts"] = ts_ms
    position["exit_price"] = current_price
    position["exit_reason"] = reason
    position["pnl_pct"] = pnl_pct
    return position


def _check_exit_conditions_fast(position, ts_ms, current_price, current_score, invalidation_threshold):
    direction = position["direction"]
    entry_price = position["entry_price"]
    entry_ts = position["entry_ts"]
    high_water = position["high_water_price"] or entry_price

    pnl_pct = _compute_exit_pnl(direction, entry_price, current_price)
    if pnl_pct >= TP_PCT:
        return "tp"
    if pnl_pct <= -SL_PCT:
        return "sl"

    if direction == "long":
        new_hwm = max(high_water, current_price)
        pullback = (new_hwm - current_price) / new_hwm if new_hwm else 0.0
    else:
        new_hwm = min(high_water, current_price) if high_water > 0 else current_price
        pullback = (current_price - new_hwm) / new_hwm if new_hwm else 0.0

    hwm_pnl = _compute_exit_pnl(direction, entry_price, new_hwm)
    if hwm_pnl >= TRAIL_ACTIVATE_PCT and pullback >= TRAIL_DISTANCE_PCT:
        return "trail"

    bars_elapsed = (ts_ms - entry_ts) / (4 * 3600 * 1000)
    if bars_elapsed >= TIME_STOP_BARS:
        return "time"

    if (
        invalidation_threshold is not None
        and position["entry_ml_score"] is not None
        and bars_elapsed >= INVALIDATION_GRACE_BARS
        and position["entry_ml_score"] < invalidation_threshold
    ):
        return "invalidation"

    return None


def _replay_model(db, model_row, ts_list, all_symbols):
    model_id = model_row["model_id"]
    model = _load_model(model_id)
    if model is None:
        raise RuntimeError(f"Missing pickle for {model_id}")

    feature_names = _resolve_feature_names(model_row["feature_set"])
    direction = model_row["direction"]
    invalidation_threshold = model_row["invalidation_threshold"]
    entry_threshold = effective_entry_threshold(
        model_row["entry_threshold"],
        invalidation_threshold,
    )

    open_positions = []
    closed_positions = []

    for ts_ms in ts_list:
        price_rows = db.execute(
            "SELECT symbol, close FROM candles WHERE ts = ?",
            (ts_ms,),
        ).fetchall()
        price_map = {row["symbol"]: float(row["close"]) for row in price_rows}
        open_symbols = {pos["symbol"] for pos in open_positions}

        batch_symbols = []
        batch_vectors = []
        for symbol in all_symbols:
            if symbol in open_symbols:
                continue

            vec = _get_feature_values(db, symbol, ts_ms, feature_names)
            if vec is None:
                continue
            if symbol not in price_map:
                continue
            batch_symbols.append(symbol)
            batch_vectors.append(vec)

        score_map = {}
        if batch_vectors:
            scores = model.predict_proba(np.array(batch_vectors, dtype=np.float32))[:, 1]
            for symbol, score in zip(batch_symbols, scores):
                score = float(score)
                score_map[symbol] = score
                if score < entry_threshold:
                    continue

                entry_price = price_map.get(symbol)
                if entry_price is None:
                    continue

                open_positions.append({
                    "symbol": symbol,
                    "direction": direction,
                    "model_id": model_id,
                    "entry_ts": ts_ms,
                    "entry_price": entry_price,
                    "entry_ml_score": score,
                    "high_water_price": entry_price,
                    "trailing_active": 0,
                    "status": "open",
                })

        still_open = []
        for position in open_positions:
            current_price = price_map.get(position["symbol"])
            if current_price is None:
                still_open.append(position)
                continue

            current_score = score_map.get(position["symbol"])
            exit_reason = _check_exit_conditions_fast(
                position,
                ts_ms,
                current_price,
                current_score,
                invalidation_threshold,
            )

            direction = position["direction"]
            hwm = position["high_water_price"] or position["entry_price"]
            if direction == "long":
                new_hwm = max(hwm, current_price)
            else:
                new_hwm = min(hwm, current_price) if hwm > 0 else current_price
            position["high_water_price"] = new_hwm
            hwm_pnl = _compute_exit_pnl(direction, position["entry_price"], new_hwm)
            if hwm_pnl >= TRAIL_ACTIVATE_PCT:
                position["trailing_active"] = 1

            if exit_reason:
                closed_positions.append(
                    _close_position(position, ts_ms, current_price, exit_reason)
                )
            else:
                still_open.append(position)

        open_positions = still_open

    if ts_list:
        final_ts = ts_list[-1]
        price_rows = db.execute(
            "SELECT symbol, close FROM candles WHERE ts = ?",
            (final_ts,),
        ).fetchall()
        price_map = {row["symbol"]: float(row["close"]) for row in price_rows}
        final_open = []
        for position in open_positions:
            current_price = price_map.get(position["symbol"])
            if current_price is None:
                final_open.append(position)
                continue
            closed_positions.append(
                _close_position(position, final_ts, current_price, "retest_end")
            )
        open_positions = final_open

    return closed_positions, _compute_stats(closed_positions)


def _replace_model_positions(db, model_id, closed_positions):
    db.execute(
        "DELETE FROM positions WHERE model_id = ? AND is_champion_trade = 0",
        (model_id,),
    )

    for pos in closed_positions:
        db.execute(
            """INSERT INTO positions
               (symbol, direction, model_id, is_champion_trade,
                entry_ts, entry_price, entry_ml_score,
                exit_ts, exit_price, exit_reason, pnl_pct,
                high_water_price, trailing_active, status, leverage)
               VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', 1)""",
            (
                pos["symbol"],
                pos["direction"],
                pos["model_id"],
                pos["entry_ts"],
                pos["entry_price"],
                pos["entry_ml_score"],
                pos["exit_ts"],
                pos["exit_price"],
                pos["exit_reason"],
                pos["pnl_pct"],
                pos["high_water_price"],
                pos["trailing_active"],
            ),
        )


def _update_model_record(db, model_id, stats, unretire):
    now_ms = int(time.time() * 1000)
    if unretire:
        db.execute(
            """UPDATE tournament_models
               SET ft_trades = ?, ft_wins = ?, ft_pnl = ?, ft_pf = ?,
                   ft_max_drawdown_pct = ?, stage = 'forward_test',
                   retired_at = NULL, retire_reason = NULL, promoted_to_ft_at = ?,
                   is_paused = 0, paused_until = NULL
               WHERE model_id = ?""",
            (
                stats["ft_trades"],
                stats["ft_wins"],
                stats["ft_pnl"],
                stats["ft_pf"],
                stats["ft_max_drawdown_pct"],
                now_ms,
                model_id,
            ),
        )
    else:
        db.execute(
            """UPDATE tournament_models
               SET ft_trades = ?, ft_wins = ?, ft_pnl = ?, ft_pf = ?,
                   ft_max_drawdown_pct = ?
               WHERE model_id = ?""",
            (
                stats["ft_trades"],
                stats["ft_wins"],
                stats["ft_pnl"],
                stats["ft_pf"],
                stats["ft_max_drawdown_pct"],
                model_id,
            ),
        )


def _should_unretire(stats, min_trades, min_pf, min_pnl):
    return (
        stats["ft_trades"] >= min_trades
        and stats["ft_pf"] >= min_pf
        and stats["ft_pnl"] >= min_pnl
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--model-id", action="append", dest="model_ids")
    parser.add_argument("--min-bt-pf", type=float, default=1.0)
    parser.add_argument("--retire-reason-like", default="ft_pf_below_%")
    parser.add_argument("--unretire-min-trades", type=int, default=10)
    parser.add_argument("--unretire-min-pf", type=float, default=1.0)
    parser.add_argument("--unretire-min-pnl", type=float, default=0.0)
    args = parser.parse_args()

    db = get_db()
    end_ts = db.execute("SELECT MAX(ts) AS ts FROM candles").fetchone()["ts"]
    start_ts = end_ts - (args.days * 24 * 3600 * 1000)

    ts_rows = db.execute(
        "SELECT DISTINCT ts FROM candles WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
        (start_ts, end_ts),
    ).fetchall()
    ts_list = [row["ts"] for row in ts_rows]
    all_symbols = [
        row["symbol"]
        for row in db.execute(
            "SELECT symbol FROM coins WHERE is_active = 1 ORDER BY symbol ASC"
        ).fetchall()
    ]

    if args.model_ids:
        placeholders = ",".join("?" for _ in args.model_ids)
        model_rows = db.execute(
            f"""SELECT model_id, direction, feature_set, entry_threshold, invalidation_threshold
                FROM tournament_models
                WHERE model_id IN ({placeholders})""",
            args.model_ids,
        ).fetchall()
    else:
        model_rows = db.execute(
            """SELECT model_id, direction, feature_set, entry_threshold, invalidation_threshold
               FROM tournament_models
               WHERE stage = 'retired'
                 AND retire_reason LIKE ?
                 AND bt_pf >= ?
               ORDER BY bt_pnl DESC
               LIMIT ?""",
            (args.retire_reason_like, args.min_bt_pf, args.limit),
        ).fetchall()

    results = []
    if not ts_list:
        raise RuntimeError("No candle timestamps found in the replay window")

    for model_row in model_rows:
        closed_positions, stats = _replay_model(db, model_row, ts_list, all_symbols)
        _replace_model_positions(db, model_row["model_id"], closed_positions)
        unretire = _should_unretire(
            stats,
            min_trades=args.unretire_min_trades,
            min_pf=args.unretire_min_pf,
            min_pnl=args.unretire_min_pnl,
        )
        _update_model_record(db, model_row["model_id"], stats, unretire)
        results.append({
            "model_id": model_row["model_id"],
            "direction": model_row["direction"],
            "ft_trades": stats["ft_trades"],
            "ft_wins": stats["ft_wins"],
            "ft_pnl": stats["ft_pnl"],
            "ft_pf": stats["ft_pf"],
            "ft_max_drawdown_pct": stats["ft_max_drawdown_pct"],
            "unretired": unretire,
        })
        print(json.dumps(results[-1], sort_keys=True))

    db.commit()


if __name__ == "__main__":
    main()
