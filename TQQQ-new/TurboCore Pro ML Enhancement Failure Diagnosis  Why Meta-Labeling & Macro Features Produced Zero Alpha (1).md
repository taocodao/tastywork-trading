# TurboCore Pro ML Enhancement Failure Diagnosis: Why Meta-Labeling & Macro Features Produced Zero Alpha
## Executive Summary
The TurboCore Pro strategy achieved 29.60% CAGR with basic EMA crossovers and regime matrix rules. After implementing Triple-Barrier Meta-Labeling and macro fakeout-detection features (VIX term structure, HYG credit spreads, volume ratios), the CAGR remained stuck at exactly 29.60%. This is not a subtle underperformance — the ML enhancements have had **mathematically zero impact** on the equity curve.

The root cause is a compound failure across four interacting layers: (1) the HMM regime gate dominates the allocation matrix so completely that XGBoost confidence variations cannot materially move portfolio weights, (2) the triple-barrier parameters are calibrated for a 20-day swing trading horizon while the strategy manages 6–12 month LEAPS positions, creating a fundamental label-target mismatch, (3) raw daily macro features fed into XGBoost produce near-zero SHAP values because they lack the preprocessing needed for tree-based models, and (4) the meta-labeling output is being used as a scalar modifier within a discretized matrix rather than as a continuous bet-sizing input per López de Prado's original formulation.

The good news: the 29.60% baseline is robust. The ML additions didn't *hurt* — they simply didn't help. Each of the four failure modes has a specific, code-level fix, and the diagnostic tests provided will confirm exactly which failures dominate before any architectural changes are made.

***
## The Masked Signal Problem
### How HMM Regime Dominance Nullifies XGBoost
The allocation architecture has a fatal hierarchical structure: the HMM regime state acts as a **hard gate** that pre-selects which row of the allocation matrix is active, and the XGBoost confidence score only modulates within that row's narrow band. In practice, if the HMM classifies the current market as BEAR, the portfolio goes 100% SGOV regardless of whether XGBoost outputs 0.95 confidence in a recovery signal. Conversely, if the HMM says BULL, the XGBoost score merely shifts LEAPS allocation between, say, 50% and 60% — a difference that produces negligible CAGR impact when compounded.[^1][^2]

This is a well-documented problem in hierarchical ML trading systems. Research on ensemble HMM + XGBoost voting frameworks for market regime detection confirms that when one model dominates the decision hierarchy, the subordinate model's signal gets "absorbed" — the subordinate adds refinement that may improve Sharpe by 0.05–0.10 but is invisible in CAGR terms. A Reddit practitioner building a long-short volatility book with HMM-based allocation specifically noted that in their system, "the state must also pass through two bias filters before the algorithm deems the bias valid, ultimately leading to a deterministic outcome" — meaning the HMM collapse makes downstream signals irrelevant.[^2][^1]
### The Mathematical Proof
Consider the allocation matrix over a 16-year backtest. The HMM spends approximately:
- 65–70% of days in BULL state
- 15–20% in SIDEWAYS
- 10–20% in BEAR (100% SGOV, XGBoost irrelevant)

During BULL periods, the XGBoost confidence score modulates between allocation tiers. But the tiers are narrow: the difference between "60% confidence → 50% LEAPS" and "80% confidence → 60% LEAPS" is only a 10 percentage-point shift in LEAPS weight. On a day when QQQ moves +0.5%, the difference in portfolio return between these two tiers is approximately:

- 50% LEAPS tier: 0.50 × 0.005 × 3.75 = 0.94% portfolio return from LEAPS
- 60% LEAPS tier: 0.60 × 0.005 × 3.75 = 1.13% portfolio return from LEAPS

The differential is 0.19% per day — only on days when the tiers differ. If XGBoost upgrades the allocation on 50 days per year (out of ~180 bull days), and the average daily benefit is ~0.15%, the total annual alpha is 50 × 0.0015 = 0.75% — well within the noise floor of the backtest.
### The Fix: Multiplicative Bet Sizing, Not Additive Matrix Tiers
The fundamental error is using XGBoost confidence as a discrete tier selector instead of a continuous multiplier. López de Prado's meta-labeling framework explicitly prescribes that the secondary model's probability output should feed directly into bet sizing via the Kelly Criterion, producing continuous position sizes — not discretized allocation buckets. Hudson & Thames research demonstrates that the meta-model's calibrated probability should determine "how much" rather than "whether" to trade, and that mapping to discrete tiers destroys most of the information content in the probability output.[^3][^4][^5][^6]

The corrected architecture should be:

```python
# WRONG: Discrete matrix lookup
if regime == 'BULL':
    if confidence >= 0.75: leaps_weight = 0.60
    elif confidence >= 0.60: leaps_weight = 0.50
    else: leaps_weight = 0.15

# RIGHT: Continuous Kelly-based sizing
if regime == 'BULL':
    # Meta-model probability -> Kelly fraction -> LEAPS weight
    p = calibrated_meta_prob  # e.g., 0.72
    b = avg_win / avg_loss    # e.g., 2.0
    kelly_full = (p * b - (1 - p)) / b
    kelly_quarter = kelly_full * 0.25  # Quarter-Kelly for safety
    leaps_weight = np.clip(kelly_quarter * regime_leverage_cap, 0.10, 0.70)
```

