# TradeMind × Whop — $15 Trial + Native Migration Plan

**For:** Antigravity (Development Team)
**Revision:** v2 — Trial Funnel Architecture
**Date:** April 2026

---

## 1. The Strategy in Plain English

Whop is not TradeMind's permanent home. It is the **acquisition funnel**. A user discovers TradeMind on TikTok, pays $15 for a 30-day trial on Whop, gets 30 days of full signals and community access, and then at day 30 they migrate to a full paid subscription on **trademind.bot** (native Vercel + Stripe stack).

```
[TikTok / FinTok]
       │  "Try TradeMind for $15 — 30 days"
       ▼
[Whop Listing — $15 one-time, 30-day access]
       │  membership.activated webhook fires
       ▼
[TradeMind DB — user pre-provisioned, email captured]
       │  30 days of signals, education, community on Whop
       ▼
[Day 25 — "Trial ends in 5 days" warning DM + email]
       │
       ▼
[Day 30 — membership.deactivated webhook fires]
       │  Magic link email sent to trademind.bot
       ▼
[User subscribes on trademind.bot — Core / Pro / Bundle]
       │  Native Stripe subscription, full platform access
       ▼
[Whop access terminates — user lives entirely on trademind.bot]
```

**Why this works:** Whop handles the cold acquisition problem (trusted marketplace, TikTok-native Gen Z audience, no trust barrier) while trademind.bot retains the long-term subscriber relationship and full LTV.

---

## 2. Architecture Overview

### Two Distinct Phases

| Phase | Duration | Platform | Payment | What user gets |
|-------|----------|----------|---------|----------------|
| **Trial** | 30 days | Whop | $15 one-time | Signals, community, courses, morning brief via Whop apps |
| **Subscription** | Ongoing | trademind.bot | $29–$69/mo via Stripe | Full platform, AI tools, all TradeMind features |

### Data Flow

```
Whop webhook → /api/whop/webhook (Vercel)
                    │
                    ├── INSERT into whop_trials table (email, user_id, trial_end)
                    ├── INSERT into users table (pre-provision account)
                    ├── Send welcome DM via Whop SDK
                    └── Send welcome email via Resend (existing email stack)
```

---

## 3. Whop Dashboard Setup

### 3.1 Create the Trial Product in Whop

1. Log into Whop dashboard → **Create Product**
2. **Pricing:** Set as a one-time payment of **$15**
3. **Access duration:** 30 days (set `renewal_period` = 30 days, `cancel_at_period_end` = true)
4. **Product name:** "TradeMind — 30-Day Trial"
5. **Description:** "Daily AI signals, morning briefings, 7-year backtested TurboCore strategy, and community access. After 30 days, continue on trademind.bot."
6. **After trial note:** Add a prominent note in the product description that continuation happens at trademind.bot

> **Important:** Set `cancel_at_period_end: true` on the Whop plan so it automatically deactivates at day 30 without charging again. This is what fires the `membership.deactivated` webhook.

### 3.2 New Environment Variables

Add to `.env.local` and Vercel:

```env
# Existing from v1 plan — keep these
WHOP_API_KEY=your_company_api_key_here
WHOP_WEBHOOK_SECRET=your_webhook_secret_here
WHOP_COMPANY_ID=biz_xxxxxxxxxxxxxx
WHOP_ANNOUNCEMENTS_CHANNEL_ID=channel_xxxxxxxxxx
WHOP_CHAT_BOT_CHANNEL_ID=channel_xxxxxxxxxx

# New — trial product specifically
WHOP_TRIAL_EXPERIENCE_ID=exp_xxxxxxxxxxxxxx     # The $15/30-day trial experience
WHOP_TRIAL_PLAN_ID=plan_xxxxxxxxxxxxxx          # The plan ID for the $15 product

# trademind.bot upgrade URLs
TRADEMIND_UPGRADE_URL=https://trademind.bot/upgrade
TRADEMIND_MAGIC_LINK_SECRET=your_jwt_secret_32_chars_min  # For magic link generation

# Cron auth (already exists — keep)
CRON_SECRET=your_cron_secret_here
```

---

## 4. Database Schema

Add these tables. The `users` table likely already exists — only add the new columns if they don't already exist.

