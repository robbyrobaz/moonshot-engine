"""Moonshot v2 — Walk-forward backtest with 3 expanding folds."""

import json
import time

import joblib
import numpy as np

from config import (
    BOOTSTRAP_PF_LOWER_BOUND,
    BOOTSTRAP_PF_LOWER_BOUND_LONG,
    BOOTSTRAP_RESAMPLES,
    DISABLE_SOCIAL_FEATURES,
    MIN_BT_PF,
    MIN_BT_PF_LONG,
    MIN_BT_PRECISION,
    MIN_BT_PRECISION_LONG,
    MIN_BT_TRADES,
    PNL_WEIGHT_SL,
    PNL_WEIGHT_TP,
    TP_PCT,
    SL_PCT,
    TOURNAMENT_DIR,
    log,
)
from src.features.registry import FEATURE_REGISTRY
from src.tournament.challenger import resolve_feature_set


# ---------------------------------------------------------------------------
# GPU Detection
# ---------------------------------------------------------------------------

def _detect_xgb_gpu_device():
    """Detect GPU availability for XGBoost and return device string."""
    try:
        from xgboost import XGBClassifier
        m = XGBClassifier(device='cuda', n_estimators=1)
        m.fit(np.array([[1, 2], [3, 4]]), np.array([0, 1]))
        return 'cuda'
    except Exception:
        return 'cpu'

XGB_DEVICE = _detect_xgb_gpu_device()
LABEL_LOAD_BATCH_SIZE = 100_000


def _feature_value(name_to_val: dict, feature_name: str):
    reg = FEATURE_REGISTRY.get(feature_name)
    if DISABLE_SOCIAL_FEATURES and reg and reg.get("category") == "social":
        return reg["neutral"]
    return name_to_val.get(feature_name)


def _get_rss_mb() -> float:
    """Return current process RSS in MiB."""
    with open("/proc/self/status", encoding="utf-8") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
                return rss_kb / 1024.0
    return 0.0


def _build_model(params: dict):
    """Instantiate an untrained model from params."""
    mt = params["model_type"]
    neg_w = params["neg_class_weight"]
    depth = params["max_depth"]
    lr = params["learning_rate"]
    n_est = params["n_estimators"]

    if mt == "lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=n_est,
            learning_rate=lr,
            num_leaves=params.get("num_leaves", 31),
            max_depth=depth,
            class_weight={0: 1, 1: neg_w},
            device="gpu",
            verbosity=-1,
            n_jobs=-1,
        )
    elif mt == "xgboost":
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=n_est,
            learning_rate=lr,
            max_depth=depth,
            scale_pos_weight=neg_w,
            tree_method="hist",
            device=XGB_DEVICE,
            use_label_encoder=False,
            eval_metric="logloss",
            verbosity=0,
            n_jobs=-1,
        )
    elif mt == "catboost":
        from catboost import CatBoostClassifier
        return CatBoostClassifier(
            iterations=n_est,
            learning_rate=lr,
            depth=min(depth, 10),
            class_weights={0: 1, 1: neg_w},
            task_type="GPU",
            devices="0",
            verbose=0,
        )
    else:
        raise ValueError(f"Unknown model_type: {mt}")


def _compute_sample_weights(labels: np.ndarray) -> np.ndarray:
    """PnL-weighted samples: TP weight=1.0, SL weight=PNL_WEIGHT_SL."""
    weights = np.where(labels == 1, PNL_WEIGHT_TP, PNL_WEIGHT_SL)
    return weights


def _compute_pf(pnl_list: list[float]) -> float:
    """Profit factor: sum(wins) / abs(sum(losses)). No losses -> 999.0."""
    wins = sum(p for p in pnl_list if p > 0)
    losses = abs(sum(p for p in pnl_list if p < 0))
    if losses == 0:
        return 999.0
    return wins / losses


def bootstrap_pf(trades_pnl: list[float], n_resamples: int = None) -> tuple[float, float]:
    """Bootstrap confidence interval on profit factor.

    Returns (pf_point_estimate, pf_ci_lower_bound_2.5pct).
    """
    if n_resamples is None:
        n_resamples = BOOTSTRAP_RESAMPLES

    if len(trades_pnl) < 2:
        return (_compute_pf(trades_pnl), 0.0)

    arr = np.array(trades_pnl)
    pf_point = _compute_pf(trades_pnl)

    rng = np.random.default_rng()
    pf_samples = []
    for _ in range(n_resamples):
        sample = rng.choice(arr, size=len(arr), replace=True)
        pf_samples.append(_compute_pf(sample.tolist()))

    ci_lower = float(np.percentile(pf_samples, 2.5))
    return (pf_point, ci_lower)


