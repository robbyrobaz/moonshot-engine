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
DB_PATH = Path(os.environ.get("MOONSHOT_DB_PATH", str(BASE_DIR / "data" / "moonshot_v2.db")))
MODELS_DIR = BASE_DIR / "models"
TOURNAMENT_DIR = MODELS_DIR / "tournament"
CHAMPION_LONG_PATH = MODELS_DIR / "champion_long.pkl"
CHAMPION_SHORT_PATH = MODELS_DIR / "champion_short.pkl"
V1_DATA_DIR = Path("/home/rob/.openclaw/workspace/blofin-moonshot/data")

# ── Blofin API ───────────────────────────────────────────────────────────
BLOFIN_BASE_URL = "https://openapi.blofin.com"
# Shared budget: 500 req/min total
# Conservative: use 150 req/min (30%) to leave room for:
#   - Historical backfill (300 req/min)
#   - Live ingestor (WebSocket, minimal REST)
#   - Other processes
# 150 req/min = 2.5 req/sec
BLOFIN_RATE_LIMIT_RPS = _env("BLOFIN_RATE_LIMIT_RPS", 2.5, float)

# ── Data ─────────────────────────────────────────────────────────────────
CANDLE_INTERVAL = _env("CANDLE_INTERVAL", "4H")
CANDLE_LOOKBACK_BARS = _env("CANDLE_LOOKBACK_BARS", 200, int)
BACKFILL_TARGET_YEARS = _env("BACKFILL_TARGET_YEARS", 4, int)

# ── Labels ───────────────────────────────────────────────────────────────
# Price targets are defined on the underlying move; leveraged PnL is applied at execution time.
# 2026-03-15: Raised TP 10%→30% to hunt bigger spikes (new coin moonshots)
TP_PCT = _env("TP_PCT", 0.30, float)  # 30% take profit — hunting big moves
SL_PCT = _env("SL_PCT", 0.05, float)  # 5% stop loss
LABEL_HORIZON_BARS = _env("LABEL_HORIZON_BARS", 42, int)

# ── Leverage ─────────────────────────────────────────────────────────────
LEVERAGE = _env("LEVERAGE", 2, int)  # Default leverage for newly opened paper positions

# ── Tournament ───────────────────────────────────────────────────────────
MIN_BT_TRADES = _env("MIN_BT_TRADES", 30, int)  # 2026-03-16: Lowered 50→30 to widen net
MIN_BT_PF = _env("MIN_BT_PF", 0.6, float)  # For short (lowered 1.0→0.6)
# 2026-03-16: Raised long gate 0.3→1.5 — lottery tickets must be PROFITABLE (PF>1.0)
# A model with PF=0.79 loses money (spend $1.27 on losses per $1 won), not a lottery ticket
MIN_BT_PF_LONG = _env("MIN_BT_PF_LONG", 1.5, float)  # Require profitable backtest
MIN_BT_PRECISION = _env("MIN_BT_PRECISION", 0.12, float)  # For short (lowered 0.20→0.12)
# 2026-03-16: Raised long precision 0.08→0.20 — still loose but prevents garbage models
# At TP=15%/SL=5% (3:1 ratio), need ~25% precision for PF=1.0, 30% for PF=1.5
MIN_BT_PRECISION_LONG = _env("MIN_BT_PRECISION_LONG", 0.20, float)  # Loose but realistic
MAX_FT_MODELS = _env("MAX_FT_MODELS", 20, int)  # 2026-03-16: Raised 10→20 to allow more FT runners
# 2026-03-06: Relaxed thresholds — keep models in FT longer to collect more data.
# 2026-03-14: Lowered to 150 to clear FT backlog — retire after 150 trades if PF < 0.5.
# 2026-03-16: Two-tier retirement to manage 289-model backlog:
#   - Tier 1: Unprofitable (PF < 0.9) after 50 trades — retire early losers
#   - Tier 2: Catastrophic (PF < 0.5) after 150 trades — safety net
MIN_FT_TRADES_EVAL = _env("MIN_FT_TRADES_EVAL", 150, int)  # tier 2 eval threshold
MIN_FT_PF_KEEP = _env("MIN_FT_PF_KEEP", 0.5, float)  # tier 2: catastrophic losers
MIN_FT_TRADES_EVAL_50 = _env("MIN_FT_TRADES_EVAL_50", 50, int)  # tier 1 eval threshold
MIN_FT_PF_KEEP_50 = _env("MIN_FT_PF_KEEP_50", 0.9, float)  # tier 1: unprofitable models
CHALLENGER_COUNT_PER_HOUR = _env("CHALLENGER_COUNT_PER_HOUR", 25, int)  # 100/day = 25 per 4h cycle
BACKTEST_BATCH_SIZE_MAX = _env("BACKTEST_BATCH_SIZE_MAX", 100, int)  # max models per cycle (when CPU idle)
BACKTEST_BATCH_SIZE_MIN = _env("BACKTEST_BATCH_SIZE_MIN", 10, int)  # min models per cycle (when CPU busy)
BACKTEST_CPU_THRESHOLD = _env("BACKTEST_CPU_THRESHOLD", 70.0, float)  # CPU % threshold for throttling
CHAMPION_BEAT_MARGIN = _env("CHAMPION_BEAT_MARGIN", 0.10, float)
BOOTSTRAP_RESAMPLES = _env("BOOTSTRAP_RESAMPLES", 1000, int)
BOOTSTRAP_PF_LOWER_BOUND = _env("BOOTSTRAP_PF_LOWER_BOUND", 0.5, float)  # For short (lowered 0.8→0.5)
# 2026-03-16: Raised long bootstrap 0.2→0.7 — CI lower bound must be profitable
BOOTSTRAP_PF_LOWER_BOUND_LONG = _env("BOOTSTRAP_PF_LOWER_BOUND_LONG", 0.7, float)  # Confidence interval must be near breakeven

