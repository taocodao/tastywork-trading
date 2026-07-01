# TradeMind Complete Monetization & Growth Implementation Plan

> Version 1.0 — April 2026  
> Based on live pricing page (trademind.bot), Whop dashboard setup, and full conversation context.

---

## 1. Product Architecture Overview

TradeMind operates as two separate but connected apps sharing one backend.

| Layer | TradeMind Web (existing) | TradeMind for Whop (new) |
|---|---|---|
| Domain | trademind.bot | whop.com/trademindbot |
| Auth | Privy | Whop iframe auth |
| Billing | Stripe | Whop memberships |
| Trial entry | trademind.bot pricing page | Whop $15 trial product |
| Post-trial | trademind.bot/upgrade | trademind.bot/upgrade |
| Backend | EC2 + PostgreSQL (unchanged) | Same EC2 + PostgreSQL |
| Signal engine | TurboCore ML on EC2 | Same — shared |

The EC2 backend, PostgreSQL database, and all signal generation logic remain completely untouched. Only the presentation and billing layers differ between the two apps.

---

## 2. Pricing Structure (Current — trademind.bot)

Based on the live pricing page screenshots.

### Monthly Pricing

| Plan | Price | Key Features |
|---|---|---|
| TurboCore | $29/mo | TQQQ Core Model, SMA200 Gate, Tastytrade Execution, Standard UI |
| TurboCore Pro | $49/mo | Enhanced ML Regime Detection, Dynamic VIX Positioning, Early Signal Access, Priority Slack |
| Both Bundle | $69/mo | All models + TurboBounce Alpha, Portfolio Allocation Tooling, Founder Office Hours |

### Annual Pricing (existing toggle on site)

| Plan | Annual Price | Per Month | Savings |
|---|---|---|---|
| TurboCore | $249/yr | $20.75/mo | 28% (3.5 months free) |
| TurboCore Pro | $399/yr | $33.25/mo | 32% (4 months free) |
| Both Bundle | $549/yr | $45.75/mo | 33% (4 months free) |

### Trial (Whop entry point — new)

| Detail | Value |
|---|---|
| Price | $15 one-time |
| Duration | 30 days |
| Access level | TurboCore signals only |
| After expiry | Auto-redirect to trademind.bot/upgrade |
| Trial credit | $15 returned as credit on any subscription |
| Whop affiliate payout | $13.50 (90% of $15) |

---

## 3. The $15 Trial Conversion Mechanic

The trial fee is not just an entry price — it is a conversion engine. The $15 comes back to the user the moment they subscribe, making the trial effectively free in hindsight.

### How It Works

1. User pays $15 on Whop for 30-day TurboCore trial access.
2. On day 28, automated DM fires:
   > "Your TradeMind trial ends in 2 days. The $15 you paid comes back as credit the moment you subscribe — so your first month of TurboCore is $14, Pro is $34, or the Bundle is $54. Use code TRIALBACK15 at checkout: trademind.bot/upgrade"
3. User lands on trademind.bot/upgrade where the $15 credit is shown pre-applied on all three plan options.
4. User selects a plan and subscribes via Stripe (existing flow, no changes).

### Promo Code Setup (Whop — no code required)

- Navigate to Marketing → Promo codes → Create
- Code: `TRIALBACK15`
- Type: Fixed amount → $15 off
- Applies to: All subscription plans (monthly and annual)
- Limit: 1 use per customer
- Expiry: 7 days after trial end date (urgency)

---

## 4. Annual BOGO Promotion

For users who choose annual billing, TradeMind offers a second year free.

### Terms

| Detail | Value |
|---|---|
| Offer | Buy 1 year, get 1 year free |
| Applies to | All three annual plans |
| Effective monthly cost | TurboCore: ~$10.38/mo over 2 years |
| Effective monthly cost | Pro: ~$16.63/mo over 2 years |
| Effective monthly cost | Bundle: ~$22.88/mo over 2 years |
| Trial credit stacks | Yes — $15 off first payment |
| Promo code | `BOGO2026` |

