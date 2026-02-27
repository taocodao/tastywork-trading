import pytest
import pandas as pd
from src.tqqq.crash_guard import CrashGuard, CrashGuardResult

def test_crash_guard_hard_gate_sma():
    cg = CrashGuard()
    
    # Daily says SMA is 100
    daily_df = pd.DataFrame([{"tqqq_close": 80.0, "sma_200": 100.0}] * 200)
    
    # Intraday drops to 70 (-30% below SMA)
    intraday_row = pd.Series({"close": 70.0, "rsi_2": 2.0, "vol_ratio": 3.0})
    
    res = cg.evaluate_entry(daily_df, intraday_row, ml_prob=0.9)
    
    assert res.passed is False
    assert res.multiplier == 0.0
    assert "FAIL" in res.reasons["gate_200ma"]

def test_crash_guard_max_score():
    cg = CrashGuard()
    daily_df = pd.DataFrame([{
        "sma_200": 100.0,
        "hurst_100": 0.30,      # 15 pts
        "vix_sma_ratio": 0.90,  # 15 pts
    }] * 200)
    
    intraday_row = pd.Series({
        "close": 105.0,         # > SMA -> 20 pts
        "rsi_2": 2.0,           # < 5 -> 25 pts
        "vol_ratio": 3.0        # > 2.0 -> 10 pts
    })
    
    # ML = 0.90 -> 15 pts
    # Total expected: 15+15+20+25+10+15 = 100 pts
    res = cg.evaluate_entry(daily_df, intraday_row, ml_prob=0.90)
    
    assert res.passed is True
    assert res.score == 100
    assert res.multiplier == 1.0

def test_crash_guard_mid_tier_pass():
    cg = CrashGuard()
    daily_df = pd.DataFrame([{
        "sma_200": 100.0,
        "hurst_100": 0.48,      # 8 pts
        "vix_sma_ratio": 1.15,  # 5 pts
    }] * 200)
    
    intraday_row = pd.Series({
        "close": 90.0,          # -10% SMA -> 10 pts
        "rsi_2": 12.0,          # < 15 -> 15 pts
        "vol_ratio": 1.2        # > 1.0 -> 3 pts
    })
    
    # ML = 0.60 -> 5 pts
    # Total expected: 8+5+10+15+3+5 = 46 pts -> Fails (needs 55)
    res = cg.evaluate_entry(daily_df, intraday_row, ml_prob=0.60)
    assert res.passed is False
    assert res.multiplier == 0.0
    
    # Bump RSI to < 5 (+10 extra pts) -> 56 pts (passes tier 1)
    intraday_row["rsi_2"] = 3.0 
    res2 = cg.evaluate_entry(daily_df, intraday_row, ml_prob=0.60)
    assert res2.passed is True
    assert res2.multiplier == 0.4
    assert res2.score == 56

def test_crash_guard_insufficient_data():
    cg = CrashGuard()
    daily_df = pd.DataFrame([{"tqqq_close": 100.0}] * 50) # only 50 rows
    res = cg.evaluate_entry(daily_df, pd.Series(), 0.5)
    
    assert res.passed is False
    assert "error" in res.reasons
