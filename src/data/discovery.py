"""Moonshot v2 — Coin discovery via Blofin instruments endpoint."""

import time
import requests
from config import BLOFIN_BASE_URL, log


def discover_coins(db) -> list[str]:
    """Fetch all active USDT swap pairs from Blofin and upsert into coins table.

    Returns list of active symbols like ["BTC-USDT", "ETH-USDT", ...].
    """
    url = f"{BLOFIN_BASE_URL}/api/v1/market/instruments"
    params = {"instType": "SWAP"}
    now_ms = int(time.time() * 1000)

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("discover_coins: API error: %s", e)
        # Fall back to whatever is already in the DB
        rows = db.execute("SELECT symbol FROM coins WHERE is_active = 1").fetchall()
        return [r["symbol"] for r in rows]

    instruments = data.get("data", [])
    active_symbols = []

    for inst in instruments:
        if inst.get("quoteCurrency") != "USDT":
            continue
        if inst.get("state") != "live":
            continue
        symbol = inst.get("instId", "")
        if not symbol:
            continue
        active_symbols.append(symbol)

    if not active_symbols:
        log.warning("discover_coins: no active USDT swaps found")
        rows = db.execute("SELECT symbol FROM coins WHERE is_active = 1").fetchall()
        return [r["symbol"] for r in rows]

    # Upsert active coins
    db.executemany(
        "INSERT OR IGNORE INTO coins (symbol, first_seen_ts) VALUES (?, ?)",
        [(s, now_ms) for s in active_symbols],
    )

    # Mark all coins active/inactive based on current listing
    active_set = set(active_symbols)
    all_coins = db.execute("SELECT symbol FROM coins").fetchall()
    for row in all_coins:
        is_active = 1 if row["symbol"] in active_set else 0
        db.execute(
            "UPDATE coins SET is_active = ? WHERE symbol = ?",
            (is_active, row["symbol"]),
        )

    db.commit()
    log.info("discover_coins: %d active USDT swap pairs", len(active_symbols))
    return active_symbols
