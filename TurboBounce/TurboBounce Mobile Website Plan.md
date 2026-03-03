# TurboBounce Mobile-First Website: Complete Implementation Plan
## Executive Summary
This document is a detailed blueprint for building a mobile-first Progressive Web App (PWA) website for TurboBounce that integrates with the existing dark-theme trading dashboard (visible in the attached screenshots), incorporates all marketing plan elements (compounding calculator, referral system, family program, trust content), and targets both Gen Z and their parents. The architecture uses **Next.js + Tailwind CSS** as a PWA, matching the existing dark purple/green aesthetic already established in the tastytrade-integrated dashboard.[^1][^2]

PWAs are now the dominant mobile strategy in fintech — Alibaba saw a 76% conversion lift after adopting a PWA, and Pinterest saw dramatically higher engagement from indexed PWA pages. For TurboBounce, a PWA avoids the app store friction that kills Gen Z conversion while delivering the "Add to Home Screen" experience that feels like a native app.[^3][^4]

***
## Part 1: Design System — Matching the Existing Dashboard
### Current Design Analysis
The existing TurboBounce dashboard (shown in the attached screenshots) establishes a clear design language:



**Settings screen**: Dark background (#0D0B1A approximate), purple accent borders on selected cards (#7C3AED), green text for positive values (#10B981), red for negatives (#EF4444), white primary text, muted gray secondary text. Card-based layout with rounded corners (~12px). Strategy summary uses a clean key-value layout.[^1]



**Home dashboard**: Same dark base, green "TRADING ACTIVE" badge, teal-green progress cards for "Your Progress" section, purple accent on leaderboard/rank elements. Bottom nav uses icon-only navigation. The "Net Liquidating Value" is prominently displayed as the hero metric.[^2]
### Design Token Specification
Every screen in the new website must use these exact tokens to maintain visual continuity:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0D0B1A` | Page backgrounds |
| `--bg-card` | `#1A1730` | Card surfaces, nav |
| `--bg-card-hover` | `#231F3E` | Card hover states |
| `--accent-purple` | `#7C3AED` | CTA buttons, active borders, links |
| `--accent-purple-glow` | `rgba(124,58,237,0.3)` | Glow effects on buttons |
| `--text-primary` | `#FFFFFF` | Headings, primary content |
| `--text-secondary` | `#9CA3AF` | Subtitles, labels, timestamps |
| `--success` | `#10B981` | Positive P&L, live badges, success states |
| `--danger` | `#EF4444` | Negative P&L, drawdown, alerts |
| `--warning` | `#F59E0B` | Caution badges, streak icons |
| `--border-card` | `#2D2A4A` | Card borders |
| `--border-active` | `#7C3AED` | Active/selected card borders |
| `--font-heading` | `Inter, system-ui` | Headings |
| `--font-mono` | `JetBrains Mono, monospace` | Numbers, P&L, percentages |
| `--radius-card` | `12px` | Card corner radius |
| `--radius-button` | `8px` | Button corner radius |
### Typography Scale
| Level | Size | Weight | Color | Usage |
|-------|------|--------|-------|-------|
| H1 | 32px / 2rem | 700 | `--text-primary` | Page titles |
| H2 | 24px / 1.5rem | 600 | `--text-primary` | Section headers |
| H3 | 18px / 1.125rem | 600 | `--text-primary` | Card titles |
| Body | 16px / 1rem | 400 | `--text-secondary` | Paragraph text |
| Small | 14px / 0.875rem | 400 | `--text-secondary` | Labels, captions |
| Mono-Large | 28px / 1.75rem | 700 | `--text-primary` | Account value, big numbers |
| Mono-Data | 16px / 1rem | 500 | varies by +/- | P&L values, stats |
### Component Library
All components should mirror the existing dashboard's visual language:

**Card Component**: Dark surface (`--bg-card`), 1px border (`--border-card`), 12px radius, 16px padding. On active/selected state, border changes to `--border-active` (purple).[^1]

**Progress Card**: Teal-green gradient background for gamification cards (Week Streak, Win Rate, Rank), matching the existing "Your Progress" row.[^2]

**Badge Component**: Small pill-shaped badges — green for "TRADING ACTIVE" / "LIVE", purple for tier labels, amber for streaks.[^2]

**Button — Primary**: Purple background (`--accent-purple`), white text, 8px radius, subtle glow shadow on hover. Matches the "Set" button in the settings screen.[^1]

**Button — Secondary**: Transparent background, purple border, purple text. For less prominent CTAs.

**Bottom Navigation**: 5-icon fixed footer (Home, Signals, Positions, Activity, Settings), matching the existing dashboard nav exactly.[^2]

***
## Part 2: Tech Stack and Architecture
### Recommended Stack
| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | **Next.js 14+ (App Router)** | SSR for SEO (landing pages), client components for dashboard, built-in image optimization, API routes for backend[^5][^3] |
| Styling | **Tailwind CSS** + CSS custom properties | Utility-first matches rapid iteration; CSS variables enable the token system above[^6][^7] |
| PWA | **next-pwa** or `@serwist/next` | Service worker, offline support, "Add to Home Screen" manifest[^3][^8] |
| Auth | **NextAuth.js** or **Clerk** | OAuth for Google/Apple/email login; Clerk adds pre-built UI components |
| Payments | **Stripe** (subscriptions) + **Afterpay/Klarna** SDK (BNPL) | Recurring billing, referral credit management, BNPL for annual plans[^9] |
| Referral | **Rewardful** ($49/mo) or **Refgrow** ($29/mo) | Stripe-integrated referral tracking, unique links, automated payouts[^10] |
| Email | **ConvertKit** or **Resend** | Onboarding sequences (Day 0–30), Quarterly Letters, drawdown dispatches[^11] |
| Charts | **Recharts** or **Visx** (lightweight) | Compounding calculator charts, equity curves, performance visualizations |
| Database | **Supabase** (Postgres + Auth + Realtime) | User profiles, referral tracking, milestone badges, family linking |
| Broker API | **tastytrade JS SDK** (`@tastytrade/api`) | Auto-execution, account streaming, position sync[^12][^13] |
| Analytics | **PostHog** or **Mixpanel** (free tier) | Referral funnel, retention cohorts, churn prediction triggers[^10] |
| Hosting | **Vercel** | Edge deployment, automatic HTTPS, preview deploys, serverless functions |
### PWA Configuration
The `manifest.json` should establish TurboBounce as an installable app:

```json
{
  "name": "TurboBounce — Compounding Engine",
  "short_name": "TurboBounce",
  "description": "Automated options compounding — set it and grow",
  "start_url": "/dashboard",
  "display": "standalone",
  "background_color": "#0D0B1A",
  "theme_color": "#7C3AED",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

This ensures the PWA feels native on both iOS and Android home screens, with the dark purple theme color visible in the system UI.[^14][^3]

***
## Part 3: Site Map — Every Page and Screen
### Public Pages (No Login Required)
These pages are SEO-optimized, server-rendered, and designed to convert visitors into subscribers.

#### 3.1 Landing Page (`/`)

**Purpose**: Convert cold traffic (TikTok, YouTube, Reddit, ads) into Observer signups or paid subscribers.

**Layout (top-to-bottom, single scroll):**

1. **Hero Section**
   - Headline: "Turn Options Into a Compounding Machine"
   - Subheadline: "A volatility-adaptive engine that targets ~20% annualized growth. Automated. Defined-risk. 7-year track record."
   - CTA button (purple, glowing): "Start Free → Observer"
   - Secondary link: "See 7-year results ↓"
   - Background: Subtle animated gradient (dark purple → dark blue), matching the dashboard aesthetic
   - Social proof bar: "X compounders active · Sharpe Ratio 6.01 · 7 years backtested"[^1]

2. **Compounding Calculator (Interactive Widget)**
   - Full-width card component
   - Sliders: Starting capital ($1K–$100K), Monthly additions ($0–$500), CAGR (15%/20%/25%), Years (1–30)
   - Stacked area chart (Recharts): blue = contributions, green = compounding growth
   - Pre-set buttons: "College Student ($1K)" / "Side Hustle ($5K)" / "Serious Investor ($25K)" / "TurboBounce Actual ($5K → $21.8K)" / "TurboBounce Actual ($25K → $116.5K)"[^11][^15]
   - Default: $5K, $0/mo additions, 20% CAGR, 20 years = $191,688
   - Disclaimer text below: "Based on historical backtest results. Past performance ≠ future results."
   - This is the highest-converting element — visitors who spend 3+ minutes with a compound interest calculator convert at 60%[^16][^17]

3. **"How It Works" — 3-Step Visual**
   - Step 1: "Markets overreact" — icon of a chart dipping sharply
   - Step 2: "TurboBounce catches the snapback" — icon of a bounce arrow
   - Step 3: "Compounding does the rest" — icon of exponential curve
   - Below: "Average trade duration: 3–12 days. You check in once a week. The engine does everything else."[^15]

4. **7-Year Performance Section**
   - Two side-by-side performance cards (matching the dashboard card style):
     - $25K Track: +366.1% total return, +24.6% CAGR, 1,274 trades, 47.4% win rate, Sharpe 6.01[^15][^1]
     - $5K Track: +336.2% total return, +23.4% CAGR, 1,078 trades, 50.5% win rate[^15]
   - Year-by-year table (including red years: 2020 -5.3%, 2022 -27.7%) — transparency builds trust[^15]
   - Mini equity curve chart for each track

5. **"The Chameleon Engine" Explainer**
   - Visual diagram: two states
     - Left card: "Low Volatility" → "Buys deep ITM options for stock-like exposure at fraction of cost"
     - Right card: "High Volatility" → "Sells premium with defined-risk spreads to collect inflated insurance premiums"
   - Below: "The only options engine that dynamically adapts its structure to the VIX regime. Competitors always sell. Or always buy. TurboBounce does both."[^9][^15]

6. **"What About Crashes?" — 2022 Proof Section**
   - Headline: "Our Worst Year: -27.7%. Here's Why That Matters."
   - Comparison bar chart: TQQQ -79% | QQQ -33% | TurboBounce 25K -27.7% | TurboBounce 5K -35.2%
   - Recovery callout: "2023: +65.8%. 2024: +93.5%. If you quit in December 2022, you missed the two best years in our history."[^15]
   - Quote card: "The stock market is a device for transferring money from the impatient to the patient." — Warren Buffett

7. **Social Proof / Trust Badges**
   - "Integrated with tastytrade · Defined-risk on every trade · Level 2+ options approval"
   - Logos: tastytrade, E*TRADE (custodial), Stripe (payments)
   - "All trade signals auto-execute on your own brokerage account. We never touch your money."

8. **Pricing Section**
   - Three cards (Observer / Builder / Compounder) matching the "Risk Level" card selector style from settings page[^1]
   - Observer ($0): 24h delayed alerts, educational content, compounding calculator access
   - Builder ($29/mo): Real-time alerts, Discord access, basic trade signals
   - Compounder ($49/mo or $399/yr): Full auto-execution via tastytrade API, all strategy layers, priority support, family dashboard eligible
   - BNPL badge on annual plan: "4 × $100 via Afterpay/Klarna"[^9]
   - "Compounder Annual" highlighted as "Best Value — Save 30%"

9. **Family Section (Parent-Targeted)**
   - Headline: "Teach Your Child How Professional Investing Actually Works"
   - Two-column: left = parent card ($25K track), right = child card ($5K track)
   - "Family Bundle: 2 Compounder plans at $39/mo each (20% off). Shared Family Dashboard."[^10]
   - "Works with tastytrade and E*TRADE custodial accounts"[^10]
   - CTA: "Start Your Family's Compounding Journey →"

10. **Final CTA**
    - "One decision now. Thousands of smart trades over the next decade."
    - Email capture for Observer tier
    - Purple CTA button: "Start Free"

#### 3.2 Performance Page (`/results`)

**Purpose**: Detailed, transparent performance data — the trust engine.

**Content**:
- Full year-by-year table for both $25K and $5K accounts (all data from TurboBounce Overview)[^15]
- Monthly return heatmap grid (green = positive, red = negative)
- Interactive equity curve chart (toggle between $25K / $5K / both overlaid)
- Benchmark comparison chart: TurboBounce vs SPY vs QQQ vs TQQQ (buy-and-hold)
- Risk metrics table: Sharpe ratio (6.01), max drawdown (-27.7%), Calmar ratio, win rate, avg win size, avg loss size[^1]
- Trade distribution chart: % NAKED_LONG vs DIAGONAL vs CREDIT_SPREAD, broken by year
- Drawdown chart: shows every peak-to-trough cycle and recovery time
- Download button: "Download Full Performance Report (PDF)"

#### 3.3 How It Works Page (`/how-it-works`)

**Purpose**: Educate without overwhelming. Reduce the "what is mean reversion?" barrier for Gen Z beginners.

**Content sections**:
1. "What Is Mean Reversion?" — 60-second explainer with animated bouncing ball visual
2. "The Volatility-Adaptive Engine" — expanded chameleon diagram with real trade examples
3. "Crash Protection" — the falling-knife filter explained with 2022 walkthrough[^15]
4. "Your Time Investment" — "5 minutes per week. The engine handles everything else."
5. "Is This For Me?" — Comparison cards:
   - "I have $1K–5K" → Builder tier, small account track record
   - "I have $5K–25K" → Compounder tier, standard track record
   - "I want to teach my teen" → Family Bundle
   - "I want to watch first" → Observer tier (free)

#### 3.4 Referral Hub (`/refer`)

**Purpose**: Central page for the referral program — shareable, trackable.

**Content**:
- Hero: "Invite a Friend to Start a 10-Year Compounding Journey"
- Unique referral link generator (auto-generated for logged-in users)
- One-tap share buttons: WhatsApp, iMessage, TikTok DM, Instagram DM, Twitter, Email, Copy Link[^10]
- Referral tier table (matching the card-selector style from the dashboard):[^10]

| Tier | Referrals | You Get | Friend Gets |
|------|-----------|---------|-------------|
| Standard | 1–4 | $15 credit | $15 off first month |
| Power Referrer | 5–9 | $20 credit | $15 off first month |
| Ambassador | 10+ | $25 + free month Compounder | $15 + free week |

- Real-time referral tracker: "You've referred X friends. Y converted. $Z earned."
- Leaderboard preview (top 10 referrers this month)[^18]
- "10-Year Compounding Challenge" enrollment section: "Commit to 10 years of compounding with your friends. Track your journey side-by-side."[^11]

#### 3.5 Family Page (`/family`)

**Purpose**: Dedicated parent-facing landing page for the "Teach & Trade Together" program.

**Content**:
- Hero: "What If Your Child's First Investment Grew 20% Per Year — Automatically?"
- Family Bundle pricing card: 2 × Compounder at $39/mo each (20% off)[^10]
- Custodial account setup guide (tastytrade + E*TRADE): step-by-step with screenshots[^10]
- Family Dashboard preview mockup: parent and child equity curves side-by-side
- "Safety First" section:
  - "Every trade has a defined maximum loss"
  - "No margin calls, no YOLO, just math"
  - "You manage the custodial account until they're 18"[^10]
- Parent testimonial cards (composite/anonymized)
- Video embed: "How I Set Up a 10-Year Account for My Teenager"
- CTA: "Start Your Family Bundle →"

#### 3.6 Blog / Learn (`/learn`)

**Purpose**: SEO content hub + trust-building educational content.

**Categories**:
- "Compounding 101" — series on compound interest, long-term wealth, Buffett's approach[^11]
- "Strategy Deep Dives" — how mean reversion works, what a diagonal spread is, VIX regimes
- "Trade Recaps" — weekly summaries of what the engine did (monthly for Observer, weekly for Builder+)
- "Quarterly Letters" — the hedge fund-style investor letters (delayed 30 days for Observer)[^11]
- "For Parents" — custodial account guides, teaching financial literacy, family investing

Each article should have: share buttons, related content, CTA to upgrade, and comment section (via Discord embed or Disqus).

#### 3.7 Quarterly Letter Archive (`/letters`)

**Purpose**: Searchable archive of all quarterly letters. Builds long-term trust and SEO authority.

- Latest letter displayed in full
- Past letters listed with summaries
- Access gating: Observer gets letters 30 days delayed; Builder+ gets immediate access[^11]

***
### Authenticated Pages (Login Required)
These pages mirror and extend the existing dashboard functionality shown in the screenshots.

#### 3.8 Dashboard (`/dashboard`)

This is the primary logged-in experience, matching the existing layout from the screenshots exactly:[^2]

**Top Bar**:
- "Welcome back, [first name]"
- Strategy badge: "TQQQ DUAL-SIDED · TRADING ACTIVE" with green dot
- VIX value + REGIME indicator (LOW_VOL / HIGH_VOL / CRISIS / UNKNOWN)[^2]

**Hero Card — Net Liquidating Value**:
- Large mono font: "$251,478.48"
- Green/red delta today: "+$1,234.56 today"
- Circular progress indicator (73%)[^2]

**"Your Progress" Row** (gamification cards, matching existing):

| Card | Value | Icon | Description |
|------|-------|------|-------------|
| Week Streak | 12 | 🔥 | Consecutive weeks subscribed |
| Win Rate | 51.2% | 🎯 | Rolling 90-day win rate |
| Rank | #47 | 🏆 | Position on subscriber leaderboard |

- "Total Profit" below: "+$8,234.50" (inception-to-date)[^2]

**Auto-Approve Trades** toggle: "Signals execute automatically on Tastytrade"[^2]

**Trade Signals Section**: "ACTION REQUIRED" banner when pending trades, or "All caught up! No pending signals."[^2]

**NEW — Compounding Dashboard Widgets** (added below existing layout):

- **"Time in Strategy" counter**: "You've been compounding for 247 days" — with a daily-incrementing counter and badge[^11]
- **Projected Value Panel**: Shows current trajectory projected to 1, 5, 10, 20 years at current growth rate. Interactive slider to adjust assumed CAGR (15%/20%/25%)
- **Drawdown Context Panel**: "Current drawdown: -3.2%. Historical worst: -27.7%. Recovery from worst: 14 months."[^11]
- **Milestone Badges Row**: Earned badges displayed as small purple/gold icons:
  - "First Trade" / "First $1K Profit" / "First Year" / "Survived First Drawdown" / "3-Year Veteran" / "10-Year Challenger"[^11]
- **Compounding Chart**: Mini equity curve showing the subscriber's own account growth since signup, with the backtest curve overlaid as a reference line

#### 3.9 Signals Page (`/signals`)

Matches existing "Signals" tab from the dashboard nav:[^2]

- Active signals list with entry price, stop, target, DTE, strategy type (NAKED_LONG / DIAGONAL / CREDIT_SPREAD)
- Signal status: PENDING / FILLED / CLOSED
- Historical signals archive with filter/search
- For Builder tier: manual copy instructions
- For Compounder tier: auto-execution status + one-tap approve/reject for non-auto users

#### 3.10 Positions Page (`/positions`)

- Live positions synced from tastytrade API[^12]
- Each position card shows: ticker, strategy type, entry date, current P&L (green/red), DTE remaining, max risk
- Position detail: opens to show full leg breakdown (e.g., diagonal spread → short put strike, long put strike, expiration dates)

#### 3.11 Activity Page (`/activity`)

- Timeline of all account events: trades opened, trades closed, P&L posted, milestone earned, referral converted
- Filter by: Trades / Milestones / Referrals / Account Events

#### 3.12 Settings Page (`/settings`)

Matches existing settings screen from screenshot exactly:[^1]

- **Investment Principal** input (currently shows $25,000 with "Set" button)
- **Risk Level** selector: Conservative (+117%) / Balanced (+98%) / Aggressive (+135%)[^1]
- **Strategy Summary**: Strategy name, Put Side, Call Side, Backtest Return, Sharpe Ratio[^1]
- **Auto-Approval** toggle with tastytrade linking instructions
- **NEW additions**:
  - Account linking section: "Connect Tastytrade" / "Connect E*TRADE" OAuth buttons
  - Notification preferences: email, push, Discord
  - Referral link and stats: "Your unique link: turbobounce.com/r/[code]. Referrals: X. Earnings: $Y."
  - Family linking: "Link a family member's account" → enters their email, sends invite for Family Dashboard
  - Subscription management: current plan, upgrade/downgrade, billing history, BNPL status
  - "10-Year Challenge" enrollment toggle

#### 3.13 Referral Dashboard (`/referrals`)

- Referral link + share buttons (same as `/refer` but authenticated)
- Stats: Total shared / Clicks / Signups / Converted / Credits earned
- Referral status list: each referred friend's status (clicked / signed up / paid / active 30 days → credit issued)
- Tier progress bar: "You're at Power Referrer level (6/10 to Ambassador)"
- Monthly leaderboard (top 25 referrers)[^18][^19]

#### 3.14 Family Dashboard (`/family/dashboard`)

- Side-by-side equity curves: parent account + child account
- Combined household P&L summary
- Each account's "Time in Strategy" counter
- Shared milestone feed: "Your child hit $1K in profits! 🎉"
- Family referral status

#### 3.15 Leaderboard (`/leaderboard`)

Full leaderboard accessible from "Your Progress" section:[^2]

- Ranking by: Total profit ($ or %), Streak length, Referrals
- Toggle: All Time / This Month / This Week
- Each entry: rank, anonymized username (or opted-in display name), metric value, tier badge
- "Your Position" highlighted
- Friend-based leaderboards outperform anonymous ones by 3:1 in driving engagement — allow subscribers to follow specific users[^18]

***
## Part 4: Mobile Navigation Architecture
### Bottom Tab Bar (Authenticated — 5 Tabs)
Matching the existing dashboard exactly:[^2]

| Tab | Icon | Route | Notes |
|-----|------|-------|-------|
| Home | 🏠 | `/dashboard` | Primary dashboard |
| Signals | 📈 | `/signals` | Active trade alerts |
| Positions | 📊 | `/positions` | Live portfolio |
| Activity | 🔔 | `/activity` | Timeline of events |
| Settings | ⚙️ | `/settings` | Account config |
### Hamburger Menu (Public Pages — Top Right)
For non-authenticated pages:

- Home
- How It Works
- Results
- Refer a Friend
- Family
- Learn (Blog)
- Quarterly Letters
- Pricing
- Login / Sign Up (purple CTA button)
### Swipe Navigation
Enable left/right swipe gestures between the 5 main dashboard tabs for native-feeling navigation on mobile.

***
## Part 5: Push Notifications (PWA)
PWA push notifications are critical for retention and re-engagement, especially since TurboBounce's strategy requires users to stay engaged over years.[^19][^3]
### Notification Types
| Notification | Trigger | Content Example | Purpose |
|-------------|---------|-----------------|---------|
| Trade Opened | New signal filled | "🟢 New trade: TQQQ Bull Put Spread opened at $2.15 credit. Max risk: $285." | Engagement |
| Trade Closed | Position exited | "✅ TQQQ trade closed: +$340 profit (119% return on risk). Total P&L this month: +$1,280." | Trust + celebration |
| Milestone | Badge earned | "🏆 Milestone! You've been compounding for 365 days. 3-year badge unlocked next!" | Gamification |
| Weekly Summary | Every Sunday 6pm | "📊 This week: 3 trades, 2 wins, +$520. Your projected 10-year value: $84,200." | Retention |
| Drawdown Alert | Portfolio -5%+ | "📉 Current drawdown: -8%. Worst historical: -28%. The engine is still running. Details →" | Panic prevention |
| Quarterly Letter | Letter published | "📬 Q1 2027 Letter to Compounders is live. Read the full results →" | Trust content |
| Referral Converted | Friend pays | "🎉 Your friend Alex just subscribed! $15 credit added to your account." | Referral loop |
| Re-engagement | No login in 14 days | "Your engine earned +$380 while you were away. Check your dashboard →" | Churn prevention[^11] |

***
## Part 6: Onboarding Flow (First-Time User Journey)
### Step 1: Landing Page → Sign Up
User clicks "Start Free" on landing page. Modal opens (or redirect to `/signup`):

- Option A: "Sign up with Google" (OAuth)
- Option B: "Sign up with Apple" (OAuth)
- Option C: Email + password
- Below: "Already have an account? Log in"
### Step 2: Profile Setup (3 Screens)
**Screen 1 — "About You"**:
- "What's your investing experience?" → Beginner / Intermediate / Advanced
- "How much are you starting with?" → Under $5K / $5K–$25K / $25K+
- Purpose: Customizes onboarding content and default settings

**Screen 2 — "Choose Your Plan"**:
- Three cards: Observer / Builder / Compounder (same as pricing section)
- "Start with Observer (free)" as default
- "Upgrade anytime" reassurance text

**Screen 3 — "Connect Your Broker" (optional)**:
- "Link Tastytrade" button → OAuth flow using tastytrade API[^12]
- "Skip for now — I'll connect later"
- For Compounder: required for auto-execution
- For Observer/Builder: optional, enables position tracking
### Step 3: Dashboard Tour (First Login)
Guided tooltip overlay (5 steps):
1. "This is your Net Liquidating Value — your account's total worth."
2. "Your Progress tracks your streak, win rate, and rank. Keep compounding!"
3. "Trade Signals shows you what the engine is doing. Compounder tier auto-executes."
4. "Your compounding counter starts now. The longer you stay, the more it works."
5. "Invite friends from the Referral tab. Both of you get $15 off."
### Step 4: Email Onboarding (Days 0–30)
Triggered automatically via ConvertKit/Resend — the full 6-email sequence from the Master Marketing Plan:[^11]
- Day 0: "Your compounding engine is live 🚀"
- Day 3: "Why 48% win rate still makes money"
- Day 7: "Our worst year: -27.7%. Here's the full story."
- Day 14: "Meet two TurboBounce subscribers"
- Day 21: "The Chameleon Engine explained"
- Day 30: "Your first month scorecard"

***
## Part 7: Key Functional Features
### 7.1 Interactive Compounding Calculator
**Implementation**: Custom React component using Recharts for the stacked area chart.

**Inputs** (all sliders with numeric input fallback):
- Starting capital: $1,000 – $100,000 (step: $500)
- Monthly addition: $0 – $500 (step: $25)
- CAGR: 15%, 20%, 25% (toggle buttons)
- Time horizon: 1 – 30 years (slider)

**Outputs**:
- Final value (large, mono font)
- Total contributions vs total growth (donut or stacked bar)
- Year-by-year table (expandable)
- Stacked area chart: blue = contributions, green = growth[^11]

**Pre-set scenario buttons**: "College Student" / "Side Hustle" / "Serious Investor" / "TB Actual 5K" / "TB Actual 25K"[^11]

The calculator should be embeddable via iframe for use in blog posts, TikTok link-in-bio pages, and ambassador content.
### 7.2 Referral System Integration
**Backend**: Rewardful or Refgrow integrated with Stripe.[^10]

**User-facing features**:
- Unique referral link generated at signup (e.g., `turbobounce.com/r/alexj`)
- Share buttons: WhatsApp, iMessage, TikTok DM, Instagram DM, Twitter, Email, Copy[^10]
- Referral dashboard: real-time tracking of clicks → signups → conversions → credits
- Tier progression bar: Standard → Power Referrer → Ambassador
- Leaderboard: monthly ranking with top 3 highlighted
- Automated credit issuance after 30-day qualification period[^10]

**Fraud prevention**:
- Device fingerprinting to prevent self-referral
- Cap: 20 referrals per person per quarter
- Manual review trigger: >10 referrals in one week[^10]
### 7.3 Tastytrade API Integration
Using the official `@tastytrade/api` JavaScript SDK:[^12]

- **OAuth login**: Users authorize TurboBounce to read positions and execute trades on their tastytrade account
- **Account streaming**: Real-time position updates via WebSocket (`accountStreamer`)[^12]
- **Auto-execution**: When a signal fires, API places the order on the user's account (Compounder tier only)
- **Position sync**: Dashboard shows live positions pulled from tastytrade API
- **Net Liquidating Value**: Pulled from `balancesAndPositionsService` — displayed as the hero metric[^2]
### 7.4 Gamification System
Based on fintech gamification research showing leaderboards increase transaction frequency by 28%:[^18]

**Badges** (stored in Supabase, displayed on dashboard):

| Badge | Criteria | Icon |
|-------|----------|------|
| First Trade | First signal filled | 🟢 |
| First Win | First profitable trade closed | ✅ |
| Week Warrior | 4 consecutive weeks active | 🔥 |
| $1K Club | $1,000 cumulative profit | 💰 |
| Drawdown Survivor | Stayed subscribed through -10%+ drawdown | 🛡️ |
| 1-Year Compounder | 365 days subscribed | 🏅 |
| 3-Year Veteran | 1,095 days subscribed | ⭐ |
| 10-Year Challenger | Enrolled in 10-Year Challenge | 🏆 |
| Family Builder | Linked a family member's account | 👨‍👩‍👧 |
| Referral Star | 5+ successful referrals | 🌟 |

**Leaderboard**: Ranking by total profit %, updated weekly. Friend-based comparisons for opted-in users.[^19][^18]

**Weekly Streak**: Consecutive weeks with at least one dashboard login. Displayed prominently in the "Your Progress" row.[^2]
### 7.5 Family Dashboard
**Linking flow**:
1. Parent (account A) clicks "Link Family Member" in settings
2. Enters child's email → system sends invite
3. Child (account B) accepts → accounts linked
4. Both see `/family/dashboard` with side-by-side view

**Shared view**:
- Two equity curve charts (parent left, child right)
- Combined household stats: total profit, combined streak, joint milestone feed
- 20% Family Bundle discount auto-applied when both on Compounder tier[^10]

***
## Part 8: Content Management
### Blog/Learn Section CMS
Use **MDX** (Markdown + React components) stored in the repo, or **Contentful** headless CMS for non-technical team members to publish.

**Content types**:

| Type | Schedule | Author | Access |
|------|----------|--------|--------|
| Trade Recap | Weekly | TurboBounce team | Builder+ (delayed 7 days for Observer) |
| Strategy Explainer | Bi-weekly | TurboBounce team | All |
| Compounding 101 | Monthly | TurboBounce team | All |
| Quarterly Letter | Quarterly | TurboBounce founder | Builder+ (delayed 30 days for Observer)[^11] |
| Parent Guide | Monthly | TurboBounce team | All |
| Guest Post | As available | Community / ambassadors | All |
### SEO Optimization
Every public page should have:
- Server-rendered HTML via Next.js SSR
- Dynamic `<meta>` tags: title, description, OG image
- Structured data (JSON-LD) for FAQ pages, performance data, and articles
- Canonical URLs
- Sitemap.xml auto-generated by Next.js

***
## Part 9: Ambassador Portal (`/ambassador`)
A dedicated section for campus ambassadors, accessible by invitation only:[^10]

**Features**:
- Custom referral link with campus-specific tracking code
- Content library: pre-made TikTok scripts, Instagram carousel templates, story templates
- Content calendar: what to post each Monday/Wednesday/Friday[^10]
- Earnings dashboard: referrals converted, credits earned, monthly stipend status
- Leaderboard: monthly ranking across all campuses, top 3 earn bonus rewards
- Direct messaging with TurboBounce team

***
## Part 10: Development Phases
### Phase 1 — MVP (Weeks 1–6)
**Goal**: Launchable product with core conversion and trust features.

- [ ] Next.js project setup with Tailwind CSS, dark theme tokens, PWA manifest
- [ ] Landing page with all 10 sections (hero → final CTA)
- [ ] Interactive compounding calculator (Recharts)
- [ ] Auth system (NextAuth or Clerk: Google, Apple, email)
- [ ] Observer / Builder / Compounder tier gating via Stripe subscriptions
- [ ] BNPL integration (Afterpay or Klarna) for annual Compounder
- [ ] Dashboard home page matching existing screenshot layout[^2]
- [ ] Settings page matching existing screenshot layout[^1]
- [ ] Tastytrade OAuth linking + position sync[^12]
- [ ] Email onboarding sequence (Days 0–30) via ConvertKit
- [ ] Performance page (`/results`) with year-by-year data
- [ ] Basic blog/learn section with first 5 articles
- [ ] Mobile-responsive across all pages
- [ ] PWA installable from browser ("Add to Home Screen")
### Phase 2 — Growth Features (Weeks 7–10)
**Goal**: Referral engine, gamification, community integration.

- [ ] Referral system via Rewardful + Stripe webhooks
- [ ] Referral hub page (`/refer`) with share buttons and tracking
- [ ] Referral dashboard for authenticated users
- [ ] Gamification badges system (Supabase)
- [ ] Leaderboard page (`/leaderboard`)
- [ ] Weekly streak tracking
- [ ] Compounding widgets on dashboard (time counter, projected value, drawdown context)
- [ ] Milestone badges row on dashboard
- [ ] Push notification system (trade opened/closed, milestones, weekly summary)
- [ ] "10-Year Compounding Challenge" enrollment and tracking
- [ ] Discord integration: webhook for trade alerts, invite link in dashboard
### Phase 3 — Family + Ambassador (Weeks 11–14)
**Goal**: Parent acquisition channel and campus program.

- [ ] Family page (`/family`) with parent-targeted content
- [ ] Family Dashboard (`/family/dashboard`) with linked accounts
- [ ] Family Bundle pricing logic in Stripe (20% discount for 2+ household accounts)
- [ ] Custodial account setup guides (tastytrade + E*TRADE)
- [ ] Ambassador portal (`/ambassador`) with content library and leaderboard
- [ ] Ambassador-specific referral tracking codes
- [ ] Quarterly Letter system: CMS + email distribution + gated archive
- [ ] Drawdown Dispatch automated emails (triggered by -10%+ drawdown)
- [ ] "Pause, Don't Cancel" modal on cancellation page[^11]
- [ ] Churn prediction triggers: no login 14 days → re-engagement email[^11]
### Phase 4 — Polish + Scale (Weeks 15–18)
**Goal**: Optimization, analytics, and marketing automation.

- [ ] PostHog/Mixpanel analytics: referral funnel, retention cohorts, feature adoption
- [ ] A/B testing framework for landing page CTAs, pricing display, calculator defaults
- [ ] Auto-generated monthly performance video (template + data injection)
- [ ] Embeddable calculator widget for ambassador content and external blogs
- [ ] Reddit/Twitter auto-posting for trade recaps (with approval workflow)
- [ ] Mobile performance optimization: Lighthouse 90+ on all pages
- [ ] Accessibility audit: WCAG AA compliance for all interactive elements[^6][^7]
- [ ] Full SEO audit and optimization
- [ ] Load testing for 1,000+ concurrent dashboard users

***
## Part 11: Estimated Development Resources
| Role | Scope | Estimated Time |
|------|-------|---------------|
| Full-Stack Developer (Next.js) | Framework, API routes, auth, Stripe, tastytrade integration | 12–16 weeks |
| Frontend Developer | UI components, dark theme, animations, charts, mobile responsiveness | 10–14 weeks |
| Designer (Figma) | Component library, new page layouts matching existing aesthetic, marketing assets | 4–6 weeks |
| Backend Developer | Supabase schema, referral tracking, gamification logic, notification system | 8–10 weeks |
| Content Writer | Landing page copy, blog articles, email sequences, quarterly letter template | Ongoing |

**For a solo founder / small team**: Phases 1+2 can be executed by a single strong full-stack developer in ~10 weeks using the existing dashboard as the component reference, with pre-built solutions (Clerk for auth, Rewardful for referrals, ConvertKit for email). Phase 3 adds 4 weeks. Phase 4 is iterative.

**Estimated cost** (freelance): $15,000–$25,000 for Phases 1–3, or $0 if built in-house with the existing team.

---

## References

1. [image.jpg](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/images/67975583/aa40e51c-fa19-4f24-b148-d6cf77e9a7b5/image.jpg?AWSAccessKeyId=ASIA2F3EMEYEURBNQUWT&Signature=CNWFsLnEahG%2FtphM99mpaD7fFJ4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEJT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIByog2nxvdfuFTV5f70r3m6I5qX41xm2tELEWKW%2BbZW7AiEA2dB0rSl%2Fi6qxMrjIWxNn232aSY7EEYcwPvJ6qaE5wwUq8wQIXRABGgw2OTk3NTMzMDk3MDUiDOnYxkUXMk4AdD5F%2FyrQBKYs%2FhY0vQlQ23gkXVoZQSWkct5SiVApd2FeXHMOHrXhWigHkhKy8xgiyz4MjD7rjj1fwM1rX3aP6n5fQEiJcIF96sZQQ1Db4pOP3%2FbRoMQv9j2QCAJlSDVXwxbgBDBtd0jyabN1dpAOVEI3rPwhJyxHisxkyAJXOzijpFX3kuXqHEGKVTkOzn8J2dHwQJB9QKn5YzIMVgCSEqm7nR24q%2BkNfrwWUqbbsLiUH%2FGylnRzJe0o4NO9qJufQ4NBlW9X5FqhPMW9MpkpbbPdiHSNsp%2BIZngA9ZgUSYpPZDNKHhUJ5sXaebmbYiYh78tq%2BbJUFMNM2YFjbu%2B0Rmy%2BXEf666p9eIgqy6rREl0oe6r%2Fa6BRXuOxUDzwgVOMYowP%2BcVMrZs0%2FK8gDRvN2BLVvI8K5MB9NBuZF2AnZYKhnt5iG8jSbgkr7lmnxf56rJxYRADip75KgPYO79pCRWFyKjVM%2BoCse6PkBvF70HkmqjG8rap0ykX0Cc7i1jAai8cnJxU5qaMCtD0nc8JTI%2Fi5Jl9t8yjVAo2AtGKPvsHVvOt3dZtB8ZH%2BWnrL7WmaBtWgGhqiWxRdIcs8W2pbBNWhlxX%2FBhT%2B4ZL3TVE2CvtK6rMvoKNwc6ezlvLQqyIZWulOodcAXWuUHgGgY9%2B0d8PwWNFYuBAdktu8kAmBwPtDsWdnEZZwzTY6muV123llgZzvqRLRrGs1stJ%2BG%2FTpyrILKnKksd%2BQ89Hr1tbH03ggmeu%2FNjFSiyB0hzU0rqTYmqMQ%2FgJU%2FvY8jsMbRrcavk%2FEKbHGSSQwgYmNzQY6mAHGR8owCMMiMQO2mauWBMvTupsSHkrVQdgWsRD64ivmxk9oPe9mNuEy61lTnqdB%2BBVmFyyrTHx%2BE8wvelLgKU150VkWUFYmldWviEql7Hi0HcdJpnVfJqRaHk0o5sOHqcDsPDKVngI5DfOzHp3ewcZ1Gl2jnXzytjzxS%2B8ijFunh%2BNQI0YRZX9VYxjMWD2wm18qIMU%2BmlHIig%3D%3D&Expires=1772311267)

2. [image.jpg](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/images/67975583/0603daec-0fa0-466d-8537-47eef723bd6e/image.jpg?AWSAccessKeyId=ASIA2F3EMEYEURBNQUWT&Signature=P%2Flaf46qqbFiacCTVaB6F1Cy6WY%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEJT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIByog2nxvdfuFTV5f70r3m6I5qX41xm2tELEWKW%2BbZW7AiEA2dB0rSl%2Fi6qxMrjIWxNn232aSY7EEYcwPvJ6qaE5wwUq8wQIXRABGgw2OTk3NTMzMDk3MDUiDOnYxkUXMk4AdD5F%2FyrQBKYs%2FhY0vQlQ23gkXVoZQSWkct5SiVApd2FeXHMOHrXhWigHkhKy8xgiyz4MjD7rjj1fwM1rX3aP6n5fQEiJcIF96sZQQ1Db4pOP3%2FbRoMQv9j2QCAJlSDVXwxbgBDBtd0jyabN1dpAOVEI3rPwhJyxHisxkyAJXOzijpFX3kuXqHEGKVTkOzn8J2dHwQJB9QKn5YzIMVgCSEqm7nR24q%2BkNfrwWUqbbsLiUH%2FGylnRzJe0o4NO9qJufQ4NBlW9X5FqhPMW9MpkpbbPdiHSNsp%2BIZngA9ZgUSYpPZDNKHhUJ5sXaebmbYiYh78tq%2BbJUFMNM2YFjbu%2B0Rmy%2BXEf666p9eIgqy6rREl0oe6r%2Fa6BRXuOxUDzwgVOMYowP%2BcVMrZs0%2FK8gDRvN2BLVvI8K5MB9NBuZF2AnZYKhnt5iG8jSbgkr7lmnxf56rJxYRADip75KgPYO79pCRWFyKjVM%2BoCse6PkBvF70HkmqjG8rap0ykX0Cc7i1jAai8cnJxU5qaMCtD0nc8JTI%2Fi5Jl9t8yjVAo2AtGKPvsHVvOt3dZtB8ZH%2BWnrL7WmaBtWgGhqiWxRdIcs8W2pbBNWhlxX%2FBhT%2B4ZL3TVE2CvtK6rMvoKNwc6ezlvLQqyIZWulOodcAXWuUHgGgY9%2B0d8PwWNFYuBAdktu8kAmBwPtDsWdnEZZwzTY6muV123llgZzvqRLRrGs1stJ%2BG%2FTpyrILKnKksd%2BQ89Hr1tbH03ggmeu%2FNjFSiyB0hzU0rqTYmqMQ%2FgJU%2FvY8jsMbRrcavk%2FEKbHGSSQwgYmNzQY6mAHGR8owCMMiMQO2mauWBMvTupsSHkrVQdgWsRD64ivmxk9oPe9mNuEy61lTnqdB%2BBVmFyyrTHx%2BE8wvelLgKU150VkWUFYmldWviEql7Hi0HcdJpnVfJqRaHk0o5sOHqcDsPDKVngI5DfOzHp3ewcZ1Gl2jnXzytjzxS%2B8ijFunh%2BNQI0YRZX9VYxjMWD2wm18qIMU%2BmlHIig%3D%3D&Expires=1772311267)

3. [The Future of Mobile-First in FinTech: Why PWAs Are Leading ...](https://softwaretrends.com/the-future-of-mobile-first-in-fintech-why-pwas-are-leading-the-charge/) - Explore how Progressive Web Apps offer seamless, secure, and storage-friendly experiences for modern...

4. [Progressive Web Apps in 2026: SEO, UX & Conversion Benefits](https://www.nunuqs.com/blog/progressive-web-apps-in-2026-seo-ux-conversion-benefits) - This article explores how Progressive Web Apps (PWAs) in 2026 provide significant advantages in SEO,...

5. [Fintech Web Design Trends 2026: Trust, Performance & AI Visibility](https://wsa.design/news/modern-fintech-web-design-trends-in-2026) - Explore the key fintech web design trends shaping 2026 — from trust-centered architecture and Core W...

6. [How to Design Dark Mode: A 2026 Guide for Mobile App Designers](https://appinventiv.com/blog/guide-on-designing-dark-mode-for-mobile-app/) - 1. Avoid the pure black color · 2. Avoid the use of saturated colors on the dark themes · 3. Conside...

7. [Dark Theme Mobile UI Best Practices - Hakuna Matata Tech](https://www.hakunamatatatech.com/our-resources/blog/mobile-app-dark-theme-best-practices) - Dark Theme Mobile UI Best Practices improves user comfort.This guide shows USA company owners how to...

8. [7 PWA Trends That Will Define Mobile and Web development ...](https://www.appstory.org/blog/7-pwa-trends-that-will-define-mobile-and-web-development-in-2026/) - As browsers mature and performance APIs evolve, PWAs are set to redefine what “mobile-first” truly m...

9. [TurboBounce-Market-Analysis.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/7d866519-2ace-4786-b1cc-aaa009d4fea3/TurboBounce-Market-Analysis.pdf?AWSAccessKeyId=ASIA2F3EMEYEURBNQUWT&Signature=%2FSr9a92SRY%2B%2BMwLu2nJfmyIzOVY%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEJT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIByog2nxvdfuFTV5f70r3m6I5qX41xm2tELEWKW%2BbZW7AiEA2dB0rSl%2Fi6qxMrjIWxNn232aSY7EEYcwPvJ6qaE5wwUq8wQIXRABGgw2OTk3NTMzMDk3MDUiDOnYxkUXMk4AdD5F%2FyrQBKYs%2FhY0vQlQ23gkXVoZQSWkct5SiVApd2FeXHMOHrXhWigHkhKy8xgiyz4MjD7rjj1fwM1rX3aP6n5fQEiJcIF96sZQQ1Db4pOP3%2FbRoMQv9j2QCAJlSDVXwxbgBDBtd0jyabN1dpAOVEI3rPwhJyxHisxkyAJXOzijpFX3kuXqHEGKVTkOzn8J2dHwQJB9QKn5YzIMVgCSEqm7nR24q%2BkNfrwWUqbbsLiUH%2FGylnRzJe0o4NO9qJufQ4NBlW9X5FqhPMW9MpkpbbPdiHSNsp%2BIZngA9ZgUSYpPZDNKHhUJ5sXaebmbYiYh78tq%2BbJUFMNM2YFjbu%2B0Rmy%2BXEf666p9eIgqy6rREl0oe6r%2Fa6BRXuOxUDzwgVOMYowP%2BcVMrZs0%2FK8gDRvN2BLVvI8K5MB9NBuZF2AnZYKhnt5iG8jSbgkr7lmnxf56rJxYRADip75KgPYO79pCRWFyKjVM%2BoCse6PkBvF70HkmqjG8rap0ykX0Cc7i1jAai8cnJxU5qaMCtD0nc8JTI%2Fi5Jl9t8yjVAo2AtGKPvsHVvOt3dZtB8ZH%2BWnrL7WmaBtWgGhqiWxRdIcs8W2pbBNWhlxX%2FBhT%2B4ZL3TVE2CvtK6rMvoKNwc6ezlvLQqyIZWulOodcAXWuUHgGgY9%2B0d8PwWNFYuBAdktu8kAmBwPtDsWdnEZZwzTY6muV123llgZzvqRLRrGs1stJ%2BG%2FTpyrILKnKksd%2BQ89Hr1tbH03ggmeu%2FNjFSiyB0hzU0rqTYmqMQ%2FgJU%2FvY8jsMbRrcavk%2FEKbHGSSQwgYmNzQY6mAHGR8owCMMiMQO2mauWBMvTupsSHkrVQdgWsRD64ivmxk9oPe9mNuEy61lTnqdB%2BBVmFyyrTHx%2BE8wvelLgKU150VkWUFYmldWviEql7Hi0HcdJpnVfJqRaHk0o5sOHqcDsPDKVngI5DfOzHp3ewcZ1Gl2jnXzytjzxS%2B8ijFunh%2BNQI0YRZX9VYxjMWD2wm18qIMU%2BmlHIig%3D%3D&Expires=1772311267) - TurboBounce is highly marketable to Gen Z and younger retail
investors — but not as a traditional su...

10. [TurboBounce-Referral-Driven-Social-Media-Marketing-Plan-Targeting-Gen-Z-and-Their-Parents.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/9c0bb3dd-0f83-4260-b7eb-43b4ef9c167d/TurboBounce-Referral-Driven-Social-Media-Marketing-Plan-Targeting-Gen-Z-and-Their-Parents.pdf?AWSAccessKeyId=ASIA2F3EMEYEURBNQUWT&Signature=sLT4R0yw8IK6SLHvQ9JdXKNdiDQ%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEJT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIByog2nxvdfuFTV5f70r3m6I5qX41xm2tELEWKW%2BbZW7AiEA2dB0rSl%2Fi6qxMrjIWxNn232aSY7EEYcwPvJ6qaE5wwUq8wQIXRABGgw2OTk3NTMzMDk3MDUiDOnYxkUXMk4AdD5F%2FyrQBKYs%2FhY0vQlQ23gkXVoZQSWkct5SiVApd2FeXHMOHrXhWigHkhKy8xgiyz4MjD7rjj1fwM1rX3aP6n5fQEiJcIF96sZQQ1Db4pOP3%2FbRoMQv9j2QCAJlSDVXwxbgBDBtd0jyabN1dpAOVEI3rPwhJyxHisxkyAJXOzijpFX3kuXqHEGKVTkOzn8J2dHwQJB9QKn5YzIMVgCSEqm7nR24q%2BkNfrwWUqbbsLiUH%2FGylnRzJe0o4NO9qJufQ4NBlW9X5FqhPMW9MpkpbbPdiHSNsp%2BIZngA9ZgUSYpPZDNKHhUJ5sXaebmbYiYh78tq%2BbJUFMNM2YFjbu%2B0Rmy%2BXEf666p9eIgqy6rREl0oe6r%2Fa6BRXuOxUDzwgVOMYowP%2BcVMrZs0%2FK8gDRvN2BLVvI8K5MB9NBuZF2AnZYKhnt5iG8jSbgkr7lmnxf56rJxYRADip75KgPYO79pCRWFyKjVM%2BoCse6PkBvF70HkmqjG8rap0ykX0Cc7i1jAai8cnJxU5qaMCtD0nc8JTI%2Fi5Jl9t8yjVAo2AtGKPvsHVvOt3dZtB8ZH%2BWnrL7WmaBtWgGhqiWxRdIcs8W2pbBNWhlxX%2FBhT%2B4ZL3TVE2CvtK6rMvoKNwc6ezlvLQqyIZWulOodcAXWuUHgGgY9%2B0d8PwWNFYuBAdktu8kAmBwPtDsWdnEZZwzTY6muV123llgZzvqRLRrGs1stJ%2BG%2FTpyrILKnKksd%2BQ89Hr1tbH03ggmeu%2FNjFSiyB0hzU0rqTYmqMQ%2FgJU%2FvY8jsMbRrcavk%2FEKbHGSSQwgYmNzQY6mAHGR8owCMMiMQO2mauWBMvTupsSHkrVQdgWsRD64ivmxk9oPe9mNuEy61lTnqdB%2BBVmFyyrTHx%2BE8wvelLgKU150VkWUFYmldWviEql7Hi0HcdJpnVfJqRaHk0o5sOHqcDsPDKVngI5DfOzHp3ewcZ1Gl2jnXzytjzxS%2B8ijFunh%2BNQI0YRZX9VYxjMWD2wm18qIMU%2BmlHIig%3D%3D&Expires=1772311267) - The optimal referral reward for TurboBounce's $29–49/month
pricing is a double-sided "Give $15, Get ...

11. [TurboBounce-Master-Marketing.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/22a5acb6-9c3f-464e-bcc0-83e64cd62dc5/TurboBounce-Master-Marketing.pdf?AWSAccessKeyId=ASIA2F3EMEYEURBNQUWT&Signature=3s9zVMJFHzfVr0XaGM9mf2jQBaM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEJT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIByog2nxvdfuFTV5f70r3m6I5qX41xm2tELEWKW%2BbZW7AiEA2dB0rSl%2Fi6qxMrjIWxNn232aSY7EEYcwPvJ6qaE5wwUq8wQIXRABGgw2OTk3NTMzMDk3MDUiDOnYxkUXMk4AdD5F%2FyrQBKYs%2FhY0vQlQ23gkXVoZQSWkct5SiVApd2FeXHMOHrXhWigHkhKy8xgiyz4MjD7rjj1fwM1rX3aP6n5fQEiJcIF96sZQQ1Db4pOP3%2FbRoMQv9j2QCAJlSDVXwxbgBDBtd0jyabN1dpAOVEI3rPwhJyxHisxkyAJXOzijpFX3kuXqHEGKVTkOzn8J2dHwQJB9QKn5YzIMVgCSEqm7nR24q%2BkNfrwWUqbbsLiUH%2FGylnRzJe0o4NO9qJufQ4NBlW9X5FqhPMW9MpkpbbPdiHSNsp%2BIZngA9ZgUSYpPZDNKHhUJ5sXaebmbYiYh78tq%2BbJUFMNM2YFjbu%2B0Rmy%2BXEf666p9eIgqy6rREl0oe6r%2Fa6BRXuOxUDzwgVOMYowP%2BcVMrZs0%2FK8gDRvN2BLVvI8K5MB9NBuZF2AnZYKhnt5iG8jSbgkr7lmnxf56rJxYRADip75KgPYO79pCRWFyKjVM%2BoCse6PkBvF70HkmqjG8rap0ykX0Cc7i1jAai8cnJxU5qaMCtD0nc8JTI%2Fi5Jl9t8yjVAo2AtGKPvsHVvOt3dZtB8ZH%2BWnrL7WmaBtWgGhqiWxRdIcs8W2pbBNWhlxX%2FBhT%2B4ZL3TVE2CvtK6rMvoKNwc6ezlvLQqyIZWulOodcAXWuUHgGgY9%2B0d8PwWNFYuBAdktu8kAmBwPtDsWdnEZZwzTY6muV123llgZzvqRLRrGs1stJ%2BG%2FTpyrILKnKksd%2BQ89Hr1tbH03ggmeu%2FNjFSiyB0hzU0rqTYmqMQ%2FgJU%2FvY8jsMbRrcavk%2FEKbHGSSQwgYmNzQY6mAHGR8owCMMiMQO2mauWBMvTupsSHkrVQdgWsRD64ivmxk9oPe9mNuEy61lTnqdB%2BBVmFyyrTHx%2BE8wvelLgKU150VkWUFYmldWviEql7Hi0HcdJpnVfJqRaHk0o5sOHqcDsPDKVngI5DfOzHp3ewcZ1Gl2jnXzytjzxS%2B8ijFunh%2BNQI0YRZX9VYxjMWD2wm18qIMU%2BmlHIig%3D%3D&Expires=1772311267) - TurboBounce's success depends on one behavioral shift: getting
subscribers to stay invested and subs...

12. [Javascript sdk for the tastytrade api - GitHub](https://github.com/tastytrade/tastytrade-api-js) - Javascript sdk for the tastytrade api. Contribute to tastytrade/tastytrade-api-js development by cre...

13. [tastytrade-api-js/README.md at master · tastytrade/tastytrade-api-js](https://github.com/tastytrade/tastytrade-api-js/blob/master/README.md) - Javascript sdk for the tastytrade api. Contribute to tastytrade/tastytrade-api-js development by cre...

14. [Progressive Web App UX Tips & Design Strategies 2025 | Lollypop](https://lollypop.design/blog/2025/september/progressive-web-app-ux-tips-2025/) - Here, I want to share some of the hidden UX design tips and strategies that really set successful PW...

15. [TurboBounce_Overview.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/f207b9e6-5f40-43aa-a9f9-6888ed4edfab/TurboBounce_Overview.pdf?AWSAccessKeyId=ASIA2F3EMEYEURBNQUWT&Signature=D7r2woDHJENCcEsc0xAl30QhvZU%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEJT%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIByog2nxvdfuFTV5f70r3m6I5qX41xm2tELEWKW%2BbZW7AiEA2dB0rSl%2Fi6qxMrjIWxNn232aSY7EEYcwPvJ6qaE5wwUq8wQIXRABGgw2OTk3NTMzMDk3MDUiDOnYxkUXMk4AdD5F%2FyrQBKYs%2FhY0vQlQ23gkXVoZQSWkct5SiVApd2FeXHMOHrXhWigHkhKy8xgiyz4MjD7rjj1fwM1rX3aP6n5fQEiJcIF96sZQQ1Db4pOP3%2FbRoMQv9j2QCAJlSDVXwxbgBDBtd0jyabN1dpAOVEI3rPwhJyxHisxkyAJXOzijpFX3kuXqHEGKVTkOzn8J2dHwQJB9QKn5YzIMVgCSEqm7nR24q%2BkNfrwWUqbbsLiUH%2FGylnRzJe0o4NO9qJufQ4NBlW9X5FqhPMW9MpkpbbPdiHSNsp%2BIZngA9ZgUSYpPZDNKHhUJ5sXaebmbYiYh78tq%2BbJUFMNM2YFjbu%2B0Rmy%2BXEf666p9eIgqy6rREl0oe6r%2Fa6BRXuOxUDzwgVOMYowP%2BcVMrZs0%2FK8gDRvN2BLVvI8K5MB9NBuZF2AnZYKhnt5iG8jSbgkr7lmnxf56rJxYRADip75KgPYO79pCRWFyKjVM%2BoCse6PkBvF70HkmqjG8rap0ykX0Cc7i1jAai8cnJxU5qaMCtD0nc8JTI%2Fi5Jl9t8yjVAo2AtGKPvsHVvOt3dZtB8ZH%2BWnrL7WmaBtWgGhqiWxRdIcs8W2pbBNWhlxX%2FBhT%2B4ZL3TVE2CvtK6rMvoKNwc6ezlvLQqyIZWulOodcAXWuUHgGgY9%2B0d8PwWNFYuBAdktu8kAmBwPtDsWdnEZZwzTY6muV123llgZzvqRLRrGs1stJ%2BG%2FTpyrILKnKksd%2BQ89Hr1tbH03ggmeu%2FNjFSiyB0hzU0rqTYmqMQ%2FgJU%2FvY8jsMbRrcavk%2FEKbHGSSQwgYmNzQY6mAHGR8owCMMiMQO2mauWBMvTupsSHkrVQdgWsRD64ivmxk9oPe9mNuEy61lTnqdB%2BBVmFyyrTHx%2BE8wvelLgKU150VkWUFYmldWviEql7Hi0HcdJpnVfJqRaHk0o5sOHqcDsPDKVngI5DfOzHp3ewcZ1Gl2jnXzytjzxS%2B8ijFunh%2BNQI0YRZX9VYxjMWD2wm18qIMU%2BmlHIig%3D%3D&Expires=1772311267) - TurboBounce The Next Generation of Mean 
Reversion Trading 
Executive Summary 
TurboBounce is a soph...

16. [Free Compound Interest Calculator | Add Investment Growth ...](https://embeddable.co/free-compound-interest-calculator-widgets) - Create a compound interest calculator for your website with AI. Show investment growth with principa...

17. [Compound Interest Calculator widget | CALCONIC](https://www.calconic.com/calculator-widgets/compound-interest-calculator) - Our Compound interest calculator is designed to estimate how much money will be accumulated from one...

18. [1. Cred -- Spin The Wheel](https://www.plotline.so/blog/fintech-app-gamification-examples) - Discover 5 gamification strategies in fintechs like leaderboards, progress bars, and badges, and lea...

19. [Gamification Examples | User Retention - StriveCloud](https://www.strivecloud.io/blog/gen-z-fintech-user-retention) - Gen Z are the first digital-native generation and require a different approach to boost user retenti...

