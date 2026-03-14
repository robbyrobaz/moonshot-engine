"""Moonshot v2 — Exit logic for open positions.

Checked every 4h cycle. Evaluates all open positions against six exit
conditions in strict priority order (first match wins).
"""

import sqlite3

import config
from config import log


# ── Helper functions ─────────────────────────────────────────────────────────


def get_current_price(db: sqlite3.Connection, symbol: str) -> float | None:
    """Get latest close price from candles table."""
    row = db.execute(
        "SELECT close FROM candles WHERE symbol = ? ORDER BY ts DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    return row["close"] if row else None


def compute_pnl_pct(entry_price: float, exit_price: float, direction: str) -> float:
    """Compute PnL percentage for a trade, including leverage.

    Long:  (exit - entry) / entry * LEVERAGE
    Short: (entry - exit) / entry * LEVERAGE
    """
    import config as _config
    if direction == "long":
        return (exit_price - entry_price) / entry_price * _config.LEVERAGE
    else:
        return (entry_price - exit_price) / entry_price * _config.LEVERAGE


def update_high_water(
    db: sqlite3.Connection,
    position_id: int,
    current_price: float,
    direction: str,
    current_hwp: float,
):
    """Update high_water_price tracking for a position.

    Long: track highest price since entry.
    Short: track lowest price since entry.
    """
    if direction == "long":
        new_hwp = max(current_hwp, current_price)
    else:
        new_hwp = min(current_hwp, current_price)

    if new_hwp != current_hwp:
        db.execute(
            "UPDATE positions SET high_water_price = ? WHERE id = ?",
            (new_hwp, position_id),
        )
    return new_hwp


def update_confidence(db: sqlite3.Connection, symbol: str, model_id: str, is_win: bool):
    """Update coin_model_confidence after a trade closes.

    Win:  consecutive_wins += 1, consecutive_losses = 0
    Loss: consecutive_losses += 1, consecutive_wins = 0

    Confidence multiplier rules:
    - 5+ consecutive losses -> 0.0
    - 3+ consecutive losses -> 0.5
    - Each win recovers +0.25 toward 1.0 (capped at 1.0)
    """
    row = db.execute(
        "SELECT consecutive_losses, consecutive_wins, confidence_multiplier "
        "FROM coin_model_confidence WHERE symbol = ? AND model_id = ?",
        (symbol, model_id),
    ).fetchone()

    if row is None:
        # First trade for this symbol/model pair
        if is_win:
            c_wins, c_losses, mult = 1, 0, 1.0
        else:
            c_wins, c_losses, mult = 0, 1, 1.0
        db.execute(
            """INSERT INTO coin_model_confidence
               (symbol, model_id, consecutive_losses, consecutive_wins,
                confidence_multiplier, last_updated)
               VALUES (?, ?, ?, ?, ?, strftime('%s','now') * 1000)""",
            (symbol, model_id, c_losses, c_wins, mult),
        )
    else:
        c_losses = row["consecutive_losses"]
        c_wins = row["consecutive_wins"]
        mult = row["confidence_multiplier"]

        if is_win:
            c_wins += 1
            c_losses = 0
            mult = min(1.0, mult + config.CONFIDENCE_RECOVERY_PER_WIN)
        else:
            c_losses += 1
            c_wins = 0
            if c_losses >= config.CONSEC_LOSS_SKIP:
                mult = 0.0
            elif c_losses >= config.CONSEC_LOSS_HALF:
                mult = 0.5

        db.execute(
            """UPDATE coin_model_confidence
               SET consecutive_losses = ?, consecutive_wins = ?,
                   confidence_multiplier = ?,
                   last_updated = strftime('%s','now') * 1000
               WHERE symbol = ? AND model_id = ?""",
            (c_losses, c_wins, mult, symbol, model_id),
        )


def _close_position(
    db: sqlite3.Connection,
    position: sqlite3.Row,
    exit_price: float,
    exit_reason: str,
    pnl_pct: float,
    ts_ms: int,
):
    """Close a position and update confidence."""
    db.execute(
        """UPDATE positions
           SET status = 'closed', exit_ts = ?, exit_price = ?,
               exit_reason = ?, pnl_pct = ?
           WHERE id = ?""",
        (ts_ms, exit_price, exit_reason, pnl_pct, position["id"]),
    )
    is_win = pnl_pct > 0
    update_confidence(db, position["symbol"], position["model_id"], is_win)
    log.info(
        "EXIT %s %s %s  pnl=%.2f%%  reason=%s",
        position["direction"].upper(),
        position["symbol"],
        position["model_id"][:8],
        pnl_pct * 100,
        exit_reason,
    )


def _load_invalidation_threshold(db: sqlite3.Connection, model_id: str):
    """Load the model's invalidation threshold."""
    row = db.execute(
        "SELECT invalidation_threshold FROM tournament_models WHERE model_id = ?",
        (model_id,),
    ).fetchone()
    if row is None:
        log.warning("_load_invalidation_threshold: model %s not found in DB", model_id)
        return None
    return row["invalidation_threshold"]


# ── Main exit check ──────────────────────────────────────────────────────────


def check_exits(
    db: sqlite3.Connection,
    long_champion: dict | None,
    short_champion: dict | None,
    regime: str,
    ts_ms: int,
) -> dict:
    """Check all open positions and close those that hit exit conditions.

    Exit conditions are checked in strict priority order (first match wins):
    1. TAKE_PROFIT
    2. STOP_LOSS
    3. TRAILING_STOP
    4. TIME_STOP
    5. INVALIDATION
    6. REGIME_EXIT

    Args:
        db: sqlite3 connection with row_factory = sqlite3.Row
        long_champion: champion dict or None (used for context, not exit scoring)
        short_champion: champion dict or None
        regime: 'bull', 'neutral', or 'bear'
        ts_ms: current timestamp in milliseconds

    Returns:
        dict with {exits_tp, exits_sl, exits_trail, exits_time,
                    exits_invalidation, exits_regime}
    """
    counts = {
        "exits_tp": 0,
        "exits_sl": 0,
        "exits_trail": 0,
        "exits_time": 0,
        "exits_invalidation": 0,
        "exits_regime": 0,
    }

    open_positions = db.execute(
        "SELECT * FROM positions WHERE status = 'open'"
    ).fetchall()

    for pos in open_positions:
        symbol = pos["symbol"]
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        position_id = pos["id"]
        model_id = pos["model_id"]
        hwp = pos["high_water_price"]
        entry_ts = pos["entry_ts"]

        current_price = get_current_price(db, symbol)
        if current_price is None:
            log.warning("check_exits: no price for %s, skipping position %d", symbol, position_id)
            continue

        # Update high water price every cycle
        hwp = update_high_water(db, position_id, current_price, direction, hwp)

        bars_since_entry = (ts_ms - entry_ts) / (4 * 3600 * 1000)

        # ── 1. TAKE_PROFIT ───────────────────────────────────────────────
        tp_hit = False
        if direction == "long":
            tp_hit = current_price >= entry_price * (1 + config.TP_PCT)
        else:
            tp_hit = current_price <= entry_price * (1 - config.TP_PCT)

        if tp_hit:
            pnl = compute_pnl_pct(entry_price, current_price, direction)
            _close_position(db, pos, current_price, "TAKE_PROFIT", pnl, ts_ms)
            counts["exits_tp"] += 1
            continue

        # ── 2. STOP_LOSS ─────────────────────────────────────────────────
        sl_hit = False
        if direction == "long":
            sl_hit = current_price <= entry_price * (1 - config.SL_PCT)
        else:
            sl_hit = current_price >= entry_price * (1 + config.SL_PCT)

        if sl_hit:
            pnl = compute_pnl_pct(entry_price, current_price, direction)
            _close_position(db, pos, current_price, "STOP_LOSS", pnl, ts_ms)
            counts["exits_sl"] += 1
            continue

        # ── 3. TRAILING_STOP ─────────────────────────────────────────────
        trailing_active = bool(pos["trailing_active"])

        # Check if trailing should activate
        if not trailing_active:
            if direction == "long":
                activate = hwp >= entry_price * (1 + config.TRAIL_ACTIVATE_PCT)
            else:
                activate = hwp <= entry_price * (1 - config.TRAIL_ACTIVATE_PCT)
            if activate:
                trailing_active = True
                db.execute(
                    "UPDATE positions SET trailing_active = 1 WHERE id = ?",
                    (position_id,),
                )
                log.info(
                    "TRAILING activated for %s %s (hwp=%.6f)",
                    direction.upper(), symbol, hwp,
                )

        # Check if trailing stop triggers
        if trailing_active:
            trail_hit = False
            if direction == "long":
                trail_hit = current_price <= hwp * (1 - config.TRAIL_DISTANCE_PCT)
            else:
                trail_hit = current_price >= hwp * (1 + config.TRAIL_DISTANCE_PCT)

            if trail_hit:
                pnl = compute_pnl_pct(entry_price, current_price, direction)
                _close_position(db, pos, current_price, "TRAILING_STOP", pnl, ts_ms)
                counts["exits_trail"] += 1
                continue

        # ── 4. TIME_STOP ─────────────────────────────────────────────────
        if bars_since_entry > config.TIME_STOP_BARS:
            pnl = compute_pnl_pct(entry_price, current_price, direction)
            _close_position(db, pos, current_price, "TIME_STOP", pnl, ts_ms)
            counts["exits_time"] += 1
            continue

        # ── 5. INVALIDATION ──────────────────────────────────────────────
        if bars_since_entry >= config.INVALIDATION_GRACE_BARS:
            inv_threshold = _load_invalidation_threshold(db, model_id)
            entry_score = pos["entry_ml_score"]
            if (
                inv_threshold is not None
                and entry_score is not None
                and entry_score < inv_threshold
            ):
                pnl = compute_pnl_pct(entry_price, current_price, direction)
                _close_position(
                    db, pos, current_price, "INVALIDATION", pnl, ts_ms
                )
                counts["exits_invalidation"] += 1
                continue

        # ── 6. REGIME_EXIT ───────────────────────────────────────────────
        if regime == "bear" and direction == "long":
            pnl = compute_pnl_pct(entry_price, current_price, direction)
            _close_position(db, pos, current_price, "REGIME_EXIT", pnl, ts_ms)
            counts["exits_regime"] += 1
            continue

    db.commit()
    return counts
