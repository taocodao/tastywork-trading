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

# Suppress some repetitive warnings for the backtester
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TurboCoreProBacktest")

def run_backtest(start_date="2010-01-01", end_date="2026-03-01", initial_capital=10000.0):
    logger.info(f"Starting TurboCore Pro LEAPS Backtest from {start_date} to {end_date} with ${initial_capital}")
    
    # 1. Fetch Data
    pipeline = TurboCoreDataPipeline(tickers=['QQQ', 'TQQQ', 'QLD', 'SGOV', '^VIX'])
    pipeline.fetch_data("16y") # Need long history for ATH and SMA200
    raw_df = pipeline.prepare_core_features()
    
    # Filter by date range after calculating features
    df = raw_df[(raw_df.index >= start_date) & (raw_df.index <= end_date)].copy()
    
    if df.empty:
        logger.error("No data available for the specified date range.")
        return
        
    logger.info(f"Backtesting over {len(df)} trading days.")
    
    # 2. Base Strategy Rules
    strategy = BaseStrategy(df)
    df = strategy.evaluate()
    
    # 3. ML Regime Detector (HMM)
    detector = TurboCoreRegimeDetector()
    try:
        detector.fit(raw_df) 
        df = detector.predict_regimes(df)
    except Exception as e:
        logger.error(f"HMM Regime detection failed: {e}")
        df['final_regime'] = 'SIDEWAYS'
        
    # 4. ML Signal Scorer (XGBoost)
    scorer = TurboCoreSignalScorer()
    try:
        scorer.fit(raw_df) 
        df = scorer.predict_confidence(df)
    except Exception as e:
        logger.error(f"XGBoost scoring failed: {e}")
        df['ml_confidence'] = 0.5
        
    # 5. Calculate Daily Asset Returns
    logger.info("Calculating asset returns...")
    
    # Base QQQ Returns
    df['QQQ_return'] = df['qqq_close'].pct_change()
    
    # QLD Returns
    if 'QLD' in pipeline.data:
        qld_prices = pipeline.data['QLD']['Close'].reindex(df.index).ffill()
        df['QLD_return'] = qld_prices.pct_change()
    else:
        df['QLD_return'] = df['QQQ_return'] * 2
        
    # SGOV Returns
    if 'SGOV' in pipeline.data:
        sgov_prices = pipeline.data['SGOV']['Close'].reindex(df.index).ffill()
        df['SGOV_return'] = sgov_prices.pct_change().fillna(0.0002) 
    else:
        df['SGOV_return'] = 0.0002
        
    # Dynamic Theta Model (Fix #3)
    leaps_leverage = 3.75
    df['theta_annual'] = 0.075
    df.loc[df['final_regime'] == 'BULL', 'theta_annual'] = 0.045
    df.loc[df['final_regime'] == 'SIDEWAYS', 'theta_annual'] = 0.065
    df['daily_theta_drag'] = df['theta_annual'] / 252.0
    
    df['QQQ_LEAPS_return'] = (df['QQQ_return'] * leaps_leverage) - df['daily_theta_drag']
                
    # Fill NAs
    for ticker in ['QQQ', 'QQQ_LEAPS', 'QLD', 'SGOV']:
        df[f'{ticker}_return'] = df[f'{ticker}_return'].fillna(0)

    # 6. Simulate Portfolio Equity Curve
    logger.info("Simulating daily rebalancing & portfolio equity curve...")
    allocator = AllocationOptimizer()
    
    capital = initial_capital
    portfolio_values = []
    
    # Start all cash (100% SGOV)
    current_alloc = {'QQQ': 0.0, 'QLD': 0.0, 'QQQ_LEAPS': 0.0, 'SGOV': 1.0} 
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Calculate today's return based on YESTERDAY'S ending allocation
        if i > 0:
            daily_port_return = (
                current_alloc.get('QQQ', 0) * row['QQQ_return'] +
                current_alloc.get('QLD', 0) * row['QLD_return'] +
                current_alloc.get('QQQ_LEAPS', 0) * row['QQQ_LEAPS_return'] +
                current_alloc.get('SGOV', 0) * row['SGOV_return']
            )
            
            capital = capital * (1 + daily_port_return)
            
        portfolio_values.append(capital)
        
        # Target for tomorrow
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
        
        # Calculate expected turnover today (this represents slippage that will hit the capital when rebalancing happens)
        etf_turnover = sum(abs(target_allocation.get(k, 0) - current_alloc.get(k, 0)) for k in ['QQQ', 'QLD', 'SGOV'])
        leaps_turnover = abs(target_allocation.get('QQQ_LEAPS', 0) - current_alloc.get('QQQ_LEAPS', 0))
        
        # Simulating transaction-based slippage directly against capital (Fix #2)
        if etf_turnover > 0.01:
            capital -= capital * (etf_turnover * 0.0002) # 2 bps per ETF rebalance turnover
            
        if leaps_turnover > 0.01:
            capital -= capital * (leaps_turnover * 0.001) # 10 bps bid-ask spread per LEAPS weight rebalance
            
        # LEAPS Roll cost: Twice a year
        if i > 0:
            prev_date = df.index[i-1]
            current_date = df.index[i]
            if current_date.month in [6, 12] and prev_date.month not in [6, 12]:
                leaps_weight = current_alloc.get('QQQ_LEAPS', 0)
                if leaps_weight > 0:
                    capital -= capital * (leaps_weight * 0.01) # 1% roll cost on the LEAPS sleeve
        
        current_alloc = target_allocation.copy()
        
    df['portfolio_value'] = portfolio_values
    
    # Buy and Hold Benchmark (QQQ)
    df['qqq_cum_return'] = (1 + df['QQQ_return']).cumprod()
    df['qqq_benchmark'] = initial_capital * df['qqq_cum_return']
    
    # QQQ LEAPS Naked Benchmark
    df['leaps_cum_return'] = (1 + df['QQQ_LEAPS_return']).cumprod()
    df['leaps_benchmark'] = initial_capital * df['leaps_cum_return']
    
    # 7. Metrics & Output
    total_return_pct = (capital / initial_capital - 1) * 100
    qqq_total_return = (df['qqq_benchmark'].iloc[-1] / initial_capital - 1) * 100
    leaps_total_return = (df['leaps_benchmark'].iloc[-1] / initial_capital - 1) * 100
    
    days = (df.index[-1] - df.index[0]).days
    annualized_return = ((capital / initial_capital) ** (365/days) - 1) * 100
    qqq_annualized = ((df['qqq_benchmark'].iloc[-1] / initial_capital) ** (365/days) - 1) * 100
    leaps_annualized = ((df['leaps_benchmark'].iloc[-1] / initial_capital) ** (365/days) - 1) * 100
    
    # Max Drawdowns
    port_roll_max = df['portfolio_value'].cummax()
    port_drawdown = (df['portfolio_value'] - port_roll_max) / port_roll_max
    max_dd = port_drawdown.min() * 100
    
    qqq_roll_max = df['qqq_benchmark'].cummax()
    qqq_drawdown = (df['qqq_benchmark'] - qqq_roll_max) / qqq_roll_max
    qqq_max_dd = qqq_drawdown.min() * 100
    
    leaps_roll_max = df['leaps_benchmark'].cummax()
    leaps_drawdown = (df['leaps_benchmark'] - leaps_roll_max) / leaps_roll_max
    leaps_max_dd = leaps_drawdown.min() * 100
    
    print("\n" + "="*60)
    start_yr = df.index[0].year
    end_yr = df.index[-1].year
    print(f"🚀 TURBOCORE PRO v2.0 LEAPS-ENHANCED BACKTEST ({start_yr} - {end_yr})")
    print("="*60)
    print(f"Initial Capital    : ${initial_capital:,.2f}")
    print(f"Final Capital      : ${capital:,.2f}")
    print(f"Total Return       : {total_return_pct:,.2f}%")
    print(f"Annualized Return  : {annualized_return:,.2f}%")
    print(f"Max Drawdown       : {max_dd:.2f}%")
    print("-" * 60)
    print(f"QQQ Benchmark Final: ${df['qqq_benchmark'].iloc[-1]:,.2f}")
    print(f"QQQ Annualized     : {qqq_annualized:.2f}%")
    print(f"QQQ Max Drawdown   : {qqq_max_dd:.2f}%")
    print("-" * 60)
    print(f"Unfiltered LEAPS ($): ${df['leaps_benchmark'].iloc[-1]:,.2f}")
    print(f"Unfiltered LEAPS Ann: {leaps_annualized:.2f}%")
    print(f"Unfiltered LEAPS MDD: {leaps_max_dd:.2f}%")
    print("="*60)
    
if __name__ == "__main__":
    run_backtest(start_date="2019-01-01", end_date="2026-03-01", initial_capital=5000)
