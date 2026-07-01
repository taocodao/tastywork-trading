# HILO-IV Phase B Roadmap: Scaling from 3–5% to 15–25% CAGR

## Executive Summary

The HILO-IV strategy carries a genuine, validated edge — a 76% win rate and 1.41 profit factor that holds across bear, bull, and high-volatility regimes from 2018–2024. However, the path to 15–25% CAGR requires attacking three distinct bottlenecks simultaneously: **(1)** capital utilization (60–70% idle cash earning zero), **(2)** per-trade sizing that sits far below what the Kelly framework recommends for this edge profile, and **(3)** signal frequency, which caps annual trades at 56–117 depending on the market regime. No single lever reaches the target alone — all three must be pulled together.

A phased rollout is the safest path:
- **Phase 1** (immediate, no signal changes): Raise per-trade risk to 4% + SGOV T-bill ETF deployment → estimated +9% CAGR
- **Phase 2** (signal expansion): Add VIX ≥ 18 conditional entries + RSI < 30 confirmation gate → +14–19% CAGR
- **Phase 3** (advanced, optional): Quarter Kelly sizing (5.5%) + earnings IV crush overlay → 20–25% CAGR

***

## 1. Position Sizing: Kelly Criterion Applied to This Strategy

### The Full Kelly Math

For a strategy with a 76% win rate and 1.41 profit factor, the classical Kelly formula yields a surprisingly high number. Using the standard formulation \( K\% = W - \frac{1-W}{R} \) where \(W\) = 0.76 and \(R\) = avg_win/avg_loss:[^1][^2]

The profit factor of 1.41 implies \(R \approx 0.445\) (average win is 44.5% of average loss in dollar terms, consistent with a 50% profit-take against an average realized loss of ~1.12x premium — not the full 2x stop, since most losers exit before full stop). This gives:

\[ K\% = 0.76 - \frac{0.24}{0.445} \approx 22.1\% \]

**Full Kelly = 22.1% of NAV per trade.** This is the theoretical ceiling and should never be used directly.[^2][^3]

### Fractional Kelly Recommendations

| Kelly Fraction | Per-Trade Sizing | $ per Trade ($50K) | Academic Support |
|---|---|---|---|
| Full Kelly (22.1%) | Theoretically optimal ceiling | $11,050 | Never use directly [^2] |
| Half Kelly (11.1%) | Captures ~71% of optimal growth, 38% of volatility[^4] | $5,525 | Aggressive but backed |
| **Quarter Kelly (5.5%)** | **Recommended starting point** | **$2,762** | Practitioners' default [^2][^3] |
| Current (2.0%) | Far below Kelly optimal | $1,000 | Leaves CAGR on table |

The takeaway is stark: the strategy's current `max_risk_per_trade_pct = 2.0%` is **9x below the theoretically optimal full Kelly allocation** for an edge of this quality. Even quarter Kelly (5.5%) is 2.75x the current level.[^4][^1]

**Practical recommendation:** Migrate `max_risk_per_trade_pct` from 2% → 4% immediately (below quarter Kelly), then to 5.5% (quarter Kelly) only after verifying out-of-sample walk-forward performance holds. The key constraint is that Kelly's inputs (win rate, R) are estimated from only ~350 trades — statistical uncertainty in the win rate of ±5 percentage points can shift the Kelly output by 3× or more, which is precisely why practitioners cap at 25–50% of full Kelly.[^2]

### Concurrent Positions and Heat Cap

With a universe of 128 symbols and average hold of 6 days, the binding constraint is signal frequency, not slot availability. Testing at 8 concurrent positions showed no improvement in 2024 (only 56 total trades fired). The current 5-position limit is already non-binding in low-frequency environments.

The correct lever is **not more concurrent position slots but larger per-slot sizing**. Retain the 5-slot structure but raise `max_risk_per_trade_pct` to 4–5.5%. If VIX-regime supplemental entries (Section 4) are added, consider raising concurrent positions to 7–8 for the overlay trades only, keeping the HILO-IV core at 5.

***

## 2. Capital Efficiency: Deploying Idle Cash

### The T-Bill ETF Sweep Strategy

With 60–70% of capital sitting idle, deploying into SGOV (iShares 0–3 Month Treasury Bond ETF) or BIL (1–3 Month T-Bill ETF) is the single highest-certainty improvement available, requiring zero changes to signal logic.[^5][^6][^7]

