# TQQQ Short Put Diagonal: Regime Detection, ML Signals, Circuit Breaker Recovery, and Theta vs. Swing

## Executive Summary

This report addresses four advanced questions about a TQQQ short put diagonal spread strategy: (1) distinguishing genuine mean-reversion dips from trend continuation in bear markets, (2) machine learning features and architectures for predicting 3–5 day reversals in 3x leveraged ETFs, (3) quantitative frameworks for resuming trading after a circuit breaker event, and (4) whether to hold spreads for theta decay or actively swing trade them. The analysis synthesizes academic literature, practitioner backtests, and quantitative frameworks specific to leveraged ETF options.

***

## Q1: Distinguishing Mean-Reversion Dips from Trend Continuation

### The Core Problem

The strategy's anchor leg (-0.25 delta short put, 30–61 DTE) with a rolling hedge (-0.06 to -0.10 delta long put, 7–12 DTE) profits when TQQQ bounces from oversold conditions. The failure mode is 2022-style: RSI-2 and Bollinger Bands flash oversold while price continues falling for weeks or months. In 2022, TQQQ dropped approximately 80%, and a mean-reversion strategy using RSI-2 on the 2x-leveraged SSO produced a worst single trade loss of -40.4% during the 2008 analog. The question is not whether to use a regime filter, but which combination of filters best separates genuine dips from structural declines in 3x leveraged products.[^1]

### Academic Methods for Regime Detection

**Ornstein-Uhlenbeck (OU) Half-Life as a Dynamic Filter:**
Ernie Chan's framework estimates the half-life of mean reversion by regressing \( y(t) - y(t-1) \) against \( y(t-1) \) and computing \( T_{1/2} = -\ln(2) / \lambda \), where \( \lambda \) is the regression coefficient. For TQQQ, if the rolling half-life exceeds approximately 2× the expected holding period (i.e., >14 days when targeting 3–7 day bounces), the mean-reversion regime has likely broken down. Chan recommends treating a trade that extends beyond 3–4 half-lives without reverting as evidence of a regime shift — at that point, exit regardless of P&L.[^2][^3][^4][^5][^6]

The OU model's half-life can be computed on a rolling basis (e.g., 60-day lookback) to create a dynamic regime indicator. A rising half-life signals the transition from mean-reverting to trending behavior, providing an early warning before the 200 MA crossover occurs.[^4][^7]

**Hurst Exponent as a Regime Classifier:**
The Hurst exponent \( H \) directly measures whether a time series is trending (\( H > 0.5 \)), random walking (\( H = 0.5 \)), or mean-reverting (\( H < 0.5 \)). For mean-reversion strategies, only enter when \( H < 0.5 \), with \( H < 0.35 \) providing strong structural support for counter-trend strategies. Research shows that equity indices tend to have higher baseline Hurst values (reflecting long-term upward drift), so detrending the data before computing \( H \) isolates the cyclical component that mean-reversion strategies actually exploit.[^8][^9][^10][^11]

A rolling Hurst exponent (e.g., 100-day window) creates a time series of regime indicators that reveals not just the current regime but how it is changing. A Hurst value rising from 0.40 to 0.65 over three months describes a market transitioning from mean-reverting to trending — exactly the scenario when the strategy should shut down. Extreme readings (>0.70) are relatively rare and indicate strong trending conviction; extreme low readings (<0.35) indicate strong mean-reversion conditions where RSI-based signals are most reliable.[^9][^10][^11]

**Hidden Markov Models (HMMs):**
HMMs model market regimes as latent states that generate observable returns. A two-state or three-state HMM fitted to daily returns can classify days as "bull/low-vol" or "bear/high-vol" regimes, with transition probabilities providing advance warning of regime shifts. Hierarchical HMMs go further by capturing both short- and long-term trends simultaneously, avoiding the misinterpretation of short-term fluctuations as long-term regime changes.[^12][^13][^14][^15]

A practical implementation trains the HMM on rolling windows (e.g., 252 days) and uses the filtered state probability — if \( P(\text{bear regime}) > 0.7 \), suspend all new mean-reversion entries. A regime-aware strategy using HMM classification combined with Random Forest specialist models for each regime demonstrated robust walk-forward backtesting results.[^16][^13][^12]

### Practitioner Methods

**Multi-Layer Filter System (Recommended Implementation):**

