from datetime import datetime, timedelta
import pandas as pd
import numpy as np

class ZebraEntryTiming:
    """
    Regime-aware entry timing engine.
    Uses ATR % as a volatility regime proxy.
    """
    
    def __init__(self):
        # Regime thresholds (ATR %)
        self.LOW_VOL_THRESHOLD = 1.5
        self.HIGH_VOL_THRESHOLD = 3.5
        self.CRISIS_THRESHOLD = 5.0
        
        # Calendar events (Block dates)
        self.BLOCKED_DATES = [
            # 2024 FOMC Dates (Example)
            '2024-01-31', '2024-03-20', '2024-05-01', '2024-06-12', 
            '2024-07-31', '2024-09-18', '2024-11-07', '2024-12-18',
            # 2025 Placeholder
            '2025-01-29', '2025-03-19'
        ]

    def should_enter(self, symbol: str, row: pd.Series, prev_rows: pd.DataFrame, current_date) -> dict:
        """
        Determines if entry is safe based on regime and timing.
        """
        # 1. Check Calendar
        date_str = current_date.strftime('%Y-%m-%d')
        if date_str in self.BLOCKED_DATES:
            return {'enter': False, 'reason': 'Calendar Event (FOMC/CPI)'}
            
        # 2. Detect Regime
        regime = self._detect_regime(row)
        
        if regime == 'CRISIS':
            return {'enter': False, 'reason': 'Crisis Regime (High Vol)'}
            
        # 3. Momentum Confirmation
        mom_check = self._momentum_confirmation(row, prev_rows)
        if not mom_check:
             # In strict mode, we might block. For now, just flag.
             # return {'enter': False, 'reason': 'No Momentum Confirmation'}
             pass

        # Adjust parameters based on regime
        params = self._get_regime_params(regime)
        
        return {
            'enter': True,
            'regime': regime,
            'adjusted_params': params,
            'reason': f"Safe Entry ({regime})"
        }

    def _detect_regime(self, row):
        atr = row.get('ATR', 0)
        close = row['Close']
        if close == 0: return 'NORMAL'
        
        atr_pct = (atr / close) * 100
        
        if atr_pct < self.LOW_VOL_THRESHOLD:
            return 'LOW_VOL'
        elif atr_pct > self.CRISIS_THRESHOLD:
            return 'CRISIS'
        elif atr_pct > self.HIGH_VOL_THRESHOLD:
            return 'HIGH_VOL'
        else:
            return 'NORMAL'

    def _get_regime_params(self, regime):
        # Default Params
        params = {
            'profit_target_pct': 0.50,
            'stop_loss_pct': -0.40,
            'time_exit_days': 30,
            'position_size_multiplier': 1.0,
            'min_score': 65
        }
        
        if regime == 'LOW_VOL':
            # Wider stops, longer hold, larger size
            params.update({
                'profit_target_pct': 0.60,
                'stop_loss_pct': -0.30,
                'time_exit_days': 45,
                'position_size_multiplier': 1.2
            })
        elif regime == 'HIGH_VOL':
            # Tighter stops, quick profits, smaller size
            params.update({
                'profit_target_pct': 0.35, # Take quick profits
                'stop_loss_pct': -0.25, # Tight stop
                'time_exit_days': 20,
                'position_size_multiplier': 0.7,
                'min_score': 75 # Higher quality Only
            })
            
        return params

    def _momentum_confirmation(self, row, prev_rows):
        # Simple check: Close > Prev Close
        # Or 3 of 5 days up
        if prev_rows is None or len(prev_rows) < 5: return True
        
        recent = prev_rows.tail(5)
        wins = (recent['Close'] > recent['Open']).sum()
        
        # Today's close > SMA20
        sma_ok = row['Close'] > row.get('SMA20', 0)
        
        return wins >= 3 and sma_ok
