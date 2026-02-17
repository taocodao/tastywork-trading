from datetime import datetime
import pandas as pd
import numpy as np
import logging

class TrailingStopExit:
    """
    Trailing stop that activates after a minimum profit threshold.
    Tracks high-watermark P&L and exits if profit retraces by trailing_pct.
    """
    def __init__(self, activation_pct=0.15, trailing_pct=0.12):
        self.activation_pct = activation_pct
        self.trailing_pct = trailing_pct

    def evaluate(self, entry_price, current_price, high_watermark_price, entry_debit, leverage_delta=0.90, 
                 activation_pct=None, trailing_pct=None):
        
        act_pct = activation_pct if activation_pct is not None else self.activation_pct
        trail_pct = trailing_pct if trailing_pct is not None else self.trailing_pct
        
        # Calculate P&L based on ZEBRA mechanics (delta approx)
        move_from_entry = current_price - entry_price
        pnl_dollar = move_from_entry * leverage_delta * 100
        pnl_pct = pnl_dollar / (entry_debit * 100)
        
        # Calculate High Watermark P&L
        hw_move = high_watermark_price - entry_price
        hw_pnl_pct = (hw_move * leverage_delta * 100) / (entry_debit * 100)

        # Check activation
        if hw_pnl_pct >= act_pct:
            # Trailing stop logic:
            # If current P&L drops by trailing_pct from High Watermark P&L
            # Note: This is simplified. Better: Price-based trail.
            # Trail price = High Watermark Price * (1 - trailing_pct_of_stock?) 
            # OR Trail P&L = Max P&L - trailing_pct_of_debit?
            
            # Implementation: Trailing % of PROFIT. 
            # Actually, standard trailing stop trails PRICE.
            # Let's trail PRICE to be robust.
            
            # Stop Price = High Watermark Price - (High Watermark Price * trailing_pct_stock?)
            # But ZEBRA is leverage.
            # Let's use P&L based trail:
            # If P&L drops by X% of DEBIT from max P&L?
            # E.g. Max P&L +50%, current +30%. Drop = 20%. 
            
            # Let's use the plan's logic:
            # "If price drops trailing_pct (e.g. 12%) from high watermark"
            pass

        # Robust implementation: Trail Price
        # Calculate theoretical stop price based on high watermark
        # If we are long delta 90, we behave like stock.
        # Stop Price = High Watermark * (1 - trailing_pct)
        if hw_pnl_pct >= act_pct:
            stop_price = high_watermark_price * (1.0 - trail_pct)
            if current_price <= stop_price:
                return {
                    'exit': True,
                    'reason': 'TRAILING_STOP',
                    'details': f"Price {current_price:.2f} crossed trail {stop_price:.2f} (HW: {high_watermark_price:.2f})"
                }
        
        return {'exit': False}

class ATRAdaptiveStop:
    """
    Stop loss that adjusts to volatility.
    Stop Price = Entry Price - (ATR * multiplier)
    """
    def __init__(self, atr_multiplier=2.5):
        self.atr_multiplier = atr_multiplier

    def calculate_stop_price(self, entry_price, atr_val):
        return entry_price - (atr_val * self.atr_multiplier)

class MomentumExit:
    """
    Exits when trend breaks down (SMA crossover, RSI drop).
    """
    def evaluate(self, row, prev_row):
        # row is current day, prev_row is yesterday
        # Conditions:
        # 1. Price < SMA20
        # 2. RSI < 40
        # 3. MACD < Signal (bearish cross)
        
        score = 0
        details = []
        
        if row['Close'] < row.get('SMA20', 0):
            score += 1
            details.append("Price<SMA20")
            
        if row.get('RSI', 50) < 40:
            score += 1
            details.append("RSI<40")
            
        # If 2+ conditions met
        if score >= 2:
            return {
                'exit': True,
                'reason': 'MOMENTUM_EXIT',
                'details': ", ".join(details)
            }
        
        return {'exit': False}

class DTEExit:
    """
    Exits as the position approaches expiration to avoid high Gamma and low liquidity.
    """
    def __init__(self, min_dte_threshold=21):
        self.threshold = min_dte_threshold

    def evaluate(self, days_to_expiry):
        if days_to_expiry <= self.threshold:
            return {
                'exit': True,
                'reason': 'DTE_EXIT',
                'details': f"DTE {days_to_expiry} below threshold {self.threshold}"
            }
        return {'exit': False}

class StagnationExit:
    """
    Exits positions that are 'dead money' - flat or negative after a threshold time.
    """
    def __init__(self, check_days=15, min_profit_pct=0.03):
        self.check_days = check_days
        self.min_profit = min_profit_pct

    def evaluate(self, days_held, pnl_pct):
        if days_held >= self.check_days and pnl_pct < self.min_profit:
            return {
                'exit': True,
                'reason': 'STAGNATION_EXIT',
                'details': f"Profit {pnl_pct:.1%} below {self.min_profit:.1%} after {days_held} days"
            }
        return {'exit': False}

