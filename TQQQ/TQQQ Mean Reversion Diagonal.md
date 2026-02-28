# Automated Mean-Reversion Swing Trading on TQQQ via Put Diagonal Spreads

## Executive Summary

This report addresses four questions about building a mean-reversion swing trading system on TQQQ (3x leveraged Nasdaq-100 ETF) using put diagonal spreads as the vehicle. The analysis covers optimal delta/DTE construction for directional sensitivity, quantitative signal selection for 3–5 day reversals, regime filters to avoid 2022-style trend continuation, and relevant academic and practitioner literature. Because the strategy is explicitly directional — profiting from the spread's P&L as TQQQ bounces — rather than theta-based, the emphasis is on maximizing short-term delta/gamma responsiveness while managing the unique risks of 3x leverage.

***

## Q1: Optimal Delta and DTE for Directional Sensitivity

### The Core Mechanic

In a put diagonal used for directional P&L on a bounce, two legs interact:

- **Short put (sold, 30–60 DTE):** When TQQQ rallies, this put loses value — that's the profit engine. Higher delta on this leg means more sensitivity to the upward price move.[^1][^2]
- **Long put (bought, 7–12 DTE, lower strike):** Acts as crash protection. It should be cheap enough to not eat the profit but responsive enough to save the position if the dip continues.[^3][^1]

The spread's net delta is the difference between the two put deltas. Since both deltas are negative, selling the higher-delta (closer-to-ATM) put and buying the lower-delta (further-OTM) put creates a **net positive delta** — exactly what a bounce trade requires.

### Recommended Delta/DTE Framework

| Leg | Delta | DTE | Rationale |
|-----|-------|-----|-----------|
| Short put (sold) | -0.35 to -0.45 | 30–45 DTE | High enough delta for meaningful directional P&L; 30–45 DTE keeps theta manageable without excessive premium outlay; ATM gamma is highest but also riskiest[^4][^5] |
| Long put (bought) | -0.15 to -0.25 | 7–12 DTE | Low premium cost; high gamma near expiration amplifies protection on continued selloffs; provides defined risk on a crash day[^6][^7] |
| Net spread | +0.15 to +0.25 net delta | — | Enough directional bias to capture a 5–10% TQQQ bounce over 3–7 days |

### Why This Configuration Works for Directional Swings

**Short put delta of -0.35 to -0.45 (not -0.50):** Going full ATM on the short put maximizes delta but also maximizes gamma risk if the dip continues. Stepping slightly OTM to -0.35 to -0.45 retains ~70–90% of the directional sensitivity while giving more room on the downside. For a 30–45 DTE option on TQQQ (IV typically 60–90%), this also means richer absolute premium than shorter DTE alternatives.[^4][^8][^9]

**Long put at 7–12 DTE:** This is deliberately short-dated. The near-expiration long put has extremely high gamma, meaning if TQQQ continues to dump, the long put's delta accelerates toward -1.0 fast, providing emergency protection. However, it bleeds theta rapidly, which is the cost of insurance. If the bounce happens within 3–5 days, the short-dated long put still has residual value. If the bounce takes 7+ days, the long put may expire worthless, leaving the short put naked — a scenario that demands strict exit discipline.[^6][^7]

**TQQQ-specific consideration:** TQQQ's IV is approximately 3x QQQ's IV (typically 60–90% in normal conditions, spiking to 150%+ in stressed markets). This means absolute option premiums are fat relative to the underlying's price, creating wide bid-ask spreads at far OTM strikes. Sticking to strikes with strong open interest (multiples of $5 on TQQQ) ensures better fills.[^9][^10]

### Gamma and Vega Dynamics

The spread is **net long gamma** due to the short-dated long put's elevated gamma overwhelming the longer-dated short put's lower gamma. This is desirable: on a continued dip, the long put's delta accelerates protectively. On a bounce, the short put loses value faster because its higher absolute delta drives the profit.[^6]

The spread is also **net long vega** since the longer-dated short put has more vega exposure. In a dip scenario, IV typically spikes — this benefits the position (the long vega hedge helps). On the bounce, IV typically contracts, which hurts the long vega position. This means the directional P&L on the bounce needs to overcome a modest vega headwind from IV compression.[^11][^12]

***

## Q2: Quantitative Signals for 3–5 Day Mean Reversion in TQQQ

### Signal Comparison

