"""Moonshot v2 — Champion selection and demotion logic.

2026-03-07: MAJOR POLICY CHANGE
- FT is FREE data collection — never demote early
- Only demote if: PF < 0.5 AND trades >= 500 (catastrophic AND significant)
- Rank by: ft_pnl (primary), ft_pf (secondary), ft_trades (tiebreaker)
- Let models run! Data collection IS the goal.
"""

import time

import joblib

from config import (
    BOOTSTRAP_PF_LOWER_BOUND,
    CHAMPION_BEAT_MARGIN,
    CHAMPION_LONG_PATH,
    CHAMPION_SHORT_PATH,
    MIN_BT_PF,
    MIN_BT_PRECISION,
    MIN_BT_TRADES,
    MIN_FT_PF_KEEP,
    MIN_FT_TRADES_EVAL,
    TOURNAMENT_DIR,
    log,
)


def demote_underperformers(db):
    """Demote FT models that fail performance gates.

    POLICY: FT is FREE data. Only demote truly catastrophic performers.
    - Must have 150+ trades (statistically significant)
    - Must have PF < 0.5 (clearly no edge)
    - Everything else keeps running to collect data
    """
    now_ms = int(time.time() * 1000)

    # Only demote catastrophic losers with enough data
    demoted = db.execute(
        """UPDATE tournament_models
           SET stage = 'retired', retired_at = ?,
               retire_reason = 'ft_catastrophic_pf_below_0.5_after_150_trades'
           WHERE stage IN ('forward_test', 'ft')
             AND ft_trades >= 150
             AND ft_pf < 0.5
             AND ft_pf IS NOT NULL""",
        (now_ms,),
    ).rowcount

    db.commit()
    if demoted > 0:
        log.info("demote_underperformers: retired %d catastrophic models (PF < 0.5 after 150+ trades)", demoted)
    else:
        log.debug("demote_underperformers: no models demoted (good — FT is free data)")


def crown_champion_if_ready(db):
    """Select the best FT model as champion, separately for long and short.

    Ranking criteria (in order):
    1. ft_pnl — total profit/loss percentage (primary)
    2. ft_pf — profit factor (secondary)
    3. ft_trades — more trades = more confidence (tiebreaker)

    Champion requirements:
    - stage = 'forward_test' or 'ft'
    - ft_trades >= 20 (basic minimum for comparison)
    - Must beat current champion's ft_pnl by CHAMPION_BEAT_MARGIN (10%)
    - MUST pass all backtest gates (dual validation — backtest + forward test)
      to prevent regime-shift bugs (e.g., FT PF 2.22 but BT PF 0.98).
      Gates: bt_pf >= MIN_BT_PF, bt_precision >= MIN_BT_PRECISION,
             bt_trades >= MIN_BT_TRADES, bt_ci_lower >= BOOTSTRAP_PF_LOWER_BOUND
    """
    now_ms = int(time.time() * 1000)

    for direction, pkl_path in [("long", CHAMPION_LONG_PATH),
                                 ("short", CHAMPION_SHORT_PATH)]:
        # Find current champion
        current = db.execute(
            """SELECT model_id, ft_pnl, ft_pf, ft_trades FROM tournament_models
               WHERE stage = 'champion' AND direction = ?""",
            (direction,),
        ).fetchone()

        current_pnl = current["ft_pnl"] if current else 0.0
        current_id = current["model_id"] if current else None

        # Find best FT candidate (ranked by pnl, then pf, then trades)
        # Also filter by backtest gates to prevent regime-shift bugs
        candidate = db.execute(
            """SELECT model_id, ft_pnl, ft_pf, ft_trades, bt_pf, bt_precision, bt_trades, bt_ci_lower
               FROM tournament_models
               WHERE stage IN ('forward_test', 'ft') AND direction = ?
                 AND ft_trades >= 20
                 AND ft_pnl IS NOT NULL
                 AND bt_pf >= ?
                 AND bt_precision >= ?
                 AND bt_trades >= ?
                 AND bt_ci_lower >= ?
               ORDER BY ft_pnl DESC, ft_pf DESC, ft_trades DESC
               LIMIT 1""",
            (direction, MIN_BT_PF, MIN_BT_PRECISION, MIN_BT_TRADES, BOOTSTRAP_PF_LOWER_BOUND),
        ).fetchone()

        if candidate is None:
            log.debug("crown_champion %s: no qualifying candidates (failed BT gates)", direction)
            continue

        cand_pnl = candidate["ft_pnl"]
        cand_pf = candidate["ft_pf"] or 0
        cand_trades = candidate["ft_trades"]
        cand_bt_pf = candidate["bt_pf"]
        cand_id = candidate["model_id"]

        # Must beat current champion by margin
        required_pnl = current_pnl * (1.0 + CHAMPION_BEAT_MARGIN) if current_pnl > 0 else 0.0
        if cand_pnl <= required_pnl:
            log.info("crown_champion %s: candidate %s (ft_pnl=%.2f%%, ft_pf=%.2f, bt_pf=%.2f, trades=%d) "
                     "does not beat current %s (pnl=%.2f%%, required=%.2f%%)",
                     direction, cand_id[:12], cand_pnl, cand_pf, cand_bt_pf, cand_trades,
                     current_id[:12] if current_id else "none", current_pnl, required_pnl)
            continue

        # Copy model pickle to champion path
        src_path = TOURNAMENT_DIR / f"{cand_id}.pkl"
        if src_path.exists():
            pkl_path.parent.mkdir(parents=True, exist_ok=True)
            model = joblib.load(src_path)
            joblib.dump(model, pkl_path)
            log.info("crown_champion %s: saved %s to %s", direction, cand_id[:12], pkl_path)
        else:
            log.error("crown_champion %s: pickle not found for %s", direction, cand_id[:12])
            continue

        # Demote old champion back to forward_test (NOT retired!)
        if current_id:
            db.execute(
                """UPDATE tournament_models
                   SET stage = 'forward_test', promoted_to_champion_at = NULL
                   WHERE model_id = ?""",
                (current_id,),
            )
            log.info("crown_champion %s: demoted old champion %s back to FT (keeps running)",
                     direction, current_id[:12])

        # Promote new champion
        db.execute(
            """UPDATE tournament_models
               SET stage = 'champion', promoted_to_champion_at = ?
               WHERE model_id = ?""",
            (now_ms, cand_id),
        )
        log.info("crown_champion %s: promoted %s (ft_pnl=%.2f%%, ft_pf=%.2f, bt_pf=%.2f, trades=%d)",
                 direction, cand_id[:12], cand_pnl, cand_pf, cand_bt_pf, cand_trades)

    db.commit()