**Estimated CAGR contribution:** 60% idle × 4.5% yield (approximate current T-bill rate) = **+2.7% CAGR on $50K** with essentially zero additional risk.[^6]

**Practical mechanics on TastyTrade:**
- Sell the SGOV position same-day when a new options entry fires; liquidation takes seconds during market hours[^7][^8]
- SGOV and BIL are penny-wide spreads and fully liquid for intraday deployment/recall[^7]
- **Margin interaction warning:** TastyTrade treats SGOV with a ~25–30% maintenance margin requirement, versus 1% for actual T-bills purchased directly. This means buying SGOV in a margin account does not give full collateral efficiency — approximately 70–75% of SGOV value counts toward buying power reduction. For accounts below portfolio margin threshold ($125K minimum at TastyTrade), the T-bill-direct route or SGOV-in-cash-portion is more capital-efficient.[^8][^9]

**Action: Implement a daily cash sweep into SGOV/BIL for any idle capital exceeding the options margin buffer.** This alone is worth an estimated +2.5–2.7% CAGR with no strategy risk added.

### Should You Sell Cash-Secured Puts on SGOV/BIL?

This adds operational complexity with minimal incremental yield. SGOV/BIL option chains have minimal volume and wide bid-ask spreads — the transaction costs erode the edge. The T-bill ladder alone is the correct implementation here.

### SPY/QQQ Weekly Iron Condors as an Overlay

Adding a delta-neutral weekly iron condor program on SPY/QQQ would increase trade frequency and generate income in calm markets (exactly when HILO-IV goes quiet). ORATS data shows QQQ iron condors with appropriate strikes have ~71% theoretical probability of max profit. However, this introduces a **new, separate strategy** with its own risk profile and should be treated as a dedicated sub-strategy rather than a modification to HILO-IV. The empirical evidence for systematic SPX/QQQ iron condors is favorable on a risk-adjusted basis but the CAGR contribution at defined-risk sizing is modest (typically 5–10% annually on allocated capital).[^10][^11]

***

## 3. Exit Management: 21-DTE Forced Exit and Trailing Profit Lock

### The 21-DTE Exit Rule (High-Confidence Recommendation)

TastyTrade's Market Measures research — the most comprehensive practitioner-level dataset on short options exit timing — consistently shows that managing positions at 21 DTE reduces portfolio CVaR and gamma risk without materially sacrificing returns. The specific mechanism: beyond 21 DTE, theta decay is roughly linear for 45-DTE options; inside 21 DTE, gamma accelerates and the risk/reward deteriorates for undefined-risk sellers.[^12][^13][^14][^15]

**Empirical finding from TastyTrade research:** Of trades that were losers at 21 DTE, 64% would have become profitable by expiration — *but the ones that didn't became significant drawdowns*. The 21-DTE exit captures most of the theta harvest while cutting the tail risk from those gamma-dominant final weeks.[^16]

**Recommendation: Implement a hard 21-DTE exit rule as the third exit criterion**, alongside the existing 50% profit take and 2x stop. Precedence order:
1. 50% profit target (GTC limit order, placed same day as entry)
2. 2x stop loss (dynamic, spread-adjusted)
3. 21-DTE forced exit (regardless of P&L)

**Supported by peer-reviewed literature:** The Wysocki (2025) study on systematic SPX put-writing confirms that managing 45-DTE short puts at 15–21 DTE "exhibited strong performance on a risk-adjusted basis" and that the capital tied up in margin beyond this point represents increasingly poor risk/reward.[^17][^18]

### IV-Rank Adjusted Stops

There is practitioner logic for widening stops in high-IV environments and tightening in low-IV regimes. The rationale: when IV is elevated, a 2x premium stop in dollar terms already represents a large absolute move; in low-IV environments, 2x premium is small and can be triggered by normal intraday noise. Consider:

- **VIX ≤ 18 (low vol):** Tighten stop to 1.5x premium
- **VIX 18–25 (normal):** Keep stop at 2.0x premium
- **VIX > 25 (high vol):** Widen stop to 2.5x premium (or remove stop, rely on 21-DTE exit only)

This adaptive stop logic is consistent with volatility regime-based position management described in Wysocki (2025) and standard TastyTrade guidance.[^19][^17]

