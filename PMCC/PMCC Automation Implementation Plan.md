# Poor Man's Covered Call (PMCC) — AI-Automated Trading System: Comprehensive Implementation Plan

## Executive Summary

The Poor Man's Covered Call (PMCC) is a capital-efficient diagonal call spread strategy that uses a deep in-the-money LEAPS call option as a stock replacement, combined with recurring short-term OTM call sales for income generation. This plan provides a complete technical specification for automating the PMCC strategy via the Interactive Brokers API, designed for handoff to Antigravity for implementation.[^1][^2]

The video by 天哥聊退休 covers the core PMCC mechanics using Tesla and NVIDIA as examples, emphasizing that the strategy requires active management and rolling—it is not "set and forget". The system must automate: (1) underlying selection, (2) LEAPS entry, (3) short call selling with technical analysis, (4) rolling management, (5) exit/risk management, and (6) portfolio-level oversight.

***

## Module 1: Underlying Asset Screening Engine

### 1.1 Candidate Universe

Filter the tradable universe to identify optimal PMCC candidates. The underlying must meet these criteria:[^2][^3]

- **Liquidity**: Average daily volume > 1M shares; options open interest > 500 contracts on target LEAPS strikes
- **Market Cap**: > $10B (large-cap bias for stability)
- **Sector Diversification**: Spread positions across at least 3 sectors
- **IV Rank**: Ideally buy LEAPS when IV Rank is below 30 (options are cheap relative to the past year). IV Rank formula: `(Current_IV - 52wk_Low_IV) / (52wk_High_IV - 52wk_Low_IV) × 100`[^4]
- **Trend Confirmation**: Stock must be in a neutral-to-bullish trend (above 200-day SMA, or in identifiable uptrend channel)
- **No Earnings Within 14 Days of Short Call Expiration**: Avoid gamma risk around earnings
- **Low/No Dividend**: LEAPS holders don't receive dividends; avoid high-yield stocks to reduce early assignment risk[^5][^2]
- **Options Bid-Ask Spread**: LEAPS bid-ask spread < 2% of option midprice

### 1.2 Scoring Algorithm

Score each candidate on a 0–100 scale:

| Factor | Weight | Scoring Logic |
|--------|--------|---------------|
| Options Liquidity | 25% | Open interest tiers: >5000 = 100, >2000 = 75, >500 = 50 |
| IV Rank | 20% | Below 30 = 100, 30-50 = 60, 50-70 = 30, >70 = 0 |
| Trend Score | 20% | Above 200 SMA + above 50 SMA = 100, above 200 only = 60 |
| Bid-Ask Tightness | 15% | < 0.5% = 100, < 1% = 75, < 2% = 50 |
| Sector Balance | 10% | Bonus for underrepresented sectors in portfolio |
| Fundamental Quality | 10% | Positive earnings, low debt-to-equity |

**Output**: Ranked list of top 10-15 candidates refreshed weekly.

### 1.3 Data Sources

```
- Stock data: IB API historical bars (reqHistoricalData)
- Options chains: IB API (reqSecDefOptParams + reqMktData)
- IV Rank: Calculate from IB historical volatility or use Barchart API
- Fundamentals: IB fundamentals or Yahoo Finance API
```

***

## Module 2: LEAPS Selection Engine (Long Leg)

### 2.1 Delta and Strike Selection

The consensus across professional sources is clear on LEAPS parameters:[^6][^7][^8][^1][^2]

| Parameter | Optimal Value | Range | Rationale |
|-----------|--------------|-------|-----------|
| **Delta** | **0.80** | 0.75–0.85 | Mimics stock ownership; moves ~$0.80 per $1 stock move |
| **DTE** | **365–730 days** | Min 180 days | Slow theta decay; allows 6-12+ short call cycles |
| **Strike** | Deep ITM | Varies | Minimize extrinsic (time) value component |
| **Extrinsic Value** | < 25% of option price | Target < 20% | Lower extrinsic = better stock replacement |

**Key Rule (BCI Methodology)**: The initial trade must satisfy this structuring formula:[^6]

```
(Short_Call_Strike - LEAPS_Strike) + Short_Call_Premium > Cost_of_LEAPS
```

This ensures the trade can achieve a net profit if the stock reaches the short call strike.

### 2.2 Selection Algorithm

```python
def select_leaps(symbol, current_price):
    """
    Select optimal LEAPS for PMCC long leg.
    
    Steps:
    1. Get all option expirations > 365 DTE
    2. For each expiration, find strikes where delta is 0.75-0.85
    3. Score by: lowest extrinsic value ratio, tightest bid-ask, highest OI
    4. Validate BCI structuring formula
    5. Return top candidate
    """
    
    target_delta = 0.80
    min_delta = 0.75
    max_delta = 0.85
    min_dte = 365
    max_dte = 730
    max_extrinsic_ratio = 0.25
    
    # Extrinsic value = Option Price - Intrinsic Value
    # Intrinsic Value = max(0, Current Price - Strike)
    # Extrinsic Ratio = Extrinsic / Option Price
    
    # Score = (1 - extrinsic_ratio) * 40 + liquidity_score * 30 + delta_proximity * 30
    # delta_proximity = 1 - abs(delta - 0.80) / 0.10
```