def load_champions(db) -> tuple:
    """Load current long and short champion models.

    Returns (long_champ_dict, short_champ_dict) or (None, None).
    Each dict contains: model_id, model, ft_pnl, ft_trades, ft_pf, direction.
    The 'model' key holds the actual loaded classifier object.
    """
    results = {}

    for direction, pkl_path in [("long", CHAMPION_LONG_PATH), ("short", CHAMPION_SHORT_PATH)]:
        row = db.execute(
            "SELECT model_id, ft_pnl, ft_trades, ft_pf, entry_threshold, invalidation_threshold, "
            "feature_set, feature_version "
            "FROM tournament_models WHERE stage = 'champion' AND direction = ?",
            (direction,),
        ).fetchone()

        if row is None or not pkl_path.exists():
            results[direction] = None
            continue

        try:
            model = joblib.load(pkl_path)
        except Exception as e:
            log.error("load_champions: failed to load %s champion: %s", direction, e)
            results[direction] = None
            continue

        # Deserialize feature_set from JSON string or named preset
        import json as _json
        from src.tournament.challenger import FEATURE_SUBSETS
        raw_fs = row["feature_set"]
        feature_set = []
        if raw_fs:
            try:
                feature_set = _json.loads(raw_fs)
            except Exception:
                # Try as a named preset (e.g. "extended_only")
                feature_set = FEATURE_SUBSETS.get(raw_fs, [])
                if not feature_set:
                    log.warning("load_champions: unknown feature_set '%s' for %s", raw_fs, row["model_id"][:12])

        champ = {
            "model_id": row["model_id"],
            "model": model,
            "ft_pnl": row["ft_pnl"],
            "ft_trades": row["ft_trades"],
            "ft_pf": row["ft_pf"],
            "entry_threshold": row["entry_threshold"],
            "invalidation_threshold": row["invalidation_threshold"],
            "feature_set": feature_set,
            "feature_version": row["feature_version"],
            "direction": direction,
        }
        log.info("champion %s: %s pnl=%.2f%% trades=%d pf=%.2f",
                 direction, row["model_id"][:12], row["ft_pnl"] or 0,
                 row["ft_trades"] or 0, row["ft_pf"] or 0)
        results[direction] = champ

    return (results.get("long"), results.get("short"))
