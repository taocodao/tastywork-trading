# Prompt for Perplexity: Diagnosing Failed ML Strategy Enhancements

Please act as a senior quantitative researcher and machine learning engineer at a top-tier systematic hedge fund diagnosing a failed model deployment.

## Context
We are managing "TurboCore Pro," a hybrid equity strategy that dynamically rotates capital between QQQ, QLD, QQQ LEAPS, and SGOV based on Market Regime (HMM) and Signal Confidence (XGBoost). Our baseline strategy, using just basic EMA crossovers and broad regime matrix rules, achieved a **29.60% CAGR** over a 2010–2026 backtest.

To push returns into the 40%+ range, we implemented "Phase 1 & 2" of a newly designed MLOps architecture:
1. **Triple-Barrier Meta-Labeling:** We moved away from a static 6% target. Instead, we label 20-day forward paths as profitable (1) or unprofitable (0) based on hitting a dynamic Take-Profit (+2x path volatility) before a Stop-Loss (-1x path volatility).
2. **Macro & Breadth Features:** We added `vol_ratio` (5-day vs 20-day volume), `vix_term_slope` (VIX3M - VIX / VIX), and `hyg_5d_change` to help XGBoost detect "fake-out" dead cat bounces.

**The Problem:**
After fully implementing these structural changes, training the model, and running the same 16-year backtest, our Annualized Return stubbornly remained exactly the same as before (~29.60%). The ML enhancements appear to have had effectively zero marginal impact on the strategy's PnL.

## THE QUESTION FOR PERPLEXITY
Why would implementing Triple-Barrier Meta-Labeling and adding canonical "fakeout detection" macro features result in zero performance improvement, and how do we quantitatively debug this? 

Please provide a highly technical analysis covering the following four areas:

### 1. The "Masked Signal" Problem (Architecture)
Is it common for complex meta-labeling to get "washed out" in long-term position management? Our XGBoost model outputs a confidence score (0 to 1) that maps to LEAPS allocation size in our matrix. If the HMM regime (BULL, SIDEWAYS, BEAR) dominates the matrix logic, does the XGBoost micro-signal mathematically lose its alpha? How should we restructure the interaction between Regime (HMM) and Trade Confidence (XGBoost) so the ML actually impacts the equity curve?

### 2. Triple Barrier Calibration for Macro Trends
Our pseudo-Triple Barrier approach looks 20 days ahead, evaluating if price hits +2x path_vol before -1x path_vol. If neither is hit within 20 days, it times out (class 0). 
* Are these barrier widths (+2 / -1) and time horizons (20 days) completely mismatched for a strategy whose goal is allocating into long-term LEAPS holding periods (which might last 6-12 months)? 
* How should Triple Barrier parameters (tp_mult, sl_mult, forward_days) be calibrated for a core-satellite trend-following system rather than a high-frequency mean-reversion bot?

### 3. Feature Toxicity and Stationarity Breakdown
Features like `hyg_5d_change` and `vix_term_slope` are standard macro leading indicators, but we fed them "raw" into XGBoost alongside technicals (RSI, MACD). 
* Do daily macro features typically act as "noise" in a decision tree model unless they are aggregated, lagged, or fractionally differenced? 
* What is the exact mathematical preprocessing required to make HYG credit spreads and VIX term structure actually predictive for a daily decision tree?

### 4. Code-Level Diagnostic Tests
As a Quant Developer, I need to know exactly why the XGBoost output didn't change the portfolio. What are the top 3 quantitative diagnostic tests (e.g., specific SHAP visualizations, ROC-AUC across Regimes, or Signal/Noise distribution plots) I must write right now in Python to mathematically prove why the model is failing to add Alpha? Please provide the conceptual Python code for these diagnostics.
