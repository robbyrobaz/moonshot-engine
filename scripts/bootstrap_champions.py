#!/usr/bin/env python3
"""Bootstrap champions for both long and short directions.

This script:
1. Generates 50 challengers (25 long, 25 short)
2. Backtests all of them
3. Promotes the best FT models to champion status
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import log
from src.db.schema import get_db
from src.tournament.challenger import generate_challengers
from src.tournament.backtest import backtest_new_challengers
from src.tournament.champion import crown_champion_if_ready


def main():
    """Bootstrap champions for both directions."""
    db = get_db()

    log.info("=" * 60)
    log.info("BOOTSTRAP CHAMPIONS — Generating long & short models")
    log.info("=" * 60)

    # Step 1: Generate 50 challengers (balanced 25 long, 25 short)
    log.info("Step 1: Generating 50 challengers...")
    new_challengers = generate_challengers(db, n=50)
    log.info(f"Generated {len(new_challengers)} new challengers")

    long_count = sum(1 for c in new_challengers if c.get("direction") == "long")
    short_count = sum(1 for c in new_challengers if c.get("direction") == "short")
    log.info(f"  - Long: {long_count}")
    log.info(f"  - Short: {short_count}")

    # Step 2: Backtest all new challengers
    log.info("\nStep 2: Backtesting all challengers...")
    backtest_new_challengers(db)
    log.info("Backtest complete")

    # Check how many passed BT gates
    long_ft = db.execute(
        "SELECT COUNT(*) as count FROM tournament_models WHERE stage='ft' AND direction='long'"
    ).fetchone()["count"]

    short_ft = db.execute(
        "SELECT COUNT(*) as count FROM tournament_models WHERE stage='ft' AND direction='short'"
    ).fetchone()["count"]

    log.info(f"\nBacktest results:")
    log.info(f"  - Long FT models: {long_ft}")
    log.info(f"  - Short FT models: {short_ft}")

    # Step 3: Check if we can promote any to champion
    log.info("\nStep 3: Attempting to crown champions...")

    # For new models with no FT trades yet, we'll need to manually promote the best BT performer
    # if there are no FT models with enough trades

    for direction in ["long", "short"]:
        # Check if there's already a champion
        current_champ = db.execute(
            "SELECT model_id FROM tournament_models WHERE stage='champion' AND direction=?",
            (direction,)
        ).fetchone()

        if current_champ:
            log.info(f"{direction.capitalize()} champion already exists: {current_champ['model_id'][:12]}")
            continue

        # Check if there are FT models with enough trades (20+)
        ft_with_trades = db.execute(
            "SELECT COUNT(*) as count FROM tournament_models WHERE stage='ft' AND direction=? AND ft_trades >= 20",
            (direction,)
        ).fetchone()["count"]

        if ft_with_trades == 0:
            # No FT models with trades yet — manually promote the best BT performer
            log.info(f"No {direction} FT models with enough trades. Promoting best BT performer...")

            # Get the best BT model (highest bt_pf that passed gates)
            min_bt_pf = 0.5 if direction == "long" else 1.0
            min_bt_precision = 0.15 if direction == "long" else 0.2
            min_bootstrap = 0.4 if direction == "long" else 0.8

            best_bt = db.execute(
                """SELECT model_id, bt_pf, bt_precision, bt_trades, bt_ci_lower
                   FROM tournament_models
                   WHERE stage='ft' AND direction=?
                     AND bt_pf >= ?
                     AND bt_precision >= ?
                     AND bt_trades >= 50
                     AND bt_ci_lower >= ?
                   ORDER BY bt_pf DESC, bt_precision DESC, bt_trades DESC
                   LIMIT 1""",
                (direction, min_bt_pf, min_bt_precision, min_bootstrap)
            ).fetchone()

            if best_bt:
                model_id = best_bt["model_id"]
                now_ms = int(time.time() * 1000)

                # Promote to champion
                db.execute(
                    """UPDATE tournament_models
                       SET stage='champion', promoted_to_champion_at=?
                       WHERE model_id=?""",
                    (now_ms, model_id)
                )
                db.commit()

                log.info(
                    f"Promoted {direction} champion: {model_id[:12]} "
                    f"(BT PF={best_bt['bt_pf']:.2f}, prec={best_bt['bt_precision']:.2f}, "
                    f"trades={best_bt['bt_trades']}, CI={best_bt['bt_ci_lower']:.2f})"
                )

                # Copy model pickle to champion path
                import joblib
                from pathlib import Path
                tournament_dir = Path("models/tournament")
                champion_path = Path(f"models/champion_{direction}.pkl")

                src_path = tournament_dir / f"{model_id}.pkl"
                if src_path.exists():
                    champion_path.parent.mkdir(parents=True, exist_ok=True)
                    model = joblib.load(src_path)
                    joblib.dump(model, champion_path)
                    log.info(f"Copied {model_id[:12]} to {champion_path}")
            else:
                log.warning(f"No {direction} models passed BT gates!")

    # Also try the normal crown_champion_if_ready (for models with FT trades)
    crown_champion_if_ready(db)

    # Final summary
    log.info("\n" + "=" * 60)
    log.info("FINAL STATE")
    log.info("=" * 60)

    champions = db.execute(
        """SELECT model_id, direction, bt_pf, ft_trades, ft_pf, ft_pnl
           FROM tournament_models WHERE stage='champion'"""
    ).fetchall()

    for champ in champions:
        log.info(
            f"{champ['direction'].capitalize()} champion: {champ['model_id'][:12]} "
            f"(BT PF={champ['bt_pf']:.2f}, FT trades={champ['ft_trades'] or 0}, "
            f"FT PF={champ['ft_pf'] or 0:.2f}, FT PnL={champ['ft_pnl'] or 0:.2f}%)"
        )

    ft_models = db.execute(
        "SELECT direction, COUNT(*) as count FROM tournament_models WHERE stage='ft' GROUP BY direction"
    ).fetchall()

    for ft in ft_models:
        log.info(f"{ft['direction'].capitalize()} FT models: {ft['count']}")

    db.close()
    log.info("\nBootstrap complete!")


if __name__ == "__main__":
    main()
