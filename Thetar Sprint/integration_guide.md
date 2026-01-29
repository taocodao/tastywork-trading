# System Integration Guide
## How Symbol Selection & Options Analysis Integrate with Main System

---

## EXECUTIVE SUMMARY

This guide shows how the **symbol selection system** integrates with the **core trading system** to create a fully automated workflow.

**Complete Morning Flow:**
```
9:30 AM   → Market opens
9:45 AM   → Run morning analysis (5 min)
          → Select best 12 symbols
          → Analyze options chains
          → Rank 100+ puts by confidence
          → Identify best 6-8 trades
10:00 AM  → Execute first signals (auto if enabled)
10:05 AM  → Start continuous monitoring
          → Check exit signals every minute
          → Auto-redeploy capital when exits triggered
4:00 PM   → End of day reporting
```

---

## PART 1: DATA FLOW ARCHITECTURE

### 1.1 Complete System Flow

```
┌─────────────────────────────────────────────────────────────┐
│ MARKET DATA (Real-time from IB API)                         │
│ - Option chains (all symbols, all expirations)              │
│ - Greeks (Delta, Theta, Vega, Gamma)                        │
│ - Underlying prices (updating every second)                 │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ SYMBOL SELECTOR (9:45 AM)                                   │
│ Input: 50+ candidates, market data                          │
│ Process:                                                    │
│ - Score each symbol (5 factors)                             │
│ - Apply filters (earnings, div, liquidity)                  │
│ - Maintain sector balance                                   │
│ Output: Best 12 symbols TODAY                               │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ OPTIONS ANALYZER (9:45 AM)                                  │
│ Input: 12 symbols, full options chains                      │
│ Process:                                                    │
│ - Filter to 30-delta puts                                   │
│ - Score each put (100-point scale)                          │
│ - Rank by confidence                                        │
│ Output: 100+ qualified puts, ranked                         │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ ENTRY SIGNAL GENERATOR (9:45 AM)                            │
│ Input: Ranked puts, portfolio state                         │
│ Process:                                                    │
│ - Apply capital allocation rules                            │
│ - Respect max positions                                     │
│ - Identify executable trades                                │
│ Output: 6-8 entry signals ready to execute                  │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ ORDER EXECUTOR (10:00 AM or auto)                           │
│ Input: Ranked entry signals                                 │
│ Process:                                                    │
│ - Submit SELL_TO_OPEN orders (limit orders)                 │
│ - Track order status                                        │
│ - Confirm fills                                             │
│ Output: Positions in portfolio                              │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ CONTINUOUS MONITORING (Every minute during market hours)    │
│ Input: Open positions                                       │
│ Process:                                                    │
│ - Update Greeks in real-time                                │
│ - Check exit conditions                                     │
│ - Monitor for profit targets                                │
│ Output: Exit signals when conditions met                    │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ EXIT EXECUTOR (Continuous)                                  │
│ Input: Exit signals                                         │
│ Process:                                                    │
│ - Submit BUY_TO_CLOSE orders                                │
│ - Release capital                                           │
│ - Log trades                                                │
│ Output: Profit booked, capital freed                        │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ CAPITAL REDEPLOYMENT (After each exit)                      │
│ Input: Freed capital, current market conditions             │
│ Process:                                                    │
│ - Scan for replacement opportunities                        │
│ - Instantly execute if available                            │
│ - Maximize capital turns                                    │
│ Output: New positions opened                                │
└─────────────────────────────────────────────────────────────┘
```

---

## PART 2: CONFIGURATION INTEGRATION

### 2.1 Unified Config File

