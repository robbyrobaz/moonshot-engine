"""Moonshot v2 — Feature Computation Engine.

THE SINGLE MOST IMPORTANT FILE. compute_features() is called identically for
training, live scoring, and exit re-scoring. Every feature compute function is
deterministic: same (symbol, ts_ms, db) -> same output.

Missing data -> neutral fill. Never crashes.
"""

import hashlib
import json
import math
import time
from functools import lru_cache

from config import log
from src.features.registry import FEATURE_REGISTRY


# ── Helpers ─────────────────────────────────────────────────────────────────

def _load_candles(db, symbol, ts_ms, n_bars):
    """Load up to n_bars of candles ending at or before ts_ms, ordered oldest-first."""
    rows = db.execute(
        "SELECT ts, open, high, low, close, volume FROM candles "
        "WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT ?",
        (symbol, ts_ms, n_bars),
    ).fetchall()
    return list(reversed(rows))  # oldest first


def _load_candles_cached(db, symbol, ts_ms, n_bars, _cache={}):
    """Cached candle loader. Cache keyed on (symbol, ts_ms, n_bars).

    Cache is per-call-batch: cleared at the start of compute_all_features.
    """
    key = (symbol, ts_ms, n_bars)
    if key not in _cache:
        _cache[key] = _load_candles(db, symbol, ts_ms, n_bars)
    return _cache[key]


def _clear_candle_cache():
    """Clear the mutable-default cache."""
    _load_candles_cached.__defaults__[0].clear()