```sql
-- Trial tracking table — core of the migration flow
CREATE TABLE whop_trials (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  whop_user_id    VARCHAR(100) NOT NULL UNIQUE,  -- user_xxxxxxxxxxxxx from Whop
  whop_member_id  VARCHAR(100) NOT NULL,          -- mber_xxxxxxxxxxxxx
  whop_membership_id VARCHAR(100) NOT NULL,       -- mem_xxxxxxxxxxxxxx
  email           VARCHAR(255) NOT NULL,
  name            VARCHAR(255),
  username        VARCHAR(100),
  trial_started_at TIMESTAMPTZ NOT NULL,
  trial_ends_at   TIMESTAMPTZ NOT NULL,           -- renewal_period_end from webhook
  warning_sent_at TIMESTAMPTZ,                    -- Day 25 DM/email sent
  migration_sent_at TIMESTAMPTZ,                  -- Day 30 magic link sent
  migrated        BOOLEAN DEFAULT FALSE,           -- True once they subscribe on trademind.bot
  migrated_at     TIMESTAMPTZ,
  migrated_tier   VARCHAR(20),                    -- 'core' | 'pro' | 'bundle'
  cancelled_early BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Add Whop trial columns to existing users table (if not already present)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS whop_trial_id UUID REFERENCES whop_trials(id),
  ADD COLUMN IF NOT EXISTS trial_active  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS source        VARCHAR(50) DEFAULT 'direct'; 
  -- source = 'whop_trial' | 'direct' | 'referral'

-- Magic links table — secure one-time migration tokens
CREATE TABLE migration_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token      VARCHAR(255) NOT NULL UNIQUE,   -- JWT or random UUID
  user_email VARCHAR(255) NOT NULL,
  whop_user_id VARCHAR(100) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,           -- 7 days from issue
  used       BOOLEAN DEFAULT FALSE,
  used_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_migration_tokens_token ON migration_tokens (token) WHERE used = FALSE;
CREATE INDEX idx_whop_trials_ends_at ON whop_trials (trial_ends_at, warning_sent_at, migration_sent_at);
```

---

## 5. Webhook Handler — Full Rewrite

Replace the previous webhook handler entirely. This is the brain of the whole flow.

```typescript
// src/app/api/whop/webhook/route.ts
import { NextRequest, NextResponse } from "next/server";
import { waitUntil } from "@vercel/functions";
import { whop } from "@/lib/whop";
import { db } from "@/lib/db";
import { sendEmail } from "@/lib/resend";          // existing email utility
import { generateMagrationToken } from "@/lib/migration";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const bodyText = await request.text();
  const headers = Object.fromEntries(request.headers);

  // NEVER skip signature validation
  const webhookData = whop.webhooks.unwrap(bodyText, { headers });

  switch (webhookData.type) {
    case "membership.activated":
      waitUntil(handleTrialStarted(webhookData.data));
      break;
    case "membership.deactivated":
      waitUntil(handleTrialEnded(webhookData.data));
      break;
    case "payment.succeeded":
      waitUntil(handlePaymentSucceeded(webhookData.data));
      break;
  }

  // Always return 200 immediately — Whop retries on any non-2xx
  return new NextResponse("OK", { status: 200 });
}
```

### 5.1 Trial Started Handler (`membership.activated`)

This fires the moment someone pays $15 on Whop. The email is included directly in the webhook payload at `data.user.email`.[cite:web:138]