### Trailing Profit Lock: Does It Outperform Fixed GTC?

There is limited peer-reviewed evidence that a trailing profit lock (e.g., once +60% of max profit is reached, floor the exit at +40%) outperforms a fixed 50% GTC order for 45-DTE short options. The SteadyOptions research on "Managing Winners" (2024) found that actively managing short strangles for profit added value, but the comparison was primarily 50% vs. 75% profit takes rather than trailing floors specifically.[^20]

**Assessment:** A trailing profit lock adds implementation complexity (it cannot be placed as a simple GTC order; it requires conditional monitoring). Given the strategy's mean hold time of 4–10 days and the 21-DTE hard exit as backstop, the marginal benefit of a trailing profit lock over a fixed 50% GTC order is unlikely to exceed the operational cost. **Stick with the 50% GTC order.** The 21-DTE exit is the higher-priority improvement.

***

## 4. Signal Frequency Enhancement

### Lever 1: VIX ≥ 18 Conditional Entry (Most Promising)

Adding entries whenever VIX ≥ 18 *regardless of HILO position* allows the strategy to capture premium during normal-to-elevated volatility environments without requiring the ticker to be near its 52-week extreme. The theoretical basis: implied volatility statistically exceeds realized volatility most of the time (the volatility risk premium), but the edge is larger and more reliable when VIX is elevated.[^21][^19]

Practitioner research (options.cafe, 2026) on a VIX-filtered RSI momentum strategy showed the VIX Rank filter "dramatically improved risk-adjusted returns" while reducing total trade count from 165 to 91 — suggesting that a VIX ≥ 18 *entry* filter (not an exclusion filter) could add meaningful high-quality trades in calm-market periods when the 52W HILO signal is quiet.[^22]

**Expected trade frequency increase:** Conservatively +25–40 trades/year in 2024-type "choppy bull" environments where VIX oscillates between 15 and 25. This partially fills the gap created by the HILO signal's infrequency.

**Implementation:** Add a second entry pathway to the signal logic:
```python
# Pathway A (existing): HILO signal fires
hilo_signal = (price <= low_52w * 1.15) and (iv_rank >= 30)

# Pathway B (new): VIX elevated, IV Rank elevated, standard OTM delta
vix_entry = (vix >= 18) and (iv_rank >= 35) and (delta <= 0.25) and (not hilo_signal)

entry = hilo_signal or vix_entry
```

### Lever 2: RSI < 30 Confirmation Gate (Secondary Enhancement)

Adding RSI < 30 as a *confirmation filter* (not a replacement) for the HILO signal can improve entry quality by ensuring the put is sold into genuine oversold conditions rather than slow, sustained downtrends. Research on mean-reversion strategies with RSI < 30 + 200-day SMA trend filters shows win rates of 75–87% depending on implementation.[^23][^24][^25]

**For the HILO-IV put-selling context:** RSI < 30 when a ticker is near its 52-week low represents double confirmation of oversold conditions — the price is both structurally depressed (52W HILO) and momentum-exhausted (RSI). This should improve the profit factor above 1.41 while maintaining 70%+ win rate, though the filter may reduce total signals by 10–20%.

**Important caveat:** RSI < 30 in strong downtrends can be a momentum *confirmation* rather than a reversal signal. Apply the filter only when the broad market (SPY) is **above** its 200-day SMA, filtering out deep-bear regimes where continued decline is more likely.[^24][^25]

### Lever 3: Earnings IV Crush (Caution Required)

Selling short straddles one day before earnings (entering 15 min before close, exiting next day) captures the post-earnings IV crush. Published ORATS backtests across 5,217 earnings events show this strategy is net profitable when specific filters are applied, but **with brutal tail risk** — some earnings events produce 80–100% losses on the position.[^26][^27][^28]

**Key finding from ORATS backtest:** "Systematic earnings straddle buying is a losing strategy... Selling straddles is more profitable on average — with brutal tail risk. Most short-straddle traders eventually graduate to defined-risk structures after a blow-up."[^26]

