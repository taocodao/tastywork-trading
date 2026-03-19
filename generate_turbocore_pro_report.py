import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.turbocore_pro.data_pipeline import TurboCoreDataPipeline
from src.turbocore_pro.base_strategy import BaseStrategy
from src.turbocore_pro.ml.regime_detector import TurboCoreRegimeDetector
from src.turbocore_pro.ml.signal_scorer import TurboCoreSignalScorer
from src.turbocore_pro.allocation_optimizer import AllocationOptimizer

import warnings
warnings.filterwarnings('ignore')

def generate_report():
    print("Generating comprehensive TurboCore Pro $5k Detailed Orders Report...")
    initial_capital = 5000.0
    start_date = "2019-01-01"
    end_date = "2026-03-01"

    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("10y") 
    raw_df = pipeline.prepare_core_features()
    
    df = raw_df[(raw_df.index >= start_date) & (raw_df.index <= end_date)].copy()
    
    strategy = BaseStrategy(df)
    df = strategy.evaluate()
    
    detector = TurboCoreRegimeDetector()
    try:
        detector.fit(raw_df) 
        df = detector.predict_regimes(df)
    except Exception as e:
        print(f"Error regime: {e}")
        df['final_regime'] = 'SIDEWAYS'
        
    scorer = TurboCoreSignalScorer()
    try:
        scorer.fit(raw_df) 
        df = scorer.predict_confidence(df)
    except Exception as e:
        print(f"Error scorer: {e}")
        df['ml_confidence'] = 0.5
        
    # Extract closing prices for simulating quantities
    for ticker in ['QQQ', 'QLD', 'SGOV']:
        col_name = f"{ticker}_close"
        if ticker == 'QQQ':
            df[col_name] = df['qqq_close']
        elif ticker == 'SGOV': 
            if 'SGOV' in pipeline.data:
                df[col_name] = pipeline.data['SGOV']['Close'].reindex(df.index).ffill()
            else:
                df[col_name] = 100.0  # Safe default if SGOV data drops
        elif ticker == 'QLD':
            if 'QLD' in pipeline.data:
                df[col_name] = pipeline.data['QLD']['Close'].reindex(df.index).ffill()
            else:
                df[col_name] = 100.0
                
    # Fill NAs in prices using backfill then forward fill
    for ticker in ['QQQ', 'QLD', 'SGOV']:
        df[f'{ticker}_close'] = df[f'{ticker}_close'].bfill().ffill()

    # Generate mock prices for QQQ_LEAPS
    # First get returns
    df['QQQ_return'] = df['QQQ_close'].pct_change()
    leaps_leverage = 3.75
    df['theta_annual'] = 0.075
    df.loc[df['final_regime'] == 'BULL', 'theta_annual'] = 0.045
    df.loc[df['final_regime'] == 'SIDEWAYS', 'theta_annual'] = 0.065
    df['daily_theta_drag'] = df['theta_annual'] / 252.0
    
    df['QQQ_LEAPS_return'] = (df['QQQ_return'] * leaps_leverage) - df['daily_theta_drag']
    df['QQQ_LEAPS_return'] = df['QQQ_LEAPS_return'].fillna(0)
    
    # Create mock price index for leaps starting at 100
    df['QQQ_LEAPS_close'] = 100.0 * (1 + df['QQQ_LEAPS_return']).cumprod()
    df['QQQ_LEAPS_close'] = df['QQQ_LEAPS_close'].bfill().ffill()

    allocator = AllocationOptimizer()
    
    cash = initial_capital
    positions = {'QQQ': 0.0, 'QLD': 0.0, 'QQQ_LEAPS': 0.0, 'SGOV': 0.0}
    current_alloc = {'QQQ': 0.0, 'QLD': 0.0, 'QQQ_LEAPS': 0.0, 'SGOV': 0.0} 
    
    order_log = []
    yearly_data = {}
    
    portfolio_values = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        date = df.index[i].date()
        year = date.year
        
        # Current closing prices for this session
        prices = {
            'QQQ': row['QQQ_close'],
            'QLD': row['QLD_close'],
            'QQQ_LEAPS': row['QQQ_LEAPS_close'],
            'SGOV': row['SGOV_close']
        }
        
        # Mark to market (Portfolio Value = Cash + Value of current holdings)
        port_val = cash + sum(positions[t] * prices[t] for t in ['QQQ', 'QLD', 'QQQ_LEAPS', 'SGOV'])
        portfolio_values.append(port_val)
        
        if year not in yearly_data:
            yearly_data[year] = {
                'start_capital': port_val,
                'end_capital': port_val,
                'orders_count': 0
            }
        yearly_data[year]['end_capital'] = port_val
        
        # Matrix Signals
        regime = str(row.get('final_regime', 'SIDEWAYS'))
        base_signal = int(row.get('base_signal', 0))
        confidence = float(row.get('ml_confidence', 0.5))
        qqq_drawdown = float(row.get('qqq_drawdown_ath', 0.0))
        
        target_allocation = allocator.get_target_allocation(
            regime=regime,
            signal=base_signal,
            ml_confidence=confidence,
            qqq_drawdown=qqq_drawdown
        )
        # Sift dictionary into clean format
        target_alloc = {t: target_allocation.get(t, 0.0) for t in ['QQQ', 'QLD', 'QQQ_LEAPS', 'SGOV']}
                
        # If target allocation changed, rebalance mathematically 
        if target_alloc != current_alloc:
            target_holdings = {}
            # Evaluate exactly how many fractional shares we SHOULD own
            for t in ['QQQ', 'QLD', 'QQQ_LEAPS', 'SGOV']:
                target_value = port_val * target_alloc[t]
                target_qty = target_value / prices[t] if prices[t] > 0 else 0
                target_holdings[t] = target_qty
                
            # Execute SELL orders first to free up Cash
            for t in ['QQQ', 'QLD', 'QQQ_LEAPS', 'SGOV']:
                diff = target_holdings[t] - positions[t]
                if diff < -0.01: # Sell Condition (with small float buffer)
                    qty_to_sell = abs(diff)
                    val = qty_to_sell * prices[t]
                    
                    if t == 'QQQ_LEAPS':
                        fee = val * 0.001
                    else:
                        fee = val * 0.0002
                    cash += (val - fee)
                    positions[t] = target_holdings[t]
                    order_log.append({
                        'date': date, 'ticker': t, 'action': 'SELL', 
                        'qty': qty_to_sell, 'price': prices[t], 'val': val, 'regime': regime
                    })
                    yearly_data[year]['orders_count'] += 1
            
            # Execute BUY orders next with the freed Cash
            for t in ['QQQ', 'QLD', 'QQQ_LEAPS', 'SGOV']:
                diff = target_holdings[t] - positions[t]
                if diff > 0.01: # Buy Condition
                    qty_to_buy = diff
                    val = qty_to_buy * prices[t]
                    
                    if t == 'QQQ_LEAPS':
                        fee = val * 0.001
                    else:
                        fee = val * 0.0002
                    cash -= (val + fee)
                    positions[t] = target_holdings[t]
                    order_log.append({
                        'date': date, 'ticker': t, 'action': 'BUY', 
                        'qty': qty_to_buy, 'price': prices[t], 'val': val, 'regime': regime
                    })
                    yearly_data[year]['orders_count'] += 1
                    
            current_alloc = target_alloc.copy()

    total_return_pct = (portfolio_values[-1] / initial_capital - 1) * 100
    
    start_yr = df.index[0].year
    end_yr = df.index[-1].year
    
    md = f"""# TURBOCORE PRO ML: $5K COMPOUNDING ACCOUNT
**Testing Period:** {start_yr} to {end_yr} 
**Starting Capital:** ${initial_capital:,.2f}
**Ending Capital:** ${portfolio_values[-1]:,.2f}
**Total Return:** +{total_return_pct:,.1f}%

## 📊 Vital Statistics
- **Total Order Executions:** {len(order_log)} (Fractional Buy/Sell Rotations)
- **Total Net PnL:** ${portfolio_values[-1] - initial_capital:,.2f}

## 📅 Year-by-Year Breakdown
| Year | Start Capital | Orders Executed | Net PnL | End Capital | Return % |
|------|---------------|-----------------|---------|-------------|----------|
"""
    
    for yr, data in yearly_data.items():
        start_cap = data['start_capital']
        end_cap = data['end_capital']
        orders_count = data['orders_count']
        net_pnl = end_cap - start_cap
        ret_pct = (end_cap / start_cap - 1) * 100
        
        md += f"| {yr} | ${start_cap:,.2f} | {orders_count} | ${net_pnl:,.2f} | ${end_cap:,.2f} | {ret_pct:+.1f}% |\n"
        
    md += """
---
## 🔍 Detailed Order Breakdown Log
*Note: This log tracks every atomic buy and sell execution driven by the ML allocation multi-asset matrix shifts.*

| Execution Date | Regime | Action | Security | Quantity (Shares) | Fill Price | Target Allocation Value |
|----------------|--------|--------|----------|-------------------|------------|-------------------------|
"""
    # Write orders descending
    for o in reversed(order_log):
        # Formatting action to stand out visually
        action_str = f"🔴 {o['action']}" if o['action'] == 'SELL' else f"🟢 {o['action']} "
        md += f"| {o['date']} | {o['regime']} | {action_str} | **{o['ticker']}** | {o['qty']:,.4f} | ${o['price']:,.2f} | ${o['val']:,.2f} |\n"

    report_path = r"d:\Projects\tastywork-trading-1\TQQQ-new\detailed_turbocore_orders_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
        
    print(f"Detailed Orders Report successfully saved to {report_path}")

if __name__ == "__main__":
    generate_report()