| Signal | Mechanism | Effectiveness for TQQQ | Key Threshold |
|--------|-----------|----------------------|---------------|
| **RSI-2 < 10** | Extremely oversold on 2-period RSI; captures "too far, too fast" pullbacks within a trend | Strong. Connors' research shows 72–77% win rate on leveraged ETFs; works best when filtered by trend (price > 200 MA)[^13][^14][^15] | RSI-2 < 5–10 for entry; exit when price > 5-day MA or RSI-2 > 70[^13][^16] |
| **Bollinger Band %B < 0** | Price below lower Bollinger Band (2 standard deviations from 20-period mean) | Moderate standalone; better as confirmation. In fast-trending selloffs, price can "walk the band" for days without reverting[^17][^18] | %B < 0 (below lower band); combine with RSI for confirmation |
| **VIX term structure inversion** | VIX futures in backwardation signals extreme near-term fear; historically occurs ~16% of the time[^19][^20] | Excellent regime signal but not a timing signal. Backwardation confirms panic is present but doesn't pinpoint the reversal day[^21][^22] | VIX M1 > VIX M2 (front month > second month) |
| **Volume capitulation** | Extreme volume spike (>2x 20-period average) on a down day suggests forced/panic selling near exhaustion[^23][^24] | Good confirmation filter. A swing low on high volume suggests selling climax[^23]. Best combined with price-based signals | Volume > 2x 20-day average + RSI-2 < 10 |

### Recommended Signal Stack

The most effective approach for TQQQ specifically combines multiple signals rather than relying on any single indicator:

1. **Primary entry trigger:** RSI-2 < 10 (or more aggressively, < 5 for higher win rates but fewer signals). Larry Connors' RSI-2 Pullback variant requires three consecutive RSI-2 readings below 10, which further filters for genuine capitulation rather than one-day noise.[^13][^15]

2. **Trend filter:** TQQQ price must be above its 200-day moving average. This single condition is the most important regime gate — it ensures the dip is a pullback within an uptrend rather than a continuation of a bear trend. Backtests of Connors RSI-2 on SPY consistently show that adding a 200 MA filter preserves the strategy's edge while filtering out destructive trades.[^14][^25][^16][^13]

3. **Confirmation (optional but additive):** Volume capitulation (current day volume > 2x 20-day average) or Bollinger %B < 0 provides confluence. The volume spike confirms that the selling is climactic rather than orderly.[^23][^24]

4. **Exit trigger:** Price closes above the 5-day moving average, or RSI-2 > 70. For the put diagonal specifically, this translates to closing the entire spread when the short put has lost significant value from the bounce.[^13][^14]

### RSI-2 on Leveraged ETFs: Backtested Evidence

CXO Advisory backtested RSI-2 (10-90 thresholds) on SSO (2x S&P) from 2006–2019 and found a 72% win rate with an average trade return of 1.0%, but a CAGR of only 4.9% vs. 11.6% buy-and-hold — because the strategy is in the market only ~40% of the time. The more conservative RSI-2 (5-70) produced 77% win rate, 1.6% average trade return, and was in the market only 11% of the time. The worst loss was -40.4% during September–November 2008, highlighting the catastrophic tail risk without a regime filter.[^15]

For TQQQ specifically, a Reddit backtester found that a mean reversion swing algo produced CAGR of 154% during volatile 2024–2025 markets vs. 74% for buy-and-hold TQQQ, with lower drawdowns. Over the full 2024–2025 period, the combined results closely matched buy-and-hold (121% vs. 124% CAGR) but with notably better risk-adjusted returns.[^26]

***

## Q3: Crash Guard — Distinguishing Dips from Trend Continuation

### The 2022 Problem

In 2022, TQQQ fell approximately 80%, and every apparent "dip" was a trap — RSI-2 would flash oversold, price would bounce 5–10%, then resume falling. The TQQQ/TMF hedge strategy that many relied on also failed catastrophically (-75.47% for 60/40 TQQQ/TMF) because bonds and equities fell simultaneously during rate hikes. Any mean-reversion system without a regime filter would have been destroyed by repeated false signals.[^27]

### Multi-Layer Regime Filter Framework

The following tiered filter system addresses the 2022 problem, with each layer adding protection:

**Layer 1 — Trend Gate (200-Day Moving Average):**
The most backtested and widely validated filter is simply requiring price to be above its 200-day SMA before taking any long mean-reversion trade. Paul Tudor Jones famously uses the 200 MA as a defensive line: "I've seen too many things go to zero. If you use the 200-day moving average rule, then you get out". In the Connors RSI-2 backtest, adding a stop loss when price closes below the 200 MA actually *hurt* performance because it cut trades prematurely. The better approach is to simply **not enter** new trades when below the 200 MA rather than using it as a stop.[^28][^25][^16][^14][^13]

**Layer 2 — VIX Regime Classification:**
A VIX-based regime filter classifies the market into volatility buckets. A practical implementation uses a 50-day SMA of the VIX:[^29]

- **Low-vol regime (VIX < VIX 50-SMA):** Full position size. Mean reversion works well here.
- **Elevated-vol regime (VIX > VIX 50-SMA but < VIX 50-SMA × 1.15):** Half position size. Mean reversion still works but with wider stops.
- **Crisis regime (VIX > VIX 50-SMA × 1.15):** No new trades. The 15% buffer represents approximately the 90th percentile of VIX deviations from its average, ensuring the system stays in "bull" mode ~90% of the time.[^30]

A regime-based overnight mean reversion model on leveraged ETFs using VIX-based classification achieved a 3.3+ Sharpe ratio with 64% win rate and low correlation to SPX. The key insight: regime classification using momentum indicators and volatility measures allows mean reversion to work in appropriate conditions while sitting out destructive ones.[^31][^32]

**Layer 3 — VIX Term Structure Confirmation:**
When the VIX futures curve inverts (backwardation), it signals acute market stress. Backwardation occurs only ~16% of the time and often coincides with market bottoms — but in a sustained bear market like 2022, backwardation can persist for weeks. The rule: **if VIX is in backwardation AND price is below the 200 MA, absolute no-trade zone.** If VIX is in backwardation but price is still above the 200 MA, reduce position size to 25%.[^22][^21][^19][^20]

**Layer 4 — Crash Circuit Breaker:**
A hard stop for catastrophic protection: if TQQQ drops more than 20% in a single day, exit all positions and move to cash. One backtested TQQQ/TMF strategy used this exact filter and reduced maximum drawdown from ~75% to ~28%. Re-entry requires TQQQ to recover above its pre-crash level.[^33]

### Why the 200 MA Filter Is Paramount for TQQQ

Academic research confirms that leveraged ETFs suffer disproportionately in mean-reverting regimes due to volatility drag — the daily rebalancing mechanism amplifies losses when prices oscillate rather than trend. In a bear market, TQQQ's path-dependent losses compound: a 50% decline in QQQ produces roughly 80–90% in TQQQ, and recovery requires a 9x return (QQQ would need to triple). The 200 MA filter prevents the strategy from fighting this structural headwind.[^34][^35][^36]

***

## Q4: Academic Papers and Practitioner Frameworks

### Academic Literature

There is no large academic body specifically on "swing trading options spreads on mean-reversion signals in leveraged products." However, several adjacent literatures are directly applicable:

**Mean Reversion in Equity Returns:**
- **Avellaneda & Lee (2008/2010), "Statistical Arbitrage in the U.S. Equities Market":** The foundational paper for systematic mean-reversion trading. Uses Ornstein-Uhlenbeck (OU) processes to model residual mean reversion, with an average expected reversion time of ~7 days and equilibrium spread volatility of ~300 bps. The s-score framework (standardized deviation from mean) provides a principled entry/exit system. While focused on equity pairs, the OU model is directly applicable to modeling TQQQ's mean-reversion behavior.[^37][^38]

- **Da & Gao / Miwa (NY Fed Staff Report 513), "Decomposing Short-Term Return Reversal":** Shows that short-term reversal is driven by liquidity shocks on the long side (buying recent losers) and investor sentiment on the short side (selling recent winners). The reversal is strongest for intraday price movements and during volatile market conditions. This supports the thesis that TQQQ dip-buying captures liquidity premium.[^39][^40]

- **Nagel (2012), "Evaporating Liquidity":** Demonstrates that short-term reversal returns are a proxy for returns from liquidity provision, and that expected returns from liquidity provision spike during periods of financial turmoil (predictable via VIX). This directly supports using VIX as a regime filter — higher VIX = higher expected returns from mean reversion, but also higher risk.[^41]

