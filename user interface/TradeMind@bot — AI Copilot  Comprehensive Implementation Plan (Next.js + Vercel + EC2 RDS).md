# TradeMind@bot — AI Investment Copilot: Comprehensive Implementation Plan
## Executive Summary
This plan delivers a fully production-ready specification for integrating 5 high-demand AI features into TradeMind@bot as a unified **AI Investment Copilot** — not just a chatbot. The implementation targets Next.js 14 (App Router) on Vercel for the frontend/serverless layer, with a dedicated EC2 backend server and AWS RDS PostgreSQL for data persistence. All 5 features leverage the Perplexity Sonar API with streaming responses and are designed to match TradeMind@bot's existing dark UI design system (deep navy/black cards, purple accents, green/red signals, bottom tab nav).

The 5 features are sequenced from highest to lowest conversion impact:
1. **Position Screenshot Analyzer** — the #1 most-downloaded AI trading feature across all competitor apps[^1][^2]
2. **Pre-Market AI Briefing** — daily push habit; iOS opt-in 51%, Android 81%[^3][^4]
3. **Options Strategy Builder** — strongest Pro-tier upgrade driver; Robinhood, Public.com, Tickeron all gate this[^5][^6][^7]
4. **Stock Deep Dive ("Why did it drop?")** — live web-search answers via Sonar; broadest daily appeal[^8][^9]
5. **Weekly AI Performance Debrief** — churn prevention; AI apps without weekly touchpoints show severe drop-off[^10][^11]



***
## Part 1: Competitor Analysis by Feature
### Feature 1 — Position Screenshot Analyzer
**What competitors do:**

| Competitor | Approach | Gap vs. TradeMind |
|---|---|---|
| Chart AI (100K+ downloads)[^1] | Analyze uploaded screenshots for technical patterns | No signal injection — pure chart analysis |
| Trade AI (App Store Top Finance)[^12] | Instant chart analysis + stock picks | No proprietary signal alignment |
| TrendSpider Sidekick[^8] | "Can see what you see" — analyzes active chart in session | Desktop-only, $47–$239/mo, no mobile screenshot |
| Tickeron FLMs[^9] | Pattern recognition + buy/sell signal overlay | Autonomous bots only; no user screenshot input |

**TradeMind's edge:** The TurboCore signal context (BULL/BEAR/SIDEWAYS + ML score) injected into every analysis transforms a generic chart read into a regime-aligned assessment. No competitor combines user-submitted screenshots with a proprietary quantitative signal.
### Feature 2 — Pre-Market AI Briefing
**What competitors do:**
- TrendSpider sends AI alert automation (Jan 2026 update) — but only for pre-set conditions, not a narrative daily brief[^13]
- Tickeron provides daily buy/sell signals but requires the user to log in to see them — no push delivery[^14]
- No major competitor delivers a structured, AI-generated pre-market narrative via PWA push notification at 8:15 AM with live web search[^3]

**TradeMind's edge:** Perplexity Sonar's live web search generates a genuinely fresh briefing with today's pre-market prices, VIX level, and earnings calendar — not a templated newsletter. The push notification habit (4× daily opens) is unmatched by desktop-first tools.[^15][^3]
### Feature 3 — Options Strategy Builder
**What competitors do:**

| Competitor | Approach | Pricing | Gap |
|---|---|---|---|
| Robinhood[^6] | Filter by outlook; shows payoff diagram | Free (but no AI signal integration) | No AI regime context |
| Public.com[^7] | "Turn thesis into structured trade" — multi-leg | Free tier | No IV analysis |
| Tickeron Options Bots[^5] | 5-min/15-min bots targeting 0DTE, up to +481% annualized claimed | $90–$200/mo | Bot-driven, not user-configured |
| TrendSpider AI Strategy Lab[^8] | Build custom ML models on charts | $47–$239/mo | No options-specific builder |

**TradeMind's edge:** TradeMind's builder combines the user's thesis, today's TurboCore regime, and IV environment in one prompt to Sonar Reasoning — producing strategy suggestions calibrated to both the market regime and current options pricing conditions.
### Feature 4 — Stock Deep Dive
**What competitors do:**
- TrendSpider Sidekick AI answers questions about price, market conditions, historical data — but uses its own LLM, not live web search[^8]
- Tickeron provides pattern analysis + earnings screening — but technical only, no news synthesis[^16]
- AlphaSense ($80/mo) delivers institutional-grade news synthesis but has no signal alignment layer[^9]

**TradeMind's edge:** Perplexity Sonar's live web search answers "why did QQQ drop today?" with today's actual news — not training-data hallucinations. Injecting TurboCore alignment into the output makes it contextually actionable in a way no competitor replicates.[^15]
### Feature 5 — Weekly AI Performance Debrief
**What competitors do:**
- TrendSpider has backtesting and strategy tester reports — but they are strategy-level, not user-behavior coaching[^17]
- Tickeron has portfolio management tools but no personalized weekly narrative[^16]
- No competitor delivers a weekly AI coaching debrief that compares user behavior to a proprietary signal benchmark

**TradeMind's edge:** The debrief is anchored in the user's actual trade data vs. TurboCore signal performance — making it the most personalized content in the app and the strongest churn-prevention mechanism.[^10][^11]

***
## Part 2: System Architecture — Vercel + EC2 + RDS
### Architecture Overview
The recommended hybrid architecture separates concerns cleanly:

```
┌──────────────────────────────────────────────────────┐
│  USER (Mobile Browser / PWA)                         │
└──────────────────────┬───────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼───────────────────────────────┐
│  VERCEL (Next.js 14 App Router)                      │
│  • Page rendering (RSC + Client Components)           │
│  • /api/ai/* routes → Perplexity API calls           │
│  • /api/stripe/* routes → Stripe webhooks            │
│  • /api/cron/* routes → Vercel Cron Jobs             │
│  • PWA service worker + VAPID push                   │
│  • Auth via Privy middleware                         │
└──────────┬───────────────────────┬───────────────────┘
           │                       │
           │ VPC / HTTPS            │ RDS IAM Auth
┌──────────▼───────────┐  ┌────────▼───────────────────┐
│  AWS EC2 (Backend)   │  │  AWS RDS PostgreSQL         │
│  • Signal engine     │  │  • user_settings            │
│  • Tastytrade sync   │  │  • ai_chat_logs             │
│  • TurboCore ML      │  │  • ai_briefings             │
│  • Cron signal runs  │  │  • ai_debriefs              │
│  • WebSocket server  │  │  • referrals                │
│  Express.js API      │  │  • positions                │
└──────────────────────┘  └────────────────────────────┘
           │
┌──────────▼───────────┐
│  Perplexity API      │
│  (Sonar + Reasoning) │
└──────────────────────┘
```

**Why this split:**
- Vercel handles all user-facing Next.js rendering, API routes, cron jobs, and PWA push — with zero-config deploys and automatic scaling[^18]
- EC2 runs the TurboCore ML signal engine and Tastytrade sync, which require persistent processes and are unsuitable for serverless functions[^19]
- RDS PostgreSQL on AWS connects to Vercel via OIDC federation + IAM auth — no hardcoded passwords, short-lived tokens, no connection exhaustion with RDS Proxy[^20][^21]
### Vercel ↔ EC2 Communication
```typescript
// lib/signals.ts — Vercel calls EC2 signal endpoint
export async function getTodaySignal(): Promise<Signal> {
  // Try Redis cache first (15-min TTL)
  const cached = await redis.get('turbocore:signal:today')
  if (cached) return JSON.parse(cached)

  // Call EC2 internal API
  const res = await fetch(`${process.env.EC2_INTERNAL_API}/signal/today`, {
    headers: { 
      'x-api-key': process.env.EC2_API_SECRET!,
      'Content-Type': 'application/json'
    },
    next: { revalidate: 900 } // 15-min ISR cache
  })
  
  const signal = await res.json()
  await redis.setex('turbocore:signal:today', 900, JSON.stringify(signal))
  return signal
}
```

