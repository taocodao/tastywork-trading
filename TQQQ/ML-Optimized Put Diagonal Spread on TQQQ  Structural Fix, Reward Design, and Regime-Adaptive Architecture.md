# ML-Optimized Put Diagonal Spread on TQQQ: Structural Fix, Reward Design, and Regime-Adaptive Architecture

## Executive Summary

This report addresses a specific structural problem in a TQQQ mean-reversion swing trading system: a put diagonal spread that collapses into a short calendar spread due to TQQQ's low nominal price, creating a gamma drag that offsets directional gains during bounces. The analysis covers three domains: (A) how to use reinforcement learning (PPO) or differential evolution to dynamically optimize spread parameters; (B) alternative option structures that bypass the calendar spread trap; and (C) a concrete architectural blueprint for integrating an ML parameter-optimizer into a live trading pipeline. Recommendations are grounded in the deep hedging literature (Buehler et al. 2019), differential evolution optimization of option strategies (Munoz & Tymerski 2020), and the latest DRL hedging benchmarks (Neagu et al. 2025).

***

## Part A: Structural Optimization via Machine Learning

### The Core Problem — Why Static Parameters Fail

With TQQQ trading at ~$50, the $0.50 strike increments mean that a 40-delta put and a 20-delta put frequently map to the **same strike**. When both legs share a strike, the diagonal becomes a **short calendar spread** — which is long gamma and short vega. On a 3–5 day bounce:[^1][^2]

- The 45 DTE anchor leg loses value from IV crush (good — short vega profit).
- But the 10 DTE hedge leg's **enormous near-expiration gamma** causes it to lose value explosively as TQQQ moves away — acting as a massive drag.
- Near-zero theta is collected because the hold time is only 2–4 days.

The net effect: directional gains on the anchor are largely offset by gamma losses on the hedge, producing average wins under $250 on positions consuming significant buying power.

### RL Agent Design: Action Space

The ML agent should output a **4-dimensional continuous action vector** at each entry trigger:

\[
a_t = [\text{Anchor\_DTE}, \text{Anchor\_Delta}, \text{Hedge\_DTE}, \text{Hedge\_Delta}]
\]

Using SB3's PPO with a `gym.spaces.Box` action space is the standard approach for multi-dimensional continuous outputs. The action bounds should be:[^3][^4]

| Parameter | Low | High | Rationale |
|-----------|-----|------|-----------|
| Anchor DTE | 30 | 60 | Sufficient vega exposure without excessive time cost |
| Anchor Delta | 0.25 | 0.50 | OTM to slightly ATM range for short puts |
| Hedge DTE | 5 | 21 | Near-term for gamma protection |
| Hedge Delta | 0.10 | 0.35 | OTM protection with varying aggressiveness |

A critical **constraint** the agent must learn (or that should be hard-coded): enforce a minimum 1-strike separation between anchor and hedge. If the agent outputs parameters that map to the same strike, override with a fixed-width vertical at equal DTE (see Part B).[^5]

### RL Agent Design: State Space

The state space draws from both the deep hedging literature and TQQQ-specific regime indicators. Hull et al. (2023) demonstrated that including portfolio Greeks (gamma, vega) in the state space significantly improves RL hedging performance. François et al. (2025) showed that IV surface dynamics — level, slope, and curvature — are the most informative forward-looking features.[^6][^7][^8][^9]

The recommended state vector:

| Feature | Source | Why It Matters |
|---------|--------|----------------|
| RSI-2 value | TQQQ price | Primary entry signal; magnitude predicts bounce strength |
| TQQQ distance from 200 SMA (%) | TQQQ price | Regime classification: trend vs. mean-reversion |
| Hurst Exponent (rolling 60d) | TQQQ returns | H < 0.5 confirms mean-reversion regime[^10][^11] |
| VIX level | CBOE | Absolute volatility regime |
| VIX/VXV ratio | CBOE | Term structure slope; >1.0 = backwardation = stress[^12][^13] |
| TQQQ ATM IV (30d) | Options chain | Current implied volatility level |
| TQQQ IV skew (25d put - 25d call) | Options chain | Skew steepness predicts crash risk[^14][^15] |
| Anchor leg Vega | Black-Scholes | Current vega exposure of the position |
| Hedge leg Gamma | Black-Scholes | Current gamma drag magnitude |
| Days held | Counter | Time-in-trade for exit timing |

