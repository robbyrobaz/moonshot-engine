#!/usr/bin/env python3
"""Fix ft_stats for all FT models by recomputing from closed positions."""

import sqlite3
import time

def compute_ft_pnl_metrics(db, model_id: str, total_pnl: float):
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


def update_model_ft_stats(db, model_id: str):
    """Recompute forward test stats for a model from its closed positions."""
    rows = db.execute(
        """SELECT pnl_pct FROM positions
           WHERE model_id = ? AND is_champion_trade = 0 AND status = 'closed'""",
        (model_id,),
    ).fetchall()

    trades = len(rows)
    if trades == 0:
        # Still update to set ft_trades=0 explicitly
        db.execute(
            """UPDATE tournament_models
               SET ft_trades = 0, ft_wins = 0, ft_pnl = 0.0, ft_pnl_per_day = 0.0,
                   ft_pnl_last_7d = 0.0, ft_pf = 0.0, ft_max_drawdown_pct = 0.0
               WHERE model_id = ?""",
            (model_id,),
        )
        return 0

    pnls = [r["pnl_pct"] for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    total_pnl = sum(pnls)
    win_pnl = sum(p for p in pnls if p > 0)
    loss_pnl = abs(sum(p for p in pnls if p < 0))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 999.0
    ft_pnl_per_day, ft_pnl_last_7d = compute_ft_pnl_metrics(db, model_id, total_pnl)

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
        (trades, wins, total_pnl, ft_pnl_per_day, ft_pnl_last_7d, pf, max_dd, model_id),
    )
    return trades


def main():
    db = sqlite3.connect('data/moonshot_v2.db')
    db.row_factory = sqlite3.Row

    # Get all FT models
    models = db.execute(
        "SELECT model_id, direction FROM tournament_models WHERE stage='forward_test'"
    ).fetchall()

    print(f"Fixing ft_stats for {len(models)} FT models...")

    updated_count = 0
    for model in models:
        model_id = model["model_id"]
        direction = model["direction"]
        trades = update_model_ft_stats(db, model_id)
        if trades > 0:
            print(f"  {model_id[:12]} ({direction}): {trades} trades")
            updated_count += 1

    db.commit()
    print(f"\nUpdated {updated_count} models with closed trades")

    # Show top LONG models after fix
    print("\nTop 5 LONG FT models after fix:")
    top_long = db.execute("""
        SELECT model_id, ft_pf, ft_trades, ft_pnl_last_7d
        FROM tournament_models
        WHERE direction='long' AND stage='forward_test' AND ft_trades > 0
        ORDER BY ft_pnl_last_7d DESC, ft_pf DESC
        LIMIT 5
    """).fetchall()

    for m in top_long:
        print(f"  {m['model_id'][:12]}: PF={m['ft_pf']:.2f}, trades={m['ft_trades']}, 7d PnL={m['ft_pnl_last_7d']:.2f}%")

    db.close()


if __name__ == "__main__":
    main()
