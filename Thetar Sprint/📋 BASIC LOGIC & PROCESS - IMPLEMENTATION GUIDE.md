<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# 📋 BASIC LOGIC \& PROCESS - IMPLEMENTATION GUIDE

Let me break down the complete system into understandable, implementable logic flows:

***

## 🎯 SYSTEM OVERVIEW

```
MARKET DATA → SYMBOL SELECTION → OPTIONS ANALYSIS → SIGNAL GENERATION → EXECUTION → MONITORING → EXITS → REDEPLOYMENT
```


***

## 🔧 PART 1: SYMBOL SELECTION LOGIC

### Step 1.1: Collect Market Data for Candidates

```
For each of 50+ candidate symbols:
├─ Get IV percentile (IB API)
├─ Get 20-day average volume (IB API)
├─ Get bid-ask spread (current quotes)
├─ Get current price and SMA200 (technical)
├─ Get RSI (technical)
├─ Get current sector exposure from portfolio
└─ Store all data for scoring
```


### Step 1.2: Score Each Symbol (5 Factors)

```python
# Pseudocode for scoring

for symbol in candidates:
    score = 0
    
    # Factor 1: IV Percentile (0-30 points)
    if iv_percentile >= 70:
        score += 30
    elif iv_percentile >= 50:
        score += 25
    elif iv_percentile >= 30:
        score += 20
    elif iv_percentile >= 20:
        score += 10
    else:
        continue  # Skip (low premiums)
    
    # Factor 2: Liquidity (0-25 points)
    if volume >= 5M and spread < 0.05:
        score += 25
    elif volume >= 2M and spread < 0.08:
        score += 20
    elif volume >= 1M and spread < 0.10:
        score += 15
    elif volume >= 500K and spread < 0.15:
        score += 10
    else:
        score += 5
    
    # Factor 3: Premium Availability (0-20 points)
    puts_with_30delta = count_puts_in_range(symbol, delta=0.25-0.35)
    if puts_with_30delta >= 3:
        score += 20
    elif puts_with_30delta == 2:
        score += 15
    elif puts_with_30delta == 1:
        score += 10
    else:
        score += 0
    
    # Factor 4: Technical Trend (0-15 points)
    trend = detect_trend(symbol)
    price_vs_sma = current_price / sma200
    rsi = get_rsi(symbol)
    
    if trend == "UPTREND" and price_vs_sma > 1.0 and rsi < 70:
        score += 15
    elif trend == "UPTREND" and price_vs_sma > 1.0:
        score += 12
    elif trend == "SIDEWAYS" and price_vs_sma > 0.95:
        score += 8
    elif trend == "DOWNTREND":
        score += 0
    
    # Factor 5: Sector Diversification (0-10 points)
    current_sector_exposure = check_portfolio_sector(symbol)
    if current_sector_exposure < 15%:
        score += 10
    elif current_sector_exposure < 20%:
        score += 5
    elif current_sector_exposure < 25%:
        score += 2
    else:
        score += 0
    
    symbol_scores[symbol] = score
```


### Step 1.3: Apply Filters

```python
# Filter out symbols that don't meet criteria

filtered_symbols = []

for symbol, score in symbol_scores.items():
    
    # Check 1: Pre-earnings within 21 days?
    if days_to_earnings < 21:
        continue  # Skip
    
    # Check 2: Low volume today?
    if today_volume < 100K:
        continue  # Skip
    
    # Check 3: Score high enough?
    if score < 40:  # Arbitrary minimum
        continue  # Skip
    
    filtered_symbols.append((symbol, score))

# Sort by score (highest first)
ranked_symbols = sorted(filtered_symbols, key=lambda x: x[1], reverse=True)

# Select top 12
final_watchlist = ranked_symbols[:12]
```


### Step 1.4: Result = Daily Watchlist

```
OUTPUT: 12 best symbols for TODAY

Example:
1. QQQ - Score 87 (tech, high IV, liquid)
2. SPY - Score 85 (broad market, trending up)
3. IWM - Score 82 (small cap, good premium)
4. TLT - Score 81 (bonds, high theta)
5. USO - Score 78 (commodity, volatile)
6. XLV - Score 76 (healthcare sector)
7. XLK - Score 74 (tech sector)
8. GLD - Score 72 (gold, defensive)
9. IEF - Score 71 (intermediate bonds)
10. EEM - Score 68 (international, EM)
11. VXX - Score 65 (volatility)
12. DBC - Score 61 (commodities basket)
```