```typescript
async function handleTrialStarted(membership: {
  id: string;
  status: string;
  joined_at: string;
  renewal_period_end: string;
  user: {
    id: string;
    username: string;
    name: string;
    email: string;
  };
  member: { id: string };
}) {
  const { user, member } = membership;
  const trialEndsAt = new Date(membership.renewal_period_end);
  const trialStartedAt = new Date(membership.joined_at);

  // 1. Store trial record in DB
  const trial = await db.whopTrials.upsert({
    where: { whop_user_id: user.id },
    create: {
      whop_user_id: user.id,
      whop_member_id: member.id,
      whop_membership_id: membership.id,
      email: user.email,
      name: user.name,
      username: user.username,
      trial_started_at: trialStartedAt,
      trial_ends_at: trialEndsAt,
    },
    update: {
      trial_ends_at: trialEndsAt,
      whop_membership_id: membership.id,
    },
  });

  // 2. Pre-provision account on trademind.bot
  //    This creates the account NOW so the migration at day 30 is frictionless
  await db.users.upsert({
    where: { email: user.email },
    create: {
      email: user.email,
      name: user.name,
      source: "whop_trial",
      trial_active: true,
      trial_ends_at: trialEndsAt,
      whop_trial_id: trial.id,
      // No password set yet — they'll set it via magic link at day 30
    },
    update: {
      trial_active: true,
      trial_ends_at: trialEndsAt,
      whop_trial_id: trial.id,
    },
  });

  // 3. Send welcome DM via Whop chat
  await whop.messages.createDm({
    user_id: user.id,
    content: buildWelcomeDm(user.name, trialEndsAt),
  });

  // 4. Send welcome email via existing email stack (Resend)
  await sendEmail({
    to: user.email,
    subject: "Welcome to TradeMind — your 30-day trial starts now",
    template: "trial-welcome",
    data: {
      name: user.name,
      trial_ends: trialEndsAt.toLocaleDateString("en-US", {
        month: "long", day: "numeric", year: "numeric",
      }),
      upgrade_url: process.env.TRADEMIND_UPGRADE_URL,
    },
  });
}

function buildWelcomeDm(name: string, trialEndsAt: Date): string {
  const endDate = trialEndsAt.toLocaleDateString("en-US", {
    month: "long", day: "numeric",
  });
  return `
👋 **Welcome to TradeMind, ${name.split(" ")[0]}.**

Your 30-day trial runs until **${endDate}**. Here is what to do right now:

**1. Turn on push notifications** for the Whop app — that is how the 3 PM TurboCore signal reaches you every trading day.

**2. Check #morning-brief** every day at 8:15 AM ET before market open.

**3. When the 3 PM signal drops** — you have until market close to execute. Takes under 2 minutes in any brokerage.

**4. Start TurboCore 101** — the course in the Courses tab walks you through the entire strategy in under 30 minutes.

---
On **${endDate}**, your Whop access ends and you will get a link to continue on trademind.bot where the full platform (AI tools, options builder, auto-execution) lives.

Any questions? Reply here or ask in #general-chat.

_Educational analysis only. Not personalized investment advice._
  `.trim();
}
```

### 5.2 Trial Ended Handler (`membership.deactivated`)

This fires at day 30 when Whop automatically cancels the trial. This is the migration trigger.

```typescript
async function handleTrialEnded(membership: {
  id: string;
  user: { id: string; email: string; name: string };
}) {
  // 1. Look up the trial record
  const trial = await db.whopTrials.findUnique({
    where: { whop_user_id: membership.user.id },
  });

  if (!trial) {
    console.error(`No trial record found for Whop user ${membership.user.id}`);
    return;
  }

  // 2. Mark trial as ended in DB
  await db.whopTrials.update({
    where: { id: trial.id },
    data: { cancelled_early: new Date() < trial.trial_ends_at },
  });

  await db.users.update({
    where: { email: trial.email },
    data: { trial_active: false },
  });

  // 3. Generate a magic link for trademind.bot
  //    This lets the user log into their pre-provisioned account without setting a password
  const migrationToken = await generateMigrationToken({
    email: trial.email,
    whop_user_id: membership.user.id,
    trial_id: trial.id,
  });

  const magicLink = `${process.env.TRADEMIND_UPGRADE_URL}?token=${migrationToken}`;

  // 4. Send migration DM via Whop (they can still read DMs for a few days after deactivation)
  try {
    await whop.messages.createDm({
      user_id: membership.user.id,
      content: buildMigrationDm(membership.user.name, magicLink),
    });
  } catch {
    // DM may fail if user lost access — email is the backup
    console.log("Whop DM failed, email is the primary channel");
  }

  // 5. Send migration email — this is the primary migration channel
  await sendEmail({
    to: trial.email,
    subject: "Your TradeMind trial has ended — continue here",
    template: "trial-migration",
    data: {
      name: membership.user.name,
      magic_link: magicLink,
      core_price: "$29/mo",
      pro_price: "$49/mo",
      bundle_price: "$69/mo",
    },
  });

  // 6. Update trial record
  await db.whopTrials.update({
    where: { id: trial.id },
    data: { migration_sent_at: new Date() },
  });
}

function buildMigrationDm(name: string, magicLink: string): string {
  return `
