"""Moonshot v2 — Challenger generation: random model variant sampling."""

import hashlib
import json
import random
import time

from config import CHALLENGER_COUNT_PER_CYCLE, LONG_DISABLED, log
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

_PRICE_FEATURES = [
    "price_vs_52w_high", "price_vs_52w_low",
    "momentum_4w", "momentum_8w",
    "bb_squeeze_pct", "bb_position",
    "distance_from_support", "distance_from_resistance",
    "consec_down_bars", "consec_up_bars", "higher_highs",
    "price_vs_24h_high", "price_vs_24h_low", "price_change_24h_pct",
]

_VOLUME_FEATURES = [
    "volume_ratio_7d", "volume_ratio_3d",
    "obv_slope", "volume_spike", "volume_trend",
    "vol_24h_vs_7d_avg",
    "oi_change_24h", "oi_change_7d", "oi_price_divergence", "oi_percentile_90d",
]

_VOLATILITY_FEATURES = [
    "atr_percentile", "atr_compression",
    "high_low_range_pct", "realized_vol_ratio",
    "mark_index_spread", "funding_rate_current",
    "funding_rate_7d_avg", "funding_rate_extreme",
]

_REGIME_FEATURES = [
    "btc_30d_return", "btc_vol_percentile", "market_breadth",
]

_NON_SOCIAL_FEATURES = sorted(set(_CORE_FEATURES + _EXTENDED_FEATURES))
_ALL_FEATURES = _CORE_FEATURES + _EXTENDED_FEATURES + _SOCIAL_FEATURES

FEATURE_SUBSETS = {
    "all": _ALL_FEATURES,
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

_RANDOM_SUBSET_FOCUS_AREAS = (
    "price_heavy",
    "volume_heavy",
    "volatility_heavy",
    "regime_aware",
    "social_boost",
    "minimal",
    "maximal",
)


def _sample_unique_features(pool: list[str], count: int, required: list[str] | None = None) -> list[str]:
    """Sample a deduplicated feature list with optional required features."""
    required = list(dict.fromkeys(required or []))
    base = [feature for feature in required if feature in pool]
    remaining = [feature for feature in pool if feature not in base]
    extra_count = max(0, min(count - len(base), len(remaining)))
    sampled = random.sample(remaining, k=extra_count) if extra_count else []
    return base + sampled


def generate_random_feature_subset(focus_area: str | None = None) -> list[str]:
    """Generate a random feature subset biased toward one discovery focus area."""
    focus_area = focus_area or random.choice(_RANDOM_SUBSET_FOCUS_AREAS)
    if focus_area not in _RANDOM_SUBSET_FOCUS_AREAS:
        raise ValueError(f"Unknown focus area: {focus_area}")

    if focus_area == "maximal":
        return list(_ALL_FEATURES)

    if focus_area == "social_boost":
        return list(dict.fromkeys(_CORE_FEATURES + _SOCIAL_FEATURES))

    if focus_area == "minimal":
        subset_size = random.randint(10, 15)
        required = random.sample(_CORE_FEATURES, k=min(4, subset_size))
        return sorted(_sample_unique_features(_NON_SOCIAL_FEATURES, subset_size, required))

    if focus_area == "regime_aware":
        regime_count = max(1, min(len(_REGIME_FEATURES), random.randint(5, 9) // 2))
        market_count = random.randint(5, 9)
        regime = random.sample(_REGIME_FEATURES, k=regime_count)
        market_pool = sorted(set(_PRICE_FEATURES + _VOLUME_FEATURES) - set(regime))
        market = random.sample(market_pool, k=min(market_count, len(market_pool)))
        return sorted(set(regime + market))

    if focus_area == "price_heavy":
        primary_pool = _PRICE_FEATURES
        secondary_pool = sorted(set(_ALL_FEATURES) - set(_PRICE_FEATURES))
        subset_size = random.randint(14, 24)
        primary_ratio = 0.8
    elif focus_area == "volume_heavy":
        primary_pool = _VOLUME_FEATURES
        secondary_pool = sorted(set(_ALL_FEATURES) - set(_VOLUME_FEATURES))
        subset_size = random.randint(14, 24)
        primary_ratio = 0.8
    else:
        primary_pool = _VOLATILITY_FEATURES
        secondary_pool = sorted(set(_ALL_FEATURES) - set(_VOLATILITY_FEATURES))
        subset_size = random.randint(12, 22)
        primary_ratio = 0.8

    primary_target = max(1, min(len(primary_pool), round(subset_size * primary_ratio)))
    secondary_target = max(0, subset_size - primary_target)
    primary = random.sample(primary_pool, k=primary_target)
    secondary = random.sample(secondary_pool, k=min(secondary_target, len(secondary_pool)))
    return sorted(set(primary + secondary))


def resolve_feature_set(feature_set_raw) -> list[str]:
    """Support preset keys, raw lists, and JSON-serialized feature lists."""
    if not feature_set_raw:
        return FEATURE_SUBSETS["core_only"]
    if isinstance(feature_set_raw, list):
        return feature_set_raw
    if isinstance(feature_set_raw, str):
        try:
            parsed = json.loads(feature_set_raw)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return parsed
        return FEATURE_SUBSETS.get(feature_set_raw, FEATURE_SUBSETS["core_only"])
    return FEATURE_SUBSETS["core_only"]


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
    if random.random() < 0.5:
        params["feature_set"] = generate_random_feature_subset()
    else:
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
        n = CHALLENGER_COUNT_PER_CYCLE

    now_ms = int(time.time() * 1000)
    created = []

    # Force directional balance per cycle — but respect LONG_DISABLED.
    if LONG_DISABLED:
        target_dirs = ["short"] * n
    else:
        target_dirs = (["long", "short"] * ((n + 1) // 2))[:n]

    for i in range(n * 4):  # oversample to account for duplicates
        if len(created) >= n:
            break

        forced_direction = target_dirs[len(created)] if len(created) < len(target_dirs) else None
        params = _sample_params(forced_direction=forced_direction)
        model_id = _make_model_id(params)
        feature_names = resolve_feature_set(params["feature_set"])
        feature_set = json.dumps(feature_names)

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
