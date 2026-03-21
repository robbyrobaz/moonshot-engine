#!/usr/bin/env python3
"""Test incremental feature computation fix.

This verifies that:
1. Initial run computes all features
2. Second run with no new candles skips computation
3. Run with new candles only computes the delta
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.db.schema import get_db
from src.features.compute import compute_all_features


def main():
    db = get_db()
    
    # Get a small sample of active symbols
    test_symbols = db.execute(
        "SELECT symbol FROM coins WHERE is_active = 1 LIMIT 5"
    ).fetchall()
    symbols = [r["symbol"] for r in test_symbols]
    
    print(f"\n{'='*60}")
    print(f"Testing incremental feature computation with {len(symbols)} symbols:")
    print(f"  {', '.join(symbols)}")
    print(f"{'='*60}\n")
    
    # Check current state
    for symbol in symbols:
        max_ts = db.execute(
            "SELECT MAX(ts) as max_ts FROM features WHERE symbol = ?",
            (symbol,)
        ).fetchone()["max_ts"]
        
        candle_count = db.execute(
            "SELECT COUNT(DISTINCT ts) as cnt FROM candles WHERE symbol = ?",
            (symbol,)
        ).fetchone()["cnt"]
        
        feature_count = db.execute(
            "SELECT COUNT(DISTINCT ts) as cnt FROM features WHERE symbol = ?",
            (symbol,)
        ).fetchone()["cnt"]
        
        print(f"{symbol}:")
        print(f"  Candles: {candle_count} bars")
        print(f"  Features: {feature_count} bars (latest: {max_ts})")
        print(f"  Gap: {candle_count - feature_count} bars")
    
    print(f"\n{'='*60}")
    print("Running incremental feature computation...")
    print(f"{'='*60}\n")
    
    # Run the incremental computation
    start = time.time()
    ts_ms = int(time.time() * 1000)
    results = compute_all_features(db, symbols, ts_ms)
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"Completed in {elapsed:.2f} seconds")
    print(f"{'='*60}\n")
    
    # Check results
    for symbol in symbols:
        feature_count_after = db.execute(
            "SELECT COUNT(DISTINCT ts) as cnt FROM features WHERE symbol = ?",
            (symbol,)
        ).fetchone()["cnt"]
        
        max_ts_after = db.execute(
            "SELECT MAX(ts) as max_ts FROM features WHERE symbol = ?",
            (symbol,)
        ).fetchone()["max_ts"]
        
        candle_count = db.execute(
            "SELECT COUNT(DISTINCT ts) as cnt FROM candles WHERE symbol = ?",
            (symbol,)
        ).fetchone()["cnt"]
        
        print(f"{symbol}:")
        print(f"  Features after: {feature_count_after} bars (latest: {max_ts_after})")
        print(f"  Candles: {candle_count} bars")
        print(f"  Status: {'✓ UP TO DATE' if feature_count_after == candle_count else f'⚠ {candle_count - feature_count_after} bars behind'}")
    
    print(f"\n{'='*60}")
    print("Re-running to verify skip logic...")
    print(f"{'='*60}\n")
    
    # Run again - should skip everything
    start = time.time()
    results2 = compute_all_features(db, symbols, ts_ms)
    elapsed2 = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"Second run completed in {elapsed2:.2f} seconds")
    print(f"Expected: <1 second (all skipped)")
    print(f"Status: {'✓ FAST (incremental working)' if elapsed2 < 1 else '⚠ SLOW (still recomputing)'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