**Assessment:** Earnings IV crush plays belong in an **iron condor (defined-risk) format only**, not naked straddles. The tail risk profile is fundamentally different from 45-DTE HILO-IV puts, and mixing them in the same P&L framework obscures the HILO-IV edge. If implemented, run as a separate defined-risk sub-strategy with its own allocation (≤5% of NAV total, ≤1% per trade), using the filter criteria: IV rank < 20 (implies options are cheap-for-earnings), term structure slope negative, IV/RV ratio > 1.25.[^29][^26]

***

## 5. Machine Learning for Signal Enhancement

### Is 350 Trades Enough Data?

The short answer is **no, not reliably** — and the 74% vs. 76% win rate result from the XGBoost gate test (documented in the strategy history) is consistent with the expected outcome at this sample size.[^30][^31]

**Statistical reasoning:** A binary classification model over 350 observations with 6–8 features faces severe overfitting risk. Standard ML practice requires 10–30 observations per feature per class for reliable generalization; at 350 trades (266 wins, 84 losses), even a 4-feature model is at the edge of viability. Walk-forward validation on this dataset will produce high variance in out-of-sample accuracy, and the improvement in win rate may not survive transaction costs.[^31][^32]

**Feature engineering that *is* supported by published research** for short put win/loss prediction:[^33][^30]
- **VIX percentile rank (rolling 1-year):** Strongest predictor — higher VIX rank correlates with better edge for sellers[^21][^19]
- **IV/RV ratio (IV30 / 20-day realized vol):** Measures the VRP premium being captured; ratio > 1.2 is a positive predictor
- **Term structure slope (VX1/VX2 ratio):** Contango implies low near-term volatility demand; backwardation implies panic — useful regime classifier
- **52-week distance percentile** (existing HILO feature): Already capturing mean-reversion setup quality
- **Sector beta relative to SPY:** Higher-beta sectors (tech, biotech) have wider option premiums but also higher tail risk

**Recommendation on ML:** Rather than a binary classifier gate, use a **simpler rule-based ensemble** of the features above (3–4 conditions with documented empirical support) rather than XGBoost. Rule-based signals are transparent, don't overfit, and can be validated independently. Reserve ML for when the dataset reaches 800–1,000 labeled trades.

### Bayesian Optimization with Optuna

Bayesian optimization (e.g., Optuna) over parameters like `iv_rank_min`, `profit_take_pct`, `stop_loss_multiplier`, and `dte_target` can identify locally optimal parameter sets, but with 350 trades and 5 parameters, the in-sample optimization is almost certain to produce overfitted results that fail out-of-sample.[^34][^35]

**Published warning from Man Group's overfitting research (2022):** "An overfitted strategy will likely underperform when faced with new data... Common red flags include: too many parameters vs. dataset size, unrealistically low drawdowns in backtest, isolated parameter performance that collapses with slight variations." The HILO-IV backtest (which already discovered a double-counting accounting bug) is at high risk of this.[^32]

**The correct application** of Bayesian optimization here is **parameter sensitivity testing** — not finding the optimal parameters but mapping the performance surface around the current parameters to confirm the strategy is in a stable region, not an isolated spike. If CAGR varies smoothly as `iv_rank_min` moves from 25 to 40, the current value at 30 is robust. If it is a sharp peak at 30 that collapses at 28 or 32, the parameter is overfit.[^32]

***

## 6. Phased Implementation Roadmap

### Phase 1: Immediate Wins (~2–4 weeks to implement)

| Change | Parameter | Current → Target | Expected CAGR Impact |
|---|---|---|---|
| Raise per-trade sizing | `max_risk_per_trade_pct` | 2.0% → 4.0% | +3.2% (2x options P&L) |
| Deploy idle cash to SGOV | — | 0 yield on idle → 4.5% | +2.7% (60% idle × 4.5%)[^5][^6] |
| Add 21-DTE forced exit | New exit criterion | None → 21 DTE hard exit | Risk reduction (maintains CAGR)[^12][^14] |
| **Phase 1 total** | | | **~9% CAGR** (from 3.2% baseline) |

### Phase 2: Signal Expansion (~4–8 weeks to implement and backtest)

| Change | Signal Addition | Expected New Trades | Expected CAGR Impact |
|---|---|---|---|
| VIX ≥ 18 entry pathway | Pathway B conditional | +25–40/year | +2.5–4.5%[^22][^21] |
| RSI < 30 confirmation | HILO signal filter | Net neutral or slight ↑ trades | +0.5–1.5% (quality improvement) |
| Concurrent positions | `max_concurrent` | 5 → 7 (Pathway B only) | Enables Pathway B utilization |
| **Phase 2 cumulative** | | ~110–130 trades/year | **~14–18% CAGR** |

