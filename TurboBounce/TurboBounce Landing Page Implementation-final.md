# TurboBounce Landing Page: Full Implementation Plan
## Executive Summary
This document is a comprehensive, developer-ready implementation plan for the TurboBounce animated landing page. The page serves as a 3-minute cinematic pitch that walks visitors through 7 years of backtested data (2019–2025) across 1,078 trades, showing $5K → $21,811 growth at +336.2% total return. The tech stack is **Next.js (TypeScript) on Vercel**, with **Recharts** for interactive charts, **ElevenLabs** for multilingual voice narration, **Privy** for authentication, and **i18next** for internationalization in English, Spanish, and Chinese. The entire build is designed to be handed off to **Google Antigravity IDE** for agent-driven development, with optimized prompts included for each phase.[^1][^2][^3][^4]

The key selling point: TurboBounce uses AI to create a **mean-reversion return engine** with controlled risk. Starting from as low as $5K, AI actively monitors and applies innovative volatility-adaptive options strategies — making it a hands-free investment.[^5]

***
## Tech Stack and Architecture
### Core Stack
| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | Next.js 14+ (App Router, TypeScript) | SSR for SEO, client components for animations[^6] |
| Styling | Tailwind CSS + CSS custom properties | Dark theme tokens matching existing dashboard |
| Charts | Recharts + Framer Motion | Equity curve, calculator, animated reveals[^7][^8] |
| Auth | Privy (`@privy-io/react-auth`) | Email, Google, Apple, wallet login[^9] |
| i18n | react-i18next + i18next-http-backend | EN / ES / 中文 translations[^1] |
| Voice | ElevenLabs (pre-generated MP3s) | 3-minute multilingual narration[^10][^11] |
| Database | Supabase (Postgres + Auth + Realtime) | User profiles, referrals, milestones |
| Broker API | @tastytrade/api JS SDK | OAuth, position sync, auto-execution[^1] |
| Payments | Stripe + Afterpay/Klarna | Subscriptions, BNPL for annual plans |
| Referral | Rewardful or Refgrow | Stripe-integrated referral tracking[^1] |
| Hosting | Vercel | Edge deployment, HTTPS, preview deploys[^12] |
### Design Token Specification
All components use the established dark theme tokens from the existing dashboard:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0D0B1A` | Page backgrounds |
| `--bg-card` | `#1A1730` | Card surfaces, nav |
| `--accent-purple` | `#7C3AED` | CTA buttons, active borders, links |
| `--text-primary` | `#FFFFFF` | Headings, primary content |
| `--text-secondary` | `#9CA3AF` | Subtitles, labels |
| `--success` | `#10B981` | Positive P&L, live badges |
| `--danger` | `#EF4444` | Negative P&L, drawdown alerts |
| `--font-mono` | JetBrains Mono | Numbers, P&L, percentages |
| `--radius-card` | 12px | Card corner radius |

***
## Project Setup
### Step 1: Initialize Next.js Project
```bash
npx create-next-app@latest turbobounce-landing --typescript --tailwind --app --eslint
cd turbobounce-landing
```
### Step 2: Install All Dependencies
```bash
# Core UI
npm install recharts framer-motion

# Internationalization
npm install i18next react-i18next i18next-browser-languagedetector i18next-http-backend

# Authentication
npm install @privy-io/react-auth

# ElevenLabs (build-time only, for generating audio)
npm install elevenlabs

# Database
npm install @supabase/supabase-js

# Payments
npm install @stripe/stripe-js stripe

# Fonts
npm install @fontsource/jetbrains-mono

# Utilities
npm install clsx
```
### Step 3: Environment Variables (`.env.local`)
```env
# Privy
NEXT_PUBLIC_PRIVY_APP_ID=your_privy_app_id
PRIVY_APP_SECRET=your_privy_secret

# Supabase
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_key

# Stripe
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_xxx
STRIPE_SECRET_KEY=sk_live_xxx

# ElevenLabs (build-time script only)
ELEVENLABS_API_KEY=your_elevenlabs_key

# App
NEXT_PUBLIC_APP_URL=https://turbobounce.com
```
### Step 4: Project Structure
```
turbobounce-landing/
├── app/
│   ├── layout.tsx              # Root layout with providers
│   ├── page.tsx                # Landing page (single-page)
│   ├── dashboard/
│   │   └── page.tsx            # Post-login dashboard redirect
│   └── api/
│       ├── stripe/webhook/route.ts
│       └── referral/route.ts
├── components/
│   ├── Header.tsx              # Fixed header bar
│   ├── LanguageBar.tsx         # EN | ES | 中文 pill toggle
│   ├── PrivyLoginButton.tsx    # Top-right login CTA
│   ├── ReferralButton.tsx      # Top-left refer a friend
│   ├── ReferralModal.tsx       # Share modal with channels
│   ├── EquityCurveChart.tsx    # Animated Recharts AreaChart
│   ├── TradeFeed.tsx           # Scrolling trade cards
│   ├── TimelineScrubber.tsx    # Voice + timeline progress bar
│   ├── PlayButton.tsx          # Play/pause narration control
│   ├── CompoundingCalculator.tsx # Interactive calculator
│   ├── SubtitleOverlay.tsx     # Narration subtitles
│   └── CustomTooltip.tsx       # Recharts custom tooltip
├── contexts/
│   └── NarrationContext.tsx    # Shared timeline state
├── hooks/
│   ├── useNarrationProgress.ts # Audio playback + progress
│   └── useCompounding.ts      # Calculator math logic
├── lib/
│   ├── i18n.ts                # i18next configuration
│   ├── supabase.ts            # Supabase client
│   ├── stripe.ts              # Stripe helpers
│   └── tradeData.ts           # Pre-processed trade JSON
├── data/
│   ├── equity_curve.json       # 1,078 data points
│   ├── trade_feed.json         # Trade details per point
│   └── milestones.json         # Key milestone markers
├── public/
│   ├── audio/
│   │   ├── narration_en.mp3
│   │   ├── narration_es.mp3
│   │   └── narration_zh.mp3
│   └── locales/
│       ├── en/translation.json
│       ├── es/translation.json
│       └── zh/translation.json
├── scripts/
│   ├── processTradeCSV.ts      # Build-time CSV → JSON
│   └── generateNarration.ts    # ElevenLabs audio generation
└── tailwind.config.ts
```

***
## Data Pipeline: CSV to Animation Data
### Build-Time Processing Script (`scripts/processTradeCSV.ts`)
This script transforms the raw 1,078-trade CSV into animation-ready JSON files. The CSV contains 11 columns: Symbol, Strategy, Direction, Exit, Entry Date, Exit Date, Days Held, Entry $, Exit $, PnL $, PnL %.[^13]

```typescript
// scripts/processTradeCSV.ts
import fs from "fs";
import path from "path";
import { parse } from "csv-parse/sync";

interface RawTrade {
  Symbol: string;
  Strategy: string;
  Direction: string;
  Exit: string;
  "Entry Date": string;
  "Exit Date": string;
  "Days Held": string;
  "Entry $": string;
  "Exit $": string;
  "PnL $": string;
  "PnL %": string;
}

interface EquityPoint {
  index: number;
  exitDate: string;
  accountValue: number;
  pnl: number;
  cumulativePnl: number;
  year: number;
  normalizedTime: number; // 0.0 → 1.0
}

interface TradeDetail {
  index: number;
  symbol: string;
  strategy: string;
  direction: string;
  entryDate: string;
  exitDate: string;
  daysHeld: number;
  entryPrice: number;
  exitPrice: number;
  pnl: number;
  pnlPercent: number;
  accountValueAfter: number;
}

interface Milestone {
  index: number;
  type: "first_10k" | "worst_drawdown" | "recovery_peak" | "final";
  label: string;
  value: number;
  date: string;
}

const STARTING_CAPITAL = 5000;
const csvPath = path.resolve("data/turbobounce_options_5k_all_trades.csv");
const raw = fs.readFileSync(csvPath, "utf-8");
const records: RawTrade[] = parse(raw, { columns: true, skip_empty_lines: true });

// Sort by Exit Date
records.sort(
  (a, b) =>
    new Date(a["Exit Date"]).getTime() - new Date(b["Exit Date"]).getTime()
);

let cumPnl = 0;
const totalTrades = records.length;

const equityCurve: EquityPoint[] = [];
const tradeFeed: TradeDetail[] = [];

records.forEach((row, i) => {
  const pnl = parseFloat(row["PnL $"]);
  cumPnl += pnl;
  const accountValue = STARTING_CAPITAL + cumPnl;
  const exitDate = row["Exit Date"];
  const year = new Date(exitDate).getFullYear();

  equityCurve.push({
    index: i,
    exitDate,
    accountValue: Math.round(accountValue * 100) / 100,
    pnl: Math.round(pnl * 100) / 100,
    cumulativePnl: Math.round(cumPnl * 100) / 100,
    year,
    normalizedTime: i / (totalTrades - 1),
  });

  tradeFeed.push({
    index: i,
    symbol: row.Symbol,
    strategy: row.Strategy,
    direction: row.Direction,
    entryDate: row["Entry Date"],
    exitDate,
    daysHeld: parseInt(row["Days Held"]),
    entryPrice: parseFloat(row["Entry $"]),
    exitPrice: parseFloat(row["Exit $"]),
    pnl: Math.round(pnl * 100) / 100,
    pnlPercent: parseFloat(row["PnL %"]),
    accountValueAfter: Math.round(accountValue * 100) / 100,
  });
});

// Identify milestones
const milestones: Milestone[] = [
  {
    index: equityCurve.findIndex((p) => p.accountValue >= 10000),
    type: "first_10k",
    label: "$10K Club",
    value: 10000,
    date: "",
  },
  {
    index: equityCurve.reduce(
      (minIdx, p, i) =>
        p.accountValue < equityCurve[minIdx].accountValue ? i : minIdx,
      0
    ),
    type: "worst_drawdown",
    label: "Crash Filter Active",
    value: 0,
    date: "",
  },
  {
    index: equityCurve.length - 1,
    type: "final",
    label: "$21,811 — +336.2%",
    value: 21811.2,
    date: "",
  },
];

milestones.forEach((m) => {
  if (m.index >= 0) {
    m.date = equityCurve[m.index].exitDate;
    if (m.type === "worst_drawdown") {
      m.value = equityCurve[m.index].accountValue;
    }
  }
});

// Write output JSON files
const outDir = path.resolve("data");
fs.writeFileSync(
  path.join(outDir, "equity_curve.json"),
  JSON.stringify(equityCurve, null, 2)
);
fs.writeFileSync(
  path.join(outDir, "trade_feed.json"),
  JSON.stringify(tradeFeed, null, 2)
);
fs.writeFileSync(
  path.join(outDir, "milestones.json"),
  JSON.stringify(milestones, null, 2)
);

console.log(
  `✅ Processed ${totalTrades} trades → equity_curve.json, trade_feed.json, milestones.json`
);
```

