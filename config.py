"""Moonshot v2 — Central Configuration.

All values overridable via environment variables with MOONSHOT_ prefix.
Example: MOONSHOT_TP_PCT=0.25 overrides TP_PCT.
"""

import os
from pathlib import Path

def _env(key: str, default, cast=None):
    val = os.environ.get(f"MOONSHOT_{key}", None)
    if val is None:
        return default
    if cast is not None:
        return cast(val)
    return type(default)(val)


def _env_csv(key: str, default: list[str] | None = None) -> list[str]:
    """Read comma-separated env var into uppercase, trimmed symbol list."""
    if default is None:
        default = []
    raw = os.environ.get(f"MOONSHOT_{key}", None)
    if raw is None:
        return default
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "moonshot_v2.db"
MODELS_DIR = BASE_DIR / "models"
TOURNAMENT_DIR = MODELS_DIR / "tournament"
CHAMPION_LONG_PATH = MODELS_DIR / "champion_long.pkl"
CHAMPION_SHORT_PATH = MODELS_DIR / "champion_short.pkl"
V1_DATA_DIR = Path("/home/rob/.openclaw/workspace/blofin-moonshot/data")

# ── Blofin API ───────────────────────────────────────────────────────────
BLOFIN_BASE_URL = "https://openapi.blofin.com"
BLOFIN_RATE_LIMIT_RPS = _env("BLOFIN_RATE_LIMIT_RPS", 10, int)

# ── Data ─────────────────────────────────────────────────────────────────
CANDLE_INTERVAL = _env("CANDLE_INTERVAL", "4H")
CANDLE_LOOKBACK_BARS = _env("CANDLE_LOOKBACK_BARS", 200, int)
BACKFILL_TARGET_YEARS = _env("BACKFILL_TARGET_YEARS", 4, int)

# ── Labels ───────────────────────────────────────────────────────────────
# 15%/5% price targets with 3x leverage = effective 45%/15% PnL (same 3:1 R:R)
TP_PCT = _env("TP_PCT", 0.15, float)
SL_PCT = _env("SL_PCT", 0.05, float)
LABEL_HORIZON_BARS = _env("LABEL_HORIZON_BARS", 42, int)

# ── Leverage ─────────────────────────────────────────────────────────────
LEVERAGE = _env("LEVERAGE", 3, int)  # Applied to all paper positions

# ── Tournament ───────────────────────────────────────────────────────────
MIN_BT_TRADES = _env("MIN_BT_TRADES", 50, int)
MIN_BT_PF = _env("MIN_BT_PF", 1.0, float)  # Lowered: FT is FREE, test everything
MIN_BT_PRECISION = _env("MIN_BT_PRECISION", 0.20, float)  # Lowered: PF matters more than precision
MAX_FT_MODELS = _env("MAX_FT_MODELS", 10, int)
# 2026-03-06: Relaxed thresholds — keep models in FT longer to collect more data.
# Only retire clear losers (PF < 0.8) after substantial sample (200+ trades).
MIN_FT_TRADES_EVAL = _env("MIN_FT_TRADES_EVAL", 500, int)  # only eval after 500 FT trades
MIN_FT_PF_KEEP = _env("MIN_FT_PF_KEEP", 0.5, float)  # only demote catastrophic losers
MIN_FT_PF_KEEP_50 = _env("MIN_FT_PF_KEEP_50", 0.5, float)  # same - FT is free data
CHALLENGER_COUNT_PER_HOUR = _env("CHALLENGER_COUNT_PER_HOUR", 10, int)
CHAMPION_BEAT_MARGIN = _env("CHAMPION_BEAT_MARGIN", 0.10, float)
BOOTSTRAP_RESAMPLES = _env("BOOTSTRAP_RESAMPLES", 1000, int)
BOOTSTRAP_PF_LOWER_BOUND = _env("BOOTSTRAP_PF_LOWER_BOUND", 0.8, float)

# ── PnL Weights (from NQ pipeline) ──────────────────────────────────────
PNL_WEIGHT_TP = _env("PNL_WEIGHT_TP", 1.0, float)
PNL_WEIGHT_SL = _env("PNL_WEIGHT_SL", 0.50, float)  # (SL/TP) × 1.5 = 0.5

