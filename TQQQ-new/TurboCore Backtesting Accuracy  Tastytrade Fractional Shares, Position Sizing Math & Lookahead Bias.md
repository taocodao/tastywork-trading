# TurboCore Backtesting Accuracy: Tastytrade Fractional Shares, Position Sizing Math & Lookahead Bias

## Executive Summary

Three compounding errors in the original backtest — fractional options contracts (impossible in reality), integer rounding constraints at small account sizes, and full-sample ML training lookahead bias — combine to inflate CAGR from a realistic ~6–15% range to the reported 39%. The 6.6% CAGR walk-forward integer simulation is almost certainly the more accurate production baseline, though it may be conservatively low due to overcorrecting with a $5,000 account's severe indivisibility problem. The path to improving accuracy requires separating the two independent problems: (1) fractional ETF shares are real on Tastytrade but fractional options contracts do not exist anywhere, and (2) walk-forward ML training eliminates lookahead bias but integer position sizing at $5,000 creates a structural cash drag that narrows significantly at larger account sizes.

***

## Question 1: Tastytrade Fractional Shares — What Is and Is Not Possible

### Fractional ETF Shares: Confirmed and Supported

Tastytrade does support fractional share trading for stocks and ETFs. The minimum investment is 5 and fractional trades carry no commission. A Tastytrade demo explicitly showed purchasing 0.048 shares of SPY (an ETF) as a market order, confirming that quantities like "19.78 shares of QQQ" or "0.0165 shares of QLD" are mechanically executable on the platform.[^1][^2][^3][^4][^5]

Bankrate confirmed that Tastytrade's fractional program covers "thousands of stocks and ETFs" with a 5 minimum purchase and a 0.10 clearing fee per transaction. For SGOV specifically, a 2025 Reddit thread noted a temporary minimum quantity increase to 100 shares on some settings, but a commenter confirmed that fractional shares remained purchasable. The eligible universe is broad — all major ETFs including QQQ, QLD, and SGOV fall within the supported range for fractional trading.[^2][^6][^7]

**Key implementation detail:** Fractional share orders on Tastytrade must be placed as **market orders**, not limit orders. For daily-rebalancing algorithms executing at-the-open or at-the-close, this means you cannot specify a limit price on the fractional portion, introducing minor execution slippage that a backtest may not account for.[^4]

### Fractional Options Contracts: Categorically Impossible

Options contracts in the U.S. are standardized by the Options Clearing Corporation (OCC), and **the minimum tradeable unit is always 1 full contract**, representing 100 shares of the underlying. This is not a broker limitation — it is a market structure rule enforced across all U.S. exchanges and brokers. As Nasdaq explicitly states: "You can have one contract or many, but fractional contracts are not traded."[^8][^9]

This is the single most consequential finding for your backtest: the simulation allowing 19.78 LEAPS contracts is physically impossible. Any position in QQQ LEAPS must be a non-negative integer — 0, 1, 2, 3, etc. — regardless of account size or broker. On a $5,000 account with a single deep ITM LEAPS contract costing ~$4,000–$8,000, the system can only hold 0 or 1 contract at any given time, creating enormous position sizing distortions.[^10][^8]

### Practical Impact: Which Backtest Assumption Is Correct?

| Asset | Fractional Possible? | Tastytrade Minimum | Notes |
|---|---|---|---|
| QQQ (ETF) | ✅ Yes | $5 | Market order only[^4] |
| QLD (ETF) | ✅ Yes | $5 | Market order only[^2] |
| SGOV (ETF) | ✅ Yes | $5 | Fractional confirmed despite some UI quirks[^6] |
| QQQ LEAPS Call (options) | ❌ No | 1 full contract | OCC standard; no exceptions[^9][^8] |

**Verdict:** Your backtest should model fractional ETF positions for QQQ, QLD, and SGOV — this is realistic on Tastytrade. But QQQ LEAPS must always be modeled in whole integer contracts (0, 1, 2, …). Allowing 19.78 LEAPS contracts as the simulation did is the primary driver of the inflated 39% CAGR figure.

***

## Question 2: The Mathematical Mechanics of Fractional vs. Integer Constraint Effects

### Why the CAGR Gap is So Large at $5,000

