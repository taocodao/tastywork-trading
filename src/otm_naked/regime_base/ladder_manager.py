"""
RegimeBase Dynamic Ladder Strategy - Ladder Manager
===========================================
Tracks multi-rung positions, rolls, and naked-to-spread conversions.
"""
import logging
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.otm_naked.stop_manager import StopState, SpreadAwareStopManager
from src.otm_naked.regime_base.config import RegimeBaseLadderConfig
from src.otm_naked.strike_selector import bs_all_greeks, bs_call_price, bs_put_price, bs_call_delta, bs_put_delta

logger = logging.getLogger(__name__)

def get_bs_price(S, K, T, r, sigma, opt="call"):
    return bs_call_price(S, K, T, r, sigma) if opt == "call" else bs_put_price(S, K, T, r, sigma)

def get_bs_delta(S, K, T, r, sigma, opt="call"):
    return bs_call_delta(S, K, T, r, sigma) if opt == "call" else bs_put_delta(S, K, T, r, sigma)

def _calc_friction(entry_premium, entry_delta, is_spread, fill_efficiency=0.75):
    """Delta-aware friction model based on bid-ask spread research."""
    if entry_delta >= 0.25:
        spread_pct = 0.08
    elif entry_delta >= 0.20:
        spread_pct = 0.12
    elif entry_delta >= 0.15:
        spread_pct = 0.18
    else:
        spread_pct = 0.28
    
    half_spread = entry_premium * spread_pct / 2
    slippage_per_share = half_spread * (1 - fill_efficiency) * 2
    commission = 2.00
    per_contract = slippage_per_share * 100 + commission
    if is_spread:
        per_contract *= 2
    return per_contract


@dataclass
class LadderRung:
    opt_type: str
    strike: float
    entry_premium: float
    entry_delta: float
    entry_iv: float
    entry_date: pd.Timestamp
    rung_num: int
    contracts: int
    target_dte: int = 60
    stop_state: Optional[StopState] = None
    # For spread conversion
    is_spread: bool = False
    wing_strike: float = 0.0
    wing_cost: float = 0.0

class LadderManager:
    def __init__(self, config: Optional[RegimeBaseLadderConfig] = None):
        self.config = config or RegimeBaseLadderConfig()
        self.call_rungs: List[LadderRung] = []
        self.put_rungs: List[LadderRung] = []
        self.stop_manager = SpreadAwareStopManager(
            base_stop_mult=self.config.stop_loss_credit_mult
        )
        
    def get_portfolio_delta(self, spot: float, T_remaining: float, iv_current: float) -> float:
        """Calculate total position delta."""
        total_delta = 0.0
        for rung in self.call_rungs + self.put_rungs:
            d = get_bs_delta(spot, rung.strike, T_remaining, 0.045, iv_current, opt=rung.opt_type)
            if rung.opt_type == "call":
                # Short call -> negative delta
                total_delta -= abs(d) * rung.contracts
            else:
                # Short put -> positive delta
                total_delta += abs(d) * rung.contracts
                
            if rung.is_spread:
                wing_d = get_bs_delta(spot, rung.wing_strike, T_remaining, 0.045, iv_current, opt=rung.opt_type)
                if rung.opt_type == "call":
                    total_delta += abs(wing_d) * rung.contracts
                else:
                    total_delta -= abs(wing_d) * rung.contracts
                    
        return total_delta
        
    def add_rung(self, rung: LadderRung):
        if rung.opt_type == "call":
            self.call_rungs.append(rung)
        else:
            self.put_rungs.append(rung)
            
    def convert_to_spread_if_needed(self, rung: LadderRung, ml_confidence: float, spot: float, T: float, iv: float) -> LadderRung:
        """
        Converts marginal confidence signals to credit spreads.
        """
        if ml_confidence >= self.config.spread_conversion_conf_high:
            return rung # Keep naked
            
        if ml_confidence >= self.config.spread_conversion_conf_low:
            # Convert to spread
            if rung.opt_type == "call":
                wing_strike = rung.strike * (1.0 + self.config.spread_wing_pct)
            else:
                wing_strike = rung.strike * (1.0 - self.config.spread_wing_pct)
                
            wing_premium = get_bs_price(spot, wing_strike, T, 0.045, iv, opt=rung.opt_type)
            
            rung.is_spread = True
            rung.wing_strike = wing_strike
            rung.wing_cost = wing_premium
            rung.entry_premium -= wing_premium # Net credit
            
            logger.info(f"Converted {rung.opt_type} rung to spread. Wing K={wing_strike:.2f}, Cost=${wing_premium:.2f}")
            
        return rung

    def manage_positions(self, today: pd.Timestamp, spot: float, iv_current: float) -> Tuple[List[dict], float]:
        """
        Check for profits, stops, delta breaches, and DTE expirations.
        Returns closed/rolled positions info and realized net PnL (including friction).
        """
        actions = []
        realized_pnl = 0.0
        
        # Friction is calculated per trade based on entry delta

        
        for rung_list in [self.call_rungs, self.put_rungs]:
            to_remove = []
            for rung in rung_list:
                days_held = (today - rung.entry_date).days
                T_rem = max((rung.target_dte - days_held) / 365.0, 0.001)
                
                # Mark to market
                current_prem = get_bs_price(spot, rung.strike, T_rem, 0.045, iv_current, opt=rung.opt_type)
                if rung.is_spread:
                    current_wing = get_bs_price(spot, rung.wing_strike, T_rem, 0.045, iv_current, opt=rung.opt_type)
                    current_prem = current_prem - current_wing
                    
                pnl = (rung.entry_premium - current_prem) * rung.contracts * 100
                pnl_pct = (rung.entry_premium - current_prem) / max(rung.entry_premium, 0.001)
                
                current_delta = abs(get_bs_delta(spot, rung.strike, T_rem, 0.045, iv_current, opt=rung.opt_type))
                
                # Friction applies on exit
                friction_cost = _calc_friction(rung.entry_premium, rung.entry_delta, rung.is_spread) * rung.contracts
                    
                net_pnl = pnl - friction_cost
                
                # DTE-aware profit target: use 50% for long-dated, 25% for short-dated
                effective_profit_target = self.config.profit_take_pct  # default 50%
                if rung.target_dte <= getattr(self.config, 'profit_dte_threshold', 25):
                    effective_profit_target = getattr(self.config, 'profit_take_pct_short', 0.25)
                
                # Profit target
                if pnl_pct >= effective_profit_target:
                    actions.append({"action": "CLOSE", "reason": "profit_target", "pnl": net_pnl, "rung": rung})
                    realized_pnl += net_pnl
                    to_remove.append(rung)
                    continue
                    
                # Stop Loss
                if pnl_pct <= -self.config.stop_loss_credit_mult:
                    actions.append({"action": "CLOSE", "reason": "stop_loss", "pnl": net_pnl, "rung": rung})
                    realized_pnl += net_pnl
                    to_remove.append(rung)
                    continue
                    
                # Roll on delta breach
                if current_delta > self.config.delta_breach_threshold:
                    actions.append({"action": "ROLL", "reason": "delta_breach", "pnl": net_pnl, "rung": rung})
                    realized_pnl += net_pnl
                    to_remove.append(rung)
                    continue
                    
                # DTE roll/close
                if T_rem * 365 <= self.config.dte_roll_threshold:
                    actions.append({"action": "CLOSE", "reason": "dte_threshold", "pnl": net_pnl, "rung": rung})
                    realized_pnl += net_pnl
                    to_remove.append(rung)
                    
            for r in to_remove:
                rung_list.remove(r)
                
        return actions, realized_pnl