Run with:
```bash
npx tsx scripts/processTradeCSV.ts
```
### Year-by-Year Data Mapped to Animation Timeline
Trade count per year determines proportional timeline allocation within the 3-minute narration:[^2]

| Year | Trades | Net PnL | End Capital | Timeline Position | Key Event |
|------|--------|---------|-------------|-------------------|-----------|
| 2019 | 183 | +$2,401 | $7,401 | 0:00–0:26 | Engine launch, 48% return |
| 2020 | 173 | +$987 | $8,389 | 0:26–0:51 | COVID chaos, stayed profitable |
| 2021 | 178 | +$5,847 | $14,236 | 0:51–1:17 | Breakout year, 69.7% return |
| 2022 | 87 | −$5,010 | $9,226 | 1:17–1:38 | Bear market, crash filter active |
| 2023 | 178 | +$4,017 | $13,243 | 1:38–2:03 | Recovery, 43.5% return |
| 2024 | 147 | +$5,950 | $19,193 | 2:03–2:24 | Acceleration, 44.9% return |
| 2025 | 132 | +$2,618 | $21,811 | 2:24–3:00 | Final reveal + CTA |

***
## Landing Page Layout Architecture
### Header Bar (Fixed, 48px)
```
┌─────────────────────────────────────────────────────┐
│  [👥 Refer]     [ EN | ES | 中文 ]       [Login →]  │
└─────────────────────────────────────────────────────┘
```

| Position | Element | Behavior |
|----------|---------|----------|
| Top Left | Refer a Friend button | Purple outline badge; opens referral modal[^1] |
| Top Center | Language Bar (EN \| ES \| 中文) | Pill-shaped toggle; EN selected by default; triggers i18next switch + voice swap[^1] |
| Top Right | Privy Login button | Purple glowing CTA; triggers Privy modal (Google, Apple, email, wallet)[^9] |
### Body: Single Viewport Layout (100vh)
The body is divided into visual zones that animate in sequence during narration:

- **Zone 1 — Animated Equity Curve Chart (Top 55%)**: Full-width Recharts AreaChart rendering cumulative account value from $5,000 → $21,811 across 1,078 trades. Green-to-transparent gradient fill. Interactive tooltip shows account value, trade details, and yearly return on hover.[^8][^7]

- **Zone 2 — Synchronized Trade Feed (Middle 20%)**: Scrolling card feed of individual trades at the current timeline position. Each card: Symbol, Strategy, Direction, Entry/Exit dates, P&L with green/red coloring.[^1]

- **Zone 3 — Play Button + Timeline Scrubber (Bottom 25%)**: A play/pause button initiating the narration. The unified scrubber doubles as voice progress and historical timeline (2019–2025). Year labels at proportional intervals. Draggable to seek.[^1]

Below the fold, the **Interactive Compounding Calculator** appears after narration completes, replacing the separate calculator with the integrated backtest simulation where users can adjust starting capital and see projected returns.[^1]

***
## Core Component Code
### Root Layout (`app/layout.tsx`)
```typescript
// app/layout.tsx
import type { Metadata } from "next";
import { PrivyProvider } from "@privy-io/react-auth";
import "@fontsource/jetbrains-mono";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n-provider";

export const metadata: Metadata = {
  title: "TurboBounce — AI-Powered Mean Reversion Options Engine",
  description:
    "Turn $5K into $21,811 with AI-driven options compounding. 7 years backtested, 1,078 trades, +336% return.",
  openGraph: {
    title: "TurboBounce — Hands-Free Options Compounding",
    description: "AI catches the snapback. Start from $5K.",
    images: ["/og-image.png"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0D0B1A] text-white antialiased">
        <PrivyProvider
          appId={process.env.NEXT_PUBLIC_PRIVY_APP_ID!}
          config={{
            loginMethods: ["email", "google", "apple"],
            appearance: {
              theme: "dark",
              accentColor: "#7C3AED",
            },
          }}
        >
          <I18nProvider>{children}</I18nProvider>
        </PrivyProvider>
      </body>
    </html>
  );
}
```
### i18n Configuration (`lib/i18n.ts`)
```typescript
// lib/i18n.ts
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import HttpBackend from "i18next-http-backend";

i18next
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "en",
    supportedLngs: ["en", "es", "zh"],
    interpolation: { escapeValue: false },
    backend: {
      loadPath: "/locales/{{lng}}/translation.json",
    },
    detection: {
      order: ["querystring", "cookie", "localStorage", "navigator"],
      caches: ["localStorage", "cookie"],
    },
  });

export default i18next;
```
### Narration Context (`contexts/NarrationContext.tsx`)
This is the single source of truth that drives all synchronized animations:

```typescript
// contexts/NarrationContext.tsx
"use client";

import React, {
  createContext,
  useContext,
  useState,
  useRef,
  useCallback,
  useEffect,
} from "react";
import { useTranslation } from "react-i18next";

interface NarrationState {
  progress: number; // 0.0 → 1.0
  isPlaying: boolean;
  currentYear: number;
  currentTradeIndex: number;
  duration: number;
  currentTime: number;
  play: () => void;
  pause: () => void;
  seek: (normalizedPosition: number) => void;
}

const TOTAL_TRADES = 1078;
const YEAR_BOUNDARIES = [
  { year: 2019, startIndex: 0, endIndex: 182 },
  { year: 2020, startIndex: 183, endIndex: 355 },
  { year: 2021, startIndex: 356, endIndex: 533 },
  { year: 2022, startIndex: 534, endIndex: 620 },
  { year: 2023, startIndex: 621, endIndex: 798 },
  { year: 2024, startIndex: 799, endIndex: 945 },
  { year: 2025, startIndex: 946, endIndex: 1077 },
];

const NarrationContext = createContext<NarrationState | null>(null);

export function NarrationProvider({ children }: { children: React.ReactNode }) {
  const { i18n } = useTranslation();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [progress, setProgress] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(180);
  const [currentTime, setCurrentTime] = useState(0);

  // Load audio based on current language
  useEffect(() => {
    const lang = i18n.language?.substring(0, 2) || "en";
    const audio = new Audio(`/audio/narration_${lang}.mp3`);
    audio.preload = "auto";

    audio.addEventListener("loadedmetadata", () => {
      setDuration(audio.duration);
    });

    audio.addEventListener("timeupdate", () => {
      const p = audio.currentTime / audio.duration;
      setProgress(p);
      setCurrentTime(audio.currentTime);
    });

    audio.addEventListener("ended", () => {
      setIsPlaying(false);
      setProgress(1);
    });

    // If switching languages mid-playback, sync position
    if (audioRef.current) {
      const prevProgress =
        audioRef.current.currentTime / audioRef.current.duration;
      audioRef.current.pause();
      audio.currentTime = prevProgress * audio.duration;
    }

    audioRef.current = audio;

    return () => {
      audio.pause();
      audio.removeEventListener("loadedmetadata", () => {});
      audio.removeEventListener("timeupdate", () => {});
      audio.removeEventListener("ended", () => {});
    };
  }, [i18n.language]);

  const currentTradeIndex = Math.min(
    Math.floor(progress * TOTAL_TRADES),
    TOTAL_TRADES - 1
  );
  const currentYear =
    YEAR_BOUNDARIES.find(
      (y) =>
        currentTradeIndex >= y.startIndex && currentTradeIndex <= y.endIndex
    )?.year ?? 2019;

  const play = useCallback(() => {
    audioRef.current?.play();
    setIsPlaying(true);
  }, []);

  const pause = useCallback(() => {
    audioRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const seek = useCallback(
    (normalizedPosition: number) => {
      if (audioRef.current) {
        audioRef.current.currentTime = normalizedPosition * duration;
        setProgress(normalizedPosition);
      }
    },
    [duration]
  );

  return (
    <NarrationContext.Provider
      value={{
        progress,
        isPlaying,
        currentYear,
        currentTradeIndex,
        duration,
        currentTime,
        play,
        pause,
        seek,
      }}
    >
      {children}
    </NarrationContext.Provider>
  );
}

export function useNarration() {
  const ctx = useContext(NarrationContext);
  if (!ctx)
    throw new Error("useNarration must be used within NarrationProvider");
  return ctx;
}
```
### Header Component (`components/Header.tsx`)
```typescript
// components/Header.tsx
"use client";

import { LanguageBar } from "./LanguageBar";
import { PrivyLoginButton } from "./PrivyLoginButton";
import { ReferralButton } from "./ReferralButton";

export function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-12 bg-[#0D0B1A]/90 backdrop-blur-md border-b border-white/5 flex items-center justify-between px-4">
      <ReferralButton />
      <LanguageBar />
      <PrivyLoginButton />
    </header>
  );
}
```
### Language Bar Component (`components/LanguageBar.tsx`)
```typescript
// components/LanguageBar.tsx
"use client";

import { useTranslation } from "react-i18next";
import clsx from "clsx";

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "es", label: "ES" },
  { code: "zh", label: "中文" },
];

export function LanguageBar() {
  const { i18n } = useTranslation();
  const currentLang = i18n.language?.substring(0, 2) || "en";

  return (
    <div className="flex items-center bg-[#1A1730] rounded-full p-0.5 border border-white/10">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          onClick={() => i18n.changeLanguage(lang.code)}
          className={clsx(
            "px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-200",
            currentLang === lang.code
              ? "bg-[#7C3AED] text-white shadow-[0_0_12px_rgba(124,58,237,0.4)]"
              : "text-[#9CA3AF] hover:text-white"
          )}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
```
### Privy Login Button (`components/PrivyLoginButton.tsx`)
```typescript
// components/PrivyLoginButton.tsx
"use client";

import { usePrivy } from "@privy-io/react-auth";
import { useTranslation } from "react-i18next";

export function PrivyLoginButton() {
  const { login, authenticated, logout, user } = usePrivy();
  const { t } = useTranslation();

  if (authenticated) {
    return (
      <button
        onClick={logout}
        className="px-4 py-1.5 text-sm font-medium text-[#9CA3AF] hover:text-white transition"
      >
        {user?.email?.address?.substring(0, 12) || t("nav.logout")}
      </button>
    );
  }

  return (
    <button
      onClick={login}
      className="px-5 py-1.5 text-sm font-semibold text-white bg-transparent border border-[#7C3AED] rounded-lg hover:bg-[#7C3AED]/20 hover:shadow-[0_0_16px_rgba(124,58,237,0.3)] transition-all duration-300"
    >
      {t("nav.login")}
    </button>
  );
}
```
### Animated Equity Curve Chart (`components/EquityCurveChart.tsx`)
This is the core visualization — a Recharts AreaChart that progressively reveals the equity curve synchronized with narration:[^7][^14]