```python
# config.py - Master configuration for entire system

CONFIG = {
    # ============ SYMBOL SELECTION ============
    'symbol_selection': {
        'use_dynamic_watchlist': True,
        'refresh_schedule': '09:30',      # Daily at market open
        'select_top_n': 12,                # Best 12 from 50+ candidates
        'min_candidates': 50,
    },
    
    'symbol_scores': {
        'iv_weight': 30,                   # IV Percentile importance
        'liquidity_weight': 25,
        'premium_weight': 20,
        'trend_weight': 15,
        'sector_weight': 10,
    },
    
    'symbol_filters': {
        'exclude_pre_earnings_days': 21,   # Exclude 21 days before/after
        'min_volume': 100_000,             # Daily volume
        'min_iv_percentile': 20,           # Don't trade low IV
        'max_bid_ask_spread': 0.10,        # Max 10% spread
    },
    
    'sectors': {
        'max_exposure_pct': 25,            # Max 25% per sector
        'target_diversification': 'HIGH',
    },
    
    # ============ OPTIONS ANALYSIS ============
    'options_selection': {
        'target_delta': 0.30,              # Sweet spot
        'delta_range': (0.25, 0.35),       # Acceptable range
        'days_to_exp': (28, 35),           # Expiration window
        'expiration_day': 'THIRD_FRIDAY',  # Always 3rd Friday
        'min_volume': 50,                  # Options volume
        'min_open_interest': 500,
    },
    
    'put_scoring': {
        'delta_weight': 30,                # Precision to 0.30
        'premium_weight': 25,              # Quality of premium
        'theta_weight': 20,                # Time decay benefit
        'liquidity_weight': 15,            # Bid-ask spread
        'vega_weight': 10,                 # IV sensitivity
    },
    
    # ============ ENTRY SIGNALS ============
    'entry_signals': {
        'min_confidence': 60,              # Only trade 60+ scores
        'max_daily_entries': 8,            # Max 8 new trades per day
        'execution_delay': 30,             # Minutes after signal to execute
    },
    
    # ============ EXIT SIGNALS (Time-Based!) ============
    'exit_targets': {
        'week_1_days': (1, 7),
        'week_1_profit_pct': 50,
        'week_2_days': (8, 14),
        'week_2_profit_pct': 60,
        'week_3_days': (15, 21),
        'week_3_profit_pct': 75,
        'week_4_days': (22, 28),
        'week_4_profit_pct': 90,
    },
    
    # ============ EXECUTION ============
    'execution': {
        'auto_trade': False,               # Manual review first
        'order_type': 'LIMIT',
        'entry_limit_buffer': -0.02,       # 2% below bid when selling
        'exit_limit_buffer': 0.02,         # 2% above ask when buying
        'time_in_force': 'DAY',
    },
    
    # ============ RISK MANAGEMENT ============
    'risk': {
        'contracts_per_trade': 10,         # Can adjust per capital
        'max_positions': 6,                # Max 6 simultaneous positions
        'max_portfolio_heat': 50_000,      # Max capital at risk
        'max_position_size': 10_000,       # Max per trade
        'stop_loss_pct': -5,               # Hard stop at -5%
    },
    
    # ============ ALERTS ============
    'alerts': {
        'slack_enabled': True,
        'slack_channel': '#trading',
        'email_enabled': True,
        'email_address': 'trader@example.com',
    },
    
    # ============ DATA & MONITORING ============
    'data': {
        'primary_api': 'INTERACTIVE_BROKERS',
        'backup_api': 'TRADIER',
        'data_refresh': 60,                # Seconds
        'cache_timeout': 300,              # Seconds
    },
}
```

---

## PART 3: DAILY EXECUTION FLOW

### 3.1 Morning Workflow (9:45 AM)

