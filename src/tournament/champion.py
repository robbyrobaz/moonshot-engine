"""Moonshot v2 — Champion selection and demotion logic."""

import time

import joblib

from config import (
    CHAMPION_BEAT_MARGIN,
    CHAMPION_LONG_PATH,
    CHAMPION_SHORT_PATH,
    MIN_FT_PF_KEEP,
    MIN_FT_PF_KEEP_50,
    MIN_FT_TRADES_EVAL,
    TOURNAMENT_DIR,
    log,
)


def demote_underperformers(db):
    """Demote FT models that fail performance gates.

    After 20 trades: ft_pf < 1.3 -> stage='retired'
    After 50 trades: ft_pf < 1.5 -> stage='retired'
    """
    now_ms = int(time.time() * 1000)

    # Gate 1: 20+ trades, PF < 1.3
    demoted_20 = db.execute(
        """UPDATE tournament_models
           SET stage = 'retired', retired_at = ?,
               retire_reason = 'ft_pf_below_1.3_after_20_trades'
           WHERE stage = 'forward_test'
             AND ft_trades >= ?
             AND ft_pf < ?""",
        (now_ms, MIN_FT_TRADES_EVAL, MIN_FT_PF_KEEP),
    ).rowcount

    # Gate 2: 50+ trades, PF < 1.5
    demoted_50 = db.execute(
        """UPDATE tournament_models
           SET stage = 'retired', retired_at = ?,
               retire_reason = 'ft_pf_below_1.5_after_50_trades'
           WHERE stage = 'forward_test'
             AND ft_trades >= 50
             AND ft_pf < ?""",
        (now_ms, MIN_FT_PF_KEEP_50),
    ).rowcount

    db.commit()
    total = demoted_20 + demoted_50
    if total > 0:
        log.info("demote_underperformers: retired %d models (%d at 20-trade gate, %d at 50-trade gate)",
                 total, demoted_20, demoted_50)


def crown_champion_if_ready(db):
    """Select the best FT model as champion, separately for long and short.

    Champion criteria:
    - stage = 'forward_test'
    - ft_trades >= MIN_FT_TRADES_EVAL (20)
    - Best ft_pnl among qualifying models
    - Must beat current champion's ft_pnl by CHAMPION_BEAT_MARGIN (10%)
    """
    now_ms = int(time.time() * 1000)

    for direction, pkl_path in [("long", CHAMPION_LONG_PATH),
                                 ("short", CHAMPION_SHORT_PATH)]:
        # Find current champion
        current = db.execute(
            """SELECT model_id, ft_pnl FROM tournament_models
               WHERE stage = 'champion' AND direction = ?""",
            (direction,),
        ).fetchone()

        current_pnl = current["ft_pnl"] if current else 0.0
        current_id = current["model_id"] if current else None

        # Find best FT candidate
        candidate = db.execute(
            """SELECT model_id, ft_pnl FROM tournament_models
               WHERE stage = 'forward_test' AND direction = ?
                 AND ft_trades >= ?
               ORDER BY ft_pnl DESC
               LIMIT 1""",
            (direction, MIN_FT_TRADES_EVAL),
        ).fetchone()

        if candidate is None:
            continue

        cand_pnl = candidate["ft_pnl"]
        cand_id = candidate["model_id"]

        # Must beat current champion by margin
        required_pnl = current_pnl * (1.0 + CHAMPION_BEAT_MARGIN) if current_pnl > 0 else 0.0
        if cand_pnl <= required_pnl:
            log.info("crown_champion %s: candidate %s (pnl=%.4f) does not beat "
                     "current %s (pnl=%.4f, required=%.4f)",
                     direction, cand_id, cand_pnl,
                     current_id or "none", current_pnl, required_pnl)
            continue

        # Copy model pickle to champion path
        src_path = TOURNAMENT_DIR / f"{cand_id}.pkl"
        if src_path.exists():
            pkl_path.parent.mkdir(parents=True, exist_ok=True)
            model = joblib.load(src_path)
            joblib.dump(model, pkl_path)
            log.info("crown_champion %s: saved %s to %s", direction, cand_id, pkl_path)
        else:
            log.error("crown_champion %s: pickle not found for %s", direction, cand_id)
            continue

        # Demote old champion back to forward_test
        if current_id:
            db.execute(
                """UPDATE tournament_models
                   SET stage = 'forward_test', promoted_to_champion_at = NULL
                   WHERE model_id = ?""",
                (current_id,),
            )
            log.info("crown_champion %s: demoted old champion %s to forward_test",
                     direction, current_id)

        # Promote new champion
        db.execute(
            """UPDATE tournament_models
               SET stage = 'champion', promoted_to_champion_at = ?
               WHERE model_id = ?""",
            (now_ms, cand_id),
        )
        log.info("crown_champion %s: promoted %s (ft_pnl=%.4f)",
                 direction, cand_id, cand_pnl)

    db.commit()


def load_champions(db) -> tuple:
    """Load current long and short champion models.

    Returns (long_model, short_model) or (None, None).
    Each model is loaded from the champion pickle path.
    """
    long_model = None
    short_model = None

    if CHAMPION_LONG_PATH.exists():
        try:
            long_model = joblib.load(CHAMPION_LONG_PATH)
        except Exception as e:
            log.error("load_champions: failed to load long champion: %s", e)

    if CHAMPION_SHORT_PATH.exists():
        try:
            short_model = joblib.load(CHAMPION_SHORT_PATH)
        except Exception as e:
            log.error("load_champions: failed to load short champion: %s", e)

    # Log champion info
    for direction, model in [("long", long_model), ("short", short_model)]:
        if model is not None:
            row = db.execute(
                "SELECT model_id, ft_pnl, ft_trades, ft_pf FROM tournament_models "
                "WHERE stage = 'champion' AND direction = ?",
                (direction,),
            ).fetchone()
            if row:
                log.info("champion %s: %s ft_pnl=%.4f ft_trades=%d ft_pf=%.2f",
                         direction, row["model_id"], row["ft_pnl"],
                         row["ft_trades"], row["ft_pf"])

    return (long_model, short_model)