def _linreg_slope(values):
    """Simple linear regression slope over evenly-spaced values."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _percentile_rank(value, history):
    """Percentile rank of value within history list (0-100)."""
    if not history:
        return 50.0
    count_below = sum(1 for v in history if v < value)
    return (count_below / len(history)) * 100.0


def _safe_div(a, b, default=0.0):
    """Safe division, returns default if b is zero or None."""
    if b is None or b == 0:
        return default
    return a / b


def _atr_series(candles):
    """Compute ATR values (True Range) for a candle series. Returns list of TR values."""
    trs = []
    for i, c in enumerate(candles):
        high, low, close = c["high"], c["low"], c["close"]
        if i == 0:
            trs.append(high - low)
        else:
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
    return trs


# ── BTC cache (shared across all symbols in a batch) ───────────────────────

_btc_candle_cache = {}


def _get_btc_candles(db, ts_ms, n_bars):
    """Load BTC candles with batch-level caching."""
    key = (ts_ms, n_bars)
    if key not in _btc_candle_cache:
        _btc_candle_cache[key] = _load_candles(db, "BTC-USDT", ts_ms, n_bars)
    return _btc_candle_cache[key]


def _clear_btc_cache():
    _btc_candle_cache.clear()


# ═══════════════════════════════════════════════════════════════════════════
# CORE FEATURES — Price Action
# ═══════════════════════════════════════════════════════════════════════════

def _compute_price_vs_52w_high(db, symbol, ts_ms, candles):
    """Current close / 52-week high (0-1)."""
    if not candles:
        return None
    close = candles[-1]["close"]
    high_52w = max(c["high"] for c in candles)
    return _safe_div(close, high_52w, 0.5)


def _compute_price_vs_52w_low(db, symbol, ts_ms, candles):
    """Current close / 52-week low."""
    if not candles:
        return None
    close = candles[-1]["close"]
    low_52w = min(c["low"] for c in candles)
    return _safe_div(close, low_52w, 1.0)


def _compute_momentum_4w(db, symbol, ts_ms, candles):
    """28-day return clipped to [-1, 1]. 4H bars: 28d = 168 bars."""
    if len(candles) < 2:
        return None
    close_now = candles[-1]["close"]
    # 28d ago = 168 bars back
    idx = max(0, len(candles) - 168)
    close_then = candles[idx]["close"]
    ret = _safe_div(close_now - close_then, close_then, 0.0)
    return max(-1.0, min(1.0, ret))


def _compute_momentum_8w(db, symbol, ts_ms, candles):
    """56-day return clipped to [-1, 1]. 4H bars: 56d = 336 bars."""
    if len(candles) < 2:
        return None
    close_now = candles[-1]["close"]
    idx = max(0, len(candles) - 336)
    close_then = candles[idx]["close"]
    ret = _safe_div(close_now - close_then, close_then, 0.0)
    return max(-1.0, min(1.0, ret))


def _compute_bb_squeeze_pct(db, symbol, ts_ms, candles):
    """BB width / 20-period SMA of BB width."""
    if len(candles) < 20:
        return None
    # Compute current BB width
    closes_20 = [c["close"] for c in candles[-20:]]
    sma = sum(closes_20) / 20
    std = (sum((c - sma) ** 2 for c in closes_20) / 20) ** 0.5
    bb_width = 2 * 2 * std  # 2 standard deviations each side

    # Compute historical BB widths for SMA of widths
    widths = []
    for end in range(20, len(candles) + 1):
        segment = [c["close"] for c in candles[end - 20:end]]
        seg_sma = sum(segment) / 20
        seg_std = (sum((v - seg_sma) ** 2 for v in segment) / 20) ** 0.5
        widths.append(2 * 2 * seg_std)

    if not widths:
        return None
    avg_width = sum(widths[-20:]) / len(widths[-20:])
    return _safe_div(bb_width, avg_width, 1.0)


def _compute_bb_position(db, symbol, ts_ms, candles):
    """(close - lower_band) / (upper_band - lower_band), clipped [0, 1]."""
    if len(candles) < 20:
        return None
    closes_20 = [c["close"] for c in candles[-20:]]
    sma = sum(closes_20) / 20
    std = (sum((c - sma) ** 2 for c in closes_20) / 20) ** 0.5
    upper = sma + 2 * std
    lower = sma - 2 * std
    close = candles[-1]["close"]
    pos = _safe_div(close - lower, upper - lower, 0.5)
    return max(0.0, min(1.0, pos))


# ═══════════════════════════════════════════════════════════════════════════
# CORE FEATURES — Volume
# ═══════════════════════════════════════════════════════════════════════════

def _compute_volume_ratio_7d(db, symbol, ts_ms, candles):
    """7d avg vol / 30d avg vol. 4H: 7d=42 bars, 30d=180 bars."""
    if len(candles) < 42:
        return None
    vols_7d = [c["volume"] for c in candles[-42:]]
    vols_30d = [c["volume"] for c in candles[-180:]]
    avg_7d = sum(vols_7d) / len(vols_7d)
    avg_30d = sum(vols_30d) / len(vols_30d)
    return _safe_div(avg_7d, avg_30d, 1.0)


def _compute_volume_ratio_3d(db, symbol, ts_ms, candles):
    """3d avg vol / 14d avg vol. 4H: 3d=18 bars, 14d=84 bars."""
    if len(candles) < 18:
        return None
    vols_3d = [c["volume"] for c in candles[-18:]]
    vols_14d = [c["volume"] for c in candles[-84:]]
    avg_3d = sum(vols_3d) / len(vols_3d)
    avg_14d = sum(vols_14d) / len(vols_14d)
    return _safe_div(avg_3d, avg_14d, 1.0)


def _compute_obv_slope(db, symbol, ts_ms, candles):
    """OBV 14-period linear regression slope, normalized by price."""
    if len(candles) < 15:
        return None
    # Compute OBV for last 14+1 bars
    segment = candles[-(14 + 1):]
    obv = [0.0]
    for i in range(1, len(segment)):
        if segment[i]["close"] > segment[i - 1]["close"]:
            obv.append(obv[-1] + segment[i]["volume"])
        elif segment[i]["close"] < segment[i - 1]["close"]:
            obv.append(obv[-1] - segment[i]["volume"])
        else:
            obv.append(obv[-1])
    slope = _linreg_slope(obv[-14:])
    price = candles[-1]["close"]
    return _safe_div(slope, price, 0.0)


def _compute_volume_spike(db, symbol, ts_ms, candles):
    """Current bar volume / 14-period average volume."""
    if len(candles) < 14:
        return None
    current_vol = candles[-1]["volume"]
    avg_vol = sum(c["volume"] for c in candles[-14:]) / 14
    return _safe_div(current_vol, avg_vol, 1.0)


def _compute_volume_trend(db, symbol, ts_ms, candles):
    """Linear regression slope of volume over 30 bars, normalized."""
    if len(candles) < 30:
        return None
    vols = [c["volume"] for c in candles[-30:]]
    slope = _linreg_slope(vols)
    avg_vol = sum(vols) / len(vols)
    return _safe_div(slope, avg_vol, 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# CORE FEATURES — Volatility
# ═══════════════════════════════════════════════════════════════════════════

def _compute_atr_percentile(db, symbol, ts_ms, candles):
    """Current ATR vs 90d ATR history as percentile 0-100. 90d = 540 bars."""
    if len(candles) < 15:
        return None
    trs = _atr_series(candles)
    # Current ATR = 14-period average of TR
    current_atr = sum(trs[-14:]) / 14
    # Historical ATR values (rolling 14-period)
    atr_history = []
    for end in range(14, len(trs) + 1):
        atr_history.append(sum(trs[end - 14:end]) / 14)
    return _percentile_rank(current_atr, atr_history)


def _compute_atr_compression(db, symbol, ts_ms, candles):
    """ATR 7d avg / ATR 28d avg. 4H: 7d=42, 28d=168."""
    if len(candles) < 15:
        return None
    trs = _atr_series(candles)
    # Rolling 14-period ATR values
    atr_vals = []
    for end in range(14, len(trs) + 1):
        atr_vals.append(sum(trs[end - 14:end]) / 14)
    if len(atr_vals) < 42:
        return None
    avg_7d = sum(atr_vals[-42:]) / 42
    avg_28d = sum(atr_vals[-168:]) / len(atr_vals[-168:])
    return _safe_div(avg_7d, avg_28d, 1.0)


def _compute_high_low_range_pct(db, symbol, ts_ms, candles):
    """(high - low) / low for the current bar."""
    if not candles:
        return None
    bar = candles[-1]
    return _safe_div(bar["high"] - bar["low"], bar["low"], 0.02)


def _compute_realized_vol_ratio(db, symbol, ts_ms, candles):
    """7d realized vol / 30d realized vol."""
    if len(candles) < 43:
        return None
    # Log returns
    returns = []
    for i in range(1, len(candles)):
        prev_c = candles[i - 1]["close"]
        if prev_c > 0:
            returns.append(math.log(candles[i]["close"] / prev_c))
        else:
            returns.append(0.0)

    if len(returns) < 42:
        return None
    # 7d realized vol (std of last 42 returns)
    r7 = returns[-42:]
    mean7 = sum(r7) / len(r7)
    vol_7d = (sum((r - mean7) ** 2 for r in r7) / len(r7)) ** 0.5

    # 30d realized vol (std of last 180 returns)
    r30 = returns[-180:]
    mean30 = sum(r30) / len(r30)
    vol_30d = (sum((r - mean30) ** 2 for r in r30) / len(r30)) ** 0.5

    return _safe_div(vol_7d, vol_30d, 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# CORE FEATURES — Price Structure
# ═══════════════════════════════════════════════════════════════════════════

def _compute_distance_from_support(db, symbol, ts_ms, candles):
    """% distance from lowest low in past 30d. 4H: 30d=180 bars."""
    if len(candles) < 2:
        return None
    window = candles[-180:]
    support = min(c["low"] for c in window)
    close = candles[-1]["close"]
    return _safe_div(close - support, support, 0.05)


def _compute_distance_from_resistance(db, symbol, ts_ms, candles):
    """% distance below highest high in past 30d."""
    if len(candles) < 2:
        return None
    window = candles[-180:]
    resistance = max(c["high"] for c in window)
    close = candles[-1]["close"]
    return _safe_div(resistance - close, close, 0.05)


def _compute_consec_down_bars(db, symbol, ts_ms, candles):
    """Count of consecutive bars closing lower (from most recent bar backwards)."""
    if len(candles) < 2:
        return None
    count = 0
    for i in range(len(candles) - 1, 0, -1):
        if candles[i]["close"] < candles[i - 1]["close"]:
            count += 1
        else:
            break
    return count


def _compute_consec_up_bars(db, symbol, ts_ms, candles):
    """Count of consecutive bars closing higher (from most recent bar backwards)."""
    if len(candles) < 2:
        return None
    count = 0
    for i in range(len(candles) - 1, 0, -1):
        if candles[i]["close"] > candles[i - 1]["close"]:
            count += 1
        else:
            break
    return count


def _compute_higher_highs(db, symbol, ts_ms, candles):
    """Count of higher-highs in past 14 bars."""
    if len(candles) < 15:
        return None
    segment = candles[-15:]
    count = 0
    for i in range(1, len(segment)):
        if segment[i]["high"] > segment[i - 1]["high"]:
            count += 1
    return count


# ═══════════════════════════════════════════════════════════════════════════
# CORE FEATURES — Market Regime (BTC-based)
# ═══════════════════════════════════════════════════════════════════════════

def _compute_btc_30d_return(db, symbol, ts_ms, candles):
    """BTC 30d return. 4H: 30d=180 bars."""
    btc = _get_btc_candles(db, ts_ms, 180)
    if len(btc) < 2:
        return None
    close_now = btc[-1]["close"]
    idx = max(0, len(btc) - 180)
    close_then = btc[idx]["close"]
    return _safe_div(close_now - close_then, close_then, 0.0)


def _compute_btc_vol_percentile(db, symbol, ts_ms, candles):
    """BTC ATR percentile over 90d. 4H: 90d=540 bars."""
    btc = _get_btc_candles(db, ts_ms, 540)
    if len(btc) < 15:
        return None
    trs = _atr_series(btc)
    current_atr = sum(trs[-14:]) / 14
    atr_history = []
    for end in range(14, len(trs) + 1):
        atr_history.append(sum(trs[end - 14:end]) / 14)
    return _percentile_rank(current_atr, atr_history)


def _compute_market_breadth(db, symbol, ts_ms, candles):
    """% of top-20 coins by OI that are above their 30d SMA."""
    # Get top 20 coins by latest OI
    top_coins = db.execute(
        "SELECT symbol, oi_usd FROM open_interest "
        "WHERE ts = (SELECT MAX(ts) FROM open_interest WHERE ts <= ?) "
        "ORDER BY oi_usd DESC LIMIT 20",
        (ts_ms,),
    ).fetchall()

    if not top_coins:
        return None

    above_sma_count = 0
    total = 0
    for coin_row in top_coins:
        coin_sym = coin_row["symbol"]
        coin_candles = _load_candles_cached(db, coin_sym, ts_ms, 180)
        if len(coin_candles) < 30:
            continue
        total += 1
        close = coin_candles[-1]["close"]
        sma_30d = sum(c["close"] for c in coin_candles[-180:]) / len(coin_candles[-180:])
        if close > sma_30d:
            above_sma_count += 1

    if total == 0:
        return None
    return above_sma_count / total


# ═══════════════════════════════════════════════════════════════════════════
# CORE FEATURES — Coin Metadata
# ═══════════════════════════════════════════════════════════════════════════

def _compute_days_since_listing(db, symbol, ts_ms, candles):
    """Days since listing from coins table, capped at 730."""
    row = db.execute(
        "SELECT days_since_listing FROM coins WHERE symbol = ?", (symbol,)
    ).fetchone()
    if row is None or row["days_since_listing"] is None:
        return None
    return min(row["days_since_listing"], 730)


def _compute_is_new_listing(db, symbol, ts_ms, candles):
    """1 if days_since_listing < 30, else 0."""
    days = _compute_days_since_listing(db, symbol, ts_ms, candles)
    if days is None:
        return None
    return 1 if days < 30 else 0


# ═══════════════════════════════════════════════════════════════════════════
# EXTENDED FEATURES — Funding Rate
# ═══════════════════════════════════════════════════════════════════════════

def _compute_funding_rate_current(db, symbol, ts_ms, candles):
    """Latest funding rate."""
    row = db.execute(
        "SELECT funding_rate FROM funding_rates "
        "WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()
    if row is None:
        return None
    return row["funding_rate"]


def _compute_funding_rate_7d_avg(db, symbol, ts_ms, candles):
    """Average of last 21 funding periods (8h * 21 = 7d)."""
    rows = db.execute(
        "SELECT funding_rate FROM funding_rates "
        "WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 21",
        (symbol, ts_ms),
    ).fetchall()
    if not rows:
        return None
    return sum(r["funding_rate"] for r in rows) / len(rows)


def _compute_funding_rate_extreme(db, symbol, ts_ms, candles):
    """1 if abs(current) > 2x 30d avg, else 0."""
    current = _compute_funding_rate_current(db, symbol, ts_ms, candles)
    if current is None:
        return None
    # 30d of funding = ~90 periods (3 per day * 30)
    rows = db.execute(
        "SELECT funding_rate FROM funding_rates "
        "WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 90",
        (symbol, ts_ms),
    ).fetchall()
    if not rows:
        return None
    avg_30d = sum(abs(r["funding_rate"]) for r in rows) / len(rows)
    return 1 if abs(current) > 2 * avg_30d else 0


# ═══════════════════════════════════════════════════════════════════════════
# EXTENDED FEATURES — Open Interest
# ═══════════════════════════════════════════════════════════════════════════

def _compute_oi_change_24h(db, symbol, ts_ms, candles):
    """(latest OI - OI 24h ago) / 30d avg OI."""
    ms_24h = 24 * 3600 * 1000
    ms_30d = 30 * 24 * 3600 * 1000

    latest = db.execute(
        "SELECT oi_usd FROM open_interest WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()
    ago_24h = db.execute(
        "SELECT oi_usd FROM open_interest WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms - ms_24h),
    ).fetchone()
    avg_rows = db.execute(
        "SELECT AVG(oi_usd) as avg_oi FROM open_interest "
        "WHERE symbol = ? AND ts > ? AND ts <= ?",
        (symbol, ts_ms - ms_30d, ts_ms),
    ).fetchone()

    if not latest or not ago_24h or not avg_rows or avg_rows["avg_oi"] is None:
        return None
    return _safe_div(latest["oi_usd"] - ago_24h["oi_usd"], avg_rows["avg_oi"], 0.0)


def _compute_oi_change_7d(db, symbol, ts_ms, candles):
    """(latest OI - OI 7d ago) / 30d avg OI."""
    ms_7d = 7 * 24 * 3600 * 1000
    ms_30d = 30 * 24 * 3600 * 1000

    latest = db.execute(
        "SELECT oi_usd FROM open_interest WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()
    ago_7d = db.execute(
        "SELECT oi_usd FROM open_interest WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms - ms_7d),
    ).fetchone()
    avg_rows = db.execute(
        "SELECT AVG(oi_usd) as avg_oi FROM open_interest "
        "WHERE symbol = ? AND ts > ? AND ts <= ?",
        (symbol, ts_ms - ms_30d, ts_ms),
    ).fetchone()

    if not latest or not ago_7d or not avg_rows or avg_rows["avg_oi"] is None:
        return None
    return _safe_div(latest["oi_usd"] - ago_7d["oi_usd"], avg_rows["avg_oi"], 0.0)


def _compute_oi_price_divergence(db, symbol, ts_ms, candles):
    """sign(oi_change_7d) * sign(price_change_7d). 1=aligned, -1=diverged."""
    oi_chg = _compute_oi_change_7d(db, symbol, ts_ms, candles)
    if oi_chg is None or len(candles) < 42:
        return None
    close_now = candles[-1]["close"]
    close_7d = candles[-42]["close"]  # 7d = 42 bars at 4H
    price_chg = close_now - close_7d
    if oi_chg == 0 or price_chg == 0:
        return 0
    oi_sign = 1 if oi_chg > 0 else -1
    price_sign = 1 if price_chg > 0 else -1
    return oi_sign * price_sign


def _compute_oi_percentile_90d(db, symbol, ts_ms, candles):
    """Current OI vs 90d history percentile."""
    ms_90d = 90 * 24 * 3600 * 1000
    latest = db.execute(
        "SELECT oi_usd FROM open_interest WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()
    if not latest:
        return None
    history = db.execute(
        "SELECT oi_usd FROM open_interest WHERE symbol = ? AND ts > ? AND ts <= ?",
        (symbol, ts_ms - ms_90d, ts_ms),
    ).fetchall()
    if not history:
        return None
    return _percentile_rank(latest["oi_usd"], [r["oi_usd"] for r in history])


# ═══════════════════════════════════════════════════════════════════════════
# EXTENDED FEATURES — Mark Price
# ═══════════════════════════════════════════════════════════════════════════

def _compute_mark_index_spread(db, symbol, ts_ms, candles):
    """(mark - index) / index."""
    row = db.execute(
        "SELECT mark_price, index_price FROM mark_prices "
        "WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()
    if not row or row["index_price"] is None or row["index_price"] == 0:
        return None
    return (row["mark_price"] - row["index_price"]) / row["index_price"]


# ═══════════════════════════════════════════════════════════════════════════
# EXTENDED FEATURES — Ticker
# ═══════════════════════════════════════════════════════════════════════════

def _get_latest_ticker(db, symbol, ts_ms):
    """Get latest ticker_24h row at or before ts_ms."""
    return db.execute(
        "SELECT * FROM tickers_24h WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms),
    ).fetchone()


def _compute_price_vs_24h_high(db, symbol, ts_ms, candles):
    """Current close / 24h high from tickers_24h."""
    ticker = _get_latest_ticker(db, symbol, ts_ms)
    if not ticker or not candles:
        return None
    return _safe_div(candles[-1]["close"], ticker["high_24h"], 0.95)


def _compute_price_vs_24h_low(db, symbol, ts_ms, candles):
    """Current close / 24h low from tickers_24h."""
    ticker = _get_latest_ticker(db, symbol, ts_ms)
    if not ticker or not candles:
        return None
    return _safe_div(candles[-1]["close"], ticker["low_24h"], 1.05)


def _compute_vol_24h_vs_7d_avg(db, symbol, ts_ms, candles):
    """Today's 24h vol / 7d avg 24h vol."""
    ms_7d = 7 * 24 * 3600 * 1000
    latest = _get_latest_ticker(db, symbol, ts_ms)
    if not latest:
        return None
    rows = db.execute(
        "SELECT vol_24h FROM tickers_24h WHERE symbol = ? AND ts > ? AND ts <= ?",
        (symbol, ts_ms - ms_7d, ts_ms),
    ).fetchall()
    if not rows:
        return None
    avg_7d = sum(r["vol_24h"] for r in rows) / len(rows)
    return _safe_div(latest["vol_24h"], avg_7d, 1.0)