**Leveraged ETF Compounding and Mean Reversion:**
- **Barbon et al. (2025), "Compounding Effects in Leveraged ETFs":** Demonstrates that in mean-reverting markets, LETFs underperform their target multiples due to negative compounding effects, while in trending markets they outperform. This is critical context: the strategy profits from mean reversion in the underlying but must contend with TQQQ's structural tendency to lose value during the exact regime being traded.[^35][^34]

- **Barbon, Buraschi & Moerke (2022), "Liquidity Provision to Leveraged ETFs and Equity Options Rebalancing Flows":** Shows that LETF rebalancing creates predictable end-of-day momentum and next-day mean reversion, with annualized Sharpe ratios of ~3–5 for strategies exploiting this flow. LETF rebalancing increases end-of-day returns by 430% of the average return in the last half hour — a structural feature that can be exploited.[^42][^43][^44]

**Options-Based Mean Reversion:**
- **Reinforcement Learning for Statistical Arbitrage (arXiv:2403.12180):** Introduces a model-free framework for statistical arbitrage using empirical mean reversion time as the optimization criterion, moving beyond the OU-process assumption. While focused on equity spreads, the methodology for minimizing empirical mean reversion time is applicable to options spread construction.[^45]

### Practitioner Frameworks

**Larry Connors' RSI-2 System:** The most widely backtested short-term mean-reversion framework for equities. Core rules: RSI(2) < 5–10 for entry, price above 200 MA as trend filter, exit when price crosses above 5-day MA. Backtests show ~72–77% win rates on SPY with strong risk-adjusted returns. The RSI-2 Pullback variant (three consecutive RSI readings below threshold) further improves signal quality.[^16][^14][^13]

**Moontower Meta (Kris Abdelmessih) — Structuring Directional Option Trades:** A practitioner framework arguing that 90% of directional option trading work happens upstream of the option expression. The key principle for spread construction: the short leg should correspond to the most likely landing spot based on fundamental analysis, and vertical/diagonal spreads are preferred because they cancel many Greeks and allow thinking in discrete bets. For directional trading (as opposed to vol trading), the IV vs. RV comparison matters less — but avoiding buying options when historical vol is extremely elevated is still prudent.[^46]

**Data Driven Options — Diagonal Covered Put Optimization:** Practitioner backtesting of diagonal put spreads found that higher deltas (40–50 delta on both legs) provided better protection and premium capture than the traditional 20–30 delta range. A 60 DTE long / 3 DTE short configuration at 40 delta produced 106% return on capital in 2024 with 34% max drawdown.[^8]

**Regime-Based Overnight Mean Reversion (Christian Zahl):** A live-traded system on leveraged ETFs using five market regimes (strong bull, bull, neutral, sideways, unpredictable) based on SPY momentum and VIX. Achieved 24–26% returns over 3 months with 64% win rate, Sharpe > 3, and low correlation to SPX. Key finding: inverse/bear ETFs did not mean-revert as reliably as bull-leveraged ETFs.[^32][^31]

***

## Implementation Recommendations

### Trade Execution Workflow

1. **Daily scan (3:30 PM EST):** Check RSI-2 on TQQQ. If RSI-2 < 10 and TQQQ > 200 MA and VIX regime is green/yellow, flag as candidate.
2. **Signal confirmation:** Verify volume capitulation (>2x 20-day average) and/or Bollinger %B < 0 for confluence.
3. **Spread construction:** Sell 30–45 DTE put at -0.40 delta; buy 7–12 DTE put at -0.20 delta. Enter as a net credit or small debit depending on strike selection.
4. **Position sizing:** Risk no more than 2–3% of portfolio per trade. Account for TQQQ's 3x leverage when calculating notional exposure.
5. **Exit on bounce:** Close entire spread when price crosses above 5-day MA or RSI-2 > 70, typically 3–7 days.
6. **Emergency exit:** If TQQQ drops another 10%+ after entry, close immediately regardless of signal — the dip has likely become trend continuation.
7. **Long put expiration management:** If the long put is approaching expiration without a bounce, either roll it forward (additional cost) or close the entire spread. Never leave the short put naked.

### Risk Management Specifics for TQQQ

