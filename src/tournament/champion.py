"""Moonshot v2 — Champion selection and demotion logic.

2026-03-07: MAJOR POLICY CHANGE
- FT is FREE data collection — never demote early
- Only demote if: PF < 0.5 AND trades >= 500 (catastrophic AND significant)
- Rank by: ft_pnl_last_7d (primary), ft_pnl_per_day (secondary),
  ft_pf (tertiary), ft_trades (tiebreaker)
- Let models run! Data collection IS the goal.
"""

import time

import joblib

from config import (
    BOOTSTRAP_PF_LOWER_BOUND,
    BOOTSTRAP_PF_LOWER_BOUND_LONG,
    CHAMPION_BEAT_MARGIN,
    CHAMPION_LONG_PATH,
    CHAMPION_SHORT_PATH,
    MIN_BT_PF,
    MIN_BT_PF_LONG,
    MIN_BT_PRECISION,
    MIN_BT_PRECISION_LONG,
    MIN_BT_TRADES,
    MIN_FT_PF_KEEP,
    MIN_FT_PF_KEEP_50,
    MIN_FT_TRADES_EVAL,
    MIN_FT_TRADES_EVAL_50,
    TOURNAMENT_DIR,
    log,
)


def demote_underperformers(db):
    """Demote FT models that fail performance gates.

    POLICY: Two-tier retirement to manage FT backlog while respecting data collection.
    Tier 1: Unprofitable models (PF < MIN_FT_PF_KEEP_50 after MIN_FT_TRADES_EVAL_50)
    Tier 2: Catastrophic models (PF < MIN_FT_PF_KEEP after MIN_FT_TRADES_EVAL)
    """
    now_ms = int(time.time() * 1000)

    # Tier 1: Retire unprofitable models early (default: PF < 0.9 after 50 trades)
    tier1 = db.execute(
        """UPDATE tournament_models
           SET stage = 'retired', retired_at = ?,
               retire_reason = ?
           WHERE stage IN ('forward_test', 'ft')
             AND ft_trades >= ?
             AND ft_pf < ?
             AND ft_pf IS NOT NULL""",
        (
            now_ms,
            f'ft_unprofitable_pf_below_{MIN_FT_PF_KEEP_50}_after_{MIN_FT_TRADES_EVAL_50}_trades',
            MIN_FT_TRADES_EVAL_50,
            MIN_FT_PF_KEEP_50,
        ),
    ).rowcount

    # Tier 2: Retire catastrophic losers with more data (default: PF < 0.5 after 150 trades)
    tier2 = db.execute(
        """UPDATE tournament_models
           SET stage = 'retired', retired_at = ?,
               retire_reason = ?
           WHERE stage IN ('forward_test', 'ft')
             AND ft_trades >= ?
             AND ft_pf < ?
             AND ft_pf IS NOT NULL""",
        (
            now_ms,
            f'ft_catastrophic_pf_below_{MIN_FT_PF_KEEP}_after_{MIN_FT_TRADES_EVAL}_trades',
            MIN_FT_TRADES_EVAL,
            MIN_FT_PF_KEEP,
        ),
    ).rowcount

    db.commit()
    total = tier1 + tier2
    if total > 0:
        log.info("demote_underperformers: retired %d models (tier1=%d unprofitable, tier2=%d catastrophic)",
                 total, tier1, tier2)
    else:
        log.debug("demote_underperformers: no models demoted")


