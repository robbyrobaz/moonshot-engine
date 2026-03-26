"""Moonshot v2 — Forward test arena: score coins & track per-model PnL."""

import json
import sqlite3
import time
import traceback

import joblib
import numpy as np

from config import (
    DISABLE_SOCIAL_FEATURES,
    FT_MAX_DRAWDOWN_PAUSE,
    FT_PAUSE_HOURS,
    TP_PCT,
    SL_PCT,
    TIME_STOP_BARS,
    TRAIL_ACTIVATE_PCT,
    TRAIL_DISTANCE_PCT,
    INVALIDATION_GRACE_BARS,
    TOURNAMENT_DIR,
    log,
)
from src.features.registry import FEATURE_REGISTRY
from src.scoring.thresholds import effective_entry_threshold
from src.tournament.challenger import resolve_feature_set


def _load_model(model_id: str):
    """Load a pickled model from the tournament directory."""
    path = TOURNAMENT_DIR / f"{model_id}.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


def _resolve_feature_names(feature_set_raw):
    """Support legacy preset keys and JSON-serialized feature lists."""
    return resolve_feature_set(feature_set_raw)


def _get_feature_values(db, symbol: str, ts_ms: int, feature_names: list[str]):
    """Load pre-computed features for a symbol at a timestamp.

    Returns a list of floats in the same order as feature_names, using neutral
    values from the registry for any missing features.
    """
    row = db.execute(
        """SELECT feature_names, feature_values FROM features
           WHERE symbol = ? AND ts <= ?
           ORDER BY ts DESC LIMIT 1""",
        (symbol, ts_ms),
    ).fetchone()

    if row is None:
        return None

    stored_names = json.loads(row["feature_names"])
    stored_values_raw = json.loads(row["feature_values"])
    # feature_values may be stored as a dict {name: value} or list [value, ...]
    if isinstance(stored_values_raw, dict):
        name_to_val = stored_values_raw
    else:
        name_to_val = dict(zip(stored_names, stored_values_raw))

    vec = []
    for fn in feature_names:
        reg = FEATURE_REGISTRY.get(fn)
        if DISABLE_SOCIAL_FEATURES and reg and reg.get("category") == "social":
            val = reg["neutral"]
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
        try:
            vec.append(float(val))
        except (TypeError, ValueError):
            log.warning("_get_feature_values: invalid value for feature '%s' (%s) for %s", fn, val, symbol)
            return None
    return vec


def _score_symbols(db, model, feature_names: list[str], symbols: list[str],
                   ts_ms: int) -> list[tuple[str, float]]:
    """Score all symbols with a model. Returns list of (symbol, score)."""
    results = []
    for symbol in symbols:
        vec = _get_feature_values(db, symbol, ts_ms, feature_names)
        if vec is None:
            continue
        X = np.array([vec], dtype=np.float32)
        try:
            score = float(model.predict_proba(X)[:, 1][0])
            results.append((symbol, score))
        except ValueError as e:
            log.error("_score_symbols: prediction failed for %s — vec length=%d, expected=%d features, error: %s",
                      symbol, len(vec), len(feature_names), e)
            raise
    return results


def _compute_exit_pnl(direction: str, entry_price: float,
                      exit_price: float) -> float:
    """Compute PnL % for a position."""
    if direction == "long":
        return (exit_price - entry_price) / entry_price
    else:
        return (entry_price - exit_price) / entry_price


