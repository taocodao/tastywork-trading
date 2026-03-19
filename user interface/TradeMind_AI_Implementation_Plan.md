# TradeMind@bot — AI Feature & Platform Implementation Plan
### Comprehensive Build Guide: Mobile-First Design, Feature Specs & Pricing

---

## Executive Summary

This implementation plan consolidates all strategic decisions made across TradeMind@bot's product development sessions into a single actionable build document. The platform combines three unique capabilities no competitor currently offers simultaneously: **proprietary AI trading signals** (TurboCore / TurboCore Pro), **broker API execution** (Tastytrade), and a **signal-contextualized AI assistant** powered by the Perplexity Sonar API. The mobile-first design is engineered for Gen Z and millennial retail traders who primarily trade from their phones.

---

## Part 1: Recommended Pricing Plan

### Final Pricing Architecture

| Plan | Monthly | Annual | Effective/Mo | Savings | AI Messages | Best For |
|---|---|---|---|---|---|---|
| **TurboCore** | $29/mo | $249/yr | $20.75 | Save 28% (3.5mo free) | 30/month | New traders, no options needed |
| **TurboCore Pro** | $49/mo | $399/yr | $33.25 | Save 32% (4mo free) | 300/month | Options traders, LEAPS strategies |
| **Both Bundle** | $69/mo | $549/yr | $45.75 | Save 33% (4mo free) | Unlimited (1,500 soft cap) | Power traders, full system |
| **AI Add-On Pack** | $4.99 | — | — | — | +100 messages | Any plan, one-time |
| **AI Power Pack** | $9.99 | — | — | — | +300 messages | Any plan, one-time |

### Why This Pricing Works

- **TurboCore at $29/mo:** Low enough to convert trial users easily; the 30 AI message limit creates upgrade pressure within 3 weeks
- **The $20 gap between Core → Pro:** Justified by 10× more AI messages (30→300), options strategy tools, and +11.5% CAGR (27.8%→39.3%)
- **Bundle at $69/mo:** The $25 add-on pack deliberately makes the Bundle look cheap — 1,500 messages vs. paying $25 for 300 extra messages on a Pro plan
- **Annual discount math:** Core saves $99/yr; Pro saves $189/yr; Bundle saves $279/yr — these are meaningful dollar amounts that show clearly on the pricing card

### Referral Credit Structure (Stripe Customer Balance)

| Milestone | Reward Type | Value |
|---|---|---|
| Friend signs up (any plan) | AI message credits | +50 messages |
| Friend's 1st payment clears | AI message credits | +100 messages |
| Friend stays 2nd month | Stripe subscription credit | $50 off next bill |
| Friend subscribes annual | Stripe subscription credit | $150 off + 500 AI messages |

---

## Part 2: Mobile-First Website & App Design

### Design Principles

1. **Mobile-first, always** — design for 390px width (iPhone 15), scale up to desktop
2. **Dark theme primary** — traders work in dark environments; matches financial platform conventions
3. **Bottom navigation bar** — thumb-friendly; no hamburger menus in the core app
4. **Card-based UI** — each feature is a standalone card that swipes, taps, or expands
5. **One action per screen** — no cluttered dashboards; progressive disclosure
6. **Purple + white brand palette** — consistent with current trademind.bot identity

---

### Screen 1: Home / Today's Signal (Default Landing Screen)

```
┌─────────────────────────────────┐
│ TradeMind@bot          🔔  👤  │
│─────────────────────────────────│
│  Monday, Mar 16 · Pre-Market    │
│                                 │
│  ┌───────────────────────────┐  │
│  │  🟢  TODAY'S SIGNAL       │  │
│  │  BULL REGIME              │  │
│  │  Confidence: 87%          │  │
│  │                           │  │
│  │  TQQQ  80%  ████████░░    │  │
│  │  SGOV  20%  ██░░░░░░░░    │  │
│  │                           │  │
│  │  [Ask AI About This Signal]│  │
│  └───────────────────────────┘  │
│                                 │
│  ┌─────────┐  ┌─────────────┐  │
│  │VIX: 18.2│  │ QQQ: +0.4% │  │
│  └─────────┘  └─────────────┘  │
│                                 │
│  📋 Pre-Market Briefing →       │
│  ─────────────────────────────  │
│  • Fed: No meeting this week    │
│  • NVDA earnings Thu after mkt  │
│  • IV Rank QQQ: 34 (neutral)    │
│                                 │
│─────────────────────────────────│
│  🏠    📊    🤖    💼    👤    │
│ Home Signal  AI  Portfolio Me   │
└─────────────────────────────────┘
```