- **Bid-ask spread impact:** TQQQ options have tight ATM spreads ($0.02–0.05) but wider spreads at OTM strikes. Budget 1–2% of position value for slippage on entry and exit.[^9]
- **Leverage drag awareness:** TQQQ's daily rebalancing means that in choppy markets, the underlying decays even if QQQ is flat. This works against the short put (it stays elevated longer) and for the long put (it retains value longer).[^47][^34]
- **Assignment risk:** Short TQQQ puts can be assigned early, especially deep ITM near ex-dividend dates. Monitor and roll before expiration.[^1]
- **Correlation breakdown:** In 2022, the QQQ-TLT negative correlation broke down. For hedging beyond the long put, consider VIX calls as catastrophic insurance rather than bond-based hedges.[^27]

### What Could Go Wrong

| Risk | Probability | Mitigation |
|------|-------------|------------|
| RSI-2 fires but TQQQ continues falling 20%+ | Medium (happened repeatedly in 2022) | 200 MA filter + VIX regime gate + hard stop at 10% adverse move |
| IV crush on bounce reduces spread profit | High | Accept as cost of structure; the short put's delta loss should dominate the vega headwind on a 5–10% bounce |
| Long put expires before bounce occurs | Medium | Roll forward if bounce thesis intact; close spread if regime filter turns negative |
| Flash crash / gap risk destroys spread | Low but catastrophic | Long put provides partial protection; position sizing is the ultimate defense |
| TQQQ options liquidity dries up during crisis | Low (TQQQ has 500K+ daily options volume) | Use limit orders; stick to $5-increment strikes with high open interest[^9] |

---

## References