def _check_exit_conditions(db, pos, ts_ms: int, current_price: float) -> str | None:
    """Check all exit conditions for a position.

    Returns exit_reason string or None if position stays open.
    """
    direction = pos["direction"]
    entry_price = pos["entry_price"]
    entry_ts = pos["entry_ts"]
    high_water = pos["high_water_price"] or entry_price
    trailing_active = pos["trailing_active"]

    pnl_pct = _compute_exit_pnl(direction, entry_price, current_price)

    # TP hit
    if pnl_pct >= TP_PCT:
        return "tp"

    # SL hit
    if pnl_pct <= -SL_PCT:
        return "sl"

    # Trailing stop: activate at TRAIL_ACTIVATE_PCT, stop at TRAIL_DISTANCE_PCT
    if direction == "long":
        new_hwm = max(high_water, current_price)
    else:
        new_hwm = min(high_water, current_price) if high_water > 0 else current_price

    hwm_pnl = _compute_exit_pnl(direction, entry_price, new_hwm)
    if hwm_pnl >= TRAIL_ACTIVATE_PCT:
        # Trail is active — check if price pulled back beyond trail distance
        trail_pnl = _compute_exit_pnl(direction, new_hwm, current_price)
        # trail_pnl will be negative when price pulls back from HWM
        if direction == "long":
            pullback = (new_hwm - current_price) / new_hwm
        else:
            pullback = (current_price - new_hwm) / new_hwm
        if pullback >= TRAIL_DISTANCE_PCT:
            return "trail"

    # Time stop: exceeded TIME_STOP_BARS × 4h
    bars_elapsed = (ts_ms - entry_ts) / (4 * 3600 * 1000)
    if bars_elapsed >= TIME_STOP_BARS:
        return "time"

    # Invalidation: re-score using STORED entry_features (no drift)
    # Option A from TOURNAMENT_PHILOSOPHY.md — lock features at entry
    if bars_elapsed >= INVALIDATION_GRACE_BARS:
        inv_row = db.execute(
            "SELECT invalidation_threshold, feature_set FROM tournament_models WHERE model_id = ?",
            (pos["model_id"],),
        ).fetchone()

        if inv_row and inv_row["invalidation_threshold"] is not None and pos["entry_features"]:
            try:
                # Parse stored entry features
                entry_features_data = json.loads(pos["entry_features"])
                feature_values_dict = entry_features_data.get("feature_values", {})

                # Get model's expected feature order (NOT the sorted order from entry_features!)
                model_feature_names = _resolve_feature_names(inv_row["feature_set"])

                # Build feature vector in MODEL's expected order using STORED values
                # Fill missing features with neutral values from registry (sparse storage)
                if isinstance(feature_values_dict, dict):
                    feature_vector = []
                    for fn in model_feature_names:
                        val = feature_values_dict.get(fn)
                        if val is None:
                            # Missing feature — use neutral value from registry
                            reg = FEATURE_REGISTRY.get(fn)
                            if reg and "neutral" in reg:
                                val = reg["neutral"]
                            else:
                                val = 0.0  # Fallback for features without registry entry
                        feature_vector.append(val)
                else:
                    # Legacy format: assume entry_features are in correct order
                    feature_vector = list(feature_values_dict)

                # Validate feature count matches model expectation
                if len(feature_vector) != len(model_feature_names):
                    log.warning("FT invalidation: feature count mismatch for pos %d model %s symbol %s (expected %d, got %d), skipping",
                                pos["id"], pos["model_id"], pos["symbol"], len(model_feature_names), len(feature_vector))
                else:
                    # Load model and re-score with stored features
                    model = _load_model(pos["model_id"])
                    if model is not None:
                        try:
                            X = np.array([feature_vector], dtype=np.float32)
                            current_score = float(model.predict_proba(X)[:, 1][0])

                            # Exit if re-scored position is below invalidation threshold
                            if current_score < inv_row["invalidation_threshold"]:
                                log.info("FT invalidation: pos %d score %.3f < threshold %.3f (stored features)",
                                         pos["id"], current_score, inv_row["invalidation_threshold"])
                                return "invalidation"
                        except ValueError as e:
                            log.error("FT invalidation: prediction failed for pos %d model %s symbol %s — vec length=%d, error: %s",
                                      pos["id"], pos["model_id"], pos["symbol"], len(feature_vector), e)
                            log.error("Traceback:\n%s", traceback.format_exc())
                            raise
            except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
                log.warning("FT invalidation: failed to parse entry_features for pos %d: %s", pos["id"], e)

    return None


