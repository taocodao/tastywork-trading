# TurboCore Stripe Integration — Complete Implementation Guide

## Tech Stack Context
- **Framework:** Next.js 14 App Router on Vercel
- **Database:** PostgreSQL on AWS RDS
- **Auth:** Privy (DIDs as user IDs — `did:privy:...`)
- **Payments:** Stripe SDK v14+
- **Plans:** TurboCore ($29/mo, $249/yr), TurboCore Pro ($49/mo, $399/yr), Both Bundle ($69/mo, $549/yr)

***

## A. Product & Price Structure

### Verdict: 3 Separate Products, 2 Prices Each (6 Price IDs Total)

The 6-price-ID approach — one product per plan, one monthly price and one annual price per product — is the **correct and recommended structure** for TurboCore's use case. Stripe's documentation explicitly states that a product can have multiple prices associated with it, and you specify which price to use when creating Checkout Sessions. This keeps your product catalog semantically clean: each product maps to one subscription tier, and each price represents a billing interval.[^1]

The alternative (1 product with 6 prices) works technically but creates ambiguity. When a user upgrades from TurboCore to TurboCore Pro, the "product" they're on doesn't change in Stripe's model — only the price does — which makes webhook logic for tier-gating confusing. Separate products means `product.name` in the webhook payload always tells you unambiguously which tier the user is on.

**Stripe Dashboard Setup:**

| Product | Price ID (monthly) | Price ID (annual) |
|---|---|---|
| TurboCore | `price_tc_monthly` → $29/mo | `price_tc_annual` → $249/yr |
| TurboCore Pro | `price_pro_monthly` → $49/mo | `price_pro_annual` → $399/yr |
| Both Bundle | `price_bundle_monthly` → $69/mo | `price_bundle_annual` → $549/yr |

Store all 6 `price_*` IDs in environment variables. Never hardcode them.

### Plan Switching: Use `stripe.subscriptions.update()` with Proration, Not a New Checkout Session

For upgrades and downgrades between plans (e.g., TurboCore → Both Bundle), the correct approach is to **update the existing subscription** via the API, not redirect to a new Checkout Session. Creating a new Checkout Session for a plan change orphans the old subscription and causes double-billing risk.[^2]

```typescript
// app/api/stripe/change-plan/route.ts
import Stripe from 'stripe';
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

export async function POST(req: Request) {
  const { privyDid, newPriceId } = await req.json();

  // Fetch current subscription from your DB
  const user = await db.query(
    'SELECT stripe_subscription_id FROM user_settings WHERE privy_did = $1',
    [privyDid]
  );
  const subscriptionId = user.rows.stripe_subscription_id;

  // Get current subscription to find the item ID
  const subscription = await stripe.subscriptions.retrieve(subscriptionId);
  const itemId = subscription.items.data.id;

  // Upgrade/downgrade with immediate proration + immediate invoice
  const updated = await stripe.subscriptions.update(subscriptionId, {
    items: [{ id: itemId, price: newPriceId }],
    proration_behavior: 'always_invoice', // generates immediate proration invoice
    payment_behavior: 'pending_if_incomplete', // don't change tier if payment fails
  });

  return Response.json({ subscription: updated });
}
```

**Key `proration_behavior` options and when to use each:**

| Option | Behavior | Use Case |
|---|---|---|
| `always_invoice` | Immediately charges/credits the prorated difference | Upgrades (user gets access now, pays now)[^2] |
| `create_prorations` | Creates proration credits, applies on next renewal | Downgrades (no immediate charge) |
| `none` | No proration at all | If you want clean billing cycles |

For TurboCore, use `always_invoice` for upgrades (TurboCore → Pro, or any → Bundle) and `create_prorations` for downgrades. This matches user expectations: upgrades take effect immediately with an immediate charge; downgrades take effect at period end.

**Important gotcha from Stripe docs:** When updating a subscription item's price, you **must** specify the subscription item ID (`id: itemId`) in the `items` array. Omitting this adds a *new* price to the subscription rather than replacing the old one, resulting in the user being charged for both plans.[^2]

