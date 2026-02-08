# TradeMind.bot - Product Vision

## Mission
Build an AI-powered options trading platform that democratizes sophisticated trading strategies (calendar spreads, theta strategies) for retail traders.

## Product: TradeMind.bot

### What It Does
- Generates AI-driven trading signals for options strategies
- Automates trade execution via Tastytrade API
- Provides IB paper trading for strategy validation
- Real-time signal delivery via WebSocket

### Target Users
1. **Retail Options Traders** - Want systematic approach to options
2. **Income Seekers** - Looking for theta/premium collection strategies
3. **Active Traders** - Want AI assistance without full automation

## Core Strategies

### 1. Theta Strategy (Cash-Secured Puts)
- Sell puts on high-quality ETFs (SPY, QQQ, IWM)
- Target 30-45 DTE, 0.20-0.30 delta
- Profit from time decay in sideways/bullish markets

### 2. Calendar Spreads
- Sell near-term options, buy longer-dated options
- Profit from volatility differential
- Target earnings or event-driven scenarios

## Architecture (Hybrid)
- **Market Data**: Interactive Brokers Gateway
- **Order Execution**: Tastytrade API (production)
- **Validation**: IB Paper Trading (parallel)
- **Frontend**: Next.js on Vercel
- **Backend**: Python on EC2

## Current Status (Feb 2026)
- ✅ Backend trading logic complete
- ✅ Frontend signals UI complete
- ✅ Tastytrade OAuth integration
- ⚠️ IB Gateway connection needs debugging
- 🔄 Gen Z UX enhancements in progress