### Setup

- Create `BOGO2026` promo code: 100% off the second year (applied as 12 months free after year 1)
- Since Stripe does not natively support BOGO subscriptions, implement as: user pays annual price, receives a coupon for 12 months free applied to renewal, OR create a 2-year plan priced at the 1-year rate
- Engineering note: simplest implementation is a **24-month plan** priced identically to the 12-month plan in Stripe. Label it "2 Years — BOGO Offer" and make it accessible only via the /upgrade page, not the main pricing page.

---

## 5. Monthly Loyalty Credits

To build a 10-month retention floor on monthly subscribers.

### Structure

- 1 credit = $0.10 (standardized across the entire platform)
- Monthly subscribers receive 10 credits ($1.00) per month for 10 consecutive months
- Total value returned: $10 over 10 months
- Credits expire 90 days after issuance if unused
- Credits apply at checkout against any TradeMind subscription renewal or upgrade

### Credit Ledger (DB)

```sql
CREATE TABLE user_credits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  amount INTEGER NOT NULL,           -- in cents (10 = $0.10)
  source VARCHAR(50) NOT NULL,       -- 'loyalty', 'referral', 'trial_bonus'
  issued_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP,              -- NOW() + 90 days
  redeemed_at TIMESTAMP,
  redeemed_against VARCHAR(100)      -- invoice_id or subscription_id
);
```

### Monthly Credit Cron Job

```python
# runs 1st of each month on EC2
def issue_loyalty_credits():
    eligible = db.query("""
        SELECT user_id, months_subscribed
        FROM subscriptions
        WHERE billing_source = 'stripe'
        AND status = 'active'
        AND plan_type = 'monthly'
        AND months_subscribed <= 10
    """)
    for user in eligible:
        db.insert('user_credits', {
            'user_id': user.user_id,
            'amount': 100,  # 10 credits = $1.00 in cents
            'source': 'loyalty',
            'expires_at': now() + timedelta(days=90)
        })
```

---

## 6. Referral System (Replanned)

### Credit Values by Conversion Type

| Referral converts to | Referrer gets | New user gets |
|---|---|---|
| Trial only ($15 Whop) | 25 credits ($2.50) | 25 credits ($2.50) |
| Monthly plan (any tier) | 50 credits ($5.00) | 50 credits ($5.00) |
| Annual plan (any tier) | 150 credits ($15.00) | 100 credits ($10.00) |

### Why Tiered

Flat credits for any referral reward low-intent traffic. Tiered credits train referrers — both users and Whop affiliates — to bring in buyers who commit to annual plans. The annual referrer earning $15 in credits also creates a secondary retention incentive: they want to stay subscribed long enough to use those credits.

### Referral Code Mechanics

- Each user gets a unique referral code on account creation (e.g., `TM-ERIC2026`)
- Referral codes work on both Whop and trademind.bot checkout flows
- Referral tracking writes to `referral_events` table with plan type at conversion
- Credits issued immediately on successful payment (not on signup)
- Both sides notified via in-app notification + email

### Referral Events Table

```sql
CREATE TABLE referral_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  referrer_id UUID REFERENCES users(id),
  referred_id UUID REFERENCES users(id),
  referral_code VARCHAR(20),
  converted_plan VARCHAR(50),        -- 'trial', 'monthly', 'annual'
  converted_at TIMESTAMP,
  referrer_credit INTEGER,           -- cents
  referred_credit INTEGER,           -- cents
  billing_source VARCHAR(20)         -- 'stripe' or 'whop'
);
```

---

## 7. Whop Affiliate Program (External Creators)

Separate from the user referral system. Whop affiliates are creators and influencers, not existing members.

### Commission Structure

| Product | Affiliate payout | Whop platform cap |
|---|---|---|
| $15 Trial | $13.50 (90%) | 90% max on Whop |
| Monthly subscription | 30% recurring | Whop default |
| Annual plan | 30% of annual | Whop default |

### Affiliate Portal Instructions (paste into Whop affiliate instructions field)