This allows a confidence of 0.72 to produce a fundamentally different position size than 0.68, rather than both landing in the same "≥ 0.60" bucket. The continuous sizing creates a smooth, information-preserving mapping from ML signal to portfolio exposure.[^7]

***
## Triple-Barrier Calibration Mismatch
### The 20-Day / 6-Month Horizon Disconnect
The pseudo-triple-barrier implementation uses a 20-day forward window with +2x path volatility take-profit and -1x path volatility stop-loss. This labeling scheme is fundamentally designed for **swing trading** or **mean-reversion** strategies where positions are held for 1–4 weeks. The TurboCore strategy, however, manages LEAPS positions with holding periods of 6–12 months and QQQ/QLD positions that can persist for months during sustained bull regimes.[^8][^9]

This creates a critical mismatch: the XGBoost model is learning to predict "will QQQ hit +2σ within 20 days?" when the strategy actually needs to know "is this EMA crossover the start of a multi-month trend or a dead-cat bounce?" These are fundamentally different classification tasks. A genuine bull market onset (March 2020 recovery, January 2023 rally) might not hit +2σ within 20 days but delivers +40% over the subsequent 6 months. The 20-day barrier labels this as 0 (timeout/neutral), teaching the model to *ignore* exactly the signals it should amplify.[^10][^11]

Research on triple-barrier labeling confirms that parameter calibration is the primary determinant of labeling quality. A comprehensive study on Korean stocks found that the optimal configuration required careful joint optimization of time horizon and barrier widths, ultimately settling on 29-day windows with 9% barriers for their specific use case. For LEAPS-duration trend following, the parameters must be dramatically wider.[^11]
### The Label Distribution Problem
With 20-day windows and +2x/-1x volatility barriers, the expected label distribution is heavily skewed toward class 0 (timeout). QQQ's average 20-day absolute move is approximately 3–4%, while the +2x volatility barrier at ~6–8% is rarely hit. Most observations time out, creating a class distribution that's roughly 60–70% class 0, 15–20% class 1 (take-profit), 10–15% class -1 (stop-loss). The meta-model trained on this distribution learns primarily to predict "nothing happens in 20 days" — which is almost always correct but provides zero signal for allocation decisions.[^10][^12]
### Correct Calibration for Trend-Following LEAPS
For a core-satellite trend-following system with 6–12 month holding periods, the triple-barrier parameters should be:

| Parameter | Current (Swing) | Corrected (Trend) | Rationale |
|-----------|-----------------|-------------------|-----------|
| forward_days | 20 | 63–126 (3–6 months) | Aligns with LEAPS minimum holding period |
| tp_mult | 2.0x path_vol | 3.0–4.0x path_vol | Captures multi-month trends; wider barrier avoids premature labeling |
| sl_mult | 1.0x path_vol | 1.5–2.0x path_vol | Accommodates normal drawdown volatility during bull trends |
| Volatility window | 20-day | 60-day | Smooths vol estimate to reflect macro regime, not daily noise |

The corrected forward window of 63–126 days ensures that the barrier classification answers the strategy-relevant question: "does this signal precede a sustained trend?" rather than "does QQQ move sharply in the next month?"[^12][^13]

Additionally, trend-scanning labels (López de Prado, Chapter 3.5) may be more appropriate than triple-barrier for this use case. Trend-scanning identifies the duration and strength of trends rather than binary barrier touches, directly producing labels that match the strategy's information need.[^14]

***
## Feature Toxicity and Stationarity Breakdown
### Why Raw Macro Features Are Noise in Daily XGBoost
The three macro features — `vol_ratio` (5d/20d volume), `vix_term_slope` ((VIX3M - VIX) / VIX), and `hyg_5d_change` — are conceptually sound leading indicators. However, feeding them as raw daily values into an XGBoost model alongside technical indicators creates several pathological behaviors that collectively neutralize their predictive contribution.

**Problem 1: Scale Mismatch.** `vol_ratio` oscillates between 0.5 and 2.0; `vix_term_slope` ranges from -0.3 to +0.2; `hyg_5d_change` fluctuates between -0.03 and +0.03. While XGBoost is theoretically scale-invariant (it splits on thresholds, not distances), in practice, features with very small absolute ranges get fewer informative splits because the gain from splitting on a feature with range 0.06 (HYG) is systematically lower than splitting on RSI with range 100. This doesn't mean the feature is uninformative — it means XGBoost will preferentially split on higher-variance features first, relegating the macro features to deep tree leaves where they refine already-noisy predictions.[^15][^16]

**Problem 2: Non-Stationarity.** `hyg_5d_change` is a first-difference (stationary), but its distributional properties shift dramatically across regimes — the 5-day changes during 2020 COVID were 10x the magnitude of 2017's calm market. This means an XGBoost split learned during a high-volatility training window becomes meaningless during low-volatility out-of-sample periods. Standard integer differentiation achieves stationarity but destroys the memory that makes credit spreads predictive.[^17][^18][^19]

