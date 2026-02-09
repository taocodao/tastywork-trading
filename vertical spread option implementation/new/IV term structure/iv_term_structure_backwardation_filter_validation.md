## Direct validation results

The specific “40–60% fewer losing trades” claim cannot be validated from credible academic or institutional sources found in the research set, and no study was located that reports that magnitude for **equity/ETF diagonal spreads** with a clear sample size and methodology.[^115][^145]  
What *can* be supported is a narrower statement: **term-structure-aware entry filters are directionally helpful for calendar/diagonal-type trades**, but the magnitude is strategy- and implementation-dependent, and in equities backwardation is **rare and regime-linked**, so an `IV_Skew > 0` hard filter is likely to be too restrictive and may select the worst underlying regime (stress). The evidence base below separates what is strongly supported vs. what is not.

---

## Claim 1: “Backwardation-only reduces losers by 40–60%”

### Evidence FOR (directional, not the %)
- ORATS explicitly frames “negative contango” (their term-structure slope measure) as favorable for **buying calendars** because the trader sells the relatively expensive near-term IV and buys the relatively cheaper back-month IV.[^115]  
- ORATS published a backtest example for a **SPY long call calendar** where restricting entries to contango ≤ 0 (i.e., backwardation/negative contango) increased annual return from -0.09% to 0.58% and reduced time-in-market to 66% (their methodology and contango definition is specified as slope of a 45-day IV term structure). This supports “filtering by term-structure shape can improve outcomes,” but it does not quantify “40–60% fewer losers,” and it is for a **calendar** example, not a diagonal PMCC implementation.[^115]  
- The NY Fed staff report on option-implied term structures notes that “in most periods … the volatility term structure appears upward sloping,” with short-run peaks above long-run volatility when mean reversion is priced in, supporting the idea that **inversions are episodic** and tied to near-term risk.[^113]

### Evidence AGAINST / what could not be validated
- No peer-reviewed paper or primary practitioner study located in this research set reports “losers reduced by 40–60%” specifically for **diagonal spreads** or even calendars using a clean contango/backwardation split with that outcome metric.[^145][^127]  
- The closest academic work found (e.g., “The term structure of equity option implied volatility” draft) demonstrates that IV term-structure slope has predictive content for **future option returns** (e.g., straddles), but that’s not a calendar/diagonal P&L decomposition and does not produce a “40–60% fewer losers” figure.[^145]

### Practical takeaway
Treat “40–60% fewer losers” as **unsubstantiated marketing-level magnitude**. Treat “term structure matters and can be used as a filter” as supported.[^115][^145]

---

## Claim 2: “Calendars/diagonals profit from IV differential collapsing”

### Mechanism (supported)
- Calendar/diagonal spreads are structurally **long vega** (more vega in the longer-dated option) and **short theta** on the long leg but offset by higher theta harvested on the short-dated leg; therefore P&L is strongly driven by the *relative* movement in IV across maturities, not simply “IV up/down.”[^185][^135]  
- If the near-term IV is elevated relative to the back month (inversion/backwardation), selling the front month and buying the back month creates a positive “carry” on the IV differential if the curve normalizes (front-month IV falls relative to back-month IV). This is exactly the intuition ORATS describes when motivating negative contango as favorable for calendar entries.[^115]

### Caveat (critical)
- In equities, backwardation typically occurs during **near-term stress / event risk** (macro shocks, crashes, etc.), not during calm regimes.[^112][^144]  
- During those stress regimes, **realized volatility and jump risk** are high; the underlying can move far from the strike and destroy calendar/diagonal P&L even if the curve later “collapses.” In other words, “IV differential collapsing” is not a guaranteed or dominant profit driver unless **spot/realized path risk** is controlled.[^113][^25]

### Bottom line on Claim 2
Yes, curve normalization can be a source of edge, but it is **not reliable in isolation** in equity index ETFs because the same conditions that create backwardation also create adverse gamma/spot risk.[^112][^113]

---

## Quantitative answers (with a transparent proxy)

### Important limitation
Free/open web sources rarely provide a downloadable, survivorship-clean, daily history of **SPY/QQQ/IWM ATM IV at specific maturities** (e.g., 10 DTE vs 45 DTE) suitable for direct term-structure regime classification at scale. To provide real numbers without fabricating, the analysis below uses an established **equity index options term-structure proxy**: **VIX (30-day) vs VXV (3-month / 93-day)**, both derived from SPX options and available as daily time series via FRED.[^148][^169]  
This is not identical to “7–14 DTE vs 45–60 DTE” on SPY/QQQ, but it is directionally informative about **equity index option term-structure regimes**.[^160]