def _compute_price_change_24h_pct(db, symbol, ts_ms, candles):
    """Price change % from tickers_24h."""
    ticker = _get_latest_ticker(db, symbol, ts_ms)
    if not ticker or ticker["price_change_pct"] is None:
        return None
    return ticker["price_change_pct"]


# ═══════════════════════════════════════════════════════════════════════════
# SOCIAL FEATURES
# ═══════════════════════════════════════════════════════════════════════════

def _compute_fear_greed_score(db, symbol, ts_ms, candles):
    """Fear & Greed index score from social_events (global, not per-symbol)."""
    row = db.execute(
        "SELECT numeric_value FROM social_events "
        "WHERE source = 'fear_greed' AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (ts_ms,),
    ).fetchone()
    if not row:
        return None
    return row["numeric_value"]


def _compute_fear_greed_7d_change(db, symbol, ts_ms, candles):
    """Change in Fear & Greed over 7d."""
    ms_7d = 7 * 24 * 3600 * 1000
    current = _compute_fear_greed_score(db, symbol, ts_ms, candles)
    past = db.execute(
        "SELECT numeric_value FROM social_events "
        "WHERE source = 'fear_greed' AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (ts_ms - ms_7d,),
    ).fetchone()
    if current is None or not past:
        return None
    return current - past["numeric_value"]


