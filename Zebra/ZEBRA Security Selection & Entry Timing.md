# ZEBRA Options Strategy: Security Selection, Entry Timing, and AI Integration

## Executive Summary

The ZEBRA (Zero Extrinsic Back Ratio) strategy's profitability hinges less on the structure itself and more on **which underlying you trade** and **when you enter**. This report synthesizes practitioner screening criteria, academic research on option-implied signals, ML model designs for directional prediction and timing, institutional flow analysis, and a production-ready Perplexity Sonar API integration layer—all designed as a blueprint Antigravity can code against.

***

## Part 1: Security Selection — What Makes a Good ZEBRA Underlying

### 1.1 Practitioner Screening Criteria

The leading practitioner sources converge on a consistent set of filters for selecting ZEBRA-worthy underlyings:

**Option Samurai's ZEBRA Scanner (2025)** uses the following criteria:[^1]
- **Breakeven proximity**: -3% to +3% from current price, ensuring the trade profits from the first small upward move
- **Max loss**: Below $1,000 per position to keep total risk defined and manageable
- **Max loss %**: Below 30% to ensure favorable leverage vs. capital used
- **Fundamental & growth scores**: Above 5, targeting fundamentally strong companies with solid growth metrics
- **DTE**: 60–120 days to give the position enough time without excessive vega exposure
- **Total option volume**: Above 5,000 contracts/day for liquidity

**Options Trading IQ's comprehensive guide** recommends:[^2]
- **45 DTE as the sweet spot**; never put on a ZEBRA with less than 25 DTE (faster theta decay, larger gamma risk)
- **Avoid DTE > 90 days** for most swing trades—larger vega and capital required
- **Active management required**: manage via Greeks, set stops rather than relying on max loss
- **Low IV environments are preferable** for ZEBRAs since you are a net premium buyer (positive vega)

**Dorian Trader (Jan 2026)** emphasizes:[^3]
- Select calls with delta ≈ 0.70 and expiration 1 year+ for position trades, or 30–60 day short-term overlay
- Use high-quality, trending stocks where you have a directional thesis

**YouTube practitioner (stock replacement focus)** applies the "Peter Lynch principle":[^4]
- Know what you own: understand the business, competitive moat, and growth story
- Institutional ownership matters: >60% institutional ownership ensures deep option liquidity
- Core allocation to index ETFs (SPY, QQQ) for base ZEBRA candidates—100M+ shares daily, penny-wide spreads
- Filter for fundamentals: free cash flow positive, revenue growth, reasonable valuation

### 1.2 Synthesized Best-Practice Filter Stack

Combining all practitioner sources, the ideal ZEBRA security filter is:

| Filter | Threshold | Rationale |
|--------|-----------|-----------|
| Price | >$10 | Avoid penny stocks; ensures meaningful option chains |
| Average daily volume (stock) | >1M shares | Liquidity for underlying |
| Option volume (total) | >5,000 contracts/day | Tradeable multi-leg spreads |
| Bid-ask spread (ATM options) | <5% of underlying | Minimize slippage on 3-leg entry |
| Open interest per leg | >500 | Sufficient counterparties |
| IV Rank / IV Percentile | <50th percentile preferred | ZEBRA is net long premium; cheaper is better |
| Fundamental score | Top quartile (growth + quality) | Strong companies trend better |
| Trend confirmation | Price > 50-day SMA, RSI 40–70 | Bullish direction confirmed, not overbought |
| DTE | 45–120 days | Time for thesis to play out |
| Breakeven % from spot | Within ±3% | Near-immediate profitability zone |
| Max loss % of capital | <30% | Favorable leverage |

***

## Part 2: Entry Timing — When to Put On a ZEBRA

### 2.1 Volatility Context (IV as Strategy Selector)

Because ZEBRA is a **net debit, positive-vega** structure, entry timing must respect implied volatility regime:[^5][^6]

- **Low IV environment (IV Rank < 40)**: Ideal for ZEBRA entry. Options are cheap, extrinsic is minimal, and any subsequent IV expansion benefits the position.
- **High IV environment (IV Rank > 60)**: Avoid ZEBRA. Premium is expensive; prefer selling strategies (credit spreads, iron condors). If you must take a directional position, consider stock or synthetic stock instead.
- **Medium IV (40–60)**: Acceptable if directional conviction is strong and other signals align.

