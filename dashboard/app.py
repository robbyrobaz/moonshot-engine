"""Moonshot v2 — Read-only Flask Dashboard.

Single-file dashboard serving JSON API endpoints + main page on port 8893.
All data sourced from SQLite at config.DB_PATH in read-only mode.
"""

import json
import os
import sqlite3
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request
from cachetools import TTLCache, cached
from cachetools.keys import hashkey

import sys
sys.path.insert(0, '..')
import config

# Import ccxt for live trading data
try:
    import ccxt
except ImportError:
    ccxt = None

app = Flask(__name__)

# Cache with 30s TTL for API endpoints
_api_cache = TTLCache(maxsize=50, ttl=30)

# Exchange singleton with lazy loading (for live trading data)
_exchange_instance = None
_exchange_data_cache = {}
_exchange_cache_timestamp = 0
EXCHANGE_CACHE_TTL = 15  # seconds


def get_exchange():
    """Lazy-loaded exchange singleton"""
    global _exchange_instance
    if ccxt is None:
        return None
    if _exchange_instance is None:
        try:
            _exchange_instance = ccxt.blofin({
                'apiKey': '8ce245f6361d415ca199cd229a1d8360',
                'secret': '8807534c543b4dc0af9fa9626bade434',
                'password': 'omen_claw',
                'enableRateLimit': True,
                'options': {'brokerId': ''}
            })
            _exchange_instance.load_markets()
        except Exception as e:
            print(f"ERROR: Failed to initialize exchange: {e}")
            _exchange_instance = None
    return _exchange_instance


def get_exchange_data():
    """Get exchange balance and positions with 15s caching"""
    global _exchange_data_cache, _exchange_cache_timestamp
    
    now = time.time()
    if now - _exchange_cache_timestamp < EXCHANGE_CACHE_TTL and _exchange_data_cache:
        return _exchange_data_cache
    
    try:
        ex = get_exchange()
        if ex is None:
            return None
        
        balance = ex.fetch_balance()
        positions = ex.fetch_positions()
        
        _exchange_data_cache = {
            'balance': balance,
            'positions': positions,
            'timestamp': now
        }
        _exchange_cache_timestamp = now
        
        return _exchange_data_cache
    except Exception as e:
        print(f"ERROR: Failed to fetch exchange data: {e}")
        return None

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ro_db() -> sqlite3.Connection:
    """Open a read-only SQLite connection."""
    uri = f"file:{config.DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _ts_to_str(ts_ms):
    """Convert millisecond timestamp to human-readable string."""
    if ts_ms is None:
        return "—"
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, TypeError):
        return "—"


def _age_days(ts_ms):
    """Days since a millisecond timestamp."""
    if ts_ms is None:
        return None
    try:
        return max(0, int((time.time() * 1000 - ts_ms) / 86_400_000))
    except (TypeError, ValueError):
        return None



def _fmt_pct(val, decimals=2):
    """Format a float as a percentage string."""
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_float(val, decimals=4):
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _truncate(s, n=8):
    if s is None:
        return "—"
    return str(s)[:n]


def _safe_query(conn, sql, params=(), fetchone=False):
    """Execute a query, returning [] or None on error (table may not exist yet)."""
    try:
        cur = conn.execute(sql, params)
        return cur.fetchone() if fetchone else cur.fetchall()
    except sqlite3.OperationalError:
        return None if fetchone else []


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows):
    """Convert a list of sqlite3.Row objects to plain dicts."""
    if not rows:
        return []
    return [dict(r) for r in rows]


# ── Data Loaders ──────────────────────────────────────────────────────────────

def _load_leaderboard(conn):
    sql = """
        SELECT model_id, direction, model_type, stage, bt_pf, bt_precision,
               bt_trades, ft_trades, ft_pnl, ft_pnl_per_day, ft_pnl_last_7d,
               ft_pf, ft_max_drawdown_pct,
               is_paused, created_at
        FROM tournament_models
        WHERE stage IN ('forward_test', 'champion')
        ORDER BY ft_pnl_last_7d DESC, ft_pnl_per_day DESC, ft_pnl DESC
    """
    return _safe_query(conn, sql)



def _load_open_positions(conn):
    """Load open positions with current price via a simple join on latest candle."""
    sql = """
        SELECT p.id, p.symbol, p.direction, p.model_id, p.entry_ts,
               p.entry_price, p.entry_ml_score, p.size_usd, p.status,
               p.high_water_price, p.trailing_active,
               c.close AS current_price
        FROM positions p
        LEFT JOIN candles c ON p.symbol = c.symbol
            AND c.ts = (SELECT MAX(ts) FROM candles WHERE symbol = p.symbol)
        WHERE p.status = 'open'
        ORDER BY p.entry_ts DESC
    """
    return _safe_query(conn, sql)


def _load_recent_closes(conn):
    cutoff_ms = int((time.time() - 48 * 3600) * 1000)
    sql = """
        SELECT symbol, direction, model_id, entry_price, exit_price,
               pnl_pct, exit_reason, entry_ts, exit_ts
        FROM positions
        WHERE status = 'closed' AND exit_ts > ?
        ORDER BY exit_ts DESC
    """
    return _safe_query(conn, sql, (cutoff_ms,))


def _pnl_timeseries_window_to_cutoff(window: str) -> int | None:
    now_ms = int(time.time() * 1000)
    mapping = {
        "7d": 7 * 24 * 3600 * 1000,
        "30d": 30 * 24 * 3600 * 1000,
        "all": None,
    }
    span = mapping.get(window)
    if window not in mapping:
        raise ValueError(f"unsupported window: {window}")
    if span is None:
        return None
    return now_ms - span