### 2.3 LEAPS Rolling Rules

Roll the LEAPS when remaining DTE drops to 90 days (BCI recommendation) or 180 days (conservative):[^7][^6]

- **Roll Trigger**: DTE ≤ 90 days remaining on LEAPS
- **Roll Target**: New LEAPS with 365-730 DTE, same delta criteria (0.80)
- **Cost Estimate**: Budget $2-3/share for roll cost (debit to roll forward)[^6]
- **Execution**: Sell existing LEAPS + Buy new LEAPS as a spread order

***

## Module 3: Short Call Selection Engine (Income Leg)

This is the most critical and active module. The video specifically argues against pure delta-based selection in favor of **technical resistance levels**.[^9]

### 3.1 Hybrid Strike Selection: Delta + Resistance

Combine delta guardrails with technical analysis for strike selection:[^1][^7][^9]

**Step 1 — Delta Guardrails**:
- Minimum delta: 0.15 (below this, premiums too small)[^1]
- Maximum delta: 0.35 (above this, assignment risk too high)[^1]
- Target delta zone: 0.20–0.30[^10][^7]

**Step 2 — Resistance Level Detection**:
The video's key insight: sell the short call at the nearest resistance level that falls within the delta guardrails. This gives the trade the "market's stop sign" — a price level where the stock is likely to stall.[^9]

Implement multiple resistance detection methods:

```python
def find_resistance_levels(symbol, lookback_days=120):
    """
    Multi-method resistance detection.
    Returns list of (price_level, strength_score) tuples.
    """
    
    levels = []
    
    # Method 1: Pivot Highs (swing highs)
    # Find candles higher than N neighbors on each side
    # N = 5 for daily chart
    pivot_highs = find_pivot_highs(data, left=5, right=5)
    
    # Method 2: Volume Profile (high-volume price zones)
    # Cluster prices where significant volume traded
    volume_nodes = calculate_volume_profile(data)
    
    # Method 3: Moving Average Resistance
    # 50-SMA, 200-SMA as dynamic resistance
    sma_levels = [sma_50[-1], sma_200[-1]]
    
    # Method 4: Fibonacci Retracement Levels
    # From recent swing low to swing high
    fib_levels = calculate_fibonacci(swing_low, swing_high)
    
    # Method 5: Round Number Resistance
    # Psychological levels ($100, $110, $120, etc.)
    round_levels = get_round_number_levels(current_price)
    
    # Score each level: count touches + recency + volume
    # Cluster nearby levels (within 1% of each other)
    # Return sorted by strength
    
    return scored_resistance_levels
```

**Step 3 — Trend-Aware Strike Adjustment** (from the video):[^9]

| Market Regime | Short Call Strike Strategy | Delta Target |
|---|---|---|
| **Uptrend** (higher highs + higher lows) | Sell at next resistance above current price | 0.20–0.25 (preserve upside) |
| **Sideways/Range** | Sell at top of range/channel | 0.25–0.30 (balanced) |
| **Downtrend** (lower highs + lower lows) | Sell ATM or near the money for max premium | 0.30–0.50 (aggressive income) |
| **At bottom of channel with expected bounce** | Sell at nearest overhead resistance | 0.25–0.35 (intermediate) |

### 3.2 DTE Selection for Short Call

Optimal DTE: **30–45 days** (sweet spot for theta decay):[^11][^7][^1]

- Time decay accelerates sharply around 45 DTE[^1]
- Minimum 21 DTE (avoid gamma risk of very short-dated options)
- Maximum 60 DTE (if needed to find a resistance-aligned strike)[^8]

### 3.3 Premium Minimum Threshold

Only sell the short call if premium meets a minimum return threshold:

```python
min_premium_pct = 0.01  # 1% of LEAPS cost per cycle
min_premium_absolute = max(0.50, leaps_cost * min_premium_pct)

# If no strikes meet the threshold, SKIP this cycle
# Better to wait than sell for negligible premium
```

### 3.4 Earnings and Ex-Dividend Check

Before selling any short call:[^2][^5]

```python
def is_safe_to_sell_call(symbol, expiration_date):
    earnings_date = get_next_earnings_date(symbol)
    ex_div_date = get_next_ex_dividend_date(symbol)
    
    # Don't sell if earnings falls before expiration
    if earnings_date and earnings_date <= expiration_date:
        return False, "Earnings within expiration window"
    
    # Don't sell if ex-dividend falls before expiration (assignment risk)
    if ex_div_date and ex_div_date <= expiration_date:
        return False, "Ex-dividend within expiration window"
    
    return True, "Clear to sell"
```

***

## Module 4: Position Management & Rolling Engine

### 4.1 Short Call Monitoring Rules

Run monitoring checks every 15 minutes during market hours:[^12][^13]

