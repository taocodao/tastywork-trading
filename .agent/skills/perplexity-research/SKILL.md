---
name: perplexity-research
description: >
  Rule: Whenever there is uncertainty, ambiguity, or a knowledge gap about
  an API, library behavior, broker rule, exchange specification, or external
  system — STOP and prepare a focused Perplexity question instead of guessing
  and iterating. Apply this BEFORE writing any code that depends on the answer.
---

# Perplexity Research Rule

## When to Trigger This Skill

You MUST prepare a Perplexity question (instead of guessing) when:

1. **API / SDK behavior is unclear** — e.g., which parameters, methods, or error
   codes to use (IB Gateway, TastyTrade, Composio, Resend, etc.)
2. **Exchange / broker rules are involved** — e.g., strike intervals, settlement
   dates, market data subscription tiers, order types
3. **A fix has been tried more than once and still fails** — stop iterating;
   the root cause requires verified knowledge
4. **"I think" or "I believe" or "probably" appears in your reasoning** — these
   are signals that you don't actually know
5. **External system format / schema is assumed** — e.g., OCC symbol format,
   Vercel config, Composio webhook payload, IB error codes

## When NOT to Trigger

- Straightforward code logic with no external dependencies
- Fixing a clear syntax / type error
- Applying a pattern already confirmed in the codebase

## How to Write the Question

Structure every Perplexity question in three parts:

```
## Context
[2-3 sentences describing the system, library version, and what you're trying to do]

## Specific Question
[The exact technical question — be precise about versions, environments, error codes]

## What You've Already Tried
[What approach was used and what happened — include exact error messages]
```

### Example — Good Question

> **Context**: Using `ib_insync` (latest) with Interactive Brokers Gateway on a
> paper trading account (DUK prefix). Trying to fetch live bid/ask for QQQ
> equity options (Jun 2026 expiry) using delayed market data.
>
> **Specific Question**: Does `reqMarketDataType(3)` (delayed) work for US equity
> options (OPRA feed) on a paper account WITHOUT a paid OPRA subscription? If not,
> what is the minimum subscription required, and can it be shared from a linked
> live account?
>
> **What You've Already Tried**: Called `ib.reqMarketDataType(3)` before
> `ib.reqMktData(contract)`. Got Error 354: "Requested market data is not
> subscribed. Delayed market data is available." The same call works for equity
> spot prices (QQQ stock) but not for option contracts.

### Example — Bad (Do NOT do this)

> "How do I get option prices from IB?"  ← too vague, wastes time

## After Getting the Answer

1. Confirm the answer changes the approach before writing code
2. Document the confirmed behavior in a comment near the relevant code
3. If the answer reveals a prior fix was wrong, revert the wrong fix FIRST,
   then apply the correct one

## Template (copy-paste)

```
## Context
[system / library / environment]

## Specific Question
[precise technical question with version numbers, error codes, field names]

## What You've Already Tried
[approach taken + exact error message / unexpected behavior observed]
```