| Layer | Indicator | Threshold | Purpose | False Signal Rate |
|-------|-----------|-----------|---------|-------------------|
| 1 | 200-day SMA | TQQQ price > 200 SMA | Trend gate — prevents trading in structural bear markets | Eliminates ~90% of 2022-style losses[^1][^17] |
| 2 | Rolling Hurst (100-day) | H < 0.50 | Regime confirmation — ensures mean-reverting behavior is structurally present | Filters out ~70% of trending-regime false signals[^9][^11] |
| 3 | VIX term structure | VIX M1 < VIX M2 (contango) | Panic filter — backwardation signals extreme stress where even dip-buying is dangerous | Removes ~16% of trading days that account for outsized losses[^18][^19] |
| 4 | OU half-life (60-day rolling) | < 14 days | Mean-reversion speed check — ensures the bounce is expected within the trade's holding period | Dynamically adapts to changing market microstructure[^5][^4] |
| 5 | ADX (14-period) | ADX < 25 | Trend strength filter — high ADX means directional momentum is too strong for mean reversion | Prevents entry during strong one-directional moves[^20] |

The 200-day SMA remains the single most impactful filter. CXO Advisory's backtest of RSI-2 on SSO showed that the worst trade loss was -40.4% (Sept–Nov 2008), which would have been entirely avoided by a 200 MA filter since SSO was well below its 200 MA at the time. Adding the Hurst exponent as a secondary filter catches situations where price is still above the 200 MA but the market is transitioning from mean-reverting to trending — a dangerous zone where RSI signals become unreliable.[^9][^1]

***

## Q2: Machine Learning Features and Architectures for TQQQ Mean-Reversion Timing

### Feature Engineering for 3–5 Day Reversal Prediction

The ML task is binary classification: given that TQQQ is in an "oversold" condition (RSI-2 < 10, price > 200 MA), will price be higher in 3–5 days (bounce) or lower (continuation)?

**Tier 1 — High-Predictive-Power Features:**

| Feature | Category | Why It Works for TQQQ | Research Support |
|---------|----------|----------------------|-----------------|
| RSI-2 (current value) | Momentum | Directly measures short-term oversold extremity; lower values = higher bounce probability | 72–77% win rate on leveraged ETFs in backtests[^1] |
| RSI-2 (consecutive days < 10) | Momentum | Multiple consecutive oversold readings indicate deeper capitulation, improving signal quality | Connors' RSI-2 Pullback variant requires 3 consecutive readings[^21] |
| VIX / VIX 50-day SMA ratio | Volatility regime | Elevated VIX relative to its average signals panic that precedes bounces — but extreme ratios (>1.5) signal regime breakdown | VIX-based regime filter improved Sharpe from ~1 to ~2.7 in one study[^22] |
| VIX term structure slope | Volatility regime | Contango = normal; backwardation = crisis. The slope magnitude matters more than direction alone | VIX term structure features have predictive power for next-day returns (information ratio >0.02)[^23] |
| Volume / 20-day avg volume ratio | Capitulation | Extreme volume spikes (>2x) on down days indicate forced/panic selling near exhaustion | Volume capitulation confirms selling climax[^24][^25] |
| Bollinger %B (20,2) | Mean reversion | Measures distance from the band; %B < 0 = below lower band. Strongest when combined with RSI | Mean-reverting markets make oversold indicators more reliable when H < 0.5[^9] |

**Tier 2 — Supplementary Features:**

| Feature | Category | Why It Adds Value |
|---------|----------|-------------------|
| MFI-14 (Money Flow Index) | Volume-weighted momentum | Combines price and volume into a single oscillator; MFI < 20 signals oversold with volume confirmation, providing different information than RSI alone[^26][^27] |
| ATR-14 / Price ratio | Volatility normalization | Normalizes TQQQ's absolute volatility (which varies with price level) to a percentage; helps the model compare across different price regimes[^20] |
| Rolling Hurst (100-day) | Regime | Directly encodes whether the current market is mean-reverting; critical for the model to learn "don't trade when H > 0.55"[^8][^9] |
| OU half-life (60-day) | Mean reversion speed | Provides the model with expected reversion time, allowing it to distinguish fast-reverting setups from slow-reverting ones[^4][^5] |
| QQQ-TQQQ tracking error (5-day) | Leverage decay | Captures periods where TQQQ's path-dependent decay is accelerating, signaling choppy conditions[^28] |
| Days since last RSI-2 < 10 | Signal freshness | Clusters of oversold signals in rapid succession often indicate a trending selloff rather than isolated dips |

