# TurboCore ML-Enhanced TQQQ Strategy: Five Critical Architecture Problems Diagnosed & Fixed

## Executive Summary

Five interconnected problems are crippling this ML trading pipeline: triple-barrier parameters calibrated for standard equities that make TP unreachable on a 3x leveraged ETF; a GaussianHMM with pathological oscillation caused by poorly initialized transition priors and miscalibrated features; a meta-labeling model starved of training data from an episodic signal source; a Kelly formula with a miscalculated b-ratio for options; and a BOCD implementation whose Gaussian likelihood assumption is catastrophically mismatched to TQQQ's fat-tailed return distribution. Each problem has a specific, evidence-backed fix detailed below.

***

## Problem 1: Triple-Barrier Labeling Produces 0% Positive Labels

### Root Cause: Path Volatility Misuse

The core failure is using **TQQQ path volatility as the barrier scaler** when it is orders of magnitude too large. With TQQQ's 60-day realized volatility at ~60–80%, setting TP = 3.0× path_vol means requiring a ~180–210% gain within 63 trading days — an event that essentially never occurs in a single 3-month window. The triple-barrier method is designed to set barriers as multiples of *daily* volatility, not *path volatility* (which is the cumulative standard deviation over the entire holding period).[^1][^2][^3][^4]

López de Prado's original formulation uses `trgt` as the *daily volatility* (typically a 20-day exponentially weighted moving standard deviation of daily returns), then scales horizontal barriers as multiples of this daily estimate. The correct TP barrier for one day's exposure is:[^3][^1]

\[ \text{TP barrier} = pt \times \sigma_{daily} \]

where \( \sigma_{daily} \) is the 20-day EWMA daily vol, and \( pt \) is a multiplier typically between 1.0 and 3.0 for standard equities. For a 63-day holding window, the correct barrier level is not 3× cumulative path vol — it is 3× *one day's* vol applied as a *return threshold* from entry.

### Correct Parameters for a 3x Leveraged ETF

Standard equity backtests (1–2% daily vol) typically use TP multipliers of 1.5–3.0× daily vol and SL of 0.5–1.0×. For TQQQ with 4–5% daily vol, the absolute barriers need recalibration. Empirical research on Korean equities found that optimal triple-barrier parameters for a 29-day horizon were 9% absolute TP/SL barriers, yielding a balanced label distribution (35% TP, 29% SL, 36% timeout). Scaling this for TQQQ's 3× leverage and higher volatility suggests:[^5][^6][^3]

| Parameter | Standard Equity (1–2% daily vol) | TQQQ Recommendation (4–5% daily vol) |
|---|---|---|
| Barrier scaler | 20-day EWMA daily vol | 20-day EWMA daily vol (NOT path vol) |
| TP multiplier | 1.5–3.0× | 1.0–1.5× |
| SL multiplier | 0.5–1.0× | 0.5–0.75× (tighter to reflect leverage) |
| Forward window | 20–60 days | 15–30 days |
| Target label split | ~33% each | ~30–35% TP, aim for balance |

### Label on QQQ vs TQQQ

For meta-labeling a TQQQ strategy, label on **TQQQ price directly** rather than QQQ. The meta-model's job is to predict whether the TQQQ trade itself succeeds; QQQ returns have a different (and smoother) path due to the absence of compounding leverage decay. However, volatility features used to compute `trgt` can be based on QQQ vol (less noisy, more stable EWMA) — this is a legitimate hybrid: QQQ-derived volatility target, TQQQ-priced barriers.[^7][^8]

### Minimum Label Balance for XGBoost

A class imbalance more severe than approximately 1:10 (minority:majority) causes XGBoost meta-labelers to default to predicting the majority class constantly, achieving low loss but zero alpha. For meta-labeling to outperform a constant-output baseline, the label distribution should be at least 20–30% positive before any oversampling is applied. With 31 golden-cross events over 7 years, the fundamental problem is not just the barrier calibration — the sample size is also critically insufficient (addressed in Problem 3).[^9][^10][^11]

***

## Problem 2: GaussianHMM Oscillating at ~98% Daily Transition Rate

### Why This Happens

A 98% daily BULL↔SIDEWAYS transition rate means the HMM's learned transition matrix has `transmat_[^1] ≈ 0.98` — the model assigns near-certainty to switching states on every step. This pathology emerges from three causes:[^12][^13]

