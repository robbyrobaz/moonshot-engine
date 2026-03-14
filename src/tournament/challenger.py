"""Moonshot v2 — Challenger generation: random model variant sampling."""

import hashlib
import json
import random
import time

from config import CHALLENGER_COUNT_PER_HOUR, log
from src.db.schema import get_db

# ── Parameter space for random sampling ─────────────────────────────────────
PARAM_SPACE = {
    "model_type": ["lightgbm", "xgboost", "catboost"],
    "n_estimators": [100, 200, 500],
    "learning_rate": [0.01, 0.05, 0.1],
    "num_leaves": [31, 63, 127],          # LGB only
    "max_depth": [4, 6, 8, 10],
    "neg_class_weight": [3, 5, 8, 10],
    "confidence_threshold": [0.30, 0.40, 0.50, 0.60, 0.70],
    "direction": ["long", "short"],
}

# ── Feature subsets ─────────────────────────────────────────────────────────
# Core (25 features — always available from candles)
_CORE_FEATURES = [
    # Price Action (6)
    "price_vs_52w_high", "price_vs_52w_low",
    "momentum_4w", "momentum_8w",
    "bb_squeeze_pct", "bb_position",
    # Volume (5)
    "volume_ratio_7d", "volume_ratio_3d",
    "obv_slope", "volume_spike", "volume_trend",
    # Volatility (4)
    "atr_percentile", "atr_compression",
    "high_low_range_pct", "realized_vol_ratio",
    # Price Structure (5)
    "distance_from_support", "distance_from_resistance",
    "consec_down_bars", "consec_up_bars", "higher_highs",
    # Market Regime (3 — from BTC)
    "btc_30d_return", "btc_vol_percentile", "market_breadth",
    # Coin Metadata (2)
    "days_since_listing", "is_new_listing",
]

# Extended (12 additional features — requires 30+ days of API data)
_EXTENDED_FEATURES = [
    # Funding Rate (3)
    "funding_rate_current", "funding_rate_7d_avg", "funding_rate_extreme",
    # Open Interest (4)
    "oi_change_24h", "oi_change_7d", "oi_price_divergence", "oi_percentile_90d",
    # Mark/Index (1)
    "mark_index_spread",
    # Ticker (4)
    "price_vs_24h_high", "price_vs_24h_low",
    "vol_24h_vs_7d_avg", "price_change_24h_pct",
]

# Social features
_SOCIAL_FEATURES = [
    "fear_greed_score", "fear_greed_7d_change",
    "is_coingecko_trending", "trending_rank", "hours_on_trending",
    "news_mentions_24h", "news_mentions_7d_avg", "news_velocity_ratio",
    "reddit_mentions_24h", "reddit_score_24h", "reddit_velocity_ratio",
    "github_commits_7d", "github_commit_spike",
]

FEATURE_SUBSETS = {
    "all": _CORE_FEATURES + _EXTENDED_FEATURES + _SOCIAL_FEATURES,
    "core_only": _CORE_FEATURES,
    "price_volume": [
        "price_vs_52w_high", "price_vs_52w_low",
        "momentum_4w", "momentum_8w",
        "bb_squeeze_pct", "bb_position",
        "volume_ratio_7d", "volume_ratio_3d",
        "obv_slope", "volume_spike", "volume_trend",
        "btc_30d_return", "btc_vol_percentile", "market_breadth",
        "days_since_listing", "is_new_listing",
    ],
    "no_social": _CORE_FEATURES + _EXTENDED_FEATURES,
    "extended_only": _CORE_FEATURES + _EXTENDED_FEATURES,
}


def _make_model_id(params: dict) -> str:
    """Deterministic model ID from sorted JSON of params."""
    blob = json.dumps(params, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _sample_params(forced_direction: str | None = None) -> dict:
    """Sample one random challenger configuration."""
    params = {}
    for key, choices in PARAM_SPACE.items():
        if key == "direction" and forced_direction is not None:
            params[key] = forced_direction
        else:
            params[key] = random.choice(choices)
    params["feature_set"] = random.choice(list(FEATURE_SUBSETS.keys()))
    return params


def generate_challengers(db, n: int = None) -> list[dict]:
    """Generate n random challenger model variants.

    Each challenger gets a deterministic model_id from its params hash.
    Skips if model_id already exists in tournament_models.
    Inserts new challengers with stage='backtest'.

    Returns list of param dicts for newly created challengers.
    """
    if n is None:
        n = CHALLENGER_COUNT_PER_HOUR

    now_ms = int(time.time() * 1000)
    created = []

    # Force directional balance per cycle to avoid short-only drift.
    target_dirs = (["long", "short"] * ((n + 1) // 2))[:n]

    for i in range(n * 4):  # oversample to account for duplicates
        if len(created) >= n:
            break

        forced_direction = target_dirs[len(created)] if len(created) < len(target_dirs) else None
        params = _sample_params(forced_direction=forced_direction)
        model_id = _make_model_id(params)
        feature_set = json.dumps(FEATURE_SUBSETS[params["feature_set"]])

        # Check if already exists
        row = db.execute(
            "SELECT model_id FROM tournament_models WHERE model_id = ?",
            (model_id,),
        ).fetchone()
        if row is not None:
            continue

        json.loads(feature_set)

        # Insert new challenger
        db.execute(
            """INSERT INTO tournament_models
               (model_id, direction, stage, model_type, params, feature_set,
                entry_threshold, created_at)
               VALUES (?, ?, 'backtest', ?, ?, ?, ?, ?)""",
            (
                model_id,
                params["direction"],
                params["model_type"],
                json.dumps(params, sort_keys=True),
                feature_set,
                params["confidence_threshold"],
                now_ms,
            ),
        )
        params["model_id"] = model_id
        created.append(params)

    db.commit()
    log.info("generate_challengers: created %d new challengers", len(created))
    return created
