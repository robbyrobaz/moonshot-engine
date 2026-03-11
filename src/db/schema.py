"""Moonshot v2 — Database schema: all CREATE TABLE statements + init_db().

Uses SQLite with WAL mode for concurrent reads. All tables use INSERT OR IGNORE
for deduplication on natural keys.
"""

import sqlite3
from config import DB_PATH, log

SCHEMA_SQL = """
-- ── Discovered coins ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coins (
    symbol TEXT PRIMARY KEY,
    first_seen_ts INTEGER,
    is_active INTEGER DEFAULT 1,
    days_since_listing INTEGER,
    oldest_candle_ts INTEGER
);

-- ── Raw candles (immutable) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT,
    ts INTEGER,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_candles_symbol ON candles(symbol);

-- ── Extended market data ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS funding_rates (
    symbol TEXT,
    ts INTEGER,
    funding_rate REAL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS open_interest (
    symbol TEXT,
    ts INTEGER,
    oi_contracts REAL,
    oi_usd REAL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS mark_prices (
    symbol TEXT,
    ts INTEGER,
    mark_price REAL,
    index_price REAL,
    PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS tickers_24h (
    symbol TEXT,
    ts INTEGER,
    high_24h REAL,
    low_24h REAL,
    vol_24h REAL,
    price_change_pct REAL,
    PRIMARY KEY (symbol, ts)
);

-- ── Social / news events (append-only) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS social_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    source TEXT,
    ts INTEGER,
    event_type TEXT,
    numeric_value REAL,
    text_snippet TEXT
);
CREATE INDEX IF NOT EXISTS idx_social_events_symbol_ts ON social_events(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_social_events_source_ts ON social_events(source, ts);

-- ── Computed features (JSON blob) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS features (
    symbol TEXT,
    ts INTEGER,
    feature_version TEXT,
    feature_names TEXT,
    feature_values TEXT,
    computed_at INTEGER,
    PRIMARY KEY (symbol, ts, feature_version)
);

-- ── Path-dependent labels ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS labels (
    symbol TEXT,
    ts INTEGER,
    direction TEXT,
    label INTEGER,
    tp_pct REAL,
    sl_pct REAL,
    horizon_bars INTEGER,
    computed_at INTEGER,
    PRIMARY KEY (symbol, ts, direction, tp_pct, sl_pct)
);

-- ── Tournament model registry ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tournament_models (
    model_id TEXT PRIMARY KEY,
    direction TEXT,
    stage TEXT,
    model_type TEXT,
    params TEXT,
    feature_set TEXT,
    feature_version TEXT,
    entry_threshold REAL,
    invalidation_threshold REAL,
    bt_trades INTEGER,
    bt_pf REAL,
    bt_precision REAL,
    bt_pnl REAL,
    bt_ci_lower REAL,
    ft_trades INTEGER DEFAULT 0,
    ft_wins INTEGER DEFAULT 0,
    ft_pnl REAL DEFAULT 0.0,
    ft_pf REAL DEFAULT 0.0,
    ft_max_drawdown_pct REAL DEFAULT 0.0,
    is_paused INTEGER DEFAULT 0,
    paused_until INTEGER,
    created_at INTEGER,
    promoted_to_ft_at INTEGER,
    promoted_to_champion_at INTEGER,
    retired_at INTEGER,
    retire_reason TEXT
);

-- ── Positions (one record per trade) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    direction TEXT,
    model_id TEXT,
    is_champion_trade INTEGER DEFAULT 0,
    entry_ts INTEGER,
    entry_price REAL,
    entry_ml_score REAL,
    entry_features TEXT,
    exit_ts INTEGER,
    exit_price REAL,
    exit_reason TEXT,
    leverage INTEGER DEFAULT 1,
    pnl_pct REAL,
    high_water_price REAL,
    trailing_active INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',
    size_usd REAL,
    FOREIGN KEY (model_id) REFERENCES tournament_models(model_id)
);
CREATE INDEX IF NOT EXISTS idx_positions_model ON positions(model_id, status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_unique_open
    ON positions(symbol, direction, is_champion_trade)
    WHERE status = 'open';

-- ── Per-coin model confidence ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coin_model_confidence (
    symbol TEXT,
    model_id TEXT,
    consecutive_losses INTEGER DEFAULT 0,
    consecutive_wins INTEGER DEFAULT 0,
    last_10_trades_pf REAL,
    confidence_multiplier REAL DEFAULT 1.0,
    last_updated INTEGER,
    PRIMARY KEY (symbol, model_id)
);

-- ── Cycle run log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER,
    ended_at INTEGER,
    regime TEXT,
    coins_scored INTEGER,
    champion_long_model TEXT,
    champion_short_model TEXT,
    entries_long INTEGER DEFAULT 0,
    entries_short INTEGER DEFAULT 0,
    exits_tp INTEGER DEFAULT 0,
    exits_sl INTEGER DEFAULT 0,
    exits_time INTEGER DEFAULT 0,
    exits_trail INTEGER DEFAULT 0,
    exits_invalidation INTEGER DEFAULT 0,
    exits_regime INTEGER DEFAULT 0,
    errors TEXT
);
"""


def get_db(db_path=None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and row factory."""
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path, timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=120000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None) -> sqlite3.Connection:
    """Create all tables if they don't exist. Returns connection."""
    conn = get_db(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    log.info("Database initialized at %s", db_path or DB_PATH)
    return conn