```typescript
// EC2 Express.js — signal endpoint (port 3001, behind ALB)
app.get('/signal/today', authenticate, async (req, res) => {
  const signal = await runTurboCorePrediction()
  res.json({
    regime: signal.regime,           // 'BULL' | 'BEAR' | 'SIDEWAYS'
    confidence: signal.confidence,   // 0-100
    mlScore: signal.mlScore,         // 0-100
    allocation: signal.allocation,   // { TQQQ: 80, SGOV: 20 }
    timestamp: new Date().toISOString()
  })
})
```
### Vercel ↔ RDS Connection (IAM Auth, No Passwords)
```typescript
// lib/db.ts — Vercel serverless safe connection pooling
import { Pool } from 'pg'
import { Signer } from '@aws-sdk/rds-signer'
import { awsCredentialsProvider } from '@vercel/functions/oidc'
import { attachDatabasePool } from '@vercel/functions'

const signer = new Signer({
  hostname: process.env.PGHOST!,
  port: 5432,
  region: process.env.AWS_REGION!,
  username: process.env.PGUSER!,
  credentials: awsCredentialsProvider({
    roleArn: process.env.AWS_ROLE_ARN!,
  }),
})

const pool = new Pool({
  host: process.env.PGHOST,
  user: process.env.PGUSER,
  database: process.env.PGDATABASE,
  password: () => signer.getAuthToken(), // rotates automatically
  port: 5432,
  ssl: { rejectUnauthorized: false },
  max: 20,
})

attachDatabasePool(pool) // Vercel utility — manages connections across serverless invocations
export const query = (sql: string, args: unknown[]) => pool.query(sql, args)
```

> **RDS Proxy required:** Always put RDS Proxy between Vercel serverless functions and RDS PostgreSQL. Each Vercel function invocation opens a new connection — without a proxy, a spike in traffic will exhaust PostgreSQL's `max_connections` limit. RDS Proxy multiplexes connections automatically.[^21]
### Environment Variables
```bash
# .env.local (development)
# Perplexity
PERPLEXITY_API_KEY=pplx-...

# EC2 Backend
EC2_INTERNAL_API=https://api.trademind.bot
EC2_API_SECRET=...

# AWS RDS
PGHOST=trademind-db.cluster-xxxx.us-east-1.rds.amazonaws.com
PGUSER=vercel_user
PGDATABASE=trademind
PGPORT=5432
AWS_REGION=us-east-1
AWS_ROLE_ARN=arn:aws:iam::123456789:role/VercelRDSRole

# Vercel/App
NEXT_PUBLIC_VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
CRON_SECRET=...
NEXT_PUBLIC_PRIVY_APP_ID=...

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

***
## Part 3: Mobile UI Design System — Matching Your App
The existing TradeMind@bot UI (as seen in the attached screenshot) uses:
- **Background:** Deep navy/near-black (`#0A0B14`)
- **Cards:** Dark navy with subtle border (`#12152A` + `border: 1px solid rgba(255,255,255,0.08)`)
- **Purple accent:** Crown/pro badge, active states (`#7B5EA7` / `#8B5CF6`)
- **Green:** Positive signals, gains (`#10B981`)
- **Red:** Cancellations, losses, bear signals (`#EF4444`)
- **Yellow/amber:** SIDEWAYS signal (`#F59E0B`)
- **Typography:** White headers, `text-zinc-400` subtext
- **Bottom nav:** 5-tab persistent bar with icon + label

The AI features should integrate as a new **5th tab ("AI")** in the existing bottom nav, maintaining full visual consistency.
### Shared Component Library (TypeScript)
```typescript
// components/ui/AIFeatureCard.tsx
interface AIFeatureCardProps {
  icon: string
  title: string
  description: string
  tier: 'all' | 'pro' | 'bundle'
  messagesRequired: number
  href: string
  userTier: string
}

export function AIFeatureCard({ icon, title, description, tier, messagesRequired, href, userTier }: AIFeatureCardProps) {
  const isLocked = (tier === 'pro' && userTier === 'core') || 
                   (tier === 'bundle' && !['bundle'].includes(userTier))
  
  return (
    <Link href={isLocked ? '#' : href}>
      <div className={`relative rounded-xl border p-4 
        ${isLocked 
          ? 'bg-[#0D1020] border-zinc-800 opacity-60' 
          : 'bg-[#12152A] border-[rgba(255,255,255,0.08)] active:scale-[0.98]'
        } transition-all`}>
        {isLocked && (
          <div className="absolute top-3 right-3 bg-purple-600/20 rounded-full px-2 py-0.5 text-xs text-purple-400 font-medium">
            {tier === 'pro' ? 'PRO' : 'BUNDLE'}
          </div>
        )}
        <div className="text-2xl mb-2">{icon}</div>
        <div className="text-white font-semibold text-sm">{title}</div>
        <div className="text-zinc-400 text-xs mt-1">{description}</div>
        {!isLocked && (
          <div className="text-zinc-500 text-xs mt-2">Uses {messagesRequired} AI messages</div>
        )}
      </div>
    </Link>
  )
}
```