***

## B. Free Trial Setup

### Verdict: Pass `trial_period_days` at the Checkout Session Level, NOT at the Price Level

Stripe supports two places to configure a 14-day trial:

1. **Price-level trial** (`trial_period_days` on the Price object in Dashboard/API)
2. **Session-level trial** (`subscription_data.trial_period_days` in Checkout Session creation)

**Always use the session-level approach for TurboCore.** Here's the critical reason: a trial configured at the Price level applies automatically every time that Price is used — including when an existing paying customer downgrades and reactivates, or when you do a plan switch internally. You cannot conditionally suppress it. Session-level trial gives you full programmatic control over whether to grant a trial.[^3]

```typescript
// app/api/stripe/create-checkout/route.ts
import Stripe from 'stripe';
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

export async function POST(req: Request) {
  const { privyDid, priceId, email } = await req.json();

  // Check if this user/card has already had a trial (fraud prevention — see Section B2)
  const hasHadTrial = await checkPriorTrial(privyDid);

  // Retrieve or create Stripe customer, keyed to Privy DID
  let customerId = await getStripeCustomerId(privyDid);
  if (!customerId) {
    const customer = await stripe.customers.create({
      email,
      metadata: { privy_did: privyDid }, // Store DID in Stripe metadata
    });
    customerId = customer.id;
    await saveStripeCustomerId(privyDid, customerId);
  }

  const sessionParams: Stripe.Checkout.SessionCreateParams = {
    customer: customerId,
    mode: 'subscription',
    line_items: [{ price: priceId, quantity: 1 }],
    payment_method_collection: 'always', // Require card even during trial
    success_url: `${process.env.NEXT_PUBLIC_URL}/dashboard?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${process.env.NEXT_PUBLIC_URL}/pricing`,
    // Only add trial if user hasn't had one before
    ...(hasHadTrial ? {} : {
      subscription_data: {
        trial_period_days: 14,
        trial_settings: {
          end_behavior: { missing_payment_method: 'cancel' },
        },
        metadata: { privy_did: privyDid },
      },
    }),
  };

  const session = await stripe.checkout.sessions.create(sessionParams);
  return Response.json({ url: session.url });
}
```

### Trial Abuse Prevention: Card Fingerprinting

From November 2025 to February 2026, Stripe detected a significant increase in abusive free trials across its network, with 62% of merchants experiencing an increase in first-party fraud. Every payment method in Stripe carries a `fingerprint` — a unique identifier for the underlying card number that persists across different Stripe customer objects. Two users using the same physical card will have identical fingerprints, even if they have different emails and Stripe customer IDs.[^4][^5][^6]

The strategy: store the card fingerprint in your `user_settings` table and block trial creation if that fingerprint has been seen before.

```typescript
// lib/stripe/trial-guard.ts
export async function checkPriorTrial(privyDid: string): Promise<boolean> {
  // Check flag in your own DB first (fast path)
  const user = await db.query(
    'SELECT has_had_trial, card_fingerprint FROM user_settings WHERE privy_did = $1',
    [privyDid]
  );
  if (user.rows?.has_had_trial) return true;
  return false;
}

// Call this from your checkout.session.completed webhook handler
export async function recordTrialAndFingerprint(
  privyDid: string,
  stripeCustomerId: string
) {
  // Get the payment method attached to the customer
  const paymentMethods = await stripe.paymentMethods.list({
    customer: stripeCustomerId,
    type: 'card',
  });
  const fingerprint = paymentMethods.data?.card?.fingerprint;

  if (fingerprint) {
    // Check if this fingerprint belongs to any other account
    const duplicate = await db.query(
      'SELECT privy_did FROM user_settings WHERE card_fingerprint = $1 AND privy_did != $2',
      [fingerprint, privyDid]
    );
    if (duplicate.rows.length > 0) {
      // Same card, different account — flag for review or block silently
      await flagAccountForReview(privyDid, 'duplicate_card_fingerprint');
    }
  }

  await db.query(
    `UPDATE user_settings 
     SET has_had_trial = true, card_fingerprint = $1 
     WHERE privy_did = $2`,
    [fingerprint, privyDid]
  );
}
```