def _compute_is_coingecko_trending(db, symbol, ts_ms, candles):
    """1 if coin is on CoinGecko trending list now."""
    ms_6h = 6 * 3600 * 1000  # trending data refreshes ~every few hours
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM social_events "
        "WHERE symbol = ? AND source = 'coingecko_trending' AND ts > ?",
        (symbol, ts_ms - ms_6h),
    ).fetchone()
    return 1 if row and row["cnt"] > 0 else 0


def _compute_trending_rank(db, symbol, ts_ms, candles):
    """Trending rank 1-15, 0 if not trending."""
    ms_6h = 6 * 3600 * 1000
    row = db.execute(
        "SELECT numeric_value FROM social_events "
        "WHERE symbol = ? AND source = 'coingecko_trending' AND ts > ? "
        "ORDER BY ts DESC LIMIT 1",
        (symbol, ts_ms - ms_6h),
    ).fetchone()
    if not row or row["numeric_value"] is None:
        return 0
    return int(row["numeric_value"])


def _compute_hours_on_trending(db, symbol, ts_ms, candles):
    """Hours coin has been on trending list (consecutive recent entries)."""
    ms_48h = 48 * 3600 * 1000
    rows = db.execute(
        "SELECT ts FROM social_events "
        "WHERE symbol = ? AND source = 'coingecko_trending' AND ts > ? "
        "ORDER BY ts DESC",
        (symbol, ts_ms - ms_48h),
    ).fetchall()
    if not rows:
        return 0
    # Count hours spanned by the trending entries
    earliest = rows[-1]["ts"]
    latest = rows[0]["ts"]
    return max(1, int((latest - earliest) / (3600 * 1000)) + 1)