```typescript
// components/ui/SignalContextBadge.tsx — auto-injects into every AI feature
export function SignalContextBadge({ signal }: { signal: Signal }) {
  const colors = {
    BULL: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400',
    BEAR: 'bg-red-500/15 border-red-500/30 text-red-400',
    SIDEWAYS: 'bg-amber-500/15 border-amber-500/30 text-amber-400',
  }
  return (
    <div className={`rounded-lg border px-3 py-2 ${colors[signal.regime]}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">Today's TurboCore Signal</span>
        <span className="text-xs opacity-70">Auto-injected ↓</span>
      </div>
      <div className="flex items-center gap-3 mt-1">
        <span className="font-bold text-sm">{signal.regime}</span>
        <span className="text-xs">{signal.confidence}% confidence</span>
        <span className="text-xs">ML: {signal.mlScore}%</span>
      </div>
      <div className="text-xs mt-0.5 opacity-80">
        {Object.entries(signal.allocation).map(([k,v]) => `${k} ${v}%`).join(' / ')}
      </div>
    </div>
  )
}
```

***
## Part 4: Feature 1 — Position Screenshot Analyzer (AI Copilot Mode)
### Competitive Differentiation
Chart AI and Trade AI analyze charts in isolation. TrendSpider's Sidekick can see open charts but only on desktop. **TradeMind@bot is the only mobile app that combines user screenshot + TurboCore regime signal + live IV data in a single analysis.**[^8][^1][^12]
### Mobile Screen Design (Matches Existing UI)
```
┌─────────────────────────────────┐  390px wide
│ ←  Analyze Position            │  bg-[#0A0B14]
│─────────────────────────────────│  border-b border-zinc-800
│                                 │
│  ┌─────────────────────────┐   │  bg-[#12152A] rounded-xl
│  │  📸                     │   │  border border-[rgba(255,255,255,0.08)]
│  │  Upload screenshot      │   │  
│  │  or take photo          │   │  min-h-[140px] flex items-center
│  │                         │   │  justify-center
│  │  [Choose Photo]         │   │  
│  │  [Take Photo]           │   │  
│  └─────────────────────────┘   │
│                                 │
│  ── or describe manually ──     │  text-zinc-500 text-xs
│  ┌─────────────────────────┐   │  bg-[#0D1020] rounded-xl
│  │ "5 QQQ calls Apr 18     │   │  border border-zinc-800
│  │  $445 strike, -$340..."  │   │  min-h-[80px] p-3
│  └─────────────────────────┘   │
│                                 │
│  ┌── Today's TurboCore ──────┐ │  SignalContextBadge component
│  │ 🟢 BULL · 87% · ML:100% │ │  bg-emerald-500/15 rounded-xl
│  │ TQQQ 80% / SGOV 20%     │ │  
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │  bg-purple-600 rounded-xl
│  │  🤖 Analyze My Position │   │  h-12 text-white font-semibold
│  │     uses 3 AI messages   │   │  text-xs text-purple-200
│  └─────────────────────────┘   │
│                                 │
│  ── AI Response (streaming) ───│
│  ┌─────────────────────────┐   │  bg-[#12152A] rounded-xl
│  │ Signal Alignment: ✅    │   │  text-white text-sm
│  │ ...typing in real-time..│   │  streaming token by token
│  └─────────────────────────┘   │
│                                 │
│  ⓘ Educational analysis only  │  text-zinc-600 text-xs text-center
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │  fixed bottom-0 BottomNav
└─────────────────────────────────┘
```
### Perplexity API Integration with Streaming
```typescript
// app/api/ai/screenshot/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { getUserFromRequest, checkAIBudget, consumeMessages, getTodaySignal } from '@/lib/ai'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const user = await getUserFromRequest(req)
  const budget = await checkAIBudget(user.privyDid, 3)
  
  if (!budget.allowed) {
    return NextResponse.json({ 
      error: 'LIMIT_REACHED', used: budget.used, limit: budget.limit 
    }, { status: 402 })
  }
  
  const formData = await req.formData()
  const image = formData.get('image') as File | null
  const description = formData.get('description') as string
  const signal = await getTodaySignal()

  const messages: any[] = [{
    role: 'system',
    content: `You are TradeMind AI — an educational investment copilot.
TODAY'S TURBOCORE SIGNAL: ${signal.regime} regime, ${signal.confidence}% confidence, ML Score ${signal.mlScore}/100.
Current allocation: ${Object.entries(signal.allocation).map(([k,v]) => `${k} ${v}%`).join(', ')}.
Your job: analyze the user's position and provide educational context.
Structure your response in 4 sections:
**Signal Alignment** — does this position align with today's ${signal.regime} regime? (1 sentence)
**Key Risk Factors** — time decay, delta, distance from strike, or directional exposure (2-3 bullets)
**If Holding** — one educational scenario (2 sentences)
**If Adjusting** — one alternative educational scenario (2 sentences)
Never say "you should buy/sell". Use "If your thesis is X..." framing.
Max 300 words. Be specific and educational.`
  }]
  
  if (image) {
    const buffer = await image.arrayBuffer()
    const base64 = Buffer.from(buffer).toString('base64')
    messages.push({
      role: 'user',
      content: [
        { type: 'image_url', image_url: { url: `data:${image.type};base64,${base64}` } },
        { type: 'text', text: description || 'Analyze this position relative to today\'s signal.' }
      ]
    })
  } else {
    messages.push({ role: 'user', content: description })
  }
  
  // Streaming response — ChatGPT-like token-by-token display
  const perplexityRes = await fetch('https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'sonar',
      messages,
      max_tokens: 500,
      stream: true
    })
  })
  
  // Pipe streaming response to client
  const stream = new TransformStream()
  const writer = stream.writable.getWriter()
  const encoder = new TextEncoder()
  
  ;(async () => {
    const reader = perplexityRes.body!.getReader()
    const decoder = new TextDecoder()
    let fullContent = ''
    let usage = null
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      const chunk = decoder.decode(value)
      const lines = chunk.split('\n').filter(l => l.startsWith('data: '))
      
      for (const line of lines) {
        const json = line.replace('data: ', '')
        if (json === '[DONE]') continue
        try {
          const parsed = JSON.parse(json)
          const token = parsed.choices?.?.delta?.content || ''
          if (token) {
            fullContent += token
            await writer.write(encoder.encode(`data: ${JSON.stringify({ token })}\n\n`))
          }
          if (parsed.usage) usage = parsed.usage
        } catch {}
      }
    }
    
    // Log and deduct after stream completes
    await consumeMessages(user.privyDid, 3, 'screenshot', usage, fullContent)
    await writer.write(encoder.encode(`data: ${JSON.stringify({ done: true, remaining: budget.remaining - 3 })}\n\n`))
    await writer.close()
  })()
  
  return new Response(stream.readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive'
    }
  })
}
```

```typescript
// app/ai/screenshot/page.tsx — Client component, streaming reader
'use client'
import { useRef, useState } from 'react'
import { SignalContextBadge } from '@/components/ui/SignalContextBadge'

