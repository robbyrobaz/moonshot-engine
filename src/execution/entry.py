"""Moonshot v2 — Champion model entry logic.

Called every 4h cycle. Scores all coins with the current champion models
and opens paper positions for signals that pass the entry threshold.
"""

import json
import sqlite3

import joblib

import config
from config import log
from src.features.compute import compute_features


def _get_symbol_whitelist(db: sqlite3.Connection) -> set[str]:
    """Build symbol whitelist from manual config + profitable trade history."""
    manual_symbols = set(config.SYMBOL_WHITELIST)
    min_trades = int(config.SYMBOL_WHITELIST_MIN_TRADES)
    rows = db.execute(
        """SELECT symbol
           FROM positions
           WHERE status = 'closed' AND pnl_pct IS NOT NULL
           GROUP BY symbol
           HAVING SUM(pnl_pct) > 0 AND COUNT(*) >= ?""",
        (min_trades,),
    ).fetchall()
    auto_symbols = {r["symbol"] for r in rows}
    whitelist = manual_symbols | auto_symbols
    if whitelist:
        log.info(
            "score_and_enter: symbol whitelist size=%d (auto=%d manual=%d min_trades=%d)",
            len(whitelist),
            len(auto_symbols),
            len(manual_symbols),
            min_trades,
        )
    else:
        log.warning(
            "score_and_enter: symbol whitelist empty; trading all active symbols"
        )
    return whitelist


def _get_active_symbols(db: sqlite3.Connection) -> list[dict]:
    """Return all active coins with their metadata."""
    rows = db.execute(
        "SELECT symbol, days_since_listing FROM coins WHERE is_active = 1"
    ).fetchall()
    return [{"symbol": r["symbol"], "days_since_listing": r["days_since_listing"]} for r in rows]


def _get_current_price(db: sqlite3.Connection, symbol: str) -> float | None:
    """Get the latest close price from candles table."""
    row = db.execute(
        "SELECT close FROM candles WHERE symbol = ? ORDER BY ts DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    return row["close"] if row else None


def _count_open_positions(db: sqlite3.Connection, direction: str) -> int:
    """Count open champion positions for a given direction."""
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM positions WHERE direction = ? AND status = 'open' AND is_champion_trade = 1",
        (direction,),
    ).fetchone()
    return row["cnt"]


def _has_open_position(db: sqlite3.Connection, symbol: str, direction: str) -> bool:
    """Check if there is already an open champion position for this symbol+direction."""
    row = db.execute(
        "SELECT 1 FROM positions WHERE symbol = ? AND direction = ? AND status = 'open' AND is_champion_trade = 1 LIMIT 1",
        (symbol, direction),
    ).fetchone()
    return row is not None


def _get_confidence_multiplier(db: sqlite3.Connection, symbol: str, model_id: str) -> float:
    """Get confidence multiplier from coin_model_confidence table.

    Returns 1.0 if no record exists (new symbol/model pair).
    """
    row = db.execute(
        "SELECT confidence_multiplier FROM coin_model_confidence "
        "WHERE symbol = ? AND model_id = ?",
        (symbol, model_id),
    ).fetchone()
    return row["confidence_multiplier"] if row else 1.0


def _get_symbol_ft_pnl_ranks(db: sqlite3.Connection, direction: str) -> dict[str, int]:
    """Rank symbols by cumulative closed champion-trade pnl_pct (best first)."""
    rows = db.execute(
        """SELECT symbol, SUM(pnl_pct) AS ft_pnl
           FROM positions
           WHERE status = 'closed'
             AND is_champion_trade = 1
             AND direction = ?
             AND pnl_pct IS NOT NULL
           GROUP BY symbol
           ORDER BY ft_pnl DESC""",
        (direction,),
    ).fetchall()
    return {row["symbol"]: i + 1 for i, row in enumerate(rows)}


def _get_symbol_rank_multiplier(symbol: str, rank_map: dict[str, int], top_n: int = 3) -> float:
    """Map symbol FT rank into top/middle/bottom sizing tiers."""
    if symbol not in rank_map:
        return 1.0

    rank = rank_map[symbol]
    total = len(rank_map)
    if rank <= top_n:
        return 1.5

    # For small universes, prefer top-tier over bottom-tier overlap.
    bottom_start_rank = max(top_n + 1, total - top_n + 1)
    if rank >= bottom_start_rank:
        return 0.75
    return 1.0


def _compute_position_size(
    days_since_listing: int | None,
    confidence_mult: float,
    symbol_mult: float,
) -> float:
    """Compute position size in USD.

    base_size = PAPER_ACCOUNT_SIZE * BASE_POSITION_PCT  (2% = $2000)
    new_listing_boost applied if coin listed < NEW_LISTING_DAYS ago
    final_size = base_size * symbol_mult * new_listing_boost * confidence_mult
    safety cap = PAPER_ACCOUNT_SIZE * MAX_POSITION_PCT
    """
    base_size = config.PAPER_ACCOUNT_SIZE * config.BASE_POSITION_PCT
    if days_since_listing is not None and days_since_listing < config.NEW_LISTING_DAYS:
        boost = config.NEW_LISTING_BOOST
    else:
        boost = 1.0
    raw_size = base_size * symbol_mult * boost * confidence_mult
    size_cap = config.PAPER_ACCOUNT_SIZE * config.MAX_POSITION_PCT
    return min(raw_size, size_cap)