def crown_champion_if_ready(db):
    """Select the best FT model as champion, separately for long and short.

    Ranking criteria (in order):
    1. ft_pf — profit factor (primary, always populated, robust metric)
    2. ft_trades — more trades = more confidence (tiebreaker)

    Champion requirements:
    - stage = 'forward_test' or 'ft'
    - ft_trades >= 20 (basic minimum for comparison)
    - Must beat current champion's ft_pf by CHAMPION_BEAT_MARGIN (10%)
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
            """SELECT model_id, ft_pnl, ft_pnl_per_day, ft_pnl_last_7d, ft_pf, ft_trades
               FROM tournament_models
               WHERE stage = 'champion' AND direction = ?""",
            (direction,),
        ).fetchone()

        current_pf = current["ft_pf"] if current else 0.0
        current_id = current["model_id"] if current else None

        # Select direction-specific gates
        min_bt_pf = MIN_BT_PF_LONG if direction == "long" else MIN_BT_PF
        min_bt_precision = MIN_BT_PRECISION_LONG if direction == "long" else MIN_BT_PRECISION
        min_bootstrap = BOOTSTRAP_PF_LOWER_BOUND_LONG if direction == "long" else BOOTSTRAP_PF_LOWER_BOUND

        # Find best FT candidate (ranked by profit factor, then trades for confidence)
        # Also filter by backtest gates to prevent regime-shift bugs
        candidate = db.execute(
            """SELECT model_id, ft_pnl, ft_pnl_per_day, ft_pnl_last_7d, ft_pf,
                      ft_trades, bt_pf, bt_precision, bt_trades, bt_ci_lower
               FROM tournament_models
               WHERE stage IN ('forward_test', 'ft') AND direction = ?
                 AND ft_trades >= 20
                 AND bt_pf >= ?
                 AND bt_precision >= ?
                 AND bt_trades >= ?
                 AND bt_ci_lower >= ?
               ORDER BY ft_pf DESC, ft_trades DESC
               LIMIT 1""",
            (direction, min_bt_pf, min_bt_precision, MIN_BT_TRADES, min_bootstrap),
        ).fetchone()

        if candidate is None:
            log.debug("crown_champion %s: no qualifying candidates (failed BT gates: pf>=%.2f, prec>=%.2f, ci>=%.2f)",
                      direction, min_bt_pf, min_bt_precision, min_bootstrap)
            continue

        cand_pnl = candidate["ft_pnl"]
        cand_pnl_per_day = candidate["ft_pnl_per_day"] or 0.0
        cand_recent_pnl = candidate["ft_pnl_last_7d"] or 0.0
        cand_pf = candidate["ft_pf"] or 0
        cand_trades = candidate["ft_trades"]
        cand_bt_pf = candidate["bt_pf"]
        cand_id = candidate["model_id"]

        # Must beat current champion by margin
        required_pf = (
            current_pf * (1.0 + CHAMPION_BEAT_MARGIN)
            if current_pf > 0
            else current_pf
        )
        if cand_pf <= required_pf:
            log.info(
                "crown_champion %s: candidate %s (ft_pf=%.2f, ft_trades=%d, bt_pf=%.2f) "
                "does not beat current %s (ft_pf=%.2f, required_pf=%.2f)",
                direction,
                cand_id[:12],
                cand_pf,
                cand_trades,
                cand_bt_pf,
                current_id[:12] if current_id else "none",
                current_pf,
                required_pf,
            )
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
        log.info(
            "crown_champion %s: promoted %s (ft_pf=%.2f, ft_trades=%d, bt_pf=%.2f)",
            direction,
            cand_id[:12],
            cand_pf,
            cand_trades,
            cand_bt_pf,
        )

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

        # Get actual champion performance (not FT stats)
        champ_stats = db.execute(
            """SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) as closed_trades,
                SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) as open_trades,
                SUM(CASE WHEN status='closed' THEN pnl_pct ELSE 0 END) as total_pnl,
                AVG(CASE WHEN status='closed' AND pnl_pct IS NOT NULL THEN pnl_pct END) as avg_pnl
            FROM positions
            WHERE model_id = ? AND is_champion_trade = 1""",
            (row["model_id"],),
        ).fetchone()

        total = champ_stats["total_trades"] or 0
        closed = champ_stats["closed_trades"] or 0
        open_pos = champ_stats["open_trades"] or 0
        total_pnl = champ_stats["total_pnl"] or 0
        avg_pnl = champ_stats["avg_pnl"] or 0

        # Calculate PF from closed trades
        champ_pf = 0.0
        if closed > 0:
            closed_trades = db.execute(
                """SELECT pnl_pct FROM positions
                WHERE model_id = ? AND is_champion_trade = 1 AND status = 'closed' AND pnl_pct IS NOT NULL""",
                (row["model_id"],),
            ).fetchall()
            wins = sum(1 for t in closed_trades if t["pnl_pct"] > 0)
            losses = sum(1 for t in closed_trades if t["pnl_pct"] <= 0)
            if losses > 0:
                avg_win = sum(t["pnl_pct"] for t in closed_trades if t["pnl_pct"] > 0) / wins if wins > 0 else 0
                avg_loss = abs(sum(t["pnl_pct"] for t in closed_trades if t["pnl_pct"] <= 0) / losses)
                if avg_loss > 0:
                    champ_pf = (wins / (wins + losses)) * (avg_win / avg_loss) if wins > 0 else 0

        log.info("champion %s: %s champ_trades=%d (%d open, %d closed) pnl=%.2f%% pf=%.2f | FT: %d trades pf=%.2f",
                 direction, row["model_id"][:12], total, open_pos, closed,
                 total_pnl, champ_pf, row["ft_trades"] or 0, row["ft_pf"] or 0)
        results[direction] = champ

    return (results.get("long"), results.get("short"))