### 1) Historical frequency (proxy: VIX – VXV)
Using daily closes from **2007-12-04 through 2026-02-05** (4572 observations), and defining:
- Backwardation: VIX − VXV > +0.5 vol points
- Contango: VIX − VXV < −0.5 vol points
- Flat: otherwise

Results:
- **Contango:** 85.13% of days
- **Backwardation:** 7.13% of days
- **Flat:** 7.74% of days

This supports the qualitative observation that equity index vol term structure is “upward sloping in most periods,” with inversions being relatively rare.[^113]



### 2) Duration / persistence of regimes (proxy)
Run-length statistics for the same series:
- Backwardation runs: median 1 day, mean 3.98 days, max 62 days
- Contango runs: median 6 days, mean 23.73 days, max 277 days
- Flat runs: median 1 day, mean 1.77 days, max 9 days

This shows that backwardation is not only **infrequent** but tends to be **short-lived**, consistent with it being tied to near-term event/stress bursts.[^112][^113]



### 3) “Flat vs contango vs backwardation” for SPY/QQQ specifically
A direct answer for SPY/QQQ **ATM chain IV at fixed DTE buckets** requires paid datasets (see Data Sources section) or a broker/OPRA feed plus historical storage; the research set did not contain an authoritative free dataset that could be programmatically pulled for those exact term points without paywalls. Therefore the only defensible quantitative frequency provided here is the SPX-options-derived VIX/VXV proxy.[^148][^169]

---

## Optimal threshold: is `IV_Skew > 0` or `> 0.02` good?

### Why “> 0” is usually too naive
- Backwardation in equity indices is frequently a **stress indicator**, so a hard `> 0` filter tends to select high-variance regimes.[^112][^144]  
- If using your definition `IV_Skew = front_month_IV - back_month_IV`, a positive number may be dominated by **event premia** (FOMC, CPI) that can persist into your short expiration, and the short leg can expand in IV *more* than the long leg before it collapses.[^137][^144]

### Practical starting thresholds (recommendations)
Because the best threshold depends on the *distribution* of skew for each underlying, the most defensible approach is **normalization**:

1. **Use vol points, not percent**: thresholds like **+0.5, +1.0, +2.0 vol points** are interpretable and align with how index vol indices are quoted.[^113][^160]  
2. **Percentile threshold per underlying**: compute a rolling 1–3 year percentile of `IV_Skew` and trade only when `IV_Skew` is in (say) the **top 20%** (strong backwardation) *or* the **bottom 20%** (steep contango), depending on whether you’re trading *long* or *short* calendar structures.[^115][^145]
3. **Regime-conditioned threshold**: use VIX level (or ETF IV rank) as a regime switch; in low-vol regimes, require only mild skew (e.g., +0.5 vol pts) whereas in high-vol regimes require larger skew but also stronger spot-risk controls.[^127][^112]

### Is “2%” a good starting point?
A 2% absolute IV difference (e.g., 0.20 vs 0.22) is **0.02 in IV**, which equals **2 vol points** (in the common “20 vol” style). That is a *strong* inversion for equity indices and will be rare (the VIX–VXV 95th percentile of diff is ~+1.19 vol points in this proxy sample; the max is much larger during crises).  
So “> 0.02” is likely too strict for continuous deployment; it may be more appropriate as a “crisis-mode” filter or a signal that you should trade a different structure (e.g., **short calendar / long front vol**) depending on your thesis.[^183][^184]



---

## Win-rate differential (backwardation vs contango) for calendars/diagonals

### What the research supports
- ORATS provides evidence that term-structure filtering (“contango max=0”) improved an example SPY long calendar’s annual return versus unfiltered. However, ORATS does not (in the cited excerpt) provide a full confusion-matrix style win-rate split for backwardation vs contango entries, nor does it claim a 40–60% reduction in losers.[^115]  
- Tastylive has studies on calendar spreads under low IV rank, and frames calendars as a long-vol strategy with “mid-forties” probability of success and typical small profit targets; however, the cited materials do not provide a term-structure regime split.[^127][^135]

### What is missing (and how to get it)
A clean quantitative answer for “win rate and P&L difference for diagonals entered in backwardation vs contango” needs a full historical options surface dataset (OptionMetrics/LiveVol/IVolatility/ORATS API) and a defined trading protocol (strikes, deltas, management rules, slippage). This is not available from free public sources in a reproducible way in the research set.[^131][^115]

---

## Evidence FOR using term structure as a filter

- Equity index option term structure is **usually upward sloping**, with **inversions episodic**, aligning with the intuition that “inversions reflect near-term risk that often mean reverts.”[^113][^112]  
- Practitioner backtests (ORATS) show that using a term-structure slope filter can improve outcomes for a calendar strategy example, supporting the general usefulness of the filter concept.[^115]  
- Academic work indicates the IV term-structure slope contains predictive information for future option returns (not calendars directly, but supports “term structure is informative, not noise”).[^145]