**Key design decisions:**
- Signal card is the entire above-the-fold experience — the #1 reason users open the app
- Confidence score shown as percentage + color (green/yellow/red)
- Allocation shown as visual bars, not just numbers
- "Ask AI About This Signal" button — one tap to open AI chat with today's signal pre-loaded
- Pre-market briefing is collapsed (expandable) to keep screen clean
- Bottom nav: 5 tabs, icons + labels, active tab highlighted purple

---

### Screen 2: AI Assistant Hub (Main AI Screen)

```
┌─────────────────────────────────┐
│ ← TradeMind AI          ⚡300  │
│─────────────────────────────────│
│  Quick Actions:                 │
│                                 │
│  ┌──────────┐  ┌──────────┐    │
│  │ 📸        │  │ 🔍        │   │
│  │ Analyze   │  │ Deep     │   │
│  │ Position  │  │ Dive     │   │
│  └──────────┘  └──────────┘    │
│                                 │
│  ┌──────────┐  ┌──────────┐    │
│  │ 🧮        │  │ 📅        │   │
│  │ Strategy  │  │ Earnings │   │
│  │ Builder   │  │ Analyzer │   │
│  └──────────┘  └──────────┘    │
│                                 │
│  ┌──────────┐  ┌──────────┐    │
│  │ 🩺        │  │ 🔥        │   │
│  │ Position  │  │ Roast My │   │
│  │ Health    │  │ Trade    │   │
│  └──────────┘  └──────────┘    │
│                                 │
│  ─── Or just ask anything ───  │
│                                 │
│  ┌─────────────────────────┐   │
│  │ Ask TradeMind AI...   📎│   │
│  └─────────────────────────┘   │
│                                 │
│  ⓘ Educational use only        │
│─────────────────────────────────│
│  🏠    📊    🤖    💼    👤    │
└─────────────────────────────────┘
```

**Key design decisions:**
- "⚡300" in top-right = remaining AI messages this month (tappable → shows usage/upgrade)
- 6 feature cards in 2×3 grid — each is a distinct specialized tool, not just a chat
- "📎" paperclip icon in text input = screenshot upload
- Disclaimer shown as small muted text — present but not intrusive
- Tapping any quick action card pre-loads a context prompt and opens the chat modal

---

### Screen 3: Position Screenshot Analyzer (Modal)

```
┌─────────────────────────────────┐
│ ← Position Analyzer    🤖 AI   │
│─────────────────────────────────│
│                                 │
│  ┌─────────────────────────┐   │
│  │                         │   │
│  │   📸 Upload Screenshot  │   │
│  │   of your position      │   │
│  │                         │   │
│  │   [Tap to upload]       │   │
│  │   or drag & drop        │   │
│  │                         │   │
│  └─────────────────────────┘   │
│                                 │
│  Or describe manually:          │
│  ┌─────────────────────────┐   │
│  │ e.g. "5 QQQ calls exp   │   │
│  │ Apr 18, strike $445,    │   │
│  │ down $340..."           │   │
│  └─────────────────────────┘   │
│                                 │
│  Context (auto-filled):         │
│  ┌─────────────────────────┐   │
│  │ 🟢 BULL signal · 87%    │   │
│  │ TQQQ 80% / SGOV 20%     │   │
│  └─────────────────────────┘   │
│                                 │
│  [  Analyze My Position  ]      │
│                                 │
│  ⓘ Uses 3 AI messages          │
│─────────────────────────────────│
│  🏠    📊    🤖    💼    👤    │
└─────────────────────────────────┘
```

---

### Screen 4: Stock Deep Dive Tool