Stripe Radar also has a built-in **trial abuse control** that can detect and block repeated trial signups — enable it in your Radar Dashboard settings as a complementary layer.[^7]

***

## C. Referral Credits

### Verdict: Use `stripe.customers.createBalanceTransaction()` (Customer Balance), Not Coupons or Promotion Codes

Three native Stripe options exist for subscription credits:

| Method | Best For | TurboCore Fit |
|---|---|---|
| **Customer Balance** | Arbitrary credits applied automatically to next invoice | ✅ Best — milestone-based, controllable timing |
| **Coupons** | Blanket % or $ off applied at checkout | ❌ Hard to control per-milestone timing |
| **Promotion Codes** | User-entered codes at checkout | ❌ Not suitable for automatic backend rewards |

Customer balance is the correct choice. Stripe's customer balance is a ledger-based system: every credit grant is recorded immutably, credits auto-apply to the next invoice, and you can set expiration dates. The credit balance automatically deducts from the referrer's next invoice — zero manual work after the grant.[^8][^9][^10]

### Two-Stage Referral Credit Implementation

The two-stage release (Stage 1: $50 at first payment, Stage 2: $50 at second payment) maps cleanly onto `invoice.payment_succeeded` events. The webhook fires for every successfully paid invoice, and each invoice has a `billing_reason` that tells you whether it's the first (`subscription_create`), renewal (`subscription_cycle`), or upgrade (`subscription_update`).

**Step 1: Store referral relationship at checkout**

When a referred user signs up via referral link, store the mapping in your DB:

```sql
CREATE TABLE referrals (
  id SERIAL PRIMARY KEY,
  referrer_privy_did TEXT NOT NULL,
  referred_privy_did TEXT NOT NULL,
  referred_stripe_customer_id TEXT NOT NULL,
  stage1_paid BOOLEAN DEFAULT FALSE,
  stage2_paid BOOLEAN DEFAULT FALSE,
  annual_bonus_paid BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Step 2: Webhook handler for `invoice.payment_succeeded`**

```typescript
// app/api/stripe/webhook/route.ts

// CRITICAL for Next.js App Router: disable body parser
export const config = { api: { bodyParser: false } };

export async function POST(req: Request) {
  const rawBody = await req.text(); // Must be raw bytes for signature verification
  const sig = req.headers.get('stripe-signature')!;

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      rawBody,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    return new Response(`Webhook signature error: ${err}`, { status: 400 });
  }

  // Idempotency guard — always return 200 quickly to avoid Stripe retries
  // Process asynchronously or use a queue for heavy operations
  
  switch (event.type) {
    case 'invoice.payment_succeeded': {
      const invoice = event.data.object as Stripe.Invoice;
      await handleInvoicePaymentSucceeded(invoice);
      break;
    }
    case 'checkout.session.completed': {
      const session = event.data.object as Stripe.Checkout.Session;
      await handleCheckoutCompleted(session);
      break;
    }
    // ... other events
  }

  return new Response('OK', { status: 200 });
}

