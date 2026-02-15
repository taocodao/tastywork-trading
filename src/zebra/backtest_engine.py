import yfinance as yf
import pandas as pd
import numpy as np
import logging
import datetime
from typing import List, Dict

from src.zebra.exit_engine import ZebraExitEngine
from src.zebra.security_scorer import ZebraSecurityScorer 
from src.zebra.entry_timing import ZebraEntryTiming

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("ZebraBacktestEngine")

class ZebraBacktestEngine:
    """
    Enhanced Walk-Forward Backtester for ZEBRA Strategy.
    Integrates Scoring, Timing, and Exit Engines.
    """
    
    def __init__(self, initial_capital=100000, max_positions=8, verbose=False):
        self.output_log = []
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.verbose = verbose
        self.data_cache = {}
        
        # Modules
        self.scorer = ZebraSecurityScorer()
        self.timing = ZebraEntryTiming()
        self.exit_engine = ZebraExitEngine() 

    def log(self, msg):
        if self.verbose:
            print(msg)
        self.output_log.append(msg)

    def fetch_data(self, symbols: List[str], start_date="2024-01-01", end_date=None):
        """Pre-fetch data for optimization efficiency."""
        if self.verbose: print(f"Fetching data for {len(symbols)} symbols...")
        for sym in symbols:
            try:
                df = yf.download(sym, start=start_date, end=end_date, progress=False)
                if df.empty: continue
                
                # Flatten MultiIndex columns if present (yfinance quirk)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # Compute indicators ONCE
                df = self.scorer._compute_indicators(df)
                self.data_cache[sym] = df
            except Exception as e:
                if self.verbose: print(f"Error fetching {sym}: {e}")
        if self.verbose: print("Data fetch complete.")

    def run_simulation(self, params: Dict = None, simulation_start_date="2024-01-01") -> Dict:
        """
        Run simulation on cached data with specific parameters.
        Returns performance metrics dict.
        """
        if not self.data_cache:
            return {'error': 'No data'}
            
        # Convert to datetime for comparison
        sim_start = pd.to_datetime(simulation_start_date).tz_localize(None)
            
        # Reset State
        current_capital = self.initial_capital
        positions = [] 
        trade_history = []
        
        # Override Engine Params
        sim_exit_engine = ZebraExitEngine(params) if params else self.exit_engine
        
        # Build Timeline
        all_dates = sorted(list(set().union(*[df.index for df in self.data_cache.values()])))
        
        for current_date in all_dates:
            # Skip warm-up period
            if current_date.tz_localize(None) < sim_start:
                continue
            
            # A. Manage Existing Positions
            for pos in positions[:]:
                sym = pos['symbol']
                df = self.data_cache[sym]
                if current_date not in df.index: continue
                
                curr_row = df.loc[current_date]
                
                pos['current_price'] = curr_row['Close']
                pos['days_held'] = (current_date - pos['entry_date']).days
                pos['days_to_expiry'] = (pos['expiry_date'] - current_date).days
                pos['high_watermark'] = max(pos.get('high_watermark', 0), curr_row['Close'])
                pos['current_row'] = curr_row
                
                # Check Exit
                exit_res = sim_exit_engine.evaluate(pos)
                
                if exit_res['exit']:
                    # Close
                    pnl_dollar = (curr_row['Close'] - pos['entry_price']) * 0.90 * 100
                    pnl_pct = pnl_dollar / (pos['entry_debit'] * 100)
                    current_capital += (pos['entry_debit'] * 100) + pnl_dollar
                    
                    trade_history.append({
                        'symbol': sym,
                        'pnl': pnl_dollar,
                        'pnl_pct': pnl_pct, 
                        'reason': exit_res['reason'],
                        'days': pos['days_held'],
                        'entry_date': pos['entry_date'],
                        'exit_date': current_date
                    })
                    
                    self.log(f"  {current_date.date()} [SELL] {sym} {exit_res['reason']} P&L: ${pnl_dollar:.2f} ({pnl_pct:.1%})")
                    positions.remove(pos)
            
            # B. Check Entires
            if len(positions) < self.max_positions:
                candidates = []
                for sym, df in self.data_cache.items():
                    if current_date not in df.index: continue
                    if any(p['symbol'] == sym for p in positions): continue
                    
                    row = df.loc[current_date]
                    
                    # Score
                    score = self.scorer.score_symbol(sym, df.loc[:current_date])
                    min_req_score = params.get('min_score', 65)
                    if score['composite_score'] < min_req_score:
                        continue
                    
                    self.log(f"DEBUG: {current_date.date()} {sym} Passed Score: {score['composite_score']:.1f}")
                    
                    # Timing
                    prev_rows = df.loc[:current_date].iloc[:-1]
                    timing = self.timing.should_enter(sym, row, prev_rows, current_date)
                    if not timing['enter']:
                        self.log(f"DEBUG: {current_date.date()} {sym} Rejected by Timing: {timing['reason']}")
                        continue
                    
                    self.log(f"DEBUG: {current_date.date()} {sym} CANDIDATE FOUND")
                    candidates.append({
                        'symbol': sym,
                        'score': score['composite_score'],
                        'price': row['Close'],
                        'atr': row.get('ATR', 0)
                    })
                
                candidates.sort(key=lambda x: x['score'], reverse=True)
                for cand in candidates[:(self.max_positions - len(positions))]:
                    cost = cand['price'] * 0.50
                    entry_debit = cost
                    self.log(f"  {current_date.date()} [BUY] {cand['symbol']} @ {cand['price']:.2f} (Score: {cand['score']:.1f})")
                    expiry = current_date + datetime.timedelta(days=90)
                    positions.append({
                        'symbol': cand['symbol'],
                        'entry_date': current_date,
                        'expiry_date': expiry,
                        'entry_price': cand['price'],
                        'entry_debit': entry_debit,
                        'current_price': cand['price'],
                        'high_watermark': cand['price'],
                        'atr_at_entry': cand['atr'],
                        'days_held': 0,
                        'days_to_expiry': 90,
                        'score_at_entry': cand['score']
                    })
                    current_capital -= (cost * 100)
        
        # Calculate Metrics
        total_trades = len(trade_history)
        if total_trades == 0:
            return {'sharpe': -999, 'pnl': 0, 'trades': 0}
            
        df_trades = pd.DataFrame(trade_history)
        total_pnl = df_trades['pnl'].sum()
        win_rate = len(df_trades[df_trades['pnl'] > 0]) / total_trades
        
        avg_ret = df_trades['pnl'].mean()
        std_ret = df_trades['pnl'].std()
        sharpe = (avg_ret / std_ret) * np.sqrt(252) if std_ret != 0 else 0
        
        return {
            'sharpe': sharpe,
            'pnl': total_pnl,
            'win_rate': win_rate,
            'trades': total_trades,
            'history': trade_history,
            'final_capital': current_capital
        }

if __name__ == "__main__":
    # Test Run with Verbose=True
    engine = ZebraBacktestEngine(verbose=True)
    engine.fetch_data(["SPY"], start_date="2024-01-01", end_date="2024-04-01")
    
    # Run with default 'loose' parameters to see action
    res = engine.run_simulation({
        'profit_target_pct': 0.50, 
        'stop_loss_pct': -0.40,
        'min_score': 30 # Even looser
    })
    
    print("\n=== FINAL RESULTS ===")
    print(f"P&L: ${res['pnl']:.2f}")
    print(f"Win Rate: {res.get('win_rate', 0):.1%}")
    print(f"Trades: {res.get('trades', 0)}")
    print(f"Sharpe: {res.get('sharpe', 0):.2f}")