This is consistent with the quantitative framework of combining IV with RSI and MACD for timing options entries:[^6]

**Strategy: Low IV + MACD Bullish Crossover → Long ZEBRA Entry**
> When an asset has low IV Rank (options are cheap) and the MACD line crosses above the signal line confirming bullish momentum shift, this is a high-conviction opportunity for long directional trades. Low IV means extrinsic value risk (theta decay) is minimized, and positive momentum suggests the underlying price will generate delta value quickly.[^6]

### 2.2 Momentum and Trend Confirmation

The Options Trading IQ ZEBRA guide provides a concrete example of entry criteria:[^2]
- Bullish candle bouncing up from the 8-day EMA
- 8-day EMA above the upward-sloping 20-day SMA
- RSI stair-stepping upward but NOT in overbought territory (RSI < 70)
- No immediate overhead resistance

For bearish ZEBRAs:[^2]
- Moving averages stacked sequentially downward (price < 8 EMA < 20 SMA < 50 SMA < 200 SMA)
- RSI not yet oversold (still room to fall)

### 2.3 Regime Framework for Entry Timing

Research on combining VIX with momentum signals shows that regime-aware timing significantly improves entry quality:[^7][^8]

- **Regime 2 (VIX > 30, RSI ≥ 40)**: Delivers the most consistent returns across time horizons. Waiting for signs of momentum recovery amid persistent fear is a superior timing strategy.
- **Regime 1 (VIX > 30, RSI < 40)**: Shows strong initial gains that tend to reverse—too early for ZEBRA entry.
- For ZEBRA specifically, enter **after** regime shifts toward stabilization, not during peak panic.

### 2.4 Institutional Flow as Entry Catalyst

A proven practitioner method uses AI to track institutional options flow for entry timing:[^9]

1. **Flow scanning**: Identify tickers with unusual institutional activity (block trades, sweeps)
2. **Flow + trend alignment filter**:
   - Bearish flow + uptrend → REJECT (likely hedging a long)
   - Bullish flow + downtrend → REJECT (likely hedging a short)
   - Flow matches trend → KEEP (genuine directional conviction)
3. **IV filter**: Reject stocks with IV Rank above 70th percentile—high IV signals the move is already priced in
4. Enter ZEBRA only when flow confirms direction AND IV is favorable

Professional platforms like Optionomics use 10 separate algorithms to detect unusual activity: block trades (>$1M), multi-exchange sweeps, IV spikes, volume-exceeding-OI (3x+), aggressive fills above ask (calls) or below bid (puts), opening interest surges, complex multi-leg strategies, and after-hours activity.[^10]

***

## Part 3: Academic Research — Option-Implied Signals for Stock Selection

### 3.1 Option-Implied Moments Predict Returns

A study published in the Journal of Futures Markets constructs a **joint score** from option-implied volatility, skewness, and kurtosis. Portfolios formed on this score earn a statistically significant **0.75% monthly return** (value-weighted). The alpha is robust across controls and driven by information flow from options to stock markets.[^11][^12]

**Implication for ZEBRA**: Build a composite score from option-implied moments to rank ZEBRA candidates. High-score stocks (favorable distribution properties implied by options) should receive priority.

### 3.2 IV Spread and Skew Identify Momentum Stages

Research shows that IV spread (call IV minus put IV) and IV skew can distinguish **early-stage momentum** stocks from **late-stage** ones:[^13][^14]

- **Early-stage winners**: Informed options traders are buying calls, generating positive IV spread signals that reinforce the upward price trend. Momentum persists longer.
- **Late-stage winners**: Informed traders are selling calls or buying puts against winners, generating negative signals. Momentum is about to reverse.

An early-stage momentum strategy—buying early-stage winners and selling early-stage losers—**significantly outperforms** traditional momentum, with more gradual reversals.[^13]

**Implication for ZEBRA**: Only enter bullish ZEBRAs on stocks classified as early-stage winners (positive IV spread, positive IV skew trend). Avoid late-stage momentum names where reversal risk is high.

### 3.3 Option-Implied Skewness and Momentum Crashes

CFA Institute research demonstrates that risk-neutral skewness (RNS) helps identify and avoid momentum crashes:[^15]