async function handleInvoicePaymentSucceeded(invoice: Stripe.Invoice) {
  const customerId = invoice.customer as string;
  const billingReason = invoice.billing_reason;
  
  // Find if this customer is a referred user
  const referral = await db.query(
    'SELECT * FROM referrals WHERE referred_stripe_customer_id = $1',
    [customerId]
  );
  if (!referral.rows.length) return;
  
  const ref = referral.rows;
  
  // Get referrer's Stripe customer ID
  const referrer = await db.query(
    'SELECT stripe_customer_id FROM user_settings WHERE privy_did = $1',
    [ref.referrer_privy_did]
  );
  const referrerStripeId = referrer.rows?.stripe_customer_id;
  if (!referrerStripeId) return;

  // Stage 1: First successful payment (billing_reason = 'subscription_create' 
  // or first cycle after trial)
  if (!ref.stage1_paid && 
      (billingReason === 'subscription_create' || billingReason === 'subscription_cycle')) {
    
    // Check if this is an annual plan — grant $150 instead
    const subscription = await stripe.subscriptions.retrieve(invoice.subscription as string);
    const isAnnual = subscription.items.data.price.recurring?.interval === 'year';
    
    if (isAnnual && !ref.annual_bonus_paid) {
      // Annual plan: $150 instant credit
      await stripe.customers.createBalanceTransaction(referrerStripeId, {
        amount: -15000, // Stripe balance is in cents, negative = credit
        currency: 'usd',
        description: 'Referral bonus — friend joined annual plan',
        metadata: { referral_stage: 'annual_bonus', referred_customer: customerId },
      });
      await db.query(
        'UPDATE referrals SET stage1_paid=true, annual_bonus_paid=true WHERE id=$1',
        [ref.id]
      );
    } else if (!ref.stage1_paid) {
      // Monthly plan: $50 stage 1
      await stripe.customers.createBalanceTransaction(referrerStripeId, {
        amount: -5000,
        currency: 'usd',
        description: 'Referral credit — Stage 1 ($50)',
        metadata: { referral_stage: '1', referred_customer: customerId },
      });
      await db.query(
        'UPDATE referrals SET stage1_paid=true WHERE id=$1',
        [ref.id]
      );
    }
  }

  // Stage 2: Second successful payment on monthly plan
  // invoice_count on the subscription can be checked, or track invoice number in DB
  else if (ref.stage1_paid && !ref.stage2_paid && !ref.annual_bonus_paid &&
           billingReason === 'subscription_cycle') {
    await stripe.customers.createBalanceTransaction(referrerStripeId, {
      amount: -5000,
      currency: 'usd',
      description: 'Referral credit — Stage 2 ($50)',
      metadata: { referral_stage: '2', referred_customer: customerId },
    });
    await db.query(
      'UPDATE referrals SET stage2_paid=true WHERE id=$1',
      [ref.id]
    );
  }
}
```

**Important:** `invoice.payment_succeeded` can fire multiple times if your webhook endpoint doesn't return `200` promptly — Stripe retries for up to 3 days. Always mark actions as done in DB **before** returning 200, or use an idempotency key check at the top of each handler.[^11][^12]

***

## D. Afterpay / Klarna on Annual Plans

### Klarna: Fully Supported on Recurring Annual Subscriptions ✅

Klarna supports automatic payments for subscriptions, **including long-term subscriptions (longer than monthly)**. This covers TurboCore's annual plans. Stripe documentation explicitly shows Klarna being configured for recurring subscriptions with yearly intervals.[^13][^14][^15]

**Geographic coverage for Klarna (USD annual plans):** United States, with a limit of $4,000 USD for Pay in Full. TurboCore's annual plans ($249–$549) fall well within limits.[^14]

To enable Klarna on your Checkout Session, add it to `payment_method_types`:

```typescript
const session = await stripe.checkout.sessions.create({
  customer: customerId,
  mode: 'subscription',
  payment_method_types: ['card', 'klarna'],
  line_items: [{ price: priceId, quantity: 1 }],
  // For Klarna on subscriptions, pass subscription line item details
  payment_method_options: {
    klarna: {
      subscriptions: [{
        interval: 'year',
        interval_count: 1,
      }],
    },
  },
  // ... rest of session params
});
```

### Afterpay: NOT Supported on Recurring Subscriptions ❌

This is the critical limitation to know: **Afterpay can only be used for non-recurring (one-time) payments**. Afterpay also does not support delayed payments or free trials. This is an Afterpay policy enforced at Stripe's level — it cannot be worked around.[^16]

Additionally, Afterpay's US Pay in 4 is limited to transactions up to $2,000 and monthly installments (6–12 months) for US customers only. For TurboCore's annual subscription model, Afterpay is architecturally incompatible.[^17]

**Recommendation:** Enable Klarna only for annual plans. For monthly plans, stick to card + Link (Stripe's saved card accelerator). You can conditionally show/hide Klarna based on the user's selected plan interval in your UI before redirecting to Checkout.

| Payment Method | Monthly Plans | Annual Plans | Has Trial |
|---|---|---|---|
| Card | ✅ | ✅ | ✅ |
| Klarna | ❌ (monthly too short-term for meaningful split) | ✅ | ✅ via Klarna flow[^13] |
| Afterpay | ❌ | ❌ (no recurring support)[^16] | ❌ |
| Link (Stripe) | ✅ | ✅ | ✅ |

***

## E. Test → Staging → Production Workflow

### Environment Setup

Use separate `.env` files at each environment tier. Never commit any Stripe secret keys.

```bash
# .env.local (local dev — gitignored)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...  # From `stripe listen` CLI output
NEXT_PUBLIC_URL=http://localhost:3000