```typescript
// components/EquityCurveChart.tsx
"use client";

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { motion, AnimatePresence } from "framer-motion";
import { useNarration } from "@/contexts/NarrationContext";
import { CustomTooltip } from "./CustomTooltip";
import equityCurveData from "@/data/equity_curve.json";
import type { TooltipProps } from "recharts";

type ValueType = number;
type NameType = string;

export function EquityCurveChart() {
  const { progress, currentYear, currentTradeIndex } = useNarration();

  // Slice data based on current progress
  const visibleData = useMemo(() => {
    const endIdx = Math.max(1, Math.ceil(progress * equityCurveData.length));
    return equityCurveData.slice(0, endIdx);
  }, [progress]);

  // Current account value for the animated counter
  const currentValue =
    visibleData.length > 0
      ? visibleData[visibleData.length - 1].accountValue
      : 5000;

  // Determine chart color: red during 2022 drawdown
  const isDrawdown = currentYear === 2022;
  const gradientColor = isDrawdown ? "#EF4444" : "#10B981";
  const strokeColor = isDrawdown ? "#EF4444" : "#10B981";

  return (
    <div className="relative w-full h-full">
      {/* Animated Account Value Counter */}
      <div className="absolute top-4 left-6 z-10">
        <p className="text-[#9CA3AF] text-xs uppercase tracking-wider">
          Account Value
        </p>
        <motion.p
          key={Math.round(currentValue)}
          className="text-3xl md:text-4xl font-bold font-mono text-white"
          initial={{ opacity: 0.7, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15 }}
        >
          ${currentValue.toLocaleString("en-US", { minimumFractionDigits: 2 })}
        </motion.p>
      </div>

      {/* Year Badge */}
      <div className="absolute top-4 right-6 z-10">
        <motion.span
          key={currentYear}
          className={`px-3 py-1 rounded-full text-sm font-bold ${
            isDrawdown ? "bg-[#EF4444]/20 text-[#EF4444]" : "bg-[#10B981]/20 text-[#10B981]"
          }`}
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 300 }}
        >
          {currentYear}
        </motion.span>
      </div>

      {/* 2022 Crash Filter Badge */}
      <AnimatePresence>
        {isDrawdown && (
          <motion.div
            className="absolute top-16 right-6 z-10 flex items-center gap-2 px-3 py-1.5 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-lg"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            <span className="text-lg">🛡️</span>
            <span className="text-[#EF4444] text-xs font-semibold">
              Crash Filter Active
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* The Chart */}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={visibleData}
          margin={{ top: 60, right: 20, left: 20, bottom: 10 }}
        >
          <defs>
            earGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={gradientColor} stopOpacity={0.3} />
              <stop offset="95%" stopColor={gradientColor} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="exitDate"
            tick={{ fill: "#9CA3AF", fontSize: 10 }}
            tickFormatter={(val: string) => {
              const d = new Date(val);
              return `${d.getFullYear()}`;
            }}
            interval={Math.floor(visibleData.length / 7)}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#9CA3AF", fontSize: 10 }}
            tickFormatter={(val: number) =>
              `$${(val / 1000).toFixed(0)}k`
            }
            axisLine={false}
            tickLine={false}
            domain={["dataMin - 500", "dataMax + 1000"]}
          />
          <Tooltip
            content={<CustomTooltip />}
            cursor={{ stroke: "#7C3AED", strokeWidth: 1 }}
          />
          <ReferenceLine
            y={5000}
            stroke="#9CA3AF"
            strokeDasharray="3 3"
            label={{
              value: "Principal: $5,000",
              fill: "#9CA3AF",
              fontSize: 10,
            }}
          />
          <Area
            type="monotone"
            dataKey="accountValue"
            stroke={strokeColor}
            strokeWidth={2}
            fill="url(#equityGradient)"
            animationDuration={0}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```
### Custom Tooltip (`components/CustomTooltip.tsx`)
Interactive tooltip showing trade details when hovering over the chart:[^14][^15]

```typescript
// components/CustomTooltip.tsx
"use client";

import type { TooltipProps } from "recharts";

type ValueType = number;
type NameType = string;

export function CustomTooltip({
  active,
  payload,
  label,
}: TooltipProps<ValueType, NameType>) {
  if (!active || !payload || !payload.length) return null;

  const data = payload.payload;

  return (
    <div className="bg-[#1A1730] border border-[#7C3AED]/30 rounded-lg p-3 shadow-xl min-w-[200px]">
      <p className="text-[#9CA3AF] text-xs">{data.exitDate}</p>
      <p className="text-white text-lg font-mono font-bold mt-1">
        ${data.accountValue.toLocaleString("en-US", {
          minimumFractionDigits: 2,
        })}
      </p>
      <div className="mt-2 border-t border-white/10 pt-2 space-y-1">
        <p className="text-xs">
          <span className="text-[#9CA3AF]">Trade P&L: </span>
          <span
            className={`font-mono ${
              data.pnl >= 0 ? "text-[#10B981]" : "text-[#EF4444]"
            }`}
          >
            {data.pnl >= 0 ? "+" : ""}${data.pnl.toFixed(2)}
          </span>
        </p>
        <p className="text-xs">
          <span className="text-[#9CA3AF]">Year: </span>
          <span className="text-white">{data.year}</span>
        </p>
        <p className="text-xs">
          <span className="text-[#9CA3AF]">Total P&L: </span>
          <span
            className={`font-mono ${
              data.cumulativePnl >= 0 ? "text-[#10B981]" : "text-[#EF4444]"
            }`}
          >
            {data.cumulativePnl >= 0 ? "+" : ""}$
            {data.cumulativePnl.toFixed(2)}
          </span>
        </p>
      </div>
    </div>
  );
}
```
### Trade Feed (`components/TradeFeed.tsx`)
```typescript
// components/TradeFeed.tsx
"use client";

import { useMemo, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { useNarration } from "@/contexts/NarrationContext";
import tradeFeedData from "@/data/trade_feed.json";

export function TradeFeed() {
  const { currentTradeIndex } = useNarration();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Show the 5 most recent trades up to currentTradeIndex
  const visibleTrades = useMemo(() => {
    const start = Math.max(0, currentTradeIndex - 4);
    return tradeFeedData.slice(start, currentTradeIndex + 1).reverse();
  }, [currentTradeIndex]);

  // Auto-scroll to latest trade
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [currentTradeIndex]);

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto scrollbar-hide space-y-2 px-4"
    >
      {visibleTrades.map((trade, i) => (
        <motion.div
          key={trade.index}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: i === 0 ? 1 : 0.6, y: 0 }}
          transition={{ duration: 0.3 }}
          className={`flex items-center justify-between px-3 py-2 rounded-lg border ${
            i === 0
              ? "bg-[#1A1730] border-[#7C3AED]/40"
              : "bg-[#1A1730]/50 border-white/5"
          }`}
        >
          <div className="flex items-center gap-3">
            <span className="text-white font-semibold text-sm">
              {trade.symbol}
            </span>
            <span className="text-[#9CA3AF] text-xs">
              {trade.strategy.replace("_", " ")}
            </span>
            <span
              className={`text-xs px-1.5 py-0.5 rounded ${
                trade.direction === "BULLISH"
                  ? "bg-[#10B981]/20 text-[#10B981]"
                  : "bg-[#EF4444]/20 text-[#EF4444]"
              }`}
            >
              {trade.direction}
            </span>
          </div>
          <div className="text-right">
            <span
              className={`font-mono text-sm font-semibold ${
                trade.pnl >= 0 ? "text-[#10B981]" : "text-[#EF4444]"
              }`}
            >
              {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
            </span>
            <p className="text-[#9CA3AF] text-xs">
              {trade.pnlPercent.toFixed(1)}%
            </p>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
```
### Timeline Scrubber + Play Button (`components/TimelineScrubber.tsx`)
```typescript
// components/TimelineScrubber.tsx
"use client";

import { useRef, useCallback } from "react";
import { useNarration } from "@/contexts/NarrationContext";
import { useTranslation } from "react-i18next";

const YEAR_LABELS = [
  { year: 2019, position: 0 },
  { year: 2020, position: 0.17 },
  { year: 2021, position: 0.33 },
  { year: 2022, position: 0.5 },
  { year: 2023, position: 0.58 },
  { year: 2024, position: 0.74 },
  { year: 2025, position: 0.88 },
];

export function TimelineScrubber() {
  const { progress, isPlaying, play, pause, seek, currentTime, duration } =
    useNarration();
  const { t } = useTranslation();
  const barRef = useRef<HTMLDivElement>(null);

  const handleBarClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!barRef.current) return;
      const rect = barRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      seek(Math.max(0, Math.min(1, x)));
    },
    [seek]
  );

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="w-full px-4 space-y-2">
      {/* Play button + time */}
      <div className="flex items-center gap-4">
        <button
          onClick={isPlaying ? pause : play}
          className="w-10 h-10 flex items-center justify-center rounded-full bg-[#7C3AED] hover:bg-[#6D28D9] shadow-[0_0_20px_rgba(124,58,237,0.4)] transition"
        >
          {isPlaying ? (
            <svg width="14" height="16" viewBox="0 0 14 16" fill="white">
              <rect x="1" y="0" width="4" height="16" rx="1" />
              <rect x="9" y="0" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg width="14" height="16" viewBox="0 0 14 16" fill="white">
              <path d="M1 1.5L13 8L1 14.5V1.5Z" />
            </svg>
          )}
        </button>
        <span className="text-[#9CA3AF] text-xs font-mono">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>

      {/* Scrubber bar */}
      <div
        ref={barRef}
        className="relative h-2 bg-[#1A1730] rounded-full cursor-pointer group"
        onClick={handleBarClick}
      >
        {/* Progress fill */}
        <div
          className="absolute top-0 left-0 h-full rounded-full bg-gradient-to-r from-[#7C3AED] to-[#A78BFA] transition-all duration-100"
          style={{ width: `${progress * 100}%` }}
        />
        {/* Thumb */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition"
          style={{ left: `calc(${progress * 100}% - 8px)` }}
        />
      </div>

      {/* Year labels */}
      <div className="relative h-5">
        {YEAR_LABELS.map((y) => (
          <span
            key={y.year}
            className={`absolute text-xs font-medium transition-colors ${
              progress >= y.position ? "text-[#7C3AED]" : "text-[#9CA3AF]/50"
            }`}
            style={{ left: `${y.position * 100}%`, transform: "translateX(-50%)" }}
          >
            {y.year}
          </span>
        ))}
      </div>
    </div>
  );
}
```
### Interactive Compounding Calculator (`components/CompoundingCalculator.tsx`)
This replaces the standalone calculator by integrating with the backtest data. Users can adjust starting capital to see projected returns using actual CAGR from the backtest:[^1]