```python
class MorningWorkflow:
    """
    Automated morning analysis and execution
    Triggered every trading day at 9:45 AM
    """
    
    def run(self):
        """Execute complete morning analysis"""
        
        start_time = datetime.now()
        print(f"\n{'='*80}")
        print(f"MORNING ANALYSIS - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
        
        try:
            # STEP 1: Get current portfolio state (2 sec)
            portfolio = self.portfolio_manager.get_current_state()
            print(f"✓ Portfolio loaded")
            print(f"  Cash available: ${portfolio.cash_available:,.0f}")
            print(f"  Positions: {len(portfolio.positions)}")
            print(f"  Unrealized P&L: ${portfolio.get_unrealized_pnl():,.0f}\n")
            
            # STEP 2: Select daily watchlist (10 sec)
            watchlist = self.symbol_selector.select_daily_watchlist()
            print(f"✓ Selected {len(watchlist)} symbols from 50+ candidates")
            print(f"  Symbols: {', '.join(watchlist)}\n")
            
            # STEP 3: Get market data for all symbols (15 sec)
            market_data = self.data_provider.get_market_data(watchlist)
            print(f"✓ Retrieved market data (IV, Greeks, prices)\n")
            
            # STEP 4: Analyze options for each symbol (20 sec)
            all_qualified_puts = []
            for symbol in watchlist:
                symbol_puts = self.options_analyzer.analyze_symbol(
                    symbol=symbol,
                    market_data=market_data[symbol],
                    portfolio=portfolio
                )
                all_qualified_puts.extend(symbol_puts)
            
            print(f"✓ Analyzed options chains")
            print(f"  Total qualified puts: {len(all_qualified_puts)}\n")
            
            # STEP 5: Rank all puts by confidence (5 sec)
            ranked_puts = sorted(
                all_qualified_puts,
                key=lambda x: x['confidence'],
                reverse=True
            )
            
            print(f"✓ Ranked {len(ranked_puts)} puts by confidence\n")
            
            # STEP 6: Apply capital allocation rules (5 sec)
            executable_signals = self.capital_allocator.allocate_capital(
                ranked_puts=ranked_puts,
                portfolio=portfolio,
                config=CONFIG
            )
            
            print(f"✓ Identified {len(executable_signals)} executable trades")
            print(f"  Capital required: ${self.calc_capital(executable_signals):,.0f}\n")
            
            # STEP 7: Display execution plan
            self.display_execution_plan(executable_signals)
            
            # STEP 8: Execute if auto_trade enabled
            if CONFIG['execution']['auto_trade']:
                print(f"\n🤖 AUTO-TRADING ENABLED\n")
                for rank, signal in enumerate(executable_signals, 1):
                    status = self.order_executor.execute_entry_signal(signal)
                    print(f"{rank}. {signal['symbol']} {signal['strike']} - {status}")
            else:
                print(f"\n⏸️  MANUAL REVIEW MODE\n")
                print(f"Review above signals and execute manually if satisfied.\n")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"\n✓ Analysis complete in {elapsed:.1f} seconds")
            print(f"{'='*80}\n")
            
            return executable_signals
            
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            self.alert_system.send_error_alert(e)
            raise
    
    def display_execution_plan(self, signals):
        """Display ranked execution plan"""
        print(f"{'EXECUTION PLAN':^80}")
        print(f"{'-'*80}")
        print(f"{'#':<3} {'Symbol':<8} {'Strike':<8} {'Bid':<8} {'Delta':<8} "
              f"{'Conf':<6} {'Capital':<12}")
        print(f"{'-'*80}")
        
        for rank, signal in enumerate(signals, 1):
            capital = signal['strike'] * 100 * CONFIG['risk']['contracts_per_trade']
            print(f"{rank:<3} {signal['symbol']:<8} ${signal['strike']:<7.2f} "
                  f"${signal['bid']:<7.2f} {signal['delta']:<7.2f} "
                  f"{signal['confidence']:<6.0f} ${capital:<11,.0f}")
        
        print(f"{'-'*80}\n")
```

### 3.2 Continuous Monitoring (Every Minute)

