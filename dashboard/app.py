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

import sys
sys.path.insert(0, '..')
import config

app = Flask(__name__)

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
    btc_sql = """
        SELECT close FROM candles
        WHERE symbol LIKE '%BTC%'
        ORDER BY ts DESC LIMIT 1
    """
    btc_30d_sql = """
        SELECT close FROM candles
        WHERE symbol LIKE '%BTC%'
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


@app.route("/api/health")
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


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.DASHBOARD_PORT, debug=False)