```
┌─────────────────────────────────┐
│ ← Deep Dive             🔍     │
│─────────────────────────────────│
│  ┌─────────────────────────┐   │
│  │  Enter ticker symbol    │   │
│  │  [ QQQ            ] 🔎  │   │
│  └─────────────────────────┘   │
│                                 │
│  Recent: QQQ  NVDA  AAPL  TSLA │
│                                 │
│  ─── QQQ Analysis ─────────── │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 📰 Why it moved today   │   │
│  │ Fed commentary + tech   │   │
│  │ sell-off on rate fears  │   │
│  │                    [+]  │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 🌡️ IV Rank: 34          │   │
│  │ Options fairly priced   │   │
│  │ → Calls reasonable buy  │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 🧠 TurboCore Alignment  │   │
│  │ ✅ BULL signal supports │   │
│  │ bullish QQQ position    │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 🎯 Risk Score: 4/10     │   │
│  │ Low-moderate risk in    │   │
│  │ current regime          │   │
│  └─────────────────────────┘   │
│                                 │
│  [  Ask follow-up question  ]  │
│─────────────────────────────────│
│  🏠    📊    🤖    💼    👤    │
└─────────────────────────────────┘
```

---

### Screen 5: Portfolio Dashboard (Virtual + Live)

```
┌─────────────────────────────────┐
│ Portfolio               [+Add] │
│─────────────────────────────────│
│  Virtual      Live (Tastytrade) │
│  ──────       ─────────────────│
│                                 │
│  Starting: $10,000              │
│  Current:  $11,847  +18.5%     │
│  vs S&P:            +8.2% ✅   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ TQQQ  8 shares  $3,847  │   │
│  │       +$420  +12.2% ▲  │   │
│  │                    [AI] │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ SGOV  $1,200   $1,204   │   │
│  │       +$4    +0.3%  →  │   │
│  │                    [AI] │   │
│  └─────────────────────────┘   │
│                                 │
│  ┌─────────────────────────┐   │
│  │ 🩺 Health Check         │   │
│  │ 1 position needs review │   │
│  │            [View →]     │   │
│  └─────────────────────────┘   │
│                                 │
│  Weekly Report  [Download PDF] │
│─────────────────────────────────│
│  🏠    📊    🤖    💼    👤    │
└─────────────────────────────────┘
```

---

### Screen 6: Upgrade / Paywall Card (appears at message limit)

```
┌─────────────────────────────────┐
│                                 │
│         ⚡ Out of Messages      │
│                                 │
│   You've used your 30 monthly   │
│   AI messages on TurboCore.     │
│                                 │
│   ┌─────────────────────────┐  │
│   │  TurboCore Pro          │  │
│   │  $49/month              │  │
│   │                         │  │
│   │  ✅ 300 AI messages/mo  │  │
│   │  ✅ Options Strategy    │  │
│   │     Builder             │  │
│   │  ✅ Earnings Analyzer   │  │
│   │  ✅ 39.3% CAGR signals  │  │
│   │                         │  │
│   │  [  Upgrade to Pro  ]   │  │
│   └─────────────────────────┘  │
│                                 │
│   Or buy a one-time pack:       │
│   [+100 messages — $4.99]       │
│                                 │
│   Resets in 12 days             │
│                          [✕]   │
└─────────────────────────────────┘
```

---

## Part 3: Feature Implementation Specifications

### Feature 1: Signal-Contextualized AI Chat (Core Engine)

**What it does:** Every AI session automatically receives today's TurboCore regime signal, confidence score, and allocation as system context. The AI answers every question with this live data injected — making responses proprietary to TradeMind@bot.

**Technical spec:**
```typescript
// Dynamic system prompt — rebuilt fresh each session
const buildSystemPrompt = async (userId: string) => {
  const signal = await getTodaySignal(); // your existing signal DB
  const user = await getUserTier(userId);

  return `You are TradeMind AI for ${user.plan} subscribers.
Today's TurboCore signal: ${signal.regime} (${signal.confidence}% confidence).
Current allocation model: ${signal.allocation}.
You provide educational trading analysis only — not personalized advice.
Keep responses under 400 words. Be specific and direct.`;
};
```

**Message routing by plan:**
- TurboCore: Sonar model only, 30 msg/month cap
- TurboCore Pro: Sonar default + Sonar Reasoning on "Deep Analysis" toggle, 300 msg/month
- Both Bundle: All models, 1,500 msg/month soft cap

---

### Feature 2: Position Screenshot Analyzer