***

## 🎲 PART 2: OPTIONS CHAIN ANALYSIS

### Step 2.1: Get Options Chain for Each Symbol

```python
# For each of the 12 symbols:

for symbol in watchlist:
    
    # Get next expiration (3rd Friday of month)
    expiration_date = get_third_friday()
    
    # Get all puts for that expiration
    options_chain = ib_api.get_options_chain(
        symbol=symbol,
        expiration_date=expiration_date
    )
    
    # Filter to qualifying puts
    qualified_puts = []
    
    for put in options_chain['puts']:
        
        # Must be between 28-35 days to expiration
        if not (28 <= put['days_to_exp'] <= 35):
            continue
        
        # Must be 30-delta (±5%)
        if not (0.25 <= abs(put['delta']) <= 0.35):
            continue
        
        # Must have reasonable premium (>$0.50)
        if put['bid_price'] < 0.50:
            continue
        
        # Must have decent liquidity
        if put['volume'] < 50 and put['open_interest'] < 500:
            continue
        
        # Must have tight spread (<10%)
        spread_pct = (put['ask'] - put['bid']) / put['mid']
        if spread_pct > 0.10:
            continue
        
        # Passed all filters - add to qualified list
        qualified_puts.append(put)
    
    # Store for this symbol
    options_by_symbol[symbol] = qualified_puts
```


### Step 2.2: Score Each Put (0-100)

```python
# For each qualified put, calculate confidence score

for symbol, puts in options_by_symbol.items():
    
    symbol_base_score = symbol_scores[symbol]  # Use from Step 1
    
    for put in puts:
        
        score = symbol_base_score  # Start with symbol score
        
        # Factor 1: Delta Precision (0-30 points)
        delta_distance = abs(abs(put['delta']) - 0.30)
        if delta_distance < 0.01:
            score += 30  # Perfect 0.30
        elif delta_distance < 0.02:
            score += 27
        elif delta_distance < 0.03:
            score += 24
        elif delta_distance < 0.05:
            score += 20
        else:
            score += 10
        
        # Factor 2: Premium Quality (0-25 points)
        bid_price = put['bid_price']
        if bid_price >= 1.00:
            score += 25
        elif bid_price >= 0.75:
            score += 22
        elif bid_price >= 0.50:
            score += 18
        elif bid_price >= 0.30:
            score += 10
        else:
            score += 5
        
        # Factor 3: Time Decay / Theta (0-20 points)
        theta = put['theta']
        if theta >= 0.02:
            score += 20
        elif theta >= 0.015:
            score += 16
        elif theta >= 0.01:
            score += 12
        else:
            score += 5
        
        # Factor 4: Liquidity (0-15 points)
        spread_pct = (put['ask'] - put['bid']) / put['mid']
        volume = put['volume']
        
        if volume >= 500 and spread_pct < 0.02:
            score += 15
        elif volume >= 100 and spread_pct < 0.05:
            score += 12
        elif volume >= 50 and spread_pct < 0.08:
            score += 8
        else:
            score += 3
        
        # Factor 5: Vega (0-10 points) - Lower is better
        vega = put['vega']
        if vega < -0.05:
            score += 10
        elif vega < -0.08:
            score += 8
        elif vega < -0.12:
            score += 5
        else:
            score += 2
        
        # Cap at 100
        put['confidence_score'] = min(score, 100)
```


### Step 2.3: Rank All Puts

```python
# Collect all puts from all symbols
all_puts = []

for symbol, puts in options_by_symbol.items():
    for put in puts:
        all_puts.append({
            'symbol': symbol,
            'strike': put['strike'],
            'bid': put['bid_price'],
            'delta': put['delta'],
            'theta': put['theta'],
            'confidence': put['confidence_score'],
            'days_to_exp': put['days_to_exp'],
        })

# Sort by confidence score (highest first)
ranked_puts = sorted(all_puts, key=lambda x: x['confidence'], reverse=True)

# Result: Top 30-50 puts ranked by confidence
```


***

## 💰 PART 3: ENTRY SIGNAL GENERATION

### Step 3.1: Apply Capital Allocation Rules

