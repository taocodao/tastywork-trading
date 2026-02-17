
import pandas as pd
import numpy as np
import logging
from datetime import datetime
import itertools

logger = logging.getLogger(__name__)

from src.zebra.regime_detector import REGIME_PARAMS

class ZebraParamOptimizer:
    def __init__(self, backtester):
        self.backtester = backtester
        
    def optimize(self, start_date, end_date):
        # ... (rest of method)
        
            if best_p:
                logger.info(f"Best for {regime}: {best_p} (Score: {best_score:.0f})")
                
                # Keep original non-optimized fields
                defaults = REGIME_PARAMS.get(regime, {})
                best_p['max_positions'] = defaults.get('max_positions', 6)
                best_p['allocation'] = defaults.get('allocation', 0.10)
                
                optimized_params[regime] = best_p
        
    def optimize(self, start_date, end_date):
        """
        Run grid search optimization for each regime.
        """
        logger.info(f"Starting Parameter Optimization ({start_date} to {end_date})...")
        
        # 1. Fetch Data
        self.backtester.fetch_data(start_date=start_date, end_date=end_date)
        
        # 2. Identify Regime Days
        regime_days = {'LOW_VOL': [], 'NORMAL': [], 'HIGH_VOL': []}
        
        # Iterate all dates in SPY data to classify
        spy_data = self.backtester.regime_detector.spy_data
        if spy_data is None or spy_data.empty:
            logger.error("No SPY data found for optimization.")
            return {}
            
        for date in spy_data.index:
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, pd.Timestamp) else date
            label, _ = self.backtester.regime_detector.get_regime(date)
            if label in regime_days:
                regime_days[label].append(date)
                
        # 3. Grid Search per Regime
        optimized_params = {}
        
        # Parameter Grid
        grid = {
            'trailing_stop_pct': [0.08, 0.10, 0.12, 0.15, 0.18, 0.20],
            'time_exit_days': [10, 15, 21, 25, 30, 45],
            'hard_stop_pct': [-0.20, -0.30, -0.40]
        }
        
        for regime, days in regime_days.items():
            if not days: continue
            
            logger.info(f"Optimizing {regime} ({len(days)} days)...")
            best_score = -float('inf')
            best_p = None
            
            # Generate combinations
            keys, values = zip(*grid.items())
            combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
            
            for params in combinations:
                # Run backtest only on these specific regime days
                # This is tricky because a trade might start in one regime and end in another.
                # Standard approach: Run full sim, but filter Entry Dates matching this regime.
                
                # We need a way to run the backtester efficiently.
                # Instead of re-running the WHOLE sim 100 times, let's inject params.
                
                # Actually, simpler approach:
                # Run the backtester ONCE with a strategy that accepts a parameter override.
                # But we validly want to test specific params.
                # Let's run a "Partial Simulation" - only enter trades if date in days.
                
                # NOTE: This simplistic optimization might be slow if data is huge.
                # Given 30 symbols * 4 years, it's fast enough.
                
                params['allocation'] = 0.10 # Fixed for potential comparison
                params['max_positions'] = 5
                
                # Override run method logic or use a specialized run?
                # We can use backtester.run() but we need to pass these params as THE params.
                # And we need to restrict entries to 'days'.
                
                # Let's assume backtester has a method `run_optimization_subset` or we mock it.
                # We'll use the standard run() but use `strategy_params` to enforce these values,
                # AND we will post-filter trades that started in this regime.
                
                self.backtester.run(
                    strategy="NEW", 
                    use_regime=False, # We force specific params
                    strategy_params=params, 
                    collect_training=False
                )
                
                # Filter results for trades entered during this regime
                results = pd.DataFrame(self.backtester.results)
                if results.empty: continue
                
                # Convert Entry to timestamp for filtering
                # Note: 'entry' key in results is a date object usually
                if 'entry' not in results.columns: continue
                
                # Filter indices where entry date is in our regime_days list
                # This can be slow. Faster: set index to entry.
                results['entry'] = pd.to_datetime(results['entry'])
                subset = results[results['entry'].isin(days)]
                
                if subset.empty: continue
                
                # Score: Risk-Adjusted Return
                total_pnl = subset['pnl'].sum()
                win_rate = len(subset[subset['pnl'] > 0]) / len(subset)
                # Max Drawdown estimation (simplified as max loss trade)
                max_loss = subset['pnl'].min()
                if max_loss >= 0: max_loss = -1 # Avoid div/0
                
                # Simple proprietary score: Total P&L * Win Rate (penalize low win rates)
                score = total_pnl * win_rate 
                
                if score > best_score:
                    best_score = score
                    best_p = params
            
            if best_p:
                logger.info(f"Best for {regime}: {best_p} (Score: {best_score:.0f})")
                
                # Keep original non-optimized fields
                defaults = REGIME_PARAMS.get(regime, {})
                best_p['max_positions'] = defaults.get('max_positions', 6)
                best_p['allocation'] = defaults.get('allocation', 0.10)
                
                optimized_params[regime] = best_p
                
        return optimized_params