**What it does:** User uploads a brokerage screenshot → AI reads position details (ticker, strike, expiry, P&L, Greeks if visible) and provides educational analysis aligned with today's signal.

**Implementation:**
- Use Perplexity Sonar's vision capability (multimodal input)
- Count as 3 messages toward monthly budget (higher token cost)
- Show "Using 3 messages" warning before submit
- Extract key data points and confirm with user before full analysis

**System prompt injection:**
```
User has uploaded a screenshot of their brokerage position.
Today's signal context: [BULL/87%/TQQQ 80%].
Analyze the visible position data and provide:
1. Assessment of alignment with today's signal
2. Key risk factors (Greeks, time decay, distance from strike)
3. Two educational action scenarios (hold/adjust/close)
Do NOT say "you should" — frame as "if your thesis is X, then..."
```

---

### Feature 3: Stock / ETF Deep Dive

**What it does:** User enters a ticker → returns a structured 6-panel analysis card: news context, technicals, IV environment, TurboCore alignment, strategy suggestion, risk score.

**Perplexity advantage:** Sonar has live web search built in — the "Why it moved today" panel uses real-time news data, not stale training data. This is a key differentiator.

**UI behavior:**
- Results render as collapsible cards (tap to expand each panel)
- "Ask follow-up" button at bottom opens inline chat with ticker context loaded
- Recent tickers saved locally (last 5)
- Each deep dive = 2 messages toward monthly budget

---

### Feature 4: Options Strategy Builder (Pro + Bundle only)

**What it does:** User inputs ticker + directional view + max risk → AI outputs top 3 strategy matches with Greeks, max profit/loss, and breakeven.

**Input form (mobile-optimized):**
```
Ticker: [QQQ]
Your view: [Bullish ▼] [Neutral] [Bearish]
Time horizon: [< 2 weeks ▼] [1 month] [3 months]
Max risk ($): [$500]
Account level: [Level 2 Options ▼]
[Build My Strategy]
```

**Output card example:**
```
#1 Bull Call Spread (Best fit)
  Buy  $448 call exp Apr 18 — cost $280
  Sell $455 call exp Apr 18 — credit $120
  Net cost: $160 | Max gain: $540 | Breakeven: $449.60
  Prob profit: ~52% | IV environment: Fair

#2 Buy $445 Call
  Cost: $380 | Max gain: Unlimited | B/E: $448.80
  Higher risk, higher reward

#3 Sell $440 Cash-Secured Put
  Collect $180 premium | Keep if QQQ > $440
  Best if slightly bullish or neutral
```

---

### Feature 5: Pre-Market AI Briefing (Daily Push Notification)

**What it does:** Every morning at 8:15 AM ET, auto-generate a personalized 5-bullet briefing pushed as a notification + available as the top card on the Home screen.

**Data sources:** Perplexity Sonar live web search for news, earnings calendar, Fed schedule; TurboCore signal engine for regime + confidence; VIX API for volatility reading.

**Briefing format:**
```
🌅 TradeMind Morning Brief — Mon Mar 16

🟢 Signal: BULL · 87% confidence · TQQQ 80%
📅 Today: No major economic data releases
📊 Pre-market: QQQ +0.3% · VIX 18.2 (low)
⚡ This week: NVDA earnings Thu (high IV)
💡 Tip: In BULL + low VIX → favor buying calls
   over selling puts (IV cheap, room to run)
```

**Cost:** 1 message per user per morning (auto-generated, not user-initiated).
**Implementation:** Next.js Cron Job at 8:15 AM ET → batch generate for all active users → push via web push notifications (PWA).

---

### Feature 6: Position Health Check (Pro + Bundle)

**What it does:** Weekly automated scan of connected Tastytrade positions; flags positions needing attention with AI explanation.

**Alert triggers:**
- Position expiring within 7 days → "⏰ Expiry alert"
- Position up 50%+ → "💰 Consider taking profits"
- Position down 35%+ → "⚠️ Review stop-loss"
- Delta drifted >20 points from entry → "📐 Greeks shifted"
- Upcoming earnings in underlying → "📅 Earnings risk"

**Push notification:** "🩺 Your portfolio health check found 2 positions that need attention."
**Cost:** 2 messages per user per weekly scan.

---

### Feature 7: Earnings Play Analyzer (Pro + Bundle)

