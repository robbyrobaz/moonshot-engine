# Hang Audit Report — Moonshot v2 Orchestration
**Date:** 2026-03-18  
**Audited files:** `orchestration/run_cycle.py`, `src/data/extended.py`, `src/data/social.py`, `systemd/moonshot-v2.service`, `systemd/moonshot-v2-social.service`

---

## Summary

Three hung processes in 48 hours are caused by **three separate bugs that compound each other**. The Reddit rate-limit loop is a slow infinite retry. The systemd `TimeoutStopSec=infinity` config ensures the OS can never forcibly kill a hung process. The 470-symbol extended data fetch has no overall wall-clock timeout. Any one of these alone is manageable; all three together produce 37–38 hour zombies.

---

## Bug 1 — Reddit Infinite Retry (No Circuit Breaker)

**File:** `src/data/social.py`, function `collect_reddit()`, lines ~120–150

**The code:**
```python
for subreddit in REDDIT_SUBREDDITS:          # 3 subreddits
    for symbol in top_symbols[:50]:           # up to 50 symbols
        try:
            resp = requests.get(url, ..., timeout=10)
            if resp.status_code == 429:
                log.warning("collect_reddit: rate limited on r/%s, pausing", subreddit)
                time.sleep(5)
                continue              # ← CONTINUES TO NEXT SYMBOL
            ...
            time.sleep(1.0)
        except Exception as e:
            log.warning(...)
```

**The bug:** Reddit's 429 is IP-wide — the ban applies to ALL requests from this IP, not just one query. When rate limited on `r/SatoshiStreetBets`, the code:
1. Sleeps 5 seconds
2. `continue`s to the **next symbol** in the inner loop
3. That symbol also gets 429 immediately
4. Repeat for all 50 symbols

**Time math:**
- 3 subreddits × 50 symbols × 5s sleep on 429 = **750 seconds = 12.5 minutes**
- The social service has `TimeoutStartSec=600` (10 minutes) — this loop exceeds it
- After SIGTERM, if the process is mid-`time.sleep(5)`, it sleeps up to 5 more seconds before Python processes the signal
- `TimeoutStopSec` on social.service is not set → defaults to 90s → SIGKILL fires, service eventually dies

**Log evidence from March 16:**
```
01:30:17 run_social_collection: starting
01:32:29 collect_reddit: rate limited on r/SatoshiStreetBets, pausing
01:32:34 collect_reddit: rate limited on r/SatoshiStreetBets, pausing
[repeated every ~5 seconds for 20+ lines observed]
```
This is 50 symbols × 5s sleep = 250s of rate-limit thrashing on one subreddit alone.

---

## Bug 2 — `TimeoutStopSec=infinity` (The Zombie Maker)

**File:** Live systemd unit at `/home/rob/.config/systemd/user/moonshot-v2.service`

**The critical difference between repo and live:**

| Setting | Repo version | Live version |
|---------|-------------|-------------|
| `TimeoutStartSec` | `1800` (30 min) | `14400` (4 hours) |
| `TimeoutStopSec` | *(not set, defaults to 90s)* | **`infinity`** |

**How systemd kills oneshot services:**
1. `TimeoutStartSec` expires → systemd sends **SIGTERM**
2. Process has `TimeoutStopSec` time to exit
3. If it doesn't exit: systemd sends **SIGKILL**

With `TimeoutStopSec=infinity`, step 3 **never happens.** systemd sends SIGTERM and then waits forever. If the process is stuck in a blocking C-library call (e.g., `requests` socket recv, or SQLite busy-wait), Python may not process the SIGTERM signal promptly — and since SIGKILL never comes, the process becomes a permanent zombie.

**This is why the Mar 16 16:25 main cycle was still visible at Mar 18 06:32 (38 hours later).** The process received SIGTERM from systemd (after 4-hour `TimeoutStartSec`) but `TimeoutStopSec=infinity` means it was never SIGKILL'd.

**The "Social timer hung 38h" incident is likely the same Mar 16 16:25 main cycle process** — 38 hours after Mar 16 ~16:32 is Mar 18 ~06:32, which matches exactly. The "social" label may reflect how the zombie was identified (social timer triggering while the old cycle was still alive).