The dramatic CAGR difference between the fractional simulation (39%) and the integer simulation (6.6%) can be decomposed into three compounding mathematical mechanisms:

**1. Cash Drag from Indivisibility**

With a 60% LEAPS allocation target on a $5,000 account, the target deployment is $3,000. A single deep ITM QQQ LEAPS contract (80% strike, 1-year expiry) costs approximately $4,000–$8,000 — meaning the account either cannot afford even one contract (resulting in 0% allocation instead of 60%), or it must use ~80–160% of its capital to buy one contract (a forced over-allocation). On the days where the system cannot buy a contract, the entire 60% allocation sits in cash earning near-zero or SGOV-level returns instead of the leveraged LEAPS position. This is **extreme cash drag**.[^11]

In the fractional simulation, 60% of capital is deployed into LEAPS *every single day*, perfectly compounding at the strategy's true geometric return. In the integer simulation, the strategy may deploy 0% or 100%+ in LEAPS depending on the arbitrary relationship between account value and option price. The expected allocation error per rebalance period is not small — it can represent the entire LEAPS position.

**2. Compounding Distortion**

Daily rebalancing with a fixed-percentage allocation rule produces dramatically different compound growth depending on whether the allocation can be executed precisely. Let \( r_L \) be the daily LEAPS return, \( r_C \) be the cash return, and \( f = 0.60 \) be the target LEAPS fraction. With perfect fractional execution, portfolio return per day is:

\[ R_{\text{fractional}} = f \cdot r_L + (1-f) \cdot r_C \]

With integer constraint, the system either deploys \( f' = 0 \) (zero contracts, full cash drag) or \( f' = \frac{\text{contract cost}}{\text{account value}} \) (often > 1.0 when account < contract cost). The realized portfolio return becomes:

\[ R_{\text{integer}} = f' \cdot r_L + (1-f') \cdot r_C \]

Over 252 trading days compounding daily, even a small persistent difference in the deployed fraction translates into an enormous CAGR gap. If the fractional strategy achieves +1.5% geometric mean per day and the integer strategy averages +0.5% due to cash drag on non-contract days, the annualized returns diverge by orders of magnitude: \( 1.015^{252} \approx 41x \) vs. \( 1.005^{252} \approx 3.5x \).

**3. Rebalancing Efficiency Loss**

A daily rebalancing strategy depends on selling winners and buying losers *continuously* to maintain target allocations and harvest rebalancing premium. With integer contracts, the system cannot rebalance incrementally — it must add or remove entire $4,000–$8,000 blocks. This destroys the mean-reversion harvesting benefit of daily rebalancing for the LEAPS component entirely. The ETF components (QLD, SGOV) *can* rebalance fractionally, but the dominant LEAPS position cannot, so the strategy's core rebalancing alpha is impaired.[^12]

### Does the Gap Narrow at Larger Account Sizes?

Yes — substantially. The indivisibility problem is a function of the ratio of contract cost to account size. As account size grows, the LEAPS allocation target ($3,000 at $5,000 account → $12,500 at $25,000 → $30,000 at $50,000) exceeds the per-contract cost, allowing the system to hold 3–7 contracts and approximate the target allocation much more closely.

| Account Size | Target LEAPS (60%) | Typical LEAPS Contract Cost | Approx. Contracts | Allocation Error |
|---|---|---|---|---|
| $5,000 | $3,000 | ~$5,000 | 0 or 1 | Very high (0%–100%+) |
| $25,000 | $15,000 | ~$5,000 | 3 | ~5–10% error |
| $50,000 | $30,000 | ~$5,000 | 6 | ~2–5% error |
| $100,000 | $60,000 | ~$5,000 | 12 | ~1–2% error |

At $25,000–$50,000, the integer constraint becomes a modest drag rather than a strategy-crippling indivisibility problem. The CAGR convergence between fractional and integer simulations at these sizes would be dramatically closer. This is why your $5,000 account test is an extreme case that exaggerates the simulation divergence far beyond what would occur in a more adequately capitalized account.

### The Minimum Practical Account Size for This Strategy

For a 60% LEAPS allocation with deep ITM QQQ LEAPS at ~$5,000 per contract, the minimum account where integer constraints become manageable is approximately $20,000–$25,000 (allowing 2–3 contracts, keeping allocation error under 10%). Below $10,000, the strategy is structurally incompatible with integer-only LEAPS sizing — the backtest's fractional assumption isn't just theoretically wrong, it's practically necessary for the strategy to function as designed.