```
Welcome to the TradeMind Affiliate Program

Earn $13.50 per trial signup — that is 90% commission on a $15 product.

What to promote:
- TradeMind is an AI trading signal platform built for Gen Z investors
- TurboCore ML engine — backtested at 27.8% CAGR on TQQQ
- $15 gets 30 full days of live signals, and the $15 comes back as credit if they subscribe
- No AUM fees. Keep 100% of your gains.

Content that converts:
- TikTok/Reels: "I let an AI trade my account for 30 days" 
- Show the actual signal dashboard or a real signal alert
- Honest reviews work — our signal history is public, use it

Rules:
- Always disclose the affiliate relationship (#ad or "paid partnership")
- Do not guarantee specific returns or profit amounts
- Do not run paid ads without written approval from TradeMind
- Do not impersonate TradeMind or use the logo outside the provided kit

Questions: DM us on Whop or email partners@trademind.bot
```

### Whop Dashboard Config

| Setting | Value |
|---|---|
| Global affiliate rate | 90% |
| Member affiliate rate | 50% |
| Trial product price | $15 |
| Auto-expire | 30 days |
| Product name | TradeMind 30-Day Trial |

---

## 8. The Complete Funnel Map

```
[DISCOVERY]
TikTok / Instagram / Whop Discover / Google
         ↓
[ENTRY POINT — WHOP]
whop.com/trademindbot — $15 / 30-day trial
Affiliate earns $13.50 at this step
         ↓
[TRIAL EXPERIENCE — 30 DAYS]
TurboCore signals delivered daily
In-app onboarding, signal history, performance dashboard
         ↓ Day 28 DM fires
[CONVERSION PAGE]
trademind.bot/upgrade
$15 trial credit pre-applied to all three plans
         ↓
    ┌────────────────────────────────────────────────────┐
    │  MONTHLY                                           │
    │  TurboCore  $29 → $14 first month (credit applied) │
    │  Pro        $49 → $34 first month                  │
    │  Bundle     $69 → $54 first month                  │
    │  + 10 credits/mo for 10 months ($10 back total)    │
    │  + referral earns 50 credits per monthly convert   │
    └────────────────────────────────────────────────────┘
         OR
    ┌────────────────────────────────────────────────────┐
    │  ANNUAL BOGO                                       │
    │  TurboCore  $249 → $234 (credit applied) + yr 2    │
    │  Pro        $399 → $384 + yr 2 free                │
    │  Bundle     $549 → $534 + yr 2 free                │
    │  + referral earns 150 credits per annual convert   │
    └────────────────────────────────────────────────────┘
         ↓
[RETENTION LOOP]
Monthly: 10 credits/mo × 10 months keeps user through month 10
Month 10: Annual renewal prompt — BOGO offer surfaced again
Annual: BOGO means user is locked in for 2 years minimum
```

---

## 9. trademind.bot/upgrade Page Spec

This is the single most important new page to build. It is where every trial conversion happens.

### Required Elements

1. **Hero**: "Your trial is ending. Your $15 isn't gone." — with countdown timer to trial expiry
2. **Three plan cards** mirroring the existing pricing page design, with $15 credit shown pre-applied in green on each
3. **Annual toggle** showing BOGO badge prominently
4. **Comparison table** (see below)
5. **Social proof**: 2-3 member testimonials + signal performance stats
6. **FAQ**: "What happens to my trial data?", "Can I cancel anytime?", "What is the BOGO offer?"

### Plan Comparison on /upgrade

| | TurboCore | TurboCore Pro | Both Bundle |
|---|---|---|---|
| Monthly (after credit) | $14 first mo, then $29 | $34 first mo, then $49 | $54 first mo, then $69 |
| Annual (after credit) | $234/yr + yr 2 free | $384/yr + yr 2 free | $534/yr + yr 2 free |
| TQQQ Core Signal | Yes | Yes | Yes |
| Enhanced ML Regime | No | Yes | Yes |
| VIX Positioning | No | Yes | Yes |
| Early Signal Access | No | Yes | Yes |
| TurboBounce Alpha | No | No | Yes |
| Portfolio Allocation | No | No | Yes |
| Founder Office Hours | No | No | Yes |