⏰ **Your TradeMind 30-day trial has ended.**

Thanks for being part of the community, ${name.split(" ")[0]}.

Your account on **trademind.bot** is already set up with your trial history. Click the link below to continue — no new signup required:

👉 ${magicLink}

**Choose your plan:**
• **TurboCore** $29/mo — daily signals, morning brief, 50 AI messages
• **TurboCore Pro** $49/mo — signals + Options Builder + Weekly Debrief
• **Both Bundle** $69/mo — everything unlimited

The link is valid for 7 days.

_Educational analysis only. Not personalized investment advice._
  `.trim();
}
```

---

## 6. Migration Token System

The magic link is a secure JWT that pre-authenticates the user on trademind.bot so they do not need to create a new password. They click the link → land on the upgrade/pricing page → already logged in → one click to subscribe.

### 6.1 Token Generator

```typescript
// src/lib/migration.ts
import jwt from "jsonwebtoken";
import { db } from "@/lib/db";

export async function generateMigrationToken(params: {
  email: string;
  whop_user_id: string;
  trial_id: string;
}): Promise<string> {
  // JWT expires in 7 days
  const token = jwt.sign(
    {
      email: params.email,
      whop_user_id: params.whop_user_id,
      trial_id: params.trial_id,
      purpose: "trial_migration",
    },
    process.env.TRADEMIND_MAGIC_LINK_SECRET!,
    { expiresIn: "7d" }
  );

  // Store in DB so we can mark it as used after redemption
  await db.migrationTokens.create({
    data: {
      token,
      user_email: params.email,
      whop_user_id: params.whop_user_id,
      expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
    },
  });

  return token;
}
```

### 6.2 Magic Link Redemption Route

This is the landing page for the magic link. It authenticates the user and redirects to the upgrade/pricing page.

```typescript
// src/app/api/auth/migrate/route.ts
import { NextRequest, NextResponse } from "next/server";
import jwt from "jsonwebtoken";
import { db } from "@/lib/db";
import { createSession } from "@/lib/auth";  // existing auth utility

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = request.nextUrl.searchParams.get("token");

  if (!token) {
    return NextResponse.redirect(new URL("/login?error=invalid_token", request.url));
  }

  try {
    // Verify JWT signature
    const payload = jwt.verify(token, process.env.TRADEMIND_MAGIC_LINK_SECRET!) as {
      email: string;
      whop_user_id: string;
      trial_id: string;
      purpose: string;
    };

    if (payload.purpose !== "trial_migration") {
      throw new Error("Invalid token purpose");
    }

    // Check token has not been used
    const tokenRecord = await db.migrationTokens.findUnique({
      where: { token, used: false },
    });

    if (!tokenRecord) {
      return NextResponse.redirect(
        new URL("/login?error=token_expired", request.url)
      );
    }

    // Mark token as used
    await db.migrationTokens.update({
      where: { token },
      data: { used: true, used_at: new Date() },
    });

    // Retrieve or create the user account
    const user = await db.users.findUnique({ where: { email: payload.email } });

    if (!user) {
      return NextResponse.redirect(new URL("/signup?email=" + payload.email, request.url));
    }

    // Create an authenticated session (using existing auth system)
    const session = await createSession(user.id);

    // Redirect to the upgrade page — user is now logged in
    const response = NextResponse.redirect(
      new URL("/upgrade?from=trial&ref=whop", request.url)
    );

    // Set session cookie
    response.cookies.set("session", session.token, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 days
    });

    return response;
  } catch (err) {
    console.error("Migration token error:", err);
    return NextResponse.redirect(
      new URL("/login?error=invalid_token", request.url)
    );
  }
}
```

---

## 7. Day 25 Warning Cron Job

Five days before the trial ends, send a heads-up DM and email so the user is not surprised.

