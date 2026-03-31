#!/usr/bin/env python3
"""Insert 2026-03-31 Moonshot Scout variants into tournament queue."""

import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "configs" / "generated" / "2026-03-31"
DB_PATH = Path(__file__).parent / "data" / "moonshot_v2.db"


def insert_variant(db, config_path):
    """Insert a single variant config into tournament_models table."""
    with open(config_path) as f:
        cfg = json.load(f)
    
    # Generate unique model_id
    model_id = uuid.uuid4().hex[:12]
    
    # Serialize params and feature_set as JSON strings (DB schema stores as TEXT)
    params_json = json.dumps(cfg["params"])
    feature_set_json = json.dumps(cfg["feature_set"])
    
    # Current timestamp in milliseconds
    created_at = int(time.time() * 1000)
    
    # Insert into backtest queue
    db.execute(
        """
        INSERT INTO tournament_models 
        (model_id, direction, stage, model_type, params, feature_set, feature_version,
         entry_threshold, invalidation_threshold, created_at)
        VALUES (?, ?, 'backtest', ?, ?, ?, 'v2', ?, ?, ?)
        """,
        (
            model_id,
            cfg["direction"],
            cfg["model_type"],
            params_json,
            feature_set_json,
            cfg["entry_threshold"],
            cfg["invalidation_threshold"],
            created_at,
        )
    )
    
    return model_id, cfg


def main():
    """Load all variant configs and insert into tournament queue."""
    if not CONFIG_DIR.exists():
        print(f"❌ Config directory not found: {CONFIG_DIR}")
        return 1
    
    config_files = sorted(CONFIG_DIR.glob("variant-*.json"))
    if not config_files:
        print(f"❌ No variant-*.json files found in {CONFIG_DIR}")
        return 1
    
    print(f"📥 Inserting {len(config_files)} variants into tournament queue...\n")
    
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    
    inserted = []
    
    for config_path in config_files:
        try:
            model_id, cfg = insert_variant(db, config_path)
            print(f"✅ {config_path.name}")
            print(f"   Model ID: {model_id}")
            print(f"   {cfg['direction']} | {cfg['model_type']} | {len(cfg['feature_set'])} features")
            print(f"   {cfg['description'][:70]}...")
            inserted.append((model_id, cfg, config_path.stem))
        except Exception as e:
            print(f"❌ Failed to insert {config_path.name}: {e}")
            db.rollback()
            return 1
    
    # Commit all inserts
    db.commit()
    db.close()
    
    print(f"\n{'='*80}")
    print(f"✅ Successfully inserted {len(inserted)} variants into backtest queue!")
    print(f"\nModel IDs:")
    for model_id, cfg, stem in inserted:
        print(f"  {model_id}  {cfg['direction']:5s}  {cfg['model_type']:12s}  {stem}")
    
    print(f"\n🎯 Next tournament cycle will backtest these models (runs every 4 hours)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