def _load_labeled_data(db, direction: str, feature_names: list[str]):
    """Load all labeled data joined with features for a given direction.

    Returns (X: np.ndarray, y: np.ndarray, pnl_per_row: np.ndarray, timestamps: list[int]).
    Each row corresponds to a (symbol, ts) with both features and a label.
    """
    cursor = db.execute(
        """SELECT f.symbol, f.ts, f.feature_names, f.feature_values,
                  l.label
           FROM features f
           JOIN labels l ON f.symbol = l.symbol AND f.ts = l.ts
           WHERE l.direction = ? AND l.tp_pct = ? AND l.sl_pct = ?
           ORDER BY f.ts ASC""",
        (direction, TP_PCT, SL_PCT),
    )

    X_rows = []
    y_list = []
    ts_list = []
    total_rows = 0
    loaded_rows = 0
    skipped_rows = 0

    while True:
        rows = cursor.fetchmany(LABEL_LOAD_BATCH_SIZE)
        if not rows:
            break

        total_rows += len(rows)

        for row in rows:
            stored_names = json.loads(row["feature_names"])
            stored_values_raw = json.loads(row["feature_values"])
            # feature_values may be stored as a dict {name: value} or list [value, ...]
            if isinstance(stored_values_raw, dict):
                name_to_val = stored_values_raw
            else:
                name_to_val = dict(zip(stored_names, stored_values_raw))

            # Extract only the features this model needs, in order
            feat_vec = []
            skip = False
            for fn in feature_names:
                val = _feature_value(name_to_val, fn)
                if val is None:
                    skip = True
                    break
                feat_vec.append(float(val))

            if skip:
                skipped_rows += 1
                continue

            X_rows.append(feat_vec)
            y_list.append(int(row["label"]))
            ts_list.append(int(row["ts"]))
            loaded_rows += 1

        log.info(
            "label load progress: direction=%s rows_seen=%d rows_loaded=%d rows_skipped=%d rss_mb=%.1f",
            direction,
            total_rows,
            loaded_rows,
            skipped_rows,
            _get_rss_mb(),
        )

    if not X_rows:
        return None, None, None, []

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)
    # PnL per row: +TP_PCT for label=1, -SL_PCT for label=0
    pnl = np.where(y == 1, TP_PCT, -SL_PCT)
    return X, y, pnl, ts_list


def _evaluate_fold(model, X_test, y_test, pnl_test, threshold: float) -> dict | None:
    """Score a fold. Returns metrics dict or None if too few trades."""
    proba = model.predict_proba(X_test)[:, 1]
    mask = proba >= threshold
    trades = int(mask.sum())

    if trades == 0:
        return {"trades": 0, "precision": 0.0, "pf": 0.0, "pnl": 0.0,
                "ci_lower": 0.0, "trades_pnl": []}

    pred_labels = y_test[mask]
    pred_pnl = pnl_test[mask]

    tp = int((pred_labels == 1).sum())
    precision = tp / trades if trades > 0 else 0.0
    pf = _compute_pf(pred_pnl.tolist())
    total_pnl = float(pred_pnl.sum())
    _, ci_lower = bootstrap_pf(pred_pnl.tolist())

    return {
        "trades": trades,
        "precision": precision,
        "pf": pf,
        "pnl": total_pnl,
        "ci_lower": ci_lower,
        "trades_pnl": pred_pnl.tolist(),
        "scores": proba,
        "y_test": y_test,
    }