```typescript
// src/app/api/cron/trial-warning/route.ts
import { NextRequest, NextResponse } from "next/server";
import { whop } from "@/lib/whop";
import { sendEmail } from "@/lib/resend";
import { db } from "@/lib/db";

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (request.headers.get("authorization") !== `Bearer ${process.env.CRON_SECRET}`) {
    return new NextResponse("Unauthorized", { status: 401 });
  }

  // Find all trials ending in the next 5-6 days that haven't been warned yet
  const warningWindowStart = new Date();
  const warningWindowEnd = new Date(Date.now() + 6 * 24 * 60 * 60 * 1000);

  const trialsToWarn = await db.whopTrials.findMany({
    where: {
      trial_ends_at: {
        gte: warningWindowStart,
        lte: warningWindowEnd,
      },
      warning_sent_at: null,
      migrated: false,
    },
  });

  let warned = 0;

  for (const trial of trialsToWarn) {
    const daysLeft = Math.ceil(
      (trial.trial_ends_at.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );

    const endDate = trial.trial_ends_at.toLocaleDateString("en-US", {
      month: "long", day: "numeric",
    });

    // Send Whop DM
    try {
      await whop.messages.createDm({
        user_id: trial.whop_user_id,
        content: `
⏰ **Your TradeMind trial ends in ${daysLeft} days (${endDate}).**

You've been getting daily TurboCore signals and the morning brief. When your trial ends, access moves to **trademind.bot** where the full platform lives.

On ${endDate} you'll receive a link directly to your account — no new signup needed.

**Plans starting at $29/mo.** Pick the one that fits: trademind.bot/upgrade

_Keep following the signals until then._
        `.trim(),
      });
    } catch {
      console.log(`Whop DM failed for ${trial.whop_user_id}`);
    }

    // Send warning email
    await sendEmail({
      to: trial.email,
      subject: `Your TradeMind trial ends in ${daysLeft} days`,
      template: "trial-warning",
      data: {
        name: trial.name,
        days_left: daysLeft,
        end_date: endDate,
        upgrade_url: process.env.TRADEMIND_UPGRADE_URL,
      },
    });

    await db.whopTrials.update({
      where: { id: trial.id },
      data: { warning_sent_at: new Date() },
    });

    warned++;
  }

  return NextResponse.json({ warned });
}
```

Add to `vercel.json`:
```json
{ "path": "/api/cron/trial-warning", "schedule": "0 14 * * *" }
```
_(Runs daily at 9 AM ET — catches trials ending in 5-6 days)_

---

## 8. Migration Confirmed — Subscription Handler

When the user subscribes on trademind.bot via Stripe, mark the migration as complete.

Add to the existing Stripe webhook handler (`/api/webhooks/stripe/route.ts`):

```typescript
// ADD to existing Stripe checkout.session.completed handler

async function handleSubscriptionCreated(session: {
  customer_email: string;
  metadata: { tier?: string };
}) {
  // Check if this subscriber came from a Whop trial
  const trial = await db.whopTrials.findFirst({
    where: {
      email: session.customer_email,
      migrated: false,
    },
  });

  if (trial) {
    await db.whopTrials.update({
      where: { id: trial.id },
      data: {
        migrated: true,
        migrated_at: new Date(),
        migrated_tier: session.metadata?.tier ?? "core",
      },
    });

    // Update user record
    await db.users.update({
      where: { email: session.customer_email },
      data: {
        source: "whop_trial_converted",
        trial_active: false,
      },
    });

    // Optional: send a Whop thank-you DM (they may still have the app)
    try {
      await whop.messages.createDm({
        user_id: trial.whop_user_id,
        content: `✅ **You're all set on trademind.bot.** Welcome to the full platform. Signals continue daily — see you there.`,
      });
    } catch { /* ignore if access expired */ }
  }
}
```

---

## 9. Upgrade Page on trademind.bot

The upgrade page needs to handle the `?from=trial&ref=whop` query param and show a trial-specific message.

```typescript
// src/app/upgrade/page.tsx — add to existing page

// If user came from a Whop trial migration, show a personalized header
const fromTrial = searchParams.get("from") === "trial";
const refWhop = searchParams.get("ref") === "whop";