- High RNS stocks predict positive performance, particularly after underperformance periods
- Momentum strategies filtered by low skewness factor loadings have **significantly improved performance**
- This is driven by the ability of options data to identify the momentum phases of loser stocks

### 3.4 GS-LASSO for Trade Direction Inference

A novel ML method (GS-LASSO) integrates XGBoost with SHAP and LASSO to infer options trade directions from PHLX data, achieving **76.71% accuracy** vs. <60% for existing methods. This improved classification:[^16]
- Provides more accurate market microstructure metrics
- Reveals insights into wholesaler profitability from retail option flows
- Can be adapted to detect when retail is systematically wrong on direction

***

## Part 4: ML Model Architecture for ZEBRA Selection and Timing

### 4.1 Directional Prediction Model (XGBoost)

Based on the KTH thesis (2025) using XGBoost for stock recommendation, adapted for ZEBRA:[^17]

**Feature Engineering (24+ features per symbol)**:

| Category | Features |
|----------|----------|
| Momentum | 1d/7d/1mo/1yr/3yr total move, 1d/7d % change |
| Moving Averages | EMA, SMA, WMA, DEMA, TEMA (various periods) |
| Oscillators | RSI(14), Williams %R, ADX |
| Volatility | 20d standard deviation, 1d/7d high-low range, overnight gap % |
| Volume | Daily volume, volume vs 20d average ratio |
| Valuation | P/E ratio, free cash flow yield |
| Options-Implied | IV rank, IV percentile, 25-delta skew, IV spread (call-put), term structure slope |
| Crowding | Call/put volume ratio, small-lot %, social sentiment score |

**Model**: XGBoost Regressor with rolling training window:
```python
{
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "reg_alpha": 0.1,
    "objective": "reg:squarederror"
}
```

**Output**: Confidence score 0–10 per symbol per day:[^17]
- 8–10: Strong buy signal → eligible for bullish ZEBRA
- 0–2: Strong sell signal → eligible for bearish ZEBRA
- 3–7: Neutral → no ZEBRA

The KTH thesis found this approach **slightly outperformed buy-and-hold** overall, but critically **excelled at loss avoidance during volatile periods** by staying neutral—exactly the regime awareness ZEBRA needs.[^17]

### 4.2 Option-Implied Momentum Stage Classifier

A second model specifically classifies each candidate into momentum stages using option-derived features:[^14][^13]

**Inputs**:
- IV spread (call IV − put IV at matched deltas)
- IV skew (OTM put IV − ATM IV)
- Recent price momentum (1mo, 3mo returns)
- Option volume imbalance (call vol / put vol)

**Output**: `{EARLY_STAGE_WINNER, LATE_STAGE_WINNER, EARLY_STAGE_LOSER, LATE_STAGE_LOSER, NEUTRAL}`

**Rule**: Only allow bullish ZEBRA on `EARLY_STAGE_WINNER`; only bearish ZEBRA on `EARLY_STAGE_LOSER`. Veto all late-stage signals.

### 4.3 Entry Timing Model

Combines volatility regime and technical momentum:

**Inputs**:
- IV Rank (current vs. 1-year range)
- VIX level and VIX term structure
- RSI(14) and MACD signal
- Regime state (from regime classifier)

**Rules** (codifiable, ML-assistable):
- Bullish ZEBRA entry: IV Rank < 50 AND MACD bullish crossover AND RSI 40–65 AND regime = BULL or RECOVERY[^7][^6]
- Bearish ZEBRA entry: IV Rank < 50 AND MACD bearish crossover AND RSI 35–60 AND regime = BEAR or DISTRIBUTION
- No entry: IV Rank > 60 OR RSI overbought/oversold extremes OR regime = CHOPPY[^5][^6]

***

## Part 5: Perplexity Sonar API Integration — Real-Time Intelligence Layer

### 5.1 API Overview

Perplexity's Sonar API is OpenAI-compatible and provides web-grounded AI responses with built-in search. Key capabilities for ZEBRA:[^18][^19]