## Evidence AGAINST / caveats

- Backwardation in equities is commonly a stress/event indicator, so a naive `IV_Skew > 0` filter can become a **“trade only in crises”** rule, with poor scalability and potentially worse risk-adjusted outcomes if spot risk dominates.[^112][^144]  
- A diagonal PMCC is not a pure calendar: it carries meaningful **delta** exposure and the long leg is deep ITM with different vega/IV behavior than ATM measures, so an ATM term-structure filter may be directionally helpful but not sufficient.[^25][^32]  
- “IV differential collapsing” can be overwhelmed by adverse underlying movement; term structure is not a substitute for robust spot-risk controls (delta bands, trend filters, stop/roll rules).[^135][^184]

---

## Recommended implementation approach (practical, evidence-aligned)

### Replace hard backwardation with a **scored filter**
Instead of `enter only if IV_Skew > 0`, use:

- `skew_z = (IV_Skew - rolling_mean) / rolling_std` per underlying
- `enter if skew_z > +0.5` (mild) or `> +1.0` (strict), but only when **spot risk filter** agrees

This captures “sell relatively rich front vol” without restricting to rare crisis inversions.[^113][^145]

### Add complementary filters that matter more than slope alone
- **Event filter**: avoid entering with a major scheduled macro event inside the short leg unless intentionally trading that event premium (FOMC/CPI/NFP). Evidence shows backwardation spikes are often tied to macro dates.[^137][^144]  
- **Realized vol forecast vs IV**: ORATS emphasizes HV forecasts and statistical significance over long backtests; the calendar/diagonal edge improves when the IV you pay is cheap relative to expected realized, *and* the curve is favorable.[^123][^115]  
- **Liquidity filter**: term structure doesn’t help if spread/slippage eats the edge; enforce tight bid/ask and OI minimums (already aligned with your system design).[^16][^43]

### Suggested “first pass” parameter grid for your backtest
For each underlying, test:
- `IV_Skew_threshold`: 0, +0.5, +1.0, +2.0 vol points (and also z-score thresholds)
- `short DTE`: 7, 10, 14; `long DTE`: 45, 60
- `entry regime`: VIX < 20, 20–30, > 30 (or ETF IV rank buckets)
- `management`: roll at 50% short profit vs 7 DTE vs ML policy

Use transaction costs (half-spread + fees) because calendars/diagonals are slippage-sensitive.[^25][^115]

---

## Best data sources for backtesting (equity/ETF options term structure)

To answer your quantitative questions *exactly* (SPY/QQQ/IWM daily term structure at specific maturities, win-rate splits, regime persistence), the following data sources are appropriate:

- **OptionMetrics IvyDB (US)**: institutional standard for historical option surfaces; supports term structure and strategy backtests.
- **Cboe DataShop**: Cboe historical index/volatility data and SPX options-related datasets.[^157]
- **ORATS API / backtester**: has explicit “contango/negative contango” signals and documented backtester methodology (good for rapid hypothesis testing). Their blog posts show how they wire contango into entries.[^131][^115]
- **LiveVol (Cboe)** / **IVolatility**: implied vol surfaces and analytics.
- **Broker/OPRA feed + internal storage**: feasible if you store daily snapshots of the chain and compute ATM IV term structure yourself; costly but gives maximum control.

If you want a free “sanity-check proxy,” VIX vs VXV history via FRED is workable and reproducible, but it’s still a proxy for SPX term structure rather than SPY chain term structure.[^148][^169]

---

## What to implement now (high-confidence, low-regret)

1. Keep `IV_Skew` in the model, but do **not** implement a strict `IV_Skew > 0` entry gate as the default, because backwardation is rare (~7% of days in a robust SPX proxy) and tends to be stress-linked.[^112]  
2. Implement `IV_Skew` as a **ranking feature** and a **soft filter** (z-score/percentile) so the system prefers favorable curve shape but still trades in normal regimes.[^115][^145]  
3. Add an **event-aware layer** (macro calendar + ETF-specific events where applicable) because backwardation bumps are often event premia.[^144][^137]  
4. Make the final call with a proper backtest on OptionMetrics/ORATS/LiveVol using your exact diagonal construction (ITM long delta, OTM short delta), management rules, and realistic fills; that is the only way to get the exact “win rate differential” numbers you asked for.[^115][^131]

---

### Proxy regime datasets (downloadable)
The computed VIX–VXV regime frequency/duration data used above can be downloaded for inspection and reused in your research notebook.



---

## References