```python
class ShortCallMonitor:
    """
    Monitoring rules for the short call leg.
    Based on combined research from thetagang, BCI, and video strategy.
    """
    
    def check_position(self, position):
        current_delta = get_current_delta(position.short_call)
        current_pnl_pct = position.short_call_pnl / position.short_call_premium
        dte_remaining = position.short_call_dte_remaining
        
        # RULE 1: Profit Target - Close at 50-75% of max profit
        if current_pnl_pct >= 0.50:  # Collected 50%+ of premium
            return Action.CLOSE_SHORT_CALL, "Profit target reached"
        
        # RULE 2: Assignment Risk - Delta exceeds 0.50
        if current_delta >= 0.50:
            return Action.ROLL_UP_AND_OUT, "Delta breach - assignment risk"
        
        # RULE 3: Time Decay Exhaustion - DTE < 7
        if dte_remaining <= 7 and current_pnl_pct >= 0.30:
            return Action.CLOSE_AND_RESELL, "Approaching expiration"
        
        # RULE 4: Stop Loss - Position losing > 100% of premium received
        if current_pnl_pct <= -1.00:
            return Action.CLOSE_SHORT_CALL, "Stop loss triggered"
        
        # RULE 5: Trend Reversal Detection
        if detect_trend_reversal(position.symbol):
            return Action.EVALUATE_ADJUSTMENT, "Trend change detected"
        
        return Action.HOLD, "Within parameters"
```

### 4.2 Rolling Decision Matrix

When a short call needs to be rolled:[^14][^13][^12]

| Scenario | Action | Execution Details |
|---|---|---|
| **Short call ITM, stock rising** | Roll UP and OUT | Buy back short, sell higher strike + 30 more DTE. Must be for credit or minimal debit. |
| **Short call OTM, 50%+ profit** | Close and resell | Buy back short, sell new 30-45 DTE call at new resistance level |
| **Short call OTM, approaching expiration (< 7 DTE)** | Let expire or close for pennies, then resell | Sell new call next trading day |
| **Short call deep ITM, can't roll for credit** | Sell bull put spread to fund roll | Per video: sell put spread to generate credit, use it to fund rolling call up[^9] |
| **Stock in confirmed downtrend** | Sell ATM calls | Maximize premium collection; accept lower strike[^9] |
| **Stock at major support, bounce expected** | Sell at overhead resistance | Place short call at resistance level above current price[^9] |

### 4.3 Rolling Execution Logic

```python
def execute_roll(position, action, ib_client):
    """
    Execute roll as combo order for best fill.
    Always try for credit; accept small debit only if necessary.
    """
    if action == Action.ROLL_UP_AND_OUT:
        # Find new strike at resistance within delta 0.15-0.35
        new_strike = find_resistance_aligned_strike(
            symbol=position.symbol,
            min_delta=0.15,
            max_delta=0.35,
            min_dte=30,
            max_dte=60
        )
        
        # Create combo order: Buy old short + Sell new short
        combo = create_diagonal_roll_order(
            buy_contract=position.short_call_contract,
            sell_contract=new_strike.contract,
            order_type='LMT',
            limit_price=calculate_credit_target(position, new_strike)
        )
        
        # If can't fill for credit after 30 min, accept $0.00 net
        # If still can't fill, accept up to $0.50 debit per contract
        
        return ib_client.placeOrder(combo.contract, combo.order)
```

***

## Module 5: Risk Management System

### 5.1 Position-Level Risk Controls

```python
class PositionRiskManager:
    # Maximum loss per PMCC position
    MAX_LOSS_PER_POSITION_PCT = 0.50  # 50% of LEAPS cost
    
    # Stop loss on entire PMCC (both legs)
    TOTAL_POSITION_STOP_LOSS = -0.30  # Close if total P/L < -30%
    
    # Maximum delta exposure per position
    MAX_NET_DELTA = 0.85  # Don't let net delta exceed this
    
    # Minimum premium per cycle
    MIN_PREMIUM_PCT = 0.008  # 0.8% of LEAPS cost minimum per cycle
```

### 5.2 Portfolio-Level Risk Controls

```python
class PortfolioRiskManager:
    MAX_POSITIONS = 8  # Maximum concurrent PMCC positions
    MAX_CAPITAL_DEPLOYED = 0.60  # 60% of account in PMCC LEAPS
    CASH_RESERVE = 0.20  # 20% cash reserve for rolls and adjustments
    MAX_SINGLE_SECTOR = 0.30  # No more than 30% in one sector
    MAX_CORRELATED_POSITIONS = 3  # Max positions with correlation > 0.70
    
    def validate_new_position(self, new_position, portfolio):
        checks = [
            self.check_position_count(portfolio),
            self.check_capital_utilization(new_position, portfolio),
            self.check_sector_concentration(new_position, portfolio),
            self.check_correlation(new_position, portfolio),
            self.check_margin_requirements(new_position, portfolio),
        ]
        return all(checks)
```

### 5.3 Emergency Protocols

| Event | Automatic Response |
|---|---|
| **Stock drops > 15% in one day** | Alert + evaluate closing entire position |
| **Short call assigned early** | Exercise LEAPS to deliver shares, or buy shares + close LEAPS |
| **IV crush (post-earnings)** | Reassess LEAPS value; sell new short call at higher delta if needed |
| **Market-wide crash (VIX > 35)** | Halt new short call sales; protect LEAPS; consider protective puts |
| **LEAPS DTE < 60 and not rolled** | EMERGENCY: Roll LEAPS immediately or close position |

