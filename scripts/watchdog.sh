#!/bin/bash
# Moonshot v2 Watchdog - Kill hung cycles and alert

set -e

DB_PATH="/home/rob/.openclaw/workspace/blofin-moonshot-v2/data/moonshot_v2.db"
LOCK_FILE="/home/rob/.openclaw/workspace/blofin-moonshot-v2/data/moonshot_v2.cycle.lock"
MAX_CYCLE_MINUTES=180  # Increased from 90 — cycles with extended data take 105-120min
MAX_BACKTEST_MINUTES=120  # Increased from 60 — large backtest batches take longer
NTFY_TOPIC="jarvis-alerts"

# Check for hung run_cycle.py
cycle_pid=$(pgrep -f "run_cycle.py" || true)
if [ -n "$cycle_pid" ]; then
    # Get elapsed time in minutes
    elapsed_sec=$(ps -o etimes= -p "$cycle_pid" 2>/dev/null || echo "0")
    elapsed_min=$((elapsed_sec / 60))
    
    if [ "$elapsed_min" -gt "$MAX_CYCLE_MINUTES" ]; then
        echo "🚨 KILLING hung Moonshot cycle (PID $cycle_pid, running ${elapsed_min}min)"
        kill "$cycle_pid" 2>/dev/null || true
        sleep 2
        kill -9 "$cycle_pid" 2>/dev/null || true
        rm -f "$LOCK_FILE"
        
        # Alert Rob
        curl -s -d "Moonshot cycle hung (${elapsed_min}min) - killed PID $cycle_pid" \
            "https://ntfy.sh/$NTFY_TOPIC" || true
    fi
fi

# Check for hung backtest worker
bt_pid=$(pgrep -f "backtest_new_challengers" || true)
if [ -n "$bt_pid" ]; then
    elapsed_sec=$(ps -o etimes= -p "$bt_pid" 2>/dev/null || echo "0")
    elapsed_min=$((elapsed_sec / 60))
    
    if [ "$elapsed_min" -gt "$MAX_BACKTEST_MINUTES" ]; then
        echo "🚨 KILLING hung backtest worker (PID $bt_pid, running ${elapsed_min}min)"
        kill "$bt_pid" 2>/dev/null || true
        sleep 2
        kill -9 "$bt_pid" 2>/dev/null || true
        
        # Alert Rob
        curl -s -d "Moonshot backtest hung (${elapsed_min}min) - killed PID $bt_pid" \
            "https://ntfy.sh/$NTFY_TOPIC" || true
    fi
fi

# Check backtest queue staleness
cd /home/rob/.openclaw/workspace/blofin-moonshot-v2
staleness=$(../blofin-moonshot-v2/.venv/bin/python3 << 'EOF'
from src.db.schema import get_db
import time

db = get_db()

# Check if backtests are progressing
recent_bt = db.execute("""
    SELECT MAX(created_at) as latest 
    FROM tournament_models 
    WHERE bt_trades > 0
""").fetchone()

if recent_bt and recent_bt['latest']:
    age_min = (time.time() * 1000 - recent_bt['latest']) / 60000
    print(int(age_min))
else:
    print(999)
EOF
)

if [ "$staleness" -gt 120 ]; then
    echo "⚠️  Backtest queue stale (${staleness}min since last completion)"
    curl -s -d "Moonshot backtest queue stale (${staleness}min) - check for deadlock" \
        "https://ntfy.sh/$NTFY_TOPIC" || true
fi

echo "✅ Moonshot watchdog OK (cycle_pid=${cycle_pid:-none}, bt_pid=${bt_pid:-none}, queue_age=${staleness}min)"
