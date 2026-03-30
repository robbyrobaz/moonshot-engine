#!/usr/bin/env python3
"""Generate and insert 8 Moonshot scout variants — 2026-03-30."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "moonshot_v2.db"
CONFIG_DIR = BASE_DIR / "configs" / "generated"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

VARIANTS = [
    {
        "name": "minimal-core",
        "model_type": "catboost",
        "direction": "short",
        "feature_set": ["momentum_1d", "momentum_3d", "atr_percentile", "bb_position", "volume_spike"],
        "confidence_threshold": 0.6,
        "learning_rate": 0.1,
        "max_depth": 4,
        "n_estimators": 100,
        "neg_class_weight": 5,
        "num_leaves": 31,
    },
    {
        "name": "volume-sniper",
        "model_type": "lightgbm",
        "direction": "short",
        "feature_set": ["volume_ratio_3d", "volume_ratio_7d", "volume_spike", "volume_trend", "obv_slope", "vol_24h_vs_7d_avg"],
        "confidence_threshold": 0.7,
        "learning_rate": 0.05,
        "max_depth": 6,
        "n_estimators": 200,
        "neg_class_weight": 3,
        "num_leaves": 63,
    },
    {
        "name": "deep-catboost",
        "model_type": "catboost",
        "direction": "short",
        "feature_set": "no_social",
        "confidence_threshold": 0.6,
        "learning_rate": 0.03,
        "max_depth": 8,
        "n_estimators": 300,
        "neg_class_weight": 5,
        "num_leaves": 63,
    },
    {
        "name": "fast-trader",
        "model_type": "xgboost",
        "direction": "short",
        "feature_set": ["momentum_1d", "momentum_3d", "bb_position", "volume_ratio_3d", "atr_percentile", "high_low_range_pct"],
        "confidence_threshold": 0.7,
        "learning_rate": 0.1,
        "max_depth": 3,
        "n_estimators": 50,
        "neg_class_weight": 3,
        "num_leaves": 31,
    },
    {
        "name": "long-lottery",
        "model_type": "lightgbm",
        "direction": "long",
        "feature_set": ["momentum_8w", "price_vs_52w_low", "distance_from_support", "is_new_listing", "days_since_listing", "btc_30d_return"],
        "confidence_threshold": 0.3,
        "learning_rate": 0.05,
        "max_depth": 6,
        "n_estimators": 200,
        "neg_class_weight": 15,
        "num_leaves": 63,
    },
    {
        "name": "funding-contrarian",
        "model_type": "catboost",
        "direction": "short",
        "feature_set": ["funding_rate_current", "funding_rate_extreme", "oi_price_divergence", "mark_index_spread", "volume_spike"],
        "confidence_threshold": 0.7,
        "learning_rate": 0.05,
        "max_depth": 6,
        "n_estimators": 200,
        "neg_class_weight": 5,
        "num_leaves": 63,
    },
    {
        "name": "btc-correlation",
        "model_type": "xgboost",
        "direction": "short",
        "feature_set": ["btc_30d_return", "btc_vol_percentile", "market_breadth", "momentum_4w", "volume_ratio_7d"],
        "confidence_threshold": 0.6,
        "learning_rate": 0.05,
        "max_depth": 5,
        "n_estimators": 150,
        "neg_class_weight": 5,
        "num_leaves": 63,
    },
    {
        "name": "momentum-extremes",
        "model_type": "lightgbm",
        "direction": "short",
        "feature_set": ["momentum_1d", "momentum_3d", "momentum_4w", "bb_position", "price_vs_52w_high", "atr_percentile"],
        "confidence_threshold": 0.65,
        "learning_rate": 0.05,
        "max_depth": 6,
        "n_estimators": 200,
        "neg_class_weight": 5,
        "num_leaves": 63,
    },
]


def generate_model_id(params: dict) -> str:
    """Generate deterministic 12-char model ID from params."""
    params_json = json.dumps(params, sort_keys=True)
    return hashlib.sha256(params_json.encode()).hexdigest()[:12]


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    
    created_at = int(time.time() * 1000)
    inserted = []
    
    for variant in VARIANTS:
        name = variant.pop("name")
        params = variant.copy()
        model_id = generate_model_id(params)
        
        # Write config JSON
        config_path = CONFIG_DIR / f"2026-03-30-scout-{name}.json"
        with open(config_path, "w") as f:
            json.dump(params, f, indent=2)
        print(f"✓ Wrote {config_path.name}")
        
        # Insert into DB
        feature_set_json = json.dumps(params["feature_set"])
        params_json = json.dumps(params)
        
        try:
            db.execute(
                """
                INSERT INTO tournament_models (
                    model_id, direction, stage, model_type, params,
                    feature_set, feature_version,
                    entry_threshold, invalidation_threshold,
                    bt_trades, bt_pf, bt_precision, bt_pnl, bt_ci_lower,
                    ft_trades, ft_wins, ft_pnl, ft_pf, ft_max_drawdown_pct,
                    is_paused, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_id,
                    params["direction"],
                    "backtest",
                    params["model_type"],
                    params_json,
                    feature_set_json,
                    "v2",
                    params["confidence_threshold"],
                    0.30,  # default invalidation threshold
                    0, 0.0, 0.0, 0.0, 0.0,  # backtest metrics (not run yet)
                    0, 0, 0.0, 0.0, 0.0,     # forward test metrics
                    0,                       # is_paused
                    created_at,
                ),
            )
            db.commit()
            inserted.append((model_id, name, params["direction"], params["model_type"]))
            print(f"✓ Inserted {model_id} ({name})")
        except sqlite3.IntegrityError:
            print(f"⚠ Skipped {model_id} (already exists)")
    
    db.close()
    
    print(f"\n{'='*60}")
    print(f"Scout Variants Generated — 2026-03-30")
    print(f"{'='*60}")
    print(f"Total inserted: {len(inserted)}")
    print(f"\nModels:")
    for model_id, name, direction, model_type in inserted:
        print(f"  {model_id} | {direction:5} | {model_type:8} | {name}")
    print(f"\nConfigs: {CONFIG_DIR}")
    print(f"Next 4H cycle will backtest these models.")


if __name__ == "__main__":
    main()