def _load_regime(conn):
    # BTC 30-day return from candles (180 × 4h bars ≈ 30 days)
    # Use exact symbol match for index efficiency
    btc_sql = """
        SELECT close FROM candles
        WHERE symbol = 'BTCUSDT'
        ORDER BY ts DESC LIMIT 1
    """
    btc_30d_sql = """
        SELECT close FROM candles
        WHERE symbol = 'BTCUSDT'
        ORDER BY ts DESC LIMIT 1 OFFSET 180
    """
    latest = _safe_query(conn, btc_sql, fetchone=True)
    older = _safe_query(conn, btc_30d_sql, fetchone=True)
    btc_return = None
    if latest and older and older["close"]:
        btc_return = (latest["close"] - older["close"]) / older["close"]

    # Latest regime from runs
    run = _safe_query(conn, "SELECT regime FROM runs ORDER BY run_id DESC LIMIT 1", fetchone=True)
    regime = run["regime"] if run else None

    # Determine regime from return if not in runs
    if regime is None and btc_return is not None:
        if btc_return <= config.BEAR_THRESHOLD:
            regime = "bear"
        elif btc_return >= config.BULL_THRESHOLD:
            regime = "bull"
        else:
            regime = "neutral"

    # Market breadth from features
    breadth_sql = """
        SELECT feature_values, feature_names FROM features
        ORDER BY ts DESC LIMIT 1
    """
    breadth_row = _safe_query(conn, breadth_sql, fetchone=True)
    market_breadth = None
    if breadth_row:
        try:
            vals = json.loads(breadth_row["feature_values"])
            if isinstance(vals, dict):
                market_breadth = vals.get("market_breadth", market_breadth)
            else:
                names = json.loads(breadth_row["feature_names"])
                idx = names.index("market_breadth") if "market_breadth" in names else -1
                if idx >= 0:
                    market_breadth = vals[idx]
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

    return {
        "regime": regime or "unknown",
        "btc_30d_return": btc_return,
        "market_breadth": market_breadth,
    }


def _load_macro():
    """Load external macro data (BTC dominance, fear/greed) from /mnt/data/market_macro.db."""
    macro_db_path = Path("/mnt/data/market_macro.db")
    
    if not macro_db_path.exists():
        return None
    
    try:
        uri = f"file:{macro_db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        
        # Latest market data
        global_row = conn.execute("""
            SELECT ts_iso, btc_dominance_pct, total_market_cap_usd, total_volume_24h_usd
            FROM market_global 
            ORDER BY ts_ms DESC LIMIT 1
        """).fetchone()
        
        # Latest fear/greed (external source, more frequently updated)
        fg_row = conn.execute("""
            SELECT ts_iso, value, classification 
            FROM fear_greed 
            ORDER BY ts_ms DESC LIMIT 1
        """).fetchone()
        
        # Calculate 24h change in BTC dominance
        dom_24h_ago = conn.execute("""
            SELECT btc_dominance_pct 
            FROM market_global 
            WHERE ts_ms < (SELECT ts_ms FROM market_global ORDER BY ts_ms DESC LIMIT 1) - 86400000
            ORDER BY ts_ms DESC LIMIT 1
        """).fetchone()
        
        conn.close()
        
        if not global_row:
            return None
        
        dom_change = None
        if dom_24h_ago and global_row["btc_dominance_pct"]:
            dom_change = global_row["btc_dominance_pct"] - dom_24h_ago["btc_dominance_pct"]
        
        return {
            "btc_dom": global_row["btc_dominance_pct"],
            "btc_dom_24h_change": dom_change,
            "total_mcap_usd": global_row["total_market_cap_usd"],
            "total_vol_24h_usd": global_row["total_volume_24h_usd"],
            "fear_greed_value": fg_row["value"] if fg_row else None,
            "fear_greed_label": fg_row["classification"] if fg_row else None,
            "updated_at": global_row["ts_iso"],
        }
    except (sqlite3.Error, TypeError, KeyError) as e:
        # External DB may not exist yet or be locked
        return None