***

## Module 6: Technical Architecture

### 6.1 System Stack

```
┌─────────────────────────────────────────────────┐
│                  PMCC Trading Bot                 │
├──────────┬──────────┬───────────┬────────────────┤
│ Screener │ Selector │ Executor  │ Risk Manager   │
│ Module   │ Module   │ Module    │ Module         │
├──────────┴──────────┴───────────┴────────────────┤
│              Core Trading Engine                  │
├──────────────────────────────────────────────────┤
│         ib_insync (IB API Wrapper)               │
├──────────────────────────────────────────────────┤
│      Interactive Brokers TWS / IB Gateway        │
├──────────────────────────────────────────────────┤
│   PostgreSQL (Trades DB)  │  Redis (Real-time)   │
├──────────────────────────────────────────────────┤
│      Monitoring Dashboard (Streamlit/React)       │
└──────────────────────────────────────────────────┘
```

### 6.2 Technology Choices

| Component | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.11+ / TypeScript for dashboard | Your existing stack; ib_insync is Python |
| **Broker API** | ib_insync (IB API wrapper) | Simplified async IB interface[^15] |
| **Database** | PostgreSQL (RDS) | Trade logging, P/L tracking, position state |
| **Cache/Queue** | Redis | Real-time position state, alert queue |
| **Scheduler** | APScheduler or cron | Periodic checks every 15 min during market hours |
| **Technical Analysis** | pandas-ta, TA-Lib | Support/resistance, SMA, trend detection |
| **Hosting** | AWS EC2 (always-on) | Persistent connection to IB Gateway |
| **Alerting** | Twilio/Discord webhook | Critical alerts for assignment, stop loss |
| **Dashboard** | Streamlit or React + Next.js | Position monitoring, P/L visualization |

### 6.3 Database Schema

```sql
CREATE TABLE pmcc_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE',  -- ACTIVE, CLOSED, ROLLING
    
    -- Long Leg (LEAPS)
    leaps_strike DECIMAL(10,2),
    leaps_expiration DATE,
    leaps_delta DECIMAL(4,3),
    leaps_entry_price DECIMAL(10,2),
    leaps_current_price DECIMAL(10,2),
    leaps_contract_id INTEGER,
    
    -- Short Leg (Current Cycle)
    short_strike DECIMAL(10,2),
    short_expiration DATE,
    short_delta_at_entry DECIMAL(4,3),
    short_entry_premium DECIMAL(10,2),
    short_current_price DECIMAL(10,2),
    short_contract_id INTEGER,
    short_resistance_level DECIMAL(10,2),  -- The resistance level used
    
    -- Tracking
    total_premium_collected DECIMAL(10,2) DEFAULT 0,
    cycle_count INTEGER DEFAULT 0,
    effective_cost_basis DECIMAL(10,2),
    net_pnl DECIMAL(10,2),
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pmcc_short_call_history (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES pmcc_positions(id),
    strike DECIMAL(10,2),
    expiration DATE,
    entry_premium DECIMAL(10,2),
    exit_price DECIMAL(10,2),
    pnl DECIMAL(10,2),
    delta_at_entry DECIMAL(4,3),
    resistance_level_used DECIMAL(10,2),
    action_taken VARCHAR(30),  -- EXPIRED, CLOSED, ROLLED_UP, ROLLED_DOWN
    entry_date DATE,
    exit_date DATE
);

CREATE TABLE technical_levels (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    level_type VARCHAR(20),  -- RESISTANCE, SUPPORT
    price_level DECIMAL(10,2),
    strength_score INTEGER,  -- 0-100
    detection_method VARCHAR(30),  -- PIVOT, VOLUME_PROFILE, SMA, FIBONACCI
    last_tested DATE,
    times_tested INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6.4 Core Connection Setup with ib_insync

```python
from ib_insync import *
import asyncio

