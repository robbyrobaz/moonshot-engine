#!/usr/bin/env python3
"""Manually re-promote the better SHORT champion (1e5f3a28) after bug fix.

This script:
1. Shows current champion status
2. Manually promotes 1e5f3a2881bd (FT_PF=1.48, 344 trades) as SHORT champion
3. Demotes 3c905c7af311 (FT_PF=1.04, 349 trades) back to forward_test
4. Copies model pickle to champion path
"""

import sys
import time
from pathlib import Path
import joblib

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import log, MODELS_DIR, TOURNAMENT_DIR
from src.db.schema import get_db

CHAMPION_SHORT_PATH = MODELS_DIR / "champion_short.pkl"
BETTER_MODEL_ID = "1e5f3a28123b"  # FT_PF=1.48, 344 trades
WORSE_MODEL_ID = "3c905c7a9f91"   # FT_PF=1.04, 349 trades (current champion)


def main():
    """Manually re-promote the better SHORT champion."""
    log.info("=" * 80)
    log.info("MANUAL SHORT CHAMPION RE-PROMOTION")
    log.info("=" * 80)

    db = get_db()

    # Step 1: Show current status
    log.info("\nSTEP 1: Current champion status")
    log.info("-" * 80)

    current = db.execute(
        """SELECT model_id, stage, direction, ft_pf, ft_trades, bt_pf, bt_precision, bt_trades
           FROM tournament_models WHERE stage = 'champion' AND direction = 'short'"""
    ).fetchone()

    if current:
        log.info(
            "Current SHORT champion: %s (ft_pf=%.2f, ft_trades=%d, bt_pf=%.2f)",
            current["model_id"][:12],
            current["ft_pf"] or 0,
            current["ft_trades"] or 0,
            current["bt_pf"] or 0,
        )
    else:
        log.info("No current SHORT champion found")

    # Step 2: Show candidate models
    log.info("\nSTEP 2: Checking candidate models")
    log.info("-" * 80)

    better = db.execute(
        """SELECT model_id, stage, direction, ft_pf, ft_trades, bt_pf, bt_precision, bt_trades
           FROM tournament_models WHERE model_id = ?""",
        (BETTER_MODEL_ID,),
    ).fetchone()

    worse = db.execute(
        """SELECT model_id, stage, direction, ft_pf, ft_trades, bt_pf, bt_precision, bt_trades
           FROM tournament_models WHERE model_id = ?""",
        (WORSE_MODEL_ID,),
    ).fetchone()

    if better:
        log.info(
            "Better model: %s (stage=%s, ft_pf=%.2f, ft_trades=%d, bt_pf=%.2f)",
            better["model_id"][:12],
            better["stage"],
            better["ft_pf"] or 0,
            better["ft_trades"] or 0,
            better["bt_pf"] or 0,
        )
    else:
        log.error("Better model %s NOT FOUND in DB!", BETTER_MODEL_ID[:12])
        db.close()
        return

    if worse:
        log.info(
            "Worse model:  %s (stage=%s, ft_pf=%.2f, ft_trades=%d, bt_pf=%.2f)",
            worse["model_id"][:12],
            worse["stage"],
            worse["ft_pf"] or 0,
            worse["ft_trades"] or 0,
            worse["bt_pf"] or 0,
        )

    # Step 3: Demote current champion (if it's the worse model)
    if current and current["model_id"] == WORSE_MODEL_ID:
        log.info("\nSTEP 3: Demoting current champion %s back to forward_test", WORSE_MODEL_ID[:12])
        log.info("-" * 80)

        db.execute(
            """UPDATE tournament_models
               SET stage = 'forward_test', promoted_to_champion_at = NULL
               WHERE model_id = ?""",
            (WORSE_MODEL_ID,),
        )
        log.info("Demoted %s → forward_test", WORSE_MODEL_ID[:12])
    else:
        log.info("\nSTEP 3: Current champion is not the worse model, skipping demotion")

    # Step 4: Promote better model to champion
    log.info("\nSTEP 4: Promoting better model %s to SHORT champion", BETTER_MODEL_ID[:12])
    log.info("-" * 80)

    now_ms = int(time.time() * 1000)

    # Copy model pickle to champion path
    src_path = TOURNAMENT_DIR / f"{BETTER_MODEL_ID}.pkl"
    if src_path.exists():
        CHAMPION_SHORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        model = joblib.load(src_path)
        joblib.dump(model, CHAMPION_SHORT_PATH)
        log.info("Copied %s → %s", src_path, CHAMPION_SHORT_PATH)
    else:
        log.error("Pickle not found: %s", src_path)
        db.close()
        return

    # Update DB
    db.execute(
        """UPDATE tournament_models
           SET stage = 'champion', promoted_to_champion_at = ?
           WHERE model_id = ?""",
        (now_ms, BETTER_MODEL_ID),
    )
    log.info("Promoted %s → champion (ft_pf=%.2f)", BETTER_MODEL_ID[:12], better["ft_pf"] or 0)

    db.commit()

    # Step 5: Final status
    log.info("\nSTEP 5: Final champion status")
    log.info("-" * 80)

    final = db.execute(
        """SELECT model_id, stage, direction, ft_pf, ft_trades, bt_pf
           FROM tournament_models WHERE stage = 'champion' AND direction = 'short'"""
    ).fetchone()

    if final:
        log.info(
            "SHORT champion: %s (ft_pf=%.2f, ft_trades=%d, bt_pf=%.2f)",
            final["model_id"][:12],
            final["ft_pf"] or 0,
            final["ft_trades"] or 0,
            final["bt_pf"] or 0,
        )
    else:
        log.error("No SHORT champion after promotion!")

    log.info("=" * 80)
    log.info("RE-PROMOTION COMPLETE")
    log.info("=" * 80)

    db.close()


if __name__ == "__main__":
    main()
