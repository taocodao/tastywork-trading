import sys
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import date, timedelta

from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.backtest_engine import SNDKBacktestEngine
from src.otm_naked.sndk.feature_engineering import build_sndk_features

logging.basicConfig(level=logging.INFO)

def calculate_cagr(start_capital, end_capital, years):
    if years <= 0: return 0
    return (end_capital / start_capital) ** (1 / years) - 1

def main():
    ticker = "SNDK"
    
    # 1. Fetch full SNDK history from inception + VIX/SPY for macro context
    # SNDK began trading 2025-02-13; no warmup period needed beyond that
    start_str_full = "2025-01-01"  # Will yield data from first SNDK trading day
    end_str = "2026-06-30"
    
    raw = yf.download([ticker, "^VIX", "SPY"], start=start_str_full, end=end_str, auto_adjust=True, progress=False)
    
    close_price = raw["Close"][ticker].dropna()
    open_price = raw["Open"][ticker].dropna()
    high_price = raw["High"][ticker].dropna()
    low_price = raw["Low"][ticker].dropna()
    volume = raw["Volume"][ticker].dropna()
    
    vix = raw["Close"]["^VIX"].dropna()
    spy_close = raw["Close"]["SPY"].dropna()
    
    # 2. Build features
    df = build_sndk_features(
        close=close_price,
        open_price=open_price,
        high=high_price,
        low=low_price,
        volume=volume,
        vix=vix,
        spy_close=spy_close
    )
    
    if 'close' in df.columns:
        df = df.rename(columns={'close': 'close'})
        
    # Crop to the requested backtest window (3/1/2025 - 6/29/2026)
    # Note: SNDK IPO'd 2025-02-13; first valid rows after 20-day SMA warmup
    df = df.loc["2025-03-01":"2026-06-29"]
    logging.info(f"Generated {len(df)} feature rows for {ticker} in target window (Mar 2025 - Jun 2026)")
    config = SNDKLadderConfig(universe=[ticker])
    # --- High-Frequency Config ---
    config.entry_trigger_pct = 0.5    # Small dips trigger entries
    config.ivr_min = 20.0             # Lowered from 55 to increase trade frequency
    config.position_size_pct = 0.10   # 10% per rung (conservative after Perplexity Q4)
    config.macro_filter_spy_pct = 100.0
    config.max_rungs_per_side = 10
    config.profit_take_pct = 0.50     
    config.profit_take_pct_short = 0.25
    config.profit_dte_threshold = 20
    config.delta_breach_threshold = 0.70  
    config.initial_delta = 0.25       
    config.dte_target = 21            
    config.stop_loss_credit_mult = 3.0  
    config.initial_capital = 500_000.0
    
    engine = SNDKBacktestEngine(config)
    
    logging.info("Starting Walk-Forward Backtest...")
    # SNDK has ~330 usable rows (Mar 2025 - Jun 2026).
    # window_train=100 (5 months) → ~60+ qualifying signals for ML training
    # window_test=40  (2 months) → meaningful OOS period
    # step=40         (2 months) → gives 4-5 non-overlapping WF windows
    results_df, all_pnls = engine.walk_forward_backtest(
        df, n_trials_optuna=40, window_train=100, window_test=40, step=40
    )
    
    if len(all_pnls) == 0:
        print("No out-of-sample trades generated.")
        return
        
    print(f"\n--- Strategy Performance: SNDK Mar 2025 – Jun 2026 ---")
    print(f"Initial Capital: ${config.initial_capital:,.2f}")
    
    total_profit = sum(all_pnls)
    final_capital = config.initial_capital + total_profit
    years = len(df) / 252.0  # Actual trading days covered
    cagr = calculate_cagr(config.initial_capital, final_capital, max(years, 0.01))
    
    print(f"Final Capital:   ${final_capital:,.2f}")
    print(f"Total Profit:    ${total_profit:,.2f} ({(total_profit/config.initial_capital)*100:.2f}%)")
    print(f"CAGR:            {cagr*100:.2f}%")
    print(f"Total Trades:    {len(all_pnls)}")
    
    wins = len([p for p in all_pnls if p > 0])
    win_rate = (wins / len(all_pnls) * 100) if len(all_pnls) > 0 else 0
    print(f"Win Rate:        {win_rate:.1f}%")
    
    if 'regime' in df.columns:
        regime_counts = df['regime'].value_counts()
        print(f"\n--- Regime Distribution ---")
        for regime, count in regime_counts.items():
            print(f"  {regime}: {count} days ({count/len(df)*100:.1f}%)")

if __name__ == "__main__":
    main()