def _load_social(conn):
    cutoff_ms = int((time.time() - 24 * 3600) * 1000)
    mentions_sql = """
        SELECT symbol, COUNT(*) as mentions_24h
        FROM social_events
        WHERE ts > ? AND source LIKE 'rss_%'
        GROUP BY symbol
        ORDER BY mentions_24h DESC
        LIMIT 20
    """
    mentions = _safe_query(conn, mentions_sql, (cutoff_ms,))

    # CoinGecko trending
    trending_sql = """
        SELECT text_snippet FROM social_events
        WHERE source = 'coingecko_trending'
        ORDER BY ts DESC LIMIT 1
    """
    trending_row = _safe_query(conn, trending_sql, fetchone=True)
    trending = []
    if trending_row and trending_row["text_snippet"]:
        try:
            trending = json.loads(trending_row["text_snippet"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Fear & Greed (from Moonshot's own collection)
    fg_sql = """
        SELECT numeric_value, text_snippet, ts FROM social_events
        WHERE source = 'fear_greed'
        ORDER BY ts DESC LIMIT 1
    """
    fg_row = _safe_query(conn, fg_sql, fetchone=True)

    return {
        "mentions": mentions,
        "trending": trending if isinstance(trending, list) else [],
        "fear_greed": fg_row,
    }



def _load_system_health(conn):
    run = _safe_query(conn, "SELECT * FROM runs ORDER BY run_id DESC LIMIT 1", fetchone=True)
    candle_count = _safe_query(conn, "SELECT COUNT(*) as cnt FROM candles", fetchone=True)
    coin_count = _safe_query(conn, "SELECT COUNT(*) as cnt FROM coins", fetchone=True)

    db_size_mb = 0
    try:
        db_size_mb = os.path.getsize(config.DB_PATH) / (1024 * 1024)
    except OSError:
        pass

    return {
        "run": run,
        "candle_count": candle_count["cnt"] if candle_count else 0,
        "coin_count": coin_count["cnt"] if coin_count else 0,
        "db_size_mb": db_size_mb,
    }


def _compute_unrealized_pnl(entry_price, current_price, direction, leverage=None):
    """Compute unrealized PnL% for an open position."""
    lev = leverage if leverage is not None else config.LEVERAGE
    if not entry_price or not current_price:
        return None, None, None
    entry = float(entry_price)
    current = float(current_price)
    if entry == 0:
        return None, None, None
    if direction == "long":
        upnl = (current - entry) / entry * lev * 100
        tp_dist = (entry * (1 + config.TP_PCT) - current) / current * 100
        sl_dist = (current - entry * (1 - config.SL_PCT)) / current * 100
    else:
        upnl = (entry - current) / entry * lev * 100
        tp_dist = (current - entry * (1 - config.TP_PCT)) / current * 100
        sl_dist = (entry * (1 + config.SL_PCT) - current) / current * 100
    return upnl, tp_dist, sl_dist


# ── Routes — Main Page ────────────────────────────────────────────────────────

# Load template from file at startup (all data fetched via JS from API endpoints)
_TEMPLATE_PATH = Path(__file__).parent / "template.html"
_TEMPLATE_CACHE = None

def _get_template():
    """Load template HTML, caching in production."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None or app.debug:
        _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text()
    return _TEMPLATE_CACHE

@app.route("/")
def index():
    return _get_template()


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/api/vault")
@cached(cache=_api_cache, key=lambda: hashkey("vault"))
def api_vault():
    """Top models eligible for real money: champions first, then top FT by ft_pnl (ft_trades >= 100).

    Returns up to 5 models with full performance metrics.
    """
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        sql = """
            SELECT model_id, direction, stage, model_type,
                   ft_pnl, ft_pnl_per_day, ft_pnl_last_7d, ft_pf,
                   ft_trades, ft_wins, ft_max_drawdown_pct,
                   is_paused, bt_pf, bt_precision, promoted_to_ft_at
            FROM tournament_models
            WHERE (stage = 'champion')
               OR (stage = 'forward_test' AND ft_trades >= 100)
            ORDER BY
                CASE WHEN stage = 'champion' THEN 0 ELSE 1 END ASC,
                ft_pnl_last_7d DESC,
                ft_pnl_per_day DESC,
                ft_pnl DESC
            LIMIT 5
        """
        rows = _safe_query(conn, sql)
        now_ms = time.time() * 1000
        result = []
        for r in rows:
            ft_trades = r["ft_trades"] or 0
            ft_wins = r["ft_wins"] or 0
            ft_win_rate = (ft_wins / ft_trades * 100) if ft_trades > 0 else None
            promoted_at = r["promoted_to_ft_at"]
            days_in_ft = _age_days(promoted_at)
            result.append({
                "model_id": r["model_id"],
                "direction": r["direction"],
                "stage": r["stage"],
                "model_type": r["model_type"],
                "ft_pnl": r["ft_pnl"],
                "ft_pnl_per_day": r["ft_pnl_per_day"],
                "ft_pnl_last_7d": r["ft_pnl_last_7d"],
                "ft_pf": r["ft_pf"],
                "ft_trades": ft_trades,
                "ft_wins": ft_wins,
                "ft_win_rate": round(ft_win_rate, 2) if ft_win_rate is not None else None,
                "ft_max_drawdown_pct": r["ft_max_drawdown_pct"],
                "days_in_ft": days_in_ft,
                "is_paused": bool(r["is_paused"]),
                "bt_pf": r["bt_pf"],
                "bt_precision": r["bt_precision"],
            })
        return jsonify({"vault": result, "count": len(result)})
    finally:
        conn.close()


@app.route("/api/models")
@cached(cache=_api_cache, key=lambda: hashkey("models"))
def api_models():
    """All FT + champion models for the master leaderboard table."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        sql = """
            SELECT model_id, direction, stage, model_type,
                   ft_pnl, ft_pnl_per_day, ft_pnl_last_7d, ft_pf,
                   ft_trades, ft_wins, ft_max_drawdown_pct,
                   is_paused, bt_pf, bt_precision, promoted_to_ft_at
            FROM tournament_models
            WHERE stage IN ('forward_test', 'champion')
            ORDER BY ft_pnl_last_7d DESC, ft_pnl_per_day DESC, ft_pnl DESC
        """
        rows = _safe_query(conn, sql)
        now_ms = time.time() * 1000
        result = []
        for r in rows:
            ft_trades = r["ft_trades"] or 0
            ft_wins = r["ft_wins"] or 0
            ft_win_rate = (ft_wins / ft_trades * 100) if ft_trades > 0 else None
            days_in_ft = _age_days(r["promoted_to_ft_at"])
            result.append({
                "model_id": r["model_id"],
                "direction": r["direction"],
                "stage": r["stage"],
                "model_type": r["model_type"],
                "ft_pnl": r["ft_pnl"],
                "ft_pnl_per_day": r["ft_pnl_per_day"],
                "ft_pnl_last_7d": r["ft_pnl_last_7d"],
                "ft_pf": r["ft_pf"],
                "ft_trades": ft_trades,
                "ft_wins": ft_wins,
                "ft_win_rate": round(ft_win_rate, 2) if ft_win_rate is not None else None,
                "ft_max_drawdown_pct": r["ft_max_drawdown_pct"],
                "days_in_ft": days_in_ft,
                "is_paused": bool(r["is_paused"]),
                "bt_pf": r["bt_pf"],
                "bt_precision": r["bt_precision"],
            })
        return jsonify({"models": result, "count": len(result)})
    finally:
        conn.close()


@app.route("/api/models/<model_id>/pnl-timeseries")
def api_model_pnl_timeseries(model_id):
    """Daily closed-trade PnL aggregation for one model."""
    window = request.args.get("window", "7d")
    try:
        cutoff_ms = _pnl_timeseries_window_to_cutoff(window)
    except ValueError:
        return jsonify({"error": "window must be one of 7d, 30d, all"}), 400

    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        where = [
            "model_id = ?",
            "status = 'closed'",
            "is_champion_trade = 0",
            "exit_ts IS NOT NULL",
        ]
        params = [model_id]
        if cutoff_ms is not None:
            where.append("exit_ts >= ?")
            params.append(cutoff_ms)

        sql = f"""
            SELECT date(exit_ts / 1000, 'unixepoch') AS bucket,
                   COALESCE(SUM(pnl_pct), 0.0) AS pnl_pct_sum,
                   COUNT(*) AS trade_count,
                   COALESCE(AVG(pnl_pct), 0.0) AS avg_pnl_pct
            FROM positions
            WHERE {' AND '.join(where)}
            GROUP BY bucket
            ORDER BY bucket ASC
        """
        rows = _safe_query(conn, sql, tuple(params))
        series = [
            {
                "bucket": r["bucket"],
                "pnl_pct_sum": r["pnl_pct_sum"],
                "trade_count": r["trade_count"],
                "avg_pnl_pct": r["avg_pnl_pct"],
            }
            for r in rows
        ]
        return jsonify(
            {
                "model_id": model_id,
                "window": window,
                "series": series,
                "count": len(series),
            }
        )
    finally:
        conn.close()


@app.route("/api/pipeline")
@cached(cache=_api_cache, key=lambda: hashkey("pipeline"))
def api_pipeline():
    """Pipeline funnel counts: how many models at each stage.

    Includes total_ever, per-stage counts, and conversion rates.
    """
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        total_row = _safe_query(conn, "SELECT COUNT(*) as cnt FROM tournament_models", fetchone=True)
        total_ever = total_row["cnt"] if total_row else 0

        # Backtest failed = retired where retire_reason contains 'backtest'
        bt_failed_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM tournament_models
            WHERE stage = 'retired'
              AND retire_reason IS NOT NULL
              AND retire_reason LIKE '%backtest%'
        """, fetchone=True)
        bt_failed = bt_failed_row["cnt"] if bt_failed_row else 0

        # Currently in forward test
        ft_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM tournament_models
            WHERE stage = 'forward_test'
        """, fetchone=True)
        in_ft = ft_row["cnt"] if ft_row else 0

        # Currently champion
        champ_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM tournament_models
            WHERE stage = 'champion'
        """, fetchone=True)
        champion = champ_row["cnt"] if champ_row else 0

        # Retired from FT (promoted to FT but not retired for backtest reason)
        retired_ft_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM tournament_models
            WHERE stage = 'retired'
              AND promoted_to_ft_at IS NOT NULL
              AND (retire_reason IS NULL OR retire_reason NOT LIKE '%backtest%')
        """, fetchone=True)
        retired_ft = retired_ft_row["cnt"] if retired_ft_row else 0

        # Ever reached FT (currently in FT + champion + retired from FT)
        ever_ft = in_ft + champion + retired_ft

        bt_pass_rate = round(ever_ft / total_ever * 100, 1) if total_ever > 0 else 0
        ft_to_champion_rate = round(champion / ever_ft * 100, 1) if ever_ft > 0 else 0

        return jsonify({
            "total_ever": total_ever,
            "backtest_failed": bt_failed,
            "forward_test": in_ft,
            "champion": champion,
            "retired_from_ft": retired_ft,
            "ever_reached_ft": ever_ft,
            "bt_pass_rate_pct": bt_pass_rate,
            "ft_to_champion_rate_pct": ft_to_champion_rate,
        })
    finally:
        conn.close()


@app.route("/api/rising-stars")
@cached(cache=_api_cache, key=lambda: hashkey("rising_stars"))
def api_rising_stars():
    """Emerging FT models with <100 trades but high profit factor (>= 2.5)."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        sql = """
            SELECT model_id, direction, ft_pnl, ft_pf, ft_trades, ft_wins,
                   promoted_to_ft_at
            FROM tournament_models
            WHERE stage = 'forward_test'
              AND ft_trades < 100
              AND ft_pf >= 2.5
            ORDER BY ft_pf DESC
        """
        rows = _safe_query(conn, sql)
        result = []
        for r in rows:
            ft_trades = r["ft_trades"] or 0
            ft_wins = r["ft_wins"] or 0
            result.append({
                "model_id": r["model_id"],
                "direction": r["direction"],
                "ft_pnl": r["ft_pnl"],
                "ft_pf": r["ft_pf"],
                "ft_trades": ft_trades,
                "ft_wins": ft_wins,
                "days_in_ft": _age_days(r["promoted_to_ft_at"]),
            })
        return jsonify({"rising_stars": result, "count": len(result)})
    finally:
        conn.close()


@app.route("/api/positions")
@cached(cache=_api_cache, key=lambda: hashkey("positions"))
def api_positions():
    """Open positions with unrealized PnL, TP distance, and SL distance."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        rows = _load_open_positions(conn)
        result = []
        for p in rows:
            entry = p["entry_price"]
            current = p["current_price"]
            direction = p["direction"]
            leverage = p["leverage"] if "leverage" in p.keys() else config.LEVERAGE
            upnl, tp_dist, sl_dist = _compute_unrealized_pnl(entry, current, direction, leverage)

            # Handle entry_ml_score which may be bytes or float
            ml_score = p["entry_ml_score"]
            if isinstance(ml_score, bytes):
                # Convert bytes to float (little-endian 32-bit float)
                ml_score = struct.unpack('<f', ml_score)[0] if len(ml_score) == 4 else None

            result.append({
                "id": p["id"],
                "symbol": p["symbol"],
                "direction": direction,
                "model_id": p["model_id"],
                "entry_price": entry,
                "current_price": current,
                "unrealized_pnl_pct": round(upnl, 4) if upnl is not None else None,
                "tp_distance_pct": round(tp_dist, 4) if tp_dist is not None else None,
                "sl_distance_pct": round(sl_dist, 4) if sl_dist is not None else None,
                "entry_ts": _ts_to_str(p["entry_ts"]),
                "entry_ts_ms": p["entry_ts"],
                "entry_ml_score": ml_score,
                "size_usd": p["size_usd"],
            })
        return jsonify({"positions": result, "count": len(result)})
    finally:
        conn.close()


@app.route("/api/recent-trades")
@cached(cache=_api_cache, key=lambda: hashkey("recent_trades"))
def api_recent_trades():
    """Closed trades in the last 48h with summary stats."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        rows = _load_recent_closes(conn)
        trades = []
        total_pnl = 0.0
        wins = 0
        losses = 0
        by_reason = {}

        for r in rows:
            pnl = r["pnl_pct"] or 0.0
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1
            reason = r["exit_reason"] or "unknown"
            if reason not in by_reason:
                by_reason[reason] = {"count": 0, "pnl": 0.0, "wins": 0}
            by_reason[reason]["count"] += 1
            by_reason[reason]["pnl"] += pnl
            if pnl > 0:
                by_reason[reason]["wins"] += 1

            trades.append({
                "symbol": r["symbol"],
                "direction": r["direction"],
                "model_id": r["model_id"],
                "pnl_pct": pnl,
                "exit_reason": reason,
                "entry_ts": _ts_to_str(r["entry_ts"]),
                "exit_ts": _ts_to_str(r["exit_ts"]),
                "entry_ts_ms": r["entry_ts"],
                "exit_ts_ms": r["exit_ts"],
                "entry_price": r["entry_price"],
                "exit_price": r["exit_price"],
            })

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

        # Round by_reason pnl values
        for v in by_reason.values():
            v["pnl"] = round(v["pnl"], 4)

        return jsonify({
            "trades": trades,
            "summary": {
                "total_pnl": round(total_pnl, 4),
                "wins": wins,
                "losses": losses,
                "total": total_trades,
                "win_rate": round(win_rate, 2),
                "by_reason": by_reason,
            },
        })
    finally:
        conn.close()


@app.route("/api/market")
@cached(cache=_api_cache, key=lambda: hashkey("market"))
def api_market():
    """Market context: regime, BTC 30d return, Fear & Greed index, external macro."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        regime_data = _load_regime(conn)

        # Fear & Greed (from Moonshot's own social_events)
        fg_sql = """
            SELECT numeric_value, text_snippet, ts FROM social_events
            WHERE source = 'fear_greed'
            ORDER BY ts DESC LIMIT 1
        """
        fg_row = _safe_query(conn, fg_sql, fetchone=True)
        fear_greed = None
        if fg_row:
            fear_greed = {
                "value": fg_row["numeric_value"],
                "label": fg_row["text_snippet"],
                "ts": _ts_to_str(fg_row["ts"]),
                "ts_ms": fg_row["ts"],
            }

        # External macro data (BTC dominance, global market cap)
        macro = _load_macro()

        return jsonify({
            "regime": regime_data["regime"],
            "btc_30d_return": round(regime_data["btc_30d_return"] * 100, 2)
                              if regime_data["btc_30d_return"] is not None else None,
            "market_breadth": regime_data["market_breadth"],
            "fear_greed": fear_greed,
            "macro": macro,  # BTC dom, total mcap, 24h vol
        })
    finally:
        conn.close()


@app.route("/api/portfolio")
def api_portfolio():
    """Portfolio-level aggregated metrics across all FT + champion models."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        # Total capital allocated (open positions only)
        capital_row = _safe_query(conn, """
            SELECT COALESCE(SUM(size_usd), 0) as total_capital
            FROM positions
            WHERE status = 'open'
              AND model_id IN (
                  SELECT model_id FROM tournament_models
                  WHERE stage IN ('forward_test', 'champion')
              )
        """, fetchone=True)
        total_capital = capital_row["total_capital"] if capital_row else 0

        # Total positions
        positions_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM positions
            WHERE status = 'open'
              AND model_id IN (
                  SELECT model_id FROM tournament_models
                  WHERE stage IN ('forward_test', 'champion')
              )
        """, fetchone=True)
        total_positions = positions_row["cnt"] if positions_row else 0

        # Overall PnL% and win rate (all FT models combined)
        models_sql = """
            SELECT
                COALESCE(SUM(ft_pnl), 0) as total_pnl,
                COALESCE(SUM(ft_wins), 0) as total_wins,
                COALESCE(SUM(ft_trades), 0) as total_trades,
                COALESCE(SUM(ft_pnl_last_7d), 0) as total_pnl_7d,
                COALESCE(SUM(ft_pnl_per_day), 0) as total_pnl_per_day
            FROM tournament_models
            WHERE stage IN ('forward_test', 'champion')
        """
        agg = _safe_query(conn, models_sql, fetchone=True)

        total_pnl = agg["total_pnl"] if agg else 0
        total_wins = agg["total_wins"] if agg else 0
        total_trades = agg["total_trades"] if agg else 0
        total_pnl_7d = agg["total_pnl_7d"] if agg else 0
        total_pnl_per_day = agg["total_pnl_per_day"] if agg else 0
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

        # Daily PnL trend (last 7 days) for portfolio sparkline
        cutoff_ms = int((time.time() - 7 * 86400) * 1000)
        pnl_series_sql = """
            SELECT date(exit_ts / 1000, 'unixepoch') AS bucket,
                   COALESCE(SUM(pnl_pct), 0.0) AS pnl_pct_sum,
                   COUNT(*) AS trade_count
            FROM positions
            WHERE status = 'closed'
              AND is_champion_trade = 0
              AND exit_ts >= ?
              AND model_id IN (
                  SELECT model_id FROM tournament_models
                  WHERE stage IN ('forward_test', 'champion')
              )
            GROUP BY bucket
            ORDER BY bucket ASC
        """
        series_rows = _safe_query(conn, pnl_series_sql, (cutoff_ms,))
        pnl_series = [
            {
                "bucket": r["bucket"],
                "pnl_pct_sum": r["pnl_pct_sum"],
                "trade_count": r["trade_count"],
            }
            for r in series_rows
        ]

        return jsonify({
            "total_capital_usd": round(total_capital, 2),
            "total_positions": total_positions,
            "overall_pnl_pct": round(total_pnl, 2),
            "overall_pnl_7d_pct": round(total_pnl_7d, 2),
            "overall_pnl_per_day_pct": round(total_pnl_per_day, 2),
            "overall_win_rate_pct": round(overall_win_rate, 2),
            "total_trades": total_trades,
            "pnl_series": pnl_series,
        })
    finally:
        conn.close()