# Vercel Preview Environment Variables (staging)
STRIPE_SECRET_KEY=sk_test_...    # Same test keys as local
STRIPE_WEBHOOK_SECRET=whsec_...  # NEW secret from Stripe Dashboard webhook endpoint
NEXT_PUBLIC_URL=https://your-app-preview.vercel.app

# Vercel Production Environment Variables
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...  # NEW secret from live webhook endpoint
NEXT_PUBLIC_URL=https://turbobounce.com
```

### Local Development with Stripe CLI

Run both commands in parallel in your terminal:[^18]

```bash
# Terminal 1: Start Next.js dev server
npm run dev

# Terminal 2: Forward Stripe events to local webhook
stripe listen --forward-to localhost:3000/api/stripe/webhook

# Stripe CLI prints: Ready! Webhook signing secret: whsec_xxxx
# Copy this value into STRIPE_WEBHOOK_SECRET in .env.local
```

The `stripe listen` command is a **local-only development tool** — it should never run on a server or in a Vercel deployment. In staging and production, Stripe delivers webhooks directly to your registered HTTPS endpoint.[^18]

### Copying Products from Test to Live Mode

Stripe provides a **"Copy to live mode"** button on the Product details page in the Dashboard. This is the correct workflow — do not recreate products manually in live mode, as this creates a mismatch between your test and live price IDs.[^19]

**Step-by-step promotion workflow:**

1. **Create all 3 products + 6 prices in Stripe test mode**
2. **Build and test locally** with `stripe listen`
3. **Deploy to Vercel preview** with test keys + a new webhook endpoint registered in Stripe Dashboard pointing to your preview URL
4. **Verify all flows in preview** (checkout, upgrades, cancellation, trial expiry, referral credits)
5. **Copy each product to live mode** via Dashboard "Copy to live mode" button — this also copies the associated prices[^19]
6. **Note:** You can only copy a test product to live mode **once**. After that, live product is independent. If you update test product prices after copying, manually update the live product too[^20]
7. **Register a new webhook endpoint** in Stripe Dashboard for your production URL → get new `whsec_` secret → set in Vercel production environment variables
8. **Deploy to production** with live keys

**Critical Vercel gotcha:** Each Vercel environment (preview, production) requires its **own** webhook signing secret registered in the Stripe Dashboard. If you reuse the same `whsec_` across environments, signature verification will fail because Stripe signs each delivery with the secret for that specific endpoint.[^21]

### Differentiating Test vs. Live Data in PostgreSQL

Since your DB is shared across environments (or you use the same schema), add a `livemode` column to `user_settings` and populate it from Stripe's webhook payload. Every Stripe event object includes `livemode: boolean`:[^22]

```sql
ALTER TABLE user_settings ADD COLUMN livemode BOOLEAN DEFAULT FALSE;
```

```typescript
// In webhook handler
const isLive = event.livemode; // true in production, false in test
await db.query(
  `UPDATE user_settings SET livemode = $1, subscription_tier = $2 
   WHERE stripe_customer_id = $3`,
  [isLive, tier, customerId]
);
```

This prevents test events from contaminating your production user records if both environments point to the same DB during staging.

***

## F. Webhook Events — Complete Production Event Map

Beyond the basic three events, a production-grade billing system for TurboCore requires the following webhook events:[^11]

### Subscription Lifecycle Events

| Event | What It Means | Your Action |
|---|---|---|
| `checkout.session.completed` | New subscriber created | Create/update `user_settings` row, set `subscription_tier`, record trial fingerprint |
| `customer.subscription.created` | Subscription object created | Backup handler if checkout webhook fails |
| `customer.subscription.updated` | Plan changed, trial ended, status changed | Update `subscription_tier`; if `status = past_due`, downgrade access |
| `customer.subscription.deleted` | Subscription cancelled (end of period or immediately) | Set `subscription_tier = null` or `'free'`; revoke access |
| `customer.subscription.trial_will_end` | Trial ends in 3 days | Send reminder email: "Your trial ends in 3 days — you won't be charged until X" |

### Invoice & Payment Events

| Event | What It Means | Your Action |
|---|---|---|
| `invoice.payment_succeeded` | Successful charge | Update subscription period, trigger referral credits logic |
| `invoice.payment_failed` | Charge declined | Notify user via email; subscription goes `past_due` → restrict access after grace period[^23] |
| `invoice.payment_action_required` | 3D Secure / SCA authentication required | Send email with `hosted_invoice_url` for user to authenticate[^11] |
| `invoice.upcoming` | Invoice due in ~7 days | Optional: send renewal reminder email |
| `invoice.finalization_failed` | Invoice couldn't be finalized (e.g., Stripe Tax issue) | Alert to engineering; subscription stays active but you can't collect payment[^11] |

### Payment Method & Recovery Events

| Event | What It Means | Your Action |
|---|---|---|
| `payment_method.attached` | New card added to customer | Update stored fingerprint, check for duplicates |
| `customer.updated` | Customer marked delinquent | Trigger dunning sequence |
| `payment_intent.payment_failed` | Underlying payment attempt failed | Log payment failure details for support |

### Revenue Recovery Configuration

Beyond webhooks, enable these in the **Stripe Dashboard → Billing → Settings**:[^24]
- **Smart Retries:** Stripe ML retries failed charges at optimal times (recovers significant failed revenue)
- **Customer emails for failed payments:** Stripe sends branded emails with payment update links
- **Automatic card updates:** Stripe works with card networks to update expired card details automatically[^25]

### Webhook Handler Architecture for Next.js App Router

The most common Next.js + Stripe webhook failure mode is **body parsing**. App Router automatically parses request bodies, which corrupts the raw bytes Stripe needs for signature verification. Use `req.text()` not `req.json()`:[^21]

```typescript
// app/api/stripe/webhook/route.ts
import Stripe from 'stripe';
import { NextRequest } from 'next/server';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

