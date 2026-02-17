
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import norm
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("DVO_Sim")

def black_scholes_put(S, K, T, r, sigma):
    """Calculate Put Price using Black-Scholes."""
    if T <= 0:
        return max(K - S, 0)
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return put_price

def calculate_delta(S, K, T, r, sigma, option_type='put'):
    if T <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if option_type == 'call':
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1

class DVOSimulator:
    def __init__(self, tickers, start_date='2022-01-01', risk_profile="MEDIUM"):
        self.tickers = tickers
        self.start_date = start_date
        self.risk_profile = risk_profile
        self.results = {}
        
        # Risk Settings (Simplified)
        self.min_mos = 0.20
        self.target_profit = 0.50
        self.max_allocation_per_symbol = 10000.0
        
    def run(self):
        total_pnl = 0
        total_trades = 0
        
        print(f"--- Starting DVO Simulation from {self.start_date} ---")
        
        for ticker in self.tickers:
            print(f"\nAnalyzing {ticker}...")
            try:
                # 1. Fetch Data
                data = yf.download(ticker, start=self.start_date, progress=False)
                if len(data) < 200:
                    print(f"Insufficient data for {ticker}")
                    continue
                    
                # 2. Calculate Indicators
                # Proxy Fair Value: 120-Day SMA (Lagging indicator of 'true value')
                # Real Fair Value is fundamental, but for backtest without that data, SMA is a proxy for "Trend/Value anchoring"
                # Actually, DVO buys when Price < Value. 
                # If we use 100 or 200 SMA as 'Value', buying below it is 'Deep Value' logic (Mean Reversion).
                data['SMA_200'] = data['Close'].rolling(window=200).mean()
                
                # Volatility (Annualized)
                data['Log_Ret'] = np.log(data['Close'] / data['Close'].shift(1))
                data['HV_30'] = data['Log_Ret'].rolling(window=30).std() * np.sqrt(252)
                
                # 3. Simulate Loop
                position = None # {'entry_date': ..., 'strike': ..., 'premium': ..., 'contracts': ...}
                symbol_pnl = 0
                trades = []
                
                # Start after SMA valid
                valid_idx = 200
                
                for i in range(valid_idx, len(data)):
                    current_date = data.index[i]
                    price = float(data['Close'].iloc[i])
                    sma = float(data['SMA_200'].iloc[i])
                    sigma = float(data['HV_30'].iloc[i]) if not np.isnan(data['HV_30'].iloc[i]) else 0.4
                    r = 0.04 # 4% risk free
                    
                    # Margin of Safety
                    if sma <= 0: continue
                    mos = (sma - price) / sma
                    
                    # Manage Existing Position
                    if position:
                        # Check Exit
                        dte = (position['expiry'] - current_date).days / 365.0
                        if dte <= 0: dte = 0.001
                        
                        # Mark to Market
                        current_put_price = black_scholes_put(price, position['strike'], dte, r, sigma)
                        pnl_unrealized = (position['premium'] - current_put_price) * 100 * position['contracts']
                        roi = pnl_unrealized / (position['premium'] * 100 * position['contracts'])
                        
                        exit_reason = None
                        
                        # 1. 50% Profit Target
                        if roi >= self.target_profit:
                            exit_reason = "50% Profit"
                            
                        # 2. Thesis Reversion (Price > FV)
                        elif price > sma:
                             exit_reason = "Thesis Reversion"
                             
                        # 3. Expiry
                        elif dte * 365 < 5:
                             exit_reason = "Expiry"
                             
                        if exit_reason:
                            # Close Trade
                            pnl = (position['premium'] - current_put_price) * 100 * position['contracts']
                            symbol_pnl += pnl
                            trades.append({
                                'Entry': position['entry_date'].date(),
                                'Exit': current_date.date(),
                                'Reason': exit_reason,
                                'PnL': round(pnl, 2),
                                'ROI': round(roi * 100, 1)
                            })
                            position = None # Clear
                            
                    # Look for Entry (if no position)
                    elif mos > self.min_mos:
                        # Deep Value Detected!
                        # Sell 1yr Put
                        expiry = current_date + timedelta(days=365)
                        T = 1.0
                        
                        # Strike Selection: 0.20 Delta or 10% OTM, capped at Fair Value logic
                        # Simplified: Strike = Price * 0.90 (10% OTM from already low price)
                        strike = price * 0.90
                        
                        # Pricing
                        premium = black_scholes_put(price, strike, T, r, sigma)
                        
                        if premium > 0.50: # Minimum premium
                            # Size: Max Alloc / (Strike * 100 * 0.20 margin assumption) ? 
                            # Or cash secured: Max Alloc / (Strike * 100)
                            contracts = max(1, int(self.max_allocation_per_symbol / (strike * 100)))
                            
                            position = {
                                'entry_date': current_date,
                                'expiry': expiry,
                                'strike': strike,
                                'premium': premium,
                                'contracts': contracts
                            }
                            # print(f"  Entry {current_date.date()}: Sold {strike:.2f}P @ {premium:.2f} (MoS {mos:.2%})")
                            
                self.results[ticker] = {
                    'PnL': symbol_pnl,
                    'Trades': len(trades),
                    'Trade_List': trades
                }
                total_pnl += symbol_pnl
                total_trades += len(trades)
                
                print(f"  Result: ${symbol_pnl:,.2f} over {len(trades)} trades")
                if len(trades) > 0:
                     win_rate = len([t for t in trades if t['PnL'] > 0]) / len(trades)
                     print(f"  Win Rate: {win_rate:.1%}")
                     
            except Exception as e:
                logger.error(f"Error simulating {ticker}: {e}")
                
        print("\n--- Simulation Summary ---")
        print(f"Total P&L: ${total_pnl:,.2f}")
        print(f"Total Trades: {total_trades}")

if __name__ == "__main__":
    # Test on some diverse tickers
    tickers = ["PYPL", "GOOGL", "AMZN", "TSLA", "NVDA", "INTC", "SQ"]
    sim = DVOSimulator(tickers)
    sim.run()