```python
class ContinuousMonitoring:
    """
    Real-time monitoring during market hours
    Runs every 60 seconds from 9:30 AM - 4:00 PM
    """
    
    def run_continuous_loop(self):
        """Main monitoring loop"""
        
        while self.is_market_open():
            try:
                # STEP 1: Update portfolio (2 sec)
                portfolio = self.portfolio_manager.get_current_state()
                
                if len(portfolio.positions) == 0:
                    time.sleep(60)
                    continue
                
                # STEP 2: Refresh Greeks for all open positions (5 sec)
                for position in portfolio.positions.values():
                    self.update_position_greeks(position)
                
                # STEP 3: Check for exit signals (3 sec)
                exit_signals = self.exit_signal_generator.generate_exit_signals(
                    portfolio.positions.values()
                )
                
                if exit_signals:
                    print(f"\n🚨 EXIT SIGNALS DETECTED: {len(exit_signals)}")
                    
                    # STEP 4: Execute exits
                    for signal in exit_signals:
                        exit_result = self.order_executor.execute_exit_signal(signal)
                        
                        if exit_result['success']:
                            print(f"✓ Exited {signal['symbol']} {signal['strike']} "
                                  f"- Profit ${signal['profit_dollars']:,.0f}")
                            
                            # STEP 5: Immediately scan for replacement
                            if portfolio.cash_available > 0:
                                replacement_signal = self.find_replacement_trade()
                                if replacement_signal:
                                    self.order_executor.execute_entry_signal(replacement_signal)
                                    print(f"✓ Deployed freed capital to {replacement_signal['symbol']}")
                
                # STEP 6: Log current state (1 sec)
                self.log_current_state(portfolio)
                
                # Wait for next check
                time.sleep(60)
                
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                self.alert_system.send_error_alert(e)
                time.sleep(60)
    
    def update_position_greeks(self, position):
        """Update Greeks for open position"""
        option_data = self.get_option_data(
            symbol=position['symbol'],
            strike=position['strike'],
            expiration=position['expiration']
        )
        
        position['current_option_price'] = option_data['mid_price']
        position['current_delta'] = option_data['delta']
        position['current_theta'] = option_data['theta']
        position['current_underlying'] = option_data['underlying_price']
        
        # Recalculate unrealized P&L
        entry = position['entry_price']
        current = option_data['mid_price']
        profit = (entry - current) * 100 * position['contracts']
        position['unrealized_pnl'] = profit
        position['unrealized_pnl_pct'] = (profit / (entry * 100 * position['contracts'])) * 100
```

### 3.3 End of Day Report (4:00 PM)

```python
class EndOfDayReport:
    """Generate daily summary"""
    
    def generate_report(self):
        """Create end-of-day report"""
        
        portfolio = self.portfolio_manager.get_current_state()
        
        report = f"""
{'='*80}
DAILY REPORT - {datetime.now().strftime('%Y-%m-%d')}
{'='*80}

PORTFOLIO SUMMARY
{'-'*80}
Open Positions:      {len(portfolio.positions)}
Cash Available:      ${portfolio.cash_available:,.0f}
Total Equity:        ${portfolio.total_equity:,.0f}
Utilization:         {(portfolio.cash_reserved / portfolio.total_equity * 100):.1f}%

PROFIT & LOSS
{'-'*80}
Realized Today:      ${portfolio.daily_realized_pnl:,.0f}
Unrealized:          ${portfolio.get_unrealized_pnl():,.0f}
Total Today:         ${portfolio.daily_realized_pnl + portfolio.get_unrealized_pnl():,.0f}
Return %:            {((portfolio.daily_realized_pnl + portfolio.get_unrealized_pnl()) / portfolio.total_equity * 100):.2f}%

TRADES TODAY
{'-'*80}
Entries:             {len([t for t in portfolio.trade_history if t['type'] == 'ENTRY'])}
Exits:               {len([t for t in portfolio.trade_history if t['type'] == 'EXIT'])}
Win Rate:            {self.calculate_win_rate(portfolio):.1f}%
Avg Hold Time:       {self.calculate_avg_hold_time(portfolio):.1f} hours

OPEN POSITIONS
{'-'*80}
"""
        
        for pos in portfolio.positions.values():
            report += f"""
{pos['symbol']} {pos['strike']} (Exp: {pos['expiration']})
  Entered:      {pos['entry_datetime'].strftime('%H:%M')}
  Entry Price:  ${pos['entry_price']:.2f}
  Current:      ${pos['current_option_price']:.2f}
  P&L:          ${pos['unrealized_pnl']:,.0f} ({pos['unrealized_pnl_pct']:.1f}%)
  Days Held:    {pos['days_in_trade']}
  Exit Target:  {self.get_exit_target(pos['days_in_trade'])}%
"""
        
        report += f"\n{'='*80}\n"
        
        # Send report
        self.alert_system.send_end_of_day_report(report)
        
        return report
```