# ── PnL Weights (from NQ pipeline) ──────────────────────────────────────
PNL_WEIGHT_TP = _env("PNL_WEIGHT_TP", 1.0, float)
PNL_WEIGHT_SL = _env("PNL_WEIGHT_SL", 0.50, float)  # (SL/TP) × 1.5 = 0.5

# ── Execution ────────────────────────────────────────────────────────────
# 2026-03-15: ENABLE LONGS — primary mission now (hunting new coin spikes)
LONG_DISABLED = _env("LONG_DISABLED", False, lambda v: str(v).lower() in {"1", "true", "yes", "on"})
# 2026-03-16: Raised to 500 — 471 ML longs already open, 10-limit was blocking ALL new champion entries
MAX_LONG_POSITIONS = _env("MAX_LONG_POSITIONS", 500, int)
# 2026-03-16: Raised to 500 for consistency (456 ML shorts open)
MAX_SHORT_POSITIONS = _env("MAX_SHORT_POSITIONS", 500, int)
BASE_POSITION_PCT = _env("BASE_POSITION_PCT", 0.02, float)
MAX_POSITION_PCT = _env("MAX_POSITION_PCT", 0.05, float)
# 2026-03-15: Raised new listing boost 1.5x→5x — prioritize coins <30d old
NEW_LISTING_BOOST = _env("NEW_LISTING_BOOST", 5.0, float)
NEW_LISTING_DAYS = _env("NEW_LISTING_DAYS", 30, int)

# ── Rule-Based New Listing Entry (2026-03-16) ───────────────────────────
# Auto-enter ALL coins <7d old with trailing stops (ML can't predict bar 0-10 spikes)
NEW_LISTING_ENABLED = _env("NEW_LISTING_ENABLED", True, lambda v: str(v).lower() in {"1", "true", "yes", "on"})
NEW_LISTING_MAX_AGE_DAYS = _env("NEW_LISTING_MAX_AGE_DAYS", 7, int)  # Enter coins ≤7 days old
NEW_LISTING_POSITION_PCT = _env("NEW_LISTING_POSITION_PCT", 0.02, float)  # 2% per coin
NEW_LISTING_LEVERAGE = _env("NEW_LISTING_LEVERAGE", 2, int)  # 2x leverage
# Exit params for new listings use same trail config below (activate 15%, trail 10%)

TIME_STOP_DAYS = _env("TIME_STOP_DAYS", 7, int)
TIME_STOP_BARS = _env("TIME_STOP_BARS", 42, int)  # 7d at 4h
# 2026-03-16: Lowered trail activation 20%→15% for new listing strategy validation
TRAIL_ACTIVATE_PCT = _env("TRAIL_ACTIVATE_PCT", 0.15, float)  # Activate at +15%
TRAIL_DISTANCE_PCT = _env("TRAIL_DISTANCE_PCT", 0.10, float)  # Trail 10% below peak
# 2026-03-15: Raised invalidation grace 2→20 bars (80h = 3.3d) — let longs run longer
INVALIDATION_GRACE_BARS = _env("INVALIDATION_GRACE_BARS", 20, int)
PAPER_ACCOUNT_SIZE = _env("PAPER_ACCOUNT_SIZE", 100_000.0, float)
# 2026-03-11: Increased 2→5 so that when position slots are available, up to 5
# signals are taken per 4h cycle instead of just 2.
TOP_N_SIGNALS = _env("TOP_N_SIGNALS", 5, int)
# 2026-03-16: FIX: Reverted 0.30→0.50 — 0.30 caused overtrading (39 trades, PF 0.22)
# Wide net (0.30) dropped precision from 28%→7.7%, allowed scores as low as 0.366
ENTRY_THRESHOLD_FLOOR = _env("ENTRY_THRESHOLD_FLOOR", 0.50, float)
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
DISABLE_SOCIAL_FEATURES = _env(
    "DISABLE_SOCIAL_FEATURES", False,
    lambda v: str(v).lower() in {"1", "true", "yes", "on"},
)
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