***

## Question 3: Lookahead Bias in ML-Driven Backtesting

### Terminology and Academic Classification

Training an ML model on the full dataset before backtesting the same period is formally called **in-sample training bias**, **data snooping**, or **lookahead bias** in the quant literature. The most rigorous term from institutional research is **backtest overfitting** (Bailey & López de Prado). When multiple model configurations are trained on the same data, the broader problem is called the **multiple testing problem** or **selection bias**.[^13][^14][^15][^16][^17]

The key academic distinction: "data snooping" (Lo and MacKinlay, 1990) refers to the general problem of using a dataset multiple times for inference. "Backtest overfitting" specifically captures the probability that a strategy selected for in-sample performance will underperform out-of-sample. López de Prado has proposed the **Deflated Sharpe Ratio (DSR)** and **Combinatorially Symmetric Cross-Validation (CSCV)** as formal tools for quantifying the degree of overfitting, adjusting Sharpe ratios for non-normality, serial correlation, and number of trials tested.[^18][^19][^14][^20][^16][^21]

### How Much Return Inflation Does Full-Sample Training Cause?

Published research documents wide variation in overfitting magnitude, but several consistent findings apply:

- **Quantpedia's cross-strategy analysis** found that out-of-sample Sharpe ratios average **33% lower (median: 44% lower)** than in-sample Sharpe ratios across a large cohort of published strategies. For an in-sample CAGR of 39%, this implies an OOS baseline reduction to roughly 22–26% — before accounting for additional lookahead from full-sample model training.[^22]
- **Bailey and López de Prado's backtest overfitting work** demonstrated that an optimized strategy can achieve a Sharpe ratio of 1.59 in-sample but **negative (-0.18) out-of-sample**, meaning the strategy actually *lost money* — an infinite inflation ratio in terms of alpha.[^17]
- **3x–10x return inflation ratios** are not uncommon when full-sample ML training is combined with aggressive feature selection. A 2016 Price Action Lab analysis noted that "annual returns above 12% usually point to curve-fitted results or coding errors" — a benchmark that your 39% vastly exceeds.[^23]
- For a **specific HMM/XGBoost combination** with full-sample training on 7 years of data: the performance differential observed in published walk-forward experiments is severe. One LinkedIn case study showed an HMM strategy producing ~56% CAGR on a full-sample backtest vs. ~11% CAGR with proper walk-forward validation — a **5x inflation ratio**.[^24]

**The 39% vs. 6.6% ratio in your backtest (~5.9x) falls squarely within the documented range** for ML strategies with full-sample training lookahead bias.

### HMM vs. XGBoost: Relative Lookahead Severity

These two model types have different overfitting profiles:

**Hidden Markov Models (HMMs) — Higher Lookahead Risk:**

HMMs fitted to the full dataset are particularly susceptible to lookahead bias because the Baum–Welch algorithm (expectation-maximization) uses **all observations simultaneously** to estimate transition matrices and emission distributions. The resulting regime labels are "hindsight-optimal" — the model knows which regimes produced the best outcomes and assigns them retroactively. In walk-forward testing, HMMs must be re-estimated at each step using only past data, and their performance "collapses" dramatically because the forward-looking information embedded in full-sample emission parameters is unavailable.[^25][^26][^24]

Critically, in a standard full-sample HMM backtest: "oracle labels are shifted forward so that predictions for the regime on Day t+1 are based solely on information available to Day t" — but if the HMM itself was trained on the full series, the regime assignment at every point implicitly incorporates future information through the global Baum–Welch convergence. Even if you think you're using lagged regime assignments, the underlying model parameters encode full-sample statistics.[^27]

**XGBoost — Moderate Lookahead Risk:**

XGBoost fitted on the full dataset suffers lookahead bias through its learned feature importances and decision boundaries, but the bias is somewhat less severe than for HMMs because:
1. XGBoost is a discriminative model — it learns decision boundaries rather than global distributional parameters
2. If features are properly lagged (only past prices used as inputs), the bias is limited to the training period leakage rather than a structural inversion of regime assignment
3. Published walk-forward XGBoost research shows directional accuracy of 65.15% OOS vs. substantially higher IS figures — meaningful degradation but not collapse[^28]