```python
# Determine which puts can actually be traded

executable_signals = []
capital_used = 0
positions_opened = 0

for put in ranked_puts:
    
    # Calculate capital needed
    contracts = 10  # Per trade
    strike = put['strike']
    capital_needed = strike * 100 * contracts
    
    # Check 1: Capital available?
    cash_remaining = portfolio['cash_available'] - capital_used
    if cash_remaining < capital_needed:
        continue  # Skip - not enough cash
    
    # Check 2: Max positions reached?
    if positions_opened >= 6:  # Max 6 simultaneous
        continue  # Skip
    
    # Check 3: Would exceed portfolio heat (max at risk)?
    current_heat = portfolio['capital_reserved']
    if (current_heat + capital_needed) > 50000:  # Max $50K at risk
        continue  # Skip
    
    # Check 4: Confidence high enough?
    if put['confidence'] < 60:  # Minimum confidence threshold
        continue  # Skip
    
    # Check 5: Already trading this symbol/strike?
    if is_already_trading(put['symbol'], put['strike']):
        continue  # Skip
    
    # Passed all checks - create signal
    signal = {
        'action': 'SELL_TO_OPEN',
        'symbol': put['symbol'],
        'strike': put['strike'],
        'entry_price': put['bid'],
        'contracts': contracts,
        'confidence': put['confidence'],
        'capital_required': capital_needed,
        'expected_profit': put['bid'] * 100 * contracts,
        'probability_profit': abs(put['delta']),  # ~70% for 0.30 delta
    }
    
    executable_signals.append(signal)
    capital_used += capital_needed
    positions_opened += 1

# Sort by confidence (highest first)
executable_signals = sorted(executable_signals, key=lambda x: x['confidence'], reverse=True)

# Result: 6-8 executable signals, ranked by confidence
```


### Step 3.2: Display Execution Plan

```
EXECUTION PLAN - 09:45 AM
================================================================
#  Symbol  Strike    Bid     Delta    Conf    Capital
================================================================
1  QQQ     380      1.15    -0.30    87/100  $380,000
2  SPY     590      0.95    -0.29    84/100  $590,000
3  TLT     87       0.76    -0.30    81/100  $87,000
4  IWM     210      0.65    -0.31    78/100  $210,000
5  USO     72       0.55    -0.29    75/100  $72,000
6  XLV     110      0.45    -0.30    72/100  $110,000
================================================================
Total Capital Required: $1,449,000
Available Cash: $1,500,000
Ready to Execute? YES
```


***

## 🎬 PART 4: EXECUTION LOGIC

### Step 4.1: Execute Entry Signal

```python
# For each signal, place order

def execute_entry_signal(signal):
    
    # Create order
    order = {
        'type': 'SELL_TO_OPEN',
        'symbol': signal['symbol'],
        'strike': signal['strike'],
        'option_type': 'PUT',
        'contracts': signal['contracts'],
        'limit_price': signal['entry_price'] * 0.98,  # 2% below bid
        'time_in_force': 'DAY',
    }
    
    # Submit to Interactive Brokers
    order_id = ib_api.place_order(order)
    
    # Track the order
    order_tracking[order_id] = {
        'symbol': signal['symbol'],
        'strike': signal['strike'],
        'entry_price': signal['entry_price'],
        'contracts': signal['contracts'],
        'timestamp': datetime.now(),
        'status': 'PENDING',
    }
    
    return order_id
```


### Step 4.2: Wait for Fill

```python
# Monitor for order fill

while order_status != 'FILLED':
    
    # Check IB for fill status
    order_info = ib_api.get_order_status(order_id)
    
    if order_info['status'] == 'FILLED':
        
        # Create position record
        position = {
            'position_id': generate_id(),
            'symbol': order_info['symbol'],
            'strike': order_info['strike'],
            'entry_price': order_info['fill_price'],
            'entry_time': order_info['fill_time'],
            'contracts': order_info['contracts'],
            'capital_reserved': order_info['strike'] * 100 * order_info['contracts'],
            'status': 'OPEN',
            'entry_timestamp': datetime.now(),
        }
        
        # Add to portfolio
        portfolio['positions'][position['position_id']] = position
        
        # Subtract from available cash
        portfolio['cash_available'] -= position['capital_reserved']
        portfolio['cash_reserved'] += position['capital_reserved']
        
        # Send alert
        send_slack(f"✓ Opened {symbol} {strike} - ${fill_price} per contract")
        
        break
    
    # If not filled after 15 minutes, cancel
    if (datetime.now() - order_tracking[order_id]['timestamp']).seconds > 900:
        ib_api.cancel_order(order_id)
        break
    
    time.sleep(30)  # Check every 30 seconds
```