def _compute_news_mentions_24h(db, symbol, ts_ms, candles):
    """Count of news mentions in last 24h."""
    ms_24h = 24 * 3600 * 1000
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM social_events "
        "WHERE symbol = ? AND source IN ('cointelegraph', 'decrypt', 'theblock') "
        "AND ts > ?",
        (symbol, ts_ms - ms_24h),
    ).fetchone()
    return row["cnt"] if row else 0


def _compute_news_mentions_7d_avg(db, symbol, ts_ms, candles):
    """7d daily average of news mentions."""
    ms_7d = 7 * 24 * 3600 * 1000
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM social_events "
        "WHERE symbol = ? AND source IN ('cointelegraph', 'decrypt', 'theblock') "
        "AND ts > ?",
        (symbol, ts_ms - ms_7d),
    ).fetchone()
    total = row["cnt"] if row else 0
    return total / 7.0


def _compute_news_velocity_ratio(db, symbol, ts_ms, candles):
    """mentions_24h / max(mentions_7d_avg, 1)."""
    m24 = _compute_news_mentions_24h(db, symbol, ts_ms, candles)
    m7avg = _compute_news_mentions_7d_avg(db, symbol, ts_ms, candles)
    return _safe_div(m24, max(m7avg, 1.0), 1.0)


