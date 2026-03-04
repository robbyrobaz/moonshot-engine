"""Moonshot v2 — Read-only Flask Dashboard.

Single-file dashboard serving 9 panels on port 8893 (configurable).
All data sourced from SQLite at config.DB_PATH in read-only mode.
"""

import json
import os
import pickle
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string

import config
from src.db.schema import get_db

app = Flask(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

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
        return "—"
    try:
        return max(0, int((time.time() * 1000 - ts_ms) / 86_400_000))
    except (TypeError, ValueError):
        return "—"


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


# ── Data Loaders ─────────────────────────────────────────────────────────────

def _load_leaderboard(conn):
    sql = """
        SELECT model_id, direction, model_type, stage, bt_pf, bt_precision,
               bt_trades, ft_trades, ft_pnl, ft_pf, ft_max_drawdown_pct,
               is_paused, created_at
        FROM tournament_models
        WHERE stage IN ('forward_test', 'champion')
        ORDER BY ft_pnl DESC
    """
    return _safe_query(conn, sql)


def _load_top_challengers(conn):
    """Top 10 retired challengers by bt_pf — shows tournament activity even with no champion."""
    sql = """
        SELECT model_id, direction, model_type, bt_pf, bt_precision,
               bt_trades, bt_pnl, retire_reason, created_at
        FROM tournament_models
        WHERE stage = 'retired' AND bt_pf > 0
        ORDER BY bt_pf DESC
        LIMIT 10
    """
    return _safe_query(conn, sql)


def _load_champion_history(conn):
    sql = """
        SELECT model_id, direction, promoted_to_champion_at, retired_at,
               ft_pnl, ft_pf, ft_trades
        FROM tournament_models
        WHERE promoted_to_champion_at IS NOT NULL
        ORDER BY promoted_to_champion_at DESC
    """
    return _safe_query(conn, sql)


def _load_open_positions(conn):
    sql = """
        SELECT p.id, p.symbol, p.direction, p.model_id, p.entry_ts,
               p.entry_price, p.entry_ml_score, p.size_usd, p.status,
               p.high_water_price, p.trailing_active,
               c.close AS current_price
        FROM positions p
        LEFT JOIN (
            SELECT symbol, close
            FROM candles
            WHERE (symbol, ts) IN (SELECT symbol, MAX(ts) FROM candles GROUP BY symbol)
        ) c ON p.symbol = c.symbol
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


def _load_feature_importance():
    """Load champion model pickles and extract feature importances."""
    results = {}
    for label, path in [("Long Champion", config.CHAMPION_LONG_PATH),
                        ("Short Champion", config.CHAMPION_SHORT_PATH)]:
        if not path.exists():
            continue
        try:
            with open(path, "rb") as f:
                model = pickle.load(f)
            # LightGBM / XGBoost
            if hasattr(model, "feature_importances_"):
                imp = model.feature_importances_
                names = (model.feature_name_ if hasattr(model, "feature_name_")
                         else [f"f{i}" for i in range(len(imp))])
            # CatBoost
            elif hasattr(model, "feature_importance"):
                imp = model.feature_importance()
                names = (model.feature_names_ if hasattr(model, "feature_names_")
                         else [f"f{i}" for i in range(len(imp))])
            else:
                continue
            paired = sorted(zip(names, imp), key=lambda x: x[1], reverse=True)[:10]
            if paired:
                max_val = max(v for _, v in paired) or 1
                results[label] = [(n, v, v / max_val * 100) for n, v in paired]
        except Exception:
            continue
    return results


def _load_regime(conn):
    # BTC 30-day return from candles
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

    # Fear & Greed
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


def _load_funding(conn):
    sql = """
        SELECT symbol, funding_rate, ts
        FROM funding_rates
        WHERE (symbol, ts) IN (SELECT symbol, MAX(ts) FROM funding_rates GROUP BY symbol)
        ORDER BY ABS(funding_rate) DESC
        LIMIT 50
    """
    return _safe_query(conn, sql)


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


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        # DB doesn't exist yet — render empty state
        return render_template_string(TEMPLATE, **_empty_ctx())

    try:
        leaderboard = _load_leaderboard(conn)
        top_challengers = _load_top_challengers(conn)
        champion_history = _load_champion_history(conn)
        open_positions = _load_open_positions(conn)
        recent_closes = _load_recent_closes(conn)
        feature_importance = _load_feature_importance()
        regime = _load_regime(conn)
        social = _load_social(conn)
        funding = _load_funding(conn)
        health = _load_system_health(conn)

        # Compute summary for recent closes
        closes_summary = {"total_pnl": 0, "wins": 0, "losses": 0, "by_reason": {}}
        for row in recent_closes:
            pnl = row["pnl_pct"] or 0
            closes_summary["total_pnl"] += pnl
            if pnl > 0:
                closes_summary["wins"] += 1
            else:
                closes_summary["losses"] += 1
            reason = row["exit_reason"] or "unknown"
            if reason not in closes_summary["by_reason"]:
                closes_summary["by_reason"][reason] = {"count": 0, "pnl": 0}
            closes_summary["by_reason"][reason]["count"] += 1
            closes_summary["by_reason"][reason]["pnl"] += pnl

        total_trades = closes_summary["wins"] + closes_summary["losses"]
        closes_summary["win_rate"] = (
            closes_summary["wins"] / total_trades * 100 if total_trades > 0 else 0
        )

        # Compute unrealized PnL for open positions
        open_pos_data = []
        for p in open_positions:
            entry = p["entry_price"] or 0
            current = p["current_price"]
            direction = p["direction"]
            upnl = None
            tp_dist = None
            sl_dist = None
            if entry and current:
                if direction == "long":
                    upnl = (current - entry) / entry * 100
                    tp_dist = (entry * (1 + config.TP_PCT) - current) / current * 100
                    sl_dist = (current - entry * (1 - config.SL_PCT)) / current * 100
                else:
                    upnl = (entry - current) / entry * 100
                    tp_dist = (current - entry * (1 - config.TP_PCT)) / current * 100
                    sl_dist = (entry * (1 + config.SL_PCT) - current) / current * 100
            open_pos_data.append({
                "id": p["id"],
                "symbol": p["symbol"],
                "direction": direction,
                "model_id": _truncate(p["model_id"]),
                "entry_ts": _ts_to_str(p["entry_ts"]),
                "entry_price": _fmt_float(entry),
                "current_price": _fmt_float(current) if current else "—",
                "upnl": upnl,
                "upnl_str": _fmt_pct(upnl) if upnl is not None else "—",
                "tp_dist": _fmt_pct(tp_dist) if tp_dist is not None else "—",
                "sl_dist": _fmt_pct(sl_dist) if sl_dist is not None else "—",
            })

        active_models = [m for m in leaderboard if m["stage"] == "forward_test"]
        champion_models = [m for m in leaderboard if m["stage"] == "champion"]
        ft_summary = {
            "active_models": len(active_models),
            "champions": len(champion_models),
            "open_positions": len(open_pos_data),
            "closed_48h": len(recent_closes),
            "wins_48h": closes_summary["wins"],
            "losses_48h": closes_summary["losses"],
            "total_pnl_48h": closes_summary["total_pnl"],
            "win_rate_48h": closes_summary["win_rate"],
            "coins_scored": (health["run"]["coins_scored"] if health.get("run") else 0),
            "last_run_id": (health["run"]["run_id"] if health.get("run") else None),
            "last_run_ended": (health["run"]["ended_at"] if health.get("run") else None),
            "run_errors": (health["run"]["errors"] if health.get("run") else None),
        }

        ctx = {
            "refresh_seconds": config.DASHBOARD_REFRESH_SECONDS,
            "leaderboard": leaderboard,
            "top_challengers": top_challengers,
            "champion_history": champion_history,
            "open_positions": open_pos_data,
            "recent_closes": recent_closes,
            "closes_summary": closes_summary,
            "feature_importance": feature_importance,
            "regime": regime,
            "social": social,
            "funding": funding,
            "health": health,
            "ft_summary": ft_summary,
            "ts_to_str": _ts_to_str,
            "age_days": _age_days,
            "fmt_pct": _fmt_pct,
            "fmt_float": _fmt_float,
            "truncate": _truncate,
            "now_str": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "config": config,
        }
        return render_template_string(TEMPLATE, **ctx)
    finally:
        conn.close()


def _empty_ctx():
    return {
        "refresh_seconds": config.DASHBOARD_REFRESH_SECONDS,
        "leaderboard": [],
        "top_challengers": [],
        "champion_history": [],
        "open_positions": [],
        "recent_closes": [],
        "closes_summary": {"total_pnl": 0, "wins": 0, "losses": 0, "by_reason": {}, "win_rate": 0},
        "feature_importance": {},
        "regime": {"regime": "unknown", "btc_30d_return": None, "market_breadth": None},
        "social": {"mentions": [], "trending": [], "fear_greed": None},
        "funding": [],
        "health": {"run": None, "candle_count": 0, "coin_count": 0, "db_size_mb": 0},
        "ft_summary": {
            "active_models": 0,
            "champions": 0,
            "open_positions": 0,
            "closed_48h": 0,
            "wins_48h": 0,
            "losses_48h": 0,
            "total_pnl_48h": 0,
            "win_rate_48h": 0,
            "coins_scored": 0,
            "last_run_id": None,
            "last_run_ended": None,
            "run_errors": None,
        },
        "ts_to_str": _ts_to_str,
        "age_days": _age_days,
        "fmt_pct": _fmt_pct,
        "fmt_float": _fmt_float,
        "truncate": _truncate,
        "now_str": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "config": config,
    }


@app.route("/api/health")
def api_health():
    try:
        conn = _ro_db()
    except sqlite3.OperationalError:
        return jsonify({"status": "error", "detail": "database not found"}), 503

    try:
        health = _load_system_health(conn)
        run = health["run"]
        return jsonify({
            "status": "ok",
            "db_size_mb": round(health["db_size_mb"], 2),
            "candle_count": health["candle_count"],
            "coin_count": health["coin_count"],
            "last_run_id": run["run_id"] if run else None,
            "last_run_ended": _ts_to_str(run["ended_at"]) if run else None,
            "errors": run["errors"] if run else None,
        })
    finally:
        conn.close()


# ── Template ─────────────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{{ refresh_seconds }}">
<title>Moonshot v2 — Dashboard</title>
<style>
/* ── Reset & Base ──────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    line-height: 1.5;
    padding: 16px;
    min-height: 100vh;
}
a { color: #4fc3f7; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Layout ────────────────────────────────────────────────────────────── */
.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid #0f3460;
}
.header h1 { font-size: 1.6rem; font-weight: 600; color: #fff; }
.header .meta { font-size: 0.85rem; color: #888; }

.grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
}
@media (min-width: 768px) {
    .grid { grid-template-columns: repeat(2, 1fr); }
    .grid .full-width { grid-column: 1 / -1; }
}
@media (min-width: 1200px) {
    .grid { grid-template-columns: repeat(3, 1fr); }
}

/* ── Cards ─────────────────────────────────────────────────────────────── */
.card {
    background: #16213e;
    border-radius: 8px;
    padding: 16px;
    border: 1px solid #0f3460;
}
.card h2 {
    font-size: 1.05rem;
    font-weight: 600;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #0f3460;
    color: #fff;
}
.card .empty { color: #666; font-style: italic; padding: 12px 0; }

/* ── Tables ────────────────────────────────────────────────────────────── */
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
th {
    text-align: left;
    padding: 6px 8px;
    color: #aaa;
    font-weight: 500;
    white-space: nowrap;
    border-bottom: 1px solid #0f3460;
}
td {
    padding: 5px 8px;
    white-space: nowrap;
    border-bottom: 1px solid rgba(15,52,96,0.4);
}
tr:nth-child(even) td { background: rgba(15,52,96,0.15); }
tr:hover td { background: rgba(15,52,96,0.35); }

/* ── Colors ────────────────────────────────────────────────────────────── */
.green { color: #00e676; }
.red { color: #ff1744; }
.gold { color: #ffd700; }
.orange { color: #ff9100; }
.yellow { color: #ffeb3b; }
.muted { color: #888; }

/* ── Badges ────────────────────────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
}
.badge-bull { background: rgba(0,230,118,0.2); color: #00e676; }
.badge-bear { background: rgba(255,23,68,0.2); color: #ff1744; }
.badge-neutral { background: rgba(255,235,59,0.2); color: #ffeb3b; }
.badge-unknown { background: rgba(136,136,136,0.2); color: #888; }
.badge-champion { background: rgba(255,215,0,0.2); color: #ffd700; }
.badge-long { background: rgba(0,230,118,0.15); color: #00e676; }
.badge-short { background: rgba(255,23,68,0.15); color: #ff1744; }

/* ── Feature bars ──────────────────────────────────────────────────────── */
.bar-row { display: flex; align-items: center; margin-bottom: 4px; }
.bar-label {
    width: 140px;
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
}
.bar-track {
    flex: 1;
    background: rgba(15,52,96,0.3);
    height: 14px;
    border-radius: 3px;
    overflow: hidden;
    margin: 0 8px;
}
.bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #0f3460, #4fc3f7);
    border-radius: 3px;
}
.bar-val { font-size: 0.75rem; color: #aaa; width: 50px; text-align: right; flex-shrink: 0; }

/* ── Funding grid ──────────────────────────────────────────────────────── */
.funding-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
    gap: 4px;
}
.funding-cell {
    padding: 6px;
    border-radius: 4px;
    text-align: center;
    font-size: 0.75rem;
}
.funding-cell .sym { font-weight: 600; font-size: 0.72rem; }
.funding-cell .rate { font-size: 0.82rem; margin-top: 2px; }

/* ── Health metrics ────────────────────────────────────────────────────── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
}
.metric {
    background: rgba(15,52,96,0.25);
    border-radius: 6px;
    padding: 10px;
    text-align: center;
}
.metric .val { font-size: 1.3rem; font-weight: 700; color: #fff; }
.metric .lbl { font-size: 0.72rem; color: #888; margin-top: 2px; }

/* ── Summary row ──────────────────────────────────────────────────────── */
.summary-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    padding: 8px 0;
    margin-bottom: 8px;
    border-bottom: 1px solid #0f3460;
}
.summary-item { font-size: 0.85rem; }
.summary-item span { font-weight: 600; }

/* ── NQ-v3 style live summary strip ───────────────────────────────────── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
}
.kpi {
    background: rgba(15,52,96,0.28);
    border: 1px solid rgba(79,195,247,0.20);
    border-radius: 8px;
    padding: 10px;
}
.kpi .k { font-size: 0.72rem; color: #9aa4b2; text-transform: uppercase; letter-spacing: 0.03em; }
.kpi .v { font-size: 1.15rem; font-weight: 700; color: #fff; margin-top: 4px; }
.section-tag {
    display: inline-block;
    margin-bottom: 10px;
    font-size: 0.72rem;
    color: #9aa4b2;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ── Trending list ─────────────────────────────────────────────────────── */
.trending-list { display: flex; flex-wrap: wrap; gap: 6px; }
.trending-tag {
    background: rgba(79,195,247,0.12);
    color: #4fc3f7;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.78rem;
}

/* ── Timeline ──────────────────────────────────────────────────────────── */
.timeline { position: relative; padding-left: 20px; }
.timeline::before {
    content: '';
    position: absolute;
    left: 6px;
    top: 0;
    bottom: 0;
    width: 2px;
    background: #0f3460;
}
.timeline-item {
    position: relative;
    margin-bottom: 12px;
    padding: 8px 12px;
    background: rgba(15,52,96,0.2);
    border-radius: 6px;
}
.timeline-item::before {
    content: '';
    position: absolute;
    left: -18px;
    top: 14px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ffd700;
}
.timeline-item.retired::before { background: #888; }
.timeline-date { font-size: 0.72rem; color: #888; }
.timeline-info { font-size: 0.82rem; margin-top: 2px; }
</style>
</head>
<body>

<div class="header">
    <h1>Moonshot v2</h1>
    <div class="meta">{{ now_str }} &middot; Auto-refresh {{ refresh_seconds }}s</div>
</div>

<div class="grid">

<!-- ── 0. Live FT-PL Summary ───────────────────────────────────────────── -->
<div class="card full-width">
    <div class="section-tag">Live Focus</div>
    <h2>FT-PL Summary (Forward Test — Paper on Live data)</h2>
    <div class="kpi-strip">
        <div class="kpi"><div class="k">Active FT Models</div><div class="v">{{ ft_summary.active_models }}</div></div>
        <div class="kpi"><div class="k">Champions</div><div class="v">{{ ft_summary.champions }}</div></div>
        <div class="kpi"><div class="k">Open Positions</div><div class="v">{{ ft_summary.open_positions }}</div></div>
        <div class="kpi"><div class="k">Closed (48h)</div><div class="v">{{ ft_summary.closed_48h }}</div></div>
        <div class="kpi"><div class="k">Win Rate (48h)</div><div class="v">{{ "%.1f"|format(ft_summary.win_rate_48h) }}%</div></div>
        <div class="kpi"><div class="k">PnL (48h)</div><div class="v {{ 'green' if ft_summary.total_pnl_48h >= 0 else 'red' }}">{{ fmt_pct(ft_summary.total_pnl_48h, 2) }}</div></div>
        <div class="kpi"><div class="k">Coins Scored (last run)</div><div class="v">{{ ft_summary.coins_scored }}</div></div>
        <div class="kpi"><div class="k">Last Run</div><div class="v">{% if ft_summary.last_run_id %}#{{ ft_summary.last_run_id }}{% else %}—{% endif %}</div></div>
    </div>
    <div style="margin-top:10px;font-size:0.82rem;color:#a8b3c2;">
        Mode: <b>FT-PL ON</b> (live data + paper trades) &middot; <b>BLE OFF</b> (no broker execution)
        {% if ft_summary.run_errors %}&middot; <span class="red">Last run error: {{ ft_summary.run_errors }}</span>{% endif %}
    </div>
</div>

<!-- ── 1. Tournament Leaderboard ───────────────────────────────────────── -->
<div class="card full-width">
    <h2>Tournament Leaderboard</h2>
    {% if leaderboard %}
    <div class="tbl-wrap">
    <table>
    <thead><tr>
        <th>Model</th><th>Dir</th><th>Type</th><th>Stage</th>
        <th>BT PF</th><th>BT Prec</th><th>BT Trades</th>
        <th>FT Trades</th><th>FT PnL</th><th>FT PF</th><th>FT DD%</th>
        <th>Age</th><th>Status</th>
    </tr></thead>
    <tbody>
    {% for m in leaderboard %}
    {% set is_champion = m['stage'] == 'champion' %}
    {% set is_paused = m['is_paused'] == 1 %}
    {% set retiring = (m['ft_pf'] is not none and m['ft_pf'] < 1.5 and m['ft_trades'] is not none and m['ft_trades'] >= 15) %}
    <tr>
        <td>
            {% if is_champion %}<span class="gold">{{ truncate(m['model_id']) }}</span>
            {% elif is_paused %}<span class="yellow">{{ truncate(m['model_id']) }}</span>
            {% elif retiring %}<span class="orange">{{ truncate(m['model_id']) }}</span>
            {% else %}<span class="green">{{ truncate(m['model_id']) }}</span>
            {% endif %}
        </td>
        <td><span class="badge badge-{{ m['direction'] or 'long' }}">{{ m['direction'] or '—' }}</span></td>
        <td>{{ m['model_type'] or '—' }}</td>
        <td>
            {% if is_champion %}<span class="badge badge-champion">champion</span>
            {% else %}FT{% endif %}
        </td>
        <td>{{ fmt_float(m['bt_pf'], 2) }}</td>
        <td>{{ fmt_pct(m['bt_precision'] * 100 if m['bt_precision'] else None, 1) }}</td>
        <td>{{ m['bt_trades'] or 0 }}</td>
        <td>{{ m['ft_trades'] or 0 }}</td>
        <td class="{{ 'green' if (m['ft_pnl'] or 0) >= 0 else 'red' }}">{{ fmt_pct(m['ft_pnl'], 2) }}</td>
        <td>{{ fmt_float(m['ft_pf'], 2) }}</td>
        <td class="red">{{ fmt_pct(m['ft_max_drawdown_pct'], 1) }}</td>
        <td>{{ age_days(m['created_at']) }}d</td>
        <td>
            {% if is_champion %}<span class="gold">Champion</span>
            {% elif is_paused %}<span class="yellow">Paused</span>
            {% elif retiring %}<span class="orange">At risk</span>
            {% else %}<span class="green">Active</span>
            {% endif %}
        </td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty">No active FT/champion models yet — see Top Challengers below.</div>
    {% endif %}
</div>

<!-- ── 1b. Top Challengers (best retired models) ─────────────────────── -->
<div class="card full-width">
    <h2>Top 10 Challengers <small style="font-size:0.75em;color:#888">(best backtest scores, gate not yet cleared)</small></h2>
    {% if top_challengers %}
    <div class="tbl-wrap">
    <table>
    <thead><tr>
        <th>Model</th><th>Dir</th><th>Type</th>
        <th>BT PF</th><th>BT Prec</th><th>BT Trades</th><th>BT PnL</th>
        <th>Gate PF ≥ {{ config.MIN_BT_PF }}</th><th>Age</th>
    </tr></thead>
    <tbody>
    {% for m in top_challengers %}
    {% set passes_pf = m['bt_pf'] is not none and m['bt_pf'] >= config.MIN_BT_PF %}
    <tr>
        <td><span class="{{ 'green' if passes_pf else 'yellow' }}">{{ truncate(m['model_id']) }}</span></td>
        <td><span class="badge badge-{{ m['direction'] or 'long' }}">{{ m['direction'] or '—' }}</span></td>
        <td>{{ m['model_type'] or '—' }}</td>
        <td class="{{ 'green' if passes_pf else 'red' }}"><b>{{ fmt_float(m['bt_pf'], 2) }}</b></td>
        <td>{{ fmt_pct(m['bt_precision'] * 100 if m['bt_precision'] else None, 1) }}</td>
        <td>{{ m['bt_trades'] or '—' }}</td>
        <td class="{{ 'green' if (m['bt_pnl'] or 0) >= 0 else 'red' }}">{{ fmt_pct(m['bt_pnl'], 2) if m['bt_pnl'] is not none else '—' }}</td>
        <td>{{ '<span class="green">✓</span>' | safe if passes_pf else '<span class="red">✗</span>' | safe }}</td>
        <td>{{ age_days(m['created_at']) }}d</td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty">No backtest results yet — first cycle still running.</div>
    {% endif %}
</div>

<!-- ── 2. Champion History ─────────────────────────────────────────────── -->
<div class="card">
    <h2>Champion History</h2>
    {% if champion_history %}
    <div class="timeline">
    {% for c in champion_history %}
        <div class="timeline-item {{ 'retired' if c['retired_at'] else '' }}">
            <div class="timeline-date">
                Promoted: {{ ts_to_str(c['promoted_to_champion_at']) }}
                {% if c['retired_at'] %} &mdash; Retired: {{ ts_to_str(c['retired_at']) }}{% endif %}
            </div>
            <div class="timeline-info">
                <span class="{{ 'muted' if c['retired_at'] else 'gold' }}">{{ truncate(c['model_id']) }}</span>
                <span class="badge badge-{{ c['direction'] or 'long' }}">{{ c['direction'] or '—' }}</span>
                &middot; PF {{ fmt_float(c['ft_pf'], 2) }}
                &middot; PnL <span class="{{ 'green' if (c['ft_pnl'] or 0) >= 0 else 'red' }}">{{ fmt_pct(c['ft_pnl'], 2) }}</span>
                &middot; {{ c['ft_trades'] or 0 }} trades
            </div>
        </div>
    {% endfor %}
    </div>
    {% else %}
    <div class="empty">No champions promoted yet.</div>
    {% endif %}
</div>

<!-- ── 3. Open Positions ──────────────────────────────────────────────── -->
<div class="card full-width">
    <div class="section-tag">Live Focus</div>
    <h2>Open Positions (FT-PL) — {{ open_positions|length }}</h2>
    {% if open_positions %}
    <div class="tbl-wrap">
    <table>
    <thead><tr>
        <th>Symbol</th><th>Dir</th><th>Model</th><th>Entry Time</th>
        <th>Entry Price</th><th>Current</th><th>uPnL%</th>
        <th>To TP</th><th>To SL</th>
    </tr></thead>
    <tbody>
    {% for p in open_positions %}
    <tr>
        <td><strong>{{ p.symbol }}</strong></td>
        <td><span class="badge badge-{{ p.direction }}">{{ p.direction }}</span></td>
        <td>{{ p.model_id }}</td>
        <td>{{ p.entry_ts }}</td>
        <td>{{ p.entry_price }}</td>
        <td>{{ p.current_price }}</td>
        <td class="{{ 'green' if p.upnl is not none and p.upnl >= 0 else 'red' }}">{{ p.upnl_str }}</td>
        <td>{{ p.tp_dist }}</td>
        <td>{{ p.sl_dist }}</td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty">No open positions.</div>
    {% endif %}
</div>

<!-- ── 4. Recent Closes (48h) ─────────────────────────────────────────── -->
<div class="card full-width">
    <div class="section-tag">Live Focus</div>
    <h2>Recent Closes (48h FT-PL)</h2>
    {% if recent_closes %}
    <div class="summary-bar">
        <div class="summary-item">Total PnL: <span class="{{ 'green' if closes_summary.total_pnl >= 0 else 'red' }}">{{ fmt_pct(closes_summary.total_pnl, 2) }}</span></div>
        <div class="summary-item">Win Rate: <span>{{ "%.1f"|format(closes_summary.win_rate) }}%</span> ({{ closes_summary.wins }}W / {{ closes_summary.losses }}L)</div>
        {% for reason, data in closes_summary.by_reason.items() %}
        <div class="summary-item">{{ reason }}: <span>{{ data.count }}</span> (<span class="{{ 'green' if data.pnl >= 0 else 'red' }}">{{ fmt_pct(data.pnl, 2) }}</span>)</div>
        {% endfor %}
    </div>
    <div class="tbl-wrap">
    <table>
    <thead><tr>
        <th>Symbol</th><th>Dir</th><th>Model</th><th>Entry</th><th>Exit</th>
        <th>PnL%</th><th>Reason</th><th>Closed At</th>
    </tr></thead>
    <tbody>
    {% for c in recent_closes %}
    <tr>
        <td><strong>{{ c['symbol'] }}</strong></td>
        <td><span class="badge badge-{{ c['direction'] or 'long' }}">{{ c['direction'] or '—' }}</span></td>
        <td>{{ truncate(c['model_id']) }}</td>
        <td>{{ fmt_float(c['entry_price']) }}</td>
        <td>{{ fmt_float(c['exit_price']) }}</td>
        <td class="{{ 'green' if (c['pnl_pct'] or 0) >= 0 else 'red' }}">{{ fmt_pct(c['pnl_pct'], 2) }}</td>
        <td>{{ c['exit_reason'] or '—' }}</td>
        <td>{{ ts_to_str(c['exit_ts']) }}</td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty">No closed positions in the last 48 hours.</div>
    {% endif %}
</div>

<!-- ── 5. Feature Importance ──────────────────────────────────────────── -->
<div class="card">
    <h2>Feature Importance</h2>
    {% if feature_importance %}
    {% for label, features in feature_importance.items() %}
    <h3 style="font-size:0.88rem; color:#aaa; margin: 8px 0 6px;">{{ label }}</h3>
    {% for name, val, pct in features %}
    <div class="bar-row">
        <div class="bar-label">{{ name }}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{{ pct }}%"></div></div>
        <div class="bar-val">{{ "%.0f"|format(val) }}</div>
    </div>
    {% endfor %}
    {% endfor %}
    {% else %}
    <div class="empty">No champion models found.</div>
    {% endif %}
</div>

<!-- ── 6. Regime Monitor ──────────────────────────────────────────────── -->
<div class="card">
    <h2>Regime Monitor</h2>
    <div style="text-align:center; padding: 12px 0;">
        <span class="badge badge-{{ regime.regime }}" style="font-size:1.1rem; padding:6px 16px;">
            {{ regime.regime|upper }}
        </span>
    </div>
    <div class="metric-grid" style="margin-top: 12px;">
        <div class="metric">
            <div class="val {{ 'green' if regime.btc_30d_return is not none and regime.btc_30d_return >= 0 else 'red' }}">
                {{ fmt_pct(regime.btc_30d_return * 100 if regime.btc_30d_return is not none else None, 1) }}
            </div>
            <div class="lbl">BTC 30d Return</div>
        </div>
        <div class="metric">
            <div class="val">{{ fmt_float(regime.market_breadth, 2) if regime.market_breadth is not none else '—' }}</div>
            <div class="lbl">Market Breadth</div>
        </div>
    </div>
</div>

<!-- ── 7. Social Signals ─────────────────────────────────────────────── -->
<div class="card">
    <h2>Social Signals</h2>
    {% if social.fear_greed %}
    <div style="margin-bottom: 12px;">
        <strong>Fear &amp; Greed:</strong>
        {% set fg_val = social.fear_greed['numeric_value'] or 0 %}
        <span style="font-size:1.2rem; font-weight:700;
            color:{% if fg_val < 25 %}#ff1744{% elif fg_val < 50 %}#ff9100{% elif fg_val < 75 %}#ffeb3b{% else %}#00e676{% endif %}">
            {{ "%.0f"|format(fg_val) }}
        </span>
        <span class="muted">{{ social.fear_greed['text_snippet'] or '' }}</span>
    </div>
    {% endif %}
    {% if social.trending %}
    <div style="margin-bottom: 12px;">
        <strong style="font-size:0.82rem;">Trending:</strong>
        <div class="trending-list" style="margin-top:4px;">
        {% for coin in social.trending %}
            <span class="trending-tag">{{ coin }}</span>
        {% endfor %}
        </div>
    </div>
    {% endif %}
    {% if social.mentions %}
    <h3 style="font-size:0.85rem; color:#aaa; margin: 8px 0 6px;">News Mentions (24h)</h3>
    <div class="tbl-wrap">
    <table>
    <thead><tr><th>Symbol</th><th>Mentions</th></tr></thead>
    <tbody>
    {% for m in social.mentions %}
    <tr>
        <td><strong>{{ m['symbol'] }}</strong></td>
        <td>{{ m['mentions_24h'] }}</td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
    </div>
    {% elif not social.fear_greed and not social.trending %}
    <div class="empty">No social data yet.</div>
    {% endif %}
</div>

<!-- ── 8. Funding Rate Heatmap ────────────────────────────────────────── -->
<div class="card">
    <h2>Funding Rates</h2>
    {% if funding %}
    <div class="funding-grid">
    {% for f in funding %}
        {% set rate = f['funding_rate'] or 0 %}
        {% set intensity = [[(rate * 10000)|abs, 100]|min, 10]|max %}
        {% if rate > 0 %}
            {% set bg = 'rgba(255,23,68,' ~ (intensity / 100 * 0.6) ~ ')' %}
        {% elif rate < 0 %}
            {% set bg = 'rgba(33,150,243,' ~ (intensity / 100 * 0.6) ~ ')' %}
        {% else %}
            {% set bg = 'rgba(136,136,136,0.15)' %}
        {% endif %}
        <div class="funding-cell" style="background:{{ bg }}">
            <div class="sym">{{ f['symbol']|replace('-USDT','')|replace('-USD','') }}</div>
            <div class="rate">{{ "%.4f"|format(rate * 100) }}%</div>
        </div>
    {% endfor %}
    </div>
    {% else %}
    <div class="empty">No funding rate data yet.</div>
    {% endif %}
</div>

<!-- ── 9. System Health ──────────────────────────────────────────────── -->
<div class="card">
    <div class="section-tag">Runtime</div>
    <h2>Cycle Health</h2>
    <div class="metric-grid">
        <div class="metric">
            <div class="val">{{ "%.1f"|format(health.db_size_mb) }}MB</div>
            <div class="lbl">DB Size</div>
        </div>
        <div class="metric">
            <div class="val">{{ health.candle_count }}</div>
            <div class="lbl">Candles</div>
        </div>
        <div class="metric">
            <div class="val">{{ health.coin_count }}</div>
            <div class="lbl">Coins</div>
        </div>
        {% if health.run %}
        <div class="metric">
            <div class="val">{{ health.run['coins_scored'] or 0 }}</div>
            <div class="lbl">Coins Scored</div>
        </div>
        {% endif %}
    </div>
    {% if health.run %}
    <div style="margin-top: 14px;">
        <h3 style="font-size:0.85rem; color:#aaa; margin-bottom: 8px;">Last Cycle (Run #{{ health.run['run_id'] }})</h3>
        <div class="tbl-wrap">
        <table>
        <tbody>
            <tr><td>Started</td><td>{{ ts_to_str(health.run['started_at']) }}</td></tr>
            <tr><td>Ended</td><td>{{ ts_to_str(health.run['ended_at']) }}</td></tr>
            {% set cycle_ms = (health.run['ended_at'] or 0) - (health.run['started_at'] or 0) %}
            <tr><td>Duration</td><td>{{ "%.1f"|format(cycle_ms / 1000) }}s</td></tr>
            <tr><td>Regime</td><td>
                <span class="badge badge-{{ health.run['regime'] or 'unknown' }}">{{ health.run['regime'] or 'unknown' }}</span>
            </td></tr>
            <tr><td>Champions</td><td>
                L: {{ truncate(health.run['champion_long_model']) }}
                &middot; S: {{ truncate(health.run['champion_short_model']) }}
            </td></tr>
            <tr><td>Entries</td><td>Long: {{ health.run['entries_long'] or 0 }} &middot; Short: {{ health.run['entries_short'] or 0 }}</td></tr>
            <tr><td>Exits</td><td>
                TP: {{ health.run['exits_tp'] or 0 }}
                &middot; SL: {{ health.run['exits_sl'] or 0 }}
                &middot; Time: {{ health.run['exits_time'] or 0 }}
                &middot; Trail: {{ health.run['exits_trail'] or 0 }}
                &middot; Inval: {{ health.run['exits_invalidation'] or 0 }}
                &middot; Regime: {{ health.run['exits_regime'] or 0 }}
            </td></tr>
            {% if health.run['errors'] %}
            <tr><td>Errors</td><td class="red">{{ health.run['errors'] }}</td></tr>
            {% endif %}
        </tbody>
        </table>
        </div>
    </div>
    {% else %}
    <div class="empty" style="margin-top: 12px;">No cycle runs recorded yet.</div>
    {% endif %}
</div>

</div><!-- grid -->

<div style="text-align:center; padding: 20px 0 8px; color:#444; font-size:0.72rem;">
    Moonshot v2 Dashboard &middot; Read-only &middot; Refresh {{ refresh_seconds }}s
</div>

</body>
</html>
"""

# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.DASHBOARD_PORT, debug=False)