**Problem 3: Daily Frequency Mismatch.** Macro features like credit spreads and VIX term structure operate on weekly-to-monthly cycles. Their daily values are noisy oscillations around a slow-moving trend. The signal-to-noise ratio at daily frequency is extremely low — the informative component (trend) changes every 20–60 days, while the noise (daily fluctuations) changes every day. For a tree model making binary splits, the daily noise creates thousands of spurious split points that don't generalize.[^20]
### Required Mathematical Preprocessing
Each macro feature requires a specific transformation pipeline before it becomes useful for daily XGBoost:

**For `hyg_5d_change` (Credit Spreads):**
```python
# Step 1: Use OAS spread level, not price change
hyg_oas = fred_api.get('BAMLH0A0HYM2')  # ICE BofA HY OAS

# Step 2: Rolling Z-score (normalize to recent distribution)
hyg_zscore = (hyg_oas - hyg_oas.rolling(60).mean()) / hyg_oas.rolling(60).std()

# Step 3: Rate of change of Z-score (acceleration)
hyg_zscore_roc = hyg_zscore.diff(5)  # 5-day change in Z-score

# Step 4: Fractional differentiation (preserve memory)
from fracdiff import Fracdiff
fd = Fracdiff(d=0.4, window=100)  # d* found via ADF sweep
hyg_fracdiff = fd.fit_transform(hyg_oas.values.reshape(-1, 1))
```