```typescript
// components/CompoundingCalculator.tsx
"use client";

import { useState, useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { useTranslation } from "react-i18next";

const PRESETS = [
  { id: "student", label: "College Student ($1k)", capital: 1000, monthly: 50, cagr: 20, years: 10 },
  { id: "hustle", label: "Side Hustle ($5k)", capital: 5000, monthly: 100, cagr: 20, years: 15 },
  { id: "serious", label: "Serious Investor ($25k)", capital: 25000, monthly: 200, cagr: 20, years: 20 },
  { id: "tb5k", label: "TB Actual ($5k Track)", capital: 5000, monthly: 0, cagr: 23.4, years: 7, highlight: true },
  { id: "tb25k", label: "TB Actual ($25k Track)", capital: 25000, monthly: 0, cagr: 24.6, years: 7, highlight: true },
];

const CAGR_OPTIONS = [15, 20, 25, 30];

export function CompoundingCalculator() {
  const { t } = useTranslation();
  const [startingCapital, setStartingCapital] = useState(5000);
  const [monthlyAddition, setMonthlyAddition] = useState(0);
  const [cagr, setCagr] = useState(20);
  const [years, setYears] = useState(20);

  const chartData = useMemo(() => {
    const monthlyRate = Math.pow(1 + cagr / 100, 1 / 12) - 1;
    const data = [];
    let totalContributions = startingCapital;
    let totalValue = startingCapital;

    for (let year = 0; year <= years; year++) {
      data.push({
        year: `Yr ${year}`,
        principal: Math.round(totalContributions),
        total: Math.round(totalValue),
        growth: Math.round(totalValue - totalContributions),
      });
      for (let month = 0; month < 12; month++) {
        totalValue = totalValue * (1 + monthlyRate) + monthlyAddition;
        totalContributions += monthlyAddition;
      }
    }
    return data;
  }, [startingCapital, monthlyAddition, cagr, years]);

  const projectedValue = chartData[chartData.length - 1]?.total || 0;

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    setStartingCapital(preset.capital);
    setMonthlyAddition(preset.monthly);
    setCagr(preset.cagr);
    setYears(preset.years);
  };

  return (
    <div className="w-full max-w-5xl mx-auto bg-[#1A1730] rounded-2xl border border-white/10 p-6 md:p-8">
      <h2 className="text-2xl font-bold text-white mb-1">
        {t("calculator.title", "Interactive Compounding Calculator")}
      </h2>
      <p className="text-[#9CA3AF] text-sm mb-6">
        {t("calculator.subtitle", "The math of 20% annualized growth.")}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Controls */}
        <div className="space-y-6">
          {/* Starting Capital */}
          <div>
            abel className="text-[#9CA3AF] text-sm">
              {t("calculator.startingCapital", "Starting Capital")}
            </label>
            <input
              type="range"
              min={1000}
              max={100000}
              step={500}
              value={startingCapital}
              onChange={(e) => setStartingCapital(Number(e.target.value))}
              className="w-full mt-2 accent-[#7C3AED]"
            />
            <p className="text-white text-xl font-mono mt-1">
              ${startingCapital.toLocaleString()}
            </p>
          </div>

          {/* Monthly Addition */}
          <div>
            abel className="text-[#9CA3AF] text-sm">
              {t("calculator.monthly", "Monthly Addition")}
            </label>
            <input
              type="range"
              min={0}
              max={500}
              step={25}
              value={monthlyAddition}
              onChange={(e) => setMonthlyAddition(Number(e.target.value))}
              className="w-full mt-2 accent-[#7C3AED]"
            />
            <p className="text-white text-xl font-mono mt-1">
              ${monthlyAddition}
            </p>
          </div>

          {/* CAGR */}
          <div>
            abel className="text-[#9CA3AF] text-sm">
              {t("calculator.cagr", "Expected CAGR (%)")}
            </label>
            <div className="flex gap-2 mt-2">
              {CAGR_OPTIONS.map((rate) => (
                <button
                  key={rate}
                  onClick={() => setCagr(rate)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                    cagr === rate
                      ? "bg-[#7C3AED] text-white"
                      : "bg-[#0D0B1A] text-[#9CA3AF] border border-white/10 hover:border-[#7C3AED]/50"
                  }`}
                >
                  {rate}%
                </button>
              ))}
            </div>
          </div>

          {/* Time Horizon */}
          <div>
            abel className="text-[#9CA3AF] text-sm">
              {t("calculator.horizon", "Time Horizon (Years)")}
            </label>
            <input
              type="range"
              min={1}
              max={30}
              step={1}
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
              className="w-full mt-2 accent-[#7C3AED]"
            />
            <p className="text-white text-xl font-mono mt-1">{years} Years</p>
          </div>
        </div>

        {/* Chart + Projected Value */}
        <div>
          <p className="text-[#9CA3AF] text-sm">
            {t("calculator.projected", "Projected Future Value")}
          </p>
          <p className="text-4xl font-bold font-mono text-white mb-4">
            ${projectedValue.toLocaleString()}
          </p>

          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={chartData}>
              <defs>
                earGradient id="principalGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7C3AED" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#7C3AED" stopOpacity={0.05} />
                </linearGradient>
                earGradient id="growthGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="year"
                tick={{ fill: "#9CA3AF", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#9CA3AF", fontSize: 10 }}
                tickFormatter={(v: number) =>
                  v >= 1000000
                    ? `$${(v / 1000000).toFixed(1)}M`
                    : `$${(v / 1000).toFixed(0)}k`
                }
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#1A1730",
                  border: "1px solid rgba(124,58,237,0.3)",
                  borderRadius: 8,
                }}
                labelStyle={{ color: "#9CA3AF" }}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="principal"
                stackId="1"
                stroke="#7C3AED"
                fill="url(#principalGrad)"
                name="Principal"
              />
              <Area
                type="monotone"
                dataKey="growth"
                stackId="1"
                stroke="#10B981"
                fill="url(#growthGrad)"
                name="True Growth"
              />
            </AreaChart>
          </ResponsiveContainer>

          <p className="text-[#9CA3AF] text-xs mt-2">
            *Based on historical backtest averages. Past performance does not
            guarantee future results.
          </p>
        </div>
      </div>

      {/* Preset Scenario Buttons */}
      <div className="flex flex-wrap gap-2 mt-6 justify-center">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            onClick={() => applyPreset(preset)}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition ${
              preset.highlight
                ? "border border-[#10B981] text-[#10B981] hover:bg-[#10B981]/10"
                : "text-[#9CA3AF] hover:text-white hover:bg-white/5"
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```
### Main Landing Page (`app/page.tsx`)
```typescript
// app/page.tsx
"use client";

import dynamic from "next/dynamic";
import { Header } from "@/components/Header";
import { NarrationProvider } from "@/contexts/NarrationContext";
import { TimelineScrubber } from "@/components/TimelineScrubber";
import { TradeFeed } from "@/components/TradeFeed";

// Dynamic import Recharts components (no SSR)
const EquityCurveChart = dynamic(
  () =>
    import("@/components/EquityCurveChart").then((mod) => mod.EquityCurveChart),
  { ssr: false }
);

const CompoundingCalculator = dynamic(
  () =>
    import("@/components/CompoundingCalculator").then(
      (mod) => mod.CompoundingCalculator
    ),
  { ssr: false }
);

export default function LandingPage() {
  return (
    <NarrationProvider>
      <Header />

      {/* Hero: Single Viewport (100vh) */}
      <main className="pt-12 h-screen flex flex-col">
        {/* Zone 1: Equity Curve Chart (55%) */}
        <section className="flex-[^55] min-h-0">
          <EquityCurveChart />
        </section>

        {/* Zone 2: Trade Feed (20%) */}
        <section className="flex-[^20] min-h-0 border-t border-white/5">
          <TradeFeed />
        </section>

        {/* Zone 3: Timeline + Play Button (25%) */}
        <section className="flex-[^25] min-h-0 flex flex-col justify-center border-t border-white/5 pb-4">
          <TimelineScrubber />
        </section>
      </main>

      {/* Below the fold: Calculator */}
      <section className="py-16 px-4">
        <CompoundingCalculator />
      </section>
    </NarrationProvider>
  );
}
```

***
## ElevenLabs Voice Narration Setup
### Audio Generation Script (`scripts/generateNarration.ts`)
This build-time script generates the three MP3 files using the ElevenLabs JavaScript SDK:[^11][^10]

```typescript
// scripts/generateNarration.ts
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";
import fs from "fs";
import path from "path";

const client = new ElevenLabsClient({
  apiKey: process.env.ELEVENLABS_API_KEY!,
});

interface NarrationConfig {
  lang: string;
  voiceId: string; // Choose from ElevenLabs voice library
  script: string;
}

const narrations: NarrationConfig[] = [
  {
    lang: "en",
    voiceId: "JBFqnCBsd6RMkjVDRZzb", // Replace with chosen EN voice
    script: `Markets overreact. TurboBounce catches the snapback. This is seven years of real data, one thousand and seventy eight trades, starting with just five thousand dollars.

In 2019, the engine found 183 mean-reversion opportunities in its first year, growing the account 48 percent to seven thousand four hundred dollars. The AI identified moments when stocks stretched too far from their baseline and executed contrarian trades right as momentum exhausted itself.

2020 brought COVID chaos. While markets panicked, TurboBounce adapted. The volatility-adaptive engine flipped from buying options to selling premium, staying profitable with nine hundred eighty seven dollars in gains while others lost everything.

2021 was the breakout. Five thousand eight hundred forty seven dollars in profit. The account nearly doubled to fourteen thousand two hundred thirty six. The system was firing on all cylinders, scanning 40 plus stocks for the top 1 percent most mathematically skewed opportunities.

Then 2022 hit. TQQQ lost 79 percent. Our worst year: negative 35 percent. But here's the key, the crash filter protected capital. When assets entered true structural downtrends, the system stopped buying dips entirely. It bought deep in the money puts instead, cushioning the blow.

Those who stayed saw 2023 return plus 43 percent and 2024 deliver plus 45 percent. The small account slingshot kicked in. Once capital cleared fifteen thousand, the system unlocked safer tech LEAPS and resumed its steady growth curve.

By 2025, five thousand dollars became twenty one thousand eight hundred eleven. Plus 336 percent total return. The secret isn't any single trade, it's compounding. AI-driven mean reversion, hands-free, starting from as low as five thousand. Your capital, our engine. Start compounding today.`,
  },
  {
    lang: "es",
    voiceId: "REPLACE_WITH_ES_VOICE_ID",
    script: `Los mercados sobrerreaccionan. TurboBounce captura el rebote. Estos son siete años de datos reales...`, // Full Spanish translation
  },
  {
    lang: "zh",
    voiceId: "REPLACE_WITH_ZH_VOICE_ID",
    script: `市场总是过度反应。TurboBounce捕捉回弹。这是七年的真实数据...`, // Full Chinese translation
  },
];

async function generateAll() {
  const outDir = path.resolve("public/audio");
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  for (const config of narrations) {
    console.log(`Generating ${config.lang} narration...`);

    const audioStream = await client.textToSpeech.convert(config.voiceId, {
      text: config.script,
      modelId: "eleven_multilingual_v2",
      outputFormat: "mp3_44100_128",
      voiceSettings: {
        stability: 0.5,
        similarityBoost: 0.8,
        style: 0.15,
        useSpeakerBoost: true,
      },
    });

    const chunks: Buffer[] = [];
    for await (const chunk of audioStream) {
      chunks.push(Buffer.from(chunk));
    }

    const outputPath = path.join(outDir, `narration_${config.lang}.mp3`);
    fs.writeFileSync(outputPath, Buffer.concat(chunks));
    console.log(`✅ Saved: ${outputPath}`);
  }
}

generateAll().catch(console.error);
```

Run with:
```bash
ELEVENLABS_API_KEY=your_key npx tsx scripts/generateNarration.ts
```
### Narration Script Timing Guide
| Segment | Time | EN Content | Chart State |
|---------|------|------------|-------------|
| Intro | 0:00–0:15 | "Markets overreact. TurboBounce catches the snapback..." | Chart appears, $5K starting line |
| 2019 | 0:15–0:30 | "Starting with just $5,000... 183 trades, +48%" | Curve climbs to $7.4K |
| 2020 | 0:30–0:50 | "COVID chaos. Engine adapted, +$987" | Curve wobbles, green but slower |
| 2021 | 0:50–1:15 | "Breakout year — $5,847 profit, nearly doubled" | Steep climb, trade velocity increases |
| 2022 | 1:15–1:45 | "TQQQ lost 79%. Our worst: -35%. Crash filter..." | Red overlay, curve drops, shield icon |
| Recovery | 1:45–2:15 | "2023: +43%, 2024: +45%. Patience rewarded." | Sharp recovery, green burst |
| 2025+CTA | 2:15–3:00 | "$5K became $21,811. +336%. Start compounding." | Full curve revealed, CTA |

***
## Referral System Integration
The referral button opens a modal with the **Give $15, Get $15** reward structure:[^1]

| Tier | Referrals | Referrer Gets | Friend Gets |
|------|-----------|---------------|-------------|
| Standard | 1–4 | $15 credit | $15 off first month |
| Power Referrer | 5–9 | $20 credit | $15 off first month |
| Ambassador | 10+ | $25 + free month Compounder | $15 + free week |

The system integrates with **Rewardful** ($49/mo) or **Refgrow** ($29/mo), both Stripe-connected, with automated credit issuance after a 30-day qualification period.[^1]

***
## Vercel Deployment Setup
### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "TurboBounce landing page MVP"
git remote add origin https://github.com/your-org/turbobounce-landing.git
git push -u origin main
```
### Step 2: Connect Vercel
1. Go to [vercel.com](https://vercel.com) → Import Project → Select the GitHub repo.[^12][^16]
2. Framework preset: **Next.js** (auto-detected).
3. Add all environment variables from `.env.local` in the Vercel dashboard under Settings → Environment Variables.[^17]
4. Deploy. Vercel runs `npm run build` → `next build` automatically.[^12]
### Step 3: Custom Domain
1. In Vercel → Settings → Domains → Add `turbobounce.com`.
2. Update DNS: Add CNAME record pointing to `cname.vercel-dns.com`.[^16]
3. Vercel auto-provisions SSL.
### Build Configuration
```json
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    domains: ['turbobounce.com'],
  },
  // Ensure static audio files are served
  async headers() {
    return [
      {
        source: '/audio/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
```

***
## Google Antigravity Prompts
These prompts are designed for efficient agent-driven development in Antigravity IDE. Use **Planning mode** for complex tasks and **Fast mode** for quick fixes.[^3][^4]
### Prompt 1: Project Scaffold (Planning Mode)
> You are a senior TypeScript engineer. Create a Next.js 14 App Router project with TypeScript and Tailwind CSS. Initialize the following:
> 1. Tailwind config with custom dark theme tokens: bg-primary (#0D0B1A), bg-card (#1A1730), accent-purple (#7C3AED), success (#10B981), danger (#EF4444), font-mono (JetBrains Mono).
> 2. Install and configure: recharts, framer-motion, react-i18next, i18next-browser-languagedetector, i18next-http-backend, @privy-io/react-auth, @supabase/supabase-js, clsx, @fontsource/jetbrains-mono.
> 3. Create the folder structure: components/, contexts/, hooks/, lib/, data/, public/audio/, public/locales/{en,es,zh}/, scripts/.
> 4. Create placeholder translation.json files for en, es, zh with keys: nav.login, nav.refer, hero.title, hero.subtitle, calculator.title, calculator.subtitle, calculator.startingCapital, calculator.monthly, calculator.cagr, calculator.horizon, calculator.projected.
> 5. Create lib/i18n.ts with i18next config (fallback: en, supported: en/es/zh).
> 6. Create app/layout.tsx wrapping children in PrivyProvider and I18nProvider.
> Do NOT create any visual components yet. Focus on infrastructure only.
### Prompt 2: Header and Language Bar (Fast Mode)
> Create three components in the components/ folder:
> 1. Header.tsx — Fixed 48px header with bg-[#0D0B1A]/90 backdrop-blur. Flexbox layout: ReferralButton left, LanguageBar center, PrivyLoginButton right.
> 2. LanguageBar.tsx — Pill-shaped toggle with EN, ES, 中文 buttons. Use react-i18next's i18n.changeLanguage(). Active language gets bg-[#7C3AED] with purple glow shadow.
> 3. PrivyLoginButton.tsx — Uses usePrivy() hook. Shows "Login" when unauthenticated with purple border button. Shows email snippet when authenticated.
> Use the established dark theme tokens. Mark as "use client".
### Prompt 3: Narration Context (Fast Mode)
> Create contexts/NarrationContext.tsx — a React context provider that:
> 1. Manages an HTMLAudioElement loading from /audio/narration_{lang}.mp3 based on i18n.language.
> 2. Exposes: progress (0–1), isPlaying, currentYear, currentTradeIndex, duration, currentTime, play(), pause(), seek(normalizedPosition).
> 3. Uses timeupdate events to set progress = currentTime / duration.
> 4. On language change, syncs position: saves normalized progress, loads new audio, sets currentTime to saved progress × new duration.
> 5. Maps currentTradeIndex from progress × 1078. Maps currentYear from trade index to year boundaries.
> All 1,078 trades span 2019–2025 with these trade-count boundaries: 2019 (0–182), 2020 (183–355), 2021 (356–533), 2022 (534–620), 2023 (621–798), 2024 (799–945), 2025 (946–1077).
### Prompt 4: Equity Curve Chart (Planning Mode)
> Create components/EquityCurveChart.tsx — a "use client" component that:
> 1. Imports pre-built equity_curve.json (array of {index, exitDate, accountValue, pnl, cumulativePnl, year, normalizedTime}).
> 2. Subscribes to useNarration() context to get progress.
> 3. Slices the data array: visibleData = equityCurve.slice(0, ceil(progress × length)).
> 4. Renders a Recharts AreaChart with: green gradient fill (#10B981), XAxis showing years, YAxis showing $k, ReferenceLine at $5,000 for principal.
> 5. During 2022 (currentYear === 2022), switches gradient and stroke to red (#EF4444) and shows a "Crash Filter Active" badge with shield emoji.
> 6. Shows animated account value counter (top-left, JetBrains Mono, Framer Motion fade).
> 7. Custom tooltip component showing: date, account value, trade P&L, cumulative P&L, year.
> 8. Dynamic import with {ssr: false}. Use ResponsiveContainer for full width/height.
### Prompt 5: Trade Feed + Timeline Scrubber (Fast Mode)
> Create two components:
> 1. TradeFeed.tsx — Shows the 5 most recent trades up to currentTradeIndex from useNarration(). Each trade card shows: Symbol, Strategy, Direction badge (green BULLISH / red BEARISH), P&L with color. Latest trade is highlighted with purple border. Uses Framer Motion for entrance animations.
> 2. TimelineScrubber.tsx — A play/pause button (purple circle, SVG icons) + full-width scrubber bar. Bar fills with purple gradient based on progress. Year labels (2019–2025) at proportional positions. Clicking the bar calls seek(). Shows currentTime / duration in mono font.
### Prompt 6: Compounding Calculator (Planning Mode)
> Create components/CompoundingCalculator.tsx — an interactive calculator with:
> 1. Sliders for: Starting Capital ($1K–$100K, step $500), Monthly Addition ($0–$500, step $25), Time Horizon (1–30 years).
> 2. CAGR toggle buttons: 15%, 20%, 25%, 30%.
> 3. Preset scenario buttons: College Student ($1K), Side Hustle ($5K), Serious Investor ($25K), TB Actual $5K Track (capital=5000, monthly=0, cagr=23.4, years=7), TB Actual $25K Track (capital=25000, monthly=0, cagr=24.6, years=7). TB Actual presets have green borders.
> 4. Output: Stacked AreaChart with Principal (purple) and True Growth (green). Large projected value counter.
> 5. Disclaimer: "Based on historical backtest averages. Past performance does not guarantee future results."
> All in dark theme tokens. Use react-i18next t() for all labels.
### Prompt 7: Main Page Assembly (Fast Mode)
> Create app/page.tsx — a "use client" page that:
> 1. Wraps everything in NarrationProvider.
> 2. Renders Header at top.
> 3. Main section: h-screen flex-col with three zones — EquityCurveChart (flex-), TradeFeed (flex-), TimelineScrubber (flex-).[^18][^19][^20]
> 4. Below the fold: CompoundingCalculator in a py-16 px-4 section.
> 5. Use dynamic imports with {ssr: false} for EquityCurveChart and CompoundingCalculator.
### Prompt 8: Testing and Polish (Planning Mode)
> Audit the entire project:
> 1. Mobile-responsive: Test all components at 375px, 768px, 1024px, 1440px widths. Fix any overflow or layout breaks.
> 2. Accessibility: Add aria-labels to all buttons, ensure color contrast meets WCAG AA, add keyboard navigation for scrubber and calculator sliders.
> 3. Performance: Lazy-load CompoundingCalculator. Add Cache-Control headers for /audio/* in next.config.js. Verify Lighthouse score > 90.
> 4. Fix any TypeScript errors. Ensure all imports resolve. Run npm run build and fix all build errors.

***
## Trading System Integration
Once a visitor converts through the landing page:[^1][^5]

1. **Privy session** establishes user identity → stored in Supabase.
2. **Plan selection** (Observer $0 / Builder $29 / Compounder $49) → Stripe subscription created.
3. **Broker connect** → tastytrade OAuth via `@tastytrade/api` SDK → account streaming begins.
4. **Dashboard mirrors** the existing layout: Net Liquidating Value hero, Your Progress gamification cards, Trade Signals feed, Auto-Approve toggle.
5. **Referral tracking** → unique link generated at signup, tracked via Rewardful/Refgrow → credits auto-issued after 30-day qualification.

The compounding calculator's projected values from the landing page persist to the dashboard's "Projected Value Panel," creating continuity between the marketing experience and the product.[^1]

***
## Development Phases
### Phase 1: Foundation (Weeks 1–3)
- Next.js project setup with Tailwind dark theme tokens
- i18next configuration with EN/ES/ZH translation files
- Header bar: Language selector, Privy login button, Refer a Friend button
- Trade CSV preprocessing script → equity_curve.json + trade_feed.json
- Static equity curve chart with Recharts (no animation yet)
- Trade feed component with card design
### Phase 2: Animation + Voice (Weeks 4–6)
- NarrationContext provider with shared progress state
- Framer Motion animated equity curve (progressive reveal)
- Trade feed auto-scroll synced to timeline progress
- ElevenLabs narration generation (EN/ES/ZH — 3 audio files)
- Audio playback synced with timeline scrubber
- Subtitle overlay synced to narration timestamps
### Phase 3: Calculator + Auth (Weeks 7–9)
- Interactive compounding calculator with Recharts stacked area chart
- Pre-set scenario buttons (College Student, Side Hustle, TB Actual, etc.)
- Privy authentication integration (login modal, session management)
- Referral modal with share buttons and reward tier display
- Post-login redirect to dashboard with tastytrade OAuth flow
### Phase 4: Polish + Deploy (Weeks 10–12)
- 2022 crash sequence special effects (red overlay, shield icon)
- Mobile-responsive layout across all viewport sizes
- Performance optimization (Lighthouse 90+)
- Cross-browser testing (Chrome, Safari, Firefox, Edge)
- Vercel deployment with custom domain
- Analytics integration (PostHog/Mixpanel)

***
## Performance Budget
| Metric | Target | Approach |
|--------|--------|----------|
| First Contentful Paint | < 1.2s | SSR landing page, critical CSS inline |
| Largest Contentful Paint | < 2.5s | Pre-generated chart SVG, optimized images |
| Time to Interactive | < 3.0s | Code-split audio/animation, lazy-load calculator |
| Audio File Size (per language) | < 3MB | ElevenLabs MP3 at 128kbps, ~3 min |
| Total Page Weight | < 5MB | Compressed assets, CDN delivery via Vercel Edge |
| Lighthouse Score | 90+ | Performance, Accessibility, Best Practices, SEO |

***
## Cost Estimate
| Item | Monthly | Annual | Notes |
|------|---------|--------|-------|
| ElevenLabs Voice Generation | One-time $5 | — | 3 × 3-min narrations at ~$0.12/min[^10] |
| Vercel Hosting (Pro) | $20 | $240 | Edge CDN, serverless functions[^12] |
| Supabase (Free → Pro) | $0–$25 | $0–$300 | Scales with user count |
| Privy Authentication | $0–$99 | $0–$1,188 | Free tier for < 1K users[^9] |
| Rewardful Referral Tracking | $49 | $588 | Stripe-integrated |
| Stripe Payment Processing | 2.9% + $0.30/tx | Variable | Standard SaaS rate |
| **Total (Pre-Revenue)** | **~$94** | **~$1,128** | Scales with adoption |

---

## References

1. [TurboBounce-Landing-Page-Implementation-Plan.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/0852447e-8902-4f3a-a27a-ad47ae06e2b0/TurboBounce-Landing-Page-Implementation-Plan.pdf?AWSAccessKeyId=ASIA2F3EMEYEX23Y5GWT&Signature=ZpJzmztDmg6Ubs7LYjE4%2BmKBSPo%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEKn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQCEE47yg8tzEfsvb%2FzeDuUpdvWQ5ErBOnFlnNYxCxQMEwIhALM3zjCO0qzbsLeJTNh%2F8YeaE8EQSII6udbYf46vsTuwKvMECHIQARoMNjk5NzUzMzA5NzA1IgxuFGOPekPK3fXAo18q0AQ89tOgw1qTSTxTM0Wk49Psw9B%2FjK%2FQuszGu3gXmHby5stpgLVXVDAR4q6HwDs29kVvz6IxnQNYb%2FEMdhE7Q3W2vtqLkJwdPDy%2B0n8WpWPvz7V8NoXjjOYs%2F%2Byk6ADS%2FuRqLnljZogGR%2FgUKfrfo4A%2FxZnjN88iD5UEMQvFISw%2Fp8m2XTSta6y0F2NbSiNDD3Igl6AdOXPy%2FxQGFj2YZRxKfSl8KvkQr4ZmVvm2ol2OtWshZrJZU%2BY2VGjiWzqgfqb68cnRXBd%2B6p3NIAYmE6qid9WldMi0Rz6Tg4NTyTFK07AVw3UbMZD5m2EQP4IQtTyaxmXzD3T7gBqOfJd5AoTNgmuDAYv%2B%2FGVT8%2BK1PqDX8DIEoR7VEaEazZoedCzqag99HQTLM%2FGN%2BZAUGylShJ5QXWZecuFvD18Eyn4j4hckJe0uF2OtA5%2F3fk6iq4LR1JmM4qG0SRw%2BLybNGCGKodkOc%2BHJm4KkXV%2B4QbUOAnIWldDKezAboamf299MB74qVeri0t7%2FU6UDuCvRLqNwyI467VjtJ6Nm6PA3NGi2Wp8wFforw8KCdfEzmfpObFl32kL83DRSlTrydeHtLF4iZf%2FtRrK6KCBdpiauid4hOqLIylu23CEgINVZDtBjCp%2Fv5P7wPJr2Wv2fSq0aSbBmAxibVsUojZ4pusT6Dn4uh5l29Jd85oNxipoBV32RV%2B9E66TpmUWDUW26S246UND5Z3C9MGUXFBTuexvfmrvJ9rA6TUHrctBzQ0VFjy%2BTRYilxtT7jf%2FQU6633JvyzVKzhORaMNzRkc0GOpcBv3TfmspMFl%2BruI9WngkY29F30wkjQ2OypdR20GzUS6RU4MLCW1x%2Br3VOYPoUz3%2BR0L9CDbTmMF5NVVzcD4WZ3Ws1yS4KKJ%2BC0q5pCbN5s3D1EECGhfA4wNJA2ia5VSBOM3hFEAl5oO%2BjvUj1yy3NI2Lb%2BkTFEOJ%2Fcx1JYwLBVZXu6bpA2k%2FsPiNo7vklbNeSDWSDbs%2FSXg%3D%3D&Expires=1772387352) - This plan details the implementation of a single-page animated
landing experience for TurboBounce th...

2. [TURBOBOUNCE-OPTIONS-5K-COMPOUNDING-ACCOUNT.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/31a931cc-7f1f-4e55-8187-a6085c75d724/TURBOBOUNCE-OPTIONS-5K-COMPOUNDING-ACCOUNT.pdf?AWSAccessKeyId=ASIA2F3EMEYEX23Y5GWT&Signature=bTiz7EI1z3Qhdz%2BTgTMO25gkQr0%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEKn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQCEE47yg8tzEfsvb%2FzeDuUpdvWQ5ErBOnFlnNYxCxQMEwIhALM3zjCO0qzbsLeJTNh%2F8YeaE8EQSII6udbYf46vsTuwKvMECHIQARoMNjk5NzUzMzA5NzA1IgxuFGOPekPK3fXAo18q0AQ89tOgw1qTSTxTM0Wk49Psw9B%2FjK%2FQuszGu3gXmHby5stpgLVXVDAR4q6HwDs29kVvz6IxnQNYb%2FEMdhE7Q3W2vtqLkJwdPDy%2B0n8WpWPvz7V8NoXjjOYs%2F%2Byk6ADS%2FuRqLnljZogGR%2FgUKfrfo4A%2FxZnjN88iD5UEMQvFISw%2Fp8m2XTSta6y0F2NbSiNDD3Igl6AdOXPy%2FxQGFj2YZRxKfSl8KvkQr4ZmVvm2ol2OtWshZrJZU%2BY2VGjiWzqgfqb68cnRXBd%2B6p3NIAYmE6qid9WldMi0Rz6Tg4NTyTFK07AVw3UbMZD5m2EQP4IQtTyaxmXzD3T7gBqOfJd5AoTNgmuDAYv%2B%2FGVT8%2BK1PqDX8DIEoR7VEaEazZoedCzqag99HQTLM%2FGN%2BZAUGylShJ5QXWZecuFvD18Eyn4j4hckJe0uF2OtA5%2F3fk6iq4LR1JmM4qG0SRw%2BLybNGCGKodkOc%2BHJm4KkXV%2B4QbUOAnIWldDKezAboamf299MB74qVeri0t7%2FU6UDuCvRLqNwyI467VjtJ6Nm6PA3NGi2Wp8wFforw8KCdfEzmfpObFl32kL83DRSlTrydeHtLF4iZf%2FtRrK6KCBdpiauid4hOqLIylu23CEgINVZDtBjCp%2Fv5P7wPJr2Wv2fSq0aSbBmAxibVsUojZ4pusT6Dn4uh5l29Jd85oNxipoBV32RV%2B9E66TpmUWDUW26S246UND5Z3C9MGUXFBTuexvfmrvJ9rA6TUHrctBzQ0VFjy%2BTRYilxtT7jf%2FQU6633JvyzVKzhORaMNzRkc0GOpcBv3TfmspMFl%2BruI9WngkY29F30wkjQ2OypdR20GzUS6RU4MLCW1x%2Br3VOYPoUz3%2BR0L9CDbTmMF5NVVzcD4WZ3Ws1yS4KKJ%2BC0q5pCbN5s3D1EECGhfA4wNJA2ia5VSBOM3hFEAl5oO%2BjvUj1yy3NI2Lb%2BkTFEOJ%2Fcx1JYwLBVZXu6bpA2k%2FsPiNo7vklbNeSDWSDbs%2FSXg%3D%3D&Expires=1772387352) - 🟢 TURBOBOUNCE OPTIONS: $5K COMPOUNDING ACCOUNT Testing Period: 2019 to 
2026 (6 Full Years) Starting...

3. [How to Set Up and Use Google Antigravity - Codecademy](https://www.codecademy.com/article/how-to-set-up-and-use-google-antigravity) - Google Antigravity is Google's free AI-powered IDE that lets developers build software using autonom...

4. [Best Prompts for Coding Inside Antigravity (Top 50) - Skywork.ai](https://skywork.ai/blog/agent/best-prompts-antigravity/) - A curated list of the best prompts for Antigravity coding tasks.

5. [TurboBounce_Overview.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/03944e93-7822-46b0-9158-9db14c491d0f/TurboBounce_Overview.pdf?AWSAccessKeyId=ASIA2F3EMEYEX23Y5GWT&Signature=gumkKhTTNX9GehxFkAdlj0CPluc%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEKn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQCEE47yg8tzEfsvb%2FzeDuUpdvWQ5ErBOnFlnNYxCxQMEwIhALM3zjCO0qzbsLeJTNh%2F8YeaE8EQSII6udbYf46vsTuwKvMECHIQARoMNjk5NzUzMzA5NzA1IgxuFGOPekPK3fXAo18q0AQ89tOgw1qTSTxTM0Wk49Psw9B%2FjK%2FQuszGu3gXmHby5stpgLVXVDAR4q6HwDs29kVvz6IxnQNYb%2FEMdhE7Q3W2vtqLkJwdPDy%2B0n8WpWPvz7V8NoXjjOYs%2F%2Byk6ADS%2FuRqLnljZogGR%2FgUKfrfo4A%2FxZnjN88iD5UEMQvFISw%2Fp8m2XTSta6y0F2NbSiNDD3Igl6AdOXPy%2FxQGFj2YZRxKfSl8KvkQr4ZmVvm2ol2OtWshZrJZU%2BY2VGjiWzqgfqb68cnRXBd%2B6p3NIAYmE6qid9WldMi0Rz6Tg4NTyTFK07AVw3UbMZD5m2EQP4IQtTyaxmXzD3T7gBqOfJd5AoTNgmuDAYv%2B%2FGVT8%2BK1PqDX8DIEoR7VEaEazZoedCzqag99HQTLM%2FGN%2BZAUGylShJ5QXWZecuFvD18Eyn4j4hckJe0uF2OtA5%2F3fk6iq4LR1JmM4qG0SRw%2BLybNGCGKodkOc%2BHJm4KkXV%2B4QbUOAnIWldDKezAboamf299MB74qVeri0t7%2FU6UDuCvRLqNwyI467VjtJ6Nm6PA3NGi2Wp8wFforw8KCdfEzmfpObFl32kL83DRSlTrydeHtLF4iZf%2FtRrK6KCBdpiauid4hOqLIylu23CEgINVZDtBjCp%2Fv5P7wPJr2Wv2fSq0aSbBmAxibVsUojZ4pusT6Dn4uh5l29Jd85oNxipoBV32RV%2B9E66TpmUWDUW26S246UND5Z3C9MGUXFBTuexvfmrvJ9rA6TUHrctBzQ0VFjy%2BTRYilxtT7jf%2FQU6633JvyzVKzhORaMNzRkc0GOpcBv3TfmspMFl%2BruI9WngkY29F30wkjQ2OypdR20GzUS6RU4MLCW1x%2Br3VOYPoUz3%2BR0L9CDbTmMF5NVVzcD4WZ3Ws1yS4KKJ%2BC0q5pCbN5s3D1EECGhfA4wNJA2ia5VSBOM3hFEAl5oO%2BjvUj1yy3NI2Lb%2BkTFEOJ%2Fcx1JYwLBVZXu6bpA2k%2FsPiNo7vklbNeSDWSDbs%2FSXg%3D%3D&Expires=1772387352) - TurboBounce The Next Generation of Mean 
Reversion Trading 
Executive Summary 
TurboBounce is a soph...

6. [Getting Started: Installation - Next.js](https://nextjs.org/docs/app/getting-started/installation) - To add TypeScript to your project, rename a file to .ts / .tsx and run next dev . Next.js will autom...

7. [Comprehensive Guide: Using Recharts in Next.js with TypeScript - Edupala](https://edupala.com/comprehensive-guide-using-recharts-in-next-js-with-typescript/) - Learn how to integrate Recharts with Next.js and TypeScript. This guide covers setup, best practices...

8. [How to use Next.js and Recharts to build an information dashboard](https://ably.com/blog/informational-dashboard-with-nextjs-and-recharts) - Discover how to use Next.js and Recharts (a React chart library) to build an information dashboard w...

9. [Integrating with tRPC](https://docs.privy.io/recipes/trpc)

10. [The official JavaScript (Node) library for the ElevenLabs API. - GitHub](https://github.com/elevenlabs/elevenlabs-js) - The official Node SDK for ElevenLabs. ElevenLabs brings the most compelling, rich and lifelike voice...

11. [elevenlabs-js/reference.md at main · elevenlabs/elevenlabs-js](http://github.com/elevenlabs/elevenlabs-js/blob/main/reference.md) - The official JavaScript (Node) library for ElevenLabs Text to Speech. - elevenlabs/elevenlabs-js

12. [Next.js on Vercel](https://vercel.com/docs/frameworks/full-stack/nextjs) - If you already have a project with Next.js, install Vercel CLI and run the vercel command from your ...

13. [turbobounce_options_5k_all_trades.csv](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/e61c65f7-dedf-4057-be32-90846397feb4/turbobounce_options_5k_all_trades.csv?AWSAccessKeyId=ASIA2F3EMEYEX23Y5GWT&Signature=90wTpTd4JoG5V8hk%2FUeWPSu3%2BOI%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEKn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQCEE47yg8tzEfsvb%2FzeDuUpdvWQ5ErBOnFlnNYxCxQMEwIhALM3zjCO0qzbsLeJTNh%2F8YeaE8EQSII6udbYf46vsTuwKvMECHIQARoMNjk5NzUzMzA5NzA1IgxuFGOPekPK3fXAo18q0AQ89tOgw1qTSTxTM0Wk49Psw9B%2FjK%2FQuszGu3gXmHby5stpgLVXVDAR4q6HwDs29kVvz6IxnQNYb%2FEMdhE7Q3W2vtqLkJwdPDy%2B0n8WpWPvz7V8NoXjjOYs%2F%2Byk6ADS%2FuRqLnljZogGR%2FgUKfrfo4A%2FxZnjN88iD5UEMQvFISw%2Fp8m2XTSta6y0F2NbSiNDD3Igl6AdOXPy%2FxQGFj2YZRxKfSl8KvkQr4ZmVvm2ol2OtWshZrJZU%2BY2VGjiWzqgfqb68cnRXBd%2B6p3NIAYmE6qid9WldMi0Rz6Tg4NTyTFK07AVw3UbMZD5m2EQP4IQtTyaxmXzD3T7gBqOfJd5AoTNgmuDAYv%2B%2FGVT8%2BK1PqDX8DIEoR7VEaEazZoedCzqag99HQTLM%2FGN%2BZAUGylShJ5QXWZecuFvD18Eyn4j4hckJe0uF2OtA5%2F3fk6iq4LR1JmM4qG0SRw%2BLybNGCGKodkOc%2BHJm4KkXV%2B4QbUOAnIWldDKezAboamf299MB74qVeri0t7%2FU6UDuCvRLqNwyI467VjtJ6Nm6PA3NGi2Wp8wFforw8KCdfEzmfpObFl32kL83DRSlTrydeHtLF4iZf%2FtRrK6KCBdpiauid4hOqLIylu23CEgINVZDtBjCp%2Fv5P7wPJr2Wv2fSq0aSbBmAxibVsUojZ4pusT6Dn4uh5l29Jd85oNxipoBV32RV%2B9E66TpmUWDUW26S246UND5Z3C9MGUXFBTuexvfmrvJ9rA6TUHrctBzQ0VFjy%2BTRYilxtT7jf%2FQU6633JvyzVKzhORaMNzRkc0GOpcBv3TfmspMFl%2BruI9WngkY29F30wkjQ2OypdR20GzUS6RU4MLCW1x%2Br3VOYPoUz3%2BR0L9CDbTmMF5NVVzcD4WZ3Ws1yS4KKJ%2BC0q5pCbN5s3D1EECGhfA4wNJA2ia5VSBOM3hFEAl5oO%2BjvUj1yy3NI2Lb%2BkTFEOJ%2Fcx1JYwLBVZXu6bpA2k%2FsPiNo7vklbNeSDWSDbs%2FSXg%3D%3D&Expires=1772387352)

14. [Typescript Interface for Recharts Custom Tooltip - Stack Overflow](https://stackoverflow.com/questions/65913461/typescript-interface-for-recharts-custom-tooltip) - Being not well-versed with Typescript yet, I am trying to create a custom Tooltip content for my Rec...

15. [Typescript Interface for Recharts Custom Tooltip](https://stackoverflow.com/questions/65913461/typescript-interface-for-recharts-custom-tooltip/71556818) - Being not well-versed with Typescript yet, I am trying to create a custom Tooltip content for my Rec...

16. [How to Deploy a Next.js TypeScript App on Vercel and Add a Custom Domain](https://www.linkedin.com/pulse/how-deploy-nextjs-typescript-app-vercel-add-custom-domain-shakya-lhkhc) - Deploying a Next.js application with TypeScript on Vercel is straightforward and allows you to use V...

17. [How To Deploy a Full Stack Next.js 14 App To Vercel In 5 minutes](https://www.youtube.com/watch?v=GmO5r5GXtcw) - Ready to take your Next.js 14, Prisma, and TypeScript app live? In this quick and comprehensive tuto...

18. [Privy | Welcome to Astar](https://docs.astar.network/docs/build/EVM/developer-tooling/privy) - Privy is the easiest way for web3 developers to onboard their users, regardless of whether they alre...

19. [Text to Speech | ElevenLabs Documentation](https://elevenlabs.io/docs/overview/capabilities/text-to-speech) - ElevenLabs Text to Speech (TTS) API turns text into lifelike audio with nuanced intonation, pacing a...

20. [A Deep Dive into ElevenLabs Agent Workflows](https://www.webfuse.com/blog/a-deep-dive-into-elevenlabs-agent-workflows) - Explore ElevenLabs Agent Workflows, a visual platform for building dynamic voice AI agents. This gui...

25. [image.jpg](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/images/67975583/834c9e99-7a42-4c73-9c77-ad48181c0be4/image.jpg?AWSAccessKeyId=ASIA2F3EMEYEX23Y5GWT&Signature=xL%2FMSLRo5Rbj2syDwpH0jqp%2BlNk%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEKn%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQCEE47yg8tzEfsvb%2FzeDuUpdvWQ5ErBOnFlnNYxCxQMEwIhALM3zjCO0qzbsLeJTNh%2F8YeaE8EQSII6udbYf46vsTuwKvMECHIQARoMNjk5NzUzMzA5NzA1IgxuFGOPekPK3fXAo18q0AQ89tOgw1qTSTxTM0Wk49Psw9B%2FjK%2FQuszGu3gXmHby5stpgLVXVDAR4q6HwDs29kVvz6IxnQNYb%2FEMdhE7Q3W2vtqLkJwdPDy%2B0n8WpWPvz7V8NoXjjOYs%2F%2Byk6ADS%2FuRqLnljZogGR%2FgUKfrfo4A%2FxZnjN88iD5UEMQvFISw%2Fp8m2XTSta6y0F2NbSiNDD3Igl6AdOXPy%2FxQGFj2YZRxKfSl8KvkQr4ZmVvm2ol2OtWshZrJZU%2BY2VGjiWzqgfqb68cnRXBd%2B6p3NIAYmE6qid9WldMi0Rz6Tg4NTyTFK07AVw3UbMZD5m2EQP4IQtTyaxmXzD3T7gBqOfJd5AoTNgmuDAYv%2B%2FGVT8%2BK1PqDX8DIEoR7VEaEazZoedCzqag99HQTLM%2FGN%2BZAUGylShJ5QXWZecuFvD18Eyn4j4hckJe0uF2OtA5%2F3fk6iq4LR1JmM4qG0SRw%2BLybNGCGKodkOc%2BHJm4KkXV%2B4QbUOAnIWldDKezAboamf299MB74qVeri0t7%2FU6UDuCvRLqNwyI467VjtJ6Nm6PA3NGi2Wp8wFforw8KCdfEzmfpObFl32kL83DRSlTrydeHtLF4iZf%2FtRrK6KCBdpiauid4hOqLIylu23CEgINVZDtBjCp%2Fv5P7wPJr2Wv2fSq0aSbBmAxibVsUojZ4pusT6Dn4uh5l29Jd85oNxipoBV32RV%2B9E66TpmUWDUW26S246UND5Z3C9MGUXFBTuexvfmrvJ9rA6TUHrctBzQ0VFjy%2BTRYilxtT7jf%2FQU6633JvyzVKzhORaMNzRkc0GOpcBv3TfmspMFl%2BruI9WngkY29F30wkjQ2OypdR20GzUS6RU4MLCW1x%2Br3VOYPoUz3%2BR0L9CDbTmMF5NVVzcD4WZ3Ws1yS4KKJ%2BC0q5pCbN5s3D1EECGhfA4wNJA2ia5VSBOM3hFEAl5oO%2BjvUj1yy3NI2Lb%2BkTFEOJ%2Fcx1JYwLBVZXu6bpA2k%2FsPiNo7vklbNeSDWSDbs%2FSXg%3D%3D&Expires=1772387352)

55. [addpipe/Web-Speech-API-TextToSpeech-Demo - GitHub](https://github.com/addpipe/Web-Speech-API-TextToSpeech-Demo) - This Web Speech API Text-to-Speech Demo uses the Web Speech API's SpeechSynthesis interface to conve...