| Feature | Sonar API Parameter | Use Case |
|---------|-------------------|----------|
| Real-time news | `search_recency_filter="week"` | Latest news for candidates |
| SEC filings | `search_mode="sec"` | 10-K/10-Q analysis |
| Academic research | `search_mode="academic"` | Scholarly validation |
| Domain filtering | `search_domain_filter=["reuters.com", "sec.gov"]` | Source quality control |
| Date filtering | `search_after_date_filter="1/1/2026"` | Recent-only results |
| Structured JSON | `response_format={"type":"json_schema",...}` | Machine-readable output |
| Context control | `web_search_options={"search_context_size":"high"}` | Deep vs. fast queries |

### 5.2 Three Perplexity Enrichment Functions

**Function 1: `enrich_news_sentiment(symbol)`** — Fetch latest news and compute sentiment

```python
from perplexity import Perplexity
from pydantic import BaseModel
from typing import List, Optional

class NewsTag(BaseModel):
    headline: str
    category: str  # PRODUCT, REGULATORY, LITIGATION, MACRO, EARNINGS
    sentiment: str  # POSITIVE, NEGATIVE, NEUTRAL
    impact_score: float  # 0-1

class NewsSentimentResult(BaseModel):
    symbol: str
    news_tags: List[NewsTag]
    overall_sentiment_score: float  # -1 to 1
    risk_flags: List[str]
    veto: bool
    veto_reason: Optional[str] = None

client = Perplexity()

def enrich_news_sentiment(symbol: str) -> NewsSentimentResult:
    completion = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {
                "role": "system",
                "content": "You are a financial analyst. Extract news events and classify each by category, sentiment, and impact. Flag any litigation, regulatory action, or imminent binary events (FDA, merger vote). Return structured JSON only."
            },
            {
                "role": "user",
                "content": f"Analyze the latest news and events for {symbol} in the past 90 days. Classify each major event by category, sentiment, and potential stock price impact."
            }
        ],
        search_recency_filter="month",
        search_domain_filter=["reuters.com", "bloomberg.com", "wsj.com", "sec.gov", "finance.yahoo.com"],
        web_search_options={"search_context_size": "high"},
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": NewsSentimentResult.model_json_schema()}
        }
    )
    return NewsSentimentResult.model_validate_json(
        completion.choices.message.content
    )
```

**Function 2: `enrich_sec_filings(symbol)`** — Analyze latest SEC filings

```python
class SECInsight(BaseModel):
    filing_type: str  # 10-K, 10-Q, 8-K
    period: str
    revenue_trend: str  # UP, DOWN, FLAT
    margin_trend: str
    guidance_change: Optional[str] = None  # UP, DOWN, MAINTAINED, NONE
    risk_factors_new: List[str]
    insider_transactions: Optional[str] = None

class SECResult(BaseModel):
    symbol: str
    filings: List[SECInsight]
    fundamental_risk_score: float  # 0-1 (0=safe, 1=risky)

def enrich_sec_filings(symbol: str) -> SECResult:
    completion = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {
                "role": "system",
                "content": "You are a SEC filing analyst. Extract key financial trends, guidance changes, and new risk factors from recent filings. Return structured JSON."
            },
            {
                "role": "user",
                "content": f"Summarize the last 2 quarterly filings (10-Q) and most recent annual filing (10-K) for {symbol}. Focus on revenue trends, margin trends, guidance changes, and any new risk factors."
            }
        ],
        search_mode="sec",
        search_after_date_filter="1/1/2025",
        web_search_options={"search_context_size": "high"},
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": SECResult.model_json_schema()}
        }
    )
    return SECResult.model_validate_json(
        completion.choices.message.content
    )
```

**Function 3: `enrich_analyst_consensus(symbol)`** — Track analyst upgrades/downgrades

```python
class AnalystAction(BaseModel):
    firm: str
    action: str  # UPGRADE, DOWNGRADE, INITIATE, REITERATE
    rating: str  # BUY, HOLD, SELL, OVERWEIGHT, etc.
    price_target: Optional[float] = None
    date: str

class AnalystResult(BaseModel):
    symbol: str
    actions_60d: List[AnalystAction]
    net_upgrades: int
    net_downgrades: int
    consensus_trend: str  # UP, DOWN, STABLE
    avg_price_target: Optional[float] = None

def enrich_analyst_consensus(symbol: str) -> AnalystResult:
    completion = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {
                "role": "system",
                "content": "You are a sell-side research tracker. Extract analyst rating changes, price target changes, and consensus trends. Return structured JSON."
            },
            {
                "role": "user",
                "content": f"List all analyst upgrades, downgrades, initiations, and price target changes for {symbol} in the last 60 days. Compute net upgrades vs downgrades and consensus trend."
            }
        ],
        search_recency_filter="month",
        search_domain_filter=["tipranks.com", "marketbeat.com", "benzinga.com", "reuters.com"],
        web_search_options={"search_context_size": "medium"},
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": AnalystResult.model_json_schema()}
        }
    )
    return AnalystResult.model_validate_json(
        completion.choices.message.content
    )
```