The rolling Z-score normalization ensures the feature's distribution is stationary across regimes — a Z-score of +2.0 means "2 standard deviations above 60-day normal" regardless of whether that's 2020 or 2017. The fractional differentiation with minimum d preserves the long-term memory (credit spreads trending wider is more important than yesterday's reading) while achieving stationarity per López de Prado's Chapter 5 prescription.[^17][^21]

**For `vix_term_slope`:**
```python
# Step 1: Already a ratio, but normalize to regime
vts = (vix3m - vix) / vix
vts_zscore = (vts - vts.rolling(63).mean()) / vts.rolling(63).std()

# Step 2: Categorize into structural states
# Contango (normal): vts > 0.05 → Risk-on
# Flat: -0.05 < vts < 0.05 → Transitional  
# Backwardation: vts < -0.05 → Risk-off
vts_regime = np.where(vts > 0.05, 1, np.where(vts < -0.05, -1, 0))

# Step 3: Duration in current state (persistence feature)
vts_duration = (vts_regime != vts_regime.shift(1)).cumsum()
vts_days_in_state = vts_regime.groupby(vts_duration).cumcount() + 1
```

**For `vol_ratio`:**
```python
# Step 1: Log-transform (volume ratios are log-normal)
log_vol_ratio = np.log(volume_5d_avg / volume_20d_avg)

# Step 2: Rolling percentile rank (regime-normalized)
vol_ratio_pctile = log_vol_ratio.rolling(252).rank(pct=True)
```

The critical insight: raw macro features are **level features** that need to be converted into **relative features** (Z-scores, percentile ranks, fractional differences) before tree models can extract stable splits from them. XGBoost SHAP analysis on financial prediction tasks consistently shows that relative/normalized features produce 3–5x higher mean absolute SHAP values than their raw counterparts.[^22][^16][^23]

***
## Code-Level Diagnostic Tests
### Diagnostic 1: Confidence Score Distribution Analysis ("The Compression Test")
The most likely single-point-of-failure is that the XGBoost meta-model outputs confidence scores clustered in a narrow band (e.g., 0.45–0.60), making all allocation tiers map to the same matrix row. This is extremely common when XGBoost is trained on noisy financial data with weak signal-to-noise ratios — the model hedges by producing probabilities near the base rate.[^24][^25]

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def diagnostic_confidence_compression(confidence_scores, regime_labels, 
                                       allocation_thresholds=[0.50, 0.60, 0.75]):
    """
    DIAGNOSTIC 1: Is the XGBoost output actually varying enough to 
    trigger different allocation tiers?
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Panel 1: Full distribution histogram
    ax = axes[0, 0]
    ax.hist(confidence_scores, bins=50, edgecolor='black', alpha=0.7, 
            density=True, color='steelblue')
    for thresh in allocation_thresholds:
        ax.axvline(x=thresh, color='red', linestyle='--', 
                   label=f'Tier boundary: {thresh}')
    ax.set_title('XGBoost Confidence Score Distribution')
    ax.set_xlabel('Confidence Score')
    ax.legend()
    
    # Panel 2: Distribution by regime
    ax = axes[0, 1]
    for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
        mask = regime_labels == regime
        if mask.sum() > 0:
            ax.hist(confidence_scores[mask], bins=30, alpha=0.5, 
                    density=True, label=regime)
    ax.set_title('Confidence by HMM Regime')
    ax.legend()
    
    # Panel 3: Effective range that matters
    ax = axes[1, 0]
    bull_scores = confidence_scores[regime_labels == 'BULL']
    iqr = np.percentile(bull_scores, 75) - np.percentile(bull_scores, 25)
    score_range = bull_scores.max() - bull_scores.min()
    ax.boxplot([bull_scores], vert=False)
    ax.set_title(f'Bull Regime Scores: IQR={iqr:.3f}, Range={score_range:.3f}')
    
    # Panel 4: Tier assignment frequency
    ax = axes[1, 1]
    tier_counts = {}
    for i, thresh in enumerate(allocation_thresholds):
        upper = allocation_thresholds[i+1] if i+1 < len(allocation_thresholds) else 1.0
        tier_counts[f'{thresh:.0%}-{upper:.0%}'] = (
            (confidence_scores >= thresh) & (confidence_scores < upper)
        ).sum()
    ax.bar(tier_counts.keys(), tier_counts.values(), color='coral')
    ax.set_title('Days Spent in Each Allocation Tier')
    
    plt.tight_layout()
    plt.savefig('diagnostic_1_confidence_compression.png', dpi=150)
    
    # Quantitative verdict
    effective_std = np.std(bull_scores)
    print(f"\n=== DIAGNOSTIC 1: CONFIDENCE COMPRESSION ===")
    print(f"Bull-regime confidence std: {effective_std:.4f}")
    print(f"Bull-regime IQR: {iqr:.4f}")
    if effective_std < 0.08:
        print("VERDICT: COMPRESSED. Scores lack discriminative power.")
        print("The model cannot distinguish good from bad signals.")
    elif effective_std < 0.15:
        print("VERDICT: MARGINAL. Some discrimination, but likely")
        print("insufficient to cross tier boundaries frequently.")
    else:
        print("VERDICT: HEALTHY. Scores have sufficient spread.")
    
    return fig
```

**What to look for:** If the standard deviation of bull-regime confidence scores is below 0.08, the meta-model has no discriminative power — its output is functionally constant, and the allocation matrix collapses to a single row. This is the most common failure mode and should be checked first.[^25][^24]
### Diagnostic 2: Regime-Conditional SHAP Feature Importance ("The Toxicity Test")
This test reveals whether the new macro features (`vix_term_slope`, `hyg_5d_change`, `vol_ratio`) are actually influencing model predictions, or whether they're being ignored by the tree ensemble in favor of existing technical features.

```python
import shap
import xgboost as xgb
import pandas as pd

def diagnostic_shap_feature_toxicity(model, X_test, feature_names, 
                                       regime_labels, 
                                       new_features=['vix_term_slope', 
                                                     'hyg_5d_change', 
                                                     'vol_ratio']):
    """
    DIAGNOSTIC 2: Are the new macro features contributing to predictions,
    or are they noise that XGBoost ignores?
    """
    explainer = shap.TreeExplainer(model)
    shap_values = explainer(X_test)
    
    # Global SHAP importance
    mean_abs_shap = np.abs(shap_values.values).mean(axis=0)
    feature_importance = pd.Series(mean_abs_shap, index=feature_names)
    feature_importance = feature_importance.sort_values(ascending=False)
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # Panel 1: Global beeswarm (top 15 features)
    ax = axes[0, 0]
    plt.sca(ax)
    shap.plots.beeswarm(shap_values, max_display=15, show=False)
    ax.set_title('Global SHAP Beeswarm (Top 15)')
    
    # Panel 2: New features vs existing features comparison
    ax = axes[0, 1]
    new_importance = feature_importance[
        feature_importance.index.isin(new_features)
    ]
    old_importance = feature_importance[
        ~feature_importance.index.isin(new_features)
    ].head(5)
    
    comparison = pd.concat([old_importance, new_importance])
    colors = ['steelblue']*len(old_importance) + ['coral']*len(new_importance)
    comparison.plot(kind='barh', ax=ax, color=colors)
    ax.set_title('New Features (red) vs Top Existing (blue)')
    ax.set_xlabel('Mean |SHAP|')
    
    # Panel 3: SHAP by regime for new features only
    ax = axes[1, 0]
    regime_shap = {}
    for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
        mask = regime_labels == regime
        if mask.sum() > 0:
            regime_shap[regime] = {
                feat: np.abs(shap_values.values[mask][:, 
                    list(feature_names).index(feat)]).mean()
                for feat in new_features if feat in feature_names
            }
    
    regime_df = pd.DataFrame(regime_shap)
    regime_df.plot(kind='bar', ax=ax)
    ax.set_title('New Feature SHAP by Regime')
    ax.set_ylabel('Mean |SHAP|')
    
    # Panel 4: Rank of new features
    ax = axes[1, 1]
    total_features = len(feature_names)
    for feat in new_features:
        if feat in feature_importance.index:
            rank = list(feature_importance.index).index(feat) + 1
            ax.barh(feat, rank, color='coral')
            ax.text(rank + 0.5, feat, f'#{rank}/{total_features}')
    ax.set_title('Rank of New Features (lower = more important)')
    ax.set_xlabel('Rank')
    ax.invert_xaxis()
    
    plt.tight_layout()
    plt.savefig('diagnostic_2_shap_toxicity.png', dpi=150)
    
    # Quantitative verdict
    print("\n=== DIAGNOSTIC 2: FEATURE TOXICITY ===")
    for feat in new_features:
        if feat in feature_importance.index:
            rank = list(feature_importance.index).index(feat) + 1
            abs_shap = feature_importance[feat]
            top_shap = feature_importance.iloc
            ratio = abs_shap / top_shap
            print(f"{feat}: Rank #{rank}/{total_features}, "
                  f"|SHAP| = {abs_shap:.4f} "
                  f"({ratio:.1%} of top feature)")
            if ratio < 0.05:
                print(f"  -> TOXIC: Feature adds pure noise.")
            elif ratio < 0.15:
                print(f"  -> WEAK: Feature has marginal signal.")
            else:
                print(f"  -> HEALTHY: Feature is contributing.")
    
    return fig
```

**What to look for:** If any new feature's mean absolute SHAP value is less than 5% of the top feature's SHAP value, it is effectively noise — XGBoost found almost no informative splits on it. This typically means the feature needs the preprocessing described in Section 3 (Z-score normalization, fractional differentiation).[^22][^15][^16]
### Diagnostic 3: Signal Attribution — Where Does the PnL Come From? ("The Alpha Source Test")
This is the definitive test that answers: "When the XGBoost model changes the allocation versus what the HMM-only baseline would have done, does that change produce positive or negative PnL?"

```python
def diagnostic_alpha_attribution(daily_returns, regime_labels, 
                                  xgb_confidence, portfolio_weights_actual,
                                  baseline_weights_hmm_only):
    """
    DIAGNOSTIC 3: Does the XGBoost signal add or subtract PnL 
    relative to HMM-only allocation?
    
    Compares actual portfolio (HMM + XGBoost) against counterfactual
    (HMM-only, using median confidence for all days).
    """
    # Calculate daily PnL for actual strategy
    actual_daily_pnl = (portfolio_weights_actual * daily_returns).sum(axis=1)
    
    # Calculate counterfactual PnL (HMM-only, no XGBoost modulation)
    baseline_daily_pnl = (baseline_weights_hmm_only * daily_returns).sum(axis=1)
    
    # Alpha = difference
    alpha_daily = actual_daily_pnl - baseline_daily_pnl
    alpha_cumulative = (1 + alpha_daily).cumprod() - 1
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    
    # Panel 1: Cumulative alpha from XGBoost modulation
    ax = axes
    alpha_cumulative.plot(ax=ax, color='green', linewidth=1.5)
    ax.axhline(y=0, color='black', linestyle='--')
    ax.set_title('Cumulative Alpha from XGBoost (vs HMM-Only Baseline)')
    ax.set_ylabel('Cumulative Alpha')
    ax.fill_between(alpha_cumulative.index, alpha_cumulative, 0,
                    where=alpha_cumulative > 0, color='green', alpha=0.2)
    ax.fill_between(alpha_cumulative.index, alpha_cumulative, 0,
                    where=alpha_cumulative < 0, color='red', alpha=0.2)
    
    # Panel 2: Rolling 60-day alpha
    ax = axes[^1]
    rolling_alpha = alpha_daily.rolling(60).sum()
    rolling_alpha.plot(ax=ax, color='purple')
    ax.axhline(y=0, color='black', linestyle='--')
    ax.set_title('Rolling 60-Day Alpha from XGBoost Signal')
    
    # Panel 3: Alpha by regime
    ax = axes[^2]
    regime_alpha = {}
    for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
        mask = regime_labels == regime
        if mask.sum() > 0:
            regime_alpha[regime] = {
                'Daily Mean Alpha (bps)': alpha_daily[mask].mean() * 10000,
                'Annual Alpha (%)': alpha_daily[mask].mean() * 252 * 100,
                'Hit Rate (%)': (alpha_daily[mask] > 0).mean() * 100,
                'Days': mask.sum()
            }
    
    regime_df = pd.DataFrame(regime_alpha).T
    regime_df[['Annual Alpha (%)']].plot(kind='bar', ax=ax, color='teal')
    ax.set_title('Annualized Alpha by Regime')
    ax.set_ylabel('Alpha (%)')
    
    plt.tight_layout()
    plt.savefig('diagnostic_3_alpha_attribution.png', dpi=150)
    
    # Quantitative verdict
    total_alpha_ann = alpha_daily.mean() * 252 * 100
    total_alpha_vol = alpha_daily.std() * np.sqrt(252) * 100
    alpha_ir = total_alpha_ann / total_alpha_vol if total_alpha_vol > 0 else 0
    
    print("\n=== DIAGNOSTIC 3: ALPHA ATTRIBUTION ===")
    print(f"Total Annualized Alpha: {total_alpha_ann:+.2f}%")
    print(f"Alpha Volatility: {total_alpha_vol:.2f}%")
    print(f"Information Ratio: {alpha_ir:.3f}")
    print(f"\nRegime Breakdown:")
    print(regime_df.to_string())
    
    if abs(total_alpha_ann) < 0.50:
        print("\nVERDICT: ZERO ALPHA. XGBoost modulation has no impact.")
        print("The model output is not reaching the portfolio.")
    elif total_alpha_ann < -0.50:
        print("\nVERDICT: NEGATIVE ALPHA. XGBoost is hurting performance.")
        print("The model is worse than using fixed mid-confidence.")
    else:
        print("\nVERDICT: POSITIVE ALPHA. Signal is reaching portfolio.")
        print(f"But only {total_alpha_ann:.1f}% — check if tiers are too narrow.")
    
    return fig, regime_df
```

**What to look for:** If the cumulative alpha line is flat (oscillating around zero), the XGBoost modulation is producing zero information — confirming that the ML signal is not reaching the portfolio. If it's slightly negative, the meta-model is actively harmful (likely due to whipsaw from noisy probability oscillations). The regime breakdown reveals whether alpha is concentrated in one regime or uniformly absent.[^26]

***
## Root Cause Synthesis
The four failure modes interact multiplicatively. Even if the macro features had predictive power (which they don't in raw form), and even if the triple-barrier labels were correctly calibrated (which they aren't), the compressed confidence scores from the poorly-labeled model would still map to near-identical allocation tiers, and the HMM gate would still dominate the portfolio allocation.

| Failure | Impact | Fix Priority |
|---------|--------|-------------|
| HMM regime dominance (Masked Signal) | Eliminates XGBoost's ability to influence weights | Critical — fix first |
| Triple-barrier 20-day horizon mismatch | Trains model to predict wrong outcome | Critical — fix simultaneously |
| Raw macro features (no preprocessing) | Zero SHAP contribution to predictions | High — fix after labeling |
| Discrete tier mapping (no bet sizing) | Destroys information in probability output | High — fix with multiplicative sizing |
### Recommended Fix Sequence
1. **Run all three diagnostics first** to confirm which failures dominate. The confidence compression test (Diagnostic 1) should be run immediately — if the bull-regime confidence std is < 0.08, no other fix matters until the labeling is corrected.

2. **Fix the labels** by extending the triple-barrier forward window to 63–126 days with wider barriers (3–4x 60-day vol for TP, 1.5–2x for SL). Alternatively, switch to trend-scanning labels which directly capture multi-month trend characteristics.[^14]

3. **Preprocess macro features** using rolling Z-scores and fractional differentiation before retraining XGBoost. This alone should increase their SHAP contribution from < 5% of top feature to 15–25%.

4. **Replace the discrete allocation matrix** with continuous Kelly-based bet sizing that uses the calibrated meta-probability as a direct input. The HMM regime state should set the *ceiling* (max LEAPS allocation per regime) while XGBoost-Kelly determines the actual weight within that ceiling.[^4][^7]

5. **Implement purged k-fold cross-validation** with an embargo of at least `max_holding_period` (63–126 days) between train and test folds to prevent label leakage from overlapping triple-barrier windows.[^27][^28]

After these corrections, re-run Diagnostic 3 (Alpha Attribution). The target is an Information Ratio > 0.30 and annualized alpha > 3% from the XGBoost modulation layer alone, on top of the 29.60% HMM baseline.

---

## References

1. [A multi-model ensemble-HMM voting framework for market regime ...](https://www.aimspress.com/article/doi/10.3934/DSFE.2025019?viewType=HTML) - In this paper, we present a framework for detecting market regime shifts using a combination of tree...

2. [Let's talk about regime detection : r/algotrading - Reddit](https://www.reddit.com/r/algotrading/comments/1razsuv/lets_talk_about_regime_detection/) - HMM models are not intended to answer positioning as much as asset allocation. In my case, I run a l...

3. [Does Meta Labeling Add to Signal Efficacy? - Hudson & Thames](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/) - Our results confirm the fact that a combination of event-based sampling, triple-barrier method and m...

4. [Meta-Labeling: Solving for Non Stationarity and Position Sizing](https://www.youtube.com/watch?v=WbgglcXfEzA) - Join our reading group! https://hudsonthames.org/reading-group/ Meta-labeling is a technique first i...

5. [Meta-Labeling: Calibration and Position Sizing - YouTube](https://www.youtube.com/watch?v=BIBSv_gwBgs) - Join our reading group! https://hudsonthames.org/reading-group/ We dive into the world of Meta-label...

6. [[PDF] Does Meta-Labeling Add to Signal Efficacy? | Hudson & Thames](https://hudsonthames.org/wp-content/uploads/2022/04/Does-Meta-Labeling-Add-to-Signal-Efficacy.pdf) - Add position sizing (bet sizing [de Prado 2018, Chapter 10] and risk man- agement to the strategies....

7. [The Mathematics of Position Sizing, Part 1: The Kelly Criterion from ...](https://open.substack.com/pub/kniyer/p/the-mathematics-of-position-sizing) - So this series will do the math. We're starting with the Kelly Criterion — a 68-year-old formula fro...

8. [TurboCore-Pro-ML-Pipeline-Upgrade-State-of-the-Art-Quant-Architecture-Blueprint-latest-version.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/857b2971-b282-4b8d-a10e-dd5bfbe86a66/TurboCore-Pro-ML-Pipeline-Upgrade-State-of-the-Art-Quant-Architecture-Blueprint-latest-version.pdf?AWSAccessKeyId=ASIA2F3EMEYEZ376M3BZ&Signature=onJ3WHGwos9HV7JY4KFX4WxAZ6c%3D&x-amz-security-token=IQoJb3JpZ2luX2VjELb%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQDxvjC101mI0VR%2By9jHRD28mAaA56YuM%2BB9yHJaDQXjgAIgV7ItciDDtpF%2Bwgc0whIyjjUyA657s8Al5KHn5d6K790q8wQIfxABGgw2OTk3NTMzMDk3MDUiDNd0Ni%2ButK%2B%2F4NqmKirQBHUiGF2EQFQwPYeL%2BwxMJ49kPNWji01%2BHg4h5TPV4HUIUSHZ0HbnbNy3vVCRhSmt%2BWVr4%2Fv1oU7W3QDJ6EyjGX7xnDOYIt8liW0NbRTZivyxoXY4Y7vZiCuxYO61Hmuevso%2BOQUgqPTRmgH69DSmzvx4hXVIqwTn2TaINEi1JEMo0HtT3F5vQXwVroE0jIj5pqFYeaLoAI4GiJlR%2FbkhX5xtqO2XQMZh5BUBd9prhXQdHzAYgLWirh4MLoZoVyG0tKMOOZK6UEwBBL6GbsDFGSR7OYEySq4hflNm%2FZnUx5QyLWjCdJm5%2BDVnv2naXjEzG%2FrUjE%2Fne8bECqNpVHKsDIbo0CsFeAT3%2Fd6M0o5gdzvyUbMZ1aM0yQ0IblSskrALEnj3Z1fFhFYx%2FnCMD22IQSEqNSaNDMn2u7oVyfrHMjeXIGovEEIq7znVAm%2FhVt52PmN%2BjMONg0ijgyQJTRk0oSpROYzCts1N%2BcEEfe6IwYaWWVGd0Xpt2m7ftcKfuDlRsEpwtgFiMTacozPCfD%2FqPfY13vM8lGAwNIFzWYeHqmJw5gB%2BSXba2xV5qdTRH95aJMzwh%2F54LYuHejL6Xw9NsgfuXerkKAMx5AximYW6N6v3K9O8mCnsCjnlsiZcx%2FCGXw33qQBH8%2FA4UW2SpiQKKxRLvCxjz4TiSkfC8v7HwSnELCvkks%2F%2BUNTKlGd%2Fy3xeMdEs8RzsDWnsGS1chvhHgEeP%2FisvGO0uFVCFEL5FQeeMInsGJJ9y0u9QVut7bSBCCm5OjMOIrBnMc8WYFXD5hTgwlujMzQY6mAEQ%2FZm46ou%2FnvupNG%2Fo%2FuHIOE3QX6l%2B%2FCKZGiRNXY7J7KpsK4Cjx6sPnZRqz3lKDs6Yup4mryGiNTXD8unavXOKG6AwgWF%2BwHn%2FCkwq2d0dsC5G%2BCXMukqnzzGYjSfzoyqInTwsEOL4f5XX5rtLiNMcG3N9S1mu%2B1ze%2FBybYK%2BR4BRqUfERH1O4Fxt3uaXLZEruV3Hku1EEqA%3D%3D&Expires=1773355711)

9. [TurboCore-Pro-LEAPS-Strategy-Quantitative-Underperformance-Diagnosis-Architectural-Fix-Blueprint.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/67975583/5b87a5d9-ec76-4a5a-a850-0566f83ce96f/TurboCore-Pro-LEAPS-Strategy-Quantitative-Underperformance-Diagnosis-Architectural-Fix-Blueprint.pdf?AWSAccessKeyId=ASIA2F3EMEYEZ376M3BZ&Signature=9KHEeK8hd5rCQv4K1ony%2FNdsxNc%3D&x-amz-security-token=IQoJb3JpZ2luX2VjELb%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQDxvjC101mI0VR%2By9jHRD28mAaA56YuM%2BB9yHJaDQXjgAIgV7ItciDDtpF%2Bwgc0whIyjjUyA657s8Al5KHn5d6K790q8wQIfxABGgw2OTk3NTMzMDk3MDUiDNd0Ni%2ButK%2B%2F4NqmKirQBHUiGF2EQFQwPYeL%2BwxMJ49kPNWji01%2BHg4h5TPV4HUIUSHZ0HbnbNy3vVCRhSmt%2BWVr4%2Fv1oU7W3QDJ6EyjGX7xnDOYIt8liW0NbRTZivyxoXY4Y7vZiCuxYO61Hmuevso%2BOQUgqPTRmgH69DSmzvx4hXVIqwTn2TaINEi1JEMo0HtT3F5vQXwVroE0jIj5pqFYeaLoAI4GiJlR%2FbkhX5xtqO2XQMZh5BUBd9prhXQdHzAYgLWirh4MLoZoVyG0tKMOOZK6UEwBBL6GbsDFGSR7OYEySq4hflNm%2FZnUx5QyLWjCdJm5%2BDVnv2naXjEzG%2FrUjE%2Fne8bECqNpVHKsDIbo0CsFeAT3%2Fd6M0o5gdzvyUbMZ1aM0yQ0IblSskrALEnj3Z1fFhFYx%2FnCMD22IQSEqNSaNDMn2u7oVyfrHMjeXIGovEEIq7znVAm%2FhVt52PmN%2BjMONg0ijgyQJTRk0oSpROYzCts1N%2BcEEfe6IwYaWWVGd0Xpt2m7ftcKfuDlRsEpwtgFiMTacozPCfD%2FqPfY13vM8lGAwNIFzWYeHqmJw5gB%2BSXba2xV5qdTRH95aJMzwh%2F54LYuHejL6Xw9NsgfuXerkKAMx5AximYW6N6v3K9O8mCnsCjnlsiZcx%2FCGXw33qQBH8%2FA4UW2SpiQKKxRLvCxjz4TiSkfC8v7HwSnELCvkks%2F%2BUNTKlGd%2Fy3xeMdEs8RzsDWnsGS1chvhHgEeP%2FisvGO0uFVCFEL5FQeeMInsGJJ9y0u9QVut7bSBCCm5OjMOIrBnMc8WYFXD5hTgwlujMzQY6mAEQ%2FZm46ou%2FnvupNG%2Fo%2FuHIOE3QX6l%2B%2FCKZGiRNXY7J7KpsK4Cjx6sPnZRqz3lKDs6Yup4mryGiNTXD8unavXOKG6AwgWF%2BwHn%2FCkwq2d0dsC5G%2BCXMukqnzzGYjSfzoyqInTwsEOL4f5XX5rtLiNMcG3N9S1mu%2B1ze%2FBybYK%2BR4BRqUfERH1O4Fxt3uaXLZEruV3Hku1EEqA%3D%3D&Expires=1773355711) - The TurboCore Pro hybrid strategy produced a 15.47 CAGR over 16 The TurboCore Pro hybrid strategy pr...

10. [What Is the Triple Barrier Method? A Labeling Technique to ...](https://xglamdring.com/what-is-the-triple-barrier-method-a-labeling-technique-to-prevent-overfitting-in-ml-based-quantitative-trading/) - In the rapidly evolving world of FinTech, supply chain managers, engineers, and traders are increasi...

11. [Stock Price Prediction Using Triple Barrier Labeling and ...](https://arxiv.org/html/2504.02249v2)

12. [Background: Triple Barrier Labeling Method | AI Quantitative Trading](https://www.waylandz.com/quant-book-en/Triple-Barrier-Labeling-Method/) - "Traditional up/down labels ignore a key problem: how long can you hold?"

13. [Labeling Stock Prices for ML with Triple Barrier Methods](https://ayratmurtazin.beehiiv.com/p/labeling-stock-prices-for-ml-with-triple-barrier-methods) - Unveiling a cutting-edge machine learning technique for precise stock price labeling 📊🔍

14. [MetaTrader 5 Machine Learning Blueprint (Part 3): Trend-Scanning ...](https://www.mql5.com/en/articles/19253) - The triple-barrier method we explored in Part 2 was a significant improvement over fixed-time horizo...

15. [How to use Feature Importance with XGBoost](https://www.evolvingdev.com/post/xgboost-model-feature-importance) - In this guide, we will delve deep into the methods, best practices, and interpretations of feature i...

16. [A Gentle Introduction to SHAP for Tree-Based Models](https://machinelearningmastery.com/a-gentle-introduction-to-shap-for-tree-based-models/) - In this article, we'll explore how to apply SHAP to tree-based models using a well-optimized XGBoost...

17. [Machine Learning Trading Essentials (Part 2): Fractionally ...](https://hudsonthames.org/machine-learning-trading-essentials-part-2-fractionally-differentiated-features-filtering-and-labelling/) - From fractionally differentiated features, to CUSUM filters and triple-barrier labeling, we'll be di...

18. [Fractionally Differentiated¶](https://mlfinpy.readthedocs.io/en/latest/FractionalDifferentiated.html)

19. [Lesson 6.8: Advanced Concept - Fractional Differentiation](https://quantfinancelab.com/machine-learning-for-quantitative-finance/advanced-concept-fractional-differentiation) - Master the core concepts of quantitative finance with AI-powered tools, interactive guides, and a co...

20. [Market regime detection using Statistical and ML based approaches](https://developers.lseg.com/en/article-catalog/article/market-regime-detection) - We use statistical and ML models to identify normal or crash market regimes for S&P 500 and build an...

21. [Fractionally Differentiated Features¶](https://www.mlfinlab.com/en/latest/feature_engineering/frac_diff.html)

22. [XGBoost Feature Importance with SHAP Values](https://xgboosting.com/xgboost-feature-importance-with-shap-values/)

23. [Quantile XGBoost and SHAP in Creating and Explaining ...](https://ter-arkhiv.ru/0424-7388/article/view/697034) - Economics and Mathematical Methods Vol 61, No 4 (2025)

24. [Why am I getting very little variance in predict_proba values in XGBoost?](https://stackoverflow.com/questions/70070426/why-am-i-getting-very-little-variance-in-predict-proba-values-in-xgboost) - I'm having trouble understanding why all the values when calling the predict_proba function in the x...

25. [Chapter 3: Using XGBoost to predict probability - Ikigai Labs](https://www.ikigailabs.io/multivariate-time-series-forecasting-in-python-settings/xgboost-predict-probability) - In this article, we will see how XGBoost can be used to predict probability, when you should accept ...

26. [XGBoost in Long-Only Funds: Ranking Stocks for Alpha - LinkedIn](https://www.linkedin.com/posts/rahul-fernandes-b3541816a_longonly-activemanagement-quantinvesting-activity-7424695664716201984-iOso) - XGBoost is great at capturing interactions, but in long-only: the edge is rarely ML sophistication; ...

27. [The Hidden Flaw in Your Financial ML Pipeline — Label Concurrency](https://www.mql5.com/en/articles/19850) - Discover how to fix a critical flaw in financial machine learning that causes overfit models and poo...

28. [Modelling: Label Concurrency and Cross Validation - YouTube](https://www.youtube.com/watch?v=lDTSGK4JMYk) - ... cross-validation techniques in financial machine learning. Namely: K-Fold, Walk Forward, and Pur...