def backtest_challenger(db, model_params: dict) -> dict:
    """Run 3-fold expanding walk-forward backtest.

    Fold 1: Train on oldest 60%, test on next 20%
    Fold 2: Train on oldest 80%, test on next 10%
    Fold 3: Train on oldest 90%, test on final 10%

    Gate logic: Fold 3 (most recent 10%) MUST pass all gates.
    Folds 1-2 are soft (crypto regimes shift — older data can underperform).
        bt_pf >= MIN_BT_PF (from config, default 1.3)
        bt_precision >= MIN_BT_PRECISION (from config, default 0.25)
        bt_trades >= MIN_BT_TRADES (from config, default 50)
        bootstrap CI lower bound >= BOOTSTRAP_PF_LOWER_BOUND (from config, default 0.8)
    Failed models still get real aggregate PF saved to DB for dashboard visibility.

    Returns dict with: passed, bt_trades, bt_pf, bt_precision, bt_pnl,
                        bt_ci_lower, model_obj, entry_threshold, invalidation_threshold
    """
    params = model_params if isinstance(model_params, dict) else json.loads(model_params)
    direction = params["direction"]
    feature_set_key = params.get("feature_set", "core_only")
    feature_names = resolve_feature_set(feature_set_key)
    threshold = params["confidence_threshold"]

    result = {
        "passed": False,
        "bt_trades": 0,
        "bt_pf": 0.0,
        "bt_precision": 0.0,
        "bt_pnl": 0.0,
        "bt_ci_lower": 0.0,
        "model_obj": None,
        "entry_threshold": threshold,
        "invalidation_threshold": 0.0,
    }

    rss_before_load_mb = _get_rss_mb()
    log.info(
        "backtest label load start: model_id=%s direction=%s feature_set=%s feature_count=%d rss_mb=%.1f",
        params.get("model_id", "unknown"),
        direction,
        feature_set_key,
        len(feature_names),
        rss_before_load_mb,
    )
    X, y, pnl, ts_list = _load_labeled_data(db, direction, feature_names)
    rss_after_load_mb = _get_rss_mb()
    log.info(
        "backtest label load done: model_id=%s direction=%s rows=%d rss_mb=%.1f delta_mb=%.1f",
        params.get("model_id", "unknown"),
        direction,
        0 if X is None else len(X),
        rss_after_load_mb,
        rss_after_load_mb - rss_before_load_mb,
    )
    if X is None or len(X) < 100:
        log.warning("backtest_challenger: insufficient data (%s rows)",
                     0 if X is None else len(X))
        return result

    n = len(X)
    # Fold boundaries (expanding window)
    folds = [
        (0, int(n * 0.6), int(n * 0.6), int(n * 0.8)),   # train 0-60%, test 60-80%
        (0, int(n * 0.8), int(n * 0.8), int(n * 0.9)),   # train 0-80%, test 80-90%
        (0, int(n * 0.9), int(n * 0.9), n),               # train 0-90%, test 90-100%
    ]

    all_passed = True
    total_trades = 0
    total_pnl = 0.0
    all_trades_pnl = []
    fold_metrics = []
    last_model = None
    last_val_scores = None
    last_val_y = None

    for fold_idx, (tr_start, tr_end, te_start, te_end) in enumerate(folds):
        X_train, y_train = X[tr_start:tr_end], y[tr_start:tr_end]
        X_test, y_test = X[te_start:te_end], y[te_start:te_end]
        pnl_test = pnl[te_start:te_end]

        if len(X_test) == 0 or len(X_train) < 50:
            all_passed = False
            break

        sample_weights = _compute_sample_weights(y_train)

        model = _build_model(params)
        model.fit(X_train, y_train, sample_weight=sample_weights)

        metrics = _evaluate_fold(model, X_test, y_test, pnl_test, threshold)
        fold_metrics.append(metrics)

        log.info(
            "backtest fold %d: trades=%d pf=%.2f prec=%.2f ci=%.2f",
            fold_idx + 1, metrics["trades"], metrics["pf"],
            metrics["precision"], metrics["ci_lower"],
        )

        # Track per-fold gate pass/fail (fold 3 = most recent data is the hard gate)
        # Use direction-specific gates for PF, precision, and bootstrap CI
        direction = params.get("direction", "short")
        min_pf = MIN_BT_PF_LONG if direction == "long" else MIN_BT_PF
        min_prec = MIN_BT_PRECISION_LONG if direction == "long" else MIN_BT_PRECISION
        min_ci = BOOTSTRAP_PF_LOWER_BOUND_LONG if direction == "long" else BOOTSTRAP_PF_LOWER_BOUND
        
        fold_gate_ok = (
            metrics["trades"] >= MIN_BT_TRADES
            and metrics["pf"] >= min_pf
            and metrics["precision"] >= min_prec
            and metrics["ci_lower"] >= min_ci
        )
        if fold_idx == 2 and not fold_gate_ok:
            # Fold 3 (most recent data) must pass — hard requirement
            all_passed = False
        # Folds 1-2: soft gate — track but don't fail immediately (crypto regimes shift)

        total_trades += metrics["trades"]
        total_pnl += metrics["pnl"]
        all_trades_pnl.extend(metrics["trades_pnl"])

        # Keep fold 3 model + scores for thresholds
        if fold_idx == 2:
            last_model = model
            last_val_scores = metrics.get("scores")
            last_val_y = metrics.get("y_test")

    # Always compute aggregate metrics so failed models get real PF saved to DB
    agg_pf, agg_ci = bootstrap_pf(all_trades_pnl) if all_trades_pnl else (0.0, 0.0)
    agg_precision = (sum(m["precision"] * m["trades"] for m in fold_metrics)
                     / max(total_trades, 1)) if fold_metrics else 0.0

    # Save aggregate metrics into result (used for DB even on failure)
    result.update({
        "bt_trades": total_trades,
        "bt_pf": agg_pf,
        "bt_precision": agg_precision,
        "bt_pnl": total_pnl,
        "bt_ci_lower": agg_ci,
    })

    # Fold 3 (most recent data) is the hard gate — if it failed, return here
    if not all_passed or not fold_metrics:
        return result

    # Compute invalidation threshold from fold 3 validation scores
    invalidation_threshold = 0.0
    if last_val_scores is not None and last_val_y is not None:
        # 25th percentile of scores on true positive validation examples
        tp_mask = (last_val_y == 1) & (last_val_scores >= threshold)
        tp_scores = last_val_scores[tp_mask]
        if len(tp_scores) > 0:
            invalidation_threshold = float(np.percentile(tp_scores, 25))

    result.update({
        "passed": True,
        "model_obj": last_model,
        "entry_threshold": threshold,
        "invalidation_threshold": invalidation_threshold,
    })
    return result