@app.route("/api/health")
@cached(cache=_api_cache, key=lambda: hashkey("health"))
def api_health():
    """System health: DB stats, last run info, model counts, last 5 cycle durations."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"status": "error", "detail": "database not found"}), 503

    try:
        health = _load_system_health(conn)
        run = health["run"]

        # FT model count
        ft_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM tournament_models
            WHERE stage = 'forward_test'
        """, fetchone=True)
        ft_model_count = ft_row["cnt"] if ft_row else 0

        # Champion count
        champ_row = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM tournament_models
            WHERE stage = 'champion'
        """, fetchone=True)
        champion_count = champ_row["cnt"] if champ_row else 0

        # Last 5 cycle durations (ended_at - started_at) in seconds
        runs_rows = _safe_query(conn, """
            SELECT run_id, started_at, ended_at, regime, errors
            FROM runs
            WHERE ended_at IS NOT NULL AND started_at IS NOT NULL
            ORDER BY run_id DESC
            LIMIT 5
        """)
        recent_cycles = []
        for r in runs_rows:
            duration_s = None
            if r["started_at"] and r["ended_at"]:
                duration_s = round((r["ended_at"] - r["started_at"]) / 1000, 1)
            recent_cycles.append({
                "run_id": r["run_id"],
                "duration_s": duration_s,
                "regime": r["regime"],
                "ended_at": _ts_to_str(r["ended_at"]),
                "had_errors": bool(r["errors"]),
            })

        return jsonify({
            "status": "ok",
            "db_size_mb": round(health["db_size_mb"], 2),
            "candle_count": health["candle_count"],
            "coin_count": health["coin_count"],
            "ft_model_count": ft_model_count,
            "champion_count": champion_count,
            "last_run_id": run["run_id"] if run else None,
            "last_run_ended": _ts_to_str(run["ended_at"]) if run else None,
            "last_run_ended_ms": run["ended_at"] if run else None,
            "errors": run["errors"] if run else None,
            "recent_cycles": recent_cycles,
        })
    finally:
        conn.close()


@app.route("/api/charts/champion-equity")
@cached(cache=_api_cache, key=lambda: hashkey("champion_equity"))
def api_champion_equity():
    """Champion equity curve: cumulative PnL over time."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        # Get current champion model_id
        champ_sql = """
            SELECT model_id FROM tournament_models
            WHERE stage = 'champion'
            ORDER BY promoted_to_champion_at DESC
            LIMIT 1
        """
        champ_row = _safe_query(conn, champ_sql, fetchone=True)

        if not champ_row:
            return jsonify({"labels": [], "data": [], "champion": None})

        champion_id = champ_row["model_id"]

        # Get daily cumulative PnL for champion
        sql = """
            SELECT date(exit_ts / 1000, 'unixepoch') AS date,
                   pnl_pct
            FROM positions
            WHERE model_id = ?
              AND status = 'closed'
              AND exit_ts IS NOT NULL
            ORDER BY exit_ts ASC
        """
        rows = _safe_query(conn, sql, (champion_id,))

        # Calculate cumulative PnL
        cumulative = 0.0
        labels = []
        data = []

        for r in rows:
            cumulative += r["pnl_pct"] or 0.0
            labels.append(r["date"])
            data.append(round(cumulative, 2))

        return jsonify({
            "labels": labels,
            "data": data,
            "champion": champion_id,
        })
    finally:
        conn.close()


