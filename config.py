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
TP_PCT = _env("TP_PCT", 0.30, float)
SL_PCT = _env("SL_PCT", 0.10, float)
LABEL_HORIZON_BARS = _env("LABEL_HORIZON_BARS", 42, int)

# ── Tournament ───────────────────────────────────────────────────────────
MIN_BT_TRADES = _env("MIN_BT_TRADES", 50, int)
MIN_BT_PF = _env("MIN_BT_PF", 2.0, float)
MIN_BT_PRECISION = _env("MIN_BT_PRECISION", 0.40, float)
MAX_FT_MODELS = _env("MAX_FT_MODELS", 15, int)
MIN_FT_TRADES_EVAL = _env("MIN_FT_TRADES_EVAL", 20, int)
MIN_FT_PF_KEEP = _env("MIN_FT_PF_KEEP", 1.3, float)
MIN_FT_PF_KEEP_50 = _env("MIN_FT_PF_KEEP_50", 1.5, float)
CHALLENGER_COUNT_PER_HOUR = _env("CHALLENGER_COUNT_PER_HOUR", 10, int)
CHAMPION_BEAT_MARGIN = _env("CHAMPION_BEAT_MARGIN", 0.10, float)
BOOTSTRAP_RESAMPLES = _env("BOOTSTRAP_RESAMPLES", 1000, int)
BOOTSTRAP_PF_LOWER_BOUND = _env("BOOTSTRAP_PF_LOWER_BOUND", 1.0, float)

# ── PnL Weights (from NQ pipeline) ──────────────────────────────────────
PNL_WEIGHT_TP = _env("PNL_WEIGHT_TP", 1.0, float)
PNL_WEIGHT_SL = _env("PNL_WEIGHT_SL", 0.50, float)  # (SL/TP) × 1.5 = 0.5

# ── Execution ────────────────────────────────────────────────────────────
MAX_LONG_POSITIONS = _env("MAX_LONG_POSITIONS", 5, int)
MAX_SHORT_POSITIONS = _env("MAX_SHORT_POSITIONS", 5, int)
BASE_POSITION_PCT = _env("BASE_POSITION_PCT", 0.02, float)
NEW_LISTING_BOOST = _env("NEW_LISTING_BOOST", 1.5, float)
NEW_LISTING_DAYS = _env("NEW_LISTING_DAYS", 30, int)
TIME_STOP_DAYS = _env("TIME_STOP_DAYS", 7, int)
TIME_STOP_BARS = _env("TIME_STOP_BARS", 42, int)  # 7d at 4h
TRAIL_ACTIVATE_PCT = _env("TRAIL_ACTIVATE_PCT", 0.20, float)
TRAIL_DISTANCE_PCT = _env("TRAIL_DISTANCE_PCT", 0.10, float)
INVALIDATION_GRACE_BARS = _env("INVALIDATION_GRACE_BARS", 2, int)
PAPER_ACCOUNT_SIZE = _env("PAPER_ACCOUNT_SIZE", 100_000.0, float)
TOP_N_SIGNALS = _env("TOP_N_SIGNALS", 5, int)

# ── Regime ───────────────────────────────────────────────────────────────
BEAR_THRESHOLD = _env("BEAR_THRESHOLD", -0.20, float)
BULL_THRESHOLD = _env("BULL_THRESHOLD", 0.20, float)

# ── Per-Coin Confidence ──────────────────────────────────────────────────
CONSEC_LOSS_HALF = _env("CONSEC_LOSS_HALF", 3, int)
CONSEC_LOSS_SKIP = _env("CONSEC_LOSS_SKIP", 5, int)
CONFIDENCE_RECOVERY_PER_WIN = _env("CONFIDENCE_RECOVERY_PER_WIN", 0.25, float)

# ── Drawdown Circuit Breaker ─────────────────────────────────────────────
FT_MAX_DRAWDOWN_PAUSE = _env("FT_MAX_DRAWDOWN_PAUSE", 0.30, float)
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