class PMCCBot:
    def __init__(self, host='127.0.0.1', port=4001, client_id=1):
        self.ib = IB()
        self.ib.connect(host, port, clientId=client_id)
        
        # Event handlers
        self.ib.orderStatusEvent += self.on_order_status
        self.ib.newOrderEvent += self.on_new_order
        self.ib.errorEvent += self.on_error
        
    def get_options_chain(self, symbol, min_dte=30, max_dte=730):
        """Retrieve full options chain with Greeks."""
        stock = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(stock)
        
        chains = self.ib.reqSecDefOptParams(
            stock.symbol, '', stock.secType, stock.conId
        )
        
        # Filter for desired DTE range and exchange
        target_chain = [c for c in chains if c.exchange == 'SMART']
        
        # Build option contracts and request market data
        contracts = []
        for chain in target_chain:
            for exp in chain.expirations:
                dte = (datetime.strptime(exp, '%Y%m%d') - datetime.now()).days
                if min_dte <= dte <= max_dte:
                    for strike in chain.strikes:
                        opt = Option(symbol, exp, strike, 'C', 'SMART')
                        contracts.append(opt)
        
        # Qualify and request tickers in batches
        self.ib.qualifyContracts(*contracts)
        tickers = self.ib.reqTickers(*contracts)
        
        return tickers
    
    def place_pmcc_entry(self, symbol, leaps_strike, leaps_exp, 
                          short_strike, short_exp):
        """Enter PMCC as diagonal spread combo order."""
        leaps = Option(symbol, leaps_exp, leaps_strike, 'C', 'SMART')
        short = Option(symbol, short_exp, short_strike, 'C', 'SMART')
        self.ib.qualifyContracts(leaps, short)
        
        # Create combo legs
        combo = Contract()
        combo.symbol = symbol
        combo.secType = 'BAG'
        combo.currency = 'USD'
        combo.exchange = 'SMART'
        
        leg1 = ComboLeg()
        leg1.conId = leaps.conId
        leg1.ratio = 1
        leg1.action = 'BUY'
        leg1.exchange = 'SMART'
        
        leg2 = ComboLeg()
        leg2.conId = short.conId
        leg2.ratio = 1
        leg2.action = 'SELL'
        leg2.exchange = 'SMART'
        
        combo.comboLegs = [leg1, leg2]
        
        # Place as limit order at midpoint
        order = LimitOrder('BUY', 1, net_debit_limit)
        trade = self.ib.placeOrder(combo, order)
        
        return trade
```

***

## Module 7: Scheduler & Workflow Orchestration

### 7.1 Daily Schedule

```python
SCHEDULE = {
    "06:00 ET": "Pre-market: Update technical levels for all symbols",
    "09:30 ET": "Market open: Check for new PMCC entry signals",
    "09:45 ET": "Execute any pending new positions",
    "10:00 ET": "Start 15-min monitoring loop for existing positions",
    "11:00 ET": "Mid-morning: Check for roll opportunities",
    "14:00 ET": "Afternoon: Evaluate short calls approaching expiration",
    "15:30 ET": "Pre-close: Final position check; handle expiration-day positions",
    "16:00 ET": "Market close: Log daily P/L, update database",
    "16:30 ET": "Post-market: Run screener for next day's candidates",
    "20:00 ET": "Evening: Generate daily report and alerts"
}
```

### 7.2 Weekly Tasks

- **Monday AM**: Refresh underlying screening scores; update watchlist
- **Friday PM**: Review all positions approaching next-week expiration; plan rolls
- **Sunday PM**: Run weekly performance report; rebalance sector allocation

***

## Module 8: Support/Resistance Detection Algorithm

This is the algorithmic implementation of the video's core thesis — sell at resistance, not at delta.[^9]

### 8.1 Multi-Method Detection

```python
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

class ResistanceFinder:
    def __init__(self, symbol, data):
        """
        data: DataFrame with OHLCV, minimum 120 days
        """
        self.symbol = symbol
        self.data = data
        self.levels = []
    
    def find_pivot_highs(self, order=5):
        """Find swing highs using local maxima detection."""
        highs = self.data['high'].values
        indices = argrelextrema(highs, np.greater, order=order)
        pivot_levels = [(highs[i], i) for i in indices]
        return pivot_levels
    
    def find_volume_clusters(self, num_bins=50):
        """Volume-weighted price levels (Volume Profile)."""
        price_range = np.linspace(
            self.data['low'].min(), 
            self.data['high'].max(), 
            num_bins
        )
        volume_at_price = np.zeros(num_bins)
        
        for _, row in self.data.iterrows():
            for i, price in enumerate(price_range[:-1]):
                if price <= row['high'] and price_range[i+1] >= row['low']:
                    volume_at_price[i] += row['volume'] / num_bins
        
        # High volume nodes above current price = resistance
        current_price = self.data['close'].iloc[-1]
        resistance_nodes = [
            (price_range[i], volume_at_price[i])
            for i in range(len(price_range))
            if price_range[i] > current_price
        ]
        return sorted(resistance_nodes, key=lambda x: -x[^1])[:5]
    
    def find_moving_average_resistance(self):
        """Dynamic resistance from key moving averages."""
        current = self.data['close'].iloc[-1]
        sma_50 = self.data['close'].rolling(50).mean().iloc[-1]
        sma_200 = self.data['close'].rolling(200).mean().iloc[-1]
        ema_21 = self.data['close'].ewm(span=21).mean().iloc[-1]
        
        levels = []
        for level, name in [(sma_50, 'SMA50'), (sma_200, 'SMA200'), (ema_21, 'EMA21')]:
            if level > current:  # Only resistance (above current price)
                levels.append((level, name))
        return levels
    
    def score_resistance_level(self, level, tolerance_pct=0.01):
        """
        Score a resistance level by:
        - Number of times price touched/bounced from level
        - Recency of last touch
        - Volume at level
        """
        tolerance = level * tolerance_pct
        touches = 0
        last_touch_idx = 0
        
        for i, row in self.data.iterrows():
            if abs(row['high'] - level) <= tolerance:
                touches += 1
                last_touch_idx = i
        
        recency_score = min(100, (len(self.data) - last_touch_idx) / len(self.data) * 100)
        touch_score = min(100, touches * 25)  # 4+ touches = max score
        
        return (touch_score * 0.6) + ((100 - recency_score) * 0.4)
    
    def get_best_resistance_for_short_call(self, current_price, option_chain):
        """
        Find the best strike to sell that aligns with resistance
        AND falls within delta 0.15-0.35.
        """
        # Get all resistance levels
        all_levels = self.aggregate_all_levels()
        
        # Filter option chain for delta 0.15-0.35
        valid_strikes = [
            opt for opt in option_chain
            if 0.15 <= abs(opt.delta) <= 0.35
        ]
        
        # For each valid strike, check proximity to resistance
        best_strike = None
        best_score = 0
        
        for strike_opt in valid_strikes:
            for level, strength in all_levels:
                proximity = abs(strike_opt.strike - level) / current_price
                if proximity < 0.02:  # Within 2% of resistance
                    combined_score = strength * 0.7 + (1 - proximity) * 0.3
                    if combined_score > best_score:
                        best_score = combined_score
                        best_strike = strike_opt
        
        # Fallback: if no resistance-aligned strike, use 0.25 delta
        if best_strike is None:
            best_strike = min(valid_strikes, 
                            key=lambda x: abs(abs(x.delta) - 0.25))
        
        return best_strike
