"""
Backtest Engine
===============
Combines Data Loader, TA Engine, State Machine, and BSM Pricer
to simulate the Diagonal Strategy performance over historical data.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, timedelta
import copy

from diagonal_strategy.core.state_machine import (
    ActiveDiagonalManager, DiagonalPosition, DiagonalState, DiagonalCycle
)
from diagonal_strategy.backtest.bsm_pricer import bs_put, put_strike
from diagonal_strategy.core.risk_manager import DiagonalRiskManager

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, data_df: pd.DataFrame, config, ta_engine, rx_manager, osc_predictor=None):
        self.df = data_df
        self.config = config
        self.ta_engine = ta_engine
        self.rx_manager = rx_manager
        self.osc_predictor = osc_predictor
        self.manager = ActiveDiagonalManager(config, ta_engine, osc_predictor)
        
        # Determine VIX multiplier from historical TQQQ volatility vs VIX
        self.vix_mult = 1.75
        
        self.positions: Dict[str, DiagonalPosition] = {}
        self.trades_history = []
        self.daily_equity = []
        
    def run_scenario(self, override_params=None, start_date=None, end_date=None, regime_filter=None):
        logger.info("Starting Simulation...")
        
        config = self.config
        
        if override_params and regime_filter:
            # temporary deep clone to isolate test cases
            config.TQQQ_DIAGONAL_PARAMS[regime_filter].update(override_params)
            
        current_acct = self.config.ACCOUNT_VALUE
        self.rx_manager.account_value = current_acct
        self.rx_manager._current_value = current_acct
        self.rx_manager._peak_value = current_acct
        self.rx_manager._circuit_broken = False
        self.rx_manager._open_positions = 0
        self.rx_manager._total_at_risk = 0.0
        
        subset_df = self.df
        if start_date:
            subset_df = subset_df.loc[start_date:]
        if end_date:
            subset_df = subset_df.loc[:end_date]
            
        self.positions.clear()
        self.trades_history.clear()
        self.daily_equity.clear()
        
        # To avoid expensive pandas DF slice operations inside loop
        # We will keep a pointer
        
        for date_idx, (dt, row) in enumerate(subset_df.iterrows()):
            if date_idx < 50: 
                continue
                
            current_date = dt.date()
            tqqq_price = row['close']
            vix = row['vix_level']
            iv = (vix * self.vix_mult) / 100.0
            
            # Simple regime logic map
            if vix < 16: regime = 'LOW_VOL'
            elif vix < 24: regime = 'NORMAL'
            elif vix < 32: regime = 'HIGH_VOL'
            else: regime = 'CRISIS'
            
            mkt_data = {
                'current_date': current_date,
                'regime': regime,
                'vix_level': vix,
                'vix_change_1d': float(row.get('vix_level', 0)) - float(subset_df['vix_level'].iloc[date_idx-1]),
                'vix_roc_5': float(row.get('vix_roc_5', 0)) if not pd.isna(row.get('vix_roc_5', 0)) else 0.0,
                'iv_rank': float(row.get('iv_rank', 50)) if not pd.isna(row.get('iv_rank', 50)) else 50.0,
                'iv_percentile': float(row.get('iv_percentile', 50)) if not pd.isna(row.get('iv_percentile', 50)) else 50.0,
                'term_slope': float(row.get('term_slope', 0)) if not pd.isna(row.get('term_slope', 0)) else 0.0,
                'tqqq_bars': subset_df.iloc[date_idx-49:date_idx+1]
            }
            
            to_remove = []
            pending_scale_ins = []  # Defer new position creation to avoid dict-size change during iteration
            for pid, pos in self.positions.items():
                
                self._check_expirations(pos, current_date, tqqq_price)
                if pos.state == DiagonalState.CLOSING:
                    self._close_position(pos, current_date, tqqq_price, iv)
                    to_remove.append(pid)
                    continue

                if pos.state in (DiagonalState.FULL_DIAGONAL, DiagonalState.RE_HEDGED, DiagonalState.ANCHOR_ONLY):
                    if pos.anchor_expiry:
                        anchor_dte = (pos.anchor_expiry - current_date).days
                        mkt_data['anchor_mid_price'] = bs_put(tqqq_price, pos.anchor_strike, max(0.001, anchor_dte/365.0), iv)
                    
                    if pos.current_cycle and pos.current_cycle.hedge_expiry:
                        hedge_dte = (pos.current_cycle.hedge_expiry - current_date).days
                        mkt_data['hedge_mid_price'] = bs_put(tqqq_price, pos.current_cycle.hedge_strike, max(0.001, hedge_dte/365.0), iv)

                action = self.manager.evaluate(pos, mkt_data)

                if action == 'CLOSE_ALL':
                    self._close_position(pos, current_date, tqqq_price, iv)
                    to_remove.append(pid)
                elif action == 'CLOSE_HEDGE':
                    self._close_hedge(pos, current_date, tqqq_price, iv)
                elif action == 'CLOSE_ANCHOR':
                    self._close_anchor(pos, current_date, tqqq_price, iv)
                    pos.state = DiagonalState.CLOSING
                    to_remove.append(pid)
                elif action == 'ROLL_ANCHOR':
                    self._roll_anchor(pos, current_date, tqqq_price, iv, mkt_data, regime)
                elif action == 'BUY_NEW_HEDGE':
                    self._buy_hedge(pos, current_date, tqqq_price, iv, mkt_data, regime)
                elif action == 'EMERGENCY_HEDGE':
                    self._buy_hedge(pos, current_date, tqqq_price, iv, mkt_data, regime, urgent=True)
                elif action == 'SCALE_IN':
                    pos.scale_in_used = True
                    pending_scale_ins.append((tqqq_price, iv, mkt_data.copy(), regime))

            for pid in to_remove:
                del self.positions[pid]

            # Execute deferred scale-in openings (after dict iteration is complete)
            for si_price, si_iv, si_mkt, si_regime in pending_scale_ins:
                tier = self.rx_manager._get_tier()
                if len(self.positions) < tier['max_positions']:
                    params = self.config.TQQQ_DIAGONAL_PARAMS.get(si_regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])
                    a_k = put_strike(si_price, params['anchor_delta'], si_iv, params['anchor_dte'])
                    h_k = put_strike(si_price, params['hedge_delta'], si_iv, params['hedge_dte'])
                    spread_width = max(0, a_k - h_k)
                    contracts = max(1, self.rx_manager.calculate_contracts(spread_width) // 2)
                    max_loss = spread_width * 100 * contracts
                    risk_check = self.rx_manager.can_open_new_diagonal(max_loss, self.rx_manager._current_value)
                    if risk_check:
                        logger.info(f"  SCALE-IN: Opening second position at ${si_price:.2f} ({contracts}x)")
                        self._open_diagonal(current_date, si_price, si_iv, si_mkt, si_regime, max_loss, contracts)

            if regime_filter and regime != regime_filter:
                pass # skip initiating in backtest target regime mode
            else:
                # Ask Risk Manager for tier-based limits
                tier = self.rx_manager._get_tier()
                if len(self.positions) < tier['max_positions'] and regime in ('LOW_VOL', 'NORMAL', 'HIGH_VOL'):
                    dummy_pos = DiagonalPosition(position_id="dummy")
                    action = self.manager.evaluate(dummy_pos, mkt_data)
                    
                    if action == 'OPEN_DIAGONAL':
                        # Calculate real max loss for the new position
                        params = self.config.TQQQ_DIAGONAL_PARAMS.get(regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])
                        # Approx spread width difference
                        a_k = put_strike(tqqq_price, params['anchor_delta'], iv, params['anchor_dte'])
                        h_k = put_strike(tqqq_price, params['hedge_delta'], iv, params['hedge_dte'])
                        spread_width = max(0, a_k - h_k)
                        
                        contracts = self.rx_manager.calculate_contracts(spread_width)
                        max_loss = spread_width * 100 * contracts
                        
                        risk_check = self.rx_manager.can_open_new_diagonal(max_loss, self.rx_manager._current_value)
                        if risk_check:
                            self._open_diagonal(current_date, tqqq_price, iv, mkt_data, regime, max_loss, contracts)
                        
            self.daily_equity.append({'date': current_date, 'equity': self.rx_manager._current_value})
            
        ret = (self.rx_manager._current_value - current_acct) / current_acct
        drawdown = 0 if self.rx_manager._peak_value == 0 else (self.rx_manager._peak_value - self.rx_manager._current_value) / self.rx_manager._peak_value
        logger.info(f"Backtest complete. Return: {ret:.2%}, Max Drawdown recorded: {drawdown:.2%}")
        
        return {
            'total_return': ret,
            'max_drawdown': drawdown, # simplified
            'sharpe': self._calc_sharpe(),
            'trades': len(self.trades_history)
        }
        
    def _calc_sharpe(self):
        if not self.daily_equity: return 0.0
        df = pd.DataFrame(self.daily_equity)
        df['ret'] = df['equity'].pct_change()
        if df['ret'].std() == 0: return 0.0
        # annualize
        return (df['ret'].mean() / df['ret'].std()) * np.sqrt(252)

    def _open_diagonal(self, current_date, spot, iv, mkt_data, regime, max_loss=1000.0, contracts: int = 1):
        params = self.config.TQQQ_DIAGONAL_PARAMS.get(regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])
        a_dte = params['anchor_dte']
        a_del = params['anchor_delta']
        h_dte = params['hedge_dte']
        h_del = params['hedge_delta']
        
        a_k = put_strike(spot, a_del, iv, a_dte)
        h_k = put_strike(spot, h_del, iv, h_dte)
        
        a_price = bs_put(spot, a_k, a_dte/365.0, iv)
        h_price = bs_put(spot, h_k, h_dte/365.0, iv)
        
        net_credit = a_price - h_price - (self.config.COMMISSION_PER_SPREAD / 100.0) 
        
        pid = f"DIAG_{current_date.isoformat()}"
        pos = DiagonalPosition(
            position_id=pid,
            state=DiagonalState.FULL_DIAGONAL,
            contracts=contracts,
            anchor_strike=a_k,
            anchor_expiry=(pd.Timestamp(current_date) + pd.Timedelta(days=a_dte)).date(),
            anchor_entry_date=current_date,
            anchor_entry_credit=a_price,
            anchor_delta_at_entry=a_del,
            anchor_dte_at_entry=a_dte,
            tqqq_price_at_entry=spot,
            vix_at_entry=mkt_data['vix_level'],
            regime_at_entry=regime,
            anchor_profit_target_pct=params['anchor_profit_target_pct'],
            anchor_stop_loss_mult=params['anchor_stop_loss_mult'],
            max_cycles=params['max_cycles'],
            max_naked_hours=params['max_naked_hours'],
            cycle_profit_target_pct=params['hedge_close_decay_pct'],
            vix_spike_close_threshold=params.get('vix_spike_close', 3.0)
        )
        
        cycle = DiagonalCycle(
            cycle_number=1,
            hedge_entry_date=current_date,
            hedge_entry_price=h_price,
            hedge_strike=h_k,
            hedge_expiry=(pd.Timestamp(current_date) + pd.Timedelta(days=h_dte)).date(),
            hedge_dte_at_entry=h_dte,
            ta_score_at_entry=self.ta_engine.dip_score(self.ta_engine.compute_features(mkt_data))
        )
        pos.cycles.append(cycle)
        
        self.positions[pid] = pos
        self.rx_manager.on_position_opened(max_loss)
        self.rx_manager.update_pnl(net_credit * 100 * contracts)
        self.trades_history.append({'date': current_date, 'action': 'OPEN', 'pid': pid, 'net_credit': net_credit, 'contracts': contracts})

    def _close_position(self, pos, current_date, spot, iv):
        a_dte = max(0, (pos.anchor_expiry - current_date).days)
        a_price = bs_put(spot, pos.anchor_strike, a_dte/365.0, iv) if a_dte > 0 else max(0, pos.anchor_strike - spot)
        
        self.rx_manager.update_pnl(-a_price * 100 * pos.contracts)
        self.trades_history.append({'date': current_date, 'action': 'CLOSE_ANCHOR', 'pid': pos.position_id, 'cost': a_price, 'contracts': pos.contracts})
        
        if pos.state in (DiagonalState.FULL_DIAGONAL, DiagonalState.RE_HEDGED):
            self._close_hedge(pos, current_date, spot, iv)
            
        # Calculate max loss approx for risk manager release
        spread_width = max(0, pos.anchor_strike - (pos.current_cycle.hedge_strike if pos.current_cycle else pos.anchor_strike))
        self.rx_manager.on_position_closed(spread_width * 100 * pos.contracts)
        
        pos.state = DiagonalState.CLOSING

    def _close_hedge(self, pos, current_date, spot, iv):
        cycle = pos.current_cycle
        h_dte = max(0, (cycle.hedge_expiry - current_date).days)
        h_price = bs_put(spot, cycle.hedge_strike, h_dte/365.0, iv) if h_dte > 0 else max(0, cycle.hedge_strike - spot)
        
        cycle.hedge_close_date = current_date
        cycle.hedge_close_price = h_price
        
        # PnL logic for closing a LONG put (we bought it for debit, we sell it for credit)
        # However, h_price is just the *current* market value. 
        # The change in our account value from yesterday to today needs to be captured.
        # But wait, BacktestEngine is tracking cash flow, not mark-to-market.
        # We paid `hedge_entry_price` initially (recorded as negative cash flow).
        # Now we receive `h_price`. So we add `h_price * 100` back to cash.
        
        self.rx_manager.update_pnl(h_price * 100 * pos.contracts)
        self.trades_history.append({'date': current_date, 'action': 'CLOSE_HEDGE', 'pid': pos.position_id, 'credit': h_price, 'contracts': pos.contracts})
        
        pos.state = DiagonalState.ANCHOR_ONLY
        pos.naked_since = datetime.combine(current_date, datetime.min.time())

    def _buy_hedge(self, pos, current_date, spot, iv, mkt_data, regime, urgent=False):
        params = self.config.TQQQ_DIAGONAL_PARAMS.get(regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])
        h_dte = params['hedge_dte']
        h_del = params['hedge_delta']
        
        h_k = put_strike(spot, h_del, iv, h_dte)
        h_price = bs_put(spot, h_k, h_dte/365.0, iv)
        
        cycle = DiagonalCycle(
            cycle_number=pos.cycles_completed + 1,
            hedge_entry_date=current_date,
            hedge_entry_price=h_price,
            hedge_strike=h_k,
            hedge_expiry=(pd.Timestamp(current_date) + pd.Timedelta(days=h_dte)).date(),
            hedge_dte_at_entry=h_dte,
        )
        pos.cycles.append(cycle)
        pos.state = DiagonalState.RE_HEDGED
        pos.naked_since = None
        
        self.rx_manager.update_pnl(-h_price * 100 * pos.contracts)
        self.trades_history.append({'date': current_date, 'action': 'REHEDGE', 'pid': pos.position_id, 'cost': h_price, 'urgent': urgent, 'contracts': pos.contracts})

    def _close_anchor(self, pos, current_date, spot, iv):
        a_dte = max(0, (pos.anchor_expiry - current_date).days)
        a_price = bs_put(spot, pos.anchor_strike, a_dte/365.0, iv) if a_dte > 0 else max(0, pos.anchor_strike - spot)
        
        self.rx_manager.update_pnl(-a_price * 100 * pos.contracts)
        self.trades_history.append({'date': current_date, 'action': 'CLOSE_ANCHOR_ONLY', 'pid': pos.position_id, 'cost': a_price, 'contracts': pos.contracts})

    def _roll_anchor(self, pos, current_date, spot, iv, mkt_data, regime):
        # 1. Buy back current anchor
        a_dte = max(0, (pos.anchor_expiry - current_date).days)
        a_price_to_close = bs_put(spot, pos.anchor_strike, a_dte/365.0, iv) if a_dte > 0 else max(0, pos.anchor_strike - spot)
        
        # 2. Sell new anchor (roll out and up/down depending on spot)
        params = self.config.TQQQ_DIAGONAL_PARAMS.get(regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])
        new_dte = params['anchor_dte']
        new_del = params['anchor_delta']
        
        new_k = put_strike(spot, new_del, iv, new_dte)
        new_price_to_open = bs_put(spot, new_k, new_dte/365.0, iv)
        
        # Net credit = credit received - cost to close
        net_credit = new_price_to_open - a_price_to_close
        
        # Update position
        pos.anchor_strike = new_k
        pos.anchor_expiry = (pd.Timestamp(current_date) + pd.Timedelta(days=new_dte)).date()
        pos.anchor_entry_date = current_date
        pos.anchor_entry_credit = new_price_to_open
        pos.anchor_delta_at_entry = new_del
        pos.anchor_dte_at_entry = new_dte
        
        self.rx_manager.update_pnl(net_credit * 100 * pos.contracts)
        self.trades_history.append({'date': current_date, 'action': 'ROLL_ANCHOR', 'pid': pos.position_id, 'net_credit': net_credit, 'contracts': pos.contracts})

    def _check_expirations(self, pos, current_date, spot):
        if pos.anchor_expiry and current_date >= pos.anchor_expiry:
            pos.state = DiagonalState.CLOSING
            return
            
        if pos.current_cycle and pos.current_cycle.hedge_expiry and current_date >= pos.current_cycle.hedge_expiry:
            if pos.state in (DiagonalState.FULL_DIAGONAL, DiagonalState.RE_HEDGED):
                # Will be closed within same loop at DTE 0/1, so this is just a fail-safe
                pass