---

## PART 4: DATA FLOW BETWEEN MODULES

### 4.1 Symbol Selector Output → Options Analyzer Input

```python
# SYMBOL SELECTOR OUTPUT
watchlist_selection = {
    'symbols': ['QQQ', 'SPY', 'IWM', 'TLT', 'USO', 'XLV', ...],
    'scores': {
        'QQQ': 87,
        'SPY': 85,
        'IWM': 82,
        ...
    },
    'timestamp': datetime.now(),
}

# USED BY OPTIONS ANALYZER
for symbol in watchlist_selection['symbols']:
    symbol_score = watchlist_selection['scores'][symbol]
    options = get_options_chain(symbol)
    ranked_puts = analyze_options(options, symbol_score)
```

### 4.2 Options Analyzer Output → Entry Signal Generator Input

```python
# OPTIONS ANALYZER OUTPUT
qualified_puts = [
    {
        'symbol': 'QQQ',
        'strike': 380,
        'bid': 1.15,
        'ask': 1.25,
        'mid': 1.20,
        'delta': -0.30,
        'theta': 0.022,
        'confidence': 87,
    },
    {
        'symbol': 'SPY',
        'strike': 590,
        'bid': 0.95,
        'ask': 1.05,
        'mid': 1.00,
        'delta': -0.29,
        'theta': 0.018,
        'confidence': 84,
    },
    ...
]

# USED BY ENTRY SIGNAL GENERATOR
entry_signals = []
for put in qualified_puts:
    signal = {
        'action': 'SELL_PUT',
        'symbol': put['symbol'],
        'strike': put['strike'],
        'entry_price': put['bid'],
        'contracts': CONFIG['risk']['contracts_per_trade'],
        'confidence': put['confidence'],
        'capital_required': put['strike'] * 100 * contracts,
    }
    entry_signals.append(signal)
```

### 4.3 Entry Executor Output → Portfolio Manager Input

```python
# ORDER EXECUTOR OUTPUT (after fill)
fill_notification = {
    'order_type': 'SELL_TO_OPEN',
    'symbol': 'QQQ',
    'strike': 380,
    'contracts': 10,
    'fill_price': 1.12,
    'fill_time': datetime.now(),
    'status': 'FILLED',
}

# USED BY PORTFOLIO MANAGER
position = {
    'position_id': 'POS_001',
    'symbol': 'QQQ',
    'strike': 380,
    'entry_price': 1.12,
    'entry_time': fill_notification['fill_time'],
    'contracts': 10,
    'capital_reserved': 380 * 100 * 10,
    'status': 'OPEN',
}
portfolio.add_position(position)
```

---

## PART 5: ERROR HANDLING & SAFEGUARDS

### 5.1 Execution Safeguards