# ── Execution ────────────────────────────────────────────────────────────
MAX_LONG_POSITIONS = _env("MAX_LONG_POSITIONS", 3, int)
# 2026-03-11: Increased 3→6 to expand entry volume. Signal supply is abundant
# (419/468 coins score ≥0.40 per cycle) but positions were filling to capacity
# and blocking all new entries until exits occurred.
MAX_SHORT_POSITIONS = _env("MAX_SHORT_POSITIONS", 6, int)
BASE_POSITION_PCT = _env("BASE_POSITION_PCT", 0.02, float)
MAX_POSITION_PCT = _env("MAX_POSITION_PCT", 0.05, float)
NEW_LISTING_BOOST = _env("NEW_LISTING_BOOST", 1.5, float)
NEW_LISTING_DAYS = _env("NEW_LISTING_DAYS", 30, int)
TIME_STOP_DAYS = _env("TIME_STOP_DAYS", 7, int)
TIME_STOP_BARS = _env("TIME_STOP_BARS", 42, int)  # 7d at 4h
TRAIL_ACTIVATE_PCT = _env("TRAIL_ACTIVATE_PCT", 0.20, float)
TRAIL_DISTANCE_PCT = _env("TRAIL_DISTANCE_PCT", 0.10, float)
INVALIDATION_GRACE_BARS = _env("INVALIDATION_GRACE_BARS", 2, int)
PAPER_ACCOUNT_SIZE = _env("PAPER_ACCOUNT_SIZE", 100_000.0, float)
# 2026-03-11: Increased 2→5 so that when position slots are available, up to 5
# signals are taken per 4h cycle instead of just 2.
TOP_N_SIGNALS = _env("TOP_N_SIGNALS", 5, int)
ENTRY_THRESHOLD_FLOOR = _env("ENTRY_THRESHOLD_FLOOR", 0.30, float)
SYMBOL_WHITELIST = _env_csv("SYMBOL_WHITELIST", [])
SYMBOL_WHITELIST_MIN_TRADES = _env("SYMBOL_WHITELIST_MIN_TRADES", 20, int)

# ── Regime ───────────────────────────────────────────────────────────────
BEAR_THRESHOLD = _env("BEAR_THRESHOLD", -0.20, float)
BULL_THRESHOLD = _env("BULL_THRESHOLD", 0.20, float)

# ── Per-Coin Confidence ──────────────────────────────────────────────────
CONSEC_LOSS_HALF = _env("CONSEC_LOSS_HALF", 3, int)
CONSEC_LOSS_SKIP = _env("CONSEC_LOSS_SKIP", 5, int)
CONFIDENCE_RECOVERY_PER_WIN = _env("CONFIDENCE_RECOVERY_PER_WIN", 0.25, float)

# ── Drawdown Circuit Breaker ─────────────────────────────────────────────
FT_MAX_DRAWDOWN_PAUSE = _env("FT_MAX_DRAWDOWN_PAUSE", 100.0, float)  # 10000% - effectively disabled
FT_PAUSE_HOURS = _env("FT_PAUSE_HOURS", 48, int)
CHAMPION_DD_REDUCE = _env("CHAMPION_DD_REDUCE", 0.20, float)
CHAMPION_DD_PAUSE = _env("CHAMPION_DD_PAUSE", 0.35, float)

# ── Dashboard ────────────────────────────────────────────────────────────
DASHBOARD_PORT = _env("DASHBOARD_PORT", 8893, int)
DASHBOARD_REFRESH_SECONDS = _env("DASHBOARD_REFRESH_SECONDS", 300, int)

# ── Social Data ──────────────────────────────────────────────────────────
SOCIAL_COLLECTION_INTERVAL_HOURS = _env("SOCIAL_COLLECTION_INTERVAL_HOURS", 1, int)
FEAR_GREED_URL = "https://api.alternative.me/fng/"
COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
RSS_FEEDS = [
    ("cointelegraph", "https://cointelegraph.com/rss"),
    ("decrypt", "https://decrypt.co/feed"),
    ("theblock", "https://www.theblock.co/rss.xml"),
]
REDDIT_SUBREDDITS = [
    "CryptoCurrency",
    "CryptoMoonShots",
    "SatoshiStreetBets",
]
GITHUB_REPOS_PATH = BASE_DIR / "data" / "github_repos.json"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ── Logging ──────────────────────────────────────────────────────────────
import logging

LOG_LEVEL = _env("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
log = logging.getLogger("moonshot")
