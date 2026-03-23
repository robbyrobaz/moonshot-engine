# Crypto Agent Bootstrap

**Last updated:** 2026-03-23 06:20 MST

## ✅ BLOFIN V1 — LIVE (Restored Mar 22 2026)

### Current Status
- ✅ Paper trading: LIVE (12 closed trades, last trade 06:09 MST)
- ✅ Dashboard: http://127.0.0.1:8892 (blofin-dashboard.service ACTIVE)
- ✅ OHLCV Ingestor: blofin-ohlcv-ingestor.service ACTIVE (244k+ candles, running 28h)
- ✅ 30 active strategies, 11,558 tradeable pairs
- ⛔ Pipeline timer: STOPPED per Rob's order — do NOT restart without approval

### Services
- `blofin-stack-paper.service` — ACTIVE (running since Sun 17:21)
- `blofin-dashboard.service` — ACTIVE (running since Sun 20:42)
- `blofin-ohlcv-ingestor.service` — ACTIVE (running since Sat 01:53)

### Restoration Weekend (Mar 21-22)
- Downloaded 2.0GB 1-min OHLCV candles from 3 sources (Blofin, OKX, Binance.US)
- Built WebSocket ingestor for real-time candle updates
- All 71 strategies intact, backtest engine updated to read parquet via DuckDB
- Data: 467 parquet files at /mnt/data/blofin_ohlcv/1m/*.parquet

---

## Moonshot v2 — Tournament Status (Mar 23 06:20)

### Champion
- **SHORT Champion:** de44f72dbb01
  - FT PnL: +0.68% (68.37 basis points)
  - FT trades: 388
  - Status: HEALTHY ✅
- **New Listing:** new_listing (placeholder, 0 trades)

### Tournament Numbers
| Stage | Count |
|-------|-------|
| Backtest queue | 8 models |
| Forward test | 689 models |
| Champion | 2 models (1 active + new_listing) |
| Retired | 2,401 models (77.5%) |
| Open positions | 937 |
| **Total models** | 3,100 |

### Services
- `moonshot-v2.timer` — ACTIVE (4h cycle)
- `moonshot-v2-dashboard.service` — ACTIVE
- Dashboard: http://127.0.0.1:8893

---

## Git Status
- `blofin-stack`: CLEAN
- `blofin-moonshot-v2`: CLEAN