François et al. (2025) found that a **reduced state space** often performs as well or better than the full space due to curse-of-dimensionality effects — training time increased 190% with the full IV surface while performance sometimes degraded. Start with 8–10 features and expand only if performance plateaus.[^8]

### Reward Function Design

This is the most critical design choice. PPO is extremely sensitive to reward shaping — small changes to penalty coefficients can completely reverse which design trains a better agent.[^16]

The recommended reward function combines the **Buehler et al. (2019) convex risk measure** framework with domain-specific penalties:

\[
R_t = w_1 \cdot \text{PnL}_{\text{spread}} - w_2 \cdot \text{GammaDrag} - w_3 \cdot \text{MaxDrawdown} + w_4 \cdot \text{BPEfficiency}
\]

Where:

- **PnL_spread**: Realized P&L of the closed spread position (the primary signal).
- **GammaDrag**: Measured as \(\Gamma_{\text{hedge}} \times (\Delta S)^2 / 2\), penalizing trades where the hedge's gamma loss exceeds a fraction of anchor gains.[^6]
- **MaxDrawdown**: Peak-to-trough unrealized loss during the trade, following the asymmetric semi-quadratic penalty from Neagu et al. (2025): \(\sqrt{E[R^2 \cdot \mathbf{1}_{\{R>0\}}]}\), which penalizes losses without penalizing gains.[^17]
- **BPEfficiency**: PnL divided by buying power consumed — prevents the agent from selecting overly capital-intensive structures.

**Sparse vs. Dense Rewards**: The hedging literature demonstrates that sparse terminal rewards (P&L only at trade close) favor MCPG and PPO over value-based methods like DQL. However, for a 2–12 day swing trade, intermediate "shaping" rewards (e.g., daily mark-to-market delta of the spread) can help PPO learn faster. The Chong et al. (2023) approach of decomposing terminal reward into sub-components is recommended.[^18][^17]

**Weight Optimization**: Treat \(w_1 \ldots w_4\) as hyperparameters optimized via grid search on the simplex \(\sum w_i = 1\), following the risk-aware RL framework of recent work.[^19]

### Differential Evolution as an Alternative

For practitioners who prefer interpretability over neural network black boxes, differential evolution (DE) is a proven alternative for optimizing option strategy parameters. Munoz & Tymerski (2020) used "DE/rand/1/bin" to optimize a Broken Wing Butterfly strategy across 6+ parameters — DTE, strike selection, profit targets, stop losses — over a decade of SPY data.[^20][^5]

**DE fitness function** (adapted for the TQQQ diagonal):

\[
F(x) = w_1 \frac{\text{AnnReturn}}{\text{AnnVol}} + w_2 \cdot \text{CumReturn} - w_3 \cdot \text{MaxDrawdown}
\]

Subject to: win rate ≥ 65%, trade frequency ≥ 80% of signals.[^5]

**Key DE finding**: The **normalized strike mapping method** (strike/underlying price) significantly outperformed both delta-based and points-based mapping (fitness 2.61 vs. 1.94 and 1.77), because it's scale-invariant as the underlying price changes. This is especially relevant for TQQQ, whose price has ranged from $10 to $80+.[^5]

DE advantages over PPO for this problem:
- No reward function design required (uses a direct fitness function on backtest results).
- Deterministic: same parameters yield same backtest results.
- Faster to implement with existing backtesting infrastructure.
- Optimal entry DTE found to be ~61 days across all methods; exit DTE of 6–13 days.[^5]

DE disadvantages:
- Cannot adapt in real-time; must be re-optimized periodically (e.g., quarterly).
- Does not condition on daily market state — outputs fixed parameters.
- Susceptible to overfitting on historical data without walk-forward validation.