```

***

## Module 9: Trend Detection for Adaptive Strategy

### 9.1 Trend Classification

```python
class TrendClassifier:
    """
    Classify market regime for adaptive short call strategy.
    Per the video: sell differently based on trend.
    """
    
    def classify(self, data):
        """Returns: UPTREND, DOWNTREND, SIDEWAYS"""
        
        # Higher highs and higher lows = uptrend
        swing_highs = find_pivot_highs(data)
        swing_lows = find_pivot_lows(data)
        
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]  # Higher high
            hl = swing_lows[-1] > swing_lows[-2]     # Higher low
            lh = swing_highs[-1] < swing_highs[-2]   # Lower high
            ll = swing_lows[-1] < swing_lows[-2]      # Lower low
            
            if hh and hl:
                return 'UPTREND'
            elif lh and ll:
                return 'DOWNTREND'
        
        # Check if price is within a channel (sideways)
        atr = calculate_atr(data, period=14)
        price_range = data['high'].rolling(20).max() - data['low'].rolling(20).min()
        
        if price_range.iloc[-1] < atr.iloc[-1] * 3:
            return 'SIDEWAYS'
        
        # Check SMA alignment
        sma_50 = data['close'].rolling(50).mean().iloc[-1]
        sma_200 = data['close'].rolling(200).mean().iloc[-1]
        current = data['close'].iloc[-1]
        
        if current > sma_50 > sma_200:
            return 'UPTREND'
        elif current < sma_50 < sma_200:
            return 'DOWNTREND'
        
        return 'SIDEWAYS'
    
    def get_short_call_strategy(self, trend):
        """Map trend to short call approach per video strategy."""
        strategies = {
            'UPTREND': {
                'target_delta': 0.20,
                'strike_method': 'RESISTANCE',
                'description': 'Sell at resistance, preserve upside'
            },
            'SIDEWAYS': {
                'target_delta': 0.25,
                'strike_method': 'RESISTANCE_OR_RANGE_TOP',
                'description': 'Sell at top of range'
            },
            'DOWNTREND': {
                'target_delta': 0.35,
                'strike_method': 'ATM_OR_NEAR',
                'description': 'Aggressive premium collection'
            }
        }
        return strategies.get(trend, strategies['SIDEWAYS'])
```

***

## Module 10: Performance Tracking & Reporting

### 10.1 Key Metrics to Track

| Metric | Formula | Target |
|---|---|---|
| **Premium Yield per Cycle** | Premium / LEAPS Cost | > 1.5% per 30-day cycle |
| **Annualized ROC** | (Total Premium / LEAPS Cost) × (365 / Days Held) | 20-40%[^2] |
| **Win Rate** | Profitable Cycles / Total Cycles | > 70% |
| **Cost Basis Reduction** | Cumulative Premium / Original LEAPS Cost | Track toward 100% |
| **Net Delta Exposure** | LEAPS Delta - Short Call Delta | 0.40–0.55[^16] |
| **Assignment Rate** | Assignments / Total Short Calls | < 5% |
| **Max Drawdown** | Largest peak-to-trough in position value | < 30% |

### 10.2 Automated Report (Daily Email/Discord)

```
═══════════════════════════════════════════
  PMCC Daily Report — {date}
═══════════════════════════════════════════

Portfolio Summary:
  Active Positions: 6/8
  Total Capital Deployed: $32,400 (54% of account)
  Cash Reserve: $14,200 (24%)
  
  Today's P/L: +$342
  MTD P/L: +$1,847
  YTD Premium Collected: $8,920
  
