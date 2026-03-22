# Crypto Agent Bootstrap — BLOFIN RESTORATION

**Last updated:** 2026-03-22 07:05 MST

## 🔧 ACTIVE RESTORATION (Mar 20 Database Loss)

### What Happened
- Mar 20 2026: Database lost. All code intact in repo.
- Architecture change: tick data feed → 1-min candle WebSocket (blofin-ohlcv-ingestor.service)
- Old tick data ingestor RETIRED. New source: 1-min OHLCV candles via WebSocket.

### OHLCV Backfill (3 parallel jobs)
- ✅ **Binance.US** — COMPLETE (Mar 21 6:39 PM). 2 done, 6 failed, 147 skipped. 776K candles.
- ✅ **OKX** — COMPLETE (Mar 22 1:32 AM). 121 done, 0 failed, 15 skipped. 39.2M candles in 12.2h.
- ❌ **Blofin API** — DIED at symbol 41/182 (~1:50 AM Mar 22). Process vanished silently mid-COOKIE-USDT. NOT restarted (not critical).
- **Result:** 467 parquet files, 2.1GB at /mnt/data/blofin_ohlcv/1m/
- 2 corrupt parquets: C98-USDT.parquet, CKB-USDT.parquet (should be deleted and re-fetched)
- Backfill logs: blofin-stack/logs/ohlcv_backfill*.log

### Backtest Sweep Status ⏳ IN PROGRESS
**RUNNING:** backtest_sweep_v7_fixed.py (scripts/backtest_sweep_v7_fixed.py)
- Started: 06:40 MST Mar 22
- Coverage: 62 strategies × 467 symbols = 28,954 backtests
- Writing to: **strategy_coin_performance** table (NOT strategy_backtest_results)
- Rate: ~5 tasks/sec, ETA ~8:10 MST
- Saves: Batch of 500, 0 errors per batch
- As of 07:00: 4,300/28,954 (15%), 127 pairs passing gates so far
- Cron: Opus 30min check (job 5815c435) monitoring + auto-progressing

### Sonnet's Overnight Failures (for context)
- v2: multiprocessing broke relative imports, completed 2976 tasks but saved ZERO results
- v3: import fix only loaded 2/62 strategies
- v4: sequential worked but only saved at end — killed before save
- v5: batch saves but wrong column name (strategy vs strategy_name)
- v6: correct schema but bt_pnl_pct=0.0 for all rows (wrong dict key for final_capital)
- v7_fixed: CORRECT — final_capital from bt_result root, real pnl values

### After Backtest Completes (cron handles automatically)
1. Verify results in strategy_coin_performance (PF ≥ 1.35, trades ≥ 100, MDD < 50%)
2. Start paper trading: `systemctl --user start blofin-stack-paper.service`
3. Verify dashboard: http://127.0.0.1:8892
4. Cron self-disables when fully restored
5. **ASK ROB** before restarting pipeline timer

---

## System Status (as of Mar 22 07:05)
- ✅ WebSocket ingestor: blofin-ohlcv-ingestor.service (1-min candles flowing)
- ✅ Historical data: 467 parquet files, 2.1GB (Binance+OKX complete, Blofin partial)
- ⏳ Backtest sweep v7: RUNNING (~15% complete, 4000+ rows written, 127 passing gates)
- ⛔ Paper trading: STOPPED (waiting for backtest completion)
- ✅ Dashboard: blofin-dashboard.service running (port 8892) — waiting for data
- ✅ Moonshot v2: HEALTHY, unaffected

---

## Moonshot v2 — Tournament Status (Mar 17 snapshot)

### Champions (3 active)
- **SHORT Champion:** de44f72dbb01, FT_PF=2.22, FT_PnL=0.68% — HEALTHY ✅
- **LONG Champion:** 9b842069b20d, FT_PF=0.22, FT_PnL=-2.01% — needs investigation
- **New Listing:** new_listing, FT_trades=0 — waiting

### Tournament Numbers
| Stage | Count |
|-------|-------|
| Backtest | 32 models |
| FT | 423 models (393 SHORT, 30 LONG) |
| Retired | 1,792 models |
| Open positions | 884 |

---

## Git Status
- `blofin-stack`: multiple sweep script versions (v2-v7) from restoration attempts
- `blofin-moonshot-v2`: CLEAN