However, when XGBoost is used as a **signal confidence scorer conditioned on HMM regime labels** (as in your architecture), it inherits the full HMM lookahead contamination through the feature labels it trains on.[^29]

| Model | Lookahead Mechanism | Severity | Walk-Forward Fix |
|---|---|---|---|
| HMM (full-sample) | Baum-Welch EM uses all T timesteps simultaneously; global transition/emission parameters encode future regime information | High | Re-estimate HMM on expanding window at each step; use only past data |
| XGBoost (full-sample) | Decision boundaries fitted to full-sample signal distributions | Moderate | Re-train on expanding window; use purged k-fold cross-validation |
| HMM + XGBoost combined | XGBoost trained on contaminated HMM regime labels | Very High | Must fix HMM first, then re-train XGBoost on walk-forward HMM outputs |

### Walk-Forward Best Practices for ML Trading Systems

**1. Expanding Window Training (Preferred for Regime Models)**

For each prediction date \( t \), train the HMM and XGBoost using only data from \( [t_0, t-1] \). The training set grows incrementally. This is preferred over rolling windows when regime parameters evolve slowly (which is typical for equity markets).[^30][^28]

For XGBoost, use **Purged Walk-Forward Cross-Validation** (López de Prado's CPCV framework): after each training-test split, create an embargo period of 1–5 days between training and test folds to prevent leakage from serial autocorrelation in features. Standard k-fold cross-validation is invalid for time series because it randomly shuffles time, allowing future data into training folds.[^14]

**2. HMM Regime Label Generation Protocol**

The correct approach for walk-forward HMM regime detection:[^26][^25]
- At each day \( t \), fit HMM using returns from \( [t_0, t-1] \)
- Apply the forward-backward algorithm (not Viterbi) to compute regime probabilities \( P(\text{state} | \text{data up to } t-1) \)
- Use these probabilities as features for the next-day XGBoost prediction (predicting \( t \)'s signal using regime info from \( t-1 \))
- Never use the final Viterbi-decoded regime sequence from the full-sample HMM as labels — this is the primary lookahead mechanism

**3. Retraining Frequency**

Retraining both models daily is computationally expensive but most rigorous. Acceptable alternatives:[^31][^32]
- Retrain monthly with a 2–4 year expanding window
- Use out-of-sample validation windows of 3–6 months
- Apply the 70/30 in-sample/out-of-sample ratio as a baseline structure

**4. Formal Overfitting Detection**

After generating the walk-forward equity curve:
- Compute the **Deflated Sharpe Ratio** (DSR) — adjusts for non-normality and the number of trials tested[^20]
- Estimate **Probability of Backtest Overfitting (PBO)** via CSCV — a PBO below 5–10% is considered acceptable[^16][^33]
- Apply Hansen's **Superior Predictive Ability (SPA) test** and White's **Reality Check** when multiple model variants were tested[^15][^14]
- Report the **minimum backtest length (MinBTL)** required for statistical significance given your Sharpe ratio and number of trials — shorter periods with high Sharpe ratios require particularly skeptical evaluation[^34]

***

## Synthesizing the Verdict: Which CAGR Is Closer to Production Reality?

The 39% CAGR backtest suffers from at least three stacked biases:
1. **Fractional LEAPS contracts** (impossible — options are integer-only): inflates by enabling precise position sizing that real production cannot achieve
2. **Full-sample HMM + XGBoost training** (classic lookahead): inflates by giving the model knowledge of future regimes when assigning past signals
3. **Daily exact rebalancing assumption** (likely optimistic): production execution involves market-order fractional ETF fills with 0.10 clearing fees each, slippage on LEAPS (wide bid-ask spreads on deep ITM, 1-year expiry), and no guarantee of at-open fill prices

The 6.6% CAGR walk-forward integer simulation is structurally more honest but overcorrects for position sizing on a $5,000 account — an account size that makes the LEAPS allocation mechanically impossible. A more realistic estimate for a **properly capitalized account ($25,000+) using walk-forward ML and integer LEAPS sizing** likely lands between the two extremes: approximately **12–20% CAGR**, assuming the underlying QQQ/LEAPS strategy has genuine edge after walk-forward validation.

| Backtest Version | Fractional LEAPS | ML Training | Realistic? |
|---|---|---|---|
| 39% CAGR (original) | ✅ Fractional (impossible) | Full-sample (lookahead) | ❌ No — two major biases |
| 6.6% CAGR (corrected) | ❌ Integer (realistic) | Walk-forward (correct) | Partially — $5k structural cash drag distorts |
| Target production estimate | ❌ Integer | Walk-forward | Run at $25k+ account; expect 12–20% if real edge exists |

The corrected backtest's walk-forward ML is the right methodology. The remaining challenge is that $5,000 is simply too small a capital base for a strategy that requires $4,000–$8,000 increments to deploy its primary position. Running the same integer/walk-forward simulation on a $25,000 account would provide the most reliable production estimate.

---

## References

1. [Fractional Shares Trading - Support - Tastytrade](https://support.tastytrade.com/support/s/solutions/articles/43000657855) - tastytrade currently supports the purchase and sale of fractional shares. Additionally, we support t...

2. [Best Brokers For Fractional Share Investing - Bankrate](https://www.bankrate.com/investing/best-brokers-fractional-share-investing/) - Charles Schwab's Stock Slices allows investors to buy a fractional share of any stock in the Standar...

3. [Options, Futures, Cryptos Fees & Commissions - Tastytrade](https://tastytrade.com/pricing/) - Low commissions on options, futures, cryptos and stocks. From just $1.00/contract. Brokerage fee com...

4. [Tastytrade Fractional Share Demo - YouTube](https://www.youtube.com/watch?v=ueVjR8Gs2G0) - How to purchase fractional shares of stock using the tastytrade desktop platform. Tastytrade Fractio...

5. [tastytrade Fractional Shares Trading Conditions Explained](https://brokerchooser.com/invest-long-term/diversification/fractional-shares-tastytrade) - Fractional shares are great for beginners, since you can invest only a fraction of the money you wou...

6. [SGOV minimum quantity increased to 100? : r/tastytrade - Reddit](https://www.reddit.com/r/tastytrade/comments/1hv0zxg/sgov_minimum_quantity_increased_to_100/) - I bought 10 x SGOV. Now I noticed the minimum quantity is 100. This was the only alternative to park...

7. [Fractional Shares: What Are They and How to Invest - Finder](https://www.finder.com/stock-trading/fractional-shares) - Fractional shares are slices of whole shares, letting you invest in stocks and exchange-traded funds...

8. [How Many Shares In An Option Contract: A Beginner's Guide](https://legacystocktransfer.com/how-many-shares-in-an-option-contract/) - A single option contract represents 100 shares for most stocks. It gives traders a powerful tool for...

9. [Options 101 - Nasdaq](https://www.nasdaq.com/articles/options-101) - In most cases, stock options contracts are for 100 shares of the underlying stock. You can have one ...

10. [Other FAQs for investing in options - Help - Tiger Brokers](https://www.itiger.com/nz/help/detail/03522643) - The minimum trading unit for US stock options is 1 contract, which is generally equivalent to 100 sh...

11. [Best Small Account Leap Option Strategy - YouTube](https://www.youtube.com/watch?v=HZVKbmNJkA8) - ... Leap Options In 2024: Complete Guide By Matt Giannino https://www.youtube.com/watch?v=JmCV0EC4Xp...

12. [Investing in Fractional Shares - Yahoo Finance](https://finance.yahoo.com/news/investing-fractional-shares-040000249.html) - A fractional share represents ownership of less than a full share of stock. Rather than having to pu...

13. [[PDF] Data-Snooping Biases in Financial Analysis](https://www.hillsdaleinv.com/uploads/Data-Snooping_Biases_in_Financial_Analysis,_Andrew_W._Lo.pdf) - We snoop the data in all sorts of subtle ways (recall the backtest of 8-94), and these subtleties ar...

14. [Overfitting & Data-Snooping in Backtests: How to Avoid It | Surmount](https://surmount.ai/blogs/backtests-overfitting-data-snooping-avoid) - Data-snooping bias (also called multiple testing or p-hacking) appears when you test many versions o...

15. [[PDF] Data-Snooping, Technical Trading Rule Performance, and the ...](https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf) - In this paper we utilize White's Reality Check bootstrap methodology ~White ~1999!! to evaluate simp...

16. [[PDF] THE PROBABILITY OF BACKTEST OVERFITTING - David H Bailey](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) - In [2] Bailey and López de Prado developed methodologies to evaluate the probability that a Sharpe r...

17. [[PDF] Backtest overfitting in financial markets - David H Bailey](https://www.davidhbailey.com/dhbpapers/overfit-tools-at.pdf) - In mathematical finance, backtest overfitting means the usage of historical market data (a backtest)...

18. [Data-Snooping Biases in Tests of Financial Asset Pricing Models](https://academic.oup.com/rfs/article-abstract/3/3/431/1592120) - Tests of financial asset pricing models may yield misleading inferences when properties of the data ...

19. [[PDF] A REALITY CHECK FOR DATA SNOOPING WHENEVER A ''GOOD ...](https://www.ssc.wisc.edu/~bhansen/718/White2000.pdf) - Data snooping occurs when a given set of data is used more than once for purposes of inference or mo...

20. [Dangers of Backtest Overfitting - Marcos Lopez de Prado - YouTube](https://www.youtube.com/watch?v=QxhxLwNbMMg) - Dangers of Backtest Overfitting - Marcos Lopez de Prado. 8.8K views · 9 years ago ...more. Alex Bern...

21. [The Probability of Backtest Overfitting - ScholarWorks](https://scholarworks.wmich.edu/math_pubs/42/) - We propose a general framework to assess the probability of backtest overfitting (PBO). We illustrat...

22. [In-Sample vs. Out-Of-Sample Analysis of Trading Strategies](https://quantpedia.com/in-sample-vs-out-of-sample-analysis-of-trading-strategies/) - It seems strategies seem to deteriorate an out-of-sample, but we have some really strong positive ou...

23. [Look-Ahead Bias And How To Detect It - Price Action Lab](https://www.priceactionlab.com/Blog/2016/03/detect-look-ahead-bias/) - Look-ahead bias in backtests usually involves counting returns before the entry signal and, in some ...

24. [Regime Switching on NVDA with a Hidden Markov Model (HMM)](https://www.linkedin.com/posts/bhadz-lagayan-781211b2_quanttrading-machinelearning-hiddenmarkovmodels-activity-7374082074472931328-IrTp) - In a classic HMM, a simple IS/OOS approach can risk 'looking ahead' at the transition probability ma...

25. [Hidden Markov Model Market Regimes: How HMM Detects Market ...](https://www.quantifiedstrategies.com/hidden-markov-model-market-regimes-how-hmm-detects-market-regimes-in-trading-strategies/) - To use an HMM for regime detection, we fit the model to historical market data (typically asset retu...

26. [Creating More Consistent Investment Returns Using Market Regime ...](https://www.youtube.com/watch?v=3U2AoySocRc) - An HMM (Hidden Markov Model) is a probabilistic regime-detection ... To avoid overfitting and look-a...

27. [A multi-model ensemble-HMM voting framework for market regime ...](https://www.aimspress.com/article/id/69045d2fba35de34708adb5d) - To avoid lookahead bias, oracle labels are shifted forward so that predictions for the regime on Day...

28. [XGBoost Forecasting of NEPSE Index Log Returns with Walk ... - arXiv](https://arxiv.org/html/2601.08896v1) - A critical aspect of rigorous evaluation in financial forecasting is the avoidance of lookahead bias...

29. [TurboCore-Pro-ML-Enhancement-Failure-Diagnosis-Why-Meta-Labeling-Macro-Features-Produced-Zero-Alpha.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/383baf4b-eaf9-4971-b3b5-82fa6274932f/TurboCore-Pro-ML-Enhancement-Failure-Diagnosis-Why-Meta-Labeling-Macro-Features-Produced-Zero-Alpha.md?AWSAccessKeyId=ASIA2F3EMEYEQXKWU6AL&Signature=iSUbaK%2BiRUQOQjaY8nGFKuwCOms%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEHoaCXVzLWVhc3QtMSJHMEUCIQDz8uDA4xtbjQQUyY7OlCCTSjLwDdJ2wbgwCARnVJuEwAIgCJasN6wL4Gwjf4bZsbR1%2FpclUMmAp7ZG4GdKLc7HtxIq8wQIQhABGgw2OTk3NTMzMDk3MDUiDBgKFnDjBOvyu8k3QSrQBNXUAUIxe1XIqRa2ByKVvhl1QRZC0zI2Xke%2BZXMenjHM5hXn9XS68f%2BUnzUTZ7r3XSwd0AUf6uJp3FLSOthEI%2FtITVUFGSTVdb%2BfU2d0uvu%2FsyvnZ%2BAbYWeOi57GKzx6zXelf2FMJiR280te3N02pClP%2BnUwyo1DQS7n2yUfkZ9zeI0YvEnzl1CGdZJW4oPpIGlw2s90joTpWgEKroEFo%2FCWElK%2BJMC%2F45u4dXDFhMXK9TT8vml1qCqGbGkN7wI5QVO0CAJIr8rrG%2FhYn6oDLVMF%2BUUeP06QLnhYttQHr9J0t0n971zbV327V%2BIwFOqLGb8Wx4agFGqQ%2FGImYdOOmSkPLdBRpLzfJ6SYw6%2BEvz%2BgqKuhBxFLhvue4mZ0jjdIjhC4O%2BxQJz2sM%2Fy%2B0dCDHNW9OcjX60ARukh4c3ANpmYPxubUJM7Ui%2B14IT4i1yXPmO%2BWv3IJWN0ZEVRQOvrlis9owdQwzX9MHPxqVfXUyeDU%2FZkuI6ehF3uA8IKszSjNounKWn7%2FXH%2BZb%2BeWcWV5lcR8lwDHO6W9Hs4%2FzoLz78IQGX%2Fsc5dH%2BXbEIbzKNdda3qPG1oYyUNftIU0zN6ycv0sfnvTqvKAB%2FA59W9SQai9hxUXelxv7zuG3HutLhUkDcF56OQGqFEn5UjhsAC3cw9yNzGVlJM5boqHCIMsBRF%2FoQdoIx2VPa2X8vBj%2ByQIA%2FTb5vthcVALYU8mAevFQV8TAyVkpBu96w9TyBkcZ9nSZn7WJ8qMpnEf9BZUGXfhnlXgoeLdeBUBhMZNYcz5Zrbwwq%2BP3zQY6mAGwuAmEAONLAd7V03QUfhCxbJsnaOYcqNWsHhlJIISv98sIN9iYrJYBcKkpmQ1tYBtakS2TyQeMJcxJWcfRJMhpr4MqxVw5YuQp%2F9CvZehnYb1Rn4ZevKlqkZknKuYmh2CvN18IDPtklub81ic6OGdnwosy%2BfTCMDvlCXKJKGtw3BDo2cXpK3T%2FZ%2FSSegTo96maCc0y2G%2B5GA%3D%3D&Expires=1774059390)

30. ["Walk forward" vs "expanding window" in backtesting : r/algotrading](https://www.reddit.com/r/algotrading/comments/1qz8imc/walk_forward_vs_expanding_window_in_backtesting/) - What we can control is the risk of loss to our trading account. We can do that by adjusting the size...

31. [Walk-Forward Optimization (WFO) - QuantInsti Blog](https://blog.quantinsti.com/walk-forward-optimization-introduction/) - Walk-forward optimisation reduces overfitting by testing each segment of data in a forward-looking m...

32. [Walk-Forward Analysis vs. Backtesting: Pros, Cons, and Best Practices](https://surmount.ai/blogs/walk-forward-analysis-vs-backtesting-pros-cons-best-practices) - - Walk-forward validation with expanding training windows and sequential testing periods. Best pract...

33. [Trading Backtest Explained – 3 real life exemples - QUANTREO BLOG](https://www.blog.quantreo.com/trading-backtest-explained/) - Learn how to analyze a trading backtest thanks to 3 real life examples. How to combine the methods a...

34. [[PDF] THE EFFECTS OF BACKTEST OVERFITTING ON OUT-OF-SAMPLE ...](https://obj.portfolioconstructionforum.edu.au/articles_perspectives/Pseudo-mathematics-and-financial-charlatanism.pdf) - Indeed, the PSR-Stat is 2.83, which implies a less than 1% probability that the true Sharpe ratio is...