Position Details:
┌─────────┬──────────┬────────┬────────┬──────────┐
│ Symbol  │ LEAPS Δ  │ Short  │ Short  │ Cycle    │
│         │ Current  │ Strike │ DTE    │ P/L      │
├─────────┼──────────┼────────┼────────┼──────────┤
│ NVDA    │ 0.82     │ $145   │ 23d    │ +$180    │
│ AAPL    │ 0.79     │ $240   │ 31d    │ +$95     │
│ GLD     │ 0.84     │ $320   │ 18d    │ +$120    │
│ MSFT    │ 0.81     │ $470   │ 38d    │ -$45     │
│ QQQ     │ 0.78     │ $520   │ 12d    │ +$210    │
│ AMD     │ 0.80     │ $165   │ 28d    │ +$65     │
└─────────┴──────────┴────────┴────────┴──────────┘

Alerts:
  ⚠️ QQQ short call DTE < 14 — prepare to close/roll
  ✅ NVDA: 52% profit reached on short call — close candidate
═══════════════════════════════════════════
```

***

## Module 11: Backtesting Framework

### 11.1 Backtest Configuration

Before going live, backtest the strategy on 3-5 years of historical data:

```python
class PMCCBacktester:
    """
    Backtest PMCC strategy with configurable parameters.
    """
    
    def __init__(self, config):
        self.config = {
            'leaps_delta': 0.80,
            'leaps_dte': 365,
            'short_delta_range': (0.15, 0.35),
            'short_dte': 30,
            'profit_target': 0.50,     # Close at 50% premium collected
            'stop_loss': -1.00,        # Close at 100% loss of premium
            'use_resistance': True,    # Use resistance for strike selection
            'roll_at_delta': 0.50,     # Roll when short delta > 0.50
            'leaps_roll_dte': 90,      # Roll LEAPS at 90 DTE remaining
        }
        self.config.update(config)
    
    def run(self, symbol, start_date, end_date):
        """
        Simulate PMCC over historical period.
        Track: entry/exit dates, premium collected, rolling events, P/L.
        """
        # 1. Load historical option chain data (from CBOE or IB historical)
        # 2. Simulate LEAPS entry
        # 3. For each 30-day cycle:
        #    a. Select short call strike (delta or resistance method)
        #    b. Monitor daily: check profit target, stop loss, delta breach
        #    c. Execute roll or close as needed
        #    d. Log results
        # 4. Compare vs buy-and-hold, vs traditional covered call
        
        results = {
            'total_return': 0,
            'premium_collected': 0,
            'num_cycles': 0,
            'win_rate': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'vs_buy_and_hold': 0,
        }
        return results