def _compute_reddit_mentions_24h(db, symbol, ts_ms, candles):
    """Reddit mentions in last 24h."""
    ms_24h = 24 * 3600 * 1000
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM social_events "
        "WHERE symbol = ? AND source = 'reddit' AND ts > ?",
        (symbol, ts_ms - ms_24h),
    ).fetchone()
    return row["cnt"] if row else 0


def _compute_reddit_score_24h(db, symbol, ts_ms, candles):
    """Sum of numeric_value for reddit mentions in 24h."""
    ms_24h = 24 * 3600 * 1000
    row = db.execute(
        "SELECT COALESCE(SUM(numeric_value), 0) as total FROM social_events "
        "WHERE symbol = ? AND source = 'reddit' AND ts > ?",
        (symbol, ts_ms - ms_24h),
    ).fetchone()
    return row["total"] if row else 0


def _compute_reddit_velocity_ratio(db, symbol, ts_ms, candles):
    """Reddit mentions_24h / max(7d_avg, 1)."""
    ms_7d = 7 * 24 * 3600 * 1000
    m24 = _compute_reddit_mentions_24h(db, symbol, ts_ms, candles)
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM social_events "
        "WHERE symbol = ? AND source = 'reddit' AND ts > ?",
        (symbol, ts_ms - ms_7d),
    ).fetchone()
    total_7d = row["cnt"] if row else 0
    avg_7d = total_7d / 7.0
    return _safe_div(m24, max(avg_7d, 1.0), 1.0)


