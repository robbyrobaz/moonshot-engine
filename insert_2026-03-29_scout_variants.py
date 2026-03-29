#!/usr/bin/env python3
"""
Moonshot Strategy Scout — 2026-03-29
Generate and insert 10 model variants into tournament queue
"""

import json
import secrets
import sqlite3
import time
from pathlib import Path

# Variant definitions
VARIANTS = [
    {
        "name": "ultra-minimal-momentum",
        "direction": "short",
        "model_type": "lightgbm",
        "features": ["momentum_1d", "momentum_3d", "momentum_4w", "volume_spike", "volume_ratio_3d", "obv_slope", "atr_percentile", "bb_position", "btc_30d_return", "market_breadth"],
        "params": {
            "learning_rate": 0.01,
            "max_depth": 4,
            "num_leaves": 63,
            "n_estimators": 100,
            "neg_class_weight": 8,
        },
    },
    {
        "name": "funding-mean-reversion",
        "direction": "short",
        "model_type": "catboost",
        "features": ["funding_rate_current", "funding_rate_7d_avg", "funding_rate_extreme", "price_vs_52w_high", "momentum_4w", "momentum_8w", "atr_percentile", "realized_vol_ratio", "oi_change_24h", "oi_percentile_90d", "volume_spike", "obv_slope", "btc_vol_percentile", "market_breadth"],
        "params": {
            "learning_rate": 0.015,
            "max_depth": 5,
            "n_estimators": 100,
            "neg_class_weight": 10,
        },
    },
    {
        "name": "volatility-compression",
        "direction": "short",
        "model_type": "lightgbm",
        "features": ["bb_squeeze_pct", "atr_compression", "realized_vol_ratio", "volume_spike", "volume_ratio_7d", "obv_slope", "momentum_4w", "price_vs_52w_high", "btc_vol_percentile", "market_breadth", "consec_down_bars", "higher_highs"],
        "params": {
            "learning_rate": 0.02,
            "max_depth": 3,
            "num_leaves": 31,
            "n_estimators": 100,
            "neg_class_weight": 6,
        },
    },
    {
        "name": "btc-regime",
        "direction": "short",
        "model_type": "xgboost",
        "features": ["btc_30d_return", "btc_vol_percentile", "market_breadth", "momentum_4w", "momentum_8w", "volume_ratio_3d", "volume_ratio_7d", "volume_spike", "atr_percentile", "bb_position", "price_vs_52w_high", "price_vs_52w_low", "distance_from_resistance", "consec_down_bars", "oi_percentile_90d", "realized_vol_ratio"],
        "params": {
            "learning_rate": 0.01,
            "max_depth": 4,
            "n_estimators": 150,
            "neg_class_weight": 8,
        },
    },
    {
        "name": "champion-lite",
        "direction": "short",
        "model_type": "lightgbm",
        "features": "core_only",  # String, not array
        "params": {
            "learning_rate": 0.01,
            "max_depth": 4,
            "num_leaves": 127,
            "n_estimators": 100,
            "neg_class_weight": 8,
        },
    },
    {
        "name": "oi-divergence",
        "direction": "short",
        "model_type": "catboost",
        "features": ["oi_change_24h", "oi_change_7d", "oi_price_divergence", "oi_percentile_90d", "momentum_4w", "momentum_8w", "volume_spike", "volume_trend", "obv_slope", "price_vs_52w_high", "bb_position", "atr_percentile", "btc_vol_percentile", "market_breadth", "realized_vol_ratio"],
        "params": {
            "learning_rate": 0.02,
            "max_depth": 4,
            "n_estimators": 100,
            "neg_class_weight": 7,
        },
    },
    {
        "name": "short-term-momentum",
        "direction": "short",
        "model_type": "lightgbm",
        "features": ["momentum_1d", "momentum_3d", "volume_spike", "volume_ratio_3d", "obv_slope", "bb_position", "bb_squeeze_pct", "atr_percentile", "high_low_range_pct", "consec_down_bars", "consec_up_bars", "btc_vol_percentile", "market_breadth"],
        "params": {
            "learning_rate": 0.025,
            "max_depth": 3,
            "num_leaves": 31,
            "n_estimators": 100,
            "neg_class_weight": 6,
        },
    },
    {
        "name": "heavy-xgboost",
        "direction": "short",
        "model_type": "xgboost",
        "features": ["price_vs_52w_high", "price_vs_52w_low", "momentum_4w", "momentum_8w", "bb_position", "bb_squeeze_pct", "distance_from_support", "distance_from_resistance", "consec_down_bars", "consec_up_bars", "higher_highs", "volume_ratio_7d", "volume_spike", "obv_slope", "atr_percentile", "atr_compression", "btc_30d_return", "btc_vol_percentile", "market_breadth", "realized_vol_ratio"],
        "params": {
            "learning_rate": 0.03,
            "max_depth": 6,
            "n_estimators": 200,
            "neg_class_weight": 10,
        },
    },
    {
        "name": "long-champion-candidate",
        "direction": "long",  # LONG model
        "model_type": "lightgbm",
        "features": ["price_vs_52w_low", "momentum_4w", "momentum_8w", "consec_down_bars", "higher_highs", "volume_spike", "volume_ratio_7d", "obv_slope", "atr_percentile", "realized_vol_ratio", "bb_position", "distance_from_support", "btc_30d_return", "market_breadth", "oi_change_7d", "oi_percentile_90d", "funding_rate_current", "days_since_listing"],
        "params": {
            "learning_rate": 0.015,
            "max_depth": 4,
            "num_leaves": 63,
            "n_estimators": 100,
            "pos_class_weight": 8,  # pos_class_weight for LONG
        },
    },
    {
        "name": "extreme-minimal",
        "direction": "short",
        "model_type": "lightgbm",
        "features": ["momentum_4w", "volume_spike", "bb_position", "atr_percentile", "price_vs_52w_high", "btc_vol_percentile", "market_breadth", "realized_vol_ratio"],
        "params": {
            "learning_rate": 0.01,
            "max_depth": 3,
            "num_leaves": 15,
            "n_estimators": 100,
            "neg_class_weight": 6,
        },
    },
]


