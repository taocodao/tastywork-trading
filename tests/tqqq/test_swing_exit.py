import pytest
from src.tqqq.swing_exit_engine import SwingExitEngine, ExitDecision, ExitDecisionType

class DummyPosition:
    def __init__(self, entry_price, anchor_dte, hedge_dte, roll_count):
        self.entry_price = entry_price
        self.anchor_dte = anchor_dte
        self.hedge_dte = hedge_dte
        self.roll_count = roll_count

def test_emergency_exit():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 10, 0)
    
    decision = engine.evaluate(pos, 85.0, 40.0, 90.0, 75, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "EMERGENCY" in decision.reason

def test_regime_exit():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 10, 0)
    
    # Needs < 30 now
    decision = engine.evaluate(pos, 95.0, 40.0, 96.0, 20, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "REGIME" in decision.reason

def test_profit_target_exit():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 10, 0)
    
    decision = engine.evaluate(pos, 106.0, 40.0, 104.0, 75, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "PROFIT_TARGET" in decision.reason

def test_bounce_exit_rsi():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 10, 0)
    
    # RSI > 65
    decision = engine.evaluate(pos, 102.0, 68.0, 103.0, 75, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "BOUNCE" in decision.reason

def test_theta_kicker_roll():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 1, 0)
    
    decision = engine.evaluate(pos, 98.0, 40.0, 99.0, 75, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.ROLL_HEDGE
    assert "THETA_KICKER" in decision.reason

def test_theta_kicker_fail_roll_limit():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 1, 2)
    
    decision = engine.evaluate(pos, 98.0, 40.0, 99.0, 75, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "HEDGE_EXPIRING" in decision.reason

def test_adaptive_time_stop():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 10, 0)
    
    # ou_halflife = 4, so time_limit = max(4*2, 3) = 8
    decision = engine.evaluate(pos, 98.0, 40.0, 99.0, 75, 0.60, 9, ou_half_life=4.0)
    assert decision.decision == ExitDecisionType.CLOSE_ALL
    assert "TIME_STOP" in decision.reason

def test_hold():
    engine = SwingExitEngine()
    pos = DummyPosition(100.0, 30, 10, 0)
    
    decision = engine.evaluate(pos, 98.0, 40.0, 99.0, 75, 0.60, 5, ou_half_life=10.0)
    assert decision.decision == ExitDecisionType.HOLD