def score_and_enter(
    db: sqlite3.Connection,
    long_champion: dict | None,
    short_champion: dict | None,
    regime: str,
    ts_ms: int,
) -> dict:
    """Score all coins with champion models and open paper positions.

    Args:
        db: sqlite3 connection with row_factory = sqlite3.Row
        long_champion: dict with keys {model, model_id, entry_threshold,
            invalidation_threshold, feature_set, feature_version} or None
        short_champion: same structure, or None
        regime: 'bull', 'neutral', or 'bear'
        ts_ms: current timestamp in milliseconds

    Returns:
        dict with {entries_long: int, entries_short: int, coins_scored: int}
    """
    symbols = _get_active_symbols(db)
    whitelist = _get_symbol_whitelist(db)
    symbols_to_score = (
        [coin for coin in symbols if coin["symbol"] in whitelist] if whitelist else symbols
    )
    result = {
        "entries_long": 0,
        "entries_short": 0,
        "coins_scored": len(symbols_to_score),
    }

    directions = []
    if long_champion is not None and regime != "bear":
        directions.append(("long", long_champion, config.MAX_LONG_POSITIONS))
    if short_champion is not None:
        directions.append(("short", short_champion, config.MAX_SHORT_POSITIONS))

    for direction, champion, max_positions in directions:
        symbol_rank_map = _get_symbol_ft_pnl_ranks(db, direction)
        model = champion["model"]
        model_id = champion["model_id"]
        feature_set = champion["feature_set"]
        entry_threshold = float(champion["entry_threshold"])

        # Compute features and score all symbols
        scored = []
        for coin in symbols_to_score:
            symbol = coin["symbol"]
            try:
                features = compute_features(
                    symbol, ts_ms, db, feature_names=feature_set
                )
            except Exception as e:
                log.warning("score_and_enter: features failed for %s: %s", symbol, e)
                continue

            # Build feature vector in the order expected by the model
            fv_dict = features["feature_values"]
            feature_values = [fv_dict.get(f) for f in feature_set]
            if any(v is None for v in feature_values):
                log.debug("score_and_enter: missing features for %s, skipping", symbol)
                continue

            try:
                proba = model.predict_proba([feature_values])[0][1]
            except Exception as e:
                log.warning("score_and_enter: predict_proba failed for %s: %s", symbol, e)
                continue

            if proba >= entry_threshold:
                scored.append({
                    "symbol": symbol,
                    "score": proba,
                    "features": features,
                    "feature_values": feature_values,
                    "days_since_listing": coin["days_since_listing"],
                })

        # Rank by score descending, take top N
        scored.sort(key=lambda x: x["score"], reverse=True)
        top_signals = scored[: config.TOP_N_SIGNALS]

        for signal in top_signals:
            symbol = signal["symbol"]

            # Skip if already in open position for this symbol+direction
            if _has_open_position(db, symbol, direction):
                log.debug("score_and_enter: already open %s %s, skipping", direction, symbol)
                continue

            # Skip if max positions reached
            if _count_open_positions(db, direction) >= max_positions:
                log.info("score_and_enter: max %s positions reached", direction)
                break

            # Check confidence multiplier
            confidence_mult = _get_confidence_multiplier(db, symbol, model_id)
            if confidence_mult == 0.0:
                log.info(
                    "score_and_enter: confidence=0 for %s/%s, skipping",
                    symbol, model_id,
                )
                continue

            # Get entry price
            entry_price = _get_current_price(db, symbol)
            if entry_price is None:
                log.warning("score_and_enter: no price for %s, skipping", symbol)
                continue

            # Compute position size
            symbol_mult = _get_symbol_rank_multiplier(symbol, symbol_rank_map, top_n=3)
            size_usd = _compute_position_size(
                signal["days_since_listing"], confidence_mult, symbol_mult
            )

            # Snapshot entry features as JSON
            entry_features_json = json.dumps(signal["features"])

            # INSERT position
            try:
                db.execute(
                    """INSERT INTO positions
                       (symbol, direction, model_id, is_champion_trade,
                        entry_ts, entry_price, entry_ml_score, entry_features,
                        high_water_price, status, size_usd, leverage)
                       VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                    (
                        symbol,
                        direction,
                        model_id,
                        ts_ms,
                        entry_price,
                        signal["score"],
                        entry_features_json,
                        entry_price,  # high_water_price starts at entry
                        size_usd,
                        config.LEVERAGE,
                    ),
                )
            except sqlite3.IntegrityError:
                # Open position already exists for symbol+direction (unique-open invariant)
                log.debug("score_and_enter: duplicate open prevented for %s %s", direction, symbol)
                continue

            result_key = f"entries_{direction}"
            result[result_key] += 1
            log.info(
                "ENTRY %s %s @ %.6f  score=%.3f  size=$%.0f  symbol_mult=%.2f",
                direction.upper(),
                symbol,
                entry_price,
                signal["score"],
                size_usd,
                symbol_mult,
            )

    db.commit()
    return result