### PPO vs. MCPG: Which Algorithm?

The Neagu et al. (2025) benchmark across 8 DRL algorithms is the most comprehensive comparison available:[^17]

| Algorithm | RSQP (Lower = Better) | Training Time | Outperforms BS Baseline? |
|-----------|----------------------|---------------|--------------------------|
| MCPG | **0.8111** | 24 min | **Yes** |
| PPO | 0.9439 | 5h 58m | No |
| TD3 | 1.0113 | 10h 20m | No |
| DQL | 1.0278 | 6h 32m | No |
| DDPG | 1.0467 | 9h 37m | No |

MCPG (Buehler et al. 2019) is the clear winner for option hedging — 14× faster training, only algorithm to outperform the Black-Scholes baseline, and robust to hyperparameters (80 of 81 configurations outperformed the baseline). PPO showed promise but was unstable; only 3 of 81 hyperparameter combinations beat the baseline during tuning.[^17]

**Recommendation**: Start with MCPG (Buehler-style deterministic policy gradient with terminal risk measure). Use PPO as a secondary candidate if the action space needs to include discrete regime switches.

***

## Part B: Escaping the Calendar Spread Trap

### Why the Diagonal Collapses

TQQQ at $50 with $0.50 strike increments means:
- 40-delta put → ~$48 strike
- 20-delta put → ~$47 or $47.50 strike
- In many cases, both map to the **same** $47.50 or $48 strike

When both legs share a strike, the spread becomes a **short calendar** (sell the far-dated, buy the near-dated), which is long gamma and short vega. This is the opposite of what a directional bounce trade wants.[^21][^2]

### Alternative Structure 1: Bull Put Credit Spread (Same DTE)

The simplest fix is to enforce **equal DTE** on both legs, eliminating the calendar component entirely:[^22]

- **Sell** the 40-delta put (e.g., $48 strike, 30 DTE)
- **Buy** the 20-delta put (e.g., $46 strike, 30 DTE)

Greek profile on a bounce:
- **Delta**: Positive and strong — the short put gains value as TQQQ rises.
- **Vega**: Slightly negative (both legs lose from IV crush, but the short leg loses more).
- **Gamma**: Low and manageable — no near-expiration gamma bomb.
- **Theta**: Net positive (both legs decay, short decays faster).

This is the **recommended default structure** when the ML agent cannot find a diagonal with ≥1 strike separation. The trade-off is lower profit per trade (spread width caps the gain) but drastically improved consistency.

### Alternative Structure 2: Call Diagonal (Bullish)

Since the thesis is "TQQQ bounces from oversold," a **call diagonal** may be more natural than a put structure:[^23]

- **Buy** a 30–45 DTE call at 50–60 delta (slightly ITM, high staying power).
- **Sell** a 7–14 DTE call at 20–30 delta (OTM, capturing near-term theta/IV crush).

Advantages:
- Delta is naturally positive and aligned with the bounce thesis.
- The long leg's vega is positive (benefits from any IV expansion during the dip entry).
- No naked short put risk; defined-risk debit trade.
- Strike separation is easier on the call side since calls at different deltas span a wider range when skew is steep.

Disadvantage: Costs a debit upfront vs. potential credit on the put side.

### Alternative Structure 3: 1×2 Call Ratio Backspread

For aggressive mean-reversion plays, a **1×2 call backspread** offers positive gamma and unlimited upside:[^24]

- **Sell** 1 ATM call (~50 delta).
- **Buy** 2 OTM calls (~25–30 delta each).

This creates a position that is long gamma, long vega, and benefits from a sharp bounce. The risk zone is a small loss if TQQQ drifts sideways near the short strike. On TQQQ's $0.50 strike grid, the two bought calls can be placed 1–2 strikes above the sold call, ensuring real strike separation.[^25][^24]

### ML Agent Constraint: Minimum Strike Width

The ML model should include a **hard constraint** that prevents selecting parameter combinations that produce a calendar spread:

```
if anchor_strike == hedge_strike:
    fallback to bull_put_credit_spread(same_DTE=anchor_DTE, 
                                       width=max(1, nearest_available))
```