### 5.3 Composite Perplexity Score

All three functions combine into a single enrichment score per candidate:

```python
def compute_perplexity_composite(symbol: str) -> dict:
    news = enrich_news_sentiment(symbol)
    sec = enrich_sec_filings(symbol)
    analyst = enrich_analyst_consensus(symbol)

    # Veto logic
    if news.veto:
        return {"symbol": symbol, "action": "VETO", "reason": news.veto_reason}

    if sec.fundamental_risk_score > 0.7:
        return {"symbol": symbol, "action": "VETO", "reason": "high_fundamental_risk"}

    # Composite score: weighted average
    composite = (
        0.35 * (news.overall_sentiment_score + 1) / 2  # normalize -1..1 to 0..1
        + 0.35 * (1 - sec.fundamental_risk_score)       # lower risk = higher score
        + 0.30 * (1 if analyst.consensus_trend == "UP" else
                   0.5 if analyst.consensus_trend == "STABLE" else 0)
    )

    return {
        "symbol": symbol,
        "action": "PASS",
        "composite_score": round(composite, 3),
        "news_sentiment": news.overall_sentiment_score,
        "fundamental_risk": sec.fundamental_risk_score,
        "analyst_trend": analyst.consensus_trend,
        "net_upgrades": analyst.net_upgrades,
        "veto_flags": news.risk_flags
    }
```

***

## Part 6: Complete Signal Generation Pipeline

### 6.1 End-to-End Workflow