def _compute_github_commits_7d(db, symbol, ts_ms, candles):
    """GitHub commits in last 7d."""
    ms_7d = 7 * 24 * 3600 * 1000
    row = db.execute(
        "SELECT COALESCE(SUM(numeric_value), 0) as total FROM social_events "
        "WHERE symbol = ? AND source = 'github' AND event_type = 'commits' AND ts > ?",
        (symbol, ts_ms - ms_7d),
    ).fetchone()
    return row["total"] if row else 0


def _compute_github_commit_spike(db, symbol, ts_ms, candles):
    """commits_7d / max(commits_30d_weekly_avg, 1)."""
    ms_7d = 7 * 24 * 3600 * 1000
    ms_30d = 30 * 24 * 3600 * 1000
    commits_7d = _compute_github_commits_7d(db, symbol, ts_ms, candles)
    row = db.execute(
        "SELECT COALESCE(SUM(numeric_value), 0) as total FROM social_events "
        "WHERE symbol = ? AND source = 'github' AND event_type = 'commits' AND ts > ?",
        (symbol, ts_ms - ms_30d),
    ).fetchone()
    total_30d = row["total"] if row else 0
    avg_weekly = total_30d / (30 / 7)
    return _safe_div(commits_7d, max(avg_weekly, 1.0), 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# DISPATCH TABLE — maps fn name string to actual callable
# ═══════════════════════════════════════════════════════════════════════════

_COMPUTE_FN_MAP = {
    # Price Action
    "_compute_price_vs_52w_high": _compute_price_vs_52w_high,
    "_compute_price_vs_52w_low": _compute_price_vs_52w_low,
    "_compute_momentum_4w": _compute_momentum_4w,
    "_compute_momentum_8w": _compute_momentum_8w,
    "_compute_bb_squeeze_pct": _compute_bb_squeeze_pct,
    "_compute_bb_position": _compute_bb_position,
    # Volume
    "_compute_volume_ratio_7d": _compute_volume_ratio_7d,
    "_compute_volume_ratio_3d": _compute_volume_ratio_3d,
    "_compute_obv_slope": _compute_obv_slope,
    "_compute_volume_spike": _compute_volume_spike,
    "_compute_volume_trend": _compute_volume_trend,
    # Volatility
    "_compute_atr_percentile": _compute_atr_percentile,
    "_compute_atr_compression": _compute_atr_compression,
    "_compute_high_low_range_pct": _compute_high_low_range_pct,
    "_compute_realized_vol_ratio": _compute_realized_vol_ratio,
    # Price Structure
    "_compute_distance_from_support": _compute_distance_from_support,
    "_compute_distance_from_resistance": _compute_distance_from_resistance,
    "_compute_consec_down_bars": _compute_consec_down_bars,
    "_compute_consec_up_bars": _compute_consec_up_bars,
    "_compute_higher_highs": _compute_higher_highs,
    # Market Regime
    "_compute_btc_30d_return": _compute_btc_30d_return,
    "_compute_btc_vol_percentile": _compute_btc_vol_percentile,
    "_compute_market_breadth": _compute_market_breadth,
    # Coin Metadata
    "_compute_days_since_listing": _compute_days_since_listing,
    "_compute_is_new_listing": _compute_is_new_listing,
    # Funding Rate
    "_compute_funding_rate_current": _compute_funding_rate_current,
    "_compute_funding_rate_7d_avg": _compute_funding_rate_7d_avg,
    "_compute_funding_rate_extreme": _compute_funding_rate_extreme,
    # OI
    "_compute_oi_change_24h": _compute_oi_change_24h,
    "_compute_oi_change_7d": _compute_oi_change_7d,
    "_compute_oi_price_divergence": _compute_oi_price_divergence,
    "_compute_oi_percentile_90d": _compute_oi_percentile_90d,
    # Mark Price
    "_compute_mark_index_spread": _compute_mark_index_spread,
    # Ticker
    "_compute_price_vs_24h_high": _compute_price_vs_24h_high,
    "_compute_price_vs_24h_low": _compute_price_vs_24h_low,
    "_compute_vol_24h_vs_7d_avg": _compute_vol_24h_vs_7d_avg,
    "_compute_price_change_24h_pct": _compute_price_change_24h_pct,
    # Social
    "_compute_fear_greed_score": _compute_fear_greed_score,
    "_compute_fear_greed_7d_change": _compute_fear_greed_7d_change,
    "_compute_is_coingecko_trending": _compute_is_coingecko_trending,
    "_compute_trending_rank": _compute_trending_rank,
    "_compute_hours_on_trending": _compute_hours_on_trending,
    "_compute_news_mentions_24h": _compute_news_mentions_24h,
    "_compute_news_mentions_7d_avg": _compute_news_mentions_7d_avg,
    "_compute_news_velocity_ratio": _compute_news_velocity_ratio,
    "_compute_reddit_mentions_24h": _compute_reddit_mentions_24h,
    "_compute_reddit_score_24h": _compute_reddit_score_24h,
    "_compute_reddit_velocity_ratio": _compute_reddit_velocity_ratio,
    "_compute_github_commits_7d": _compute_github_commits_7d,
    "_compute_github_commit_spike": _compute_github_commit_spike,
}


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def compute_features(symbol, ts_ms, db, feature_names=None):
    """Compute features for a symbol at a timestamp.

    Args:
        symbol: e.g. "BTC-USDT"
        ts_ms: timestamp in milliseconds
        db: sqlite3 connection
        feature_names: list of feature names to compute, or None for all

    Returns:
        {"feature_version": "abc12345", "feature_names": [...], "feature_values": {...}}
    """
    if feature_names is None:
        names = sorted(FEATURE_REGISTRY.keys())
    else:
        names = sorted(feature_names)

    # Compute feature version from the sorted name list
    version = hashlib.sha256(json.dumps(names).encode()).hexdigest()[:8]

    # Determine max bars needed and load candles once
    max_bars = max(
        (FEATURE_REGISTRY[n]["bars"] for n in names if n in FEATURE_REGISTRY),
        default=0,
    )
    candles = _load_candles_cached(db, symbol, ts_ms, max(max_bars, 1)) if max_bars > 0 else []

    values = {}
    for name in names:
        reg = FEATURE_REGISTRY.get(name)
        if reg is None:
            log.warning("Unknown feature: %s", name)
            values[name] = 0.0
            continue

        fn_name = reg["fn"]
        fn = _COMPUTE_FN_MAP.get(fn_name)
        if fn is None:
            log.warning("No compute function for feature: %s (%s)", name, fn_name)
            values[name] = reg["neutral"]
            continue

        try:
            result = fn(db, symbol, ts_ms, candles)
            if result is None:
                values[name] = reg["neutral"]
            else:
                values[name] = result
        except Exception as e:
            log.warning("Feature %s failed for %s: %s", name, symbol, e)
            values[name] = reg["neutral"]

    return {
        "feature_version": version,
        "feature_names": names,
        "feature_values": values,
    }


def compute_all_features(db, symbols, ts_ms, feature_names=None):
    """Compute features for all symbols and store to the features table.

    Args:
        db: sqlite3 connection
        symbols: list of symbol strings
        ts_ms: timestamp in milliseconds
        feature_names: optional list of feature names (None = all)

    Returns:
        dict of symbol -> feature_values
    """
    _clear_candle_cache()
    _clear_btc_cache()

    results = {}
    computed_at = int(time.time() * 1000)

    for symbol in symbols:
        feat = compute_features(symbol, ts_ms, db, feature_names)
        results[symbol] = feat["feature_values"]

        # Store to DB
        db.execute(
            "INSERT OR REPLACE INTO features "
            "(symbol, ts, feature_version, feature_names, feature_values, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                symbol,
                ts_ms,
                feat["feature_version"],
                json.dumps(feat["feature_names"]),
                json.dumps(feat["feature_values"]),
                computed_at,
            ),
        )

    db.commit()
    _clear_candle_cache()
    _clear_btc_cache()

    log.info(
        "Computed features for %d symbols at ts=%d (version=%s)",
        len(symbols), ts_ms,
        compute_features(symbols[0], ts_ms, db, feature_names)["feature_version"]
        if symbols else "n/a",
    )
    return results