***

## 📊 PART 5: CONTINUOUS MONITORING

### Step 5.1: Monitor Loop (Every 60 Seconds)

```python
# This runs continuously during market hours

while market_is_open():
    
    # Get current time
    current_time = datetime.now()
    
    # For each open position
    for position_id, position in portfolio['positions'].items():
        
        if position['status'] != 'OPEN':
            continue  # Skip closed positions
        
        # Step 1: Get current option price
        current_data = ib_api.get_option_data(
            symbol=position['symbol'],
            strike=position['strike'],
            expiration=position['expiration']
        )
        
        # Step 2: Update position metrics
        position['current_price'] = current_data['mid_price']
        position['current_delta'] = current_data['delta']
        position['current_theta'] = current_data['theta']
        position['underlying_price'] = current_data['underlying_price']
        
        # Step 3: Calculate unrealized P&L
        entry = position['entry_price']
        current = current_data['mid_price']
        
        profit_dollars = (entry - current) * 100 * position['contracts']
        profit_pct = ((entry - current) / entry) * 100
        
        position['unrealized_pnl'] = profit_dollars
        position['unrealized_pnl_pct'] = profit_pct
        
        # Step 4: Calculate days in trade
        days_in_trade = (current_time - position['entry_timestamp']).days
        position['days_in_trade'] = days_in_trade
    
    # After updating all positions, check for exits
    exit_signals = check_for_exits(portfolio)
    
    if exit_signals:
        for signal in exit_signals:
            execute_exit(signal)
    
    # Sleep 60 seconds before next check
    time.sleep(60)
```


***

## 🚪 PART 6: EXIT SIGNAL GENERATION

### Step 6.1: Check Exit Conditions

```python
# THE HEART OF THE SYSTEM - TIME-BASED EXITS!

def check_for_exits(portfolio):
    
    exit_signals = []
    
    # Exit matrix (TIME-BASED!)
    exit_targets = {
        'WEEK_1': {'days': (1, 7), 'profit_pct': 50},
        'WEEK_2': {'days': (8, 14), 'profit_pct': 60},
        'WEEK_3': {'days': (15, 21), 'profit_pct': 75},
        'WEEK_4': {'days': (22, 28), 'profit_pct': 90},
    }
    
    for position_id, position in portfolio['positions'].items():
        
        if position['status'] != 'OPEN':
            continue
        
        days_in = position['days_in_trade']
        profit_pct = position['unrealized_pnl_pct']
        days_remaining = position['days_to_expiration']
        underlying = position['underlying_price']
        strike = position['strike']
        
        # Determine which week
        if days_in <= 7:
            current_week = 'WEEK_1'
        elif days_in <= 14:
            current_week = 'WEEK_2'
        elif days_in <= 21:
            current_week = 'WEEK_3'
        else:
            current_week = 'WEEK_4'
        
        required_profit = exit_targets[current_week]['profit_pct']
        
        # EXIT CONDITION 1: Profit target met?
        if profit_pct >= required_profit:
            
            exit_signal = {
                'action': 'BUY_TO_CLOSE',
                'position_id': position_id,
                'symbol': position['symbol'],
                'strike': position['strike'],
                'exit_price': position['current_price'],
                'profit_dollars': position['unrealized_pnl'],
                'profit_pct': profit_pct,
                'reason': f'PROFIT_TARGET ({current_week}: {profit_pct:.1f}% >= {required_profit}%)',
                'urgency': 'HIGH',
            }
            exit_signals.append(exit_signal)
            continue
        
        # EXIT CONDITION 2: Expiration imminent?
        if days_remaining <= 1:
            
            exit_signal = {
                'action': 'BUY_TO_CLOSE',
                'position_id': position_id,
                'symbol': position['symbol'],
                'strike': position['strike'],
                'exit_price': position['current_price'],
                'profit_dollars': position['unrealized_pnl'],
                'profit_pct': profit_pct,
                'reason': 'EXPIRATION_IMMINENT',
                'urgency': 'CRITICAL',
            }
            exit_signals.append(exit_signal)
            continue
        
        # EXIT CONDITION 3: Underlying breached (defensive)?
        # If underlying drops 2% below strike = risk of assignment
        if underlying < (strike * 0.98):
            
            exit_signal = {
                'action': 'BUY_TO_CLOSE',
                'position_id': position_id,
                'symbol': position['symbol'],
                'strike': position['strike'],
                'exit_price': position['current_price'],
                'profit_dollars': position['unrealized_pnl'],
                'profit_pct': profit_pct,
                'reason': 'DEFENSIVE_CLOSE (Underlying breach)',
                'urgency': 'MEDIUM',
            }
            exit_signals.append(exit_signal)
    
    return exit_signals
```


