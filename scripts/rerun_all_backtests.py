#!/usr/bin/env python3
"""Full tournament reset: re-run all backtests, 14-day FT simulation, re-crown.

Steps:
1. Re-run BT for all candidate models (trains fresh 3-fold walk-forward).
   Gates (from config): MIN_BT_PF=1.0, MIN_BT_PRECISION=0.20, MIN_BT_TRADES=50
   Gate applies to Fold 3 ONLY (most recent 10% of data).
   Aggregate bt_pf stored in DB for all models regardless of pass/fail.
2. For each model that passes BT: save new pkl, run 14-day FT simulation.
3. Update ft_* in DB.
4. Re-crown champion based on ft_pnl.

Scope flags:
  --skip-retired       Only process champion + forward_test models (~27 models, fast)
  --all-retired        Also process retired models with bt_pf < 1.0 (adds ~700 models, very slow)
  Default scope:       champion + FT + retired models with stored bt_pf >= 1.0 (~71 models)

Usage:
  python scripts/rerun_all_backtests.py                     # recommended (71 models)
  python scripts/rerun_all_backtests.py --skip-retired      # fastest (27 models)
  python scripts/rerun_all_backtests.py --all-retired       # exhaustive (788 models, hours)
  python scripts/rerun_all_backtests.py --dry-run           # preview only
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import joblib
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)

from config import (
    BOOTSTRAP_PF_LOWER_BOUND,
    INVALIDATION_GRACE_BARS,
    MIN_BT_PF,
    MIN_BT_PRECISION,
    MIN_BT_TRADES,
    SL_PCT,
    TIME_STOP_BARS,
    TP_PCT,
    TRAIL_ACTIVATE_PCT,
    TRAIL_DISTANCE_PCT,
    TOURNAMENT_DIR,
    log,
)
from src.db.schema import get_db
from src.scoring.thresholds import effective_entry_threshold
from src.tournament.backtest import backtest_challenger
from src.tournament.champion import crown_champion_if_ready
from src.tournament.challenger import FEATURE_SUBSETS
from src.tournament.forward_test import _compute_exit_pnl, _get_feature_values


# ---------------------------------------------------------------------------
# 14-day FT replay (inline — avoids loading stale pickles)
# ---------------------------------------------------------------------------

def _check_exit(position, ts_ms, current_price, current_score, inv_threshold):
    direction = position["direction"]
    entry_price = position["entry_price"]
    hwm = position["high_water_price"] or entry_price

    pnl = _compute_exit_pnl(direction, entry_price, current_price)
    if pnl >= TP_PCT:
        return "tp"
    if pnl <= -SL_PCT:
        return "sl"

    if direction == "long":
        new_hwm = max(hwm, current_price)
        pullback = (new_hwm - current_price) / new_hwm if new_hwm else 0.0
    else:
        new_hwm = min(hwm, current_price) if hwm > 0 else current_price
        pullback = (current_price - new_hwm) / new_hwm if new_hwm else 0.0

    hwm_pnl = _compute_exit_pnl(direction, entry_price, new_hwm)
    if hwm_pnl >= TRAIL_ACTIVATE_PCT and pullback >= TRAIL_DISTANCE_PCT:
        return "trail"

    bars_elapsed = (ts_ms - position["entry_ts"]) / (4 * 3600 * 1000)
    if bars_elapsed >= TIME_STOP_BARS:
        return "time"

    if (
        inv_threshold is not None
        and position["entry_ml_score"] is not None
        and bars_elapsed >= INVALIDATION_GRACE_BARS
        and position["entry_ml_score"] < inv_threshold
    ):
        return "invalidation"

    return None


def _replay_14d(db, model_id, model_obj, feature_names, direction,
                entry_threshold, inv_threshold, ts_list, all_symbols):
    """Simulate trades over ts_list using the freshly-trained model_obj."""
    entry_threshold = effective_entry_threshold(entry_threshold, inv_threshold)
    open_positions = []
    closed_positions = []

    for ts_ms in ts_list:
        price_rows = db.execute(
            "SELECT symbol, close FROM candles WHERE ts = ?", (ts_ms,)
        ).fetchall()
        price_map = {r["symbol"]: float(r["close"]) for r in price_rows}

        open_symbols = {p["symbol"] for p in open_positions}
        batch_symbols, batch_vecs = [], []
        for sym in all_symbols:
            if sym in open_symbols:
                continue
            vec = _get_feature_values(db, sym, ts_ms, feature_names)
            if vec is None or sym not in price_map:
                continue
            batch_symbols.append(sym)
            batch_vecs.append(vec)

        score_map = {}
        if batch_vecs:
            scores = model_obj.predict_proba(
                np.array(batch_vecs, dtype=np.float32)
            )[:, 1]
            for sym, score in zip(batch_symbols, scores):
                score = float(score)
                score_map[sym] = score
                if score >= entry_threshold and sym in price_map:
                    open_positions.append({
                        "symbol": sym,
                        "direction": direction,
                        "model_id": model_id,
                        "entry_ts": ts_ms,
                        "entry_price": price_map[sym],
                        "entry_ml_score": score,
                        "high_water_price": price_map[sym],
                        "trailing_active": 0,
                    })

        still_open = []
        for pos in open_positions:
            cp = price_map.get(pos["symbol"])
            if cp is None:
                still_open.append(pos)
                continue

            d = pos["direction"]
            hwm = pos["high_water_price"] or pos["entry_price"]
            pos["high_water_price"] = max(hwm, cp) if d == "long" else min(hwm, cp)

            cs = score_map.get(pos["symbol"])
            reason = _check_exit(pos, ts_ms, cp, cs, inv_threshold)
            if reason:
                pnl = _compute_exit_pnl(d, pos["entry_price"], cp)
                closed_positions.append({
                    **pos,
                    "exit_ts": ts_ms,
                    "exit_price": cp,
                    "exit_reason": reason,
                    "pnl_pct": pnl,
                })
            else:
                still_open.append(pos)
        open_positions = still_open

    # Force-close remaining positions at final bar
    if ts_list and open_positions:
        last_ts = ts_list[-1]
        last_prices = {
            r["symbol"]: float(r["close"])
            for r in db.execute(
                "SELECT symbol, close FROM candles WHERE ts = ?", (last_ts,)
            ).fetchall()
        }
        for pos in open_positions:
            cp = last_prices.get(pos["symbol"])
            if cp:
                pnl = _compute_exit_pnl(pos["direction"], pos["entry_price"], cp)
                closed_positions.append({
                    **pos,
                    "exit_ts": last_ts,
                    "exit_price": cp,
                    "exit_reason": "rerun_end",
                    "pnl_pct": pnl,
                })

    if not closed_positions:
        return {"ft_trades": 0, "ft_wins": 0, "ft_pnl": 0.0,
                "ft_pf": 0.0, "ft_max_drawdown_pct": 0.0}

    pnls = [p["pnl_pct"] for p in closed_positions]
    wins = sum(1 for p in pnls if p > 0)
    win_sum = sum(p for p in pnls if p > 0)
    loss_sum = abs(sum(p for p in pnls if p < 0))
    pf = win_sum / loss_sum if loss_sum > 0 else 999.0

    cum, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = (peak - cum) / max(peak, 0.01)
        max_dd = max(max_dd, dd)

    return {
        "ft_trades": len(pnls),
        "ft_wins": wins,
        "ft_pnl": sum(pnls),
        "ft_pf": pf,
        "ft_max_drawdown_pct": max_dd,
    }


# ---------------------------------------------------------------------------
# Feature name resolution (handles named preset and JSON list)
# ---------------------------------------------------------------------------

def _resolve_feature_names(feature_set_raw):
    if not feature_set_raw:
        return FEATURE_SUBSETS["core_only"]
    try:
        parsed = json.loads(feature_set_raw)
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        return parsed
    return FEATURE_SUBSETS.get(feature_set_raw, FEATURE_SUBSETS["core_only"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=14,
                        help="FT simulation window in days (default: 14)")
    parser.add_argument("--skip-retired", action="store_true",
                        help="Only process champion + forward_test models")
    parser.add_argument("--all-retired", action="store_true",
                        help="Also process retired models with bt_pf < 1.0 (very slow)")
    parser.add_argument("--direction", choices=["long", "short"],
                        help="Limit to one direction only")
    parser.add_argument("--model-id", action="append", dest="model_ids",
                        help="Only process specific model IDs (can repeat)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would run, no DB writes")
    args = parser.parse_args()

    db = get_db()
    now_ms = int(time.time() * 1000)

    # ---- Print current gates ----
    print(f"[CONFIG] Gates: MIN_BT_PF={MIN_BT_PF} MIN_BT_PRECISION={MIN_BT_PRECISION} "
          f"MIN_BT_TRADES={MIN_BT_TRADES} BOOTSTRAP_LB={BOOTSTRAP_PF_LOWER_BOUND}")

    # ---- Demote current champion(s) to forward_test ----
    champs = db.execute(
        "SELECT model_id, direction, bt_pf, ft_pnl, ft_trades FROM tournament_models "
        "WHERE stage = 'champion'"
    ).fetchall()
    for champ in champs:
        print(f"[INIT] Demoting champion {champ['model_id']} ({champ['direction']}) "
              f"bt_pf={champ['bt_pf']:.3f} ft_pnl={champ['ft_pnl']:.3f} "
              f"ft_trades={champ['ft_trades']} → forward_test")
        if not args.dry_run:
            db.execute(
                "UPDATE tournament_models SET stage='forward_test', "
                "promoted_to_champion_at=NULL WHERE model_id=?",
                (champ["model_id"],),
            )
    if not args.dry_run:
        db.commit()

    # ---- Build 14-day FT timestamp list ----
    end_ts = db.execute("SELECT MAX(ts) AS ts FROM candles").fetchone()["ts"]
    start_ts = end_ts - (args.days * 24 * 3600 * 1000)
    ts_list = [r["ts"] for r in db.execute(
        "SELECT DISTINCT ts FROM candles WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
        (start_ts, end_ts),
    ).fetchall()]
    all_symbols = [r["symbol"] for r in db.execute(
        "SELECT symbol FROM coins WHERE is_active = 1 ORDER BY symbol"
    ).fetchall()]
    print(f"[INIT] FT window: {args.days} days, {len(ts_list)} bars, {len(all_symbols)} symbols")

    # ---- Select models to process ----
    if args.model_ids:
        placeholders = ",".join("?" for _ in args.model_ids)
        rows = db.execute(
            f"SELECT * FROM tournament_models WHERE model_id IN ({placeholders})",
            args.model_ids,
        ).fetchall()
    elif args.skip_retired:
        q = "SELECT * FROM tournament_models WHERE stage IN ('champion','forward_test','backtest')"
        params_q = []
        if args.direction:
            q += " AND direction = ?"
            params_q.append(args.direction)
        rows = db.execute(q, params_q).fetchall()
    elif args.all_retired:
        q = "SELECT * FROM tournament_models"
        params_q = []
        if args.direction:
            q += " WHERE direction = ?"
            params_q.append(args.direction)
        rows = db.execute(q, params_q).fetchall()
    else:
        # Default: champion + FT + retired with stored bt_pf >= 1.0
        q = """SELECT * FROM tournament_models
               WHERE stage IN ('champion','forward_test','backtest')
                  OR (stage = 'retired' AND bt_pf >= 1.0)"""
        params_q = []
        if args.direction:
            q += " AND direction = ?"
            params_q.append(args.direction)
        rows = db.execute(q, params_q).fetchall()

    # Sort: non-retired first (champion, FT), then retired by bt_pf desc
    stage_order = {"champion": 0, "forward_test": 1, "backtest": 2, "retired": 3}
    rows = sorted(rows, key=lambda r: (stage_order.get(r["stage"], 9), -(r["bt_pf"] or 0)))

    total = len(rows)
    print(f"[INIT] Will process {total} models")
    if args.dry_run:
        for r in rows:
            print(f"  {r['model_id']} stage={r['stage']:12} dir={r['direction']:5} "
                  f"bt_pf={r['bt_pf'] or 0:.3f}")
        print("[DRY-RUN] No changes made.")
        return

    # ---- Process each model ----
    passed_bt = 0
    failed_bt = 0
    ft_done = 0
    t_start = time.time()

    for idx, row in enumerate(rows):
        model_id = row["model_id"]
        direction = row["direction"]
        elapsed = time.time() - t_start
        eta = (elapsed / max(idx, 1)) * (total - idx) if idx > 0 else 0
        print(f"\n[{idx+1}/{total}] {model_id} ({direction}, was={row['stage']}) "
              f"stored_bt_pf={row['bt_pf'] or 0:.3f} | "
              f"elapsed={elapsed:.0f}s eta={eta:.0f}s")

        params = json.loads(row["params"])
        params["model_id"] = model_id

        # ---- Re-run backtest (trains fresh 3-fold model) ----
        try:
            bt_result = backtest_challenger(db, params)
        except Exception as e:
            print(f"  BT ERROR: {e}")
            db.execute(
                "UPDATE tournament_models SET stage='retired', retired_at=?, "
                "retire_reason=? WHERE model_id=?",
                (now_ms, f"rerun_bt_error: {e}", model_id),
            )
            db.commit()
            failed_bt += 1
            continue

        # Always update BT metrics (even on failure — real aggregate gets stored)
        db.execute(
            """UPDATE tournament_models
               SET bt_trades=?, bt_pf=?, bt_precision=?, bt_pnl=?, bt_ci_lower=?
               WHERE model_id=?""",
            (bt_result["bt_trades"], bt_result["bt_pf"], bt_result["bt_precision"],
             bt_result["bt_pnl"], bt_result["bt_ci_lower"], model_id),
        )

        if not bt_result["passed"]:
            print(f"  BT FAILED: agg_pf={bt_result['bt_pf']:.3f} "
                  f"prec={bt_result['bt_precision']:.3f} trades={bt_result['bt_trades']}")
            db.execute(
                "UPDATE tournament_models SET stage='retired', retired_at=?, "
                "retire_reason='rerun_backtest_failed' WHERE model_id=?",
                (now_ms, model_id),
            )
            db.commit()
            failed_bt += 1
            continue

        print(f"  BT PASS: agg_pf={bt_result['bt_pf']:.3f} "
              f"prec={bt_result['bt_precision']:.3f} trades={bt_result['bt_trades']}")
        passed_bt += 1

        # ---- Save new model pickle ----
        TOURNAMENT_DIR.mkdir(parents=True, exist_ok=True)
        model_obj = bt_result["model_obj"]
        pkl_path = TOURNAMENT_DIR / f"{model_id}.pkl"
        joblib.dump(model_obj, pkl_path)

        # ---- Promote to forward_test ----
        db.execute(
            """UPDATE tournament_models
               SET stage='forward_test',
                   entry_threshold=?, invalidation_threshold=?,
                   promoted_to_ft_at=?,
                   retired_at=NULL, retire_reason=NULL,
                   is_paused=0, paused_until=NULL
               WHERE model_id=?""",
            (bt_result["entry_threshold"], bt_result["invalidation_threshold"],
             now_ms, model_id),
        )
        db.commit()

        # ---- Run 14-day FT simulation ----
        feature_set_raw = row["feature_set"] or params.get("feature_set", "core_only")
        feature_names = _resolve_feature_names(feature_set_raw)

        ft_stats = _replay_14d(
            db, model_id, model_obj, feature_names, direction,
            bt_result["entry_threshold"], bt_result["invalidation_threshold"],
            ts_list, all_symbols,
        )
        print(f"  FT 14d: trades={ft_stats['ft_trades']} "
              f"pf={ft_stats['ft_pf']:.3f} pnl={ft_stats['ft_pnl']:.4f}")

        db.execute(
            """UPDATE tournament_models
               SET ft_trades=?, ft_wins=?, ft_pnl=?, ft_pf=?, ft_max_drawdown_pct=?
               WHERE model_id=?""",
            (ft_stats["ft_trades"], ft_stats["ft_wins"], ft_stats["ft_pnl"],
             ft_stats["ft_pf"], ft_stats["ft_max_drawdown_pct"], model_id),
        )
        db.commit()
        ft_done += 1

    # ---- Summary ----
    elapsed_total = time.time() - t_start
    print(f"\n[DONE] Processed {total} models in {elapsed_total:.0f}s")
    print(f"  BT passed: {passed_bt}  BT failed: {failed_bt}  FT sims: {ft_done}")

    # ---- Re-crown champion ----
    print("\n[CROWN] Running champion selection...")
    crown_champion_if_ready(db)

    # ---- Final leaderboard ----
    print("\n[LEADERBOARD] Top 10 FT models by ft_pnl:")
    for r in db.execute(
        """SELECT model_id, direction, stage, bt_pf, bt_precision, bt_trades,
                  ft_trades, ft_pf, ft_pnl, ft_wins
           FROM tournament_models
           WHERE stage IN ('forward_test','champion')
             AND ft_trades >= 5
           ORDER BY ft_pnl DESC
           LIMIT 10"""
    ).fetchall():
        print(f"  {r['model_id']} {r['stage']:12} {r['direction']:5} "
              f"bt_pf={r['bt_pf']:.3f} | "
              f"ft: {r['ft_trades']}t pf={r['ft_pf']:.2f} pnl={r['ft_pnl']:.4f}")

    print("\n[DONE] Complete. Restart moonshot-v2.service to pick up new champion.")


if __name__ == "__main__":
    main()
