# TradeMind × Whop API — Engineering Implementation Plan

**For:** Antigravity (Development Team)
**Product:** TradeMind.bot — AI Trading Signals & Education Platform
**Target:** Whop community automation via Whop SDK and Vercel Cron
**Stack alignment:** Next.js 14, TypeScript, Vercel serverless, PostgreSQL, existing TradeMind infrastructure

---

## 1. Overview and Architecture

This document specifies how to extend TradeMind's existing Vercel/Next.js infrastructure to automate four core Whop community apps — Posts (Announcements), Chat, Docs (Content), and Courses — using the Whop SDK and Whop Webhooks.

The goal is a single integration layer sitting between TradeMind's existing daily signal pipeline (Vercel Cron jobs at 8:15 AM and 3:00 PM ET) and the Whop community, so that every signal, morning brief, member join, and educational module is delivered and tracked automatically without any manual admin work.

### High-Level Architecture

```
TradeMind Backend (Vercel)
│
├── Vercel Cron (8:15 AM ET)  ──► Whop Posts App  ──► Morning Brief announcement
├── Vercel Cron (3:00 PM ET)  ──► Whop Posts App  ──► TurboCore Signal announcement
│                              ──► Whop Push Notifications ──► All active members
│
├── Whop Webhook Handler       ──► membership.activated  ──► Automated welcome Chat DM
│   /api/whop/webhook           ──► membership.deactivated ──► Access revocation log
│                               ──► payment.succeeded     ──► Stripe sync (if needed)
│
├── Whop Chat Bot              ──► Respond to signal-related chat commands
│
├── Whop Courses API           ──► Programmatic course and lesson creation
│
└── Whop Docs API              ──► Programmatic playbook content management
```

### Key Principle

TradeMind already runs two Vercel Cron jobs that generate the Morning Brief (8:15 AM) and TurboCore Signal (3:00 PM). This integration **pipes the output of those existing jobs into Whop** rather than building anything new from scratch. The primary work is: install the Whop SDK, add three new API route files, and wire them into the existing cron handlers.

---

## 2. Prerequisites and Credentials

Before writing any code, collect these values from the Whop Developer Dashboard at `https://whop.com/dashboard/developer`.

### Required Environment Variables

Add all of the following to `.env.local` and Vercel project environment variables.

```env
# Whop Company API Key — for your own TradeMind company actions
WHOP_API_KEY=your_company_api_key_here

# Whop App API Key — only needed if building a full Whop App (optional phase 2)
WHOP_APP_API_KEY=your_app_api_key_here

# Whop Webhook Secret — copy from the webhooks table after creating your webhook
WHOP_WEBHOOK_SECRET=your_webhook_secret_here

# Whop Resource IDs — collect these from your Whop dashboard after setup
WHOP_COMPANY_ID=biz_xxxxxxxxxxxxxx
WHOP_FREE_EXPERIENCE_ID=exp_xxxxxxxxxxxxxx       # Free community experience
WHOP_CORE_EXPERIENCE_ID=exp_xxxxxxxxxxxxxx       # TurboCore Core paid experience
WHOP_PRO_EXPERIENCE_ID=exp_xxxxxxxxxxxxxx        # TurboCore Pro paid experience
WHOP_BUNDLE_EXPERIENCE_ID=exp_xxxxxxxxxxxxxx     # Bundle paid experience
WHOP_ANNOUNCEMENTS_CHANNEL_ID=channel_xxxxxxxxxx # From the Posts/Announcements app
WHOP_CHAT_BOT_CHANNEL_ID=channel_xxxxxxxxxx     # General trading floor chat
```

### How to Get Resource IDs

- **Company ID:** Whop Dashboard → Settings → Your company ID starts with `biz_`
- **Experience IDs:** Whop Dashboard → Your whop → each pricing plan corresponds to an experience with an `exp_` ID
- **Channel IDs:** Use the SDK to list channels after the apps are set up (see Section 4.1)

---

## 3. SDK Installation and Client Setup

### 3.1 Install the Whop SDK

```bash
pnpm install @whop/sdk
```

### 3.2 Create the Whop Client Singleton

Create `/src/lib/whop.ts` — a shared client used across all API routes and cron jobs.