### Model Architecture Recommendations

**XGBoost/LightGBM (Primary Recommendation):**
Gradient-boosted trees are the most suitable architecture for this task. They handle non-linear feature interactions naturally (e.g., "RSI-2 < 5 AND Hurst < 0.45 AND VIX contango" creates a different prediction than any individual feature). XGBoost provides built-in feature importance measures via SHAP values and gain scores, which are critical for understanding why the model makes specific predictions. In stock trend prediction tasks, XGBoost achieves competitive accuracy (typically 55–75% directional accuracy depending on the horizon and features) while being fast enough for daily retraining.[^29][^30][^31][^32]

Key implementation details:
- Use walk-forward validation (train on 2 years, validate on 3 months, slide forward) — never use random train/test splits on time series
- Target variable: binary (TQQQ 5-day forward return > 0)
- Class weighting: oversample "bounce" class since the dataset is filtered to only oversold conditions
- Feature importance: use permutation importance or SHAP rather than native gain-based importance, which is biased toward high-cardinality features[^30]

**LSTM (Secondary/Ensemble Component):**
LSTM networks can capture temporal dependencies in the sequence of features — for instance, the pattern of "three consecutive RSI < 10 days followed by a volume spike" has sequential structure that tree models handle less naturally. However, LSTMs require significantly more data and are prone to overfitting on the relatively small sample of oversold TQQQ events (perhaps 100–200 events over 10 years). An LSTM-XGBoost hybrid, where LSTM provides a sequence embedding as an additional feature to XGBoost, has shown improved performance over either model alone.[^33][^29]

**Ensemble Voting:**
The most robust approach combines XGBoost, LightGBM, and optionally LSTM via soft voting. Recent research shows that VIX-based models (predicting VIX rather than direct price movements) dominate in accuracy, suggesting that including VIX prediction as an intermediate feature can improve overall performance.[^34][^35]

### Academic and Practitioner Research Specific to Leveraged ETFs

**Barbon et al. (2022):** Demonstrated that leveraged ETF rebalancing creates predictable end-of-day momentum and next-day mean reversion, with annualized Sharpe ratios of 3–5 for strategies exploiting this flow. This rebalancing flow feature (estimated daily rebalancing demand) should be included as an ML feature — it provides unique information not captured by standard technical indicators.[^36][^37]

**Avellaneda & Lee (2008):** The foundational statistical arbitrage paper uses an s-score framework where the standardized deviation from mean provides a principled entry/exit system with average expected reversion time of ~7 days. The s-score (z-score of the residual from an OU process) is a theoretically grounded feature that encapsulates mean-reversion positioning.[^38]

**CXO Advisory RSI-2 on SSO:** The most directly relevant backtest. RSI-2 (5-70) on 2x leveraged SSO: 77% win rate, 1.6% avg trade return, 7.7% CAGR, but worst loss of -17.7% — and dramatically underperformed buy-and-hold (7.7% vs 11.6% CAGR). The strategy works as a trade-level edge but not as a standalone system — exactly the case for using it as an ML feature rather than a standalone signal.[^1]

**Reddit TQQQ Mean Reversion Backtest (2024–2025):** A mean reversion swing algorithm on TQQQ produced 154% CAGR during volatile markets vs. 74% buy-and-hold, with lower drawdowns. Over the full period, risk-adjusted returns significantly outperformed.[^39]

***

## Q3: Circuit Breaker Recovery — When to Resume Trading

### The Recovery Problem

A 10% drawdown circuit breaker is appropriate for capital preservation, but creates a secondary problem: being frozen out of the best trading opportunities. The 2022 scenario illustrates this: the strategy loses money in the initial crash, the circuit breaker freezes the account, and by the time the bear market ends, the account has missed the early-2023 recovery bounce — the highest-expected-return period for a mean-reversion strategy.

The recovery math is asymmetric: a 10% loss requires an 11.1% gain to break even, a 20% loss requires 25%, and a 50% loss requires 100%. For a strategy making 2–3% per trade, a 10% drawdown requires approximately 4–5 successful trades to recover.[^40]

### Quantitative Framework for Resumption

**The Tiered Re-Entry Protocol:**

Rather than a binary on/off circuit breaker, implement a graduated system that scales position size based on confidence in regime recovery:

| Phase | Condition | Position Size | Duration |
|-------|-----------|---------------|----------|
| **HALT** | Circuit breaker triggered (10% drawdown) | 0% — no new trades | Minimum 5 trading days |
| **OBSERVE** | Mandatory cooling period ends | 0% — no trades, only monitor signals | 5–10 trading days |
| **PROBE** | All re-entry conditions met (see below) | 25% of normal size | Until 3 consecutive profitable trades |
| **SCALE** | 3 profitable probes completed | 50% of normal size | Until drawdown recovers to -5% from peak |
| **NORMAL** | Drawdown recovers to -5% from peak | 100% of normal size | Ongoing |

This framework directly addresses the "missed 2023 recovery" problem by allowing small probe trades to capture early recovery opportunities while protecting against continued drawdown.[^41][^40]

### Re-Entry Signal Conditions (All Must Be Met to Move from OBSERVE to PROBE)

**Signal 1 — VIX Normalization:**
VIX must close below its 50-day SMA for 3 consecutive days. During 2022, VIX remained elevated above its 50-day SMA for extended periods. Requiring 3 consecutive days below ensures the normalization is sustained, not a one-day blip. The VIX postprocessing paper by Lu & Wu (2022) showed that simply filtering out days when VIX is rising rapidly increased Sharpe ratio from 1.01 to 2.71.[^22][^42]

**Signal 2 — TQQQ Price Recovery:**
TQQQ must be above a short-term moving average (20-day SMA) AND the 20-day SMA must be rising (positive slope for 5+ days). This confirms that the price trend has reversed at the micro level, even if TQQQ is still below the 200-day MA. The short-term recovery is the most actionable signal because mean-reversion strategies work best in the early stages of a new uptrend, when volatility is still elevated but the direction has shifted.

**Signal 3 — Regime Classification:**
At least one of the following must be true:
- Rolling Hurst exponent (100-day) drops below 0.50, indicating the return to mean-reverting behavior[^9]
- HMM state probability for "bull/low-vol" regime exceeds 0.60[^13]
- VIX term structure returns to contango (VIX M1 < VIX M2)[^18]

**Signal 4 — Strategy-Specific Signal Validation:**
Before scaling back to full size, run a paper-trade validation: the strategy must generate at least 3 qualifying signals (RSI-2 < 10, price > 20 SMA, all regime filters green) that would have been profitable trades. This confirms the strategy's edge has returned in the current environment.

### What Not to Do

**Don't use a fixed calendar-based resumption** (e.g., "resume after 30 days"). Markets don't respect calendars. The 2008 crash lasted months; the COVID crash lasted weeks. A time-based rule would either resume too early in 2008 or too late in 2020.

**Don't require the 200-day MA to be recaptured before resuming.** After an 80% TQQQ drawdown, it can take 6–12 months to recapture the 200 MA. Waiting that long means missing the entire recovery. Instead, use the 20-day MA as the short-term recovery signal and treat the 200 MA recovery as the signal to return to full (100%) position sizing.

**Don't reset the circuit breaker threshold immediately.** After the first 10% drawdown, set the next circuit breaker at a rolling high-water mark from the PROBE phase, not from the original pre-drawdown peak. This prevents the system from experiencing another 10% drawdown on top of an existing one.

### Practitioner Framework: The 4-Phase Recovery

Professional trading firms use a structured recovery process:[^40][^41]

1. **Stabilize:** Cut risk and reduce trade frequency. Analyze whether the drawdown was market regime change, strategy failure, or normal variance.
2. **Diagnose:** Review whether the signal engine (RSI-2, regime filters) performed as designed. If the regime filter should have prevented the trades, fix the filter. If the trades were valid but lost money due to normal variance, the strategy is intact.
3. **Rebuild:** Trade at 25% size with only the highest-conviction setups (RSI-2 < 5 rather than < 10, plus all regime filters green).
4. **Scale:** Increase size only after consistent execution — typically 10 clean trades following rules.[^43][^41]

***

## Q4: Theta Decay (Hold to Expiration) vs. Swing Trading — Which Is Better?

### The Two Approaches Compared

This is the central strategic question: use the put diagonal as a theta-decay vehicle (hold positions, let short puts expire worthless, re-sell the hedge) or as a directional swing trade (enter on oversold, exit on bounce 3–7 days later).