1. [Long Put Diagonal Spread: A Flexible Bearish Strategy - EFI Markets](https://efimarkets.com/learn/option/long-put-diagonal-spread) - EFI Markets is a leading brokerage firm that offers a wide range of trading platforms. Access the gl...

2. [Diagonal Put Spread Options Strategy | Visualize + Live Data](https://www.insiderfinance.io/options-profit-calculator/strategy/diagonal-put-spread) - In a Diagonal Put Spread, the delta of the long put will typically be higher (in absolute value) tha...

3. [Diagonal Spread: How it Works & How to Use it | tastylive](https://www.tastylive.com/concepts-strategies/diagonal-spread) - Diagonal Spread Definition · What is a Diagonal Spread? · Diagonal Spread Strategy · Diagonal Spread...

4. [Understanding Diagonal Spreads: A Versatile Options Strategy](https://www.tradestation.com/learn/options-education-center/understanding-diagonal-spreads-a-versatile-options-strategy/) - For debit call diagonals, consider buying a longer-term option with a delta between 0.70 and 0.80 an...

5. [What is universally accepted the 'best DTE and DELTA'?](https://www.reddit.com/r/thetagang/comments/1fsx6qx/what_is_universally_accepted_the_best_dte_and/) - What is universally accepted the 'best DTE and DELTA'?

6. [Long Gamma vs Short Gamma: Beginner's Guide - TradingBlock](https://www.tradingblock.com/blog/long-gamma-vs-short-gamma) - Directional bearish trade with limited risk and lower cost than a straight put. Long-term bullish ex...

7. [Long Gamma vs Short Gamma Explained - projectoption](https://projectoption.com/learn/long-gamma-vs-short-gamma) - A long gamma position benefits from movement. This includes long calls, long puts, straddles, strang...

8. [10/2 Dte Diagonal With 55...](https://datadrivenoptions.com/backtest-diag/) - This post utilizes two sources to find optimal strikes and duration of a diagonal covered put- theor...

9. [TQQQ Options | ProShares UltraPro QQQ Options Chain, IV & Greeks](https://apexvol.com/options/tqqq) - Real-time options analytics with Greeks, volatility analysis, and strategy builder. Free AAPL demo a...

10. [How to hedge TQQQ with puts? - Reddit](https://www.reddit.com/r/TQQQ/comments/1dyigke/how_to_hedge_tqqq_with_puts/) - Buy 1 yr exp protective TQQQ puts at $5 increments (looking at the option chain, there is better vol...

11. [Diagonal Spread Strategy: Complete Guide with Examples](https://protraderdashboard.com/blog/diagonal-spread-strategy/) - Learn how diagonal spreads work in options trading. This guide covers call diagonals, put diagonals,...

12. [Diagonal Spreads: Combining Directional and Time-Based ...](https://pomegra.io/learn/options-derivatives/chapter_05_trading_time_calendar_and_diagonal_spreads/diagonal_spreads_combining_directional_and_time_based_strategies) - Explore the power and versatility of diagonal spreads, an advanced options strategy that merges the ...

13. [Day Trading Larry Connors RSI2 Mean-Reversion Strategies - MQL5](https://www.mql5.com/en/articles/17636) - Here are the backtest results for US500 (M30) from January 1, 2024, to March ... The RSI2 Pullback S...

14. [Backtest Results for Connors RSI2 Strategy : r/algotrading - Reddit](https://www.reddit.com/r/algotrading/comments/1fm5lfj/backtest_results_for_connors_rsi2_strategy/) - Indicators: The strategy uses 3 indicators: 5 day moving average. 200 day moving average. 2 period R...

15. [Using RSI(2) to Trade Leveraged ETFs - CXO Advisory](https://www.cxoadvisory.com/technical-trading/using-rsi2-to-trade-leveraged-etfs/) - RSI(2) strategies on SSO underperformed buy-and-hold (7.7% vs 11.6% CAGR for 5-70 variant; 4.9% vs 1...

16. [Backtest Results for Connors RSI2 Strategy | Trade2Win Forums](https://www.trade2win.com/threads/backtest-results-for-connors-rsi2-strategy.242688/) - Hello. I recently got into backtesting and have tested a few strategies with mixed results. I wanted...

17. [Bollinger Bands Explained: Trading Strategy, Formula, Calculation ...](https://blog.quantinsti.com/bollinger-bands/) - In this comprehensive guide, we delve into the intricacies of Bollinger Bands, exploring their formu...

18. [RSI Reversal Fibonacci Bollinger Bands Quantitative Strategy](https://www.fmz.com/lang/en/strategy/485283) - Overview The RSI Reversal Fibonacci Bollinger Bands Quantitative Strategy is a technical analysis tr...

19. [Inside Volatility Trading: Is VIX Backwardation Necessarily ...](https://www.cboe.com/insights/posts/inside-volatility-trading-is-vix-backwardation-necessarily-a-sign-of-a-future-down-market/) - Cboe Global Markets, a leading provider of market infrastructure and tradable products, delivers cut...

20. [Bear Market and VIX Pattern: How to Read Volatility Signals for ...](https://intellectia.ai/blog/bear-market-vix-pattern) - Learn how VIX volatility patterns signal bear market bottoms and tops. Discover key VIX thresholds, ...

21. [Exploiting Term Structure of VIX Futures - Quantpedia](https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures) - When the VIX futures curve is upward sloped (in contango), the VIX is expected to rise because it is...

22. [Mean Reversion And The VIX Basis Guide - MenthorQ](https://menthorq.com/guide/mean-reversion-and-the-vix-basis/) - This article explains how mean reversion regimes evolve by analyzing volatility structure, VIX basis...

23. [Volume Oscillator - Strategy, Rules, Returns](https://www.quantifiedstrategies.com/volume-oscillator/) - The volume oscillator is a volume indicator that shows the changes in trading volume by displaying t...

24. [Capitulation Scout — Indicator by OfficerDonut](https://www.tradingview.com/script/0r1eCUkL-Capitulation-Scout/) - Capitulation Scout - Description Overview The Capitulation Scout is a streamlined technical indicato...

25. [The Ultimate Guide to Moving Averages](https://enlightenedstocktrading.com/moving-averages/) - Above the 200-day moving average, the market is generally much less volatile and trends much more sm...

26. [Mean reversion swing trade back test results](https://www.reddit.com/r/TQQQ/comments/1iys1i3/mean_reversion_swing_trade_back_test_results/) - Mean reversion swing trade back test results

27. [Why Leveraged ETFs Like TQQQ Can Be Risky After a Major Market ...](https://www.ainvest.com/news/leveraged-etfs-tqqq-risky-major-market-rally-2508/) - Why Leveraged ETFs Like TQQQ Can Be Risky After a Major Market Rally

28. [Case Study: Timing the 2008 Bear Market Using the 200 Daily or 40 Week Moving Average](https://www.reddit.com/r/stocks/comments/xzt3jd/case_study_timing_the_2008_bear_market_using_the/)

29. [Using VIX to Determine Market Volatility Regime - finaur.com](https://finaur.com/blog/en/education/using-vix-volatility-regime/) - A step‑by‑step, educational walk‑through of how to use the CBOE Volatility Index (VIX) as a regime f...

30. [Quant Radio: Machine Learning based Mean Reversion Model](https://www.youtube.com/watch?v=FjYPL4be0K0) - ... mean reversion strategy that combines both long and short signals, enhanced by a volatility regi...

31. [I Built A Regime-Based Overnight Mean Reversion Model - 3M Results: 26% returns, 64% WR, Sharpe: 3.3](https://www.reddit.com/r/Daytrading/comments/1nytt8b/i_built_a_regimebased_overnight_mean_reversion/) - I Built A Regime-Based Overnight Mean Reversion Model - 3M Results: 26% returns, 64% WR, Sharpe: 3.3

32. [Built a Regime-Based Overnight Mean Reversion Model - 10.19.25, 3M Results: 24% returns, 64.7% WR, Sharpe Ratio 3.51](https://www.reddit.com/r/algotrading/comments/1ob5xao/built_a_regimebased_overnight_mean_reversion/) - Built a Regime-Based Overnight Mean Reversion Model - 10.19.25, 3M Results: 24% returns, 64.7% WR, S...

33. [3x Leveraged ETF Strategy: 2,600% Return With 38% Drawdown](https://setup4alpha.substack.com/p/leveraged-etf-strategy-tqqq-tmf-rebalancing-backtest) - How a simple 50/50 rebalancing system turned leveraged ETF risk into steady performance, tested acro...

34. [Compounding Effects in Leveraged ETFs: Beyond the Volatility Drag ...](https://arxiv.org/html/2504.20116v1) - In particular, momentum improves compounding, while mean reversion undermines it, with these effects...

35. [[2504.20116] Compounding Effects in Leveraged ETFs](https://arxiv.org/abs/2504.20116) - A common belief is that leveraged ETFs (LETFs) suffer long-term performance decay due to \emph{volat...

36. [Tqqq during bear markets?](https://www.reddit.com/r/investing/comments/1cpbqh2/tqqq_during_bear_markets/)

37. [Mean Reversion in Action: Building a Pairs Trading Strategy with the ...](https://llmquant.substack.com/p/mean-reversion-in-action-building) - How to implement, calibrate, and test a modern statistical arbitrage model

38. [Statistical Arbitrage in the U.S. Equities Market](https://math.nyu.edu/~avellane/AvellanedaLeeStatArb20090616.pdf)

39. [[PDF] Decomposing Short-Term Return Reversal - Federal Reserve Bank](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr513.pdf) - A standard short-term reversal strategy is a zero- investment strategy that each month sorts stocks ...

40. [[PDF] A Closer Look at the Short-Term Return Reversal - Academic Web](https://academicweb.nd.edu/~zda/Reversal.pdf) - Stock returns unexplained by “fundamentals,” such as cash flow news, are more likely to reverse in t...

41. [Short Term Reversal Effect in Stocks - QuantPedia](https://quantpedia.com/strategies/short-term-reversal-in-stocks) - The short-term reversal anomaly, the phenomenon that stocks with relatively low returns over the pas...

42. [[PDF] Liquidity Provision to Leveraged ETFs and Equity Options ...](https://wp.lancs.ac.uk/fofi2022/files/2022/08/FoFI-2022-027-Mathis-Moerke.pdf) - We show that they induce significant end-of-day momentum and mean-reversion in stock returns, while ...

43. [[PDF] Liquidity Provision to Leveraged ETFs and Equity Options ...](https://abarbon.com/assets/Liquidity_Provision_to_Rebalancing_Flows_from_Leveraged_ETFs_and_Equity_Options.pdf)

44. [Liquidity Provision to Leveraged ETFs and Equity Options Rebalancing Flows](https://abarbon.com/papers/liquidity-provision-to-leveraged-etfs-and-equity-options-rebalancing-flows)

45. [5.3 Real World Experiments](https://arxiv.org/html/2403.12180v1)

46. [Structuring Directional Option Trades - Party at the Moontower](https://moontowermeta.com/structuring-directional-option-trades/) - The nearer the option tenor, the more event pricing matters. The event's variance is a larger propor...

47. [Does anyone run regime-aware, tactical strategies with leveraged ETFs?](https://www.reddit.com/r/quant/comments/1mcezip/does_anyone_run_regimeaware_tactical_strategies/) - Does anyone run regime-aware, tactical strategies with leveraged ETFs?