**What it does:** Before major earnings (auto-populated from calendar), generates a pre-earnings analysis card.

**Report sections:**
1. Historical implied move vs. actual (last 8 quarters) — bar chart
2. Current IV Rank — is the market over/under-pricing the move?
3. Recommended strategy based on IV: high IV → iron condor; low IV → straddle; neutral → skip
4. TurboCore alignment: does current regime support playing earnings?

---

### Feature 8: "Explain This to Me" — Concept Tooltips

**What it does:** Every technical term on the platform (Theta, Delta, IV Rank, CAGR, etc.) has a "?" icon. Tapping it opens a 3-second AI explanation with a relatable analogy.

**Implementation:** Pre-cached responses for the top 50 trading terms (no API call needed) — only use live API for unknown terms. This dramatically reduces token cost while maintaining the experience.

**Example (pre-cached):**
```
Theta Decay
Like ice melting in a glass. Your option loses ~$12 of value 
every day just from time passing — even if the stock doesn't 
move. With 14 days left, that's $168 that will evaporate by 
expiration regardless of what QQQ does.
```

---

### Feature 9: "Roast My Trade" (All Plans — 3/month Core, Unlimited Pro+)

**What it does:** User describes a trade → AI delivers a blunt, educational, slightly sassy critique with a "what to do differently next time" lesson.

**System prompt:**
```
The user is describing a trade they made. Give an honest, 
direct, educational critique. Be specific about what went wrong 
(if anything) and why. Keep a slightly playful tone but focus 
on the actionable lesson. End with "Next time, try:" and one 
concrete alternative approach.
```

**This feature is the viral social sharing mechanism** — users will screenshot the roast and post to TikTok/Twitter.

---

### Feature 10: Weekly Performance Debrief (Pro + Bundle)

**What it does:** Every Sunday, auto-generate a personalized weekly trading report comparing user's virtual/real portfolio performance to TurboCore benchmark.

**Report sections:**
- P&L this week (virtual + live if connected)
- vs. TurboCore signal performance this week
- Win/loss ratio on any manual trades
- AI coaching insight ("You held 3 positions past their 50% profit target — costing you $X")
- Signal accuracy this week (did the regime call correctly?)

**Delivery:** Push notification + in-app card + optional PDF export.

---

## Part 4: Technical Architecture — AI Module

### Database Schema Additions

```sql
-- Add to user_settings table
ALTER TABLE user_settings ADD COLUMN ai_messages_used INTEGER DEFAULT 0;
ALTER TABLE user_settings ADD COLUMN ai_messages_limit INTEGER DEFAULT 30;
ALTER TABLE user_settings ADD COLUMN ai_reset_date TIMESTAMP;
ALTER TABLE user_settings ADD COLUMN ai_bonus_messages INTEGER DEFAULT 0;

-- New table: AI chat logs (compliance + debugging)
CREATE TABLE ai_chat_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  privy_did VARCHAR(255) NOT NULL,
  session_id UUID NOT NULL,
  role VARCHAR(10) NOT NULL, -- 'user' or 'assistant'
  content TEXT NOT NULL,
  feature_type VARCHAR(50), -- 'screenshot', 'deep_dive', 'strategy_builder', etc.
  model_used VARCHAR(50),
  tokens_input INTEGER,
  tokens_output INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Index for compliance queries
CREATE INDEX idx_chat_logs_user ON ai_chat_logs(privy_did, created_at);
```

### API Route Structure

```
/api/ai/
  chat          → General chat + screenshot upload
  deep-dive     → Stock ticker analysis
  strategy      → Options strategy builder
  health-check  → Position scanner (Tastytrade)
  earnings      → Earnings analyzer
  briefing      → Pre-market briefing (cron)
  debrief       → Weekly performance report (cron)
```

### Cost Control Middleware

```typescript
// middleware: checkAIBudget.ts
export const checkAIBudget = async (req, res, next) => {
  const { privyDid } = req.user;
  const multiplier = req.body.hasImage ? 3 : 1; // screenshots = 3x

  const user = await db.query(
    `SELECT ai_messages_used, ai_messages_limit, ai_bonus_messages 
     FROM user_settings WHERE privy_did = $1`, [privyDid]
  );

  const totalAvailable = user.ai_messages_limit + user.ai_bonus_messages;

  if (user.ai_messages_used + multiplier > totalAvailable) {
    return res.status(402).json({ 
      error: 'LIMIT_REACHED',
      used: user.ai_messages_used,
      limit: totalAvailable,
      upgradeUrl: '/pricing'
    });
  }

  req.messageMultiplier = multiplier;
  next();
};
```