```typescript
// src/lib/whop.ts
import { Whop } from "@whop/sdk";

export const whop = new Whop({
  apiKey: process.env.WHOP_API_KEY!,
  webhookKey: process.env.WHOP_WEBHOOK_SECRET
    ? btoa(process.env.WHOP_WEBHOOK_SECRET)
    : undefined,
});

// Helper: experience IDs for all paid tiers
export const EXPERIENCES = {
  free: process.env.WHOP_FREE_EXPERIENCE_ID!,
  core: process.env.WHOP_CORE_EXPERIENCE_ID!,
  pro: process.env.WHOP_PRO_EXPERIENCE_ID!,
  bundle: process.env.WHOP_BUNDLE_EXPERIENCE_ID!,
};

// Helper: all paid experience IDs as an array
export const ALL_PAID_EXPERIENCES = [
  EXPERIENCES.core,
  EXPERIENCES.pro,
  EXPERIENCES.bundle,
];
```

---

## 4. App 1: Posts / Announcements Automation

The Posts app delivers the 8:15 AM Morning Brief and 3:00 PM TurboCore Signal as formal announcements visible to all members. These are created programmatically via the `messages.create` SDK method on the announcements channel.

### 4.1 Discover Channel IDs (Run Once)

Run this script once to log the channel IDs for your Whop community. Save the output as environment variables.

```typescript
// scripts/get-whop-channels.ts
// Run with: npx tsx scripts/get-whop-channels.ts
import { whop } from "@/lib/whop";

async function listChannels() {
  const channels = await whop.channels.list({
    company_id: process.env.WHOP_COMPANY_ID!,
  });
  for await (const channel of channels) {
    console.log(`Channel: ${channel.id} | Name: ${channel.title} | Type: ${channel.channel_type}`);
  }
}

listChannels().catch(console.error);
```

### 4.2 Morning Brief Post (8:15 AM ET)

Extend the existing `src/app/api/cron/morning-brief/route.ts` to post to Whop after generating the AI brief content. Add the Whop post call at the end of the existing handler.

```typescript
// src/app/api/cron/morning-brief/route.ts
// ADD to existing handler — after briefing is generated and stored in DB

import { whop } from "@/lib/whop";

async function postMorningBriefToWhop(brief: {
  regime: "BULL" | "SIDEWAYS" | "BEAR";
  confidence: number;
  bullets: string[];
  date: string;
}) {
  const regimeEmoji = {
    BULL: "🟢",
    SIDEWAYS: "🟡",
    BEAR: "🔴",
  }[brief.regime];

  const content = `
**${regimeEmoji} TurboCore Pre-Market Brief — ${brief.date}**

**Today's Regime:** ${brief.regime} (${brief.confidence}% confidence)

${brief.bullets.map((b, i) => `${i + 1}. ${b}`).join("\n")}

---
_3:00 PM signal with exact allocation coming at market close. Stay disciplined._
`.trim();

  await whop.messages.create({
    channel_id: process.env.WHOP_ANNOUNCEMENTS_CHANNEL_ID!,
    content,
  });
}
```

**Vercel cron config** (already in `vercel.json` — no change needed):
```json
{ "path": "/api/cron/morning-brief", "schedule": "15 13 * * 1-5" }
```
_(13:15 UTC = 8:15 AM ET)_

### 4.3 TurboCore Signal Post (3:00 PM ET)

Add the Whop post to the existing signal delivery handler.

```typescript
// src/app/api/cron/signal/route.ts
// ADD to existing handler — after signal is generated and stored in DB

import { whop } from "@/lib/whop";

async function postSignalToWhop(signal: {
  regime: "BULL" | "SIDEWAYS" | "BEAR";
  confidence: number;
  allocation: { QQQ: number; QLD: number; TQQQ: number; SGOV: number };
  reasoning: string;
  date: string;
}) {
  const regimeEmoji = {
    BULL: "🟢",
    SIDEWAYS: "🟡",
    BEAR: "🔴",
  }[signal.regime];

  const { QQQ, QLD, TQQQ, SGOV } = signal.allocation;

  const content = `
**${regimeEmoji} TURBOCORE SIGNAL — ${signal.date}**
**Regime:** ${signal.regime} | Confidence: ${signal.confidence}%

**Today's Allocation:**
• QQQ: ${QQQ}%
• QLD: ${QLD}%
• TQQQ: ${TQQQ}%
• SGOV: ${SGOV}%

**Why:** ${signal.reasoning}

