#!/usr/bin/env python3
import os
import sys
import argparse
import pandas as pd
from datetime import datetime
import logging

# Ensure we can import the production ML modules
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import exact production modules for 100% fidelity
from src.turbocore_pro.data_pipeline import TurboCoreDataPipeline
from src.turbocore_pro.base_strategy import BaseStrategy
from src.turbocore_pro.ml.regime_detector import TurboCoreRegimeDetector
from src.turbocore_pro.ml.signal_scorer import TurboCoreSignalScorer
from src.turbocore_pro.allocation_optimizer import AllocationOptimizer

# Import simulation components
from sim.portfolio import SimPortfolio
from sim.simulate_orders import execute_rebalance
from sim.leaps_pricer import estimate_leaps_price
from sim.results import compute_results

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("TurboCoreSim")

def main():
    parser = argparse.ArgumentParser(description="TurboCore Pro Backtesting Simulator")
    parser.add_argument("--start", type=str, default="2024-03-24", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2025-03-24", help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=25000.0, help="Starting capital")
    args = parser.parse_args()
    
    logger.info(f"🔄 TurboCore Pro Backtest {args.start} -> {args.end} ($ {args.capital:,.2f})")
    
    # 1. Pipeline Initialization
    logger.info("Initializing production ML pipeline modules...")
    data_pipe = TurboCoreDataPipeline()
    # Fetch 5 years to ensure EMA/SMA/Rolling features have enough burn-in before the start date
    logger.info("Fetching historical data (10y window for feature burn-in)...")
    data_pipe.fetch_data("10y")
    master_df = data_pipe.prepare_core_features()
    
    if master_df.empty:
        logger.error("Data fetch failed. Exiting.")
        return
        
    logger.info(f"Extracted {len(master_df)} raw market days.")
        
    # 2. Run Base Rules + ML Models over entire history
    logger.info("Running HMM and XGBoost models...")
    base = BaseStrategy(master_df)
    df = base.evaluate()
    
    regime_detector = TurboCoreRegimeDetector()
    scorer = TurboCoreSignalScorer()
    
    df = regime_detector.predict_regimes(df)
    df = scorer.predict_confidence(df)
    
    # 3. Slice to backtest window
    allocator = AllocationOptimizer()
    
    start_dt = pd.to_datetime(args.start)
    end_dt = pd.to_datetime(args.end)
    
    # Filter df to backtest window
    mask = (df.index >= start_dt) & (df.index <= end_dt)
    bt_df = df.loc[mask].copy()
    
    if bt_df.empty:
        logger.error(f"No data points found between {args.start} and {args.end}")
        return
        
    logger.info(f"Running simulation loop over {len(bt_df)} trading days...")
    
    portfolio = SimPortfolio(initial_capital=args.capital)
    equity_curve = []
    
    rebalances = 0
    regime_counts = {"BULL": 0, "SIDEWAYS": 0, "BEAR": 0, "BEAR_SMA_FORCED": 0}
    last_alloc = None
    
    # 4. Simulation Loop
    for idx, row in bt_df.iterrows():
        date_str = idx.strftime('%Y-%m-%d')
        
        regime = str(row.get('final_regime', 'SIDEWAYS'))
        base_signal = int(row.get('base_signal', 0))
        confidence = float(row.get('ml_confidence', 0.5))
        is_sma_forced = bool(row.get('qqq_below_sma200_sell', False))
        qqq_drawdown = float(row.get('qqq_drawdown_ath', 0.0))
        
        if is_sma_forced:
            regime = "BEAR_SMA_FORCED"
            
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
        
        target_allocation = allocator.get_target_allocation(
            regime=regime,
            signal=base_signal,
            ml_confidence=confidence,
            qqq_drawdown=qqq_drawdown
        )
        
        live_prices = {
            'QQQ': row.get('qqq_close', 0.0),
            'TQQQ': row.get('tqqq_close', 0.0),
            'QLD': MasterDF_LivePrice(data_pipe, 'QLD', idx),
            'SGOV': MasterDF_LivePrice(data_pipe, 'SGOV', idx),
            'VIX': row.get('vix_close', 20.0)
        }
        
        # Estimate LEAPS price for this day if needed
        # We need LEAPS price regardless of action to revalue portfolio accurately
        leaps_bs_price = estimate_leaps_price(
            qqq_price=live_prices['QQQ'], 
            vix_price=live_prices['VIX'], 
            dte=365
        )
        live_prices['QQQ_LEAPS'] = leaps_bs_price
        
        # Rebalance if targets changed
        if target_allocation != last_alloc:
            execute_rebalance(portfolio, target_allocation, live_prices, date_str, slippage_pct=0.001)
            last_alloc = target_allocation.copy()
            rebalances += 1
            
        # Daily MTM
        net_liq = portfolio.total_value(live_prices, leaps_bs_price)
        equity_curve.append(net_liq)
        
    bt_df['sim_net_liq'] = equity_curve
    
    # 5. Calculate Results
    results = compute_results(bt_df['sim_net_liq'])
    
    print()
    print("=" * 60)
    print(f"📊 TURBOCORE PRO BACKTEST — {args.start} to {args.end}")
    print("=" * 60)
    print(f"  Starting Capital:  ${args.capital:,.2f}")
    print(f"  Ending Value:      ${equity_curve[-1]:,.2f}")
    print(f"  CAGR:              {results['CAGR']:.1f}%")
    print(f"  Sharpe Ratio:      {results['Sharpe']:.2f}")
    print(f"  Max Drawdown:      {results['MaxDrawdown']:.1f}%")
    print(f"  Total Return:      {results['TotalReturn']:.1f}%")
    print("-" * 60)
    print(f"  Signals Generated: {len(bt_df)}")
    print(f"  Regime Breakdown:  {regime_counts}")
    print(f"  Rebalances:        {rebalances}")
    print("=" * 60)
    print()

def MasterDF_LivePrice(data_pipe, symbol, idx):
    """Helper to safely extract price for non-core symbols from the raw fetched data at a specific date"""
    try:
        closest_idx = data_pipe.data[symbol].index.asof(idx)
        if pd.isna(closest_idx): return 100.0 # fallback
        return float(data_pipe.data[symbol].loc[closest_idx, 'Close'])
    except Exception:
        # Fallback values if data failed to download
        if symbol == 'SGOV': return 100.0
        if symbol == 'QLD': return 65.0
        return 50.0

if __name__ == "__main__":
    main()
