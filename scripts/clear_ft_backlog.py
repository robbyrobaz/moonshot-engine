#!/usr/bin/env python3
"""Clear FT backlog: retire all PF<0.5 models with 150+ trades.

This script immediately applies the new demotion threshold (150 trades)
to clear accumulated weak models and make room for fresh challengers.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.schema import get_db
from config import log


def clear_ft_backlog():
    """Retire all FT models with PF < 0.5 and 150+ trades."""
    db = get_db()
    now_ms = int(time.time() * 1000)

    # Count before
    before = db.execute(
        """SELECT COUNT(*) as cnt FROM tournament_models
           WHERE stage IN ('forward_test', 'ft')
             AND ft_trades >= 150
             AND ft_pf < 0.5
             AND ft_pf IS NOT NULL"""
    ).fetchone()
    before_count = before["cnt"]

    if before_count == 0:
        log.info("No FT backlog found (all models with 150+ trades have PF >= 0.5)")
        db.close()
        return

    # Get details before retiring
    models = db.execute(
        """SELECT model_id, direction, ft_trades, ft_pf, ft_pnl
           FROM tournament_models
           WHERE stage IN ('forward_test', 'ft')
             AND ft_trades >= 150
             AND ft_pf < 0.5
             AND ft_pf IS NOT NULL
           ORDER BY ft_pf ASC"""
    ).fetchall()

    log.info("Clearing FT backlog: retiring %d underperforming models", before_count)
    print(f"\n{'Model ID':<12} {'Dir':<6} {'Trades':<7} {'PF':<6} {'PnL %':<7}")
    print("─" * 50)
    for m in models:
        pf_str = f"{m['ft_pf']:.2f}" if m['ft_pf'] else "N/A"
        pnl_str = f"{m['ft_pnl']:.2f}%" if m['ft_pnl'] else "N/A"
        print(f"{m['model_id'][:12]:<12} {m['direction']:<6} {m['ft_trades']:<7} {pf_str:<6} {pnl_str:<7}")

    # Retire them
    retired = db.execute(
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
    db.close()

    log.info("✓ Retired %d models (freed up tournament slots)", retired)
    print(f"\n✓ Successfully retired {retired} underperforming FT models")
    print("  These models will no longer open new positions.")
    print("  Existing open positions will continue to completion.")
    return True


if __name__ == "__main__":
    try:
        success = clear_ft_backlog()
        sys.exit(0 if success else 1)
    except Exception as e:
        log.error("Backlog clear failed: %s", e)
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