def _get_current_price(db, symbol: str, ts_ms: int) -> float | None:
    """Get the most recent close price for a symbol at or before ts_ms."""
    row = db.execute(
        "SELECT close FROM candles WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()
    return float(row["close"]) if row else None


def _compute_ft_pnl_metrics(db, model_id: str, total_pnl: float) -> tuple[float, float]:
    """Compute time-normalized FT PnL metrics in the same units as ft_pnl."""
    model_row = db.execute(
        "SELECT created_at FROM tournament_models WHERE model_id = ?",
        (model_id,),
    ).fetchone()
    created_at_ms = model_row["created_at"] if model_row else None
    age_days = 1.0
    if created_at_ms:
        age_days = max(1.0, (time.time() * 1000 - created_at_ms) / 86_400_000)
    ft_pnl_per_day = total_pnl / age_days

    cutoff_ms = int(time.time() * 1000) - (7 * 24 * 3600 * 1000)
    last_7d_row = db.execute(
        """SELECT COALESCE(SUM(pnl_pct), 0.0) AS pnl
           FROM positions
           WHERE model_id = ?
             AND is_champion_trade = 0
             AND status = 'closed'
             AND exit_ts IS NOT NULL
             AND exit_ts >= ?""",
        (model_id, cutoff_ms),
    ).fetchone()
    ft_pnl_last_7d = float(last_7d_row["pnl"] or 0.0) if last_7d_row else 0.0
    return ft_pnl_per_day, ft_pnl_last_7d


def _update_model_ft_stats(db, model_id: str):
    """Recompute forward test stats for a model from its closed positions."""
    rows = db.execute(
        """SELECT pnl_pct FROM positions
           WHERE model_id = ? AND is_champion_trade = 0 AND status = 'closed'""",
        (model_id,),
    ).fetchall()

    trades = len(rows)
    if trades == 0:
        return

    pnls = [r["pnl_pct"] for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    total_pnl = sum(pnls)
    win_pnl = sum(p for p in pnls if p > 0)
    loss_pnl = abs(sum(p for p in pnls if p < 0))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 999.0
    ft_pnl_per_day, ft_pnl_last_7d = _compute_ft_pnl_metrics(db, model_id, total_pnl)

    # Compute max drawdown from cumulative PnL curve
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = (peak - cum) / max(peak, 0.01)
        max_dd = max(max_dd, dd)

    db.execute(
        """UPDATE tournament_models
           SET ft_trades = ?, ft_wins = ?, ft_pnl = ?, ft_pnl_per_day = ?,
               ft_pnl_last_7d = ?, ft_pf = ?, ft_max_drawdown_pct = ?
           WHERE model_id = ?""",
        (
            trades,
            wins,
            total_pnl,
            ft_pnl_per_day,
            ft_pnl_last_7d,
            pf,
            max_dd,
            model_id,
        ),
    )

    # Drawdown pause check
    if max_dd >= FT_MAX_DRAWDOWN_PAUSE:
        pause_until = int(time.time() * 1000) + (FT_PAUSE_HOURS * 3600 * 1000)
        db.execute(
            "UPDATE tournament_models SET is_paused = 1, paused_until = ? WHERE model_id = ?",
            (pause_until, model_id),
        )
        log.warning("FT model %s paused: drawdown %.1f%% >= %.1f%%",
                     model_id, max_dd * 100, FT_MAX_DRAWDOWN_PAUSE * 100)


def check_ft_exits(db, ts_ms: int):
    """Check and close FT positions that hit exit conditions."""
    open_positions = db.execute(
        """SELECT p.*, tm.feature_set, tm.model_type
           FROM positions p
           JOIN tournament_models tm ON p.model_id = tm.model_id
           WHERE p.status = 'open' AND p.is_champion_trade = 0"""
    ).fetchall()

    if not open_positions:
        return

    models_updated = set()

    for pos in open_positions:
        symbol = pos["symbol"]
        model_id = pos["model_id"]
        current_price = _get_current_price(db, symbol, ts_ms)
        if current_price is None:
            continue

        exit_reason = _check_exit_conditions(db, pos, ts_ms, current_price)

        # Update high water mark
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        hwm = pos["high_water_price"] or entry_price
        if direction == "long":
            new_hwm = max(hwm, current_price)
        else:
            new_hwm = min(hwm, current_price) if hwm > 0 else current_price

        hwm_pnl = _compute_exit_pnl(direction, entry_price, new_hwm)
        trail_now_active = 1 if hwm_pnl >= TRAIL_ACTIVATE_PCT else pos["trailing_active"]

        if exit_reason:
            pnl_pct = _compute_exit_pnl(direction, entry_price, current_price)
            db.execute(
                """UPDATE positions
                   SET status = 'closed', exit_ts = ?, exit_price = ?,
                       exit_reason = ?, pnl_pct = ?,
                       high_water_price = ?, trailing_active = ?
                   WHERE id = ?""",
                (ts_ms, current_price, exit_reason, pnl_pct,
                 new_hwm, trail_now_active, pos["id"]),
            )
            models_updated.add(model_id)
            log.info("FT exit %s %s: %s pnl=%.2f%% reason=%s",
                     model_id, symbol, direction, pnl_pct * 100, exit_reason)
        else:
            # Just update HWM / trailing status
            db.execute(
                "UPDATE positions SET high_water_price = ?, trailing_active = ? WHERE id = ?",
                (new_hwm, trail_now_active, pos["id"]),
            )

    # Recompute stats for models that had exits
    for model_id in models_updated:
        _update_model_ft_stats(db, model_id)

    db.commit()


def score_forward_test_models(db, all_symbols: list[str], ts_ms: int):
    """For each FT model: score all coins, open paper positions, check exits.

    Loads all models with stage='forward_test' that are not paused.
    Scores all symbols, opens paper positions for signals >= entry_threshold.
    Checks exits on open positions. Updates ft stats.
    """
    now_ms = ts_ms or int(time.time() * 1000)

    # Unpause models whose pause has expired
    db.execute(
        "UPDATE tournament_models SET is_paused = 0, paused_until = NULL "
        "WHERE is_paused = 1 AND paused_until < ?",
        (now_ms,),
    )
    db.commit()

    # Load active FT models
    ft_models = db.execute(
        """SELECT model_id, direction, feature_set, entry_threshold, invalidation_threshold
           FROM tournament_models
           WHERE stage = 'forward_test' AND is_paused = 0"""
    ).fetchall()

    if not ft_models:
        log.info("score_forward_test_models: no active FT models")
        return

    log.info("score_forward_test_models: scoring %d models across %d symbols",
             len(ft_models), len(all_symbols))

    for tm in ft_models:
        model_id = tm["model_id"]
        direction = tm["direction"]
        feature_names = _resolve_feature_names(tm["feature_set"])
        entry_threshold = effective_entry_threshold(
            tm["entry_threshold"],
            tm["invalidation_threshold"],
        )

        model = _load_model(model_id)
        if model is None:
            log.warning("score_forward_test_models: no pickle for %s", model_id)
            continue

        # Validate feature shape matches model expectation (detect corrupted models)
        # CatBoost doesn't set n_features_in_ properly (it's always 0), so check feature_names_ instead
        model_feature_count = None
        if hasattr(model, 'n_features_in_') and model.n_features_in_ > 0:
            model_feature_count = model.n_features_in_
        elif hasattr(model, 'feature_names_') and model.feature_names_:
            model_feature_count = len(model.feature_names_)
        
        if model_feature_count is not None and model_feature_count != len(feature_names):
            log.error(
                "FT feature shape mismatch: model_id=%s expects %d features but feature_set has %d. "
                "This model is corrupted and will be retired.",
                model_id,
                model_feature_count,
                len(feature_names),
            )
            # Retire corrupted model
            now_ms_retire = int(time.time() * 1000)
            db.execute(
                """UPDATE tournament_models
                   SET stage = 'retired', retired_at = ?, retire_reason = ?
                   WHERE model_id = ?""",
                (now_ms_retire, f"feature_shape_mismatch: model expects {model_feature_count}, DB has {len(feature_names)}", model_id),
            )
            db.commit()
            log.info("FT retired corrupted model %s", model_id)
            continue

        try:
            # Score all symbols
            scores = _score_symbols(db, model, feature_names, all_symbols, now_ms)
            feature_map = {
                symbol: _get_feature_values(db, symbol, now_ms, feature_names)
                for symbol, _ in scores
            }

            # Find signals above threshold
            signals = [(sym, sc) for sym, sc in scores if sc >= entry_threshold]

            # Check which symbols already have open positions for this model
            open_syms = set()
            open_rows = db.execute(
                "SELECT symbol FROM positions WHERE model_id = ? AND status = 'open'",
                (model_id,),
            ).fetchall()
            for r in open_rows:
                open_syms.add(r["symbol"])

            # Open new paper positions
            for symbol, score in signals:
                if symbol in open_syms:
                    continue

                price = _get_current_price(db, symbol, now_ms)
                if price is None:
                    continue

                try:
                    db.execute(
                        """INSERT INTO positions
                           (symbol, direction, model_id, is_champion_trade,
                            entry_ts, entry_price, entry_ml_score, entry_features,
                            status, high_water_price)
                           VALUES (?, ?, ?, 0, ?, ?, ?, ?, 'open', ?)""",
                        (
                            symbol,
                            direction,
                            model_id,
                            now_ms,
                            price,
                            score,
                            json.dumps({
                                "feature_version": None,
                                "feature_names": feature_names,
                                "feature_values": dict(
                                    zip(feature_names, feature_map.get(symbol) or [])
                                ),
                            }),
                            price,
                        ),
                    )
                except sqlite3.IntegrityError:
                    log.debug("FT open skipped: duplicate open for %s %s", direction, symbol)
                    continue
                log.info("FT open %s %s %s score=%.3f price=%.6f",
                         model_id, direction, symbol, score, price)
        except Exception as e:
            log.error("score_forward_test_models: error processing model %s (feature_set=%s, %d features): %s",
                      model_id, tm["feature_set"], len(feature_names), e)
            log.error("Traceback:\n%s", traceback.format_exc())
            raise

    db.commit()

    # Check exits on all open FT positions
    check_ft_exits(db, now_ms)