---
_Execute via any brokerage or one-tap via Tastytrade. Takes under 2 minutes._
_This is educational analysis only. Not personalized investment advice._
`.trim();

  await whop.messages.create({
    channel_id: process.env.WHOP_ANNOUNCEMENTS_CHANNEL_ID!,
    content,
  });

  // Also send a push notification to all paid members
  await postSignalPushNotification(signal);
}

async function postSignalPushNotification(signal: {
  regime: "BULL" | "SIDEWAYS" | "BEAR";
  confidence: number;
  allocation: { TQQQ: number };
}) {
  const regimeEmoji = { BULL: "🟢", SIDEWAYS: "🟡", BEAR: "🔴" }[signal.regime];

  // Send to each paid experience
  const experiences = [
    process.env.WHOP_CORE_EXPERIENCE_ID!,
    process.env.WHOP_PRO_EXPERIENCE_ID!,
    process.env.WHOP_BUNDLE_EXPERIENCE_ID!,
  ];

  await Promise.all(
    experiences.map((experience_id) =>
      whop.notifications.create({
        experience_id,
        title: `${regimeEmoji} TurboCore: ${signal.regime} Signal`,
        subtitle: `${signal.confidence}% confidence`,
        content: `TQQQ: ${signal.allocation.TQQQ}% | Today's full allocation is ready.`,
        rest_path: "/signal",
      })
    )
  );
}
```

**Vercel cron config** (already in `vercel.json` — no change needed):
```json
{ "path": "/api/cron/signal", "schedule": "0 20 * * 1-5" }
```
_(20:00 UTC = 3:00 PM ET)_

---

## 5. App 2: Webhook Handler for Chat Automation

The webhook handler is the core of the Chat automation. It listens for membership events and automatically sends welcome DMs and manages access.

### 5.1 Create the Webhook Endpoint

Create `/src/app/api/whop/webhook/route.ts`. This is a new file.

```typescript
// src/app/api/whop/webhook/route.ts
import { NextRequest, NextResponse } from "next/server";
import { waitUntil } from "@vercel/functions";
import { whop } from "@/lib/whop";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const bodyText = await request.text();
  const headers = Object.fromEntries(request.headers);

  // Validate webhook signature — NEVER skip this in production
  const webhookData = whop.webhooks.unwrap(bodyText, { headers });

  switch (webhookData.type) {
    case "membership.activated":
      waitUntil(handleMembershipActivated(webhookData.data));
      break;
    case "membership.deactivated":
      waitUntil(handleMembershipDeactivated(webhookData.data));
      break;
    case "payment.succeeded":
      waitUntil(handlePaymentSucceeded(webhookData.data));
      break;
  }

  // Always return 200 immediately — Whop retries on non-2xx
  return new NextResponse("OK", { status: 200 });
}
```

### 5.2 Membership Activated — Welcome DM

When a new member subscribes to any paid plan, send an automated welcome DM within seconds.

```typescript
// Append to src/app/api/whop/webhook/route.ts

async function handleMembershipActivated(membership: {
  user_id: string;
  product_id: string;
  experience_id: string;
}) {
  const tier = getTierFromExperienceId(membership.experience_id);

  const welcomeMessages: Record<string, string> = {
    core: `
👋 **Welcome to TradeMind — TurboCore Core**

You'll get the daily 3 PM signal with exact allocation, morning briefing at 8:15 AM, and 50 AI messages/month.

**Quick start:**
1. Make sure push notifications are on for Whop — that's how the 3 PM signal reaches you
2. Check the #morning-brief channel every day before market open
3. When the 3 PM signal drops, you have until close to execute — takes under 2 min

**Your first signal** arrives at 3 PM ET today (or tomorrow if it's after market hours).

Questions? Ask in #general-chat.

_Educational analysis only. Not personalized investment advice._
    `.trim(),

    pro: `
👋 **Welcome to TradeMind — TurboCore Pro**

You have full access: daily signals, morning briefings, Options Strategy Builder, Weekly AI Debrief, and 400 AI messages/month.

**Pro-specific features to use first:**
• **Options Strategy Builder** — AI tab → Options Strategy. Paste any ticker + your thesis → get 3 ranked options strategies with legs, costs, and win probability
• **Weekly Debrief** — every Sunday 6 PM ET, you get a personalized AI review of your virtual portfolio vs TurboCore benchmark
• **Pro Lounge** — #pro-lounge channel is live, members-only discussion

The 3 PM TurboCore signal drops daily. Pro allocation includes LEAPS guidance for Tastytrade users.

_Educational analysis only. Not personalized investment advice._
    `.trim(),

    bundle: `
👋 **Welcome to TradeMind — Both Bundle (Unlimited)**

You have everything: unlimited AI features, both TurboCore and TurboCore Pro signals, full weekly debrief with PDF export, and 1,500 AI messages/month.

**Three things to do right now:**
1. Connect Tastytrade via the app for one-tap auto-execution (optional but powerful)
2. Set up the Position Screenshot Analyzer — go to AI tab → Screenshot. Upload any brokerage position for instant risk analysis
3. Bookmark the Options Strategy Builder — AI tab → Options Strategy

Your referral bonus: **$50 credit + 250 AI messages** per successful referral. Link is in the Refer tab.

_Educational analysis only. Not personalized investment advice._
    `.trim(),

    free: `
👋 **Welcome to TradeMind's free community.**

You can see delayed signal summaries here. When you're ready for real-time signals, morning briefings, and full AI tools, upgrade anytime: trademind.bot/upgrade

Any questions about the platform, ask here and the team will respond.
    `.trim(),
  };

  const message = welcomeMessages[tier] ?? welcomeMessages.free;

  // Send DM to the new member
  await whop.messages.createDm({
    user_id: membership.user_id,
    content: message,
  });

  // Log to your PostgreSQL DB for tracking
  await logWhopEvent({
    type: "membership_activated",
    user_id: membership.user_id,
    tier,
    experience_id: membership.experience_id,
    timestamp: new Date(),
  });
}

