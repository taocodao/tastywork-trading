"""
TurboBounce V3 Enhanced Backcast Runner
=======================================
This script runs the multi-year backtest utilizing the proven multi-ticker 
architecture from src/turbobounce but incorporating the V3 diagonal rules 
(Three Laws, Roll Qualifier, etc).
"""

import sys
import os

from src.turbobounce.run_multiyear import run_multiyear

def main():
    start_year = 2025
    end_year = 2026
    initial_capital = 15000

    print(f"Starting V3 Enhanced Single-Year Backtest ({start_year}-{end_year}) on user watchlist")
    
    # Run the backtest using accumulate=False to see non-compound short term rebounce
    report = run_multiyear(start_year, end_year, initial_capital, accumulate=False)
    
if __name__ == "__main__":
    main()