def backtest_new_challengers(db, max_batch=None):
    """Find all models with stage='backtest', run backtest, promote or retire.
    
    Args:
        db: Database connection
        max_batch: Maximum models to process per cycle (None = use config.BACKTEST_BATCH_SIZE)
    """
    if max_batch is None:
        from config import BACKTEST_BATCH_SIZE
        max_batch = BACKTEST_BATCH_SIZE
    rows = db.execute(
        "SELECT model_id, params FROM tournament_models WHERE stage = 'backtest' LIMIT ?",
        (max_batch,)
    ).fetchall()

    if not rows:
        log.info("backtest_new_challengers: no pending challengers")
        return

    total_pending = db.execute(
        "SELECT COUNT(*) as cnt FROM tournament_models WHERE stage = 'backtest'"
    ).fetchone()["cnt"]
    log.info("backtest_new_challengers: %d challengers to evaluate (%d total pending)", 
             len(rows), total_pending)
    now_ms = int(time.time() * 1000)

    for row in rows:
        model_id = row["model_id"]
        params = json.loads(row["params"])
        params["model_id"] = model_id

        try:
            result = backtest_challenger(db, params)
        except Exception as e:
            log.error("backtest_challenger %s failed: %s", model_id, e)
            db.execute(
                """UPDATE tournament_models
                   SET stage = 'retired', retired_at = ?, retire_reason = ?
                   WHERE model_id = ?""",
                (now_ms, f"backtest_error: {e}", model_id),
            )
            db.commit()
            continue

        if result["passed"]:
            # Save model to disk
            TOURNAMENT_DIR.mkdir(parents=True, exist_ok=True)
            model_path = TOURNAMENT_DIR / f"{model_id}.pkl"
            joblib.dump(result["model_obj"], model_path)

            db.execute(
                """UPDATE tournament_models
                   SET stage = 'forward_test',
                       bt_trades = ?, bt_pf = ?, bt_precision = ?,
                       bt_pnl = ?, bt_ci_lower = ?,
                       entry_threshold = ?, invalidation_threshold = ?,
                       promoted_to_ft_at = ?
                   WHERE model_id = ?""",
                (
                    result["bt_trades"], result["bt_pf"], result["bt_precision"],
                    result["bt_pnl"], result["bt_ci_lower"],
                    result["entry_threshold"], result["invalidation_threshold"],
                    now_ms, model_id,
                ),
            )
            log.info(
                "backtest PASSED %s: trades=%d pf=%.2f prec=%.2f → forward_test",
                model_id, result["bt_trades"], result["bt_pf"], result["bt_precision"],
            )
        else:
            db.execute(
                """UPDATE tournament_models
                   SET stage = 'retired', retired_at = ?, retire_reason = 'backtest_failed',
                       bt_trades = ?, bt_pf = ?, bt_precision = ?, bt_pnl = ?, bt_ci_lower = ?
                   WHERE model_id = ?""",
                (
                    now_ms,
                    result.get("bt_trades"), result.get("bt_pf"),
                    result.get("bt_precision"), result.get("bt_pnl"),
                    result.get("bt_ci_lower"),
                    model_id,
                ),
            )
            log.info("backtest FAILED %s → retired", model_id)

        db.commit()

    log.info("backtest_new_challengers: complete")