export default function ScreenshotAnalyzer({ signal }: { signal: Signal }) {
  const [image, setImage] = useState<File | null>(null)
  const [description, setDescription] = useState('')
  const [response, setResponse] = useState('')
  const [streaming, setStreaming] = useState(false)
  
  const handleAnalyze = async () => {
    setStreaming(true)
    setResponse('')
    
    const formData = new FormData()
    if (image) formData.append('image', image)
    formData.append('description', description)
    
    const res = await fetch('/api/ai/screenshot', { method: 'POST', body: formData })
    
    if (!res.ok) {
      const err = await res.json()
      if (err.error === 'LIMIT_REACHED') {
        // Show upgrade modal
      }
      return
    }
    
    // Read SSE stream token by token
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value)
      const lines = text.split('\n').filter(l => l.startsWith('data: '))
      for (const line of lines) {
        const json = JSON.parse(line.replace('data: ', ''))
        if (json.token) setResponse(prev => prev + json.token)
        if (json.done) setStreaming(false)
      }
    }
  }
  
  return (
    <div className="min-h-screen bg-[#0A0B14] pb-24 px-4 pt-4 space-y-4">
      <header className="flex items-center justify-between">
        <button className="text-zinc-400 text-lg">←</button>
        <h1 className="text-white font-semibold text-base">Analyze Position</h1>
        <MessageBudgetBadge />
      </header>
      
      <ImageUploadZone onSelect={setImage} selected={image} />
      
      <textarea 
        value={description}
        onChange={e => setDescription(e.target.value)}
        placeholder="Or describe: '5 QQQ calls Apr 18 $445 strike, down $340...'"
        className="w-full bg-[#0D1020] border border-zinc-800 rounded-xl p-3 text-white text-sm 
                   placeholder:text-zinc-600 min-h-[80px] resize-none focus:outline-none 
                   focus:border-purple-500/50"
      />
      
      <SignalContextBadge signal={signal} />
      
      <button
        onClick={handleAnalyze}
        disabled={streaming || (!image && !description)}
        className="w-full bg-purple-600 hover:bg-purple-700 disabled:opacity-40 
                   rounded-xl h-12 text-white font-semibold flex flex-col items-center 
                   justify-center transition-all active:scale-[0.98]"
      >
        <span>🤖 Analyze My Position</span>
        <span className="text-[10px] text-purple-200 font-normal">uses 3 AI messages</span>
      </button>
      
      {(response || streaming) && (
        <div className="bg-[#12152A] border border-[rgba(255,255,255,0.08)] rounded-xl p-4">
          <div className="text-white text-sm leading-relaxed whitespace-pre-wrap">
            {response}
            {streaming && <span className="animate-pulse text-purple-400">▌</span>}
          </div>
        </div>
      )}
      
      <p className="text-zinc-600 text-xs text-center">
        ⓘ Educational analysis only. Not personalized investment advice.
      </p>
    </div>
  )
}
```

***
## Part 5: Feature 2 — Pre-Market AI Briefing (Push + PWA)
### Mobile Screen Design
```
┌─────────────────────────────────┐
│ ←  Morning Brief   Wed Mar 18  │  bg-[#0A0B14] header
│─────────────────────────────────│
│                                 │
│  ┌─────────────────────────┐   │  bg-[#12152A] rounded-xl
│  │  🌅 TradeMind Brief     │   │  border border-[rgba(255,255,255,0.08)]
│  │  8:15 AM  ·  Today      │   │  p-4
│  │─────────────────────────│   │  divider: border-zinc-800
│  │  🟢 BULL · 87%          │   │  text-emerald-400 font-bold
│  │  TQQQ 80% / SGOV 20%    │   │  text-zinc-400 text-sm
│  │─────────────────────────│   │
│  │  📅 No economic data    │   │  text-white text-sm
│  │  📊 QQQ pre-mkt: +0.3%  │   │
│  │  🌡️ VIX: 18.2 (low)     │   │
│  │  ⚡ NVDA earnings Thu   │   │
│  │  💡 Low VIX + BULL →    │   │
│  │     cheap calls today   │   │
│  └─────────────────────────┘   │
│                                 │
│  [Ask AI About Today's Setup]  │  bg-purple-600/20 rounded-xl h-11
│                                 │
│  ── Previous Briefings ────────│  text-zinc-400 text-xs
│  ┌─────────────────────────┐   │
│  │  Tue Mar 17  🟡 SIDE    │   │  bg-[#0D1020] rounded-xl
│  │  Mon Mar 16  🟢 BULL    │   │  each row h-10 px-3
│  │  Fri Mar 13  🔴 BEAR    │   │  tap to expand
│  └─────────────────────────┘   │
│                                 │
│  ⚙️ Notification preferences  │  text-zinc-500 text-xs text-center
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │  fixed bottom BottomNav
└─────────────────────────────────┘
```
### Push Notification Payload
```
🌅 TradeMind · BULL 87% · QQQ +0.3% pre-mkt
VIX 18.2 · Low IV = good day for debit spreads
Tap for full briefing →
```
### Vercel Cron Implementation
```typescript
// vercel.json
{
  "crons": [
    { "path": "/api/cron/morning-brief", "schedule": "15 12 * * 1-5" },
    { "path": "/api/cron/weekly-debrief", "schedule": "0 22 * * 0" }
  ]
}
```

```typescript
// app/api/cron/morning-brief/route.ts
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  if (req.headers.get('authorization') !== `Bearer ${process.env.CRON_SECRET}`) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const signal = await getTodaySignal()
  
  // One Perplexity call generates the full briefing with live web search
  const res = await fetch('https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'sonar',
      messages: [{
        role: 'user',
        content: `Generate a pre-market briefing for US equity traders. 
TurboCore: ${signal.regime} (${signal.confidence}%), ML Score: ${signal.mlScore}, Allocation: ${JSON.stringify(signal.allocation)}.

Return JSON only:
{
  "headline": "<under 80 chars — signal + key market fact>",
  "pushBody": "<under 100 chars — for push notification>",
  "bullets": [
    "<economic events today>",
    "<QQQ pre-market move + %>",
    "<VIX reading + interpretation>",
    "<any earnings this week>",
    "<1 educational tip based on signal + VIX combo>"
  ]
}
Use live market data. Be specific. Today's date: ${new Date().toLocaleDateString('en-US', {weekday:'long', month:'long', day:'numeric'})}.`
      }],
      max_tokens: 400
    })
  })
  
  const data = await res.json()
  const briefing = JSON.parse(data.choices.message.content)
  
  // Store briefing in RDS
  await query(
    `INSERT INTO ai_briefings (date, regime, confidence, content) 
     VALUES ($1, $2, $3, $4) ON CONFLICT (date) DO UPDATE SET content = $4`,
    [new Date().toISOString().split('T'), signal.regime, signal.confidence, briefing]
  )
  
  // Send push to all Pro + Bundle subscribers
  const subscribers = await query(
    `SELECT push_subscription FROM user_settings 
     WHERE briefing_enabled = true AND push_subscription IS NOT NULL 
     AND subscription_tier IN ('pro', 'bundle')`, []
  )
  
  await sendBatchPush(subscribers.rows, {
    title: `🌅 TradeMind · ${signal.regime} ${signal.confidence}%`,
    body: briefing.pushBody,
    icon: '/icons/icon-192.png',
    data: { url: '/ai/briefing' }
  })
  
  return Response.json({ success: true, sent: subscribers.rows.length })
}
```
### PWA Setup (Next.js 14)
```typescript
// app/manifest.ts
import { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'TradeMind@bot',
    short_name: 'TradeMind',
    description: 'AI-powered investment copilot',
    start_url: '/',
    display: 'standalone',
    background_color: '#0A0B14',
    theme_color: '#0A0B14',
    orientation: 'portrait',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
    ]
  }
}
```

```javascript
// public/sw.js — Service Worker for push
self.addEventListener('push', (event) => {
  const data = event.data?.json()
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon || '/icons/icon-192.png',
      badge: '/icons/badge-72.png',
      data: data.data,
      vibrate: [100, 50, 100],
      tag: 'trademind-morning-brief', // replaces older notification of same tag
      renotify: true
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(clients.openWindow(event.notification.data?.url || '/ai/briefing'))
})
```

***
## Part 6: Feature 3 — Options Strategy Builder
### Mobile Screen Design
```
┌─────────────────────────────────┐
│ ←  Strategy Builder  [PRO ⭐]  │
│─────────────────────────────────│
│                                 │
│  ┌─────────────────────────┐   │  section label text-zinc-400 text-xs
│  │  Ticker                 │   │  bg-[#0D1020] rounded-xl
│  │  [QQQ            ▼ ]   │   │  h-11 px-3 border border-zinc-800
│  └─────────────────────────┘   │
│                                 │
│  Your view on this ticker:      │
│  ┌──────┐ ┌────────┐ ┌───────┐ │  pill toggle buttons
│  │Bullish│ │Neutral │ │Bearish│ │  selected: bg-purple-600 text-white
│  └──────┘ └────────┘ └───────┘ │  unselected: bg-[#0D1020] text-zinc-400
│                                 │
│  Time horizon:                  │
│  ┌──────────┐ ┌────────┐       │
│  │ < 2 weeks│ │1 month │ ...   │
│  └──────────┘ └────────┘       │
│                                 │
│  Max risk ($):                  │
│  ┌─────────────────────────┐   │
│  │  $500                   │   │
│  └─────────────────────────┘   │
│                                 │
│  Options approval level:        │
│  [Level 1] [Level 2] [Level 3] │
│                                 │
│  ┌── TurboCore ───────────────┐ │
│  │  🟢 BULL 87% (auto-loaded) │ │
│  └────────────────────────────┘ │
│                                 │
│  ┌─────────────────────────┐   │
│  │  🤖 Build My Strategy   │   │
│  │      uses 2 AI messages  │   │
│  └─────────────────────────┘   │
│                                 │
│  ── Strategies ────────────────│
│  ┌─────────────────────────┐   │  card per strategy
│  │  #1 Bull Call Spread ⭐  │   │  bg-[#12152A] rounded-xl
│  │  Buy QQQ $448c / Sell $455c │  text-white text-sm
│  │  Cost: $160  │  Max: $540  │ │  green/red for max/cost
│  │  B/E: $449.60  │  PoP: 52% │ │
│  │  [  Why this works?  ▼]  │  │  expandable drawer
│  └─────────────────────────┘   │
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │
└─────────────────────────────────┘
```
### API Route with Sonar Reasoning
```typescript
// app/api/ai/strategy/route.ts
export async function POST(req: NextRequest) {
  const user = await getUserFromRequest(req)
  
  if (!['pro', 'bundle'].includes(user.tier)) {
    return NextResponse.json({ error: 'UPGRADE_REQUIRED', requiredTier: 'pro' }, { status: 403 })
  }
  
  const budget = await checkAIBudget(user.privyDid, 2)
  if (!budget.allowed) return NextResponse.json({ error: 'LIMIT_REACHED' }, { status: 402 })
  
  const { ticker, view, horizon, maxRisk, approvalLevel } = await req.json()
  const signal = await getTodaySignal()
  
  const res = await fetch('https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: { 
      'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`, 
      'Content-Type': 'application/json' 
    },
    body: JSON.stringify({
      model: 'sonar-reasoning',  // Deep Think for options logic
      messages: [{
        role: 'system',
        content: `You are an educational options strategy assistant. Never give personalized advice.
TurboCore signal today: ${signal.regime} (${signal.confidence}% confidence). 
IV environment: use live web data to assess ${ticker} current IV rank.`
      }, {
        role: 'user',
        content: `Suggest 3 options strategies (educational) for:
Ticker: ${ticker} | View: ${view} | Horizon: ${horizon} | Max risk: $${maxRisk} | Approval Level: ${approvalLevel}

Return a JSON array of exactly 3 objects:
{
  name: string,
  legs: [{ action: "buy"|"sell", type: "call"|"put", strike: number, expiry: "YYYY-MM-DD" }],
  netCost: number (positive=debit, negative=credit),
  maxGain: number | null,
  breakeven: number,
  probabilityOfProfit: number (0-100),
  turboAlignment: "strong"|"moderate"|"neutral"|"against",
  rationale: string (1 sentence),
  riskReward: string (e.g. "1:3.4")
}

Use current market data for realistic strikes. Mark the best strategy as first in array.`
      }],
      max_tokens: 700
    })
  })
  
  const data = await res.json()
  const strategies = JSON.parse(data.choices.message.content)
  await consumeMessages(user.privyDid, 2, 'strategy_builder', data.usage)
  
  return NextResponse.json({ strategies, signal })
}
```

***
## Part 7: Feature 4 — Stock Deep Dive ("Why Did It Drop?")
### Competitive Edge
TrendSpider's Sidekick can answer market questions but uses its own LLM — no live web search. Perplexity Sonar's real-time web search answers "why did QQQ drop today?" using today's actual news and market data, not stale training data. The TurboCore alignment layer transforms a news summary into a regime-contextualized analysis.[^8][^15]
### Mobile Screen Design
```
┌─────────────────────────────────┐
│  Stock Deep Dive           🔍  │  bg-[#0A0B14]
│─────────────────────────────────│
│  ┌─────────────────────────┐   │  bg-[#0D1020] rounded-xl
│  │  QQQ                [🔎]│   │  h-11 px-3 text-white
│  └─────────────────────────┘   │
│  Recent: QQQ  NVDA  SPY  TSLA  │  text-zinc-500 text-xs chips
│                                 │
│  ── QQQ ─────────────────────  │
│  ┌─────────────────────────┐   │  analysis card
│  │ 📰 Why It Moved         │   │  bg-[#12152A] rounded-xl
│  │ Fed guidance + NVDA     │   │  border border-zinc-800
│  │ miss dragged QQQ -1.2%  │   │  text-white text-sm
│  │ in afternoon session    │   │  streaming in
│  └─────────────────────────┘   │
│  ┌─────────────────────────┐   │
│  │ 🌡️ IV Rank: 34 — Fair   │   │  text-amber-400 label
│  │ Options priced fairly.  │   │
│  │ Neither cheap nor exp.  │   │
│  └─────────────────────────┘   │
│  ┌─────────────────────────┐   │
│  │ 🧠 TurboCore View       │   │
│  │ ✅ BULL signal supports  │   │  text-emerald-400 for BULL
│  │ dip as buying opp.      │   │
│  └─────────────────────────┘   │
│  ┌─────────────────────────┐   │
│  │ 🎯 Risk Score: 3/10     │   │  color-coded 1-10
│  │ Low risk in BULL regime  │   │
│  └─────────────────────────┘   │
│  ┌─────────────────────────┐   │  copilot follow-up
│  │ 💬 Ask a follow-up...  │   │  bg-purple-600/10 rounded-xl
│  └─────────────────────────┘   │
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │
└─────────────────────────────────┘
```
### API with 15-Minute Cache
```typescript
// app/api/ai/deepdive/route.ts
const CACHE_TTL = 900 // 15 minutes

export async function POST(req: NextRequest) {
  const user = await getUserFromRequest(req)
  const budget = await checkAIBudget(user.privyDid, 2)
  if (!budget.allowed) return NextResponse.json({ error: 'LIMIT_REACHED' }, { status: 402 })
  
  const { ticker } = await req.json()
  
  // Check shared cache (same ticker within 15 min = free for any user)
  const cacheKey = `deepdive:${ticker}:${Math.floor(Date.now() / (CACHE_TTL * 1000))}`
  const cached = await redis.get(cacheKey)
  
  if (cached) {
    // Cache hit: don't charge messages for repeated same-ticker lookups
    return NextResponse.json(JSON.parse(cached))
  }
  
  const signal = await getTodaySignal()
  
  const res = await fetch('https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: { 
      'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'sonar', // live web search for today's news
      messages: [{
        role: 'system',
        content: `You are an educational market analysis copilot. TurboCore signal: ${signal.regime} (${signal.confidence}%).`
      }, {
        role: 'user',
        content: `Real-time educational analysis of ${ticker} as of today (${new Date().toLocaleDateString()}). Return JSON:
{
  "whyItMoved": "2-3 sentences: today's catalyst using live news",
  "technicalSnapshot": "support/resistance + trend in 1 sentence",
  "ivEnvironment": "IV Rank estimate + what it means for options cost",
  "turboAlignment": "yes|no + 1 sentence: does this align with ${signal.regime}?",
  "turboStrength": "strong|moderate|neutral|against",
  "strategyHint": "1 educational tip based on IV + regime combination",
  "riskScore": 1-10,
  "riskRationale": "1 sentence"
}`
      }],
      max_tokens: 500
    })
  })
  
  const data = await res.json()
  const analysis = JSON.parse(data.choices.message.content)
  
  // Cache for 15 min so all users looking up same ticker don't each use messages
  await redis.setex(cacheKey, CACHE_TTL, JSON.stringify(analysis))
  await consumeMessages(user.privyDid, 2, 'deep_dive', data.usage)
  
  return NextResponse.json(analysis)
}
```

***
## Part 8: Feature 5 — Weekly AI Performance Debrief
### Mobile Screen Design
```
┌─────────────────────────────────┐
│ ←  Weekly Debrief  Mar 10-16   │
│─────────────────────────────────│
│                                 │
│  ┌─────────────────────────┐   │  summary hero card
│  │  📊 Your Week           │   │  bg-[#12152A] rounded-xl
│  │─────────────────────────│   │  border border-emerald-500/30
│  │  Portfolio: +$420 +4.2% │   │  text-emerald-400 (green if +)
│  │  TurboCore:    +3.8%    │   │  text-zinc-400
│  │  ✅ You beat the signal  │   │  text-emerald-400 small
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │  bg-[#12152A] rounded-xl
│  │ 📈 What went right      │   │  text-emerald-400 label
│  │ Held TQQQ through dip → │   │  text-white text-sm
│  │ aligned with BULL signal │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ ⚠️ Pattern to watch     │   │  text-amber-400 label
│  │ Sold 2x at 30% profit   │   │
│  │ Both hit 60% after (-$180)  │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 💡 This Week's Tip      │   │  text-purple-400 label
│  │ In BULL + low VIX, hold │   │
│  │ to 50% target before    │   │
│  │ trimming                │   │
│  └─────────────────────────┘   │
│                                 │
│  [📄 Download PDF Report]       │  bg-[#0D1020] rounded-xl h-11
│  [💬 Ask AI About This Week]    │  bg-purple-600/20 rounded-xl h-11
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │
└─────────────────────────────────┘
```
### Cron-Driven Generation (Sunday 6 PM ET)
```typescript
// app/api/cron/weekly-debrief/route.ts
export async function GET(req: Request) {
  if (req.headers.get('authorization') !== `Bearer ${process.env.CRON_SECRET}`) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }
  
  const subscribers = await query(
    `SELECT u.privy_did, u.subscription_tier, u.push_subscription,
            us.ai_messages_used, us.ai_messages_limit
     FROM users u JOIN user_settings us ON u.privy_did = us.privy_did
     WHERE u.subscription_tier IN ('pro', 'bundle') 
     AND u.subscription_status = 'active'`, []
  )
  
  const weekStart = getWeekStart() // last Monday
  const signalHistory = await getWeekSignalSummary(weekStart)
  
  for (const user of subscribers.rows) {
    // Get this user's trade activity from EC2 (has Tastytrade connection)
    const weekData = await fetch(`${process.env.EC2_INTERNAL_API}/user/${user.privy_did}/weekly-trades`, {
      headers: { 'x-api-key': process.env.EC2_API_SECRET! }
    }).then(r => r.json())
    
    const res = await fetch('https://api.perplexity.ai/chat/completions', {
      method: 'POST',
      headers: { 
        'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'sonar',
        messages: [{
          role: 'user',
          content: `Generate a weekly trading debrief for a ${user.subscription_tier} TradeMind user.
This week's data:
- Portfolio P&L: ${weekData.totalPnl} (${weekData.totalPnlPct}%)
- TurboCore signal weekly return: ${signalHistory.weekReturn}%
- Positions entered: ${weekData.entriesCount}
- Signal alignment rate: ${weekData.alignmentPct}% of trades aligned with signal
- Notable behavioral patterns: ${weekData.patterns.join(', ')}

Return JSON:
{
  "headline": "string (1 line, < 70 chars)",
  "beatSignal": boolean,
  "userReturn": number,
  "signalReturn": number,  
  "wentRight": "string (1-2 sentences on best decision this week)",
  "watchOut": "string (1 behavioral pattern + $ impact if calculable)",
  "weeklyTip": "string (1 actionable educational tip for next week)"
}`
        }],
        max_tokens: 400
      })
    })
    
    const data = await res.json()
    const debrief = JSON.parse(data.choices.message.content)
    
    // Store in RDS
    await query(
      `INSERT INTO ai_debriefs (privy_did, week_start, content) VALUES ($1, $2, $3)
       ON CONFLICT (privy_did, week_start) DO UPDATE SET content = $3`,
      [user.privy_did, weekStart, debrief]
    )
    
    // Push notification
    if (user.push_subscription) {
      await sendPushNotification(user.push_subscription, {
        title: `📊 Your Weekly TradeMind Debrief`,
        body: `${debrief.beatSignal ? '🟢' : '🔴'} ${debrief.headline}`,
        data: { url: '/ai/debrief' }
      })
    }
  }
  
  return Response.json({ success: true, generated: subscribers.rows.length })
}
```

***
## Part 9: AI Copilot Hub — The Unified Entry Point
The AI tab in the bottom nav opens the AI Hub — a single screen presenting all 5 features in card format, with message budget prominently displayed.
### Mobile Screen Design
```
┌─────────────────────────────────┐
│  AI Copilot             ⚙️     │  bg-[#0A0B14]
│─────────────────────────────────│
│                                 │
│  ┌─────────────────────────┐   │  budget card
│  │  ⚡ 28 messages left    │   │  bg-[#12152A] rounded-xl
│  │  ████████░░░░  56%      │   │  progress bar purple-600
│  │  Resets Apr 1 · Get more│   │  text-zinc-400 text-xs
│  └─────────────────────────┘   │
│                                 │
│  ── AI Features ───────────────│
│  ┌────────────┐ ┌────────────┐  │  2-column grid
│  │ 📸         │ │ 🌅         │  │  bg-[#12152A] rounded-xl
│  │ Screenshot │ │ Morning    │  │  h-[90px] p-3
│  │ Analyzer   │ │ Brief      │  │  text-white text-sm font-medium
│  │ 3 msgs     │ │ 0 msgs     │  │  text-zinc-500 text-xs
│  └────────────┘ └────────────┘  │
│  ┌────────────┐ ┌────────────┐  │
│  │ ⚙️  [PRO] │ │ 🔍         │  │
│  │ Strategy  │ │ Deep       │  │
│  │ Builder   │ │ Dive       │  │
│  │ 2 msgs    │ │ 2 msgs     │  │
│  └────────────┘ └────────────┘  │
│  ┌──────────────────────────┐   │
│  │ 📊  [PRO] Weekly Debrief │   │  full-width card
│  │  Your performance coaching    │  bg-[#12152A] rounded-xl
│  │  every Sunday 6 PM            │  h-[70px]
│  └──────────────────────────┘   │
│                                 │
│  ── Free Chat ─────────────────│
│  ┌─────────────────────────┐   │
│  │ 💬 Ask TradeMind AI...  │   │  bg-[#0D1020] rounded-xl h-11
│  └─────────────────────────┘   │
│                                 │
│  [↑ Upgrade to Pro — 400 msgs] │  bg-purple-600 rounded-xl h-11
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │
└─────────────────────────────────┘
```

***
## Part 10: AI Copilot Free Chat (Persistent Context Window)
Beyond the 5 structured features, the AI tab includes a free-form **TradeMind AI Copilot Chat** that maintains session context with rolling conversation history. This is the conversational backbone — users can ask anything from "explain what delta means" to "should I be buying dips right now?" (answered in educational framing with signal context).
### Chat Architecture
```typescript
// app/api/ai/chat/route.ts — streaming chat with rolling context
export async function POST(req: NextRequest) {
  const user = await getUserFromRequest(req)
  const budget = await checkAIBudget(user.privyDid, 1)
  if (!budget.allowed) return NextResponse.json({ error: 'LIMIT_REACHED' }, { status: 402 })
  
  const { message, sessionId, history } = await req.json()
  const signal = await getTodaySignal()
  
  // Rolling context: keep last 8 messages only (4 exchanges) to control token cost
  const recentHistory = (history || []).slice(-8)
  
  const messages = [
    {
      role: 'system',
      content: `You are TradeMind AI — an educational investment copilot (not a financial advisor).
TurboCore signal today: ${signal.regime} (${signal.confidence}% confidence), ML Score: ${signal.mlScore}/100.
Allocation: ${JSON.stringify(signal.allocation)}.
User plan: ${user.tier}.
Rules: Be educational, not directive. Never "you should buy/sell X". 
Use "If your thesis is X, then..." framing. Be concise (under 200 words unless asked for more).
Always mention the TurboCore signal context when directly relevant.`
    },
    ...recentHistory,
    { role: 'user', content: message }
  ]
  
  // Stream the response
  const res = await fetch('https://api.perplexity.ai/chat/completions', {
    method: 'POST',
    headers: { 
      'Authorization': `Bearer ${process.env.PERPLEXITY_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'sonar',
      messages,
      max_tokens: 350,
      stream: true
    })
  })
  
  return streamPerplexityResponse(res, user.privyDid, 1, 'chat', sessionId)
}
```
### Mobile Chat Screen Design
```
┌─────────────────────────────────┐
│ ←  TradeMind AI        ⚡ 27   │
│─────────────────────────────────│
│                                 │  scrollable messages area
│  ┌─────────────────────────┐   │  bg-purple-600/20 (AI msg)
│  │ 🤖 TurboCore is BULL    │   │  bg-[#12152A] (user msg)
│  │    87% today. Low VIX   │   │  rounded-2xl px-3 py-2
│  │    makes debit spreads  │   │
│  │    cost-effective.      │   │
│  └─────────────────────────┘   │
│                        ┌──────┐ │  user message right-aligned
│                        │ What │ │
│                        │ about│ │
│                        │ TQQQ │ │
│                        │ ?    │ │
│                        └──────┘ │
│  ┌─────────────────────────┐   │
│  │ 🤖 TQQQ is the primary  │   │
│  │    model allocation     │   │
│  │    (80%) in BULL regime.│   │
│  │    ▌                    │   │  streaming cursor
│  └─────────────────────────┘   │
│                                 │
│─────────────────────────────────│  fixed bottom input
│  ┌──────────────────────┐ [▶]  │  bg-[#0D1020] rounded-2xl h-11
│  │ Ask TradeMind AI...  │      │
│  └──────────────────────┘      │
│─────────────────────────────────│
│  📊 📈 🤖 💼 👤              │
└─────────────────────────────────┘
```

***
## Part 11: Full Database Schema
```sql
-- ============================================
-- AI FEATURES TABLES (add to existing schema)
-- ============================================

-- Extend user_settings
ALTER TABLE user_settings
  ADD COLUMN IF NOT EXISTS ai_messages_used     INTEGER   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ai_messages_limit    INTEGER   DEFAULT 50,
  ADD COLUMN IF NOT EXISTS ai_bonus_messages    INTEGER   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ai_reset_date        DATE      DEFAULT date_trunc('month', NOW()),
  ADD COLUMN IF NOT EXISTS push_subscription    JSONB,
  ADD COLUMN IF NOT EXISTS briefing_enabled     BOOLEAN   DEFAULT true,
  ADD COLUMN IF NOT EXISTS debrief_enabled      BOOLEAN   DEFAULT true;

-- AI message limits by tier (enforced in checkAIBudget middleware)
-- TurboCore (core): 50/month
-- TurboCore Pro (pro): 400/month
-- Both Bundle (bundle): 1500/month

-- Compliance conversation log (FINRA 3-year retention)
CREATE TABLE IF NOT EXISTS ai_chat_logs (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  privy_did       VARCHAR(64) NOT NULL,
  session_id      UUID        NOT NULL,
  feature_type    VARCHAR(32) NOT NULL CHECK (feature_type IN 
                  ('screenshot','briefing','strategy','deepdive','debrief','chat')),
  role            VARCHAR(16) NOT NULL CHECK (role IN ('user','assistant','system')),
  content         TEXT        NOT NULL,
  model_used      VARCHAR(32),
  tokens_input    INTEGER,
  tokens_output   INTEGER,
  messages_cost   INTEGER     DEFAULT 1,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Shared morning briefings (one per day, shared across all users)
CREATE TABLE IF NOT EXISTS ai_briefings (
  id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  date        DATE    UNIQUE NOT NULL,
  regime      VARCHAR(16),
  confidence  INTEGER,
  ml_score    INTEGER,
  content     JSONB   NOT NULL,  -- {headline, pushBody, bullets[^5]}
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Per-user weekly debriefs
CREATE TABLE IF NOT EXISTS ai_debriefs (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  privy_did   VARCHAR(64) NOT NULL,
  week_start  DATE        NOT NULL,
  content     JSONB       NOT NULL,  -- {headline, wentRight, watchOut, weeklyTip, ...}
  pdf_url     VARCHAR(512),
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(privy_did, week_start)
);

-- Deep dive 15-min cache log (for audit/analytics, not primary cache)
CREATE TABLE IF NOT EXISTS ai_deepdive_cache (
  ticker      VARCHAR(16) NOT NULL,
  content     JSONB       NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (ticker)
);

-- AI message budget management
CREATE TABLE IF NOT EXISTS ai_message_transactions (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  privy_did     VARCHAR(64) NOT NULL,
  feature_type  VARCHAR(32) NOT NULL,
  messages_used INTEGER     NOT NULL,
  tokens_in     INTEGER,
  tokens_out    INTEGER,
  session_id    UUID,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Referral tracking with AI reward support
CREATE TABLE IF NOT EXISTS referrals (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  referrer_did        VARCHAR(64) NOT NULL,
  referee_did         VARCHAR(64) NOT NULL,
  referee_tier        VARCHAR(16),
  referee_billing     VARCHAR(16) CHECK (referee_billing IN ('monthly','annual')),
  stage               INTEGER     DEFAULT 0 CHECK (stage IN (0,1,2)),
  messages_awarded    INTEGER     DEFAULT 0,
  stripe_credits      NUMERIC(10,2) DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(referrer_did, referee_did)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_chat_logs_user_date    ON ai_chat_logs(privy_did, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_logs_session      ON ai_chat_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_debriefs_user_week     ON ai_debriefs(privy_did, week_start DESC);
CREATE INDEX IF NOT EXISTS idx_msg_transactions_user  ON ai_message_transactions(privy_did, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer     ON referrals(referrer_did);
CREATE INDEX IF NOT EXISTS idx_referrals_referee      ON referrals(referee_did);
```

***
## Part 12: AI Budget Middleware
```typescript
// lib/ai.ts — shared AI budget and consumption utilities
import { query } from '@/lib/db'

const TIER_LIMITS = {
  core: 50,
  pro: 400,
  bundle: 1500
}

export async function checkAIBudget(privyDid: string, cost: number) {
  const result = await query(
    `SELECT ai_messages_used, ai_messages_limit, ai_bonus_messages, ai_reset_date,
            subscription_tier
     FROM user_settings 
     JOIN users USING (privy_did)
     WHERE user_settings.privy_did = $1`,
    [privyDid]
  )
  
  const row = result.rows
  if (!row) throw new Error('User not found')
  
  // Reset monthly budget if new month
  const today = new Date()
  const resetDate = new Date(row.ai_reset_date)
  if (today.getMonth() !== resetDate.getMonth() || today.getFullYear() !== resetDate.getFullYear()) {
    await query(
      `UPDATE user_settings SET ai_messages_used = 0, ai_reset_date = date_trunc('month', NOW())
       WHERE privy_did = $1`,
      [privyDid]
    )
    row.ai_messages_used = 0
  }
  
  const baseLimit = TIER_LIMITS[row.subscription_tier as keyof typeof TIER_LIMITS] ?? 50
  const totalLimit = baseLimit + row.ai_bonus_messages
  const remaining = totalLimit - row.ai_messages_used
  
  return {
    allowed: remaining >= cost,
    used: row.ai_messages_used,
    limit: totalLimit,
    remaining,
    tier: row.subscription_tier
  }
}

export async function consumeMessages(
  privyDid: string, 
  cost: number, 
  featureType: string, 
  usage: any,
  content?: string,
  sessionId?: string
) {
  await Promise.all([
    // Deduct from budget
    query(
      `UPDATE user_settings SET ai_messages_used = ai_messages_used + $1 WHERE privy_did = $2`,
      [cost, privyDid]
    ),
    // Log for compliance + analytics
    query(
      `INSERT INTO ai_message_transactions (privy_did, feature_type, messages_used, tokens_in, tokens_out, session_id)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [privyDid, featureType, cost, usage?.prompt_tokens, usage?.completion_tokens, sessionId]
    )
  ])
}
```

***
## Part 13: Infrastructure & Deployment
### Vercel Configuration
```json
// vercel.json
{
  "crons": [
    { "path": "/api/cron/morning-brief",  "schedule": "15 12 * * 1-5" },
    { "path": "/api/cron/weekly-debrief", "schedule": "0 22 * * 0"   }
  ],
  "headers": [
    {
      "source": "/api/ai/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "no-store" }
      ]
    }
  ]
}
```
### Vercel Environment Setup Per Environment
| Variable | Local | Preview | Production |
|---|---|---|---|
| `PERPLEXITY_API_KEY` | Test key | Test key | Live key |
| `STRIPE_SECRET_KEY` | `sk_test_...` | `sk_test_...` | `sk_live_...` |
| `EC2_INTERNAL_API` | `http://localhost:3001` | `https://api-staging.trademind.bot` | `https://api.trademind.bot` |
| `PGHOST` | Local/RDS | RDS staging | RDS production |
| `NEXT_PUBLIC_PRIVY_APP_ID` | Test App ID | Test App ID | Live App ID |
### EC2 Setup Checklist
```bash
# EC2 (t3.medium minimum for ML signal processing)
# Ubuntu 22.04 LTS

# 1. Install Node.js 20 + PM2
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install -g pm2

# 2. Configure security group
# Inbound: port 3001 from Vercel IP ranges ONLY (or use VPC peering)
# Inbound: port 22 from your IP only

# 3. PM2 ecosystem
# ecosystem.config.js
module.exports = {
  apps: [{
    name: 'trademind-api',
    script: 'dist/server.js',
    instances: 2,
    exec_mode: 'cluster',
    env: {
      NODE_ENV: 'production',
      PORT: 3001
    }
  }]
}

# 4. Run
pm2 start ecosystem.config.js
pm2 startup  # persist on reboot
```
### Redis Setup (Upstash recommended for Vercel)
```typescript
// lib/redis.ts
import { Redis } from '@upstash/redis'

export const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
})
// Use for: signal cache (15min TTL), deep dive cache (15min), session data
```

***
## Part 14: Build Roadmap
### Phase 1 — Foundation + AI Hub (Weeks 1–3)
**Goal:** Ship AI tab with Screenshot Analyzer and Deep Dive on all tiers

- [ ] Add AI tab to existing bottom nav (5th tab, `🤖` icon)
- [ ] Build AI Hub screen with feature cards (locked/unlocked states)
- [ ] Implement `checkAIBudget` and `consumeMessages` middleware
- [ ] Add `ai_messages_used/limit` columns to `user_settings` in RDS
- [ ] Deploy Screenshot Analyzer (`/api/ai/screenshot`) with streaming
- [ ] Deploy Stock Deep Dive (`/api/ai/deepdive`) with 15-min shared cache
- [ ] Free Chat (`/api/ai/chat`) with rolling 8-message context
- [ ] Message budget badge component (shows remaining in top-right of each feature)
- [ ] Soft paywall upgrade modal (fires when limit reached)
- [ ] Compliance disclaimer component (renders above every AI screen)
- [ ] `ai_chat_logs` table + logging middleware
### Phase 2 — Engagement Loop (Weeks 4–6)
**Goal:** Ship push notifications and Pre-Market Briefing

- [ ] PWA manifest + service worker (`public/sw.js`)
- [ ] VAPID key generation; store `push_subscription` in `user_settings`
- [ ] Push opt-in modal (fires after user uses AI feature twice)
- [ ] Pre-Market Briefing screen (`/ai/briefing`) + history list
- [ ] Vercel Cron: morning-brief (8:15 AM ET weekdays)
- [ ] Batch push send utility (chunked, expired subscription cleanup)
- [ ] Notification preferences screen (briefing on/off, debrief on/off)
- [ ] Weekly Debrief screen (`/ai/debrief`) + PDF export (`@react-pdf/renderer`)
- [ ] Vercel Cron: weekly-debrief (Sunday 6 PM ET)
- [ ] EC2 `/user/:did/weekly-trades` endpoint for trade data
### Phase 3 — Monetization Features (Weeks 7–10)
**Goal:** Ship Options Strategy Builder + upgrade mechanics

- [ ] Options Strategy Builder screen (`/ai/strategy`) — Pro/Bundle only
- [ ] Pro-tier blurred preview card with upgrade overlay
- [ ] Upgrade modal A/B test: "Upgrade for $20 more/month" vs. "Buy 100 msgs for $4.99"
- [ ] Add-on pack one-time Stripe payment flow
- [ ] Credits auto-applied to `ai_bonus_messages` in `user_settings`
- [ ] Referral dashboard in `/me` screen
- [ ] Referral 2-stage reward triggers (Stripe webhook → `referrals` table → message credit)
- [ ] Admin monitoring dashboard: daily API cost tracker (Perplexity usage vs. revenue)

***
## Part 15: Compliance
All AI features must satisfy FINRA's 2026 GenAI supervision guidelines, which apply to AI tools used in financial contexts even for non-registered platforms.[^22][^23]

| Requirement | Implementation |
|---|---|
| Disclaimer on every screen | "Educational analysis only. Not personalized investment advice." — rendered as sticky footer component |
| No directive language | System prompt enforces "If your thesis is X..." framing — never "you should buy/sell" |
| Conversation archiving | All AI turns logged to `ai_chat_logs` with 3-year retention |
| User control | Per-category notification opt-out (briefing, debrief) in `/settings/notifications`[^3] |
| Push categorization | Use `tag: 'trademind-briefing'` (transactional, not promotional) to minimize opt-out rate[^4] |
| Privacy policy | Updated to disclose AI conversation logging; 30-day raw retention unless opted in |
| Marketing language | "AI trading education" / "AI investment copilot" — never "AI trading advice" or "guaranteed returns" |

---

## References

1. [Chart AI - AI Trading Analysis - Apps on Google Play](https://play.google.com/store/apps/details?id=com.chart.ai.analysis.trading.bot&hl=en_US) - Games

Apps

Movies & TV

Books

Kids

Chart AI - AI Trading Analysis

Identifier Studio

Contains a...

2. [Chart AI - Trading Analysis - Apps on Google Play](https://play.google.com/store/apps/details?id=com.itechgemini.ai_chart&hl=en_US) - Chart AI - Trading Analysis - Apps on Google Play

# Chart AI - Trading Analysis

iTechGemini

In-ap...

3. [App Push Notification Best Practices for 2026 (and the mistakes that ...](https://appbot.co/blog/app-push-notifications-2026-best-practices/) - Push notification best practices for 2026, backed by research and real app reviews and the mistakes ...

4. [Push Notification Best Practices: Ultimate Guide for 2026 - Reteno](https://reteno.com/blog/push-notification-best-practices-ultimate-guide-for-2026) - Discover 14 push notification best practices to help your promotional messages resonate with your ta...

5. [AI Options Bots: Tickeron Targets 481% Trading Returns](https://tickeron.com/trading-investing-101/tickeron-unveils-new-ai-trading-bots-designed-for-options-traders-targeting-returns-up-to-481/) - Tickeron Unveils New AI Trading Bots Designed for Options Traders, Targeting Returns Up to 481%. SAN...

6. [About the Options Strategy Builder | Robinhood](https://robinhood.com/support/articles/about-the-options-strategy-builder/) - The Options Strategy Builder helps you learn about, customize, and build a wide range of basic and a...

7. [Options Strategy Builder: Build Complex Trades in Minutes | Public](https://www.youtube.com/watch?v=H2_OebJVSe4) - On Public, you can structure sophisticated single-leg and multi-leg options strategies in minutes. T...

8. [Technical, Fundamental & Alternative Charting | TrendSpider](https://trendspider.com/product/analyze-and-chart-any-market-asset/) - Elevate your technical analysis with TrendSpider's Advanced Smart Charts. Analyze assets quickly wit...

9. [Top 10 AI Trading Apps to Boost Your Investment Strategy in 2026](https://hyscaler.com/insights/top-ai-trading-apps-boost-investment/) - Discover the top 10 AI trading apps that can enhance your investment strategy. Leverage advanced too...

10. [AI-powered apps struggle with long-term retention, new report shows](https://techcrunch.com/2026/03/10/ai-powered-apps-struggle-with-long-term-retention-new-report-shows/) - AI can drive stronger early monetization for apps, but sustaining value remains the challenge, Reven...

11. [Mastering the Art of Trade Review](https://tradersmastermind.com/mastering-the-art-of-trade-review/) - In this post, we'll cover building a 'Two-Part' Trade Review Process that includes a daily debrief a...

12. [Trade AI: Chart AI Analysis - App Store - Apple](https://apps.apple.com/ae/app/trade-ai-chart-ai-analysis/id6741457696) - ## iPhone Screenshots
## Description

Instantly analyze charts, get Today's Top Stock Picks, receive...

13. [January 2026 - What's New at TrendSpider](https://trendspider.com/blog/january-2026-changelog/) - In January 2026, TrendSpider introduced AI alert automation, two-factor authentication, AI-powered e...

14. [Tickeron - Stock Market News & - Apps on Google Play](https://play.google.com/store/apps/details?id=com.tickeron.mobile&hl=en) - Games

Apps

Movies & TV

Books

Kids

Tickeron - Stock Market News &

Tickeron, Inc.

4.1

star

27...

15. [Sonar API - Perplexity](https://docs.perplexity.ai/docs/sonar/quickstart) - Overview. Perplexity's Sonar API provides web-grounded AI responses with support for streaming, tool...

16. [Best AI Trading Platforms in 2025 - Tickeron](https://tickeron.com/trading-investing-101/top-ai-trading-platforms-transforming-modern-markets/) - Intuitive visual strategy builder; Commission-free trades and retirement-account support; Extensive ...

17. [February 2026 - What's New at TrendSpider](https://trendspider.com/blog/february-2026-changelog/) - In February 2026, TrendSpider introduced improvements across bot reliability, custom scripting flexi...

18. [AWS Amplify vs Vercel 2026: Complete Developer Guide for Next.js ...](https://www.agilesoftlabs.com/blog/2026/01/aws-amplify-vs-vercel-2026-complete) - In 2026, two platforms dominate the conversation: AWS Amplify and Vercel. Both promise seamless depl...

19. [Next.js Deployment on AWS Lambda, ECS, Amplify, and Vercel](https://dev.to/aws-builders/nextjs-deployment-on-aws-lambda-ecs-amplify-and-vercel-what-i-learned-nmc) - I investigated deploying a sample Next.js app on AWS Lambda, AWS ECS, AWS Amplify, and Vercel. In th...

20. [Connect Next.js to Amazon Aurora PostgreSQL using Vercel ...](https://vercel.com/kb/guide/connect-next-js-to-amazon-aurora-postgresql-using-vercel-marketplace) - Learn how to connect your Next.js application to Amazon Aurora PostgreSQL securely using the Vercel ...

21. [AWS RDS for NextJS on Vercel - Reddit](https://www.reddit.com/r/nextjs/comments/1oyf6we/aws_rds_for_nextjs_on_vercel/) - If you stay on Vercel, put RDS Proxy in front of Postgres or use Prisma Accelerate/Data Proxy; point...

22. [Regulating AI Deception in Financial Markets: How the SEC Can ...](https://nysba.org/regulating-ai-deception-in-financial-markets-how-the-sec-can-combat-ai-washing-through-aggressive-enforcement/) - Under Section 206 of the Investment Advisers Act, the SEC must rigorously enforce fiduciary standard...

23. [FINRA Releases 2026 Oversight Report Highlighting AI ...](https://www.acaglobal.com/industry-insights/finra-releases-2026-oversight-report-highlighting-ai-cybersecurity-and-compliance-risks/) - FINRA's 2026 Oversight Report highlights key compliance risks, including Generative AI, cybersecurit...