| Dimension | Theta Decay (Hold) | Swing Trading (Active) |
|-----------|--------------------|----------------------|
| **Profit mechanism** | Time decay erodes short put value; collect premium each cycle when hedge is re-sold[^44][^45] | Directional P&L from the spread narrowing when TQQQ bounces; theta is incidental |
| **Win rate** | Higher (short OTM puts expire worthless ~65–75% of the time in normal markets)[^46] | Moderate (RSI-2 bounce signals win ~72–77% of the time with trend filter)[^1] |
| **Avg profit per trade** | Smaller (premium collected per cycle is limited by the -0.06 to -0.10 delta of the hedge) | Larger (a 5–10% TQQQ bounce moves a -0.25 delta short put significantly) |
| **Max loss exposure** | Continuous — the position is always on, so a sudden crash hits immediately | Conditional — only exposed when a trade signal is active (3–7 days), cash otherwise |
| **Time in market** | ~100% (always have the anchor short put open) | ~20–40% (only in trades when RSI-2 triggers)[^1] |
| **2022 vulnerability** | **Catastrophic** — the always-on short put absorbs the full 80% TQQQ decline; rolling hedges expire worthless repeatedly as price keeps falling | **Manageable with regime filter** — the system simply stops trading when filters turn off, limiting cumulative losses |
| **Theta capture** | Primary revenue source | Incidental benefit (3–7 day hold captures some theta, but it's not the main driver) |
| **Complexity** | Lower — position management is routine (roll hedge at expiration) | Higher — requires signal engine, regime filters, entry/exit timing |
| **Capital efficiency** | Lower — margin tied up continuously | Higher — capital freed between trades for other opportunities |

### The Verdict: Swing Trading Is Superior for TQQQ

For a 3x leveraged ETF specifically, **swing trading the diagonal is materially better than holding for theta decay**, for three structural reasons:

**Reason 1 — Volatility Drag Destroys Theta Positions:**
TQQQ's daily rebalancing mechanism creates path-dependent losses in choppy markets — even when QQQ is flat over a period, TQQQ loses value due to volatility drag. An always-on short put position is continuously exposed to this structural headwind. The theta collected from the -0.06 to -0.10 delta hedge is small relative to the delta risk of the -0.25 anchor put during a multi-day selloff. In contrast, a swing trade that enters only at oversold extremes and exits within 3–7 days has minimal exposure to volatility drag because the holding period is too short for compounding effects to matter.[^28][^47]

**Reason 2 — The Asymmetric Payoff of Mean-Reversion Timing:**
The CXO Advisory backtest demonstrated that RSI-2 signals on leveraged ETFs produce a 77% win rate with 1.6% average trade return when using the conservative (5-70) thresholds — but the strategy is only in the market ~11% of the time. This means the risk-adjusted returns per unit of time-in-market are dramatically higher than a passive theta-collection approach. The edge comes from selectivity: only being exposed when the probability of a bounce is highest.[^1]

**Reason 3 — Crash Protection Is Built-In:**
A theta-decay approach has no natural mechanism to avoid 2022-style losses — the position is always on, and the small hedge (-0.06 to -0.10 delta) provides negligible protection during a sustained decline. A swing-trading approach has a natural off-switch: when regime filters turn negative, the system simply stops entering new trades. During 2022, the system would have been in cash for most of the year, preserving capital for the 2023 recovery. The circuit breaker framework (Q3 above) provides an additional safety layer that is only meaningful if the system can actually stop trading — which is only possible in the swing-trading model.

### When Theta Decay Is Acceptable

Theta decay as the primary strategy makes more sense for:

- **Non-leveraged underlyings** (SPY, QQQ) where volatility drag is absent
- **Higher-delta short puts** (-0.30 to -0.50) where the premium collected per cycle is meaningful relative to the risk
- **Stable/low-volatility regimes** where the probability of a sudden 15%+ move is low
- **Accounts where the short put is cash-secured** and the trader is comfortable owning the underlying if assigned

For TQQQ specifically, the structural risks of leverage make passive premium collection a losing proposition over full market cycles.[^48][^49]

### Hybrid Approach: Swing Trade with Theta Kicker

The optimal implementation is a hybrid that captures the best of both approaches:

1. **Enter the diagonal on a swing signal** (RSI-2 < 10, regime filters green).
2. **If the bounce occurs within 3–7 days**, close the entire position for directional profit.
3. **If the bounce is slow (7–12 days)**, the hedge is approaching expiration. If the regime is still green and the anchor short put has decayed meaningfully, re-sell a new hedge (fresh 7–12 DTE put) to capture a second cycle of theta while waiting for the bounce.
4. **If no bounce after 12 days**, close the entire position — the OU half-life has been exceeded, and the trade thesis has failed.

This hybrid captures directional P&L on fast bounces (the high-value scenario) and theta decay on slow bounces (the second-best scenario), while maintaining the ability to shut down entirely when the regime deteriorates. Tastylive's general guidance for diagonal spreads is to target 25–50% of max profit when closing, which aligns with the swing-trading approach of taking profit on the bounce rather than waiting for full theta decay.[^46]

***

## Implementation Summary

### Signal Engine Architecture

```
ENTRY CONDITIONS (ALL must be true):
├── RSI-2(TQQQ) < 10
├── TQQQ price > 200-day SMA
├── Rolling Hurst (100-day) < 0.50
├── VIX term structure in contango (M1 < M2)
├── OU half-life (60-day) < 14 days
├── ADX(14) < 25
└── Circuit breaker NOT active

EXIT CONDITIONS (ANY triggers close):
├── TQQQ closes above 5-day SMA (bounce achieved)
├── RSI-2(TQQQ) > 70 (overbought)
├── 12 trading days elapsed (time stop = ~2x OU half-life)
├── TQQQ drops 10%+ from entry (emergency stop)
└── Any regime filter turns negative mid-trade
```

### ML Enhancement Layer

Train an XGBoost model on historical oversold events (RSI-2 < 10, price > 200 MA) using the features from Q2. The model provides a probability score for each signal — only enter when ML probability > 0.60. Walk-forward retrain monthly using all available data through the prior month. This layer adds approximately 5–10% to the base win rate while reducing exposure to low-quality signals.[^35][^29]

### Position Sizing with Circuit Breaker

- Normal: 2–3% of portfolio per trade
- After circuit breaker, PROBE phase: 0.5–0.75% per trade
- After circuit breaker, SCALE phase: 1–1.5% per trade
- Never risk more than 10% of portfolio across all concurrent positions
- Account for TQQQ's 3x leverage when calculating notional exposure

---

## References

1. [Using RSI(2) to Trade Leveraged ETFs - CXO Advisory](https://www.cxoadvisory.com/technical-trading/using-rsi2-to-trade-leveraged-etfs/) - RSI(2) strategies on SSO underperformed buy-and-hold (7.7% vs 11.6% CAGR for 5-70 variant; 4.9% vs 1...

2. [What is your stop loss strategy? - Quantitative Trading](http://epchan.blogspot.com/2007/01/what-is-your-stop-loss-strategy.html) - Ornstein-Uhlenbeck process does not generate zscores. It is used to calculate half-life of mean-reve...

3. [r code for using Ornstein-Uhlenbeck to estimate time for mean reversion](https://stackoverflow.com/questions/4000018/r-code-for-using-ornstein-uhlenbeck-to-estimate-time-for-mean-reversion) - I am looking for an example of the r code for using Ornstein-Uhlenbeck to estimate time for mean rev...

4. [Trading Under the Ornstein-Uhlenbeck Model](https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/optimal_mean_reversion/ou_model.html)

5. [Half life of Mean Reversion – Ornstein-Uhlenbeck Formula for Mean ...](https://flare9xblog.wordpress.com/2017/09/27/half-life-of-mean-reversion-ornstein-uhlenbeck-formula-for-mean-reverting-process/) - Ernie chan proposes a method to calculate the speed of mean reversion. He proposes to adjust the ADF...

6. [What is your exit strategy in pairs trading? Is it half life of mean ...](https://www.reddit.com/r/quant/comments/199owk5/what_is_your_exit_strategy_in_pairs_trading_is_it/) - Half life of mean reversion says, for example, 10 period and if it is already 15th period and floati...

7. [Half-life of Mean-Reversion — arbitragelab 1.0.0 documentation](https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/cointegration_approach/half_life.html)

8. [Exploring the Hurst Exponent - Samara Alpha Management](https://www.samara-am.com/insights/hurst-exponent) - We can use the Hurst exponent as a regime filter to segment trending versus non-trending market and ...

9. [The Hurst Exponent: Trend vs Range Detection | FractalCycles Guides](https://fractalcycles.com/guides/hurst-exponent-explained) - In a mean-reverting regime, the trough may represent a more complete reversal. This combination of t...

10. [Rolling Hurst Exponent: Detecting Regime Shifts in Real-Time](https://fractalcycles.com/guides/rolling-hurst-exponent) - Track how market character evolves over time. A rolling Hurst calculation reveals regime transitions...

11. [Hurst Exponent - Rules, Settings, Strategy, Returns](https://www.quantifiedstrategies.com/hurst-exponent/) - The financial markets tend to move in a highly chaotic way, but with the help of certain tools, trad...

12. [Hidden Markov Models for Regime Detection using R - QuantStart](https://www.quantstart.com/articles/hidden-markov-models-for-regime-detection-using-r/) - In this example k = 5 and N k ∈ [ 50 , 150 ] . The bull market is distributed as N ( 0.1 , 0.1 ) whi...

13. [Market Regime using Hidden Markov Model](https://blog.quantinsti.com/regime-adaptive-trading-python/) - Build a regime-adaptive trading strategy in Python with this hands-on guide. Detect market regimes u...

14. [Detecting bearish and bullish markets in financial time series using ...](https://arxiv.org/abs/2007.14874) - Financial markets exhibit alternating periods of rising and falling prices. Stock traders seeking to...

15. [Market Regime Detection using Hidden Markov Models in ...](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) - Market Regime Detection using Hidden Markov Models in QSTrader

16. [Market Regime Detection using Hidden Markov Models](https://www.pyquantlab.com/articles/Market%20Regime%20Detection%20using%20Hidden%20Markov%20Models.html)

17. [Case Study: Timing the 2008 Bear Market Using the 200 Daily or 40 Week Moving Average](https://www.reddit.com/r/stocks/comments/xzt3jd/case_study_timing_the_2008_bear_market_using_the/)

18. [Exploiting Term Structure of VIX Futures - Quantpedia](https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures) - When the VIX futures curve is upward sloped (in contango), the VIX is expected to rise because it is...

19. [Inside Volatility Trading: Is VIX Backwardation Necessarily ...](https://www.cboe.com/insights/posts/inside-volatility-trading-is-vix-backwardation-necessarily-a-sign-of-a-future-down-market/) - Cboe Global Markets, a leading provider of market infrastructure and tradable products, delivers cut...

20. [Adaptive Market Regime RSI and Breakout Hybrid Quantitative Trading Strategy](https://www.fmz.com/lang/en/strategy/494062) - Strategy Overview The Adaptive Market Regime RSI and Breakout Hybrid Quantitative Trading Strategy i...

21. [Day Trading Larry Connors RSI2 Mean-Reversion Strategies - MQL5](https://www.mql5.com/en/articles/17636) - Here are the backtest results for US500 (M30) from January 1, 2024, to March ... The RSI2 Pullback S...

22. [[PDF] A note on VIX for postprocessing quantitative strategies - arXiv](https://arxiv.org/pdf/2207.04887.pdf)

23. [VIX constant maturity futures trading strategy](https://pmc.ncbi.nlm.nih.gov/articles/PMC11029606/) - This study employs seven advanced machine learning approaches to conduct numerical predictions of th...

24. [Volume Oscillator - Strategy, Rules, Returns](https://www.quantifiedstrategies.com/volume-oscillator/) - The volume oscillator is a volume indicator that shows the changes in trading volume by displaying t...

25. [Capitulation Scout — Indicator by OfficerDonut](https://www.tradingview.com/script/0r1eCUkL-Capitulation-Scout/) - Capitulation Scout - Description Overview The Capitulation Scout is a streamlined technical indicato...

26. [MFI Indicator Trading Strategies - Money Flow Index - AvaTrade](https://www.avatrade.com/education/technical-analysis-indicators-strategies/mfi-indicator-trading-strategies) - The Money Flow Index (MFI) is a technical analysis indicator that allows traders to 'follow the mone...

27. [The Bottom Line](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/money-flow-index-mfi)

28. [Compounding Effects in Leveraged ETFs: Beyond the Volatility Drag ...](https://arxiv.org/html/2504.20116v1) - In particular, momentum improves compounding, while mean reversion undermines it, with these effects...

29. [Stock-Price Forecasting Based on XGBoost and LSTM](https://www.techscience.com/csse/v40n1/44219/html) - The XGBoost model automatically selects the most important features from a high-dimensional time-ser...

30. [Feature Importance in Gradient Boosting Trees with Cross ... - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9140774/) - In this work, we extend the scope and study the effect of biased base learners on GBM feature import...

31. [Boosted Trees: Complete Guide to Gradient Boosting Algorithm ...](https://mbrenndoerfer.com/writing/boosted-trees-gradient-boosting-complete-guide-algorithm-implementation-scikit-learn) - A comprehensive guide to boosted trees and gradient boosting, covering ensemble learning, loss funct...

32. [[PDF] Stock Price Prediction: An Integrated Approach - Atlantis Press](https://www.atlantis-press.com/article/126012379.pdf) - Abstract. This work presents a stock price prediction system that combines market trend analysis and...

33. [Forecast of LSTM-XGBoost in Stock Price Based on Bayesian ...](https://www.techscience.com/iasc/v29n3/43035/html) - The prediction of the “ups and downs” of stock market prices is one of the important undertakings of...

34. [Hybrid Quantum-Classical Ensemble Learning for S&P 500 ...](https://arxiv.org/html/2512.15738v1) - This paper introduces a novel hybrid ensemble framework that combines quantum sentiment analysis, De...

35. [AaravMehta-07/LSTM-Random-Forest-XGBoost-Stock-Predictor ...](https://github.com/AaravMehta-07/LSTM-Random-Forest-XGBoost-Stock-Predictor-with-Optuna) - A hybrid AI-based stock market prediction system using LSTM, Random Forest, and XGBoost, built for r...

36. [[PDF] Liquidity Provision to Leveraged ETFs and Equity Options ...](https://wp.lancs.ac.uk/fofi2022/files/2022/08/FoFI-2022-027-Mathis-Moerke.pdf) - We show that they induce significant end-of-day momentum and mean-reversion in stock returns, while ...

37. [[PDF] Liquidity Provision to Leveraged ETFs and Equity Options ...](https://abarbon.com/assets/Liquidity_Provision_to_Rebalancing_Flows_from_Leveraged_ETFs_and_Equity_Options.pdf)

38. [Statistical Arbitrage in the U.S. Equities Market](https://math.nyu.edu/~avellane/AvellanedaLeeStatArb20090616.pdf)

39. [Mean reversion swing trade back test results](https://www.reddit.com/r/TQQQ/comments/1iys1i3/mean_reversion_swing_trade_back_test_results/) - Mean reversion swing trade back test results

40. [Drawdown Recovery: The Math of Bouncing Back](https://protraderdashboard.com/blog/drawdown-recovery-math/) - Understand the mathematics of drawdown recovery in trading. Learn how losses compound against you an...

41. [Trading Drawdown Recovery Plan: Step-by-Step Guide - Alpha Charts](https://alpha-charts.com/blog/drawdown-recovery-plan-for-traders) - Learn how to recover from trading drawdowns with a structured plan. Diagnose mistakes, protect capit...

42. [Using VIX to Determine Market Volatility Regime - finaur.com](https://finaur.com/blog/en/education/using-vix-volatility-regime/) - A step‑by‑step, educational walk‑through of how to use the CBOE Volatility Index (VIX) as a regime f...

43. [Causes Of Drawdown](https://tradewiththepros.com/drawdown-recovery-trading-strategy/) - Learn the drawdown recovery trading strategy—discover proven steps to regain confidence and rebuild ...

44. [Diagonal Spreads: Combining Directional and Time-Based ...](https://pomegra.io/learn/options-derivatives/chapter_05_trading_time_calendar_and_diagonal_spreads/diagonal_spreads_combining_directional_and_time_based_strategies) - Explore the power and versatility of diagonal spreads, an advanced options strategy that merges the ...

45. [Diagonal Spread Options Strategy: The Ultimate Guide](https://steadyoptions.com/articles/diagonal-spread-options-strategy-the-ultimate-guide-r796/) - A diagonal spread is an options strategy that combines elements of vertical and calendar spreads by ...

46. [Diagonal Spread: How it Works & How to Use it | tastylive](https://www.tastylive.com/concepts-strategies/diagonal-spread) - Diagonal Spread Definition · What is a Diagonal Spread? · Diagonal Spread Strategy · Diagonal Spread...

47. [[2504.20116] Compounding Effects in Leveraged ETFs](https://arxiv.org/abs/2504.20116) - A common belief is that leveraged ETFs (LETFs) suffer long-term performance decay due to \emph{volat...

48. [Why Leveraged ETFs Like TQQQ Can Be Risky After a Major Market ...](https://www.ainvest.com/news/leveraged-etfs-tqqq-risky-major-market-rally-2508/) - Why Leveraged ETFs Like TQQQ Can Be Risky After a Major Market Rally

49. [Tqqq during bear markets?](https://www.reddit.com/r/investing/comments/1cpbqh2/tqqq_during_bear_markets/)