def main():
    config_dir = Path("configs/generated")
    config_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = Path("data/moonshot_v2.db")
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    db = sqlite3.connect(str(db_path))
    inserted = []
    
    for i, variant in enumerate(VARIANTS, 1):
        model_id = secrets.token_hex(6)  # 12-char hex
        name = variant["name"]
        direction = variant["direction"]
        model_type = variant["model_type"]
        features = variant["features"]
        params = variant["params"]
        
        # Build full params dict
        full_params = {
            "model_type": model_type,
            "direction": direction,
            "feature_set": features,
            "confidence_threshold": 0.4,
            **params,
        }
        
        # Write JSON config
        config_path = config_dir / f"2026-03-29-variant-{i:02d}-{name}.json"
        config = {
            "model_id": model_id,
            "direction": direction,
            "model_type": model_type,
            "params": full_params,
            "feature_set": features,
            "feature_version": "v1",
            "entry_threshold": 0.4,
            "invalidation_threshold": 0.3,
            "stage": "backtest_queue",
        }
        
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Config written: {config_path}")
        
        # Insert into DB
        created_at = int(time.time() * 1000)
        
        # Handle feature_set (string or JSON array)
        if isinstance(features, str):
            feature_set_json = features  # "core_only", "no_social", etc.
        else:
            feature_set_json = json.dumps(features)
        
        params_json = json.dumps(full_params)
        
        db.execute(
            """
            INSERT INTO tournament_models 
            (model_id, direction, stage, model_type, params, feature_set, feature_version, entry_threshold, invalidation_threshold, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_id,
                direction,
                "backtest_queue",
                model_type,
                params_json,
                feature_set_json,
                "v1",
                0.4,
                0.3,
                created_at,
            ),
        )
        
        db.commit()
        
        inserted.append({
            "model_id": model_id,
            "name": name,
            "direction": direction,
            "model_type": model_type,
            "features": len(features) if isinstance(features, list) else features,
            "config_path": str(config_path),
        })
        
        print(f"✅ Inserted {model_id} ({name}, {direction}, {model_type})")
    
    db.close()
    
    print("\n" + "="*60)
    print(f"🎉 Successfully generated {len(inserted)} model variants")
    print("="*60)
    
    for item in inserted:
        print(f"  {item['model_id']} — {item['name']} ({item['direction']}, {item['model_type']}, {item['features']} features)")
    
    print(f"\n📂 Config files: configs/generated/2026-03-29-variant-*.json")
    print(f"💾 Database: data/moonshot_v2.db")
    print(f"📅 Next tournament cycle (4H): Will process these models")


if __name__ == "__main__":
    main()
