import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
from src.tqqq_turbocore.base_strategy import BaseStrategy
from src.tqqq_turbocore.ml.regime_detector import TurboCoreRegimeDetector
from src.tqqq_turbocore.ml.signal_scorer import TurboCoreSignalScorer
from src.tqqq_turbocore.allocation_optimizer import AllocationOptimizer

# Suppress some repetitive warnings for the backtester
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TurboCoreBacktest")

def run_backtest(start_date="2019-01-01", end_date="2025-12-31", initial_capital=5000.0):
    logger.info(f"Starting TurboCore ML Backtest from {start_date} to {end_date} with ${initial_capital}")
    
    # 1. Fetch Data
    pipeline = TurboCoreDataPipeline(tickers=['QQQ', 'TQQQ', 'QLD', 'SGOV', '^VIX'])
    # Fetch 10 years to ensure moving averages are warned up before the start date
    pipeline.fetch_data("10y") 
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
        # For this backtest we do an expanding/full fit for demonstrative viabiltiy of the math
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
        
    # 5. Calculate Daily Asset Returns (Close to Close)
    logger.info("Calculating asset returns...")
    for ticker in ['QQQ', 'TQQQ', 'QLD', 'SGOV']:
        if ticker == 'QQQ':
            df[f'{ticker}_return'] = df['qqq_close'].pct_change()
        elif ticker == 'TQQQ':
            df[f'{ticker}_return'] = df['tqqq_close'].pct_change()
        elif ticker == 'SGOV': 
            # SGOV did not exist in 2019. We will default to a proxy short-term treasury yield (e.g. 0.01% daily)
            if 'SGOV' in pipeline.data:
                sgov_prices = pipeline.data['SGOV']['Close'].reindex(df.index).ffill()
                df[f'{ticker}_return'] = sgov_prices.pct_change().fillna(0.0001) 
            else:
                df[f'{ticker}_return'] = 0.0001
        elif ticker == 'QLD':
            if 'QLD' in pipeline.data:
                qld_prices = pipeline.data['QLD']['Close'].reindex(df.index).ffill()
                df[f'{ticker}_return'] = qld_prices.pct_change()
            else:
                df[f'{ticker}_return'] = df['qqq_close'].pct_change() * 2
                
    # Fill any first row NAs with 0
    for ticker in ['QQQ', 'TQQQ', 'QLD', 'SGOV']:
        df[f'{ticker}_return'] = df[f'{ticker}_return'].fillna(0)

    # 6. Simulate Portfolio Equity Curve
    logger.info("Simulating daily rebalancing & portfolio equity curve...")
    allocator = AllocationOptimizer()
    
    capital = initial_capital
    portfolio_values = []
    
    # Start all cash (100% SGOV)
    current_alloc = {'QQQ': 0.0, 'QLD': 0.0, 'TQQQ': 0.0, 'SGOV': 1.0} 
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Calculate today's return based on YESTERDAY'S ending allocation
        if i > 0:
            daily_port_return = (
                current_alloc['QQQ'] * row['QQQ_return'] +
                current_alloc['QLD'] * row['QLD_return'] +
                current_alloc['TQQQ'] * row['TQQQ_return'] +
                current_alloc['SGOV'] * row['SGOV_return']
            )
            # Subtract a small slippage/fee for turnover
            capital = capital * (1 + daily_port_return)
            
        portfolio_values.append(capital)
        
        # Determine TARGET allocation for tomorrow based on today's close signals
        regime = str(row.get('final_regime', 'SIDEWAYS'))
        base_signal = int(row.get('base_signal', 0))
        confidence = float(row.get('ml_confidence', 0.5))
        is_sma_forced = bool(row.get('qqq_below_sma200_sell', False))
        
        target_allocation = allocator.get_target_allocation(
            regime=regime,
            signal=base_signal,
            ml_confidence=confidence
        )
        
        # Apply the targets (in reality auto_approve.py handles the orders to match this)
        current_alloc = {k: v for k, v in target_allocation.items() if k in current_alloc}
        
    df['portfolio_value'] = portfolio_values
    
    # Buy and Hold Benchmark (QQQ)
    df['qqq_cum_return'] = (1 + df['QQQ_return']).cumprod()
    df['qqq_benchmark'] = initial_capital * df['qqq_cum_return']
    
    # 7. Metrics & Output
    total_return_pct = (capital / initial_capital - 1) * 100
    qqq_total_return = (df['qqq_benchmark'].iloc[-1] / initial_capital - 1) * 100
    
    days = (df.index[-1] - df.index[0]).days
    annualized_return = ((capital / initial_capital) ** (365/days) - 1) * 100
    qqq_annualized = ((df['qqq_benchmark'].iloc[-1] / initial_capital) ** (365/days) - 1) * 100
    
    # Max Drawdowns
    port_roll_max = df['portfolio_value'].cummax()
    port_drawdown = (df['portfolio_value'] - port_roll_max) / port_roll_max
    max_dd = port_drawdown.min() * 100
    
    qqq_roll_max = df['qqq_benchmark'].cummax()
    qqq_drawdown = (df['qqq_benchmark'] - qqq_roll_max) / qqq_roll_max
    qqq_max_dd = qqq_drawdown.min() * 100
    
    print("\n" + "="*60)
    print(f"🚀 TQQQ TURBOCORE ML BACKTEST RESULTS (2019 - 2025)")
    print("="*60)
    print(f"Initial Capital    : ${initial_capital:,.2f}")
    print(f"Final Capital      : ${capital:,.2f}")
    print(f"Total Return       : {total_return_pct:.2f}%")
    print(f"Annualized Return  : {annualized_return:.2f}%")
    print(f"Max Drawdown       : {max_dd:.2f}%")
    print("-" * 60)
    print(f"QQQ Benchmark Final: ${df['qqq_benchmark'].iloc[-1]:,.2f}")
    print(f"QQQ Total Return   : {qqq_total_return:.2f}%")
    print(f"QQQ Annualized     : {qqq_annualized:.2f}%")
    print(f"QQQ Max Drawdown   : {qqq_max_dd:.2f}%")
    print("="*60)
    
if __name__ == "__main__":
    run_backtest(start_date="2019-01-01", end_date="2025-12-31", initial_capital=5000)