---

## Bug 3 — `fetch_all_extended` Has No Overall Wall-Clock Timeout

**File:** `src/data/extended.py`, function `fetch_all_extended()`

**What it does:**
1. `fetch_funding_rates(db, 470 symbols)` — one HTTP call per symbol, 15s timeout each
2. `fetch_open_interest(db, 470 symbols)` — same
3. `fetch_mark_prices(db, 470 symbols)` — same
4. `fetch_tickers(db)` — single bulk call

**Rate limit delay:** `delay = 1.0 / 2.5 = 0.4s` between symbols

**Time math under normal conditions:**
- 470 symbols × 0.4s sleep × 3 serial fetches = **564 seconds = ~9.5 minutes** (just for sleeps)
- Plus actual HTTP round trips: 470 × 3 × ~0.3s avg = ~7 more minutes
- **Normal total: ~16-20 minutes**

**Time math if Blofin becomes slow/unresponsive:**
- Each request: `timeout=15` → up to 15s per symbol
- 470 × 15s × 3 batches = **21,150 seconds = ~5.9 hours**
- No global "bail out if this takes more than N minutes" guard

When Blofin enters a degraded state (accepts connections but sends data slowly), `timeout=15` fires correctly per request, but with 1,410 requests that's still hours of cumulative wall time. The function has no circuit breaker to abort early.

**The "CPU active but no network connections" evidence** is consistent with this scenario: Blofin goes unresponsive, all 1,410 requests time out after 15s each, and the process burns through the loop via exception handlers (CPU work) without making active connections.

---

## Bug 4 — Social Timer Does NOT Call `fetch_all_extended` (Clarification)

The task description asked: "Explain why --social flag calls expensive fetch_all_extended()."

**It doesn't.** These are completely separate code paths:

```python
# run_cycle.py
if len(sys.argv) > 1 and sys.argv[1] == "--social":
    run_social_collection()          # → src/data/social.py only
else:
    success = run_cycle()            # → calls fetch_all_extended
```

`run_social_collection()` only calls: `collect_fear_greed`, `collect_coingecko_trending`, `collect_rss_feeds`, `collect_reddit`, `collect_github`. It does NOT call `fetch_all_extended` or anything in `src/data/extended.py`.

**However**, there is an indirect coupling: `collect_reddit()` queries `open_interest` to find top symbols, which is populated by the main cycle's `fetch_open_interest`. If the main cycle hasn't run recently, Reddit queries against stale/missing data.

---

## Proposed Fixes

### Fix 1: Circuit Breaker in `collect_reddit`

```python
def collect_reddit(db, top_symbols: list[str] | None = None) -> int:
    # ... existing setup code ...
    
    MAX_CONSECUTIVE_429 = 3  # Give up on a subreddit after 3 consecutive failures
    
    for subreddit in REDDIT_SUBREDDITS:
        consecutive_429 = 0
        
        for symbol in top_symbols[:50]:
            if consecutive_429 >= MAX_CONSECUTIVE_429:
                log.warning("collect_reddit: r/%s persistently rate limited, skipping rest", subreddit)
                break  # Skip remaining symbols for this subreddit
            
            try:
                resp = requests.get(url, ..., timeout=10)
                if resp.status_code == 429:
                    consecutive_429 += 1
                    wait = min(5 * consecutive_429, 30)  # Backoff, cap at 30s
                    log.warning(
                        "collect_reddit: rate limited on r/%s (%d consecutive), waiting %ds",
                        subreddit, consecutive_429, wait
                    )
                    time.sleep(wait)
                    continue
                
                consecutive_429 = 0  # Reset on success
                # ... rest of processing ...
                time.sleep(1.0)
            
            except Exception as e:
                log.warning("collect_reddit: r/%s %s error: %s", subreddit, symbol, e)
```

### Fix 2: Remove `TimeoutStopSec=infinity` from systemd units

**`/home/rob/.config/systemd/user/moonshot-v2.service`** — remove or replace:
```ini
# REMOVE THIS LINE:
TimeoutStopSec=infinity

# REPLACE WITH:
TimeoutStopSec=30
```

