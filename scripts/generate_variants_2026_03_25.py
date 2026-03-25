#!/usr/bin/env python3
"""Generate 10 tournament model variants for 2026-03-25 strategy scout."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "moonshot_v2.db"
CONFIG_DIR = Path(__file__).parent.parent / "configs" / "generated"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Extended 37 features (no social)
EXTENDED_37 = [
    "price_vs_52w_high", "price_vs_52w_low", "momentum_4w", "momentum_8w",
    "bb_squeeze_pct", "bb_position", "volume_ratio_7d", "volume_ratio_3d",
    "obv_slope", "volume_spike", "volume_trend", "atr_percentile",
    "atr_compression", "high_low_range_pct", "realized_vol_ratio",
    "distance_from_support", "distance_from_resistance", "consec_down_bars",
    "consec_up_bars", "higher_highs", "btc_30d_return", "btc_vol_percentile",
    "market_breadth", "days_since_listing", "is_new_listing",
    "funding_rate_current", "funding_rate_7d_avg", "funding_rate_extreme",
    "oi_change_24h", "oi_change_7d", "oi_price_divergence", "oi_percentile_90d",
    "mark_index_spread", "price_vs_24h_high", "price_vs_24h_low",
    "vol_24h_vs_7d_avg", "price_change_24h_pct"
]

# Core 16 features
CORE_16 = [
    "price_vs_52w_high", "price_vs_52w_low", "momentum_4w", "momentum_8w",
    "bb_squeeze_pct", "bb_position", "volume_ratio_7d", "volume_ratio_3d",
    "obv_slope", "volume_spike", "volume_trend", "btc_30d_return",
    "btc_vol_percentile", "market_breadth", "days_since_listing", "is_new_listing"
]

# Extended + Social (50 features)
EXTENDED_SOCIAL_50 = EXTENDED_37 + [
    "fear_greed_score", "fear_greed_7d_change", "is_coingecko_trending",
    "trending_rank", "hours_on_trending", "news_mentions_24h",
    "news_mentions_7d_avg", "news_velocity_ratio", "reddit_mentions_24h",
    "reddit_score_24h", "reddit_velocity_ratio", "github_commits_7d",
    "github_commit_spike"
]

VARIANTS = [
    {
        "name": "variant-1-volatility",
        "direction": "short",
        "model_type": "xgboost",
        "params": {
            "learning_rate": 0.05,
            "max_depth": 5,
            "n_estimators": 150,
            "neg_class_weight": 8
        },
        "feature_set": [
            "atr_percentile", "atr_compression", "high_low_range_pct",
            "realized_vol_ratio", "bb_squeeze_pct", "btc_vol_percentile"
        ],
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-2-volume",
        "direction": "long",
        "model_type": "lightgbm",
        "params": {
            "learning_rate": 0.03,
            "max_depth": 6,
            "n_estimators": 200,
            "num_leaves": 31
        },
        "feature_set": [
            "volume_ratio_7d", "volume_ratio_3d", "obv_slope",
            "volume_spike", "volume_trend", "vol_24h_vs_7d_avg"
        ],
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-3-social",
        "direction": "long",
        "model_type": "catboost",
        "params": {
            "learning_rate": 0.02,
            "max_depth": 7,
            "n_estimators": 120,
            "neg_class_weight": 6
        },
        "feature_set": [
            "fear_greed_score", "fear_greed_7d_change", "is_coingecko_trending",
            "trending_rank", "hours_on_trending", "news_mentions_24h",
            "news_mentions_7d_avg", "news_velocity_ratio", "reddit_mentions_24h",
            "reddit_score_24h", "reddit_velocity_ratio", "github_commits_7d",
            "github_commit_spike"
        ],
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-4-conservative",
        "direction": "short",
        "model_type": "catboost",
        "params": {
            "learning_rate": 0.01,
            "max_depth": 8,
            "n_estimators": 100,
            "neg_class_weight": 12
        },
        "feature_set": EXTENDED_37,
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-5-aggressive",
        "direction": "short",
        "model_type": "xgboost",
        "params": {
            "learning_rate": 0.02,
            "max_depth": 6,
            "n_estimators": 150,
            "neg_class_weight": 4
        },
        "feature_set": EXTENDED_37,
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-6-deep",
        "direction": "both",
        "model_type": "catboost",
        "params": {
            "learning_rate": 0.005,
            "max_depth": 10,
            "n_estimators": 200,
            "neg_class_weight": 6
        },
        "feature_set": EXTENDED_SOCIAL_50,
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-7-fast",
        "direction": "long",
        "model_type": "lightgbm",
        "params": {
            "learning_rate": 0.1,
            "max_depth": 5,
            "n_estimators": 50,
            "num_leaves": 31
        },
        "feature_set": CORE_16 + [
            "atr_percentile", "atr_compression", "high_low_range_pct",
            "realized_vol_ratio", "distance_from_support",
            "distance_from_resistance", "consec_down_bars",
            "consec_up_bars", "higher_highs"
        ],  # Core 25
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-8-structure",
        "direction": "short",
        "model_type": "xgboost",
        "params": {
            "learning_rate": 0.03,
            "max_depth": 6,
            "n_estimators": 100,
            "neg_class_weight": 8
        },
        "feature_set": [
            "distance_from_support", "distance_from_resistance",
            "consec_down_bars", "consec_up_bars", "higher_highs",
            "bb_position", "momentum_4w", "momentum_8w"
        ],
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-9-funding",
        "direction": "short",
        "model_type": "catboost",
        "params": {
            "learning_rate": 0.02,
            "max_depth": 7,
            "n_estimators": 150,
            "neg_class_weight": 10
        },
        "feature_set": [
            "funding_rate_current", "funding_rate_7d_avg", "funding_rate_extreme",
            "oi_change_24h", "oi_change_7d", "oi_price_divergence",
            "oi_percentile_90d"
        ],
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    },
    {
        "name": "variant-10-minimal",
        "direction": "both",
        "model_type": "xgboost",
        "params": {
            "learning_rate": 0.05,
            "max_depth": 5,
            "n_estimators": 100,
            "neg_class_weight": 6
        },
        "feature_set": CORE_16,
        "entry_threshold": 0.65,
        "invalidation_threshold": 0.45
    }
]


def generate_model_id(config):
    """Generate deterministic model_id from config."""
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.sha1(config_str.encode()).hexdigest()[:12]


def main():
    db = sqlite3.connect(DB_PATH, timeout=30.0)
    db.row_factory = sqlite3.Row
    
    created_count = 0
    
    for variant in VARIANTS:
        # Generate model_id
        config = {
            "direction": variant["direction"],
            "model_type": variant["model_type"],
            "params": variant["params"],
            "feature_set": variant["feature_set"],
            "entry_threshold": variant["entry_threshold"],
            "invalidation_threshold": variant["invalidation_threshold"]
        }
        model_id = generate_model_id(config)
        
        # Check if already exists
        existing = db.execute(
            "SELECT model_id FROM tournament_models WHERE model_id = ?",
            (model_id,)
        ).fetchone()
        
        if existing:
            print(f"SKIP {variant['name']} (model_id={model_id} already exists)")
            continue
        
        # Write JSON config
        config_path = CONFIG_DIR / f"2026-03-25-{variant['name']}.json"
        with open(config_path, "w") as f:
            json.dump({
                "model_id": model_id,
                **config,
                "created_at": int(time.time() * 1000)
            }, f, indent=2)
        
        # Insert into DB
        db.execute(
            """INSERT INTO tournament_models (
                model_id, direction, stage, model_type, params, feature_set,
                entry_threshold, invalidation_threshold, created_at
            ) VALUES (?, ?, 'backtest', ?, ?, ?, ?, ?, ?)""",
            (
                model_id,
                variant["direction"],
                variant["model_type"],
                json.dumps(variant["params"]),
                json.dumps(variant["feature_set"]),
                variant["entry_threshold"],
                variant["invalidation_threshold"],
                int(time.time() * 1000)
            )
        )
        db.commit()
        
        print(f"✓ Created {variant['name']} (model_id={model_id})")
        created_count += 1
    
    db.close()
    print(f"\n{created_count} new variants added to backtest queue")


if __name__ == "__main__":
    main()
