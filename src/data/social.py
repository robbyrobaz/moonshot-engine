"""Moonshot v2 — Social / news data collection (1h timer)."""

import re
import json
import time
import requests
from config import (
    FEAR_GREED_URL,
    COINGECKO_TRENDING_URL,
    RSS_FEEDS,
    REDDIT_SUBREDDITS,
    GITHUB_REPOS_PATH,
    GITHUB_TOKEN,
    log,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _known_symbols(db) -> set[str]:
    """Return set of base symbols (e.g. 'BTC', 'ETH') from coins table."""
    rows = db.execute("SELECT symbol FROM coins WHERE is_active = 1").fetchall()
    symbols = set()
    for r in rows:
        # symbol is like "BTC-USDT" -> extract "BTC"
        base = r["symbol"].split("-")[0]
        symbols.add(base.upper())
    return symbols


def collect_fear_greed(db) -> int:
    """Fetch Fear & Greed Index and insert into social_events."""
    try:
        resp = requests.get(FEAR_GREED_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return 0

        entry = data[0]
        score = float(entry.get("value", 0))
        classification = entry.get("value_classification", "")
        ts = _now_ms()

        db.execute(
            "INSERT INTO social_events (symbol, source, ts, event_type, numeric_value, text_snippet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (None, "fear_greed", ts, "fear_greed_score", score, classification),
        )
        db.commit()
        log.info("collect_fear_greed: score=%s (%s)", score, classification)
        return 1

    except Exception as e:
        log.warning("collect_fear_greed: error: %s", e)
        return 0


def collect_coingecko_trending(db) -> int:
    """Fetch CoinGecko trending coins and insert into social_events."""
    try:
        resp = requests.get(COINGECKO_TRENDING_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        coins = data.get("coins", [])
        ts = _now_ms()
        count = 0

        for i, entry in enumerate(coins):
            item = entry.get("item", {})
            coin_symbol = item.get("symbol", "").upper()
            coin_name = item.get("name", "")
            rank = i + 1

            db.execute(
                "INSERT INTO social_events (symbol, source, ts, event_type, numeric_value, text_snippet) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (coin_symbol, "coingecko_trending", ts, "trending", rank, coin_name),
            )
            count += 1

        db.commit()
        log.info("collect_coingecko_trending: %d trending coins", count)
        return count

    except Exception as e:
        log.warning("collect_coingecko_trending: error: %s", e)
        return 0


def collect_rss_feeds(db) -> int:
    """Parse RSS feeds and extract coin mentions from headlines."""
    try:
        import feedparser
    except ImportError:
        log.warning("collect_rss_feeds: feedparser not installed, skipping")
        return 0

    known = _known_symbols(db)
    if not known:
        return 0

    # Build regex pattern for known symbols (word boundary match)
    # Match both the ticker and common names
    ts = _now_ms()
    count = 0
    pending_rows = []

    for feed_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:  # Limit to recent 20 entries
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = f"{title} {summary}".upper()

                # Find mentioned symbols
                mentioned = set()
                for sym in known:
                    # Word boundary match to avoid false positives
                    if re.search(rf"\b{re.escape(sym)}\b", text):
                        mentioned.add(sym)

                for sym in mentioned:
                    pending_rows.append(
                        (sym, f"rss_{feed_name}", ts, "mention", None, title[:200])
                    )
                    count += 1

        except Exception as e:
            log.warning("collect_rss_feeds: %s error: %s", feed_name, e)

    if pending_rows:
        db.executemany(
            "INSERT INTO social_events "
            "(symbol, source, ts, event_type, numeric_value, text_snippet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            pending_rows,
        )
        db.commit()
    log.info("collect_rss_feeds: %d mentions across %d feeds", count, len(RSS_FEEDS))
    return count


def collect_reddit(db, top_symbols: list[str] | None = None) -> int:
    """Search Reddit for mentions of top coins. Uses public JSON API (no auth)."""
    if not top_symbols:
        # Default to top 50 by most recent OI if not specified
        rows = db.execute(
            "SELECT DISTINCT symbol FROM open_interest "
            "ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        top_symbols = [r["symbol"].split("-")[0] for r in rows]

    if not top_symbols:
        return 0

    ts = _now_ms()
    count = 0
    pending_rows = []
    headers = {"User-Agent": "moonshot-v2/1.0"}

    for subreddit in REDDIT_SUBREDDITS:
        for symbol in top_symbols[:50]:
            try:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                resp = requests.get(
                    url,
                    params={"q": symbol, "sort": "new", "limit": "5", "t": "day", "restrict_sr": "on"},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 429:
                    log.warning("collect_reddit: rate limited on r/%s, pausing", subreddit)
                    time.sleep(5)
                    continue
                if resp.status_code != 200:
                    continue

                data = resp.json().get("data", {}).get("children", [])
                for post in data:
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")[:200]
                    score = post_data.get("score", 0)
                    pending_rows.append(
                        (symbol, "reddit", ts, "mention", score, title)
                    )
                    count += 1

                # Respect Reddit rate limits
                time.sleep(1.0)

            except Exception as e:
                log.warning("collect_reddit: r/%s %s error: %s", subreddit, symbol, e)

    if pending_rows:
        db.executemany(
            "INSERT INTO social_events "
            "(symbol, source, ts, event_type, numeric_value, text_snippet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            pending_rows,
        )
        db.commit()
    log.info("collect_reddit: %d mentions across %d subreddits", count, len(REDDIT_SUBREDDITS))
    return count


def collect_github(db) -> int:
    """Fetch recent commit counts from tracked GitHub repos."""
    if not GITHUB_REPOS_PATH.exists():
        log.info("collect_github: %s not found, skipping", GITHUB_REPOS_PATH)
        return 0

    try:
        with open(GITHUB_REPOS_PATH) as f:
            repos = json.load(f)
    except Exception as e:
        log.warning("collect_github: error reading %s: %s", GITHUB_REPOS_PATH, e)
        return 0

    # repos is expected to be: {"BTC": "bitcoin/bitcoin", "ETH": "ethereum/go-ethereum", ...}
    ts = _now_ms()
    count = 0
    pending_rows = []
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    for symbol, repo in repos.items():
        try:
            # Get commit activity (last week)
            url = f"https://api.github.com/repos/{repo}/stats/participation"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 202:
                # GitHub is computing stats, skip this time
                continue
            if resp.status_code != 200:
                continue

            data = resp.json()
            # "all" is list of 52 weeks, last entry is most recent week
            all_commits = data.get("all", [])
            if all_commits:
                recent_commits = all_commits[-1]
                pending_rows.append(
                    (symbol.upper(), "github", ts, "weekly_commits", recent_commits, repo)
                )
                count += 1

            time.sleep(0.5)  # Respect GitHub rate limits

        except Exception as e:
            log.warning("collect_github: %s (%s) error: %s", symbol, repo, e)

    if pending_rows:
        db.executemany(
            "INSERT INTO social_events "
            "(symbol, source, ts, event_type, numeric_value, text_snippet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            pending_rows,
        )
        db.commit()
    log.info("collect_github: %d repos tracked", count)
    return count


def run_social_collection(db):
    """Master function: run all social data collectors with error isolation."""
    log.info("run_social_collection: starting")

    collectors = [
        ("fear_greed", lambda: collect_fear_greed(db)),
        ("coingecko_trending", lambda: collect_coingecko_trending(db)),
        ("rss_feeds", lambda: collect_rss_feeds(db)),
        ("reddit", lambda: collect_reddit(db)),
        ("github", lambda: collect_github(db)),
    ]

    for name, collector in collectors:
        try:
            collector()
        except Exception as e:
            log.warning("run_social_collection: %s failed: %s", name, e)

    log.info("run_social_collection: complete")
