"""Moonshot v2 — Candle data fetching and backfill."""

import time
import sqlite3
import requests
from pathlib import Path
from config import (
    BLOFIN_BASE_URL,
    BLOFIN_RATE_LIMIT_RPS,
    CANDLE_INTERVAL,
    CANDLE_LOOKBACK_BARS,
    BACKFILL_TARGET_YEARS,
    V1_DATA_DIR,
    log,
)


def _parse_candles(symbol: str, raw: list) -> list[tuple]:
    """Parse raw Blofin candle array into (symbol, ts, o, h, l, c, vol) tuples."""
    rows = []
    for c in raw:
        try:
            ts = int(c[0])
            o, h, l, cl, vol = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
            rows.append((symbol, ts, o, h, l, cl, vol))
        except (IndexError, ValueError, TypeError) as e:
            log.warning("_parse_candles: bad candle for %s: %s", symbol, e)
    return rows


def _insert_candles(db, rows: list[tuple]) -> int:
    """INSERT OR IGNORE candles. Returns count of rows inserted."""
    if not rows:
        return 0
    cursor = db.executemany(
        "INSERT OR IGNORE INTO candles (symbol, ts, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    db.commit()
    return cursor.rowcount


def fetch_latest_candles(db, symbols: list[str], bars: int = CANDLE_LOOKBACK_BARS) -> int:
    """Fetch latest N bars for each symbol. Returns total rows inserted."""
    total = 0
    delay = 1.0 / BLOFIN_RATE_LIMIT_RPS
    url = f"{BLOFIN_BASE_URL}/api/v1/market/candles"

    for i, symbol in enumerate(symbols):
        try:
            resp = requests.get(
                url,
                params={"instId": symbol, "bar": CANDLE_INTERVAL, "limit": str(bars)},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            rows = _parse_candles(symbol, data)
            inserted = _insert_candles(db, rows)
            total += inserted
        except Exception as e:
            log.warning("fetch_latest_candles: %s error: %s", symbol, e)

        if i < len(symbols) - 1:
            time.sleep(delay)

    log.info("fetch_latest_candles: %d rows inserted across %d symbols", total, len(symbols))
    return total


def backfill_candles(db, symbol: str, target_years: int = BACKFILL_TARGET_YEARS) -> int:
    """Paginate backwards to fetch historical candles for a symbol.

    Uses the `before` param (fetch candles with ts < before).
    Updates oldest_candle_ts in coins table. Returns total rows inserted.
    """
    url = f"{BLOFIN_BASE_URL}/api/v1/market/candles"
    delay = 1.0 / BLOFIN_RATE_LIMIT_RPS
    target_ms = int(time.time() * 1000) - (target_years * 365.25 * 24 * 3600 * 1000)
    total = 0

    # Start from the oldest candle we already have, or from now
    row = db.execute(
        "SELECT MIN(ts) as min_ts FROM candles WHERE symbol = ?", (symbol,)
    ).fetchone()
    before = row["min_ts"] if row and row["min_ts"] else None

    while True:
        params = {"instId": symbol, "bar": CANDLE_INTERVAL, "limit": "200"}
        if before is not None:
            params["before"] = str(before)

        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception as e:
            log.warning("backfill_candles: %s error: %s", symbol, e)
            break

        if not data:
            break

        rows = _parse_candles(symbol, data)
        if not rows:
            break

        inserted = _insert_candles(db, rows)
        total += inserted

        oldest_ts = min(r[1] for r in rows)
        before = oldest_ts

        # Check if we've reached our target
        if oldest_ts <= target_ms:
            log.info("backfill_candles: %s reached target date", symbol)
            break

        # If API returned fewer than expected, we've hit the end
        if len(data) < 200:
            break

        time.sleep(delay)

    # Update oldest_candle_ts in coins table
    if total > 0:
        oldest = db.execute(
            "SELECT MIN(ts) as min_ts FROM candles WHERE symbol = ?", (symbol,)
        ).fetchone()
        if oldest and oldest["min_ts"]:
            db.execute(
                "UPDATE coins SET oldest_candle_ts = ? WHERE symbol = ?",
                (oldest["min_ts"], symbol),
            )
            db.commit()

    log.info("backfill_candles: %s — %d rows inserted", symbol, total)
    return total


def import_v1_data(db) -> int:
    """Import candle data from v1 SQLite database if it exists.

    The v1 candles table has the same schema: (symbol, ts, open, high, low, close, volume).
    Returns total rows inserted.
    """
    v1_db_path = V1_DATA_DIR / "moonshot.db"
    if not v1_db_path.exists():
        log.info("import_v1_data: v1 database not found at %s, skipping", v1_db_path)
        return 0

    try:
        v1_conn = sqlite3.connect(str(v1_db_path))
        v1_conn.row_factory = sqlite3.Row

        # v1 candles: (symbol, ts, open, high, low, close, volume) — same as v2
        cursor = v1_conn.execute(
            "SELECT symbol, ts, open, high, low, close, volume FROM candles"
        )
        batch = []
        total = 0
        batch_size = 5000

        for row in cursor:
            batch.append((row["symbol"], row["ts"], row["open"], row["high"],
                          row["low"], row["close"], row["volume"]))
            if len(batch) >= batch_size:
                db.executemany(
                    "INSERT OR IGNORE INTO candles (symbol, ts, open, high, low, close, volume) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                total += len(batch)
                batch.clear()

        if batch:
            db.executemany(
                "INSERT OR IGNORE INTO candles (symbol, ts, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
            total += len(batch)

        db.commit()

        # Also import coins that we haven't seen yet
        v1_coins = v1_conn.execute("SELECT symbol, first_seen_ts FROM coins").fetchall()
        now_ms = int(time.time() * 1000)
        db.executemany(
            "INSERT OR IGNORE INTO coins (symbol, first_seen_ts) VALUES (?, ?)",
            [(r["symbol"], r["first_seen_ts"] or now_ms) for r in v1_coins],
        )

        # Update oldest_candle_ts for imported symbols
        symbols = db.execute(
            "SELECT DISTINCT symbol FROM candles"
        ).fetchall()
        for s in symbols:
            oldest = db.execute(
                "SELECT MIN(ts) as min_ts FROM candles WHERE symbol = ?",
                (s["symbol"],),
            ).fetchone()
            if oldest and oldest["min_ts"]:
                db.execute(
                    "UPDATE coins SET oldest_candle_ts = ? WHERE symbol = ? "
                    "AND (oldest_candle_ts IS NULL OR oldest_candle_ts > ?)",
                    (oldest["min_ts"], s["symbol"], oldest["min_ts"]),
                )

        db.commit()
        v1_conn.close()
        log.info("import_v1_data: imported %d candle rows from v1", total)
        return total

    except Exception as e:
        log.warning("import_v1_data: error importing v1 data: %s", e)
        return 0