// Conditional UI:
if (fromTrial && refWhop) {
  return (
    <div className="trial-migration-banner">
      <h1>Welcome back — your account is ready.</h1>
      <p>
        Your 30-day trial history is saved. Pick a plan below to keep
        your daily TurboCore signals running without interruption.
      </p>
      <p className="badge">30-day trial member</p>
    </div>
  );
}
```

---

## 10. Full Updated vercel.json

```json
{
  "crons": [
    { "path": "/api/cron/morning-brief",  "schedule": "15 13 * * 1-5" },
    { "path": "/api/cron/signal",         "schedule": "0 20 * * 1-5" },
    { "path": "/api/cron/weekly-debrief", "schedule": "0 23 * * 0" },
    { "path": "/api/cron/trial-warning",  "schedule": "0 14 * * *" },
    { "path": "/api/cron/winback",        "schedule": "0 15 * * *" }
  ]
}
```

---

## 11. Complete File Map

### New Files to Create

| File | Purpose |
|------|---------|
| `src/lib/whop.ts` | Whop SDK client singleton |
| `src/lib/whop-notifications.ts` | Push notification helpers |
| `src/lib/migration.ts` | JWT magic link generator |
| `src/app/api/whop/webhook/route.ts` | Webhook handler (trial start + end) |
| `src/app/api/whop/chat-bot/route.ts` | Chat bot command responder |
| `src/app/api/auth/migrate/route.ts` | Magic link redemption + session creation |
| `src/app/api/cron/trial-warning/route.ts` | Day 25 warning cron |
| `scripts/get-whop-channels.ts` | One-time: discover channel IDs |
| `scripts/seed-whop-courses.ts` | One-time: create courses via API |
| `prisma/migrations/whop_trial_tables.sql` | DB migration for new tables |

### Files to Modify

| File | Change |
|------|--------|
| `src/app/api/cron/morning-brief/route.ts` | Add Whop announcement post |
| `src/app/api/cron/signal/route.ts` | Add Whop announcement + push notification |
| `src/app/api/webhooks/stripe/route.ts` | Add migration confirmation on subscribe |
| `src/app/upgrade/page.tsx` | Add trial migration UI state |
| `vercel.json` | Add trial-warning cron |
| `.env.local` + Vercel env vars | Add all `WHOP_*` and `TRADEMIND_*` vars |

---

## 12. Conversion Funnel Metrics to Track

Add these to the TradeMind analytics dashboard so performance can be measured:

```sql
-- Daily trial conversion report
SELECT
  DATE_TRUNC('week', created_at) AS week,
  COUNT(*) AS trials_started,
  COUNT(*) FILTER (WHERE migrated = TRUE) AS converted,
  ROUND(100.0 * COUNT(*) FILTER (WHERE migrated = TRUE) / COUNT(*), 1) AS conversion_rate,
  COUNT(*) FILTER (WHERE cancelled_early = TRUE) AS early_cancels
FROM whop_trials
GROUP BY 1
ORDER BY 1 DESC;
```

**Target benchmarks:**
- Trial-to-paid conversion: aim for 25-35% (industry average for $15 trial → $29+ subscription is ~20%)
- Day 25 warning email open rate: aim for 45%+ (transactional emails open high)
- Magic link click rate from migration email: aim for 30%+
- Time from magic link click to subscription completion: under 3 minutes (frictionless goal)

---

## 13. Testing Checklist

- [ ] Whop product created with $15 price, 30-day duration, `cancel_at_period_end: true`
- [ ] Webhook endpoint `/api/whop/webhook` registered in Whop dashboard with `membership.activated` and `membership.deactivated` events
- [ ] `membership.activated` fires → trial row created in DB, user pre-provisioned, welcome DM sent, welcome email sent
- [ ] `data.user.email` is captured correctly from the webhook payload (requires `member:email:read` permission in Whop)
- [ ] Day 25 warning cron finds trials in 5-6 day window and sends DM + email
- [ ] `membership.deactivated` fires → migration token generated, magic link DM sent, migration email sent
- [ ] Magic link (`/api/auth/migrate?token=...`) authenticates user and redirects to `/upgrade?from=trial&ref=whop`
- [ ] Upgrade page shows trial migration banner when `?from=trial&ref=whop` params are present
- [ ] Stripe subscription webhook marks `whop_trials.migrated = true`
- [ ] Morning brief and signal cron posts to Whop announcements channel while trial is active
- [ ] Chat bot responds to `!signal`, `!regime`, `!help`, `!plan`, `!backtest`

---

## 14. Key Webhook Permission

The `membership.activated` webhook includes the user's email at `data.user.email` only if the required permissions are granted.[cite:web:140] In the Whop developer dashboard, ensure these permissions are enabled on the webhook:

- `member:basic:read`
- `member:email:read`
- `webhook_receive:memberships`

Without `member:email:read`, the email field will be null and the migration flow will break.

