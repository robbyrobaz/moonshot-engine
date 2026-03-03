"""Moonshot v2 — BTC-based market regime classification."""

import time

from config import BEAR_THRESHOLD, BULL_THRESHOLD, log


def classify_regime(db, ts_ms: int = None) -> str:
    """Classify current market regime based on BTC price action.

    Returns 'bull', 'neutral', or 'bear'.

    Rules:
    - btc_30d_return < -20% (BEAR_THRESHOLD): 'bear' (pause ALL long entries)
    - btc_30d_return > +20% (BULL_THRESHOLD): 'bull' (reduce short entries)
    - else: 'neutral'
    """
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)

    # BTC 30-day return: compare current price to price ~30 days ago
    # 30 days at 4h bars = 180 bars, so look back ~30d in ms
    thirty_days_ms = 30 * 24 * 3600 * 1000
    lookback_ts = ts_ms - thirty_days_ms

    btc_symbol = "BTC-USDT"

    # Current BTC price (most recent candle at or before ts_ms)
    current = db.execute(
        "SELECT close FROM candles WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (btc_symbol, ts_ms),
    ).fetchone()

    # BTC price ~30 days ago (closest candle to lookback_ts)
    past = db.execute(
        "SELECT close FROM candles WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (btc_symbol, lookback_ts),
    ).fetchone()

    if current is None or past is None:
        log.warning("classify_regime: insufficient BTC candle data, defaulting to 'neutral'")
        return "neutral"

    current_price = float(current["close"])
    past_price = float(past["close"])

    if past_price == 0:
        return "neutral"

    btc_30d_return = (current_price - past_price) / past_price

    if btc_30d_return < BEAR_THRESHOLD:
        regime = "bear"
    elif btc_30d_return > BULL_THRESHOLD:
        regime = "bull"
    else:
        regime = "neutral"

    log.info("classify_regime: BTC 30d return=%.2f%%, regime=%s",
             btc_30d_return * 100, regime)
    return regime


def compute_market_breadth(db, ts_ms: int = None) -> float:
    """Compute market breadth: % of top-20 coins by OI above their 30d SMA.

    Returns a float between 0.0 and 1.0.
    """
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)

    thirty_days_ms = 30 * 24 * 3600 * 1000

    # Find top-20 coins by most recent OI
    top_coins = db.execute(
        """SELECT symbol, oi_usd FROM open_interest
           WHERE ts = (SELECT MAX(ts) FROM open_interest WHERE ts <= ?)
           ORDER BY oi_usd DESC
           LIMIT 20""",
        (ts_ms,),
    ).fetchall()

    if not top_coins:
        log.warning("compute_market_breadth: no OI data, returning 0.5")
        return 0.5

    above_sma = 0
    total = 0

    for coin in top_coins:
        symbol = coin["symbol"]

        # Current price
        current = db.execute(
            "SELECT close FROM candles WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
            (symbol, ts_ms),
        ).fetchone()
        if current is None:
            continue

        # 30d SMA: average close price over last 30 days
        lookback_ts = ts_ms - thirty_days_ms
        sma_row = db.execute(
            "SELECT AVG(close) as sma FROM candles WHERE symbol = ? AND ts > ? AND ts <= ?",
            (symbol, lookback_ts, ts_ms),
        ).fetchone()
        if sma_row is None or sma_row["sma"] is None:
            continue

        total += 1
        if float(current["close"]) > float(sma_row["sma"]):
            above_sma += 1

    breadth = above_sma / total if total > 0 else 0.5
    log.info("compute_market_breadth: %d/%d coins above 30d SMA = %.2f",
             above_sma, total, breadth)
    return breadth
