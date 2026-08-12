# Fix: ECONNREFUSED 127.0.0.1:8002 in Vercel
**Date:** 2026-01-23
**Status:** Implemented

## Problem
When approving signals, Vercel serverless functions returned:
```
Error: connect ECONNREFUSED 127.0.0.1:8002
```

The frontend API routes (`approve/route.ts`, `signals/route.ts`) were defaulting to `localhost:8002` when `TASTYTRADE_API_URL` env var was not set.

## Root Cause
- The Python backend runs on EC2 (`34.203.194.137:8002`), not on Vercel's serverless container.
- Vercel functions can't access `localhost` - they need the public EC2 IP.

## Solution
Updated fallback URLs in:
1. `src/app/api/signals/[id]/approve/route.ts`
2. `src/app/api/signals/route.ts`

Changed:
```typescript
const PYTHON_API = process.env.TASTYTRADE_API_URL || 'http://localhost:8002';
```
To:
```typescript
const PYTHON_API = process.env.TASTYTRADE_API_URL || 'http://34.203.194.137:8002';
```

## Better Long-Term Fix
Set the env var in Vercel dashboard:
```
TASTYTRADE_API_URL=http://34.203.194.137:8002
```
This avoids hardcoding the IP in source code.