function getTierFromExperienceId(experienceId: string): string {
  const map: Record<string, string> = {
    [process.env.WHOP_FREE_EXPERIENCE_ID!]: "free",
    [process.env.WHOP_CORE_EXPERIENCE_ID!]: "core",
    [process.env.WHOP_PRO_EXPERIENCE_ID!]: "pro",
    [process.env.WHOP_BUNDLE_EXPERIENCE_ID!]: "bundle",
  };
  return map[experienceId] ?? "free";
}
```

### 5.3 Membership Deactivated — Churn Logging

```typescript
// Append to src/app/api/whop/webhook/route.ts

async function handleMembershipDeactivated(membership: {
  user_id: string;
  experience_id: string;
}) {
  const tier = getTierFromExperienceId(membership.experience_id);

  // Log churn event for analysis
  await logWhopEvent({
    type: "membership_deactivated",
    user_id: membership.user_id,
    tier,
    experience_id: membership.experience_id,
    timestamp: new Date(),
  });

  // Optional: Send a winback DM after 48 hours
  // This should be queued, not sent inline — use a background job or pg queue
  await scheduleWinbackDm(membership.user_id, tier);
}

async function scheduleWinbackDm(userId: string, tier: string) {
  // Insert into a `scheduled_messages` table with send_at = now + 48h
  // A separate cron job at /api/cron/winback processes this table
  await db.scheduledMessages.create({
    user_id: userId,
    message_type: "winback",
    tier,
    send_at: new Date(Date.now() + 48 * 60 * 60 * 1000),
    sent: false,
  });
}
```

### 5.4 Register the Webhook in Whop Dashboard

1. Go to `https://whop.com/dashboard/developer`
2. Click **Create Webhook** (top right)
3. Enter URL: `https://trademind.bot/api/whop/webhook`
4. Select API version: **v1**
5. Select events:
   - `membership.activated`
   - `membership.deactivated`
   - `payment.succeeded`
6. Copy the webhook secret → add as `WHOP_WEBHOOK_SECRET` in Vercel

---

## 6. App 2 (continued): Chat Bot Commands

The Chat bot listens to messages in the chat channel and responds to common member queries automatically. This is implemented as a separate API route that Whop calls when messages are sent.

### 6.1 Chat Bot Route

Create `/src/app/api/whop/chat-bot/route.ts`.

