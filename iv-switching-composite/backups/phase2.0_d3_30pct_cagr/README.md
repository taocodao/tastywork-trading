# Phase 2.0 + Mode D3 Snapshot — 2026-03-22

## Results at Time of Backup
- CAGR: 30.6%
- Max Drawdown: -53.9%
- Final NAV: $171,243 (from $25,000)
- Alpha vs QQQ: +13.1 pp

## Architecture
- Mode A: TQQQ 12-delta CSPs, weekly, 50% PT, -200% SL
- Mode B: QQQM ZEBRA (2x 70-delta + 1x 50-delta, 75 DTE), 15% NAV/slot, time-stop 21 DTE
- Mode C: QQQ Bear Call Spreads (30/20 delta, 45 DTE, 50% PT)
- Mode D1: Pre-positioned VIX calls
- Mode D2: SQQQ tactical (7% NAV, 21 day max)
- Mode D3: Aggressive crash-recovery ZEBRA entry (20% NAV/slot) — caused scaling issue, fixed in next version

## Files
- backtest_composite.py
- portfolio.py
- position_sizer.py
- regime_engine.py
