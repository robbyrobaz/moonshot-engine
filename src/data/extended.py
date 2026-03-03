"""Moonshot v2 — Extended market data: funding, OI, mark prices, tickers."""

import time
import requests
from config import BLOFIN_BASE_URL, BLOFIN_RATE_LIMIT_RPS, log


def _rate_sleep(delay: float, index: int, total: int):
    """Sleep for rate limiting unless this is the last item."""
    if index < total - 1:
        time.sleep(delay)


def fetch_funding_rates(db, symbols: list[str]) -> int:
    """Fetch funding rate history for each symbol. Returns total rows inserted."""
    url = f"{BLOFIN_BASE_URL}/api/v1/market/funding-rate-history"
    delay = 1.0 / BLOFIN_RATE_LIMIT_RPS
    total = 0

    for i, symbol in enumerate(symbols):
        try:
            resp = requests.get(
                url,
                params={"instId": symbol, "limit": "90"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])

            rows = []
            for entry in data:
                try:
                    ts = int(entry["fundingTime"])
                    rate = float(entry["fundingRate"])
                    rows.append((symbol, ts, rate))
                except (KeyError, ValueError, TypeError):
                    continue

            if rows:
                db.executemany(
                    "INSERT OR IGNORE INTO funding_rates (symbol, ts, funding_rate) "
                    "VALUES (?, ?, ?)",
                    rows,
                )
                total += len(rows)

        except Exception as e:
            log.warning("fetch_funding_rates: %s error: %s", symbol, e)

        _rate_sleep(delay, i, len(symbols))

    db.commit()
    log.info("fetch_funding_rates: %d rows inserted", total)
    return total


def fetch_open_interest(db, symbols: list[str]) -> int:
    """Fetch current open interest snapshot for each symbol."""
    url = f"{BLOFIN_BASE_URL}/api/v1/market/open-interest"
    delay = 1.0 / BLOFIN_RATE_LIMIT_RPS
    now_ms = int(time.time() * 1000)
    total = 0

    for i, symbol in enumerate(symbols):
        try:
            resp = requests.get(
                url,
                params={"instId": symbol, "instType": "SWAP"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])

            for entry in data:
                try:
                    oi_contracts = float(entry.get("oi", 0))
                    oi_usd = float(entry.get("oiUsd", 0))
                    db.execute(
                        "INSERT OR IGNORE INTO open_interest "
                        "(symbol, ts, oi_contracts, oi_usd) VALUES (?, ?, ?, ?)",
                        (symbol, now_ms, oi_contracts, oi_usd),
                    )
                    total += 1
                except (ValueError, TypeError):
                    continue

        except Exception as e:
            log.warning("fetch_open_interest: %s error: %s", symbol, e)

        _rate_sleep(delay, i, len(symbols))

    db.commit()
    log.info("fetch_open_interest: %d rows inserted", total)
    return total


def fetch_mark_prices(db, symbols: list[str]) -> int:
    """Fetch current mark/index prices for each symbol."""
    url = f"{BLOFIN_BASE_URL}/api/v1/market/mark-price"
    delay = 1.0 / BLOFIN_RATE_LIMIT_RPS
    now_ms = int(time.time() * 1000)
    total = 0

    for i, symbol in enumerate(symbols):
        try:
            resp = requests.get(
                url,
                params={"instId": symbol, "instType": "SWAP"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])

            for entry in data:
                try:
                    mark = float(entry.get("markPrice", 0))
                    index = float(entry.get("indexPrice", 0))
                    db.execute(
                        "INSERT OR IGNORE INTO mark_prices "
                        "(symbol, ts, mark_price, index_price) VALUES (?, ?, ?, ?)",
                        (symbol, now_ms, mark, index),
                    )
                    total += 1
                except (ValueError, TypeError):
                    continue

        except Exception as e:
            log.warning("fetch_mark_prices: %s error: %s", symbol, e)

        _rate_sleep(delay, i, len(symbols))

    db.commit()
    log.info("fetch_mark_prices: %d rows inserted", total)
    return total


def fetch_tickers(db) -> int:
    """Fetch 24h tickers for all SWAP instruments in a single call."""
    url = f"{BLOFIN_BASE_URL}/api/v1/market/tickers"
    now_ms = int(time.time() * 1000)
    total = 0

    try:
        resp = requests.get(url, params={"instType": "SWAP"}, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        rows = []
        for t in data:
            try:
                symbol = t.get("instId", "")
                if not symbol or not symbol.endswith("-USDT"):
                    continue
                high_24h = float(t.get("high24h", 0))
                low_24h = float(t.get("low24h", 0))
                vol_24h = float(t.get("volCcy24h", 0))
                open_24h = float(t.get("open24h", 0))
                last_price = float(t.get("last", 0))
                change_pct = ((last_price - open_24h) / open_24h * 100) if open_24h else 0.0
                rows.append((symbol, now_ms, high_24h, low_24h, vol_24h, change_pct))
            except (ValueError, TypeError):
                continue

        if rows:
            db.executemany(
                "INSERT OR IGNORE INTO tickers_24h "
                "(symbol, ts, high_24h, low_24h, vol_24h, price_change_pct) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            total = len(rows)

    except Exception as e:
        log.warning("fetch_tickers: error: %s", e)

    db.commit()
    log.info("fetch_tickers: %d rows inserted", total)
    return total


def fetch_all_extended(db, symbols: list[str]):
    """Master function: fetch all extended market data for a cycle."""
    log.info("fetch_all_extended: starting for %d symbols", len(symbols))
    fetch_funding_rates(db, symbols)
    fetch_open_interest(db, symbols)
    fetch_mark_prices(db, symbols)
    fetch_tickers(db)
    log.info("fetch_all_extended: complete")