```typescript
// src/app/api/whop/chat-bot/route.ts
import { NextRequest, NextResponse } from "next/server";
import { whop } from "@/lib/whop";
import { getTodaysSignal } from "@/lib/turbocore";

const BOT_COMMANDS: Record<string, () => Promise<string>> = {
  "!signal": async () => {
    const signal = await getTodaysSignal();
    return `**Today's TurboCore Signal (${signal.date})**\nRegime: ${signal.regime} (${signal.confidence}% confidence)\nQQQ: ${signal.allocation.QQQ}% | QLD: ${signal.allocation.QLD}% | TQQQ: ${signal.allocation.TQQQ}% | SGOV: ${signal.allocation.SGOV}%\n\n_Full reasoning in the #signals channel. Not personalized investment advice._`;
  },
  "!regime": async () => {
    const signal = await getTodaysSignal();
    const emoji = { BULL: "🟢", SIDEWAYS: "🟡", BEAR: "🔴" }[signal.regime];
    return `${emoji} Current Regime: **${signal.regime}** | Confidence: ${signal.confidence}%`;
  },
  "!help": async () =>
    `**TradeMind Bot Commands**\n\`!signal\` — Today's full TurboCore signal\n\`!regime\` — Current market regime\n\`!plan\` — Subscription plan options\n\`!backtest\` — 7-year performance summary`,
  "!plan": async () =>
    `**TradeMind Plans**\n• TurboCore: $29/mo — daily signals, morning brief\n• TurboCore Pro: $49/mo — signals + Options Builder + Weekly Debrief\n• Both Bundle: $69/mo — everything unlimited\n\nUpgrade at trademind.bot`,
  "!backtest": async () =>
    `**TurboCore 7-Year Backtest (2019-2025)**\n• CAGR: 27.8%\n• Max Drawdown: -11.2% (vs TQQQ -83% in 2022)\n• Win Rate: 86% (6 of 7 years positive)\n• $5,000 → $27,822 over 7 years\n\nFull report at trademind.bot`,
};

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.json();
  const { content, user_id, channel_id } = body;

  if (!content?.startsWith("!")) {
    return new NextResponse("OK", { status: 200 });
  }

  const command = content.trim().toLowerCase().split(" ")[0];
  const handler = BOT_COMMANDS[command];

  if (handler) {
    const response = await handler();
    await whop.messages.create({
      channel_id,
      content: response,
    });
  }

  return new NextResponse("OK", { status: 200 });
}
```

---

## 7. App 3: Docs (Content) — Programmatic Playbook Management

The Docs/Content app on Whop does not expose a full programmatic write API for rich content pages (as of April 2026). Content docs must be created manually inside the Whop dashboard editor. However, the following automation is possible via the API:

### 7.1 What Can Be Automated

| Action | API Available | Method |
|--------|--------------|--------|
| Send a message with doc-style content | Yes | `messages.create` with markdown |
| Upload and attach a PDF file | Yes | File attachment via messages API |
| Update channel descriptions | Limited | Manual |
| Create rich document pages | No | Manual in Whop dashboard |

### 7.2 Weekly Debrief PDF Auto-Delivery

The existing Weekly Debrief (Sunday 6 PM ET) already generates a PDF for Bundle users. Add Whop message delivery:

```typescript
// src/app/api/cron/weekly-debrief/route.ts
// ADD after generating the debrief PDF

import { whop } from "@/lib/whop";

async function deliverDebriefToWhop(userId: string, pdfUrl: string, summary: string) {
  // Send DM to the specific Bundle member with their weekly debrief
  await whop.messages.createDm({
    user_id: userId,
    content: `
📊 **Your Weekly TurboCore Debrief is Ready**

${summary}

Download your personalized PDF report: ${pdfUrl}

---
_See you next Sunday. Keep following the signals._
    `.trim(),
  });
}
```

### 7.3 Static Docs Content — Manual Setup Checklist

These documents must be created manually in the Whop dashboard Content app. Create them once and they persist:

- `START HERE: The TurboCore Playbook` — What is TurboCore, signal logic, how to execute in under 2 min
- `Understanding Regimes: BULL / SIDEWAYS / BEAR` — Plain-English explanation of each regime
- `Why 2022 Was Our Best Year` — The stress test breakdown (-11.2% vs TQQQ -83%)
- `Execution Guide: Manual vs Tastytrade Auto-Mode`
- `Glossary: QQQ, QLD, TQQQ, SGOV, LEAPS, EMA, HMM`

---

## 8. App 4: Courses — Programmatic Course Creation

The Whop Courses API supports full programmatic creation of courses, chapters, and lessons.

### 8.1 Create a Course

```typescript
// src/lib/whop-courses.ts
import { whop } from "@/lib/whop";

export async function createCourse(params: {
  experienceId: string;
  title: string;
  tagline: string;
  coverImageUrl: string;
  sequential: boolean; // true = must complete in order
}) {
  const course = await whop.courses.create({
    experience_id: params.experienceId,
    title: params.title,
    tagline: params.tagline,
    cover_image_url: params.coverImageUrl,
    sequential: params.sequential,
    visibility: "visible",
    certificate: true, // award PDF certificate on completion
  });

  return course; // Returns { id: "cors_xxx", title, ... }
}
```

### 8.2 Add a Chapter to a Course

```typescript
export async function addChapter(params: {
  courseId: string;
  title: string;
  order?: number;
}) {
  const chapter = await whop.courseChapters.create({
    course_id: params.courseId,
    title: params.title,
    order: params.order,
  });

  return chapter; // Returns { id: "chap_xxx", ... }
}
```

### 8.3 Add a Video Lesson to a Chapter

```typescript
export async function addLesson(params: {
  chapterId: string;
  title: string;
  videoUrl?: string;        // Direct video URL or YouTube embed
  content?: string;         // Markdown text content
  attachmentUrl?: string;   // Downloadable file (PDF cheat sheet, etc.)
}) {
  const lesson = await whop.courseLessons.create({
    chapter_id: params.chapterId,
    title: params.title,
    video_url: params.videoUrl,
    content: params.content,
  });

  return lesson;
}
```

### 8.4 Full Course Seeding Script

Run this once to seed TradeMind's initial course library. Create `/scripts/seed-whop-courses.ts`.

```typescript
// scripts/seed-whop-courses.ts
// Run with: npx tsx scripts/seed-whop-courses.ts