@app.route("/api/charts/daily-pnl")
@cached(cache=_api_cache, key=lambda: hashkey("daily_pnl"))
def api_daily_pnl():
    """Daily PnL bar chart: last 30 days aggregate PnL."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        cutoff_ms = int((time.time() - 30 * 86400) * 1000)
        sql = """
            SELECT date(exit_ts / 1000, 'unixepoch') AS date,
                   COALESCE(SUM(pnl_pct), 0.0) AS pnl_pct_sum
            FROM positions
            WHERE status = 'closed'
              AND exit_ts >= ?
              AND is_champion_trade = 0
              AND model_id IN (
                  SELECT model_id FROM tournament_models
                  WHERE stage IN ('forward_test', 'champion')
              )
            GROUP BY date
            ORDER BY date ASC
        """
        rows = _safe_query(conn, sql, (cutoff_ms,))

        labels = [r["date"] for r in rows]
        data = [round(r["pnl_pct_sum"], 2) for r in rows]

        return jsonify({
            "labels": labels,
            "data": data,
        })
    finally:
        conn.close()


@app.route("/api/charts/model-comparison")
@cached(cache=_api_cache, key=lambda: hashkey("model_comparison"))
def api_model_comparison():
    """Model comparison chart: top 5 FT models by total PnL."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        sql = """
            SELECT model_id, ft_pnl, direction, stage
            FROM tournament_models
            WHERE stage IN ('forward_test', 'champion')
              AND ft_pnl IS NOT NULL
            ORDER BY ft_pnl DESC
            LIMIT 5
        """
        rows = _safe_query(conn, sql)

        labels = [r["model_id"][:8] + ("★" if r["stage"] == "champion" else "") for r in rows]
        data = [round(r["ft_pnl"], 2) for r in rows]
        directions = [r["direction"] for r in rows]

        return jsonify({
            "labels": labels,
            "data": data,
            "directions": directions,
        })
    finally:
        conn.close()


@app.route("/api/moonshot-live")
def api_moonshot_live():
    """Get Moonshot live trading metrics from moonshot_live.db + exchange data"""
    try:
        # Connect to moonshot live trading DB (in blofin-stack)
        moonshot_db_path = "/home/rob/.openclaw/workspace/blofin-stack/data/moonshot_live.db"
        
        # Check if DB exists
        if not os.path.exists(moonshot_db_path):
            return jsonify({
                'error': 'Moonshot live DB not initialized',
                'summary': {
                    'starting_balance': 38.87,
                    'current_balance': 38.87,
                    'total_pnl_usd': 0,
                    'total_pnl_pct': 0,
                    'model_id': '87033f5ca7fe',
                    'model_type': 'CatBoost SHORT',
                    'ft_pf': 2.63,
                    'ft_wr': 75.8,
                    'open_count': 0,
                    'closed_count': 0,
                    'win_rate': 0,
                },
                'open_positions': [],
                'closed_trades': [],
                'exchange_connected': False,
            })
        
        conn = sqlite3.connect(moonshot_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if table exists
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='moonshot_live_trades'")
            table_exists = cursor.fetchone() is not None
        except:
            table_exists = False
        
        if not table_exists:
            conn.close()
            return jsonify({
                'error': 'Moonshot live trading not started yet (table not created)',
                'summary': {
                    'starting_balance': 38.87,
                    'current_balance': 38.87,
                    'total_pnl_usd': 0,
                    'total_pnl_pct': 0,
                    'model_id': '87033f5ca7fe',
                    'model_type': 'CatBoost SHORT',
                    'ft_pf': 2.63,
                    'ft_wr': 75.8,
                    'open_count': 0,
                    'closed_count': 0,
                    'win_rate': 0,
                },
                'open_positions': [],
                'closed_trades': [],
                'exchange_connected': False,
            })
        
        # Get all trades
        cursor.execute("""
            SELECT * FROM moonshot_live_trades 
            ORDER BY entry_time DESC
        """)
        all_trades = [dict(row) for row in cursor.fetchall()]
        
        # Calculate summary stats from DB
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_count,
                COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) as closed_count,
                COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN pnl_usd ELSE 0 END), 0) as total_realized_pnl,
                COUNT(CASE WHEN status = 'CLOSED' AND pnl_pct > 0 THEN 1 END) as winning_trades
            FROM moonshot_live_trades
        """)
        stats = dict(cursor.fetchone())
        
        win_rate = (stats['winning_trades'] / stats['closed_count'] * 100) if stats['closed_count'] > 0 else 0
        
        conn.close()
        
        # Get exchange data (balance + live positions)
        exchange_data = get_exchange_data()
        current_balance = 38.87  # Default to starting balance
        open_positions = []
        
        if exchange_data:
            try:
                # Get USDT balance
                usdt_balance = exchange_data['balance'].get('USDT', {})
                current_balance = usdt_balance.get('total', 38.87)
                
                # Process open positions from DB
                for trade in all_trades:
                    if trade['status'] == 'OPEN':
                        symbol_ccxt = trade['moonshot_symbol'].replace('-USDT', '/USDT:USDT')
                        
                        # Find matching position on exchange
                        broker_pos = next((p for p in exchange_data['positions'] 
                                         if p.get('symbol') == symbol_ccxt and p.get('contracts', 0) != 0), None)
                        
                        current_price = broker_pos.get('markPrice', trade['entry_price']) if broker_pos else trade['entry_price']
                        
                        # Calculate unrealized PnL
                        if trade['direction'] == 'short':
                            upnl_pct = ((trade['entry_price'] - current_price) / trade['entry_price']) * 100 * trade['leverage']
                        else:
                            upnl_pct = ((current_price - trade['entry_price']) / trade['entry_price']) * 100 * trade['leverage']
                        
                        position_size_usd = trade['entry_price'] * trade['contracts']
                        upnl_usd = position_size_usd * (upnl_pct / 100)
                        
                        # Calculate duration
                        duration = ""
                        if trade['entry_time']:
                            try:
                                entry_dt = datetime.fromisoformat(trade['entry_time'].replace('Z', '+00:00'))
                                duration_sec = (datetime.now(entry_dt.tzinfo) - entry_dt).total_seconds()
                                hours = int(duration_sec // 3600)
                                minutes = int((duration_sec % 3600) // 60)
                                duration = f"{hours}h {minutes}m"
                            except:
                                duration = "N/A"
                        
                        open_positions.append({
                            'symbol': trade['moonshot_symbol'],
                            'ml_score': trade['ml_score'],
                            'entry_price': trade['entry_price'],
                            'current_price': current_price,
                            'unrealized_pnl_usd': upnl_usd,
                            'unrealized_pnl_pct': upnl_pct,
                            'leverage': trade['leverage'],
                            'sl_price': trade['broker_sl_price'],
                            'tp_price': trade['broker_tp_price'],
                            'duration': duration
                        })
            except Exception as e:
                print(f"ERROR processing moonshot exchange data: {e}")
        
        # Calculate total P&L
        total_pnl_usd = stats['total_realized_pnl'] + sum(p['unrealized_pnl_usd'] for p in open_positions)
        total_pnl_pct = (total_pnl_usd / 38.87) * 100
        
        # Format closed trades with duration
        closed_trades = []
        for trade in all_trades:
            if trade['status'] == 'CLOSED':
                # Calculate duration
                duration = ""
                if trade['entry_time'] and trade['exit_time']:
                    try:
                        entry_dt = datetime.fromisoformat(trade['entry_time'].replace('Z', '+00:00'))
                        exit_dt = datetime.fromisoformat(trade['exit_time'].replace('Z', '+00:00'))
                        duration_sec = (exit_dt - entry_dt).total_seconds()
                        hours = int(duration_sec // 3600)
                        minutes = int((duration_sec % 3600) // 60)
                        duration = f"{hours}h {minutes}m"
                    except:
                        duration = "N/A"
                
                closed_trades.append({
                    'id': trade['id'],
                    'symbol': trade['moonshot_symbol'],
                    'ml_score': trade['ml_score'],
                    'entry_price': trade['entry_price'],
                    'exit_price': trade['exit_price'],
                    'pnl_usd': trade['pnl_usd'],
                    'pnl_pct': trade['pnl_pct'],
                    'leverage': trade['leverage'],
                    'exit_reason': trade['exit_reason'],
                    'duration': duration,
                })
        
        return jsonify({
            'summary': {
                'starting_balance': 38.87,
                'current_balance': round(current_balance, 2),
                'total_pnl_usd': round(total_pnl_usd, 2),
                'total_pnl_pct': round(total_pnl_pct, 2),
                'model_id': '87033f5ca7fe',
                'model_type': 'CatBoost SHORT',
                'ft_pf': 2.63,
                'ft_wr': 75.8,
                'open_count': stats['open_count'],
                'closed_count': stats['closed_count'],
                'win_rate': round(win_rate, 1),
            },
            'open_positions': open_positions,
            'closed_trades': closed_trades,
            'exchange_connected': exchange_data is not None,
        })
        
    except Exception as e:
        print(f"ERROR in /api/moonshot-live: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'summary': {
                'starting_balance': 38.87,
                'current_balance': 38.87,
                'total_pnl_usd': 0,
                'total_pnl_pct': 0,
                'model_id': '87033f5ca7fe',
                'model_type': 'CatBoost SHORT',
                'ft_pf': 2.63,
                'ft_wr': 75.8,
                'open_count': 0,
                'closed_count': 0,
                'win_rate': 0,
            },
            'open_positions': [],
            'closed_trades': [],
            'exchange_connected': False,
        }), 500


@app.route("/api/feature-subsets")
@cached(cache=_api_cache, key=lambda: hashkey("feature_subsets"))
def api_feature_subsets():
    """Feature subset distribution across tournament models."""
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"error": "database not found"}), 503

    try:
        # Get all FT + champion models with their params
        sql = """
            SELECT model_id, direction, stage, params, feature_set
            FROM tournament_models
            WHERE stage IN ('forward_test', 'champion', 'backtest')
            ORDER BY created_at DESC
        """
        rows = _safe_query(conn, sql)

        # Categorize by preset vs random
        preset_counts = {}
        random_counts = {}
        ft_champion_subsets = []

        for r in rows:
            try:
                params = json.loads(r["params"])
                fs_type = params.get("feature_set", "unknown")

                # Determine if preset or random
                if isinstance(fs_type, str):
                    # Preset
                    preset_counts[fs_type] = preset_counts.get(fs_type, 0) + 1
                    subset_type = f"preset:{fs_type}"
                    feature_count = None
                elif isinstance(fs_type, list):
                    # Random subset
                    feature_count = len(fs_type)
                    bucket = f"{feature_count // 10 * 10}-{feature_count // 10 * 10 + 9}"
                    random_counts[bucket] = random_counts.get(bucket, 0) + 1
                    subset_type = "random"
                else:
                    subset_type = "unknown"
                    feature_count = None

                # Track FT/champion models separately for detailed view
                if r["stage"] in ("forward_test", "champion"):
                    ft_champion_subsets.append({
                        "model_id": r["model_id"],
                        "direction": r["direction"],
                        "stage": r["stage"],
                        "subset_type": subset_type,
                        "feature_count": feature_count,
                    })
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        total_preset = sum(preset_counts.values())
        total_random = sum(random_counts.values())
        total = total_preset + total_random

        return jsonify({
            "summary": {
                "total_models": total,
                "preset_count": total_preset,
                "random_count": total_random,
                "preset_pct": round(total_preset / total * 100, 1) if total > 0 else 0,
                "random_pct": round(total_random / total * 100, 1) if total > 0 else 0,
            },
            "presets": preset_counts,
            "random_buckets": random_counts,
            "ft_champion_models": ft_champion_subsets,
        })
    finally:
        conn.close()


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.DASHBOARD_PORT, debug=False)