***

## 💫 PART 7: EXIT EXECUTION

### Step 7.1: Execute Exit

```python
def execute_exit(exit_signal):
    
    position_id = exit_signal['position_id']
    position = portfolio['positions'][position_id]
    
    # Create order
    order = {
        'type': 'BUY_TO_CLOSE',
        'symbol': exit_signal['symbol'],
        'strike': exit_signal['strike'],
        'contracts': position['contracts'],
        'limit_price': exit_signal['exit_price'] * 1.02,  # 2% above ask
        'time_in_force': 'DAY',
    }
    
    # Execute
    order_id = ib_api.place_order(order)
    
    # Wait for fill
    while True:
        order_info = ib_api.get_order_status(order_id)
        
        if order_info['status'] == 'FILLED':
            
            # Close position
            position['exit_price'] = order_info['fill_price']
            position['exit_time'] = order_info['fill_time']
            position['realized_pnl'] = exit_signal['profit_dollars']
            position['status'] = 'CLOSED'
            
            # Release capital
            capital_freed = position['capital_reserved']
            portfolio['cash_available'] += capital_freed
            portfolio['cash_reserved'] -= capital_freed
            
            # Update daily P&L
            portfolio['daily_pnl'] += exit_signal['profit_dollars']
            
            # Send alert
            send_slack(
                f"✓ Exited {exit_signal['symbol']} {exit_signal['strike']}\n"
                f"Profit: ${exit_signal['profit_dollars']:,.0f} ({exit_signal['profit_pct']:.1f}%)\n"
                f"Held: {position['days_in_trade']} days\n"
                f"Reason: {exit_signal['reason']}"
            )
            
            # Move to closed positions
            portfolio['trade_history'].append(position)
            del portfolio['positions'][position_id]
            
            break
        
        time.sleep(10)
```


***

## 🔄 PART 8: CAPITAL REDEPLOYMENT

### Step 8.1: Scan for Replacement

```python
def redeploy_capital():
    
    # Just exited a trade, capital is now free
    # Immediately scan for replacement opportunities
    
    # Step 1: Get freed capital amount
    freed_capital = portfolio['cash_available']
    
    if freed_capital < 50000:  # Minimum needed
        return  # Not enough for new trade
    
    # Step 2: Get current ranked puts
    ranked_puts = get_current_ranked_puts()  # From earlier analysis
    
    # Step 3: Find best unused put
    for put in ranked_puts:
        
        capital_needed = put['strike'] * 100 * 10
        
        if capital_needed > freed_capital:
            continue  # Skip - too expensive
        
        if is_already_trading(put['symbol'], put['strike']):
            continue  # Skip - already trading
        
        if len(portfolio['positions']) >= 6:
            continue  # Skip - max positions
        
        # Found a good replacement!
        new_signal = {
            'action': 'SELL_TO_OPEN',
            'symbol': put['symbol'],
            'strike': put['strike'],
            'entry_price': put['bid'],
            'confidence': put['confidence'],
            'capital_required': capital_needed,
        }
        
        # Execute immediately
        execute_entry_signal(new_signal)
        
        send_slack(f"🔄 Capital redeployed: {put['symbol']} {put['strike']}")
        
        break
```


***

## 📈 PART 9: DAILY REPORTING

### Step 9.1: Generate Daily Report

