import pytest
import pandas as pd
import numpy as np
from src.tqqq.crash_guard import CrashGuard, CrashGuardResult
from src.tqqq.swing_exit_engine import SwingExitEngine, ExitDecisionType

class MockPosition:
    def __init__(self, entry_price, anchor_dte, hedge_dte, roll_count=0):
        self.entry_price = entry_price
        self.anchor_dte = anchor_dte
        self.hedge_dte = hedge_dte
        self.roll_count = roll_count

def test_crash_guard_hard_gate_sma():
    guard = CrashGuard()
    
    # 30% below 200 SMA -> Should fail hard gate
    daily_df = pd.DataFrame([{"tqqq_close": 70.0, "sma_200": 100.0, "rsi_2": 50, "vix_sma_ratio": 1.0, "hurst_100": 0.5}] * 200)
    intraday_row = pd.Series({"close": 70.0, "rsi_2": 50, "vol_ratio": 1.0})
    
    result = guard.evaluate_entry(daily_df, intraday_row, ml_prob=0.50)
    assert not result.passed
    assert "gate_200ma" in result.reasons
    assert "FAIL" in result.reasons["gate_200ma"]

def test_crash_guard_scoring_pass():
    guard = CrashGuard()
    
    # Perfect conditions: well above SMA, oversold RSI-2, low VIX, high ML prob
    daily_df = pd.DataFrame([{"tqqq_close": 110.0, "sma_200": 100.0, "rsi_2": 5, "vix_sma_ratio": 0.9, "hurst_100": 0.2}] * 200)
    intraday_row = pd.Series({"close": 110.0, "rsi_2": 4.0, "vol_ratio": 2.5})
    
    result = guard.evaluate_entry(daily_df, intraday_row, ml_prob=0.80)
    assert result.passed
    assert result.score >= 85
    assert result.multiplier == 2.0

def test_swing_exit_emergency_drop():
    engine = SwingExitEngine()
    pos = MockPosition(entry_price=100.0, anchor_dte=30, hedge_dte=14)
    
    # Dropped 11%
    decision = engine.evaluate(pos, current_price=89.0, rsi_2=30.0, sma_5=95.0, regime_score=60, ml_prob=0.5, days_held=2)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "EMERGENCY" in decision.reason

def test_swing_exit_bounce_profit():
    engine = SwingExitEngine()
    pos = MockPosition(entry_price=100.0, anchor_dte=30, hedge_dte=14)
    
    # Bounced 6%
    decision = engine.evaluate(pos, current_price=106.0, rsi_2=30.0, sma_5=105.0, regime_score=60, ml_prob=0.5, days_held=2)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "PROFIT_TARGET" in decision.reason

def test_swing_exit_time_stop():
    engine = SwingExitEngine()
    pos = MockPosition(entry_price=100.0, anchor_dte=30, hedge_dte=14)
    
    # Held 8 days (exceeds default max of 7)
    # Using default OU half-life fallback logic (returns 3 to 15 days, usually limits at 7 in scheduler config, handled by caller)
    # Wait, the engine defaults time_limit between 3 and 15 strictly via ou_half_life. If ou_half_life is inf, max is 15.
    decision = engine.evaluate(pos, current_price=100.0, rsi_2=30.0, sma_5=100.0, regime_score=60, ml_prob=0.5, days_held=16)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "TIME_STOP" in decision.reason

def test_swing_exit_theta_kicker_roll():
    engine = SwingExitEngine()
    pos = MockPosition(entry_price=100.0, anchor_dte=30, hedge_dte=1, roll_count=0)
    
    # Hedge expiring tomorrow, good regime => ROLL HEDGE
    decision = engine.evaluate(pos, current_price=100.0, rsi_2=30.0, sma_5=100.0, regime_score=60, ml_prob=0.6, days_held=5)
    assert decision.decision == ExitDecisionType.ROLL_HEDGE
    assert "THETA_KICKER" in decision.reason

def test_swing_exit_theta_kicker_close():
    engine = SwingExitEngine()
    pos = MockPosition(entry_price=100.0, anchor_dte=30, hedge_dte=1, roll_count=0)
    
    # Hedge expiring tomorrow, BAD regime (<50 score) => CLOSE ALL
    decision = engine.evaluate(pos, current_price=100.0, rsi_2=30.0, sma_5=100.0, regime_score=30, ml_prob=0.6, days_held=5)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "HEDGE_EXPIRING" in decision.reason
