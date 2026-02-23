import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.diagonal_spreads.stop_manager import DiagonalStopManager, ExitRule, DiagonalExitAnalysis, RollOpportunity
from src.diagonal_spreads.diagonal_rl_optimizer import DiagonalAction
from src.pmcc.pmcc_short_call_selector import PMCCShortCallSelector
from src.pmcc.ml.pmcc_rl_agent import PMCCSnapshot
from ib_data_provider import IBDataProvider

logger = logging.getLogger(__name__)

class PMCCStopManager(DiagonalStopManager):
    """
    Manages stops and rolls specifically for the PMCC strategy.
    
    PMCC Additions:
    - Assignment risk monitoring (Short delta > 0.50, low extrinsic)
    - LEAPS minimum DTE is 90 days (instead of 30)
    - Roll opportunities use real market data and enforce Net Credit
    """
    
    def __init__(self, data_provider: Optional[IBDataProvider] = None, rl_agent = None):
        super().__init__(
            profit_target_pct=0.50,
            max_loss_pct=0.75,
            min_long_dte=90,  # PMCC LEAPS must be rolled or closed at 90 DTE
            roll_short_dte=7,
            roll_early_capture_pct=0.50
        )
        self.ib = data_provider or IBDataProvider()
        self.short_selector = PMCCShortCallSelector(self.ib)
        self.rl_agent = rl_agent
        
    def check_exit_rules(
        self,
        position_data: Dict,
        market_data: Dict
    ) -> DiagonalExitAnalysis:
        """
        Extends basic diagonal rules with PMCC-specific checks (assignment risk) and RL routing.
        """
        # Run base rules first to build the analysis object
        analysis = super().check_exit_rules(position_data, market_data)
        
        # Extract fields
        short_exp = position_data.get("short_expiration")
        if isinstance(short_exp, str):
            short_exp = datetime.fromisoformat(short_exp).date()
            
        short_dte = (short_exp - date.today()).days if short_exp else 0
        short_delta = abs(market_data.get("short_delta", 0.0))
        short_price = market_data.get("short_current_price", 0.0)
        short_strike = position_data.get("short_strike", 0.0)
        stock_price = market_data.get("stock_price", 0.0)
        
        # Calculate extrinsic value of short call
        intrinsic = max(0, stock_price - short_strike)
        extrinsic = max(0, short_price - intrinsic)
        
        # PMCC Rule 1: Assignment Risk
        assignment_risk = False
        urgency = "low"
        
        # Early assignment risk is highest when extrinsic value is very low
        if short_delta >= 0.80 or extrinsic < 0.10:
            assignment_risk = True
            urgency = "critical"
        elif short_delta >= 0.50 and short_dte < 7:
            assignment_risk = True
            urgency = "high"
            
        assign_rule = ExitRule(
            name="ASSIGNMENT_RISK",
            triggered=assignment_risk,
            reason=f"High assignment risk (Delta: {short_delta:.2f}, Extrinsic: ${extrinsic:.2f})",
            urgency=urgency,
            recommended_action="ROLL_SHORT_LEG" if assignment_risk else "HOLD"
        )
        
        # Add to analysis
        analysis.all_rules.append(assign_rule)
        if assignment_risk:
            analysis.triggered_rules.append(assign_rule)
            
            # Update recommendations
            if urgency == "critical":
                analysis.should_roll_short = True
                analysis.short_leg_status = "ROLL_NOW"
                analysis.exit_reason = assign_rule.reason
                
                if assign_rule.urgency == "critical" and not analysis.should_exit_completely:
                    analysis.should_roll_short = True
                    
        # ML RL Agent Override Logic
        if self.rl_agent:
            try:
                # Calculate fields for the PMCCSnapshot
                long_exp = position_data.get("long_expiration")
                if isinstance(long_exp, str):
                    long_exp = datetime.fromisoformat(long_exp).date()
                long_dte = (long_exp - date.today()).days if long_exp else 180
                
                days_held = position_data.get("days_held", 1)
                cycle_count = position_data.get("cycle_count", 1)
                current_pnl_pct = position_data.get("total_pnl_pct", 0.0)
                
                long_strike = position_data.get("long_strike", 100.0)
                leaps_be = long_strike + position_data.get("net_debit", 0.0)
                
                # BCI Headroom: Distance between Short Strike and LEAPS cost basis
                bci_headroom = (short_strike - leaps_be) / stock_price if stock_price > 0 else 0.0
                width_pct = (short_strike - long_strike) / long_strike if long_strike > 0 else 0.0
                
                snap = PMCCSnapshot(
                    short_dte=short_dte,
                    long_dte=long_dte,
                    days_held=days_held,
                    current_pnl_pct=current_pnl_pct,
                    short_leg_pnl_pct=0.0, # Approximate or fetch from position if tracked
                    long_leg_pnl_pct=0.0,
                    iv_rank=market_data.get("iv_rank", 50.0),
                    iv_change_pct=0.0,
                    term_structure_diff=market_data.get("term_structure", 0.0),
                    iv_skew=0.0,
                    position_delta=market_data.get("position_delta", 0.0),
                    theta_per_day=0.0,
                    vega_exposure=0.0,
                    breach_days=0,
                    vix_level=market_data.get("vix", 15.0),
                    underlying_move_pct=0.0,
                    symbol_id=0,
                    short_theta_decay_pct=0.5,
                    roll_credit_estimate=0.0,
                    days_since_last_roll=days_held,
                    leaps_current_delta=0.80, # Approximate baseline
                    cumulative_premium_collected_pct=position_data.get("cumulative_premium", 0.0),
                    cycle_count=cycle_count,
                    assignment_risk_score=1.0 if assignment_risk else 0.0,
                    bci_headroom=bci_headroom,
                    width_pct=width_pct,
                    extrinsic_ratio=extrinsic / (stock_price if stock_price > 0 else 1.0)
                )
                
                rl_action, rl_conf, rl_reason = self.rl_agent.should_roll_or_exit(snap)
                
                # Confidence gating at 0.70
                if rl_conf >= 0.70:
                    if rl_action == DiagonalAction.EXIT:
                        analysis.should_exit_completely = True
                        analysis.exit_reason = f"[RL Agent] High-Conviction EXIT ({rl_conf:.2f}): {rl_reason}"
                        logger.info(f"{position_data.get('symbol')}: PPO Model overriding logic to EXIT.")
                    elif rl_action == DiagonalAction.ROLL:
                        analysis.should_roll_short = True
                        analysis.short_leg_status = "ROLL_NOW"
                        analysis.exit_reason = f"[RL Agent] High-Conviction ROLL ({rl_conf:.2f}): {rl_reason}"
                        logger.info(f"{position_data.get('symbol')}: PPO Model overriding logic to ROLL.")
                    # If action is HOLD, we could theoretically clear flags, but it's safer to let 
                    # hard risk rules (like assignment risk) exit us even if RL says hold.
            except Exception as e:
                logger.error(f"Failed to query RL Agent for PMCC stop decision: {e}")
                
        return analysis

    def _generate_roll_opportunity(
        self,
        position_data: Dict,
        market_data: Dict,
        current_short_dte: int
    ) -> Optional[RollOpportunity]:
        """
        Overrides base method to generate a REAL roll opportunity.
        Uses PMCCShortCallSelector to find the best next short call.
        Enforces a net credit.
        """
        symbol = position_data.get("symbol", "")
        stock_price = market_data.get("stock_price", 0.0)
        hist_df = market_data.get("hist_df")
        
        current_short_price = market_data.get("short_current_price", 0.0)
        
        # Need historical data for S/R checks when picking new strike
        if hist_df is None or len(hist_df) == 0:
            logger.warning(f"{symbol}: Cannot generate PMCC roll opportunity without hist_df")
            return None
            
        leaps_break_even = position_data.get("long_strike", 0.0) + position_data.get("net_debit", 0.0)
        
        # Find the best short call for the NEXT cycle (30-45 DTE)
        best_call = self.short_selector.select_short_call(
            symbol=symbol,
            stock_price=stock_price,
            hist_df=hist_df,
            target_delta=0.25,
            min_dte=20,
            max_dte=45,
            leaps_break_even=leaps_break_even
        )
        
        if not best_call:
            logger.info(f"{symbol}: Could not calculate roll (no valid short call found)")
            return None
            
        new_strike = best_call['strike']
        new_price = best_call['bid'] if best_call['bid'] > 0 else best_call['ask']
        new_exp = best_call['expiration']
        if isinstance(new_exp, str):
            new_exp = datetime.fromisoformat(new_exp).date()
            
        # For a roll, Credit = Premium Received (New) - Premium Paid to Buy Back (Old)
        net_credit = new_price - current_short_price
        
        # PMCC Core Rule: ONLY Roll for a credit
        if net_credit <= 0:
            return RollOpportunity(
                should_roll=False,
                reason=f"Roll to {new_strike} at {new_exp} results in debit (${net_credit:.2f})",
                suggested_new_strike=new_strike,
                suggested_new_expiration=new_exp,
                estimated_credit=net_credit
            )
            
        return RollOpportunity(
            should_roll=True,
            reason=f"Roll short call up/out for ${net_credit:.2f} credit",
            suggested_new_strike=new_strike,
            suggested_new_expiration=new_exp,
            estimated_credit=net_credit
        )