Then reload: `systemctl --user daemon-reload`

This ensures that 30 seconds after SIGTERM, systemd sends SIGKILL and the process is guaranteed dead.

Also consider reducing `TimeoutStartSec` back to something reasonable. 4 hours is excessive for a cycle that should take 20-40 minutes:
```ini
TimeoutStartSec=3600  # 1 hour max — if it's not done in 1h, something is wrong
TimeoutStopSec=30
```

### Fix 3: Add Overall Timeout to `fetch_all_extended`

```python
import threading
import concurrent.futures

def fetch_all_extended(db, symbols: list[str], timeout_sec: int = 900):
    """Master function: fetch all extended market data for a cycle.
    
    Args:
        timeout_sec: Hard wall-clock limit for the entire operation (default 15 min).
                     Raises TimeoutError if exceeded.
    """
    log.info("fetch_all_extended: starting for %d symbols", len(symbols))
    
    def _run():
        fetch_funding_rates(db, symbols)
        fetch_open_interest(db, symbols)
        fetch_mark_prices(db, symbols)
        fetch_tickers(db)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError:
            log.error(
                "fetch_all_extended: TIMED OUT after %ds — Blofin may be unresponsive",
                timeout_sec
            )
            raise TimeoutError(f"fetch_all_extended exceeded {timeout_sec}s wall clock limit")
    
    log.info("fetch_all_extended: complete")
```

### Fix 4: Add Per-Subreddit Timeout to Social Collection

As a belt-and-suspenders measure, wrap the entire `collect_reddit` call with a timeout:

```python
# In run_social_collection (social.py)
import signal

def _timeout_handler(signum, frame):
    raise TimeoutError("collector timeout")

def run_social_collection(db):
    log.info("run_social_collection: starting")
    
    collectors = [
        ("fear_greed", lambda: collect_fear_greed(db), 30),
        ("coingecko_trending", lambda: collect_coingecko_trending(db), 30),
        ("rss_feeds", lambda: collect_rss_feeds(db), 60),
        ("reddit", lambda: collect_reddit(db), 120),   # max 2 min for Reddit
        ("github", lambda: collect_github(db), 60),
    ]
    
    for name, collector, timeout in collectors:
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            collector()
            signal.alarm(0)  # Cancel alarm
        except TimeoutError:
            signal.alarm(0)
            log.warning("run_social_collection: %s timed out after %ds, skipping", name, timeout)
        except Exception as e:
            signal.alarm(0)
            log.warning("run_social_collection: %s failed: %s", name, e)
    
    log.info("run_social_collection: complete")
```

---

## Priority Order

| Priority | Fix | Impact |
|----------|-----|--------|
| 🔴 **CRITICAL** | Remove `TimeoutStopSec=infinity` from live service | Stops 37h zombie processes immediately |
| 🔴 **CRITICAL** | Add circuit breaker to `collect_reddit` | Stops Reddit rate-limit spiral |
| 🟡 **HIGH** | Add overall timeout to `fetch_all_extended` | Prevents multi-hour stalls from Blofin degradation |
| 🟡 **HIGH** | Add per-collector timeout to `run_social_collection` | Defense-in-depth for social collection |
| 🟢 **LOW** | Reduce main service `TimeoutStartSec` from 14400→3600 | Better visibility into truly hung cycles |

---

## Root Cause Summary

The 37-38 hour hangs are a combination of:

1. **Persistent Reddit 429s** → slow 12+ minute loop in social collection that exceeds `TimeoutStartSec=600`
2. **`TimeoutStopSec=infinity`** on the main service → systemd sends SIGTERM but NEVER sends SIGKILL; processes that don't immediately respond to the signal live forever
3. **No wall-clock timeout on `fetch_all_extended`** → if Blofin degrades, the function can legitimately run for hours, keeping the main cycle alive long enough to hit the SIGTERM-but-no-SIGKILL trap

The fix hierarchy is: kill the zombie config first (2-line systemd change, no code deploy), then fix the Reddit loop, then add timeouts to extended data fetch.