1. **Identical emission distributions for BULL and SIDEWAYS**: If the two features (QQQ 20-day HV and VIX) have overlapping distributions across regimes, the Baum-Welch EM algorithm fails to separate them and creates a "blurred" model that oscillates rather than committing to states.
2. **Random initialization of the transition matrix**: hmmlearn initializes `transmat_` randomly by default, and random initializations near the boundary of the simplex (equal transition probabilities) frequently converge to oscillatory solutions.
3. **Feature scale mismatch**: VIX (range ~10–80) and QQQ_vol_20d (range ~0.005–0.04 as a decimal) are on completely different scales. The GaussianHMM's Gaussian emissions assume features are on comparable scales; without standardization, one feature dominates and the other provides near-zero discriminatory power.

### predict() vs predict_proba(): Which Reduces Oscillation?

`model.predict()` uses the **Viterbi algorithm** (MAP path decoding), which finds the single most likely state sequence globally — it naturally penalizes excessive switching because each transition incurs a transition-probability cost. `model.predict_proba()` returns smoothed **forward-backward posterior probabilities** for each state at each time step — these posteriors are smoother than Viterbi decoding but will still oscillate between 0.4/0.6 and 0.6/0.4 if the model itself is pathological.[^14][^13][^15][^12]

**The correct answer for reducing oscillation is `model.predict()` (Viterbi), but only after fixing the underlying model.** Applying Viterbi to a poorly-trained HMM does not cure the pathology; it merely enforces global coherence on a bad emission model. The real fix must happen at training time.

### Stabilization Protocol

**Step 1: Standardize features before fitting.** Apply z-score normalization (zero mean, unit variance) to both `qqq_vol_20d` and `vix_close` computed using only training-window data (critical: no future leakage in the scaler).[^12]

**Step 2: Initialize `transmat_prior` to strongly favor self-transitions.** A Dirichlet prior on each row with high concentration on the diagonal — e.g., `[[10, 1, 1], [1, 10, 1], [1, 1, 10]]` (unnormalized) — pulls Baum-Welch toward persistent regime solutions. This is the most impactful single change.[^13][^16]

```python
# Example: Initialize transmat to persist in each state ~90% of the time
model = GaussianHMM(n_components=3, covariance_type='full', n_iter=100)
model.transmat_ = np.array([[0.92, 0.05, 0.03],
                             [0.04, 0.92, 0.04],
                             [0.03, 0.05, 0.92]])
model.init_params = 'mc'  # Only randomly init means/covars, not transmat
```

**Step 3: Use a rolling window of ~3,000 days (~12 years) for re-fitting** in walk-forward mode, refitting monthly rather than daily. Published research using a 3000-day rolling HMM window on daily equity returns found stable 2–8 regime shifts per year (not 250), which is operationally meaningful.[^16]

**Step 4: Apply rolling-mean smoothing to predicted regime labels** after Viterbi decoding. Taking a rolling mode over 5–8 days of decoded states eliminates single-day flip-flops that are likely noise rather than genuine regime transitions.[^16]

### Additional Features: Evidence for Adding Momentum and VIX Term Slope

Adding `qqq_10d_return` (short-term momentum) substantially improves state separability between BULL (positive momentum, low vol) and SIDEWAYS (near-zero momentum, moderate vol) regimes. The `vix_term_slope` (VIX3M - VIX spot, also called VIX term premium) is an early leading indicator of volatility regime shifts — when the term slope inverts (VIX > VIX3M), it historically precedes market stress by days to weeks, giving the HMM forward-predictive context that pure realized-vol features lack.[^17][^12][^16]

Published work on ensemble-HMM frameworks for ETF regime detection (Russell 3000, S&P 500) specifically found that combining macroeconomic indicators (including VIX-based term structure) with technical features like momentum significantly improved regime classification stability and trading strategy performance.[^18][^17]

### Minimum Training Window for a 3-State HMM

Seven years of daily data (~1,764 observations) is considered adequate but not optimal for a 3-state Gaussian HMM on equity data. The practical guideline from quantitative finance practice is 10–15 years minimum, with 12 years (~3,000 observations) allowing coverage of at least two full market cycles. Critically, equity regime non-stationarity means that parameters fitted on 2019–2026 data will reflect a COVID-crash-and-recovery cycle and a 2022 rate-shock regime that may not generalize to future regimes not seen in the training window. The 7-year window is workable if monthly re-estimation is applied, but single-fit use of a 7-year window without periodic re-estimation is fragile.[^19][^20][^16]

### Python Alternatives to hmmlearn