Alternatively, the agent's action space can include a **discrete structure selector** (diagonal, vertical, call diagonal, backspread) alongside the continuous DTE/delta parameters. This creates a hybrid discrete-continuous action space, which PPO handles via `gym.spaces.Dict` or by discretizing the structure choice and keeping DTE/delta continuous.[^26]

***

## Part C: Regime-Based Implementation Blueprint

### Architecture Overview

The system has three layers operating at different frequencies:

```
Layer 1: Regime Classifier (Daily, before market open)
    ├── Input: VIX, VXV, 200 SMA distance, Hurst Exponent
    ├── Output: {MEAN_REVERT, TRENDING, CRISIS}
    └── Gate: Only pass to Layer 2 if regime = MEAN_REVERT

Layer 2: Entry Signal Generator (Intraday, on RSI-2 trigger)
    ├── Input: RSI-2, Bollinger %B, Volume ratio
    ├── Output: {ENTER, SKIP}
    └── Gate: Only pass to Layer 3 if ENTER

Layer 3: ML Parameter Optimizer (On entry signal)
    ├── Input: Full state vector (10 features)
    ├── Model: Trained MCPG/PPO agent or DE-optimized lookup
    ├── Output: [Anchor_DTE, Anchor_Delta, Hedge_DTE, Hedge_Delta, Structure_Type]
    └── Execute: Map to nearest available strikes via tastytrade API
```

### Layer 1: Regime Classification

The existing `DvorRegimeClassifier` and `TermStructureCircuitBreaker` integrate directly. The classification logic:

| Condition | Regime | Action |
|-----------|--------|--------|
| Hurst < 0.45 AND 200 SMA distance < 15% | MEAN_REVERT | Enable swing layer[^10][^11] |
| Hurst > 0.55 OR 200 SMA distance > 20% | TRENDING | Disable swing layer |
| VIX/VXV > 1.05 (backwardation) AND VIX > 30 | CRISIS | Disable all entries, hedge existing[^12][^13] |

The Hurst exponent is critical: when H < 0.5, mean-reversion signals (RSI-2) gain structural support; when H > 0.5, those same signals become unreliable. This directly addresses the 2022 failure mode where every "dip" kept falling — a trending regime (H > 0.55) would have gated off entries entirely.[^10]

### Layer 3: Model Training Pipeline

**Data Requirements**:
- Historical TQQQ daily OHLCV (2010–present).
- Historical options chain data (DTE, delta, bid/ask for all strikes) — IVolatility or CBOE DataShop.
- VIX and VXV daily closes.

**Training Environment (Gymnasium-compatible)**:

```python
class TQQQSwingEnv(gymnasium.Env):
    observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(10,))
    action_space = spaces.Box(
        low=np.array([30, 0.25, 5, 0.10]),   # [anch_DTE, anch_delta, hedge_DTE, hedge_delta]
        high=np.array([60, 0.50, 21, 0.35])
    )
    
    def step(self, action):
        # Map action to nearest available strikes
        # Simulate spread P&L using historical options data
        # Apply calendar-trap override if strikes collapse
        # Return: obs, reward, done, truncated, info
    
    def _compute_reward(self, pnl, gamma_drag, max_dd, bp_used):
        return (w1 * pnl - w2 * gamma_drag 
                - w3 * max_dd + w4 * pnl/bp_used)
```

**Training Protocol** (adapted from Neagu et al. 2025):[^17]
- Simulate 2^19 (~500K) entry episodes from historical data.
- Use walk-forward validation: train on 2010–2020, validate on 2020–2022, test on 2022–2024.
- MCPG hyperparameters: learning rate 1e-5, batch size 256, 4 hidden layers × 64 neurons.[^17]
- Early stopping when validation RSQP stops improving for 75 iterations.
- Re-train quarterly with fresh data.

### Live Deployment Flow

The daily pipeline runs as follows:

1. **Pre-market (8:00 AM ET)**: Compute regime features. If CRISIS or TRENDING, skip the day.
2. **Intraday monitoring**: Watch RSI-2 on 15-min bars. When RSI-2 < 10, trigger entry signal.
3. **On trigger**: Feed 10-feature state vector into the trained model.
4. **Model output**: `[anchor_DTE=42, anchor_delta=0.35, hedge_DTE=12, hedge_delta=0.18]`.
5. **Strike mapping**: Use tastytrade API to find the nearest available strikes matching the target deltas in the target DTE expiration. Apply the **normalized strike mapping** method (strike/TQQQ_price) for robustness across TQQQ price levels.[^5]
6. **Calendar-trap check**: If both legs map to the same strike → switch to bull put credit spread at the anchor DTE.
7. **Execute**: Place the spread order via tastytrade API. Set the rolling/exit rules.

### Risk Safeguards

| Safeguard | Implementation | Purpose |
|-----------|---------------|---------|
| Regime gate (Layer 1) | Hurst > 0.55 → no entries | Prevents 2022-style trend-following losses[^10] |
| VIX circuit breaker | VIX/VXV > 1.05 → close all positions | Term structure inversion signals extreme stress[^13] |
| Max concurrent positions | ≤ 3 open spreads | Capital preservation |
| Per-trade stop loss | Close at -15% of BP consumed | Limits individual trade damage |
| Rolling limit | Max 2 rolls per trade, each 5% lower | Prevents dollar-cost-averaging into a crash |
| Calendar-trap override | Same-strike → switch to vertical | Eliminates the gamma drag problem |

***

## Part D: Academic and Practitioner References

### Directly Relevant Academic Works

- **Buehler et al. (2019)** — "Deep Hedging": The foundational framework for using RL with convex risk measures to optimize hedging strategies under market frictions. Introduced MCPG for options, which remains the best-performing algorithm.[^27][^28]

- **Neagu et al. (2025)** — "Deep RL Algorithms for Option Hedging": The most comprehensive benchmark comparing 8 DRL algorithms (MCPG, PPO, DQL variants, DDPG, TD3). MCPG won decisively; sparse rewards in hedging problems favor Monte Carlo methods.[^18][^17]

- **Hull & White (2023)** — "Gamma and Vega Hedging Using Deep Distributional RL": Demonstrated that including portfolio Greeks in the RL state space and allowing gamma/vega hedging via options (not just delta hedging via stock) significantly reduces tail risk.[^9][^6]

- **François et al. (2025)** — "Enhancing Deep Hedging with Implied Volatility Surface Dynamics": Showed that IV slope, curvature, and level are the most informative state-space features for hedging decisions. Reduced state space matched or beat the full IV surface.[^7][^8]

- **Munoz & Tymerski (2020)** — "Differential Evolution Optimization of the Broken Wing Butterfly": Proved that DE can optimize multi-parameter option strategies with a fitness function balancing returns, volatility, and drawdown. Normalized strike mapping was optimal.[^20][^5]

- **Avellaneda & Lee (2008)** — "Statistical Arbitrage in the US Equities Market": The canonical OU-process framework for mean-reversion trading signals, providing the mathematical foundation for s-score entry/exit thresholds.[^29][^30]

### LETF-Specific Literature

- **SLCG (2012)** — "Crooked Volatility Smiles: Evidence from Leveraged ETF Options": Demonstrated that LETF options have asymmetric skew due to the leverage factor — OTM puts on 3× bull ETFs are disproportionately expensive because return shocks are inversely correlated with volatility shocks.[^14]

- **Compounding Effects in LETFs (2025)** — Showed that LETF performance depends fundamentally on return autocorrelation: trending markets enhance returns while mean-reverting markets induce underperformance through the compounding mechanism. This directly implies that the Hurst exponent regime filter is essential for any LETF options strategy.[^31]

### Risk-Aware Reward Design

- **Risk-Aware RL Reward (2025)** — Proposed a composite reward combining annualized return, downside risk penalty, differential return, and Treynor ratio, with theoretical analysis showing all components are differentiable and bounded — suitable for stable PPO training.[^19]