```python
class ExecutionSafeguards:
    """Prevent common trading errors"""
    
    def validate_signal(self, signal):
        """Pre-execution validation"""
        
        # Check 1: Is symbol on today's watchlist?
        if signal['symbol'] not in self.todays_watchlist:
            raise ValueError(f"{signal['symbol']} not on today's watchlist!")
        
        # Check 2: Is capital available?
        if self.portfolio.cash_available < signal['capital_required']:
            raise ValueError("Insufficient capital!")
        
        # Check 3: Would exceed max positions?
        if len(self.portfolio.positions) >= CONFIG['risk']['max_positions']:
            raise ValueError("Max positions reached!")
        
        # Check 4: Is strike within reasonable range?
        current_price = self.get_current_price(signal['symbol'])
        if abs(signal['strike'] - current_price) > current_price * 0.10:
            raise ValueError("Strike >10% away from current price!")
        
        # Check 5: Is confidence sufficient?
        if signal['confidence'] < CONFIG['entry_signals']['min_confidence']:
            raise ValueError(f"Confidence too low ({signal['confidence']}%)")
        
        return True
    
    def validate_exit(self, exit_signal):
        """Pre-exit validation"""
        
        # Check 1: Position exists?
        if exit_signal['position_id'] not in self.portfolio.positions:
            raise ValueError("Position not found!")
        
        # Check 2: Is exit reason valid?
        valid_reasons = ['PROFIT_TARGET', 'EXPIRATION_IMMINENT', 'DEFENSIVE_CLOSE']
        if exit_signal['reason'] not in valid_reasons:
            raise ValueError(f"Invalid exit reason: {exit_signal['reason']}")
        
        return True
```

---

## PART 6: MONITORING DASHBOARD

### 6.1 Real-Time Dashboard Display

```python
class RealtimeDashboard:
    """Display current state"""
    
    def display_dashboard(self):
        """Live updating dashboard (refreshes every 60 sec)"""
        
        portfolio = self.portfolio_manager.get_current_state()
        
        display = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ TRADING DASHBOARD - {datetime.now().strftime('%H:%M:%S')}                                        │
╠══════════════════════════════════════════════════════════════════════════════╣
║ PORTFOLIO                                                                    │
║ {'-'*78}│
║ Open Positions:    {len(portfolio.positions):<2}    Cash Available:  ${portfolio.cash_available:>12,.0f}    │
║ Total Equity:      ${portfolio.total_equity:>12,.0f}     Utilization:    {(portfolio.cash_reserved / portfolio.total_equity * 100):>6.1f}%   │
║ Unrealized P&L:    ${portfolio.get_unrealized_pnl():>12,.0f}     Daily Realized:  ${portfolio.daily_realized_pnl:>12,.0f}   │
║                                                                              │
║ OPEN POSITIONS                                                               │
║ {'-'*78}│
"""
        
        for pos in portfolio.positions.values():
            exit_target = self.get_exit_target(pos['days_in_trade'])
            ready = "✓" if pos['unrealized_pnl_pct'] >= exit_target else " "
            
            display += f"""║ {ready} {pos['symbol']:6} {pos['strike']:7.2f}   │ ${pos['current_option_price']:6.2f}  │  {pos['unrealized_pnl_pct']:>6.1f}%  │  {pos['days_in_trade']:>2}d   │ Tgt: {exit_target:>2}%  │
"""
        
        display += f"""╠══════════════════════════════════════════════════════════════════════════════╣
║ TODAY'S ACTIVITY                                                             │
║ Entries: {len([t for t in portfolio.trade_history if t['type'] == 'ENTRY']):<2}  Exits: {len([t for t in portfolio.trade_history if t['type'] == 'EXIT']):<2}  Win Rate: {self.calculate_win_rate(portfolio):>5.1f}%                          │
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        
        print(display)
        return display
```

---

## QUICK REFERENCE: WHEN THINGS HAPPEN

```
9:30 AM    Market opens
           → Data feeds start
           → Initial data pull

9:45 AM    Morning analysis
           → Symbol selector runs (50 → 12)
           → Options analyzer runs
           → Entry signals generated
           → Execution plan displayed

10:00 AM   Execution window opens
           → First signals executed
           → Positions added to portfolio

10:05 AM - 3:55 PM   Continuous monitoring
           → Every minute: update positions, check exits
           → When exit signal triggered:
             - Execute exit
             - Book profit
             - Scan for replacement
             - Execute replacement (auto-redeploy)

4:00 PM    Market close
           → End of day report
           → Daily summary sent

After 4:00 PM  Post-market
           → Monitor any remaining positions
           → Prepare for next day

Next 9:30 AM   New day cycle begins
```

---

**Document Version:** 1.0  
**Date:** January 26, 2026  
**Status:** ✅ Ready for Deployment