import { whop, EXPERIENCES } from "@/lib/whop";
import { createCourse, addChapter, addLesson } from "@/lib/whop-courses";

const COURSE_STRUCTURE = [
  {
    title: "TurboCore 101: Start Here",
    tagline: "Learn the signal, execute in 2 minutes, compound for life",
    targetExperience: EXPERIENCES.core,
    sequential: true,
    chapters: [
      {
        title: "Module 1: What is TurboCore?",
        lessons: [
          {
            title: "The problem: why 46% of Gen Z wants to invest but only 36% do",
            content: "...",
          },
          {
            title: "The TurboCore strategy: 4 layers of ML explained simply",
            content: "...",
          },
          {
            title: "The 2022 proof: TurboCore -11.2% vs TQQQ -83%",
            content: "...",
          },
        ],
      },
      {
        title: "Module 2: Reading Your Daily Signal",
        lessons: [
          {
            title: "BULL regime: what it means and what to do",
            content: "...",
          },
          {
            title: "SIDEWAYS regime: the 70% QQQ defensive posture",
            content: "...",
          },
          {
            title: "BEAR regime: rotating to SGOV (T-bills) to protect capital",
            content: "...",
          },
        ],
      },
      {
        title: "Module 3: Execution",
        lessons: [
          {
            title: "Manual execution: any brokerage, under 2 minutes",
            content: "...",
          },
          {
            title: "Auto-execution: connecting Tastytrade for one-tap approval",
            content: "...",
          },
          {
            title: "Position sizing: fractional shares, starting with $25",
            content: "...",
          },
        ],
      },
    ],
  },
  {
    title: "Options 101 for Gen Z",
    tagline: "From zero to first options trade",
    targetExperience: EXPERIENCES.pro,
    sequential: true,
    chapters: [
      {
        title: "Module 1: Options Basics",
        lessons: [
          { title: "What is an options contract?", content: "..." },
          { title: "Calls vs. puts explained simply", content: "..." },
          { title: "Why we use LEAPS instead of TQQQ in Pro tier", content: "..." },
        ],
      },
      {
        title: "Module 2: Using the Options Strategy Builder",
        lessons: [
          {
            title: "How to use TradeMind's AI Options Strategy Builder",
            content: "...",
          },
          {
            title: "Understanding the 3 strategy recommendations: legs, costs, breakeven",
            content: "...",
          },
          {
            title: "Risk management: the 1% rule and position sizing for beginners",
            content: "...",
          },
        ],
      },
    ],
  },
];

async function seedCourses() {
  for (const courseData of COURSE_STRUCTURE) {
    console.log(`Creating course: ${courseData.title}...`);

    const course = await createCourse({
      experienceId: courseData.targetExperience,
      title: courseData.title,
      tagline: courseData.tagline,
      coverImageUrl: "https://trademind.bot/images/course-cover.png",
      sequential: courseData.sequential,
    });

    console.log(`  Created course: ${course.id}`);

    for (const chapterData of courseData.chapters) {
      const chapter = await addChapter({
        courseId: course.id,
        title: chapterData.title,
      });

      console.log(`    Created chapter: ${chapter.id}`);

      for (const lessonData of chapterData.lessons) {
        const lesson = await addLesson({
          chapterId: chapter.id,
          title: lessonData.title,
          content: lessonData.content,
        });

        console.log(`      Created lesson: ${lesson.id}`);
      }
    }
  }

  console.log("\n✅ Course seeding complete.");
}

seedCourses().catch(console.error);
```

---

## 9. Push Notifications — Full Reference

All push notification calls are made via `whop.notifications.create`. They appear in the Whop iOS/Android app and web interface.

### 9.1 Types of Notifications to Implement

```typescript
// src/lib/whop-notifications.ts
import { whop, ALL_PAID_EXPERIENCES } from "@/lib/whop";

// 1. Daily signal notification (called from /api/cron/signal)
export async function sendSignalNotification(signal: {
  regime: "BULL" | "SIDEWAYS" | "BEAR";
  confidence: number;
}) {
  const emoji = { BULL: "🟢", SIDEWAYS: "🟡", BEAR: "🔴" }[signal.regime];
  await Promise.all(
    ALL_PAID_EXPERIENCES.map((experience_id) =>
      whop.notifications.create({
        experience_id,
        title: `${emoji} ${signal.regime} Signal — ${signal.confidence}% confidence`,
        subtitle: "TurboCore 3PM Signal",
        content: "Tap to see today's full allocation and execute in 2 minutes.",
        rest_path: "/signal",
      })
    )
  );
}