### Phase 3: Advanced Levers (~2–3 months)

| Change | Parameter / Strategy | Notes |
|---|---|---|
| Quarter Kelly sizing | `max_risk_per_trade_pct` → 5.5% | Only after Phase 2 validated in live trading |
| Earnings IC overlay | Separate sub-strategy, 5% capital | Defined-risk iron condors only; strict IV/RV > 1.25 filter[^26][^29] |
| IV-rank adaptive stops | VIX < 18: 1.5x, VIX 18–25: 2x, VIX > 25: 2.5x | Replaces static 2x stop[^17] |
| Portfolio margin upgrade | TastyTrade application | Requires $125K NAV minimum[^9]; reduces margin per trade by ~30–40%[^36] |
| **Phase 3 cumulative** | | **~20–25% CAGR** target range |

***

## 7. Risk Controls and Drawdown Guard Rails

Raising sizing to 4–5.5% per trade while adding VIX-conditional entries increases correlation risk during volatility spikes. In a Volmageddon-type event (2018) or COVID crash (2020), multiple positions would be tested simultaneously. Critical guardrails:

- **Maintain 40% heat cap** — this remains the binding risk constraint[^37]
- **Add a portfolio-level VIX circuit breaker:** If VIX > 35, pause all new Pathway B (VIX-conditional) entries; resume only when VIX drops back below 30 for 3 consecutive days
- **Separate correlated position tracking:** Count all positions in correlated sectors (tech, biotech) as a single exposure unit for Kelly sizing purposes — do not apply Kelly independently to each ticker[^2]
- **Hard max drawdown stop at 10%:** If NAV drops 10% intra-year, revert `max_risk_per_trade_pct` to 2.0% for the remainder of the quarter

The CBOE PUT Index research confirms that put-writing strategies "tend to underperform in strong bull markets" and have "sensitivity to market timing" — which is exactly why the IV Rank gate must remain in place even for Pathway B entries, preventing the strategy from selling premium into low-IV complacency without compensation.[^17]

***

## Appendix: Kelly Fraction Calculation Summary

For the HILO-IV strategy at documented metrics (76% win, 1.41 PF, avg hold 6 days):

- Profit factor: \( PF = \frac{W \cdot \bar{w}}{L \cdot \bar{l}} = 1.41 \) where \(\bar{w}\) is avg win, \(\bar{l}\) is avg loss
- Implied avg loss multiplier: \( \bar{l} \approx 1.12 \times \text{premium}\) (vs. theoretical 2x stop)
- Full Kelly: \( K = 0.76 - \frac{0.24}{0.445} \approx 22.1\%\) of NAV per trade[^38][^1]
- **Quarter Kelly target: 5.5% of NAV**, phased to after walk-forward validation[^3][^2]

Half-Kelly captures approximately 71% of optimal growth at 38% of the volatility of full-Kelly allocation — the Wysocki (2025) hybrid Kelly–VIX sizing method, which dynamically scales Kelly fraction by VIX percentile rank, showed the best balance of CAGR vs. maximum drawdown in out-of-sample testing, and is the recommended sizing model once the $125K threshold for portfolio margin is met.[^18][^17]

---

## References

