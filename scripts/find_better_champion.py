#!/usr/bin/env python3
"""Find the better SHORT champion that was demoted."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import log
from src.db.schema import get_db

def main():
    """Find models with highest FT_PF in SHORT direction."""
    db = get_db()

    # Find all SHORT models in forward_test or champion stage, ordered by ft_pf
    models = db.execute(
        """SELECT model_id, stage, direction, ft_pf, ft_trades, bt_pf, bt_precision,
                  created_at, promoted_to_champion_at
           FROM tournament_models
           WHERE direction = 'short'
             AND stage IN ('forward_test', 'ft', 'champion')
             AND ft_trades >= 300  -- Focus on models with similar trade counts
           ORDER BY ft_pf DESC
           LIMIT 20"""
    ).fetchall()

    log.info("=" * 100)
    log.info("TOP 20 SHORT MODELS (by FT_PF, ft_trades >= 300)")
    log.info("=" * 100)
    log.info(
        "%-20s %-15s %8s %10s %8s %8s %20s",
        "Model ID",
        "Stage",
        "FT_PF",
        "FT_Trades",
        "BT_PF",
        "BT_Prec",
        "Champion At",
    )
    log.info("-" * 100)

    for m in models:
        champion_at = ""
        if m["promoted_to_champion_at"]:
            from datetime import datetime
            dt = datetime.fromtimestamp(m["promoted_to_champion_at"] / 1000)
            champion_at = dt.strftime("%Y-%m-%d %H:%M")

        log.info(
            "%-20s %-15s %8.2f %10d %8.2f %8.2f %20s",
            m["model_id"][:20],
            m["stage"],
            m["ft_pf"] or 0,
            m["ft_trades"] or 0,
            m["bt_pf"] or 0,
            m["bt_precision"] or 0,
            champion_at,
        )

    log.info("=" * 100)

    # Also check models starting with 1e5f3a
    log.info("\nSearching for models starting with '1e5f3a'...")
    matches = db.execute(
        """SELECT model_id, stage, direction, ft_pf, ft_trades
           FROM tournament_models
           WHERE model_id LIKE '1e5f3a%'"""
    ).fetchall()

    if matches:
        log.info("Found %d models:", len(matches))
        for m in matches:
            log.info(
                "  %s (stage=%s, dir=%s, ft_pf=%.2f, ft_trades=%d)",
                m["model_id"],
                m["stage"],
                m["direction"],
                m["ft_pf"] or 0,
                m["ft_trades"] or 0,
            )
    else:
        log.info("No models found starting with '1e5f3a'")

    db.close()


if __name__ == "__main__":
    main()