// 2. Morning brief notification (called from /api/cron/morning-brief)
export async function sendMorningBriefNotification(regime: string) {
  await Promise.all(
    ALL_PAID_EXPERIENCES.map((experience_id) =>
      whop.notifications.create({
        experience_id,
        title: `📊 Morning Brief Ready`,
        subtitle: `Today's regime outlook: ${regime}`,
        content: "Pre-market brief is live. Tap to read before the open.",
        rest_path: "/morning-brief",
      })
    )
  );
}

// 3. Weekly debrief notification (called from /api/cron/weekly-debrief)
export async function sendWeeklyDebriefNotification(userId: string) {
  await whop.notifications.create({
    experience_id: process.env.WHOP_BUNDLE_EXPERIENCE_ID!,
    title: "📈 Your Weekly Debrief is Ready",
    subtitle: "Personalized performance review",
    content: "See how your portfolio tracked TurboCore this week + one coaching tip.",
    user_ids: [userId],
    rest_path: "/debrief",
  });
}

// 4. Regime change alert (triggered when regime shifts)
export async function sendRegimeChangeAlert(
  oldRegime: string,
  newRegime: string
) {
  const emoji = { BULL: "🟢", SIDEWAYS: "🟡", BEAR: "🔴" }[newRegime] ?? "⚠️";
  await Promise.all(
    ALL_PAID_EXPERIENCES.map((experience_id) =>
      whop.notifications.create({
        experience_id,
        title: `${emoji} Regime Change: ${oldRegime} → ${newRegime}`,
        subtitle: "TurboCore has detected a regime shift",
        content: "Market conditions have changed. Check today's allocation update.",
        rest_path: "/signal",
      })
    )
  );
}
```

---

## 10. Database Schema Additions

Add the following tables to the existing PostgreSQL database for Whop event tracking.

```sql
-- Whop membership events
CREATE TABLE whop_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type VARCHAR(50) NOT NULL,
  user_id VARCHAR(100),
  tier VARCHAR(20),
  experience_id VARCHAR(100),
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Scheduled messages (for winback DMs, etc.)
CREATE TABLE scheduled_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id VARCHAR(100) NOT NULL,
  message_type VARCHAR(50) NOT NULL,  -- 'winback', 'nudge', 'upgrade_prompt'
  tier VARCHAR(20),
  content TEXT,
  send_at TIMESTAMPTZ NOT NULL,
  sent BOOLEAN DEFAULT FALSE,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for the cron job that processes scheduled messages
CREATE INDEX idx_scheduled_messages_send_at ON scheduled_messages (send_at, sent)
  WHERE sent = FALSE;

-- Whop post log (track every announcement sent to Whop)
CREATE TABLE whop_posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_type VARCHAR(50) NOT NULL,  -- 'morning_brief', 'signal', 'weekly_debrief'
  channel_id VARCHAR(100),
  content TEXT,
  whop_message_id VARCHAR(100),
  signal_date DATE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 11. Winback Cron Job

Process the scheduled winback DMs daily at 9 AM ET.

```typescript
// src/app/api/cron/winback/route.ts
import { NextRequest, NextResponse } from "next/server";
import { whop } from "@/lib/whop";
import { db } from "@/lib/db";

export async function GET(request: NextRequest): Promise<NextResponse> {
  // Verify Vercel cron secret
  if (request.headers.get("authorization") !== `Bearer ${process.env.CRON_SECRET}`) {
    return new NextResponse("Unauthorized", { status: 401 });
  }

  // Get all unsent messages due now or earlier
  const pending = await db.scheduledMessages.findMany({
    where: { sent: false, send_at: { lte: new Date() } },
    take: 100, // batch limit
  });

  for (const msg of pending) {
    try {
      if (msg.message_type === "winback") {
        await whop.messages.createDm({
          user_id: msg.user_id,
          content: `
Hey — noticed you recently left TradeMind.

In case you're still following markets: TurboCore's regime detection has been actively protecting capital during recent volatility. If the timing wasn't right before, happy to extend a 30-day trial at no cost.

Reply here or go to trademind.bot to re-activate.
          `.trim(),
        });
      }

      await db.scheduledMessages.update({
        where: { id: msg.id },
        data: { sent: true, sent_at: new Date() },
      });
    } catch (err) {
      console.error(`Failed to send scheduled message ${msg.id}:`, err);
    }
  }

  return NextResponse.json({ processed: pending.length });
}
```

