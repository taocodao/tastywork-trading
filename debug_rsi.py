import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import sys

# Ensure src is in path to test actual classes if needed
sys.path.append(os.getcwd())

def debug_ticker(symbol):
    print(f"\n===== Debugging {symbol} =====")
    try:
        df = yf.download(symbol, period="200d", auto_adjust=True, progress=False)
        if df.empty:
            print(f"Error: {symbol} returned empty DataFrame")
            return
            
        print(f"Data shape: {df.shape}")
        last_rows = df.tail(5)
        print("Last 5 rows of Close prices:")
        print(last_rows['Close'])
        
        # Intermediate RSI-2 steps
        close = df['Close']
        delta = close.diff()
        gain_raw = delta.where(delta > 0, 0)
        loss_raw = -delta.where(delta < 0, 0)
        
        gain = gain_raw.rolling(window=2).mean()
        loss = loss_raw.rolling(window=2).mean()
        
        rs = gain / loss
        rsi_2 = 100 - (100 / (1 + rs))
        
        print("\nLast 3 RSI Calculation steps:")
        debug_df = pd.DataFrame({
            'Close': close,
            'Delta': delta,
            'GainAvg': gain,
            'LossAvg': loss,
            'RS': rs,
            'RSI-2': rsi_2
        }).tail(3)
        print(debug_df)
        
    except Exception as e:
        print(f"Error debugging {symbol}: {e}")

if __name__ == "__main__":
    symbols = ["AAPL", "MSFT", "SOXL"]
    print(f"Run time (UTC): {datetime.utcnow()}")
    for s in symbols:
        debug_ticker(s)