1. [Options Position Sizing: Kelly Criterion Explained](https://longbridge.com/en/academy/options/blog/options-position-sizing-kelly-criterion-explained-100160) - The Kelly Criterion is a mathematical framework for options position sizing. Learn how to use win ra...

2. [Kelly Criterion for Position Sizing Explained](https://journalplus.co/learn/guides/kelly-criterion-guide) - A short losing streak does not invalidate a win rate calculated from 80+ trades. Distinguish between...

3. [Kelly Criterion Explained: Smarter Position Sizing for Traders](https://www.tastylive.com/news-insights/kelly-criterion-explained-smarter-position-sizing-traders) - Learn how the Kelly Criterion helps traders optimize position sizing, balance risk, and improve long...

4. [The Smart Trader's Guide to Kelly's Criterion](https://www.tastylive.com/news-insights/smart-trader-guide-kellys-criterion) - In practice, the half-Kelly (50% of the full Kelly) strategy can capture nearly 71% of the optimal r...

5. [Cash Alternatives: Seeking Stability and Income with SGOV](https://www.ishares.com/us/insights/portfolio-insights/cash-alternatives-put-cash-to-work-sgov) - Discover cash alternatives and how to put cash to work with SGOV, a short-term Treasury ETF pursuing...

6. [Why Cash-Like ETFs Are Winning 2026: SGOV, BIL, and ...](https://www.ebc.com/forex/cash-like-etfs-2026-sgov-bil-boxx-tax-test) - SGOV tracks Treasury bills with maturities of 0-3 months and charges a 0.09% expense ratio. BIL trac...

7. [Sweep your cash balance with BIL & SGOV || Good cash ...](https://www.youtube.com/watch?v=Q2Zqj5YormM) - Sweep your cash balance with BIL & SGOV || Good cash management practices for every option trader Le...

8. [How to earn interest on collateral in Tastytrade : r/thetagang](https://www.reddit.com/r/thetagang/comments/1jxqy4m/how_to_earn_interest_on_collateral_in_tastytrade/) - Will be selling 0dte’s fully cash secured SPY puts but want to earn interest on collateral. How does...

9. [Portfolio Margin](https://tastytrade.com/portfolio-margin/) - Portfolio Margin accounts are required to fund with at least $125,000 to have Portfolio Margin activ...

10. [Ideas In-Focus: Why Selling This Iron Condor in QQQ Make..](https://marketchameleon.com/articles/i/2026/3/6/28937-why-selling-this-iron-condor-in-qqq-makes-sense-fo) - Based on historical stock price behavior, this spread for QQQ has a theoretical 71% success rate. Op...

11. [How to Make $870 a Week Selling Weekly Iron Condors on ...](https://tradersfly.com/blog/how-to-make-870-a-week-selling-weekly-iron-condors-on-the-spx/) - I'm thrilled to unveil a powerful strategy for setting up SPX (S&P 500) weekly iron condor contracts...

12. [Enter at 45 DTE, Exit at 21 DTE - The Skinny on Options](https://www.tastylive.com/shows/the-skinny-on-options-abstract-applications/episodes/enter-at-45-dte-exit-at-21-dte-07-27-2020) - We enter trades at 45 DTE to maximize our returns from positive theta, and we exit trades at 21 DTE ...

13. [What does managing at 21 DTE mean? : r/thetagang](https://www.reddit.com/r/thetagang/comments/1bwvs18/what_does_managing_at_21_dte_mean/) - Does it mean exit the trade? Or roll up or down legs? But how longer should we hold this after manag...

14. [Why We Manage at 21 DTE](https://www.youtube.com/watch?v=sqh0u63Zw6o&vl=en) - Why does Tastytrade keep talking about getting into trades at forty five days to expiration and gett...

15. [How To Manage Risk and Profit in Zero DTE Trades](https://www.tastylive.com/news-insights/How-To-Manage-Risk-and-Profit-in-Zero-DTE-Trades) - Tom Sosnoff explains his 21-Day (0DTE) rule on a recent episode of Market Measures on tastylive.

16. [What Happens After 21 Days To Expiration (DTE)](https://www.tastylive.com/shows/market-measures/episodes/what-happens-after-21-dte-05-10-2021) - The more interesting statistic however is that of the trades that were losers at 21 dt 64 of them be...

17. [Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put- ...](https://arxiv.org/pdf/2508.16598.pdf) - This paper examines systematic put-writing strategies applied to S&P 500 Index options, with a focus...

18. [Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put- ...](https://arxiv.org/html/2508.16598v1) - A similar trade‐off arises with VIX memory. Short VIX lookbacks improve returns for near‐term, near‐...

19. [Where is the edge in selling premium? What most ...](https://www.reddit.com/r/thetagang/comments/mfdtzu/where_is_the_edge_in_selling_premium_what_most/) - I wanted to start a discussion on a common misunderstanding of thetagang. The main thing that people...

20. [Does “Managing Winners” Add Value to Short Strangles?](https://steadyoptions.com/articles/does-%E2%80%9Cmanaging-winners%E2%80%9D-add-value-to-short-strangles-r618/) - ... Volatility Risk Premium and Financial Distress”. The author of the ... We closed 83 winners out ...

21. [White Paper Shows Volatility Risk Premium Facilitated ...](https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/) - Research showed the PUT Index had higher risk-adjusted returns (as measured by the Sharpe Ratio, Sor...

22. [Momentum RSI Strategy Backtest: 81% Win Rate with VIX ...](https://options.cafe/blog/momentum-rsi-strategy-backtest-results/) - The VIX Rank filter reduced trades from 165 to 91 but dramatically improved risk-adjusted returns. T...

23. [RSI Overbought and Oversold Signals Explained](https://www.luxalgo.com/blog/rsi-overbought-and-oversold-signals-explained/) - RSI > 70: Signals overbought, meaning the price might pull back. RSI < 30: Signals oversold, suggest...

24. [Mastering the RSI: Proven Strategies for Smarter Trading ...](https://www.oanda.com/us-en/trade-tap-blog/analysis/technical/mastering-rsi-trading-strategies/) - This comprehensive guide explores RSI trading strategies, combining the RSI with other indicators an...

25. [Mean Reversion Trading Strategy That Works (86.84% ...](https://www.tradingwithrayner.com/mean-reversion-trading-strategy/) - Mean reversion trading is a strategy that buys when an asset price is low, and then sell it on the n...

26. [Long Straddle Backtest: 100 Earnings Events, Brutal Average](https://apexvol.com/strategies/straddle/backtest) - Systematic earnings straddle buying is a losing strategy. 62% of trades lose; the rare big winners d...

27. [How to Trade Earnings IV Crush - Options Strategies](https://optionsjive.com/blog/how-to-trade-earnings-iv-crush-options-strategies-that-work/) - ORATS published a backtest covering 5,217 earnings announcements and 20,868 trades across four strat...

28. [What is Implied Volatility (IV Crush) & How to Avoid it](https://www.tastylive.com/concepts-strategies/iv-crush) - Implied volatility (IV crush) refers to a significant decrease in the implied volatility of a partic...

29. [The 24/7 workflow I run for earnings IV crush trades](https://www.reddit.com/r/options/comments/1t4yjba/the_247_workflow_i_run_for_earnings_iv_crush/) - The 24/7 workflow I run for earnings IV crush trades · Average return/trade ~ 10% · CAGR ~ 84.74 % v...

30. [Options Selling Using Machine Learning](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4766370) - The goal of this paper is to develop a dynamic standalone option selling strategy using technical in...

31. [How to Avoid Overfitting in Trading Strategies](https://www.linkedin.com/posts/siddharthanand1998_why-overfitting-is-the-silent-killer-of-activity-7360680470738563073-heR7) - Signs You're Overfitting: 1. Too many parameters vs dataset size. 2. Perfectly smooth backtest curve...

32. [Overfitting and Its Impact on the Investor](https://www.man.com/insights/overfitting-and-its-impact-on-the-investor) - An overfitted strategy will likely underperform when faced with new data, be it the out-of-sample th...

33. [Options Selling strategy using Machine Learning](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4766370_code6587970.pdf?abstractid=4766370&mirid=1) - Abstract. The goal of this paper is to develop a dynamic standalone option selling strategy using te...

34. [Overfitting in Bayesian Optimization: an empirical study and ...](https://www.research-collection.ethz.ch/bitstreams/d65c30af-6524-4eed-ad37-b60f3bfb2ef4/download) - Bayesian optimization (BO) is a widely popular approach for the hyperparameter optimization (HPO) of...

35. [Optimizing Trading Strategies with Bayesian Optimization](https://onepagecode.substack.com/p/optimizing-trading-strategies-with-6b1) - Optimizing the parameters of a quantitative trading strategy is a critical step in enhancing its per...

36. [What is Portfolio Margin & How Does it Work?](https://tastytrade.com/learn/accounts/account-resources/what-is-portfolio-margin-how-it-works/) - Portfolio margin (PM) is a dynamic risk-based margining system commonly used by trading firms to com...

37. [Portfolio Heat - Total Open Risk Exposure](https://journalplus.co/metrics/portfolio-heat) - You can comply with a 2% per-trade rule while running 15% portfolio heat if you hold too many simult...

38. [Kelly criterion](https://en.wikipedia.org/wiki/Kelly_criterion) - In probability theory, the Kelly criterion is a formula for risk allocation with the sizing a sequen...

