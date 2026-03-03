"""One-time historical feature backfill.

Computes features for every distinct timestamp in the labels table
so the backtest JOIN (features.ts = labels.ts) produces training data.
Safe to re-run: uses INSERT OR IGNORE.
"""
import sqlite3
import sys
import time

sys.path.insert(0, ".")
from src.features.compute import compute_all_features

DB_PATH = "data/moonshot_v2.db"

def main():
    db = sqlite3.connect(DB_PATH, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=60000")
    db.row_factory = sqlite3.Row

    symbols = [r[0] for r in db.execute(
        "SELECT DISTINCT symbol FROM candles ORDER BY symbol"
    ).fetchall()]
    print(f"Symbols: {len(symbols)}", flush=True)

    # Get all distinct label timestamps not yet in features
    missing_ts = [r[0] for r in db.execute("""
        SELECT DISTINCT l.ts FROM labels l
        WHERE NOT EXISTS (
            SELECT 1 FROM features f WHERE f.symbol = ? AND f.ts = l.ts
        )
        ORDER BY l.ts
    """, (symbols[0],)).fetchall()]
    print(f"Timestamps to backfill: {len(missing_ts)}", flush=True)

    if not missing_ts:
        print("Nothing to do — features already cover all label timestamps.", flush=True)
        return

    t_start = time.time()
    for i, ts in enumerate(missing_ts):
        compute_all_features(db, symbols, ts_ms=ts)
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            remaining = (len(missing_ts) - i - 1) / rate
            print(
                f"  [{i+1}/{len(missing_ts)}] "
                f"{elapsed:.0f}s elapsed, "
                f"~{remaining/60:.1f}m remaining",
                flush=True,
            )

    total = time.time() - t_start
    print(f"Backfill complete: {len(missing_ts)} timestamps in {total:.1f}s", flush=True)

    # Verify the JOIN now works
    count = db.execute("""
        SELECT COUNT(*) FROM features f
        JOIN labels l ON f.symbol = l.symbol AND f.ts = l.ts
        WHERE l.direction = 'long'
    """).fetchone()[0]
    print(f"Feature/label JOIN rows (long): {count:,}", flush=True)
    db.close()

if __name__ == "__main__":
    main()