class ZebraExitEngine:
    """
    Master exit engine combining all strategies.
    Priority: Hard Stop > Trailing > Momentum > Profit > Time
    """
    def __init__(self, params=None):
        if params is None: params = {}
        
        # Parameters
        self.profit_target_pct = params.get('profit_target_pct', 0.50)
        self.stop_loss_pct = params.get('stop_loss_pct', -0.40) # Hard stop
        self.time_exit_days = params.get('time_exit_days', 30)
        
        # Components
        self.trailing = TrailingStopExit(
            activation_pct=params.get('trailing_activation_pct', 0.15),
            trailing_pct=params.get('trailing_pct', 0.12)
        )
        self.atr_stop = ATRAdaptiveStop(
            atr_multiplier=params.get('atr_multiplier', 2.5)
        )
        self.momentum = MomentumExit()
        self.dte_exit = DTEExit(
            min_dte_threshold=params.get('min_dte_threshold', 21)
        )
        self.stagnation = StagnationExit(
            check_days=params.get('stagnation_days', 15),
            min_profit_pct=params.get('stagnation_min_profit', 0.03)
        )
        
    def evaluate(self, position, override_params=None):
        """
        Evaluate position for exit signals.
        position: dict containing entry_price, current_price, days_held, etc.
        override_params: dict of dynamic overrides (e.g. from RegimeDetector)
        """
        current_price = position['current_price']
        entry_price = position['entry_price']
        entry_debit = position['entry_debit']
        days_held = position['days_held']
        high_watermark = position.get('high_watermark', current_price)
        
        # Apply Overrides
        stop_val = self.stop_loss_pct
        time_exit_val = self.time_exit_days
        trail_act = None
        trail_val = None
        
        if override_params:
            stop_val = override_params.get('hard_stop_pct', stop_val)
            time_exit_val = override_params.get('time_exit_days', time_exit_val)
            # In RegimeDetector 'trailing_stop_pct' is strictly the trailing amount
            trail_val = override_params.get('trailing_stop_pct') 

        
        # 1. Calculate P&L (Approx)
        leverage = 0.90
        pnl_dollar = (current_price - entry_price) * leverage * 100
        pnl_pct = pnl_dollar / (entry_debit * 100)
        
        # 2. Hard Stop (Fixed or ATR?)
        # Use Fixed % as absolute disaster stop
        if pnl_pct <= stop_val:
            return {'exit': True, 'reason': 'STOP_LOSS', 'pnl_pct': pnl_pct}
            
        # 3. ATR Stop (if available data)
        if 'atr_at_entry' in position:
            atr_stop_price = self.atr_stop.calculate_stop_price(entry_price, position['atr_at_entry'])
            if current_price <= atr_stop_price:
                return {'exit': True, 'reason': 'ATR_STOP', 'pnl_pct': pnl_pct}
        
        # 4. Trailing Stop
        trail_res = self.trailing.evaluate(
            entry_price, current_price, high_watermark, entry_debit, 
            activation_pct=trail_act, trailing_pct=trail_val
        )
        if trail_res['exit']:
            return {'exit': True, 'reason': 'TRAILING_STOP', 'pnl_pct': pnl_pct, 'details': trail_res['details']}
            
        # 5. Momentum Exit (if history available)
        if 'current_row' in position and 'prev_row' in position:
            mom_res = self.momentum.evaluate(position['current_row'], position['prev_row'])
            if mom_res['exit']:
                return {'exit': True, 'reason': 'MOMENTUM_EXIT', 'pnl_pct': pnl_pct, 'details': mom_res['details']}
                
        # 6. Profit Target
        if pnl_pct >= self.profit_target_pct:
            return {'exit': True, 'reason': 'TAKE_PROFIT', 'pnl_pct': pnl_pct}
            
        # 7. DTE Exit (Avoid expiry Gamma)
        if 'days_to_expiry' in position:
            dte_res = self.dte_exit.evaluate(position['days_to_expiry'])
            if dte_res['exit']:
                return {'exit': True, 'reason': 'DTE_EXIT', 'pnl_pct': pnl_pct, 'details': dte_res['details']}

        # 8. Stagnation Exit (Avoid dead money)
        stag_res = self.stagnation.evaluate(days_held, pnl_pct)
        if stag_res['exit']:
            return {'exit': True, 'reason': 'STAGNATION_EXIT', 'pnl_pct': pnl_pct, 'details': stag_res['details']}

        # 9. Time Exit (Absolute max duration)
        if days_held >= time_exit_val:
            return {'exit': True, 'reason': 'TIME_EXIT', 'pnl_pct': pnl_pct}
            
        return {'exit': False}
