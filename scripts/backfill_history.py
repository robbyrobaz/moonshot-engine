#!/usr/bin/env python3
"""One-shot historical candle backfill for all active coins.

Fills each coin back to BACKFILL_TARGET_YEARS (default 4y) from today.
Safe to re-run — INSERT OR IGNORE skips already-fetched bars.

Usage:
    python scripts/backfill_history.py              # all active coins
    python scripts/backfill_history.py --limit 50   # first N coins (testing)
    python scripts/backfill_history.py --symbol BTC-USDT  # single coin
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BACKFILL_TARGET_YEARS, log
from src.db.schema import init_db, get_db
from src.data.candles import backfill_candles


def run_backfill(symbols=None, limit=None):
    init_db()
    db = get_db()

    if symbols:
        todo = symbols
    else:
        rows = db.execute(
            "SELECT symbol FROM coins WHERE is_active = 1 ORDER BY symbol"
        ).fetchall()
        todo = [r["symbol"] for r in rows]

    if limit:
        todo = todo[:limit]

    target_ms = int(time.time() * 1000) - int(BACKFILL_TARGET_YEARS * 365.25 * 24 * 3600 * 1000)
    total_coins = len(todo)
    total_rows = 0
    already_done = 0

    log.info("backfill_history: %d coins, target=%dy back (~%s)",
             total_coins, BACKFILL_TARGET_YEARS,
             time.strftime("%Y-%m-%d", time.localtime(target_ms / 1000)))

    for i, symbol in enumerate(todo):
        # Check if already at target depth
        row = db.execute(
            "SELECT MIN(ts) as min_ts FROM candles WHERE symbol = ?", (symbol,)
        ).fetchone()
        oldest_ts = row["min_ts"] if row and row["min_ts"] else None

        if oldest_ts and oldest_ts <= target_ms:
            already_done += 1
            if already_done % 50 == 0:
                log.info("backfill_history: %d/%d already at target depth", already_done, total_coins)
            continue

        inserted = backfill_candles(db, symbol, target_years=BACKFILL_TARGET_YEARS)
        total_rows += inserted

        pct = (i + 1) / total_coins * 100
        if (i + 1) % 10 == 0 or (i + 1) == total_coins:
            log.info("backfill_history: %d/%d coins (%.0f%%) — +%d rows this run",
                     i + 1, total_coins, pct, total_rows)

    db.close()
    log.info("backfill_history: DONE — %d rows inserted, %d coins already at target depth",
             total_rows, already_done)
    return total_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Process only first N coins")
    parser.add_argument("--symbol", help="Backfill a single symbol")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else None
    run_backfill(symbols=symbols, limit=args.limit)
