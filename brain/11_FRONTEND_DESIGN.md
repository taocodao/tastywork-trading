# Frontend Design - trademind-app

## Overview
Next.js 14 frontend for TradeMind.bot, deployed on Vercel.

## Tech Stack
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- WebSocket for real-time signals

## Key Pages

### /signals
- Real-time signal cards
- Approve/reject actions
- WebSocket subscription via SignalProvider

### /positions
- Active positions table
- P&L tracking
- Exit actions

### /dashboard
- Gamified stats (streaks, achievements)
- Portfolio overview
- Recent activity

## Components

### SignalCard
- Displays signal details
- "Why AI Picked This" expandable section
- Approve button → calls API → executes trade

### SignalProvider
- WebSocket connection to ws.trademind.bot
- Subscribes to channels: theta_entry, theta_exit, calendar_spread
- Provides signals to child components via context

### PositionCard
- Shows open position details
- Real-time P&L updates
- Close position action

## API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| /api/signals | GET | Get recent signals |
| /api/signals/approve | POST | Approve and execute signal |
| /api/positions | GET | Get user positions |
| /api/tastytrade/auth | POST | OAuth callback |

## Environment Variables
- `NEXT_PUBLIC_WS_URL` - WebSocket server URL
- `TASTYTRADE_CLIENT_ID` - OAuth client ID
- `TASTYTRADE_CLIENT_SECRET` - OAuth secret
