"""Moonshot v2 — Path-Dependent Label Generation.

Labels are computed per-bar: given an entry at bar N, did price hit TP first
(label=1) or SL first / neither within the horizon (label=0)?

Labels are direction-aware: long entries check high >= TP / low <= SL,
short entries check low <= TP / high >= SL.
"""

import time

from config import TP_PCT, SL_PCT, LABEL_HORIZON_BARS, PNL_WEIGHT_TP, PNL_WEIGHT_SL, log


def compute_label(symbol, ts_idx, direction, candles, tp=None, sl=None, horizon=None):
    """Path-dependent label for a single bar.

    Args:
        symbol: coin symbol (for logging only)
        ts_idx: index into the candles list for the entry bar
        direction: 'long' or 'short'
        candles: list of candle dicts/rows with keys: close, high, low
        tp: take-profit percentage (default from config)
        sl: stop-loss percentage (default from config)
        horizon: max bars to look forward (default from config)

    Returns:
        1 if TP hit first, 0 if SL hit first or neither hit within horizon,
        None if insufficient future bars (incomplete data).
    """
    if tp is None:
        tp = TP_PCT
    if sl is None:
        sl = SL_PCT
    if horizon is None:
        horizon = LABEL_HORIZON_BARS

    entry_price = candles[ts_idx]["close"]

    for i in range(1, horizon + 1):
        if ts_idx + i >= len(candles):
            return None  # incomplete — not enough future bars

        bar = candles[ts_idx + i]

        if direction == "long":
            if bar["high"] >= entry_price * (1 + tp):
                return 1
            if bar["low"] <= entry_price * (1 - sl):
                return 0
        else:  # short
            if bar["low"] <= entry_price * (1 - tp):
                return 1
            if bar["high"] >= entry_price * (1 + sl):
                return 0

    return 0  # neither TP nor SL hit within horizon


def generate_labels(db, symbols=None, tp=None, sl=None, horizon=None):
    """Generate labels for all symbols (or given list).

    Only computes for bars not already labeled with the same (tp, sl) params.
    Stores results in the labels table.

    Args:
        db: sqlite3 connection
        symbols: list of symbol strings, or None for all active coins
        tp: take-profit pct (default from config)
        sl: stop-loss pct (default from config)
        horizon: bars to look forward (default from config)

    Returns:
        dict with counts: {"total": N, "labeled": M, "skipped_incomplete": K}
    """
    if tp is None:
        tp = TP_PCT
    if sl is None:
        sl = SL_PCT
    if horizon is None:
        horizon = LABEL_HORIZON_BARS

    if symbols is None:
        rows = db.execute("SELECT symbol FROM coins WHERE is_active = 1").fetchall()
        symbols = [r["symbol"] for r in rows]

    stats = {"total": 0, "labeled": 0, "skipped_incomplete": 0}
    computed_at = int(time.time() * 1000)

    for symbol in symbols:
        # Load all candles for this symbol ordered by timestamp
        candles = db.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = ? ORDER BY ts ASC",
            (symbol,),
        ).fetchall()

        if len(candles) < horizon + 1:
            continue

        # Find which timestamps already have labels for this (symbol, direction, tp, sl)
        existing_long = set()
        existing_short = set()
        for row in db.execute(
            "SELECT ts, direction FROM labels "
            "WHERE symbol = ? AND tp_pct = ? AND sl_pct = ?",
            (symbol, tp, sl),
        ).fetchall():
            if row["direction"] == "long":
                existing_long.add(row["ts"])
            else:
                existing_short.add(row["ts"])

        batch = []
        for idx in range(len(candles)):
            bar_ts = candles[idx]["ts"]

            for direction, existing_set in [("long", existing_long), ("short", existing_short)]:
                stats["total"] += 1

                if bar_ts in existing_set:
                    continue  # already labeled

                label = compute_label(symbol, idx, direction, candles, tp, sl, horizon)

                if label is None:
                    stats["skipped_incomplete"] += 1
                    continue

                batch.append((
                    symbol, bar_ts, direction, label, tp, sl, horizon, computed_at
                ))
                stats["labeled"] += 1

            # Batch insert every 1000 rows
            if len(batch) >= 1000:
                db.executemany(
                    "INSERT OR IGNORE INTO labels "
                    "(symbol, ts, direction, label, tp_pct, sl_pct, horizon_bars, computed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                batch.clear()

        # Insert remaining
        if batch:
            db.executemany(
                "INSERT OR IGNORE INTO labels "
                "(symbol, ts, direction, label, tp_pct, sl_pct, horizon_bars, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )

    db.commit()
    log.info(
        "Label generation: %d total, %d labeled, %d incomplete",
        stats["total"], stats["labeled"], stats["skipped_incomplete"],
    )
    return stats


def get_sample_weights(labels):
    """PnL-weighted sample weights.

    label=1 (TP hit) -> weight = PNL_WEIGHT_TP (1.0)
    label=0 (SL hit) -> weight = PNL_WEIGHT_SL (0.5)

    Args:
        labels: list/array of 0/1 label values

    Returns:
        list of float weights, same length as labels
    """
    return [PNL_WEIGHT_TP if lbl == 1 else PNL_WEIGHT_SL for lbl in labels]
