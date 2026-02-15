"""
ZEBRA Strategy Backtest Simulation
==================================
Simulates ZEBRA strategy performance using historical stock data (yfinance).

Since historical options chain data is expensive/sparse, this simulation uses 
mathematical proxies for ZEBRA behavior:
1. Entry Cost ≈ 50% of Stock Price (Capital Efficiency)
2. Net Delta ≈ 90 (0.90 per share)
3. Theta Decay ≈ 0 (Zero Extrinsic assumption)
4. Leverage ≈ 2:1

This validates the *Risk Profile* and *Management Rules* (Stops/Targets), 
not the exact option pricing (which varies by IV).
"""

import yfinance as yf
import pandas as pd
import numpy as np
import logging
import warnings
from datetime import datetime, timedelta
from typing import List, Dict

# Suppress FutureWarnings from yfinance/pandas
warnings.simplefilter(action='ignore', category=FutureWarning)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("ZebraBacktest")

class ZebraBacktester:
    def __init__(self, initial_capital=100000):
        self.capital = initial_capital
        self.history = []
        self.positions = []
        
        # Strategy Parameters (Mirrors config.py)
        self.PROFIT_TARGET_PCT = 0.50  # 50% return on debit
        self.STOP_LOSS_PCT = -0.40     # -40% loss on debit
        self.TIME_EXIT_DAYS = 30       # Exit after 30 days if flat
        self.LEVERAGE_DELTA = 0.90     # Net delta
        self.ENTRY_COST_RATIO = 0.50   # Debit is ~50% of share price

    def run(self, symbols: List[str], start_date="2024-01-01", end_date=None):
        """Run backtest on list of symbols."""
        print(f"\n--- Starting ZEBRA Backtest (Start: {start_date}) ---")
        print(f"Strategy: Target={self.PROFIT_TARGET_PCT:.0%}, Stop={self.STOP_LOSS_PCT:.0%}, TimeExit={self.TIME_EXIT_DAYS}d")
        
        total_pnl = 0
        trades_count = 0
        wins = 0
        
        for symbol in symbols:
            try:
                # 1. Fetch Data
                print(f"\nScanning {symbol} for opportunities...")
                df = yf.download(symbol, start=start_date, end=end_date, progress=False)
                if df.empty:
                    print(f"  No data found for {symbol}")
                    continue
                
                # 2. Add Indicators (Simple Trend Filter)
                # Proxy for "Perplexity Selection" -> We use Price > SMA50 as "Bullish"
                df['SMA50'] = df['Close'].rolling(window=50).mean()
                df['RSI'] = self.calculate_rsi(df['Close'])
                
                in_position = False
                entry_date = None
                entry_price = 0.0
                entry_debit = 0.0
                symbol_trades = 0
                
                # Loop through days
                for date, row in df.iterrows():
                    price = float(row['Close'])
                    sma = float(row['SMA50'])
                    rsi = float(row['RSI'])
                    
                    if np.isnan(sma) or np.isnan(rsi): continue
                    
                    # --- EXIT LOGIC ---
                    if in_position:
                        days_held = (date - entry_date).days
                        
                        # Theoretical ZEBRA P&L
                        # Change in Stock * Delta * 100 shares
                        stock_move = price - entry_price
                        trade_pnl_dollar = stock_move * self.LEVERAGE_DELTA * 100
                        
                        trade_return_pct = trade_pnl_dollar / (entry_debit * 100)
                        
                        exit_reason = None
                        
                        # 1. Profit Target
                        if trade_return_pct >= self.PROFIT_TARGET_PCT:
                            exit_reason = "TAKE_PROFIT"
                            
                        # 2. Stop Loss
                        elif trade_return_pct <= self.STOP_LOSS_PCT:
                            exit_reason = "STOP_LOSS"
                            
                        # 3. Time Exit
                        elif days_held >= self.TIME_EXIT_DAYS:
                            exit_reason = "TIME_EXIT"
                            
                        if exit_reason:
                            total_pnl += trade_pnl_dollar
                            trades_count += 1
                            symbol_trades += 1
                            if trade_pnl_dollar > 0: wins += 1
                            
                            print(f"  {date.date()} [SELL] {exit_reason:<12} | Days: {days_held:<2} | P&L: ${trade_pnl_dollar:>7.2f} ({trade_return_pct:>5.1%})")
                            in_position = False
                            continue

                    # --- ENTRY LOGIC ---
                    # Logic: Uptrend (Price > SMA) + Pullback (RSI < 55)
                    if not in_position:
                         if price > sma and rsi < 55 and rsi > 40:
                            # ENTER LONG ZEBRA
                            entry_price = price
                            entry_date = date
                            entry_debit = price * self.ENTRY_COST_RATIO # Approx cost
                            
                            print(f"  {date.date()} [BUY ] ZEBRA Long  | Stock: ${price:.2f} | Est. Debit: ${entry_debit:.2f}")
                            in_position = True
            except Exception as e:
                print(f"Error testing {symbol}: {e}")
                
        # Summary
        print("\n=== ZEBRA BACKTEST SUMMARY ===")
        print(f"Period:       {start_date} to Present")
        print(f"Total Trades: {trades_count}")
        if trades_count > 0:
            win_rate = (wins/trades_count) * 100
            avg_pnl = total_pnl / trades_count
            print(f"Win Rate:     {win_rate:.1f}%")
            print(f"Total P&L:    ${total_pnl:.2f}")
            print(f"Avg P&L:      ${avg_pnl:.2f}")
        else:
            print("No trades executed.")

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

if __name__ == "__main__":
    try:
        import yfinance
    except ImportError:
        print("Error: yfinance is not installed. Please run: pip install yfinance")
        exit(1)
        
    # Test on a mix of Volatility and Blue Chips
    tester = ZebraBacktester()
    tester.run(["SPY", "NVDA", "IWM", "TSLA", "AMD"], start_date="2024-01-01")