// This is the critical config — prevents Next.js from parsing the body
export const runtime = 'nodejs'; // Required for raw body access
export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const sig = req.headers.get('stripe-signature');

  if (!sig) {
    return new Response('Missing stripe-signature header', { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      rawBody,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return new Response(`Webhook signature verification failed: ${message}`, { status: 400 });
  }

  // Always return 200 immediately, process async to avoid Stripe timeout
  // Stripe waits 30 seconds then retries; use background processing or queue
  try {
    await processWebhookEvent(event);
  } catch (err) {
    console.error('Webhook processing error:', err);
    // Still return 200 — log the error separately
    // Returning non-200 causes Stripe to retry the same event
  }

  return new Response('OK', { status: 200 });
}
```

***

## Complete `user_settings` Table Schema

Based on all requirements above, the recommended schema for `user_settings`:

```sql
CREATE TABLE user_settings (
  id SERIAL PRIMARY KEY,
  privy_did TEXT UNIQUE NOT NULL,               -- Privy DID (did:privy:...)
  stripe_customer_id TEXT UNIQUE,               -- Stripe customer ID (cus_...)
  stripe_subscription_id TEXT,                  -- Active subscription ID (sub_...)
  stripe_price_id TEXT,                         -- Current active price ID
  subscription_tier TEXT,                       -- 'turbocore' | 'turbocore_pro' | 'bundle' | null
  subscription_status TEXT,                     -- Stripe status: 'active' | 'trialing' | 'past_due' | 'canceled'
  billing_interval TEXT,                        -- 'month' | 'year'
  current_period_end TIMESTAMPTZ,               -- When current billing period ends
  trial_end TIMESTAMPTZ,                        -- When trial ends (null if not trialing)
  has_had_trial BOOLEAN DEFAULT FALSE,          -- Fraud prevention: one trial per user
  card_fingerprint TEXT,                        -- Fraud prevention: one trial per card
  livemode BOOLEAN DEFAULT FALSE,               -- Test vs. production data flag
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON user_settings (stripe_customer_id);
CREATE INDEX ON user_settings (card_fingerprint);  -- For O(1) duplicate fingerprint lookups
```

***

## Privy DID ↔ Stripe Customer Mapping

Since Privy DIDs (`did:privy:...`) are the primary user identifier and Stripe uses `cus_...` IDs, the mapping strategy is:

1. Store `privy_did` in Stripe Customer `metadata.privy_did` when creating the customer
2. Store `stripe_customer_id` in your `user_settings` table
3. In webhooks, always look up by `stripe_customer_id` — never by email, since Privy users may have multiple auth methods

```typescript
// lib/stripe/customer.ts
export async function getOrCreateStripeCustomer(
  privyDid: string,
  email?: string
): Promise<string> {
  // Check DB first
  const result = await db.query(
    'SELECT stripe_customer_id FROM user_settings WHERE privy_did = $1',
    [privyDid]
  );
  
  if (result.rows?.stripe_customer_id) {
    return result.rows.stripe_customer_id;
  }

  // Create new Stripe customer with DID in metadata
  const customer = await stripe.customers.create({
    email: email,
    metadata: { privy_did: privyDid },
  });

  // Upsert into user_settings
  await db.query(
    `INSERT INTO user_settings (privy_did, stripe_customer_id)
     VALUES ($1, $2)
     ON CONFLICT (privy_did) DO UPDATE SET stripe_customer_id = $2`,
    [privyDid, customer.id]
  );

  return customer.id;
}
```

---

## References

1. [How products and prices work | Stripe Documentation](https://docs.stripe.com/products-prices/how-products-and-prices-work) - Because a product can have multiple prices associated with it, you need to specify which price to us...

2. [Change the price of existing subscriptions - Stripe Documentation](https://docs.stripe.com/billing/subscriptions/change-price) - Upgrade or downgrade subscriptions by replacing prices with proration options including immediate, n...

3. [Configure free trials - Stripe Documentation](https://docs.stripe.com/payments/checkout/free-trials) - By default, Checkout Sessions collect a payment method to use after the trial ends. You can sign cus...

4. [Analyzing first-party fraud trends: Account, free trial, and refund abuse](https://stripe.com/blog/analyzing-first-party-fraud-trends-account-free-trial-and-refund-abuse) - From November 2025 to February 2026, we detected a significant increase in abusive free trials acros...

5. [This One Stripe Field Could Save You from Fraud (And No ... - UserJot](https://userjot.com/blog/stripe-fingerprint-detect-fraud) - Learn how Stripe's fingerprint field helps detect duplicate cards across accounts to prevent fraud a...

6. [How can I detect duplicate cards or bank accounts?](https://support.stripe.com/questions/how-can-i-detect-duplicate-cards-or-bank-accounts) - That is, if you keep track of all the fingerprints in your database you'll be able to detect a retur...

7. [Customer abuse | Stripe Documentation](https://docs.stripe.com/disputes/prevention/abuse) - Stripe Radar offers a trial abuse control to detect repeated trial signup and failure to cancel tria...

8. [Introducing credits for usage-based billing - Stripe](https://stripe.com/blog/introducing-credits-for-usage-based-billing) - The new credits feature allows businesses to offer both promotional and paid credits with enhanced c...

9. [Customer credit balance - Stripe Documentation](https://docs.stripe.com/invoicing/customer/balance) - This page is about customer credit balances, which are adjustments you can issue to customers that a...

10. [What is a credits-based subscription model and how does it work?](https://stripe.com/resources/more/what-is-a-credits-based-subscription-model-and-how-does-it-work) - Setting up a credits-based system involves tracking balances, deducting usage, handling expirations,...

11. [Using webhooks with subscriptions - Stripe Documentation](https://docs.stripe.com/billing/subscriptions/webhooks) - Handle subscription events including payment failures, status changes, trial endings, and actions re...

12. [Stripe invoice.payment_succeeded webhook is triggered multiple ...](https://stackoverflow.com/questions/34692942/stripe-invoice-payment-succeeded-webhook-is-triggered-multiple-times) - Stripe will send an invoice.payment_succeeded event each time payment succeeds for any invoice. If y...

13. [Set up future Klarna payments - Stripe Documentation](https://docs.stripe.com/payments/klarna/set-up-future-payments) - You can save Klarna as a customer's payment method and charge future payments to support: Automatic ...

14. [Klarna payments - Stripe Documentation](https://docs.stripe.com/payments/klarna) - Recurring payments support. Yes. Payout timing. Standard payout timing applies. Connect support. Yes...

15. [Set up a subscription with Klarna - Stripe Documentation](https://docs.stripe.com/billing/subscriptions/klarna) - Go to the Products page and click Create product. · Enter a Name for the product. · Select a Product...

16. [How to Enable Afterpay With Stripe and MemberPress?](https://memberpress.com/docs/enable-afterpay-with-stripe-and-memberpress/) - Afterpay is supported only through the built-in MemberPress integration with Stripe. Thus, before en...

17. [Afterpay and Clearpay payments - Stripe Documentation](https://docs.stripe.com/payments/afterpay-clearpay) - Payment options and limits · Pay in 4: customers pay for purchases in four or fewer interest-free, b...

18. [Vercel Next JS add Stripe listener webhook - Stack Overflow](https://stackoverflow.com/questions/78029480/vercel-next-js-add-stripe-listener-webhook) - I am making an eshop in Next JS and I am using stripe payment system. I want to see if the payment h...

19. [Manage products and prices - Stripe Documentation](https://docs.stripe.com/products-prices/manage-prices) - Set up your pricing model in a sandbox and click the Copy to live mode button on the product details...

20. [How to create products and prices : Stripe: Help & Support](https://support.stripe.com/questions/how-to-create-products-and-prices) - Creating products and prices using the Dashboard​​ Log into your Stripe Dashboard and navigate to th...

21. [Stripe Webhook in Nextjs issue · vercel next.js · Discussion #48885](https://github.com/vercel/next.js/discussions/48885) - If you are experiencing an issue where webhooks work on localhost but fail in Vercel production, her...

22. [Differentiating stripe test products from stripe live products in supabase](https://www.reddit.com/r/Supabase/comments/18akxzy/differentiating_stripe_test_products_from_stripe/) - The stripe webhooks and vercel serverless functions that sync supabase with stripe seem to not diffe...

23. [How to handle failed subscription payments in Stripe - Ben Foster](https://benfoster.io/blog/stripe-failed-payments-how-to/) - In this post I cover what happens when a subscription payment fails in Stripe and how you can handle...

24. [Fix Recurring Payments on Stripe in 2026 (Failed Subscriptions ...](https://www.youtube.com/watch?v=t1gBsDvBrRA) - Fix recurring payments on Stripe when subscription payments fail due to card declines, expired cards...

25. [Stripe Billing | Recurring Payments & Subscription Solutions](https://stripe.com/billing) - Stripe Billing lets you bill and manage customers however you want—from simple recurring billing to ...