### Engineering Notes for /upgrade

- Page receives `?user=<user_id>` param from Whop expiry webhook
- Loads user's trial start date from DB and shows countdown
- Pre-fills promo code `TRIALBACK15` into Stripe checkout session
- If user arrived via referral, referral credit also shown
- Mobile-first layout — most trial users will click from the Whop DM on their phone

---

## 10. Automation Sequences

### Sequence 1: Trial Onboarding (Whop)

| Day | Message |
|---|---|
| Day 0 | "Welcome to TradeMind! Your first signal drops tomorrow at 9 AM ET. Here's how to read it: [link to guide]" |
| Day 3 | "You've seen 3 signals. Here's how TurboCore decided each one: [signal explanation]" |
| Day 14 | "Halfway through your trial. Here's your performance summary so far: [link to dashboard]" |
| Day 28 | "Trial ends in 2 days. Your $15 comes back as credit the moment you subscribe. Use TRIALBACK15: trademind.bot/upgrade" |
| Day 30 | "Your trial just ended. Your credit is waiting — it expires in 7 days: trademind.bot/upgrade" |

### Sequence 2: Monthly Subscriber Retention

| Trigger | Message |
|---|---|
| Month 1 complete | "10 credits added to your account ($1.00 toward next month). 9 months of credits remaining." |
| Month 5 complete | "Halfway through your loyalty credits. You've earned $5 back so far. Consider going annual — BOGO is still available." |
| Month 10 complete | "Final loyalty credit issued. You've earned $10 back. Ready to lock in 2 years for the price of 1? [annual BOGO link]" |

### Sequence 3: Annual Renewal (Month 11)

- Send at month 11 of annual plan: "Your plan renews next month. Want to lock in another year free? Upgrade to the BOGO 2-year plan before renewal and pay nothing for year 2."

---

## 11. Database Changes Required

All changes are additive — no existing tables modified.

```sql
-- Standardize credit value
-- 1 credit = $0.10 = 10 cents stored as INTEGER

ALTER TABLE users ADD COLUMN IF NOT EXISTS whop_user_id VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_source VARCHAR(20) DEFAULT 'stripe';
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'privy';
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) UNIQUE;

-- New tables
CREATE TABLE user_credits ( ... );         -- see Section 5
CREATE TABLE referral_events ( ... );      -- see Section 6
CREATE TABLE trial_conversions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  trial_source VARCHAR(20),               -- 'whop' or 'stripe'
  trial_started_at TIMESTAMP,
  trial_ended_at TIMESTAMP,
  converted BOOLEAN DEFAULT FALSE,
  converted_plan VARCHAR(50),
  converted_at TIMESTAMP,
  promo_code_used VARCHAR(30)
);
```

---

## 12. Whop Webhook Handler

Add to existing EC2 API server. Handles all Whop membership lifecycle events.

```python
@app.route('/webhooks/whop', methods=['POST'])
def whop_webhook():
    event = request.json
    event_type = event.get('action')
    membership = event.get('data', {})

    if event_type == 'membership.went_valid':
        user = upsert_user(
            whop_user_id=membership['user_id'],
            billing_source='whop',
            plan_id=membership['plan_id']
        )
        issue_credits(user.id, 25, source='trial_signup')
        send_onboarding_day0(user)

    elif event_type == 'membership.went_invalid':
        deactivate_access(whop_user_id=membership['user_id'])
        schedule_expiry_dm(membership['user_id'], days=2)

    elif event_type == 'membership.renewed':
        log_renewal(membership['user_id'])

    return {'status': 'ok'}, 200
```

---

## 13. Phase Rollout

### Phase 0 — Whop Config (No code, this week)