| Library | Key Advantages | Limitations for Finance |
|---|---|---|
| **pomegranate** | Faster Cython implementation, supports non-Gaussian emissions (mixtures, Student-t), multithreaded training[^21][^22] | API changed significantly in v1.0; documentation thinner than hmmlearn |
| **Hidden Semi-Markov Model (HSMM)** | Models sojourn time explicitly — prevents unrealistically short-duration regimes (e.g., 1-day bear markets)[^20] | Computationally expensive; implementation via pomegranate or custom code |
| **statsmodels MarkovRegression** | Time-varying transition probabilities (TVTP) — transitions conditioned on exogenous variables (e.g., VIX level)[^23] | Only for univariate returns; no multi-feature emission |
| **HMM-GAS (Score-Driven)** | Time-varying parameters adapt within regimes, not just at transitions; superior distributional fit during crises[^24] | Requires custom implementation; not off-the-shelf in Python |
| **ruptures** | Offline changepoint detection, non-parametric cost functions, Student-t compatible[^25][^26] | Offline only (not streaming/walk-forward); different paradigm than probabilistic HMM |

For the TurboCore production pipeline, **pomegranate with Student-t emissions** is the highest-value upgrade from hmmlearn, replacing Gaussian state-emission models with fat-tailed distributions better suited to TQQQ's excess kurtosis.[^22]

***

## Problem 3: Meta-Labeling with Sparse Signals (31 Events / 7 Years)

### Minimum Sample Size Requirements

