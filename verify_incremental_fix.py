#!/usr/bin/env python3
"""Verify incremental feature computation is working after deployment.

Run this after the next 4h cycle to confirm:
1. Features were only computed for new candle bars
2. Cycle completed in <10 minutes
3. All symbols are up-to-date
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.db.schema import get_db


def main():
    db = get_db()
    
    print("=" * 60)
    print("INCREMENTAL FEATURE COMPUTATION VERIFICATION")
    print("=" * 60)
    
    # Check latest cycle run
    latest_run = db.execute(
        "SELECT run_id, started_at, ended_at, "
        "(ended_at - started_at) / 1000.0 as duration_sec "
        "FROM runs WHERE ended_at IS NOT NULL "
        "ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    
    if latest_run:
        started = datetime.fromtimestamp(latest_run["started_at"] / 1000)
        completed = datetime.fromtimestamp(latest_run["ended_at"] / 1000)
        duration = latest_run["duration_sec"]
        
        print(f"\nLatest Cycle (run_id={latest_run['run_id']}):")
        print(f"  Started:    {started}")
        print(f"  Completed:  {completed}")
        print(f"  Duration:   {duration:.1f} seconds ({duration/60:.1f} minutes)")
        
        # Check if reasonable
        if duration < 600:  # < 10 minutes
            print(f"  Status:     ✓ FAST ({duration/60:.1f} min)")
        elif duration < 1800:  # < 30 minutes
            print(f"  Status:     ⚠ MODERATE ({duration/60:.1f} min)")
        else:
            print(f"  Status:     ✗ SLOW ({duration/60:.1f} min)")
    else:
        print("\n⚠ No completed runs found")
    
    # Check feature computation stats from latest cycle
    print("\n" + "=" * 60)
    print("FEATURE COMPUTATION STATUS")
    print("=" * 60)
    
    # Get all active symbols
    symbols = db.execute("SELECT symbol FROM coins WHERE is_active = 1").fetchall()
    total_symbols = len(symbols)
    
    print(f"\nActive symbols: {total_symbols}")
    
    # Sample check: verify features exist and are recent
    needs_features = 0
    up_to_date = 0
    misaligned = 0
    
    for r in symbols:
        symbol = r['symbol']
        
        max_candle = db.execute(
            "SELECT MAX(ts) as max_ts FROM candles WHERE symbol = ?",
            (symbol,)
        ).fetchone()['max_ts']
        
        max_feat = db.execute(
            "SELECT MAX(ts) as max_ts FROM features WHERE symbol = ?",
            (symbol,)
        ).fetchone()['max_ts']
        
        if not max_feat:
            needs_features += 1
        elif max_candle and max_candle > max_feat:
            needs_features += 1
        elif max_candle and max_candle == max_feat:
            up_to_date += 1
        else:
            misaligned += 1
    
    print(f"\nFeature Status:")
    print(f"  ✓ Up-to-date:     {up_to_date:4d} ({up_to_date/total_symbols*100:.1f}%)")
    if needs_features > 0:
        print(f"  ⚠ Need features:  {needs_features:4d} ({needs_features/total_symbols*100:.1f}%)")
    if misaligned > 0:
        print(f"  ⚠ Misaligned:     {misaligned:4d} ({misaligned/total_symbols*100:.1f}%)")
    
    # Check if incremental is working
    print("\n" + "=" * 60)
    print("INCREMENTAL LOGIC CHECK")
    print("=" * 60)
    
    # Look for recently computed features (last 5 hours)
    five_hours_ago = int((datetime.now() - timedelta(hours=5)).timestamp() * 1000)
    recent_features = db.execute(
        "SELECT COUNT(DISTINCT symbol) as symbol_count, "
        "COUNT(*) as row_count "
        "FROM features WHERE computed_at > ?",
        (five_hours_ago,)
    ).fetchone()
    
    print(f"\nFeatures computed in last 5 hours:")
    print(f"  Symbols touched: {recent_features['symbol_count']}")
    print(f"  Rows inserted:   {recent_features['row_count']}")
    
    # Expected: ~467 rows per 4h cycle (one per symbol for latest bar)
    expected_per_cycle = total_symbols
    
    if recent_features['row_count'] <= expected_per_cycle * 2:
        print(f"  Status:          ✓ INCREMENTAL (expected ~{expected_per_cycle} rows/cycle)")
    else:
        print(f"  Status:          ⚠ HIGH (expected ~{expected_per_cycle} rows/cycle)")
    
    # Final verdict
    print("\n" + "=" * 60)
    print("OVERALL STATUS")
    print("=" * 60)
    
    all_good = True
    
    if latest_run and latest_run["duration_sec"] < 600:
        print("  ✓ Cycle time: Fast (<10 min)")
    else:
        print("  ✗ Cycle time: Slow or no recent cycle")
        all_good = False
    
    if up_to_date >= total_symbols * 0.95:  # 95% up-to-date is good
        print(f"  ✓ Coverage: {up_to_date/total_symbols*100:.1f}% up-to-date")
    else:
        print(f"  ⚠ Coverage: Only {up_to_date/total_symbols*100:.1f}% up-to-date")
        all_good = False
    
    if recent_features['row_count'] <= expected_per_cycle * 2:
        print("  ✓ Incremental: Working correctly")
    else:
        print("  ⚠ Incremental: May be recomputing too much")
        all_good = False
    
    if all_good:
        print("\n🎉 INCREMENTAL FEATURE FIX: VERIFIED WORKING")
    else:
        print("\n⚠️  INCREMENTAL FEATURE FIX: NEEDS ATTENTION")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