```python
def generate_end_of_day_report():
    
    report = f"""
    
DAILY REPORT - {datetime.now().strftime('%Y-%m-%d')}
{'='*60}

PORTFOLIO SUMMARY
{'-'*60}
Open Positions:      {len(portfolio['positions'])}
Cash Available:      ${portfolio['cash_available']:,.0f}
Cash Reserved:       ${portfolio['cash_reserved']:,.0f}
Total Equity:        ${portfolio['total_equity']:,.0f}
Utilization:         {(portfolio['cash_reserved']/portfolio['total_equity']*100):.1f}%

DAILY PERFORMANCE
{'-'*60}
Realized P&L:        ${portfolio['daily_pnl']:,.0f}
Unrealized P&L:      ${sum(p['unrealized_pnl'] for p in portfolio['positions'].values()):,.0f}
Total P&L:           ${portfolio['daily_pnl'] + sum(p['unrealized_pnl'] for p in portfolio['positions'].values()):,.0f}
Return %:            {((portfolio['daily_pnl'] + sum(p['unrealized_pnl'] for p in portfolio['positions'].values())) / portfolio['total_equity'] * 100):.2f}%

TODAY'S ACTIVITY
{'-'*60}
Entries:             {count_today_entries()}
Exits:               {count_today_exits()}
Win Rate:            {calculate_win_rate()}%
Avg Hold Time:       {calculate_avg_hold_time():.1f} days

OPEN POSITIONS
{'-'*60}
"""
    
    for pos in portfolio['positions'].values():
        report += f"""
{pos['symbol']} {pos['strike']}
  Entry:     ${pos['entry_price']:.2f}  ({pos['days_in_trade']}d ago)
  Current:   ${pos['current_price']:.2f}
  P&L:       ${pos['unrealized_pnl']:,.0f} ({pos['unrealized_pnl_pct']:.1f}%)
  Target:    {get_exit_target(pos['days_in_trade'])}%
"""
    
    # Send report
    send_slack(report)
    send_email(report)
    
    return report
```


***

## 🎯 COMPLETE FLOW SUMMARY

```
9:30 AM
└─ Market opens
   └─ Data starts flowing

9:45 AM (MORNING ANALYSIS)
├─ STEP 1: Select 12 best symbols
│  ├─ Score 50+ candidates (5 factors)
│  ├─ Apply filters (earnings, vol, IV)
│  └─ Output: Top 12
│
├─ STEP 2: Analyze options for 12 symbols
│  ├─ Get options chains
│  ├─ Filter to 30-delta puts
│  ├─ Score each put (0-100)
│  └─ Output: 100+ ranked puts
│
├─ STEP 3: Generate entry signals
│  ├─ Apply capital rules
│  ├─ Allocate positions
│  └─ Output: 6-8 executable signals
│
└─ STEP 4: Display execution plan
   └─ Wait for trader approval

10:00 AM (EXECUTION)
├─ Execute 6-8 entry signals
│  └─ SELL_TO_OPEN orders placed
│
└─ Positions added to portfolio
   └─ Capital reserved

10:05 AM - 3:55 PM (CONTINUOUS MONITORING)
├─ Every 60 seconds:
│  ├─ Update Greeks for all positions
│  ├─ Calculate P&L
│  ├─ Check exit conditions
│  │
│  └─ IF EXIT CONDITION MET:
│     ├─ Generate exit signal
│     ├─ Execute BUY_TO_CLOSE
│     ├─ Book profit
│     ├─ Release capital
│     │
│     └─ IMMEDIATELY:
│        └─ Scan for replacement
│           └─ REDEPLOY capital
│              └─ Execute new SELL_TO_OPEN

4:00 PM (END OF DAY)
├─ Generate daily report
├─ Calculate metrics
└─ Send alerts (Slack/Email)
```


***

## 💡 KEY LOGIC POINTS

| Component | Logic |
| :-- | :-- |
| **Symbol Selection** | Score 50+ → Filter → Select 12 best |
| **Options Analysis** | Filter → Score 0-100 → Rank all |
| **Entry Generation** | Apply capital rules → Allocate → Generate signals |
| **Execution** | Submit limit order → Wait for fill → Track |
| **Monitoring** | Every 60 sec: Update Greeks → Check exits |
| **Exit Detection** | Compare profit_pct vs target_pct for week |
| **Capital Redeployment** | Exit → Release capital → Scan for replacement → Execute |
| **Reporting** | Collect metrics → Format → Send alerts |


***

**This is the complete implementable logic. Each section can be coded as a Python class/function following this pseudocode.** 🚀