16. [SPY liquidity: Flexibility to navigate any market](https://www.ssga.com/us/en/institutional/insights/spy-liquidity-flexibility-to-navigate-any-market) - When you need a high degree of implementation flexibility—and a cost-efficient tool to navigate diff...

25. [Diagonal Spread Options Strategy: Beginner's Guide | TradingBlock](https://www.tradingblock.com/strategies/diagonal-spread) - The diagonal spread involves buying an in the money option in a later expiration cycle and selling a...

32. [Understanding Diagonal Spreads: A Versatile Options Strategy](https://www.tradestation.com/learn/options-education-center/understanding-diagonal-spreads-a-versatile-options-strategy/) - A diagonal spread is a complex options strategy that a trader may use to potentially profit from var...

43. [Most Active ETFs by Options Volume](https://www.macroption.com/etf-options-volume/)

112. [Market Anxiety Spikes: S&P 500 Options Show Rare Volatility ...](https://www.interactivebrokers.com/campus/ibkr-quant-news/market-anxiety-spikes-sp-500-options-show-rare-volatility-backwardation/) - The S&P 500 options market is flashing signs of unusual short-term anxiety.

113. [[PDF] Option-Implied Term Structures - Federal Reserve Bank of New York](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr706.pdf) - 1 This paper studies term structures of risky assets whose cash flows depend on future realized mome...

115. [Backtesting Calendar Spreads Based on IV Contango](https://orats.com/blog/backtesting-calendar-spreads-based-on-iv-contango) - Backtest a calendar when the implied volatility term structure is in your desired shape. Set the Ent...

123. [How ORATS Uses Historical Volatility Forecasts to Improve Options ...](https://orats.com/blog/how-to-use-hv-forecasts) - The optimizer's p-values will tell you if these forecast-based entries have been statistically signi...

127. [Index Put Calendar Spreads - Market Measures - tastylive](https://www.tastylive.com/shows/market-measures/episodes/index-put-calendar-spreads-11-18-2016) - A results table of RUT Calendar Spreads when IV Rank was below 25 was displayed. The table included ...

131. [Methodology | ORATS API Documentation](https://docs.orats.io/backtest-api-guide/backtester-methodology.html) - Welcome to ORATS API docs

135. [What is a Calendar Spread Option?](https://www.tastylive.com/concepts-strategies/calendar-spread) - Since a calendar spread can be hurt by too much stock movement, we tend to manage our winners at aro...

137. [S&P 500 Implied Volatility Backwardation Reflects Near-Term Event ...](https://www.interactivebrokers.com/campus/ibkr-quant-news/sp-500-implied-volatility-backwardation-reflects-near-term-event-risks/) - The S&P 500 options market is currently reflecting heightened short-term anxiety, as seen through a ...

144. [S&P 500 Implied Volatility Backwardation Reflects Near-Term Event ...](https://orats.com/blog/sp500-implied-volatility-backwardation-event-risk) - Volatility Curve Inversion Points to Caution Around Key Macro Dates

145. [The term structure of equity option implied volatility](https://msbfile03.usc.edu/digitalmeasures/christoj/intellcont/jones_wang-1.pdf)

148. [CBOE Volatility Index: VIX (VIXCLS) | FRED | St. Louis Fed](https://fred.stlouisfed.org/series/VIXCLS) - Graph and download economic data for CBOE Volatility Index: VIX (VIXCLS) from 1990-01-02 to 2026-02-...

157. [Historical Data for Cboe VIX® Index and Other Volatility Indices](https://www.cboe.com/en/tradable-products/vix/vix-historical-data/) - Old methodology: VXO data for 2004 to January 2021 Old methodology: VXO data for 1986 - 2003. Cboe V...

160. [VIX3M (CBOE S&P500 3-Month Volatility Index) - Macroption](https://www.macroption.com/vix3m/)

169. [CBOE S&P 500 3-Month Volatility Index (VXVCLS) | FRED](https://fred.stlouisfed.org/series/VXVCLS) - Graph and download economic data for CBOE S&P 500 3-Month Volatility Index (VXVCLS) from 2007-12-04 ...

183. [Volatility term structure and calendar spread arbitrage - Binance](https://www.binance.com/en/square/post/22116715117394) - Friends in the crypto community, today let's talk about the application of the calendar spread strat...

184. [Long Calendar Spread Strategy Guide - MenthorQ](https://menthorq.com/guide/long-calendar-spread-strategy/) - This article explains how to swing trade volatility using long calendar spreads to benefit from time...

185. [Calendar Spreads | A Hedged Strategy - Market Measures - tastylive](https://www.tastylive.com/shows/market-measures/episodes/calendar-spreads-a-hedged-strategy-12-30-2015) - This segment reveals the detailed study results testing call calendar spreads in the SPY and also se...

