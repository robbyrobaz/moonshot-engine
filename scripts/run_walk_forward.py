#!/usr/bin/env python3
"""Dry-run walk-forward replay for tournament models.

Usage:
  python3 scripts/run_walk_forward.py --strategy champion --tp 10 --sl 5 --dry-run

This script replays the selected model(s) over the most recent historical
window, applying alternate TP/SL settings without mutating the database.
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np

import config
from src.db.schema import get_db
from src.tournament.challenger import FEATURE_SUBSETS
from src.tournament.forward_test import (
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


def _compute_pnl(direction: str, entry_price: float, exit_price: float) -> float:
    if direction == "long":
        return (exit_price - entry_price) / entry_price
    return (entry_price - exit_price) / entry_price


def _compute_stats(closed_positions):
    trades = len(closed_positions)
    if trades == 0:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "pnl": 0.0,
            "pf": 0.0,
            "avg_hold_hours": 0.0,
            "by_reason": {},
        }

    pnls = [float(pos["pnl_pct"]) for pos in closed_positions]
    holds = [
        (float(pos["exit_ts"]) - float(pos["entry_ts"])) / (3600.0 * 1000.0)
        for pos in closed_positions
    ]
    wins = sum(1 for pnl in pnls if pnl > 0)
    losses = trades - wins
    win_sum = sum(pnl for pnl in pnls if pnl > 0)
    loss_sum = abs(sum(pnl for pnl in pnls if pnl < 0))
    pf = win_sum / loss_sum if loss_sum > 0 else 999.0

    by_reason = {}
    for pos in closed_positions:
        reason = pos["exit_reason"]
        stats = by_reason.setdefault(reason, {"count": 0, "pnl": 0.0, "wins": 0})
        stats["count"] += 1
        stats["pnl"] += float(pos["pnl_pct"])
        if pos["pnl_pct"] > 0:
            stats["wins"] += 1

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / trades,
        "pnl": sum(pnls),
        "pf": pf,
        "avg_hold_hours": sum(holds) / len(holds),
        "by_reason": by_reason,
    }


def _check_exit(position, ts_ms, current_price, current_score, inv_threshold, tp_pct, sl_pct):
    direction = position["direction"]
    entry_price = position["entry_price"]
    high_water = position["high_water_price"] or entry_price
    pnl_pct = _compute_pnl(direction, entry_price, current_price)

    if pnl_pct >= tp_pct:
        return "tp"
    if pnl_pct <= -sl_pct:
        return "sl"

    if direction == "long":
        new_hwm = max(high_water, current_price)
        pullback = (new_hwm - current_price) / new_hwm if new_hwm else 0.0
    else:
        new_hwm = min(high_water, current_price) if high_water > 0 else current_price
        pullback = (current_price - new_hwm) / new_hwm if new_hwm else 0.0

    hwm_pnl = _compute_pnl(direction, entry_price, new_hwm)
    if hwm_pnl >= config.TRAIL_ACTIVATE_PCT and pullback >= config.TRAIL_DISTANCE_PCT:
        return "trail"

    bars_elapsed = (ts_ms - position["entry_ts"]) / (4 * 3600 * 1000)
    if bars_elapsed >= config.TIME_STOP_BARS:
        return "time"

    if (
        inv_threshold is not None
        and current_score is not None
        and bars_elapsed >= config.INVALIDATION_GRACE_BARS
        and current_score < inv_threshold
    ):
        return "invalidation"

    return None


def _replay_model(db, model_row, ts_list, all_symbols, tp_pct, sl_pct):
    model_id = model_row["model_id"]
    model = _load_model(model_id)
    if model is None:
        raise RuntimeError(f"Missing pickle for {model_id}")

    feature_names = _resolve_feature_names(model_row["feature_set"])
    direction = model_row["direction"]
    entry_threshold = float(model_row["entry_threshold"])
    inv_threshold = model_row["invalidation_threshold"]

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
            if symbol in open_symbols or symbol not in price_map:
                continue
            vec = _get_feature_values(db, symbol, ts_ms, feature_names)
            if vec is None:
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
                open_positions.append({
                    "symbol": symbol,
                    "direction": direction,
                    "model_id": model_id,
                    "entry_ts": ts_ms,
                    "entry_price": price_map[symbol],
                    "entry_ml_score": score,
                    "high_water_price": price_map[symbol],
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
            exit_reason = _check_exit(
                position,
                ts_ms,
                current_price,
                current_score,
                inv_threshold,
                tp_pct,
                sl_pct,
            )

            direction = position["direction"]
            hwm = position["high_water_price"] or position["entry_price"]
            if direction == "long":
                position["high_water_price"] = max(hwm, current_price)
            else:
                position["high_water_price"] = min(hwm, current_price) if hwm > 0 else current_price

            if exit_reason:
                position["status"] = "closed"
                position["exit_ts"] = ts_ms
                position["exit_price"] = current_price
                position["exit_reason"] = exit_reason
                position["pnl_pct"] = _compute_pnl(direction, position["entry_price"], current_price)
                closed_positions.append(position)
            else:
                still_open.append(position)

        open_positions = still_open

    if ts_list:
        last_ts = ts_list[-1]
        last_prices = {
            row["symbol"]: float(row["close"])
            for row in db.execute(
                "SELECT symbol, close FROM candles WHERE ts = ?",
                (last_ts,),
            ).fetchall()
        }
        for position in open_positions:
            current_price = last_prices.get(position["symbol"])
            if current_price is None:
                continue
            position["status"] = "closed"
            position["exit_ts"] = last_ts
            position["exit_price"] = current_price
            position["exit_reason"] = "replay_end"
            position["pnl_pct"] = _compute_pnl(
                position["direction"], position["entry_price"], current_price
            )
            closed_positions.append(position)

    return closed_positions, _compute_stats(closed_positions)


def _load_model_rows(db, strategy: str, model_ids: list[str] | None):
    if model_ids:
        placeholders = ",".join("?" for _ in model_ids)
        return db.execute(
            f"""SELECT model_id, direction, stage, feature_set, entry_threshold, invalidation_threshold
                FROM tournament_models
                WHERE model_id IN ({placeholders})
                ORDER BY model_id ASC""",
            model_ids,
        ).fetchall()

    if strategy == "champion":
        return db.execute(
            """SELECT model_id, direction, stage, feature_set, entry_threshold, invalidation_threshold
               FROM tournament_models
               WHERE stage = 'champion'
               ORDER BY direction ASC"""
        ).fetchall()

    if strategy == "forward_test":
        return db.execute(
            """SELECT model_id, direction, stage, feature_set, entry_threshold, invalidation_threshold
               FROM tournament_models
               WHERE stage IN ('forward_test', 'ft')
               ORDER BY model_id ASC"""
        ).fetchall()

    raise ValueError(f"Unsupported strategy: {strategy}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=["champion", "forward_test"], default="champion")
    parser.add_argument("--model-id", action="append", dest="model_ids")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--tp", type=float, default=config.TP_PCT * 100.0)
    parser.add_argument("--sl", type=float, default=config.SL_PCT * 100.0)
    parser.add_argument("--dry-run", action="store_true", help="Accepted for parity; this script never writes")
    args = parser.parse_args()

    tp_pct = args.tp / 100.0
    sl_pct = args.sl / 100.0

    db = get_db()
    end_ts = db.execute("SELECT MAX(ts) AS ts FROM candles").fetchone()["ts"]
    start_ts = end_ts - (args.days * 24 * 3600 * 1000)

    ts_list = [
        row["ts"]
        for row in db.execute(
            "SELECT DISTINCT ts FROM candles WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
            (start_ts, end_ts),
        ).fetchall()
    ]
    all_symbols = [
        row["symbol"]
        for row in db.execute(
            "SELECT symbol FROM coins WHERE is_active = 1 ORDER BY symbol ASC"
        ).fetchall()
    ]
    model_rows = _load_model_rows(db, args.strategy, args.model_ids)

    if not model_rows:
        raise RuntimeError("No models matched the selection")
    if not ts_list:
        raise RuntimeError("No candle timestamps found in the replay window")

    print(json.dumps({
        "strategy": args.strategy,
        "days": args.days,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "dry_run": True,
        "model_count": len(model_rows),
    }, sort_keys=True))

    for model_row in model_rows:
        _, stats = _replay_model(db, model_row, ts_list, all_symbols, tp_pct, sl_pct)
        print(json.dumps({
            "model_id": model_row["model_id"],
            "direction": model_row["direction"],
            "stage": model_row["stage"],
            **stats,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