```
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: UNIVERSE FILTER (Daily pre-market)                  │
│  Filter: price, volume, option liquidity, sector             │
│  Output: ~200-500 tradeable symbols                          │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 2: FEATURE ENGINE (After first 30 min of RTH)         │
│  Compute: technicals, momentum, volatility, options-implied  │
│  Output: feature vector per symbol                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 3: ML DIRECTIONAL MODEL (XGBoost)                      │
│  Input: feature vectors                                      │
│  Output: ranked list with direction, confidence 0-10         │
│  Filter: keep only scores 8-10 (bullish) or 0-2 (bearish)   │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 4: MOMENTUM STAGE CLASSIFIER                           │
│  Input: IV spread, skew, momentum metrics                    │
│  Output: EARLY/LATE stage label                              │
│  Filter: keep only EARLY_STAGE matching direction            │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 5: ENTRY TIMING CHECK                                  │
│  Check: IV Rank < 50, MACD crossover, RSI range, regime     │
│  Filter: reject if timing signals are unfavorable            │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 6: PERPLEXITY ENRICHMENT (Top N candidates only)       │
│  Call: enrich_news_sentiment, enrich_sec_filings,            │
│        enrich_analyst_consensus                              │
│  Output: composite score, veto flags                         │
│  Filter: reject vetoed symbols, rank by composite            │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 7: ZEBRA CONSTRUCTION                                  │
│  Select: expiry (45-120 DTE), long strikes (~0.70Δ),        │
│          short strike (~0.50Δ), zero extrinsic check         │
│  Compute: net debit, breakevens, Greeks, payoff profile      │
│  Validate: max loss < risk cap, breakeven within 3%          │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 8: RISK VALIDATION                                     │
│  Check: per-trade cap, sector limits, portfolio exposure     │
│  Output: APPROVED / REJECTED                                 │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│  STEP 9: SIGNAL DISTRIBUTION                                 │
│  Push signal to: TradeMind UI, webhook, email                │
│  If auto-trade: submit to Tastytrade via broker connector    │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 Endpoints for Antigravity

**`POST /pipeline/run-daily`**
```json
{
    "as_of": "2026-02-15T10:00:00Z",
    "max_candidates": 20,
    "directions": ["LONG", "SHORT"],
    "auto_trade": false
}
```

Response:
```json
{
    "signals": [
        {
            "signal_id": "SIG-20260215-001",
            "symbol": "MSFT",
            "direction": "LONG",
            "ml_confidence": 8.7,
            "momentum_stage": "EARLY_STAGE_WINNER",
            "iv_rank": 32.5,
            "macd_signal": "BULLISH_CROSSOVER",
            "rsi": 58.3,
            "regime": "BULL",
            "perplexity_composite": 0.82,
            "news_sentiment": 0.65,
            "analyst_trend": "UP",
            "net_upgrades_60d": 4,
            "veto_flags": [],
            "zebra_spec": {
                "expiry": "2026-06-19",
                "long_strike": 380,
                "short_strike": 410,
                "long_qty": 2,
                "short_qty": -1,
                "net_debit": 18.50,
                "max_loss": 1850.00,
                "breakeven": 408.50,
                "breakeven_pct_from_spot": 1.2,
                "delta": 0.93,
                "theta": -0.06,
                "vega": 0.52
            },
            "reason_codes": [
                "strong_trend_above_50sma",
                "early_stage_momentum",
                "low_iv_rank",
                "positive_earnings_surprise",
                "analyst_consensus_upgrade",
                "low_crowding_score"
            ]
        }
    ],
    "vetoed": [
        {
            "symbol": "XYZ",
            "reason": "active_litigation_risk"
        }
    ]
}
```

***

## Part 7: ZEBRA Trade Management (Post-Entry)

### 7.1 Exit Rules

**Profit-Taking**:[^1][^2]
- Take profit at 50–100% of debit (configurable per risk profile)
- Ratchet winners: move short strike closer to ATM to lock in gains when position is profitable[^20]

**Time-Based**:[^21][^2]
- Close or evaluate at 21–30 DTE. Important: tastylive research shows **rolling ZEBRAs at 21 DTE is generally NOT recommended** because rolling adds debit and thus adds risk. Instead, close the position or take profits.[^21]
- Exception: if position is profitable and you want to continue exposure, open a new ZEBRA at higher strikes in a new expiry rather than rolling.

**Risk-Based**:[^2]
- Hard stop at 50–70% of max loss (never take full max loss)
- Exit if regime flips against direction (e.g., VIX spike + RSI collapse for bullish ZEBRA)
- Exit if Perplexity re-enrichment surfaces new material risk (litigation, regulatory)

### 7.2 Monitoring Endpoint

**`POST /zebra/monitor`** (runs every 10–15 min):
```json
{
    "position_id": "POS-001",
    "checks": ["pnl_target", "time_decay", "regime_flip", "perplexity_risk_rescan"]
}
```

Response:
```json
{
    "position_id": "POS-001",
    "current_pnl_pct": 0.62,
    "dte_remaining": 45,
    "recommendation": "RATCHET",
    "ratchet_details": {
        "new_short_strike": 420,
        "estimated_credit": 2.30,
        "new_breakeven": 412.00
    },
    "regime_status": "BULL_INTACT",
    "risk_rescan": "CLEAR"
}
```

***

## Part 8: Anti-Crowding Design

### 8.1 Crowding Detection Features

Build from institutional flow data and options microstructure:[^22][^9][^10]

| Feature | Source | Signal |
|---------|--------|--------|
| Small-lot call/put ratio | Options flow API | >2x = retail crowded long |
| Volume vs OI ratio | Options chain | >3x = fresh interest spike |
| Social mention velocity | Sentiment API | >95th percentile = meme risk |
| Aggressive fill % | Flow data | Sweeps above ask = institutional urgency |
| IV divergence from realized | Options chain | IV >> RV = priced in |

### 8.2 Anti-Crowding Rules

```python
CROWDING_RULES = {
    "max_crowding_score": 0.65,           # reject top 35% crowded
    "max_social_velocity_percentile": 90,  # avoid viral names
    "max_small_lot_call_ratio": 3.0,       # avoid retail pileup
    "reject_if_iv_rank_above": 70,         # avoid "priced in" names
    "prefer_institutional_flow_alignment": True  # only when smart money agrees
}
```

### 8.3 Adaptive Thresholds

Track ZEBRA performance by crowding decile monthly. If win rate drops in high-crowding deciles, tighten thresholds automatically:

```python
def adapt_crowding_threshold(performance_by_decile: dict) -> float:
    """Lower max_crowding_score if high-crowding trades underperform."""
    high_crowding_win_rate = performance_by_decile.get("Q4_Q5", {}).get("win_rate", 0.5)
    if high_crowding_win_rate < 0.40:
        return max(0.3, current_threshold - 0.05)  # tighten
    elif high_crowding_win_rate > 0.55:
        return min(0.8, current_threshold + 0.05)  # loosen
    return current_threshold