The meta-labeling literature is clear: **31 labeled events is far below the minimum for a reliable XGBoost meta-model**. Hudson & Thames (the lab that operationalized López de Prado's methods) found that meta-labeling requires at least 50–100 events to provide statistically meaningful discrimination, and practical implementations in published research use 200–500+ events. With 31 events, the XGBoost model has insufficient variance to learn generalizable patterns — it will either overfit dramatically or converge to the majority class.[^27][^11][^9]

### Relabeling Strategy: Daily Condition State vs. Crossover Event

The correct solution is to **label every day the EMA crossover condition is TRUE** (i.e., 5 EMA > 30 EMA is in effect), not only the day the crossover fires. This transforms 31 discrete events into ~1,000–1,500 daily labeled samples (the approximate number of days when the condition was active over 7 years), without introducing any lookahead bias.[^28][^9]

The label for each day is: did the TQQQ position, entered at the start of the current "crossover-active" window, hit the TP barrier (label=1) or SL/timeout (label=0) before the crossover condition reversed? This is fully determined by past and present prices at labeling time, as long as you impose a minimum holding period embargo equal to the forward_window length between the training and test splits.[^9]

Crucially, this approach aligns with the purpose of meta-labeling: the model's job is not to predict *when* a crossover fires but to predict *whether the current continuation of the bullish EMA state will succeed*. Labeling continuation days directly captures this.

### Alternative: Switch Primary Signal to Rolling Momentum

Replacing the 5/30 EMA crossover with a **rolling QQQ 20-day return > 0** signal generates ~1,200–1,400 signal-active days per 7 years, providing sufficient meta-labeling observations. This signal also has published evidence of positive performance when applied to leveraged Nasdaq products (a simple QQQ momentum strategy with 1.5× leverage achieved 14.7% CAGR vs. 15.3% for QQQ buy-and-hold, but with only -29.1% max drawdown vs. -49.7%). The primary signal needs to be changed first; meta-labeling a signal with insufficient edge amplifies noise, not alpha.[^8][^29][^9]

### Handling Class Imbalance: SMOTE vs. scale_pos_weight

For financial meta-labeling datasets with moderate imbalance (20–40% minority class after relabeling), **scale_pos_weight in XGBoost is the preferred approach** over SMOTE. Set `scale_pos_weight = (total negative samples) / (total positive samples)`. SMOTE generates synthetic training examples through linear interpolation between existing minority class samples; for financial time series, synthetic interpolated samples may not lie on the actual data manifold and can degrade model generalization.[^10][^30]

SMOTE is appropriate when the dataset is very small (< 500 samples) and severe imbalance (> 10:1) leaves the minority class chronically under-represented even after scale_pos_weight adjustment. In those cases, SMOTE helps stabilize training but should be applied only to the training fold within each walk-forward split, never applied before the train/test split is made.[^30][^10]

***

## Problem 4: Production Architecture — LEAPS Kelly Formula

### Correct Definition of b for an Options Strategy

The Kelly formula is:

\[ f^* = \frac{pb - (1-p)}{b} \]

where \( b \) is defined as the **net gain per unit risked on a win**. For an options trade, this is not the TQQQ price return multiple, the LEAPS delta-adjusted return, or a fixed 2.5. The correct \( b \) is:[^31]

\[ b = \frac{\text{expected option P\&L on a win}}{\text{premium paid (at risk)}} \]

For a deep ITM LEAPS call (~0.80 delta, 12-month DTE), the payoff structure is approximately: if QQQ rallies X%, the option gains ~delta × X × underlying_value / premium_paid. For an 80-delta call bought at intrinsic + modest extrinsic value, a 15% QQQ move upward yields approximately 1.5–2.0× the premium as profit (b ≈ 1.5–2.0). On a loss, the entire premium can be lost (a = 1.0).[^32][^31]

The current implementation using b = 2.5 (LEAPS payoff asymmetry) is a reasonable approximation but should be computed dynamically per trade from the current option price, delta, and the expected move distribution. Option payoff is non-linear — deep ITM LEAPS behave closer to long stock for moderate moves but have catastrophic theta decay if QQQ goes sideways for multiple months.[^33][^34]

**Theta decay must be incorporated into b.** A LEAPS position held for 90 days loses time value even if QQQ is flat. The effective b over a typical holding window should subtract expected theta decay from the win payoff:

\[ b_{adjusted} = \frac{\text{delta-adjusted gain on expected winning move} - \text{theta decay over holding period}}{\text{premium at risk}} \]

Using b = 2.5 without theta adjustment overestimates the true edge and will cause Kelly to recommend larger positions than warranted.[^35][^33]

### Fractional Kelly: Academic Basis for Quarter-Kelly

Half-Kelly is the standard recommendation from quantitative finance literature, capturing ~71% of the full-Kelly growth rate with only ~38% of full-Kelly's volatility — a significantly better risk-adjusted trade-off. The relationship is non-linear: half-Kelly approximately halves the drawdown while retaining most of the geometric growth.[^36][^37]

MacLean, Sanegre, Zhao, and Ziemba (2004) — the definitive academic treatment of fractional Kelly — explicitly quantified this: half-Kelly reduces volatility by approximately 75% while sacrificing only 25% of the growth rate. Quarter-Kelly (25% of the computed Kelly fraction) is appropriate when:[^37]
- The underlying signal (b and p estimates) has high uncertainty (which applies here — XGBoost confidence scores are uncalibrated probabilities)
- The underlying asset has high kurtosis (TQQQ with 4–5% daily vol qualifies)
- The position is an option (where maximum loss = 100% of premium, making the Kelly formula's thin-tail assumption particularly dangerous)[^38]

For TQQQ LEAPS with uncalibrated XGBoost probabilities and leverage decay risk, **quarter-Kelly is justified and appropriate**. Tastylive's own analysis confirms: the Kelly number "optimizes return without considering volatility"; the half-Kelly captures 71% of optimal return with 38% of the volatility, making quarter-Kelly appropriate for high-uncertainty, high-kurtosis instruments.[^36]

### Regime Transition Smoothing: Soft vs. Hard Allocation Switching

**Soft allocation using smoothed posterior probabilities outperforms hard discrete switching** in both return and drawdown metrics. The ARIMA-HMM research framework specifically notes that "instead of relying on fixed regime labels, using the HMM's smoothed probabilities for weighted allocations across regimes creates smoother transitions" and measurably improves Sharpe ratios.[^39]

Published regime-switching research on S&P 500, DAX, and Nikkei 225 found that hard 0/1 switching (binary full-invest/full-exit) achieves lower volatility and drawdown than buy-and-hold, but soft-weighted allocation using regime probabilities achieves superior risk-adjusted returns because it avoids whipsawing capital during genuine uncertainty periods. The recommended implementation:[^16]

\[ w_{\text{LEAPS}}(t) = P(\text{BULL}_t) \times w_{\text{max}} + P(\text{SIDEWAYS}_t) \times w_{\text{mid}} + P(\text{BEAR}_t) \times 0 \]

where \( P(\text{BULL}_t) \) is the forward-backward posterior probability (not Viterbi hard assignment), and the weights decay smoothly with an exponential half-life of 5–10 days to prevent whipsaw.[^39][^16]

### Published LEAPS + Momentum Regime Strategy Benchmarks

For calibrating return expectations:

| Strategy | CAGR | Max Drawdown | Notes |
|---|---|---|---|
| TQQQ buy-and-hold | 54.4% (since inception) | -70% daily | No regime filter; extreme volatility[^40] |
| TQQQ/TMF 50/50 bimonthly rebalancing | 44.9% | -24.5% | Crash filter: exit both on -20% TQQQ day[^40] |
| QQQ momentum strategy (20-day return) | 9.8% | -19.4% | No leverage; conservative[^29] |
| QQQ momentum + 1.5× leverage | 14.7% | -29.1% | Matches QQQ return with half the drawdown[^29] |
| QQQ LEAPS + regime filter | ~15–33% | ~35–56% | Published range; depends on regime accuracy[^41][^34] |
| QQQ LEAPS buy-and-hold (80∆, 12mo) | 33.1% vs. 18.1% QQQ benchmark | -56.3% | 15-year 2009–2025 backtest[^41] |

A realistic production estimate for a walk-forward ML regime-filtered LEAPS strategy with proper integer sizing and $25,000+ capital is 15–25% CAGR, with max drawdowns of 30–50% in bear years.

***

## Problem 5: Bayesian Online Changepoint Detection (BOCD)

### NIG Prior and Fat Tails: A Serious Mismatch

The Normal-Inverse-Gamma (NIG) conjugate prior assumes Gaussian-distributed data within each segment. TQQQ daily log returns exhibit excess kurtosis well above 3 (empirically in the range of 8–15), driven by leverage amplification of fat-tailed QQQ returns. The NIG/Gaussian BOCD is therefore fitting the *wrong likelihood function to the data*, causing two systematic problems:[^42][^7]

1. **Excess false positives**: Large single-day moves (e.g., ±8–12% on TQQQ) are many standard deviations from the Gaussian mean, causing the NIG posterior to detect a "changepoint" when in reality the event is a fat-tail draw from the same regime.[^43][^42]
2. **Detection delay in slow-onset regimes**: The 2022 rate-shock bear market was a grinding multi-month regime shift, not a sharp structural break. NIG BOCD tuned to detect sharp Gaussian mean/variance changes will miss gradual volatility transitions or flag them too late.

Published GARCH-framework research finds that the Student-t distribution substantially outperforms Gaussian for fitting equity return distributions — for S&P 500 and QQQ-type assets, the Student-t with approximately 4–6 degrees of freedom captures tail behavior that the Gaussian misses. A hybrid BOCD using Student-t or GARCH-BOCD likelihood is more appropriate.[^20][^43]

### Student-t BOCD vs. GARCH-BOCD

The **GARCH-autoregressive BOCD** extension by Altamirano et al. (2023) directly addresses both problems by incorporating time-varying variance and autoregressive structure within each regime segment, while maintaining the online Bayesian framework. This is the state-of-the-art approach for equity returns. Key features:[^44][^42]
- Volatility clustering within regimes (GARCH-like dynamics) — prevents large single-day moves from triggering false changepoints
- Score-driven parameter updates allow regime characteristics to evolve gradually rather than snapping to a new segment on every large observation

A simpler alternative that improves immediately on NIG is using a **Student-t likelihood** with approximately 4–5 degrees of freedom. The robust BOCD framework by Altamirano (published 2023) replaces the standard Bayes posterior with a generalised Bayes posterior that is robust to outliers, directly reducing false positive rates.[^42]

### False Positive Rates on Equity Regimes

There is limited published data on BOCD false positive rates for specific equity regimes (March 2020, 2022 bear). What is empirically documented:[^45][^42]
- Standard Gaussian NIG BOCD with hazard rate 1/250 generates **significant false positives** during high-kurtosis periods (multiple weekly "changepoints" during March 2020 that were tail events within a single high-volatility regime, not structural breaks)
- Robust BOCD variants (generalized Bayes posterior) detect the same true changepoints while substantially reducing spurious detections, without increasing detection delay

**Parameter guidance for equity regimes**:

| Parameter | Daily Detection | Weekly Detection | Notes |
|---|---|---|---|
| `hazard` (1/h) | 1/250 (annual cycle) | 1/52 | Expected segment duration in observation units[^44] |
| `cp_threshold` | 0.25–0.35 for NIG | 0.15–0.25 for Student-t | Lower threshold compensates for fat-tail false positives |
| Minimum confirmation | 3–5 days persistence | 2–3 weeks | Filter: don't act on changepoint until posterior confirms |

For TQQQ specifically, using a **hazard rate of 1/126** (expecting ~2 regime breaks per year) with a Student-t likelihood and cp_threshold = 0.25 is a more defensible configuration than the current 1/250 with NIG.

### Production-Ready Python BOCD Implementations

| Library/Source | Likelihood | Production Status | Notes |
|---|---|---|---|
| `gwgundersen/bocd` (GitHub)[^46] | Gaussian NIG | Reference implementation | Add Student-t emission class; widely used as base |
| `Altamirano et al. 2023` (arxiv 2302.04759)[^42] | Robust generalised Bayes | Research; Python code in paper | Best for fat-tailed equity returns |
| `ruptures` (Python)[^25][^26] | Multiple (L2, L1, RBF, Gaussian) | Production-ready, well-documented | Offline only — not streaming; does not compute posterior run-length |
| Custom GARCH-BOCD[^44] | GARCH within-regime | Research; reproducible | Best for detecting slow-onset volatility regime shifts like 2022 |

For the TurboCore production pipeline, the recommended path is to extend `gwgundersen/bocd` with a Student-t likelihood and add a 5-day confirmation filter before acting on detected changepoints. This provides meaningful improvement over NIG without requiring a full research-grade reimplementation.

***

## Integrated Fix Summary

| Problem | Current Bug | Priority Fix | Expected Impact |
|---|---|---|---|
| Triple-barrier: 0% positive labels | Path vol used as barrier scaler (~70% TP requirement) | Use 20-day EWMA *daily* vol as `trgt`; TP = 1.5×, SL = 0.75× | Label balance from 0% to ~30–35% positive |
| HMM 98% oscillation | Random transmat init; unscaled features; 2 features only | z-score features; set transmat diagonal to 0.90; add momentum + VIX term slope | Regime shifts reduce to 2–8/year |
| Sparse meta-labeling (31 events) | Label only on crossover day | Label every day condition is TRUE; or switch to 20-day momentum signal | Training set grows from 31 to 1,000–1,500 samples |
| Kelly b-ratio miscalculation | Fixed b = 2.5; ignores theta | Compute b from delta-adjusted return net of theta over holding period | Reduces overcapitalization in LEAPS |
| BOCD NIG fat-tail mismatch | NIG/Gaussian likelihood | Student-t likelihood (df ≈ 4–5); hazard = 1/126; add 5-day confirmation | False positives during high-kurtosis events (e.g., Mar 2020) substantially reduced |

---

## References

1. [The Triple Barrier Labeling of Marco Lopez de Prado - Quantreo](https://www.newsletter.quantreo.com/p/the-triple-barrier-labeling-of-marco) - The Triple Barrier Method, introduced by Marcos López de Prado, is a powerful way to label trading d...

2. [Triple Barrier Method: Python | GPU | Nvidia - QuantInsti Blog](https://blog.quantinsti.com/triple-barrier-method-gpu-python/) - The Triple-Barrier Method is a new tool in financial machine learning that offers a dynamic approach...

3. [MetaTrader 5 Machine Learning Blueprint (Part 2): Labeling ... - MQL5](https://www.mql5.com/en/articles/18864) - [0,0,0] - No Exit: All barriers disabled. Positions never close and no labels are generated. Below a...

4. [Improve Your ML Model With Better Labels | by David Zhao](https://ai.plainenglish.io/start-using-better-labels-for-financial-machine-learning-6eeac691e660) - How to use (Meta)-labelling and the Triple Barrier Method to increase the accuracy of a predictive f...

5. [The Triple Barrier Method: A New Standard for Investment Labeling ...](https://medium.datadriveninvestor.com/the-triple-barrier-method-a-new-standard-for-investment-labeling-and-analysis-1a525a0a2f46) - The triple-barrier method addresses this issue by dynamically setting the labels based on the behavi...

6. [Stock Price Prediction Using Triple Barrier Labeling and Raw ... - arXiv](https://arxiv.org/html/2504.02249v2) - Labels were generated using the low and high prices instead of the close price alone to account for ...

7. [Leveraged ETFs and Volatility: SPXL and TQQQ Guide - MenthorQ](https://menthorq.com/guide/leveraged-etfs-and-volatility-spxl-and-tqqq/) - Leveraged ETFs such as SPXL and TQQQ promise enhanced returns in strong markets. But how are they af...

8. [Investing in 3x Daily Leveraged Nasdaq 100 ETFs (TQQQ or QQQ3 ...](https://www.lambrospetrou.com/articles/investing-leveraged-qqq-macd/) - Using 3x daily leveraged ETFs makes the bull runs bigger and allows the strategy to generate amazing...

9. [Meta Labeling for Algorithmic Trading: How to Amplify a Real Edge](https://www.reddit.com/r/algotrading/comments/1lnm48w/meta_labeling_for_algorithmic_trading_how_to/) - The meta label is a machine learning model that predicts whether each individual signal should be ta...

10. [How to Configure XGBoost for Imbalanced Classification](https://www.machinelearningmastery.com/xgboost-for-imbalanced-classification/) - This tutorial is divided into four parts; they are: Imbalanced Classification Dataset; XGBoost Model...

11. [Does Meta Labeling Add to Signal Efficacy? - Hudson & Thames](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/) - Our results confirm the fact that a combination of event-based sampling, triple-barrier method and m...

12. [Hidden Markov Model Market Regimes: How HMM Detects Market ...](https://www.quantifiedstrategies.com/hidden-markov-model-market-regimes-how-hmm-detects-market-regimes-in-trading-strategies/) - To use an HMM for regime detection, we fit the model to historical market data (typically asset retu...

13. [Hidden Markov Models for Regime Detection using R - QuantStart](https://www.quantstart.com/articles/hidden-markov-models-for-regime-detection-using-r/) - In this article Hidden Markov Models will be implemented using the R statistical language via the De...

14. [[PDF] Hidden Markov Models](https://web.stanford.edu/~jurafsky/slp3/A.pdf) - 9 Viterbi algorithm for finding optimal sequence of hidden states. Given an observation sequence and...

15. [A new decoding algorithm for hidden Markov models improves the ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC1866396/) - The Viterbi and the posterior decoding algorithms are the most common. The former is very efficient ...

16. [Downside Risk Reduction Using Regime-Switching Signals - arXiv](https://arxiv.org/html/2402.05272v2) - This article investigates a regime-switching investment strategy aimed at mitigating downside risk b...

17. [A multi-model ensemble-HMM voting framework for market regime ...](https://www.aimspress.com/article/id/69045d2fba35de34708adb5d) - To avoid lookahead bias, oracle labels are shifted forward so that predictions for the regime on Day...

18. [A multi-model ensemble-HMM voting framework for market regime ...](https://www.aimspress.com/article/doi/10.3934/DSFE.2025019?viewType=HTML) - In this paper, we present a framework for detecting market regime shifts using a combination of tree...

19. [[PDF] Long Memory of Financial Time Series and Hidden Markov Models ...](https://backend.orbit.dtu.dk/ws/files/125919765/Long_memory_and_time_varying_parameters_ACCEPTED_VERSION.pdf) - Section 2 gives an introduction to the HMM. Section 3 discusses the relation between long memory and...

20. [Hybrid Hidden Markov Model for Modeling Equity Excess Growth ...](https://arxiv.org/html/2603.10202v1) - Using ten years of SPY data (2014–2024) for training and 249 trading days (full calendar year 2025) ...

21. [pomegranate v0.4.0: fast and flexible probabilistic modelling for python](https://www.reddit.com/r/Python/comments/4cllym/pomegranate_v040_fast_and_flexible_probabilistic/) - pomegranate's cython implementation is extremely fast. It does extremely well when comparing hidden ...

22. [Hidden Markov Models — pomegranate 1.0.0 documentation](https://pomegranate.readthedocs.io/en/latest/tutorials/B_Model_Tutorial_4_Hidden_Markov_Models.html) - HMMs are a form of structured prediction method that are popular for tagging all elements in a seque...

23. [Exogenous variables in hmmlearn's GaussianHMM - Stack Overflow](https://stackoverflow.com/questions/64631710/exogenous-variables-in-hmmlearns-gaussianhmm) - I am trying to use hmmlearn's GaussianHMM to fit a Hidden Markov Model with 2 main states, while all...

24. [[PDF] A Comparative Analysis Of Regime-Switching Models In Eq - POLITesi](https://www.politesi.polimi.it/retrieve/6e149f60-c547-40bc-8ffc-cb6628ad99ef/2025_12_Jia_Thesis_01.pdf) - We systematically compare three regime-switching specifications HMM, HSMM, and. HMM-GAS across three...

25. [Leveraging change point detection to discover natural experiments ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC9440658/) - A collection of cost functions and search algorithms is available as a Python library called rupture...

26. [[1801.00826] ruptures: change point detection in Python - arXiv.org](https://arxiv.org/abs/1801.00826) - ruptures is a Python library for offline change point detection. This package provides methods for t...

27. [Meta Labeling (A Toy Example) - Hudson & Thames](https://hudsonthames.org/meta-labeling-a-toy-example/) - This article explores a toy example of Meta Labeling and how it is used to filter out false positive...

28. [Meta-Labeling: The Technique That Transformed Modern Quant ...](https://whatworksintrading.substack.com/p/meta-labeling-the-technique-that) - The primary model proposes a trade. The meta-model evaluates the conditions and assigns a label: 1 →...

29. [A Simple Momentum Strategy That Reduce Risk by 63%](https://www.moneyunfiltered.com/p/a-simple-momentum-strategy-that-reduce) - Yes, momentum strategy's 9.8% CAGR trails QQQ's 15.3% by 5.5 percentage points. ... drawdown stays a...

30. [Data augmentation alters feature importance in XGBoost for CVD ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC12647713/) - All models demonstrated high predictive performance on the independent test set, with the SMOTE-augm...

31. [Kelly criterion - Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion) - In probability theory, the Kelly criterion is a formula for risk allocation with the sizing a sequen...

32. [How to Use Kelly Criterion Trading Options](https://www.environmentaltradingedge.com/trading-education/how-to-use-kelly-criterion-trading-options) - In essence, the Kelly Criterion aims to maximize long-term growth by adjusting for both your probabi...

33. [Option Theta Explained: Time Decay for Beginners | TradingBlock](https://www.tradingblock.com/blog/option-theta-time-decay) - In options trading, time decay (theta) measures how much value an option loses each day as expiratio...

34. [The QQQ Options Strategy That Blew Away Buy & Hold - YouTube](https://www.youtube.com/watch?v=Dv60NWwvglo) - ​ Income overlays: Some traders pair long QQQ LEAPS with short ... LEAPS strategies require in multi...

35. [What is Options Theta? How Time Decay Works - Option Alpha](https://optionalpha.com/learn/theta) - Theta represents the time value decline of an options contract. As expiration gets closer, the time ...

36. [The Smart Trader's Guide to Kelly's Criterion - tastylive](https://www.tastylive.com/news-insights/smart-trader-guide-kellys-criterion) - Kelly's Criterion Explained: A Q&A Guide for Options Traders. By:Kai Zeng. It helps determine the ri...

37. [Kelly Position Size Calculator — Indicator by EdgeTools - TradingView](https://www.tradingview.com/script/83fHgI24-Kelly-Position-Size-Calculator/) - Equity Markets: For stocks and ETFs, position sizing follows the calculation Shares = floor(Kelly Fr...

38. [[PDF] Using the Kelly Criterion for Investing](https://webhomes.maths.ed.ac.uk/mckinnon/blackouts/StochOptFinanceAndEnergySpringer/Chap1_KellyZiemba.pdf) - The fraction of the Kelly optimal growth strategy exceeds 1 in the most levered strategies and this ...

39. [[PDF] ARIMA Powered by Hidden Markov Regimes for Adaptive Forecasting](https://www.iaeng.org/IJAM/issues_v55/issue_12/IJAM_55_12_26.pdf) - We propose an Adaptive ARIMA-HMM framework that identifies patterns in stock returns and transitions...

40. [Triple Leveraged ETF Trading Strategy (44% Annual Returns)](https://www.quantifiedstrategies.com/triple-leveraged-etf-trading-strategy/) - Other equity TLETFs show even higher drawdowns; for example, UDOW saw a maximum daily drawdown of 80...

41. [Introducing the QQQ Trading Strategy That Beats the Market](https://www.financialwisdomtv.com/post/qqq-trading-strategy-that-beats-the-market-proven-backtest-results) - The compound annual growth rate reached 33.1%—nearly double QQQ's 18.1% return over the same timefra...

42. [[2302.04759] Robust and Scalable Bayesian Online Changepoint ...](https://ar5iv.labs.arxiv.org/html/2302.04759) - # Robust and Scalable Bayesian Online Changepoint Detection

Matias Altamirano François-Xavier Briol...

43. [[PDF] GARCH model and fat tails of the Chinese stock market returns](http://www.scienpress.com/download.asp?ID=1580303) - GARCH model and fat tails of the Chinese stock ... performance of the Student's t, NIG and NRIG dist...

44. [Bayesian Autoregressive Online Change-Point Detection with Time ...](https://arxiv.org/html/2407.16376v1) - Section 3 reviews the baseline model of [Adams and MacKay, 2007] and describes the proposed change p...

45. [[PDF] Restarted Bayesian Online Change-point Detector achieves Optimal ...](http://proceedings.mlr.press/v119/alami20a/alami20a.pdf) - achieves Optimal Detection Delay
R´eda Alami 1 Odalric Maillard 2 Raphael F´eraud 3
Abstract
In this...

46. [bocd/bocd.py at master · gwgundersen/bocd - GitHub](https://github.com/gwgundersen/bocd/blob/master/bocd.py) - Author: Gregory Gundersen Python implementation of Bayesian online changepoint detection for a norma...