- [ ] Update trial product price: $5 → $15
- [ ] Change auto-expire: 7 days → 30 days
- [ ] Rename product: "TradeMind 30-Day Trial"
- [ ] Set global affiliate rate: 90%
- [ ] Set member affiliate rate: 50%
- [ ] Paste affiliate instructions into portal
- [ ] Create promo code TRIALBACK15 ($15 off, 1 use, 7-day expiry after trial)
- [ ] Remove free access option from trial product
- [ ] Set affiliate portal to public

### Phase 1 — Backend (Antigravity sprint 1, ~1 week)

- [ ] Add DB columns: whop_user_id, billing_source, auth_provider, referral_code
- [ ] Create user_credits table
- [ ] Create referral_events table
- [ ] Create trial_conversions table
- [ ] Build Whop webhook handler (4 events)
- [ ] Build credit issuance functions (loyalty, referral, trial)
- [ ] Build referral code generator (runs on user creation)
- [ ] Add monthly loyalty credit cron job to EC2 scheduler

### Phase 2 — trademind.bot/upgrade Page (Antigravity sprint 2, ~1 week)

- [ ] Build /upgrade route with plan cards
- [ ] Show $15 trial credit pre-applied on all plans
- [ ] Annual BOGO badge on annual toggle
- [ ] Countdown timer pulling from trial_conversions table
- [ ] Mobile-first layout
- [ ] Pre-fill TRIALBACK15 into Stripe checkout session
- [ ] Create BOGO 24-month plans in Stripe (3 plans: one per tier)

### Phase 3 — Automation (Antigravity sprint 3, ~3 days)

- [ ] Build 5-message trial onboarding sequence
- [ ] Build monthly loyalty notification (month 1, 5, 10)
- [ ] Build annual renewal prompt (month 11)
- [ ] Day 28 + day 30 expiry DM via Whop API

### Phase 4 — Referral UI (Antigravity sprint 4, ~1 week)

- [ ] /account/referrals page showing unique code, stats, credit balance
- [ ] Credit balance shown in nav/dashboard header
- [ ] Referral link sharing buttons (copy, Twitter, WhatsApp)
- [ ] Credit redemption at Stripe checkout
- [ ] Referrer notification on conversion

---

## 14. Revenue Model Impact

### Before (current state)
- $354 MRR, ~120 users, Stripe only, no trial funnel, no affiliate channel

### After full implementation

| Scenario | Monthly signups | Trial → paid conversion | MRR impact |
|---|---|---|---|
| Conservative (10% conversion) | 50 trials/mo | 5 paid | +$145–$345/mo |
| Base (20% conversion) | 100 trials/mo | 20 paid | +$580–$1,380/mo |
| Optimistic (30% + affiliate traffic) | 200 trials/mo | 60 paid | +$1,740–$4,140/mo |

Annual BOGO converts 1-month cash collection into 2-year LTV anchors. A single user who buys the Both Bundle annual BOGO generates $549 upfront and $549 at year 2 renewal = $1,098 LTV from one conversion event.

---

## 15. Key Metrics to Track

| Metric | Target | Measured in |
|---|---|---|
| Trial → paid conversion rate | > 20% | trial_conversions table |
| Affiliate trial signups / month | > 30 | Whop affiliate dashboard |
| Average affiliate payout / month | > $200 | Whop affiliate dashboard |
| Monthly credit redemption rate | > 40% | user_credits table |
| Referral signup rate | > 15% of new users | referral_events table |
| Month 5 retention (monthly) | > 60% | subscriptions table |
| Annual BOGO uptake | > 25% of converting trials | Stripe dashboard |

---

## 16. Single Source of Truth for Pricing

All pricing displayed across trademind.bot, the /upgrade page, and Whop must match exactly. Any pricing change requires updates in three places:

1. trademind.bot/pricing (existing page — Antigravity updates)
2. trademind.bot/upgrade (new page — Antigravity builds)
3. Whop product page description (manual update in Whop dashboard)

Recommend storing pricing config in a single `pricing_config.ts` constants file imported by all frontend components so a one-line change updates all pages simultaneously.