```

***

## Part 9: Implementation Phases for Antigravity

### Phase 1: Foundation (Weeks 1–4)
- Universe & data ingestion service (price, volume, options chains, fundamentals)
- Feature engine (24+ features per symbol)
- Basic ZEBRA constructor with delta/extrinsic validation
- Manual signal UI in TradeMind

### Phase 2: ML Models (Weeks 5–8)
- XGBoost directional model: train on 3+ years of data, rolling window, 0–10 scoring
- Momentum stage classifier using option-implied features
- Entry timing rules engine (IV + RSI + MACD + regime)
- Backtesting framework to validate model performance

### Phase 3: Perplexity Integration (Weeks 9–10)
- Implement three Sonar API enrichment functions (news, SEC, analyst)
- Composite scoring and veto logic
- Scheduled enrichment runs for top candidates
- Store enrichment results in DB for ML feedback

### Phase 4: Execution & Risk (Weeks 11–14)
- Tastytrade connector: multi-leg ZEBRA orders
- Risk manager: per-trade caps, sector limits, portfolio Greeks
- Exit automation: profit-taking, time-based, risk-based
- Ratcheting logic for winners

### Phase 5: Optimization (Ongoing)
- Anti-crowding layer with adaptive thresholds
- Execution ML (limit price optimization, fill-rate prediction)
- Continuous ML retraining with trade outcome feedback
- SHAP-based feature importance analysis for model interpretability

***

## Part 10: Key Takeaways

1. **Security selection is the primary alpha source** for ZEBRA. The structure itself is well-understood; the edge comes from choosing the right stock at the right time.

2. **Filter stack**: Combine liquidity filters → fundamental quality → trend confirmation → options-implied momentum stage → Perplexity news/filing enrichment → crowding check.

3. **Entry timing**: ZEBRA is a net premium buyer. Enter in low IV environments with confirmed momentum (MACD crossover, RSI 40–65, early-stage classification). Never enter in high IV or late-stage momentum.

4. **Perplexity Sonar API** provides real-time news sentiment, SEC filing analysis, and analyst consensus as structured JSON—filling the "current events" gap that pure quant models miss.

5. **Option-implied signals** (IV spread, skew, implied moments) are academically validated predictors of stock returns and momentum persistence—integrate them as first-class features in your ML models.

6. **Anti-crowding** is critical: track institutional flow alignment, penalize retail-crowded names, and adapt thresholds based on live performance.

7. **Do not roll ZEBRAs at 21 DTE**—tastylive research shows this adds risk. Instead, close and re-enter if thesis is intact.[^21]

---

## References

1. [Trade Strong Stocks with Defined Risk - The ZEBRA Strategy | Blog](https://optionsamurai.com/blog/zebra-strategy-trade-strong-stocks-defined-risk/) - The long ZEBRA strategy offers upside exposure similar to shares, with lower cost and capped downsid...

2. [The Comprehensive Guide To The ZEBRA Strategy](https://optionstradingiq.com/the-comprehensive-guide-to-the-zebra-strategy/) - This is a comprehensive guide to the ZEBRA strategy. We will deep dive into probability cones, risk ...

3. [Mastering the ZEBRA Options Strategy for Stock-Like Returns](https://doriantrader.com/mastering-the-zebra-options-strategy-unlocking-stock-like-returns-with-less-capital/) - This strategy is designed for traders seeking stock-like returns while minimizing the impact of extr...

4. [How I Pick Stocks For Options Trading - Focus - YouTube](https://www.youtube.com/watch?v=RVgzE4oiFOk) - How I Pick Stocks For Options Trading - Focus: Stock Replacement & Poor Man's Covered Calls In this ...

5. [How I Use IV Rank to Time My Option Entries 📊](https://www.youtube.com/watch?v=PbHSo1JCqj8) - Most traders sell options without knowing when volatility is on their side.

In this video, I’ll sho...

6. [Combining IV with RSI and MACD: A Guide to Timing Options ...](https://quantstrategy.io/blog/combining-iv-with-rsi-and-macd-a-guide-to-timing-options/) - Table of Contents Hide The Role of Implied Volatility (IV) in Options TimingUsing RSI and MACD for D...

7. [Combining Market Volatility and Momentum Signals: A Regime ...](https://www.linkedin.com/pulse/combining-market-volatility-momentum-signals-regime-framework-choi-2dbsc) - Revisiting the VIX > 30 Strategy: Historical Limitations and Behavioral Context Market timing and po...

8. [Combining Market Volatility and Momentum Signals](https://business101pub.com/combining-market-volatility-and-momentum-signals-a-regime-framework-using-vix-and-other-metrics/)

9. [My method on using AI to track institutional/big money options trades to make consistent profits](https://www.reddit.com/r/options/comments/1pgxtx3/my_method_on_using_ai_to_track_institutionalbig/) - My method on using AI to track institutional/big money options trades to make consistent profits

10. [Unusual Options Activity Detection | 10 Algorithms](https://optionomics.ai/features/unusual-activity) - Professional options intelligence platform with real-time flow tracking, AI-powered insights, and in...

11. [Option‐implied moments and the cross‐section of stock returns](https://onlinelibrary.wiley.com/doi/10.1002/fut.22304) - ## Abstract

We construct a joint score measure using option‐implied volatility, skewness, and kurto...

12. [Option-implied moments and the cross-section of stock returns](https://www.research.ed.ac.uk/en/publications/option-implied-moments-and-the-cross-section-of-stock-returns/)

13. [Options-implied information and the momentum cycle](https://www.sciencedirect.com/science/article/abs/pii/S1386418120300343) - We employ options-implied information derived from implied volatility spreads and implied volatility...

14. [Improving momentum strategies using residual returns and option‐implied information](https://onlinelibrary.wiley.com/doi/10.1002/fut.21988) - ## Abstract

This paper provides an alternative method for enhancing momentum profits by combining r...

15. [Option-Implied Skewness and the Momentum Anomaly](https://blogs.cfainstitute.org/investor/2019/02/22/option-implied-skewness-and-the-momentum-anomaly/) - What information does option-implied skewness contain, and how is it related to the momentum anomaly...

16. [Inferring Trade Directions in Options via Machine Learning](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5127667) - We develop GS-LASSO, a novel machine learning approach integrating XGBoost, SHAP, and LASSO, to clas...

17. [[PDF] A Machine Learning-Based Stock Prediction System Using XGBoost](https://kth.diva-portal.org/smash/get/diva2:1985833/FULLTEXT01.pdf) - This thesis presents a machine learning-based stock recommendation system de- veloped using the XGBo...

18. [Sonar API - Perplexity](https://docs.perplexity.ai/docs/sonar/quickstart) - Get started with Perplexity's Sonar API for web-grounded AI responses. Make your first API call in m...

19. [Search Filters - Perplexity API Docs](https://docs.perplexity.ai/docs/sonar/filters) - Target U.S. Securities and Exchange Commission filings and official financial documents. Key paramet...

20. [How to Ratchet a ZEBRA - Options Trading Concepts Live | tastylive](https://www.tastylive.com/shows/options-trading-concepts-live/episodes/how-to-ratchet-a-zebra-07-05-2023) - The tastylive crew explains the ZEBRA options trade, and they walk through the process of ratcheting...

21. [Rolling ZEBRAs At 21 DTE - From Theory to Practice](https://www.tastylive.com/shows/from-theory-to-practice/episodes/rolling-zebr-as-at-21-dte-07-07-2023) - Should you roll a ZEBRA option strategy at 21 DTE like most other option strategies?

22. [Unusual Options Activity: Our Market Trend Detection Tool | Intrinio](https://intrinio.com/blog/how-institutional-investors-use-intrinios-unusual-options-activity) - Unusual options activity reveals hidden market trends. See how institutional investors use our data ...