***

## Implementation Priority Roadmap

### Phase 1 (Immediate — No ML Required)

1. **Implement the calendar-trap override**: When anchor and hedge map to the same strike, automatically switch to a bull put credit spread at equal DTE with minimum 1-strike width.
2. **Add the call diagonal** as an alternative entry structure when put diagonal strike separation is insufficient.
3. **Enforce the Hurst exponent gate** (H < 0.45) alongside the existing VIX/SMA filters.

Expected impact: Eliminates the structural gamma drag problem and filters out the worst regime-mismatch trades. This alone should lift the annualized return from ~4.5% toward 8–12%.

### Phase 2 (1–2 Months — DE Optimization)

4. **Run differential evolution** on historical data to find optimal static parameters for each regime bucket (High VIX/Low VIX × High Hurst/Low Hurst).
5. Use normalized strike mapping and the fitness function \(F = w_1 \frac{R}{V} + w_2 C - w_3 D\) with walk-forward validation.[^5]
6. Deploy as a lookup table: regime → optimized parameters.

### Phase 3 (3–6 Months — RL Agent)

7. **Build the Gymnasium environment** using historical options chain data.
8. **Train MCPG first** (simpler, faster, proven best for sparse rewards).[^17]
9. Walk-forward validate on 2022–2024 (includes the drawdown regime).
10. Paper-trade for 1 month before live deployment.
11. Re-train quarterly.

---

## References