Add to `vercel.json`:
```json
{ "path": "/api/cron/winback", "schedule": "0 14 * * *" }
```
_(14:00 UTC = 9:00 AM ET)_

---

## 12. Updated vercel.json — All Cron Jobs

```json
{
  "crons": [
    { "path": "/api/cron/morning-brief", "schedule": "15 13 * * 1-5" },
    { "path": "/api/cron/signal",        "schedule": "0 20 * * 1-5" },
    { "path": "/api/cron/weekly-debrief","schedule": "0 23 * * 0" },
    { "path": "/api/cron/winback",       "schedule": "0 14 * * *" }
  ]
}
```

---

## 13. File Map — All New Files to Create

| File | Type | Purpose |
|------|------|---------|
| `src/lib/whop.ts` | Utility | Shared Whop SDK client and experience ID map |
| `src/lib/whop-notifications.ts` | Utility | All push notification functions |
| `src/lib/whop-courses.ts` | Utility | Course, chapter, lesson creation helpers |
| `src/app/api/whop/webhook/route.ts` | API Route | Webhook handler for membership events |
| `src/app/api/whop/chat-bot/route.ts` | API Route | Chat bot command handler |
| `src/app/api/cron/winback/route.ts` | API Route | Winback DM cron processor |
| `scripts/get-whop-channels.ts` | Script | One-time: discover channel IDs |
| `scripts/seed-whop-courses.ts` | Script | One-time: create courses programmatically |
| `prisma/migrations/whop_tables.sql` | DB Migration | New tables for events and scheduled messages |

### Files to Modify

| File | Change |
|------|--------|
| `src/app/api/cron/morning-brief/route.ts` | Add `postMorningBriefToWhop()` call + push notification |
| `src/app/api/cron/signal/route.ts` | Add `postSignalToWhop()` call + push notification |
| `src/app/api/cron/weekly-debrief/route.ts` | Add Whop DM delivery for Bundle users |
| `vercel.json` | Add winback cron |
| `.env.local` + Vercel env | Add all `WHOP_*` environment variables |

---

## 14. Testing Checklist (Pre-Launch)

### Local Testing

Use [ngrok](https://ngrok.com/) or Cloudflare Tunnel to expose `localhost:3000` for webhook testing.

```bash
# Expose local server
ngrok http 3000

# Use the ngrok HTTPS URL as your webhook URL in Whop dashboard
# e.g., https://abc123.ngrok.io/api/whop/webhook
```

### Verification Steps

- [ ] `WHOP_API_KEY` authenticates against `https://api.whop.com/api/v1` — test with `curl -H "Authorization: Bearer $WHOP_API_KEY" https://api.whop.com/api/v1/products?company_id=$WHOP_COMPANY_ID`
- [ ] Channel IDs discovered via `scripts/get-whop-channels.ts` and added to `.env`
- [ ] Morning brief cron posts to Whop announcements channel (trigger manually via GET `/api/cron/morning-brief`)
- [ ] Signal cron posts to Whop announcements channel + sends push notification (trigger manually)
- [ ] Webhook receives `membership.activated` and welcome DM is sent to test account
- [ ] Webhook receives `membership.deactivated` and event is logged to DB
- [ ] Chat bot responds to `!signal`, `!regime`, `!help`, `!plan`, `!backtest`
- [ ] Courses seeding script creates courses successfully and they appear in Whop dashboard
- [ ] Weekly debrief delivers PDF link via Whop DM to Bundle user
- [ ] Winback cron processes pending `scheduled_messages` and sends DM

---

## 15. SDK Reference Links

| Resource | URL |
|----------|-----|
| Whop Developer Docs | https://docs.whop.com |
| SDK Getting Started | https://docs.whop.com/developer/api/getting-started |
| Webhooks Guide | https://docs.whop.com/developer/guides/webhooks |
| Push Notifications | https://docs.whop.com/developer/guides/notifications |
| Chat Quickstart | https://docs.whop.com/developer/guides/chat/quickstart |
| Courses API | https://docs.whop.com/api-reference/courses/create-course |
| API Reference | https://api.whop.com/api/v1 |
| MCP Server (Claude) | https://mcp.whop.com/sse |
| MCP Server (Cursor) | https://mcp.whop.com/mcp |

> **Tip for Antigravity:** The Whop API is available as an MCP server at `https://mcp.whop.com/sse`. Add it to Claude's MCP configuration so the AI coding assistant has live API documentation context while writing this integration.

