# Unified Multi-Layer Options Swing Trading System: Video Review, Viability Analysis, and Implementation Plan

## Executive Summary

The YouTube video by Nick (Nick's Stock Café) presents a classic **Wheel Strategy** — repeatedly selling cash-secured puts on value stocks, collecting premium, and if assigned, flipping to selling covered calls until shares are called away. This is fundamentally different from the existing TQQQ mean-reversion diagonal spread system: the Wheel is a premium-collection/value-investing hybrid, while the diagonal is a directional swing trade. The two strategies are **not competitors — they are complementary layers** that can coexist in a unified system.[^1][^2]

This report evaluates the video strategy's viability, answers whether it constitutes arbitrage, and provides a comprehensive implementation plan that integrates: (1) the existing TQQQ diagonal spread on oversold dips, (2) a "close-and-reopen at lower price" rolling mechanism, (3) a multi-ticker watchlist scanner selecting big movers with high IV for premium selling, and (4) directional naked calls in low-VIX environments.

***

## Part 1: Video Strategy Review

### What the Video Teaches

The video describes a straightforward Wheel Strategy applied to value stocks around earnings:

- **Step 1 — Sell Put**: Sell a weekly cash-secured put at delta 0.20–0.30 on a stock the trader already wants to own (NVDA at $138 strike, ANF at $135/$145 strikes).[^2][^3]
- **Step 2 — If assigned, Sell Call**: Flip direction. Sell a covered call at the same delta (0.20–0.30) above cost basis. Example: assigned TSM at $195, sell $195 call for $187 premium.[^4][^5]
- **Step 3 — Repeat**: When called away, go back to selling puts. The cycle generates income from both sides of a consolidating stock.[^6][^7]
- **Key principle**: Only sell puts on stocks you genuinely want to own at prices below your DCF fair value.[^2]
- **Earnings boost**: Sell during earnings week to capture elevated IV premiums (ANF example: $600+ in one week).[^8][^9]

### Is This Arbitrage?

**No, this is not arbitrage.** Arbitrage implies risk-free profit from mispricing. The Wheel carries real risk:

- If the stock drops 30% after put assignment, the covered call premiums cannot offset the capital loss quickly.[^10]
- During 2022-style drawdowns, Wheel traders on NVDA or TSM would have been stuck holding deeply underwater shares, unable to sell calls above cost basis.[^5][^3]
- It is better classified as a **premium-harvesting strategy with stock ownership as the fallback**.[^2]

### Viability Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Income consistency | ★★★★☆ | 1–3% weekly on earnings plays, 0.5–1% on non-earnings weeks[^2] |
| Drawdown risk | ★★☆☆☆ | Full stock ownership risk if assigned during a crash[^10] |
| Capital efficiency | ★★☆☆☆ | Cash-secured puts tie up 100× strike per contract[^1] |
| Scalability | ★★★☆☆ | Works on any liquid stock; limited by account size |
| Compatibility with TQQQ system | ★★★★★ | Completely different risk profile; diversifies strategy portfolio |

***

## Part 2: The "Close-and-Reopen" Rolling Mechanism

### The Proposed Idea

When TQQQ drops after entering a put diagonal spread:
1. Close the **entire** diagonal (both legs) — the long put profits, the short put loses, but you capture whatever net value remains.
2. Immediately re-open a **new** diagonal spread at the current (lower) TQQQ price.
3. This avoids ever holding a naked put (defined risk at all times).
4. Allow up to 2 rolls before hitting the hard stop.

### Why This Is Superior to Legging Out

The earlier conversation identified the danger of closing only the long put and holding a naked short put. The close-and-reopen approach eliminates that risk entirely:

| Approach | Max Loss | Naked Exposure | Capital Efficiency |
|----------|----------|----------------|-------------------|
| Leg out (close long only) | ~$80K on 20 lots (undefined) | Yes — naked short puts | Dangerous |
| Close entire + reopen lower | Spread width × contracts (defined) | Never | Safe, predictable |
| Hold and hope | Spread width (but opportunity cost) | No | Capital locked in losing trade |

The close-and-reopen approach works because each new diagonal is centered around the current price, meaning:
- The new short put collects fresh premium at a strike that is closer to ATM (higher premium).
- The new long put provides downside protection at the new, lower level.
- The net effect is a **cost-averaged entry** without naked exposure.[^11][^12]

### Implementation Rules

- **Trigger**: TQQQ drops 5% from entry price → close entire spread, immediately reopen at current price.
- **Roll limit**: Maximum 2 rolls. After the 2nd roll, if TQQQ drops another 5%, close for loss (hard stop at ~15% total).
- **DTE reset**: Each new diagonal uses the same DTE/delta rules from the ML optimizer (or static 45/10 DTE).
- **Accounting**: Track cumulative P&L across all rolls as a single "trade" for performance measurement.

***

## Part 3: Multi-Ticker Watchlist Scanner System

### Architectural Design

Instead of trading only TQQQ, the system scans a universe of liquid stocks/ETFs daily and selects the best candidates based on a combination of technical oversold signals and high implied volatility.[^13][^14]

### Watchlist Universe

The scanner should monitor 30–50 liquid tickers with weekly options and tight bid-ask spreads:

| Category | Tickers | Rationale |
|----------|---------|-----------|
| 3x Leveraged ETFs | TQQQ, UPRO, SOXL | High vol, strong mean-reversion, existing expertise |
| Mega-cap Tech | NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA | Deep liquidity, $0.01 spreads, high IV around earnings[^8] |
| Semiconductors | AMD, AVGO, MU, QCOM | High beta, earnings-driven IV spikes |
| High-beta Growth | SHOP, SQ, COIN, MARA, PLTR | Frequent oversold extremes, rich put premiums |
| Defensive/Value | JPM, GS, UNH, TSM, V | Lower vol, Wheel-strategy candidates for covered calls[^2] |

### Scanner Filters (Daily Pre-Market)

The scanner runs every morning at 8:00 AM ET and produces a ranked list of candidates:

**Filter 1 — Oversold Signal** (Required):
- RSI-2 < 10 (primary trigger)[^15][^13]
- OR Bollinger %B < 0.0 (price below lower band)
- OR 3-day return < -8% (large sudden drop)

**Filter 2 — IV Environment** (Determines strategy):
- IV Rank > 50 → High IV regime → **Sell put diagonal spread** or **sell put credit spread**[^16][^8]
- IV Rank < 30 → Low IV regime → **Buy naked call** (cheap premium, high gamma leverage)

**Filter 3 — Liquidity Gate** (Hard requirement):
- Average daily volume > 5M shares
- Options bid-ask spread < $0.10 on ATM strikes
- Weekly options available

**Filter 4 — Regime Confirmation**:
- Stock trading above 200-day SMA (uptrend intact — mean reversion likely)[^14]
- OR stock dropped > 15% in 5 days but VIX < 25 (panic selling in calm market — capitulation bounce likely)

### Ranking Formula

Score each candidate that passes all filters:

\[
\text{Score} = w_1 \cdot \text{RSI\_Extremity} + w_2 \cdot \text{IV\_Rank} + w_3 \cdot \text{Options\_Liquidity} + w_4 \cdot \text{Mean\_Reversion\_History}
\]

Where:
- RSI_Extremity = (10 - RSI_2) / 10 — more oversold = higher score
- IV_Rank = percentile rank of current IV — higher IV = richer premiums[^8]
- Options_Liquidity = 1 / (bid_ask_spread × 100) — tighter spreads = better execution
- Mean_Reversion_History = historical 5-day bounce rate after RSI < 10 for this ticker

Select the **top 3** candidates daily. This ensures capital concentration on the best opportunities rather than spreading too thin.

***

## Part 4: Strategy Selection Matrix

### When to Use Which Strategy

The key innovation is **dynamically selecting the strategy** based on market conditions per ticker:

| Condition | Strategy | Structure | Why |
|-----------|----------|-----------|-----|
| RSI-2 < 10 + IV Rank > 50 + VIX > 50d SMA | **Put Diagonal Spread** | Sell 45 DTE / Buy 10 DTE put | High IV → rich premium on short leg; IV crush benefits the short side on bounce[^11][^12] |
| RSI-2 < 10 + IV Rank > 50 + same-strike trap | **Bull Put Credit Spread** | Sell/Buy same DTE puts, 1+ strike width | Avoids calendar spread gamma drag when nominal price is low |
| RSI-2 < 10 + IV Rank < 30 + VIX < 50d SMA | **Naked Long Call** | Buy 14 DTE call at 30-delta | Cheap premium in low IV; pure directional bet on bounce with gamma leverage |
| RSI-2 > 70 (overbought) + IV Rank > 50 | **Call Diagonal Spread (Bearish)** | Sell 45 DTE / Buy 10 DTE call | The inverse play — sell the overbought spike, profit from reversion downward |
| Earnings within 5 days + stock in watchlist | **Wheel Entry (Sell Put)** | Cash-secured put at 20-30 delta, weekly expiry | Elevated IV from earnings uncertainty generates outsized premium[^9][^8] |
| Assigned from Wheel put | **Wheel Continuation (Sell Call)** | Covered call at 20-30 delta above cost basis | Generate income while waiting for stock to recover[^2][^4] |

### Capital Allocation

| Layer | Strategy | Allocation | Max Positions |
|-------|----------|------------|---------------|
| Layer 1 — TQQQ Swing | Put diagonal / credit spread | 40% of options BP | 3 concurrent spreads |
| Layer 2 — Multi-Ticker Swing | Diagonal / naked call on top scanner picks | 30% of options BP | 3 concurrent positions |
| Layer 3 — Wheel Premium | Cash-secured puts + covered calls on value names | 30% of options BP | 2 concurrent wheels |

***

## Part 5: Bearish / Overbought Mirror Strategy

### The Opposite Trade

The system should also scan for the **biggest gainers** — stocks that have spiked RSI-2 > 90 — and enter bearish mean-reversion trades:

- **High IV + Overbought**: Sell a call diagonal spread (sell 45 DTE call, buy 10 DTE call). Profit when the overbought stock pulls back.
- **Low IV + Overbought**: Buy a naked long put (14 DTE, 30-delta). Cheap directional bet on a pullback.

This doubles the signal frequency by capturing both oversold bounces AND overbought fade-backs. The RSI-2 strategy historically shows strong mean-reversion from both extremes.[^17][^18]

### Bearish Scanner Filters

- RSI-2 > 90
- 3-day return > +10%
- Stock below 200-day SMA (the rally is a dead-cat bounce in a downtrend — high probability of continuation lower)
- OR stock above 200-day SMA but 3-day return > +15% (over-extension in an uptrend)

***

## Part 6: Comprehensive Implementation Plan

### Phase 1 — Foundation (Week 1–2)

**Goal**: Implement the close-and-reopen rolling mechanism and basic multi-ticker scanner.

**Tasks**:
1. Modify existing TQQQ trading bot to implement the "close entire spread + reopen lower" logic with 5% trigger and 2-roll limit.
2. Build a watchlist of 30–50 tickers in tastytrade (use the categories from Part 3).
3. Create a Python script that pulls daily RSI-2 and IV Rank for all watchlist tickers using the tastytrade API or a data provider like Polygon/CBOE.
4. Implement the scoring formula and output a ranked daily report.

**Deliverable**: Daily pre-market email/Telegram alert with top 3 oversold + top 3 overbought candidates, ranked by score.

### Phase 2 — Strategy Router (Week 3–4)

**Goal**: Automate the strategy selection logic from the matrix in Part 4.

**Tasks**:
1. Build the `StrategyRouter` class that takes (ticker, RSI, IV_Rank, VIX, VIX_SMA, nominal_price) and outputs the recommended structure (diagonal, vertical, naked call, wheel entry).
2. Implement the **calendar-trap detector**: if the target anchor delta and hedge delta map to the same strike → auto-switch to bull put credit spread.
3. Add the bearish mirror: RSI-2 > 90 triggers call diagonal or naked put.
4. Connect the router output to the tastytrade order builder.

**Deliverable**: Automated trade ticket generation — the system outputs a ready-to-review order for each candidate.

### Phase 3 — Wheel Layer Integration (Week 5–6)

**Goal**: Add the Wheel Strategy as a separate income layer targeting earnings-week plays.

**Tasks**:
1. Build an earnings calendar scanner that identifies upcoming earnings in the watchlist (use tastylive's earnings calendar or a free API).
2. For earnings within 5 days: calculate the expected move, set the put strike at 1× expected move below current price (delta ~0.20).[^2]
3. If assigned: automatically queue a covered call sell order at the same delta above the assignment price.[^4][^5]
4. Track the Wheel's cumulative cost basis reduction per ticker.

**Deliverable**: Wheel-specific trade log showing premium collected, assignments, and net cost basis per ticker.

### Phase 4 — ML Optimizer Integration (Week 7–10)

**Goal**: Replace static parameters with the ML-optimized output from the previous report.

**Tasks**:
1. Extend the RL agent's action space to include a `structure_type` discrete choice alongside continuous DTE/delta.
2. Train the agent on multi-ticker data (not just TQQQ) to learn which structure works best per regime × ticker characteristics.
3. The agent receives the daily scanner's top candidates and outputs optimized parameters for each.
4. Paper trade for 2–4 weeks before going live.

**Deliverable**: Trained model deployed as a daily inference service, outputting trade parameters for the top scanner picks.

### Phase 5 — Full Automation (Week 11–12)

**Goal**: End-to-end automation from scanner → strategy selection → order placement → management → exit.

**Tasks**:
1. Connect all layers via a single orchestrator: `Scanner → StrategyRouter → MLOptimizer → OrderBuilder → tastytrade API`.
2. Implement position monitoring: track all open positions, apply rolling rules (5% drop → close+reopen), and exit rules (RSI-2 > 70 or 5-day SMA cross).
3. Build a dashboard showing: active positions by layer, daily P&L, cumulative returns, capital utilization.
4. Set up risk guardrails: max 8 concurrent positions across all layers, max 80% BP utilization, VIX circuit breaker kills all new entries.

**Deliverable**: Fully automated system with human-in-the-loop approval for each trade (click to approve/reject via Telegram).

***

## Risk Analysis

### Combined System Risks

| Risk | Mitigation |
|------|------------|
| Correlated crash (all tickers drop together) | VIX circuit breaker + Hurst regime gate disable new entries; existing spreads have defined risk |
| Wheel assignment during drawdown | Only Wheel stocks with strong fundamentals at prices below DCF fair value[^2] |
| Over-diversification diluting returns | Cap at 8 total positions; top-3 scanner picks only |
| Scanner generating false signals in trending markets | 200-day SMA filter + Hurst exponent < 0.45 requirement[^19] |
| Execution slippage on multi-leg spreads | Liquidity gate (bid-ask < $0.10); avoid illiquid names |
| Calendar spread trap on low-price tickers | Automatic detection and fallback to equal-DTE vertical |

### Expected Return Profile

| Layer | Est. Annual Trades | Avg Win | Avg Loss | Win Rate | Est. Annual Return |
|-------|-------------------|---------|----------|----------|--------------------|
| TQQQ Diagonal (with rolling fix) | 20–30 | $400 | -$600 | 70% | 8–12% on allocated capital |
| Multi-Ticker Swing | 40–60 | $350 | -$500 | 65% | 10–15% on allocated capital |
| Wheel Premium | 30–50 | $300 | -$800 (assignment) | 80% (OTM expiry) | 12–18% on allocated capital[^20] |
| **Blended (40/30/30 allocation)** | **90–140** | — | — | — | **10–15% annualized on total account** |

The blended system targets 10–15% annualized — significantly above the current ~4.5% — primarily by: (1) fixing the calendar spread trap, (2) tripling signal frequency via multi-ticker scanning, and (3) adding the Wheel as a steady income floor.

---

## References

1. [Three Things to Know About the Wheel Strategy | Charles Schwab](https://www.schwab.com/learn/story/three-things-to-know-about-wheel-strategy) - The wheel strategy is a popular options strategy that involves selling cash-secured puts on a stock,...

2. [Sell A Covered Call](https://optionalpha.com/blog/wheel-strategy) - The options wheel strategy is an income producing strategy that involves selling put options, potent...

3. [The Wheel Strategy Explained | Profiting While Managing ...](https://www.optionstrading.org/blog/the-wheel-strategy-explained/) - Learn how the Wheel Strategy helps options traders generate steady income while managing risk. A ste...

4. [What is the Wheel Strategy in Options Trading? - OptionsPlay](https://www.optionsplay.com/blogs/what-is-the-wheel-strategy-in-options-trading) - The Wheel strategy of using Cash Secured Puts and Covered Calls allows you to “buy low and sell high...

5. [The Wheel (aka Triple Income) Strategy Explained](https://www.reddit.com/r/Optionswheel/comments/1gpslvk/the_wheel_aka_triple_income_strategy_explained/) - The Wheel (aka Triple Income) Strategy Explained

6. [Options Wheel Strategy Explained: Definition and How to Trade](https://www.moomoo.com/us/learn/detail-options-wheel-strategy-117831-250138079) - The wheel strategy in options trading is a systematic, income-generating strategy that involves sell...

7. [The Wheel Strategy: Consistent Options Income - Longbridge](https://longbridge.com/en/academy/options/blog/100086) - Learn how the options wheel strategy generates consistent income through cash-secured puts and cover...

8. [Why Implied Volatility Matters for Your Options Income Strategy](https://www.rexshares.com/why-implied-volatility-matters-for-your-options-income-strategy/) - Sell options when IV is high: Premiums are richest when volatility expectations are elevated. An opt...

9. [Selling puts more attractive during high IV times?](https://www.reddit.com/r/thetagang/comments/jd1l3p/selling_puts_more_attractive_during_high_iv_times/)

10. [Wheel vs Spreads](https://www.reddit.com/r/thetagang/comments/m44o4s/wheel_vs_spreads/) - Wheel vs Spreads

11. [24 Options Income Strategies for Consistent & Safe Profit Generation](https://www.strike.money/options/best-options-income-strategies) - Diagonal Spread, Mild Directional, Moderate, Combines income with directional bias ... strategies fo...

12. [Calendar Spread & Diagonal Spread: Strategy, Pros & Cons, Real ...](https://marketrebellion.com/news/trading-insights/what-a-calendar-spread-is-and-when-to-use-it-with-a-real-life-trade-example/) - Both a diagonal spread & calendar spread allow option traders to collect premium and time decay. The...

13. [RSI Screener - Spot Overbought Oversold - IndicatorSignals.com](https://indicatorsignals.com/rsi-screener) - Find overbought & oversold opportunities! Use our free RSI screener to identify potential reversals ...

14. [Use Tagged Symbols to Find Trade Ideas - Option Alpha](https://optionalpha.com/blog/use-tagged-symbols-to-find-trade-ideas) - Uptrend Oversold Bounce automated options strategy. Set specific filters to look for low RSI, and so...

15. [Top Oversold Stocks Right Now | Track Stocks Relative to RSI](https://www.marketbeat.com/market-data/oversold-stocks-rsi/) - Gainers & Decliners · Percentage Gainers · Percentage Decliners · Pre-Market Movers ... This Week's ...

16. [IV Screener - Advanced Implied Volatility Stock Scanner & Options ...](https://www.justticks.in/iv-screener) - Professional implied volatility screener for NSE options. Filter stocks by IV ranges, volume, open i...

17. [Trading the mean reversion curve - by Quantitativo](https://www.quantitativo.com/p/trading-the-mean-reversion-curve) - Trading the mean reversion curve. A portfolio of mean-reversion strategies that delivers 26% annual ...

18. [RSI2 Strategy: Double returns with a simple rule change](https://alvarezquanttrading.com/blog/rsi2-strategy-double-returns-with-a-simple-rule-change/) - While playing around with a 2 period RSI (Relative Strength Index) mean reversion strategy, I came u...

19. [The Hurst Exponent: Trend vs Range Detection | FractalCycles Guides](https://fractalcycles.com/guides/hurst-exponent-explained) - Learn how to calculate the Hurst exponent (H), interpret values from 0 to 1, and determine if a mark...

20. [Wheel Options Strategy: The Complete Guide to Generating ...](https://options.cafe/blog/wheel-options-strategy-complete-guide/) - Master the wheel options strategy with this complete guide. Includes real trading results ($27000+ p...