1. [Ultimate Guide to Selling Options Profitably PART 7 - Reddit](https://www.reddit.com/r/options/comments/q8t3o1/ultimate_guide_to_selling_options_profitably_part/) - In a nutshell this means that the short dated options are more sensitive than the longer dated optio...

2. [CALENDAR SPREAD: a Long GAMMA / Short VEGA option strategy](https://www.youtube.com/watch?v=6bGVWHmdihY) - This video explains what a calendar spread is and how to understand how to construct it. 
A  short c...

3. [PPO¶](https://stable-baselines3.readthedocs.io/en/v1.0/modules/ppo.html)

4. [PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html)

5. [Differential Evolution Optimization of the Broken Wing Butterfly ...](https://www.scirp.org/journal/paperinformation?paperid=101276) - In this paper, we used the “DE/rand/1/bin” differential evolution strategy to find each of the BWB o...

6. [[PDF] Gamma and vega hedging using deep distributional reinforcement ...](https://www-2.rotman.utoronto.ca/~hull/downloadablepublications/Gamma_Vega_Hedging.pdf)

7. [Enhancing Deep Hedging of Options with Implied Volatility ...](https://arxiv.org/html/2407.21138v1)

8. [Enhancing Deep Hedging of Options with Implied Volatility Surface ...](https://arxiv.org/html/2407.21138v2)

9. [2. The Rl Model](https://pmc.ncbi.nlm.nih.gov/articles/PMC9992725/) - We show how reinforcement learning can be used in conjunction with quantile regression to develop a ...

10. [The Hurst Exponent: Trend vs Range Detection | FractalCycles Guides](https://fractalcycles.com/guides/hurst-exponent-explained) - In a mean-reverting regime, the trough may represent a more complete reversal. This combination of t...

11. [Rolling Hurst Exponent: Detecting Regime Shifts in Real-Time](https://fractalcycles.com/guides/rolling-hurst-exponent) - Track how market character evolves over time. A rolling Hurst calculation reveals regime transitions...

12. [VIX Futures Curve Explained (Guide to Contango, Backwardation ...www.quantvps.com › blog › vix-futures-curve-explained](https://www.quantvps.com/blog/vix-futures-curve-explained) - The VIX futures curve reveals whether contango will bleed volatility products or backwardation will ...

13. [Inside Volatility Trading: Is VIX Backwardation Necessarily ...](https://www.cboe.com/insights/posts/inside-volatility-trading-is-vix-backwardation-necessarily-a-sign-of-a-future-down-market/) - Cboe Global Markets, a leading provider of market infrastructure and tradable products, delivers cut...

14. [Evidence from Leveraged and Inverse ETF Options](https://www.slcg.com/files/research-papers/Crooked%20Volatility%20Smiles%20Evidence%20from%20Leveraged%20and%20Inverse%20ETFs.pdf)

15. [[PDF] Predicting option implied volatility features using machine learning ...](https://thesis.eur.nl/pub/67130/Thesis_MvLent_Final.pdf) - This paper investigates the predictability of shape features of option implied volatility surfaces (...

16. [How Sensitive Is PPO to Reward Shaping?](https://www.luseratech.com/ml/how-sensitive-is-ppo-to-reward-shaping) - Lock the Promise: Discover why your PPO agent's impressive performance might be a fragile illusion o...

17. [Deep Reinforcement Learning Algorithms for Option Hedging - arXiv](https://arxiv.org/html/2504.05521v2)

18. [Deep Reinforcement Learning Algorithms for Option Hedging](https://www.alphaxiv.org/overview/2504.05521v1) - View recent discussion. Abstract: Dynamic hedging is a financial strategy that consists in periodica...

19. [Risk-Aware Reinforcement Learning Reward for Financial Trading](https://arxiv.org/html/2506.04358v1)

20. [[PDF] Differential Evolution Optimization of the Broken Wing Butterfly ...](https://www.scirp.org/pdf/ti_2020062916160574.pdf) - In this paper, we used the “DE/rand/1/bin” differential evolution strategy to find each of the BWB o...

21. [The Calendar Spread Options Strategy (and How to Build with Alpaca)](https://alpaca.markets/learn/calendar-spread) - A calendar spread is a strategy where a trader simultaneously sells a short-term option and buys a l...

22. [Bull put spread vs diagonal put spread.](https://www.reddit.com/r/thetagang/comments/12z8r4d/bull_put_spread_vs_diagonal_put_spread/)

23. [Swing Trading SPX Diagonal Spreads - YouTube](https://www.youtube.com/watch?v=wdgc3WIJVYY) - I love directional calendar spreads, but I've adjusted to the volatility by trading diagonals instea...

24. [1x2 Ratio Volatility Spread with Calls - Fidelity Investments](https://www.fidelity.com/learning-center/investment-products/options/options-strategy-guide/1x2-ratio-volatility-spread-calls) - A 1x2 ratio volatility spread with calls is created by selling one lower-strike call option and buyi...

25. [Gamma Trading Strategies: A Trader's Guide to Volatility - tastylive](https://www.tastylive.com/news-insights/gamma-trading-strategies-a-trader-s-guide-to-volatility) - Traders choose strategies based on whether they want positive gamma (benefit from movement) or negat...

26. [[Question] Custom action space with PPO #1046 - GitHub](https://github.com/DLR-RM/stable-baselines3/issues/1046) - Hello, is it possible to create a custom action space to use with PPO? From what I read in the docum...

27. [[1802.03042] Deep Hedging](https://arxiv.org/abs/1802.03042) - We discuss how standard reinforcement learning methods can be applied to non-linear reward structure...

28. [[PDF] DEEP HEDGING Key words and phrases: reinforcement learning ...](https://smallake.kr/wp-content/uploads/2022/07/SSRN-id3120710.pdf) - We discuss how standard reinforcement learning methods can be applied to non-linear reward structure...

29. [[PDF] Statistical Arbitrage in the U.S. Equities Market - Puppetmaster Trading](http://www.puppetmastertrading.com/images/AvellanedaLeeStatArb20090616.pdf) - That is, mean-reversion statistical arbitrage works better when we can explain 50% of the variance w...

30. [[PDF] Risk control of mean-reversion time in statistical arbitrage](http://math.stanford.edu/~papanico/pubftp/RDA_manuscript.pdf) - This paper deals with the risk associated with the mis-estimation of mean-reversion of resid- uals i...

31. [Compounding Effects in Leveraged ETFs: Beyond the Volatility Drag ...](https://arxiv.org/html/2504.20116v1) - In particular, momentum improves compounding, while mean reversion undermines it, with these effects...