---

## Part 5: Build Phases & Timeline

### Phase 1 — MVP (Weeks 1–3)
- [ ] `/api/ai/chat` endpoint with Perplexity Sonar integration
- [ ] Signal-contextualized system prompt (dynamic, per-session)
- [ ] Per-user message counter in PostgreSQL
- [ ] 30/300/1500 tier gates with upgrade prompt
- [ ] Screenshot upload (Sonar vision)
- [ ] AI Assistant Hub screen (mobile UI)
- [ ] Compliance disclaimer in chat UI
- [ ] `ai_chat_logs` table + logging middleware

### Phase 2 — Specialized Tools (Weeks 4–7)
- [ ] Stock Deep Dive tool (live Perplexity web search)
- [ ] Options Strategy Builder (Pro + Bundle only)
- [ ] Pre-Market Briefing cron job + push notifications (PWA)
- [ ] "Roast My Trade" feature
- [ ] "Explain This to Me" tooltip system (pre-cached top 50 terms)
- [ ] AI message counter badge in top nav ("⚡ 248 left")
- [ ] Add-on pack purchase flow (Stripe)

### Phase 3 — Premium Intelligence (Weeks 8–12)
- [ ] Position Health Check (Tastytrade API integration)
- [ ] Earnings Play Analyzer (auto-populated calendar)
- [ ] Weekly Performance Debrief (Sunday cron)
- [ ] Referral → AI message credit system
- [ ] Admin spend monitoring dashboard
- [ ] Sonar Reasoning "Deep Analysis" mode (Pro+)
- [ ] Conversation history export to PDF

---

## Part 6: AI Message Allocation by Plan (Complete Matrix)

| Feature | TurboCore | TurboCore Pro | Both Bundle |
|---|---|---|---|
| General AI Chat | ✅ 1 msg | ✅ 1 msg | ✅ 1 msg |
| Position Screenshot | ✅ 3 msgs | ✅ 3 msgs | ✅ 3 msgs |
| Stock Deep Dive | ✅ 2 msgs | ✅ 2 msgs | ✅ 2 msgs |
| Options Strategy Builder | ❌ Locked | ✅ 2 msgs | ✅ 2 msgs |
| Pre-Market Briefing | ✅ (auto, 1 msg/day) | ✅ Full briefing | ✅ Full + push |
| Position Health Check | ❌ Locked | ✅ Weekly (2 msgs) | ✅ Daily |
| Earnings Analyzer | ❌ Locked | ✅ 2 msgs | ✅ 2 msgs |
| Roast My Trade | ✅ 3/month | ✅ Unlimited | ✅ Unlimited |
| Weekly Debrief | ❌ Locked | ✅ Auto Sunday | ✅ Auto Sunday |
| Deep Analysis Mode | ❌ | ✅ Counts as 3 msgs | ✅ Counts as 3 msgs |
| **Monthly Budget** | **30 msgs** | **300 msgs** | **1,500 msgs** |
| **Add-on packs** | ✅ $4.99/100 msg | ✅ $4.99/100 msg | ✅ (rarely needed) |
| **Referral bonus** | +50 msgs/referral | +100 msgs/referral | +500 msgs annual |

---

## Part 7: Compliance Checklist

- [ ] Disclaimer banner displayed on all AI screens: *"Educational use only. Not personalized investment advice."*
- [ ] `ai_chat_logs` table retaining all conversations for minimum 3 years (FINRA)
- [ ] AI responses never use directive language ("you should buy/sell X")
- [ ] Marketing copy uses: "AI-powered trading education assistant" — not "AI advisor"
- [ ] SEC-safe: no claims like "AI that knows when to trade" — compliant framing only
- [ ] Privacy policy updated to cover AI conversation data (30-day retention unless opted in)
- [ ] Risk Disclosure page updated to include AI feature limitations section

---

*TradeMind@bot LLC — Confidential Implementation Document — March 2026*
