"""
TurboBounce Multi-Ticker Backtester
===================================
Simulates the performance difference between:
- Mode A (Dedicated 50/50: 3 TQQQ + 3 Multi-Ticker)
- Mode B (Unified 100%: 6 slots, survival of the fittest)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import logging
from tqdm import tqdm

from src.turbobounce.universe import get_turbobounce_symbols, get_category_for_symbol
from src.turbobounce.scoring import TurboBounceScorer
from src.turbobounce.scanner import TurboBounceScanner
from src.turbobounce.risk_manager import TurboBounceRiskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TurboBounceBacktest")

class MockDataProvider:
    """Provides historical slice to the scanner without making fresh API calls."""
    def __init__(self, historical_data: dict, current_date: pd.Timestamp):
        self.historical_data = historical_data
        self.current_date = current_date
        
    def fetch_batch_data(self, symbols):
        """Mocks the output of data_provider.fetch_batch_data"""
        metrics = {}
        for symbol, df in self.historical_data.items():
            if symbol not in symbols: continue
            
            # Get data up to current_date
            sub_df = df[df.index <= self.current_date]
            if len(sub_df) < 200: continue
            
            latest = sub_df.iloc[-1]
            prev = sub_df.iloc[-2]
            prev3 = sub_df.iloc[-4] if len(sub_df) >= 4 else sub_df.iloc[-1]
            
            close = float(latest['Close'])
            sma_20 = float(sub_df['Close'].rolling(20).mean().iloc[-1])
            std_20 = float(sub_df['Close'].rolling(20).std().iloc[-1])
            sma_200 = float(sub_df['Close'].rolling(200).mean().iloc[-1])
            
            pct_b = (close - (sma_20 - 2*std_20)) / (4*std_20) if std_20 > 0 else 0.5
            
            metrics[symbol] = {
                'symbol': symbol,
                'category': get_category_for_symbol(symbol),
                'close': close,
                'avg_volume': float(sub_df['Volume'].rolling(20).mean().iloc[-1]),
                'rsi_2': float(self._calc_rsi(sub_df['Close'], 2)),
                'pct_b': float(pct_b),
                'ret_3d': float((close - prev3['Close']) / prev3['Close']),
                'dist_sma_200': float((close - sma_200) / sma_200) if sma_200 > 0 else 0.0,
                'iv_rank': 50.0 # Mock average IV rank for historical backtesting
            }
            
        return metrics
        
    def _calc_rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 100

class TurboBounceBacktester:
    def __init__(self, start_date='2020-01-01', end_date='2024-01-01', initial_capital=50000):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        
        self.historical_data = {}
        self.trading_days = []
        
    def fetch_data(self):
        """Downloads historical data for the universe."""
        symbols = get_turbobounce_symbols()
        logger.info(f"Downloading historical data for {len(symbols)} tickers...")
        # Fetch an extra year prior to start_date for 200 SMA
        fetch_start = pd.to_datetime(self.start_date) - pd.DateOffset(years=1)
        
        data = yf.download(symbols, start=fetch_start, end=self.end_date, group_by='ticker', progress=False)
        
        # In case of single ticker vs multi-ticker yfinance structure
        if len(symbols) == 1:
            self.historical_data[symbols[0]] = data
            self.trading_days = data[data.index >= self.start_date].index
        else:
            for sym in symbols:
                if sym in data:
                    self.historical_data[sym] = data[sym].dropna()
                    
            # Use SPY as reference for trading days
            if 'SPY' in self.historical_data:
                ref_df = self.historical_data['SPY']
                self.trading_days = ref_df[ref_df.index >= self.start_date].index
            
        logger.info("Data download complete.")

    def run_simulation(self, mode: str):
        """
        Runs the backtest using the specific allocation mode.
        mode options:
          - MODE_A       : Dedicated 50/50 (3 TQQQ + 3 Multi-Ticker)
          - MODE_B       : Unified 100% (6 shared slots, TQQQ competes)
          - TQQQ_ONLY    : 6 slots reserved for TQQQ only
          - MULTI_ONLY   : 6 slots, TQQQ excluded from universe
        """
        logger.info(f"Starting Simulation for {mode}...")
        
        risk_manager = TurboBounceRiskManager(mode="MODE_B") # Use MODE_B logic as base; slot gating is done inline
        
        MAX_SLOTS = 6
        MOCK_HOLD_DAYS = 15
        
        # Per-mode restrictions
        ALLOW_TQQQ   = mode in ("MODE_A", "MODE_B", "TQQQ_ONLY")
        ALLOW_MULTI  = mode in ("MODE_A", "MODE_B", "MULTI_ONLY")
        MAX_TQQQ     = 3 if mode == "MODE_A" else (MAX_SLOTS if mode == "TQQQ_ONLY" else MAX_SLOTS)
        MAX_MULTI    = 3 if mode == "MODE_A" else (0 if mode == "TQQQ_ONLY" else MAX_SLOTS)
        
        # Portfolio State
        capital = self.initial_capital
        open_positions = []
        trade_log = []
        
        for current_date in tqdm(self.trading_days, desc=mode, leave=False):
            # 1. Age existing positions and close them if they hit MOCK_HOLD_DAYS
            closed_today = []
            remaining_positions = []
            
            for pos in open_positions:
                days_held = (current_date - pos['entry_date']).days
                if days_held >= MOCK_HOLD_DAYS:
                    # Mock exit. 
                    # If it was an oversold signal, checking if current price > entry price.
                    # We will use purely statistical mock returns based on win rate for rapid testing of allocation logic.
                    close_price = self._get_price(pos['symbol'], current_date)
                    entry_price = pos['entry_price']
                    
                    if close_price > 0 and entry_price > 0:
                        ret = (close_price - entry_price) / entry_price
                        if pos['direction'] == 'BEARISH': ret = -ret
                        
                        # Apply naive option leverage (e.g. 3x)
                        pnl = pos['capital_allocated'] * ret * 3.0
                    else:
                        pnl = 0
                        
                    capital += pos['capital_allocated'] + pnl
                    pos['exit_date'] = current_date
                    pos['pnl'] = pnl
                    closed_today.append(pos)
                else:
                    remaining_positions.append(pos)
                    
            open_positions = remaining_positions
            trade_log.extend(closed_today)
            
            # 2. Run Scanner for today
            mock_provider = MockDataProvider(self.historical_data, current_date)
            scanner = TurboBounceScanner(mock_provider)
            try:
                picks = scanner.run_daily_scan()
            except Exception as e:
                # Not enough data early on
                continue
                
            all_picks = picks['top_oversold'] + picks['top_overbought']
            
            # 3. Allocation logic
            for pick in all_picks:
                is_tqqq = pick.symbol == 'TQQQ'
                target_pool = "TQQQ" if is_tqqq else "MULTI_TICKER"
                
                # Mode-level filter
                if is_tqqq and not ALLOW_TQQQ: continue
                if not is_tqqq and not ALLOW_MULTI: continue
                
                # Slot limits
                tqqq_open  = sum(1 for p in open_positions if p.get('symbol') == 'TQQQ')
                multi_open = sum(1 for p in open_positions if p.get('pool') == 'MULTI_TICKER')
                total_open = len(open_positions)
                
                if total_open >= MAX_SLOTS: continue
                if is_tqqq  and tqqq_open  >= MAX_TQQQ:  continue
                if not is_tqqq and multi_open >= MAX_MULTI: continue
                
                if risk_manager.check_correlation_guard(pick.category, open_positions):
                    slot_capital = self.initial_capital / MAX_SLOTS
                    entry_price  = self._get_price(pick.symbol, current_date)
                    
                    open_positions.append({
                        'symbol':            pick.symbol,
                        'pool':              target_pool,
                        'category':          pick.category,
                        'direction':         'BULLISH' if pick in picks['top_oversold'] else 'BEARISH',
                        'entry_date':        current_date,
                        'entry_price':       entry_price,
                        'capital_allocated': slot_capital
                    })
                    capital -= slot_capital
        
        # End of simulation stats
        total_pnl = sum(t['pnl'] for t in trade_log)
        wins = sum(1 for t in trade_log if t['pnl'] > 0)
        win_rate = wins / len(trade_log) if trade_log else 0
        
        tqqq_trades = sum(1 for t in trade_log if t['symbol'] == 'TQQQ')
        multi_trades = len(trade_log) - tqqq_trades
        
        return {
            'mode': mode,
            'total_return_pct': (total_pnl / self.initial_capital) * 100,
            'win_rate': win_rate * 100,
            'total_trades': len(trade_log),
            'tqqq_trade_count': tqqq_trades,
            'multi_trade_count': multi_trades,
            'final_capital': capital + sum(p['capital_allocated'] for p in open_positions)
        }
        
    def _get_price(self, symbol, date):
        try:
            df = self.historical_data.get(symbol)
            if df is not None:
                # Use asof to get nearest preceding date if holiday etc
                idx = df.index.get_indexer([date], method='pad')[0]
                if idx >= 0:
                    return df.iloc[idx]['Close']
        except:
            pass
        return 0.0

if __name__ == "__main__":
    import logging, sys
    # Suppress verbose scanner spam; show only warnings
    logging.getLogger('src.turbobounce.scanner').setLevel(logging.WARNING)
    logging.getLogger('src.turbobounce.risk_manager').setLevel(logging.WARNING)

    backtester = TurboBounceBacktester(start_date='2019-01-01', end_date='2025-01-01')
    backtester.fetch_data()
    
    modes = [
        ("MODE_B", "Mode B – Unified 100%"),
    ]
    
    results = []
    for mode_key, label in modes:
        r = backtester.run_simulation(mode_key)
        r['label'] = label
        results.append(r)
    
    # Print comparison table
    col_w = 42
    print("\n" + "=" * 90)
    print(f"{'Strategy':<{col_w}} {'Return %':>9} {'Win Rate':>9} {'Trades':>7} {'TQQQ':>6} {'Multi':>6} {'Final $':>10}")
    print("-" * 90)
    for r in results:
        print(f"{r['label']:<{col_w}} {r['total_return_pct']:>+8.2f}% {r['win_rate']:>8.1f}% {r['total_trades']:>7} {r['tqqq_trade_count']:>6} {r['multi_trade_count']:>6} ${r['final_capital']:>9,.2f}")
    print("=" * 90)