```

### 11.2 Data Sources for Backtesting

- **Historical options data**: CBOE DataShop, OptionMetrics, or Polygon.io
- **Alternative**: Use IB API `reqHistoricalData` for recent history (limited to ~2 years)
- **Free option**: Reconstruct approximate deltas using Black-Scholes from historical stock + VIX data

***

## Module 12: Implementation Phases

### Phase 1 — Foundation (Week 1-2)
- Set up IB Gateway connection with ib_insync
- Build PostgreSQL schema and database layer
- Implement options chain data retrieval
- Build underlying screening module
- Paper trading account setup

### Phase 2 — Core Strategy (Week 3-4)
- Implement LEAPS selection algorithm
- Build support/resistance detection engine
- Implement trend classification
- Build short call selection with hybrid delta + resistance logic
- Implement BCI structuring formula validation

### Phase 3 — Management Engine (Week 5-6)
- Build position monitoring loop (15-min checks)
- Implement rolling decision matrix
- Build profit target and stop loss automation
- Implement LEAPS rolling logic
- Assignment handling procedures

### Phase 4 — Risk & Reporting (Week 7-8)
- Portfolio-level risk controls
- Emergency protocols
- Daily/weekly reporting system
- Discord/email alert integration
- Dashboard (Streamlit or React)

### Phase 5 — Testing & Go-Live (Week 9-12)
- Backtest on 3+ years of historical data
- Paper trade for minimum 4-8 weeks
- Validate all rolling and edge case scenarios
- Gradual live deployment (start with 1-2 positions)
- Scale to full portfolio over 4-6 weeks

***

## Appendix A: Quick Reference Parameters

| Parameter | Value | Source |
|---|---|---|
| LEAPS Delta | 0.75–0.85 (target 0.80) | [^1][^6][^7][^2] |
| LEAPS DTE | 365–730 days | [^7][^2] |
| LEAPS Roll Trigger | 90 DTE remaining | [^6] |
| Short Call Delta | 0.15–0.35 (target resistance-aligned) | [^1][^7][^9] |
| Short Call DTE | 30–45 days | [^1][^7][^11] |
| Profit Target | 50% of premium collected | [^13] |
| Stop Loss | 100% of premium received | [^13] |
| Max Positions | 6–8 concurrent | Portfolio rule |
| Max Capital Deployed | 60% of account | Risk management |
| Cash Reserve | 20% minimum | For rolls/adjustments |
| IV Rank Entry (LEAPS) | Below 30 preferred | [^4] |
| BCI Formula | (Short Strike - LEAPS Strike) + Premium > LEAPS Cost | [^6] |
| Assignment Delta Trigger | Short call delta > 0.50 → roll | Best practice |

## Appendix B: Key Insight from Video — Resistance > Delta

The most differentiated insight from the 天哥聊退休 video and corroborated by the "Why Delta Fails in PMCCs" analysis: **do not blindly sell short calls at a fixed delta**. Instead:[^9]

1. Identify the nearest **resistance level** above the current stock price
2. Verify that a strike at or near that resistance falls within the **0.15–0.35 delta range**
3. If yes → sell at resistance-aligned strike
4. If no resistance within delta range → fall back to 0.25 delta (balanced default)
5. In confirmed **downtrends**, override to ATM/near-the-money for maximum premium

The analogy from the video: delta is a speed bump (cars slow down but don't stop); resistance is a stop sign (the stock is more likely to pause or reverse there). Always sell your short call at the market's stop sign.[^9]

---

## References

1. [Poor Man's Covered Call: Beginner's Visual Guide - TradingBlock](https://www.tradingblock.com/strategies/poor-mans-covered-call-pmcc) - PMCC: The long LEAPS call increases in value as delta approaches 1, while the short call expires nea...

2. [Poor Man's Covered Calls: The Definitive Guide to Smarter Options ...](https://www.theoptionpremium.com/p/poor-mans-covered-calls-the-definitive-guide) - The net effect is a favorable setup: slow decay on your long position, fast decay on the short posit...

3. [Poor Man's Covered Call | Blog](https://optionsamurai.com/blog/poor-mans-covered-call/) - The Poor Man's Covered Call (PMCC) is basically an option trading strategy that uses call options to...

4. [IV Rank vs IV Percentile: A Complete Guide to Options Volatility](https://www.barchart.com/education/iv_rank_vs_iv_percentile) - Look for low readings in both metrics (under 30); Pay special attention to IV Rank for timing entrie...

5. [The Poor Man's Covered Call: Rolling Options in the Current ...](https://www.thebluecollarinvestor.com/the-poor-mans-covered-call-rolling-options-in-the-current-contract-month-15-holiday-discount-expiring-soon/) - In this article, we will evaluate scenarios when share price both declines and accelerates creating ...

6. [Poor Man's Covered Call: Selecting the Best LEAPS Strike](https://www.thebluecollarinvestor.com/poor-mans-covered-call-selecting-the-best-leaps-strike/) - In the BCI methodology, we use Deltas between 75 and 100 and consider the PMCC a long-term strategy....

7. [The Poor Man's Covered Call for Bullish Long-Term Positions](https://optionstradingiq.substack.com/p/leaps-strategy-the-poor-mans-covered) - Delta: Sell calls at 25-35 delta - This is more aggressive than traditional covered calls (which typ...

8. [A Step-by-Step Approach to Poor Man's Covered Calls](https://www.cabotwealth.com/premium/cabot-options-institute-fundamentals/extra/a-step-by-step-approach-to-poor-mans-covered-calls) - An alternative way to approach a poor man's covered call, if you are a bit more bullish on the stock...

9. [Why Delta Fails in PMCCs — The Real Strike Strategy - YouTube](https://www.youtube.com/watch?v=q7dHzt9WlpE&vl=en) - 20% Off off Annual Memberships! Join my Patreon: https://www.patreon.com/mylifeoflearning My Options...

10. [Lets talk about PMCC & how to select strike for CCs : r/Optionswheel](https://www.reddit.com/r/Optionswheel/comments/1n1j41r/lets_talk_about_pmcc_how_to_select_strike_for_ccs/) - the long deltas don't move as fast as the short options. when your short call goes in the money, it ...

11. [Poor Man's Covered Call | Option Alpha Guide](https://optionalpha.com/learn/poor-mans-covered-call) - A poor man's covered call is an excellent options strategy for bullish investors that want to conser...

12. [For those running the PMCC, when do you roll the short leg? - Reddit](https://www.reddit.com/r/thetagang/comments/1k9cpbh/for_those_running_the_pmcc_when_do_you_roll_the/) - Here are my pmcc rules-. Short call. ITM- roll or buy back at 100%. Cap your loss. OTM- roll or buy ...

13. [Poor Man's Covered Call Strategy Guide & Examples](https://frameworkinvesting.com/poor-mans-covered-call-the-ultimate-guide-to-this-cost-effective-options-strategy/) - Risk Management. Establish exit points based on: Maximum acceptable loss (often 50-100% of the initi...

14. [What is a Poor Man's Covered Call and How Does it Work?](https://www.piranhaprofits.com/blog/poor-mans-covered-call) - To avoid this, you can “roll” the call option by buying back the current short call and selling a ne...

15. [ib_insync Guide - Interactive Brokers API - AlgoTrading101 Blog](https://algotrading101.com/learn/ib_insync-interactive-brokers-api-guide/) - ib_insync is a framework that simplifies the Interactive Brokers (IB) Native Python API that was dev...

16. [Poor Man's Covered Call: Overview, Example, Uses, Trading Guide ...](https://www.strike.money/options/poor-mans-covered-call) - The strategy profits most when the underlying stock price rises gradually toward the short call stri...

