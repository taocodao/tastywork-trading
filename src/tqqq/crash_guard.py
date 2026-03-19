"""
TQQQ Crash Guard
================
5-layer regime filter gating all diagonal spread entries.
Calculates a composite score based on technical and macroeconomic metrics.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class CrashGuardResult:
    passed: bool
    score: int
    multiplier: float
    reasons: Dict[str, Any]

class CrashGuard:
    """
    Hybrid scoring engine gating all diagonal spread entries.
    2 Hard gates + 6-factor scoring (0-100 pts).
    Minimum 55 points required to pass.
    """

    def evaluate_entry(self, daily_df: pd.DataFrame, intraday_row: pd.Series, ml_prob: float) -> CrashGuardResult:
        if daily_df.empty or len(daily_df) < 1:
            return CrashGuardResult(False, 0, 0.0, {"error": "Insufficient daily data"})

        latest_daily = daily_df.iloc[-1]
        reasons = {}
        score = 0
        
        # --- TIER 1: HARD GATES ---
        
        # Gate 1: Distance from 200 SMA (Don't buy falling knives > 25% below 200 SMA)
        tqqq_close = intraday_row.get("close", latest_daily.get("tqqq_close", 0))
        sma_200 = latest_daily.get("sma_200", 0)
        
        if sma_200 > 0:
            dist_sma = (tqqq_close - sma_200) / sma_200
        else:
            dist_sma = 0
            
        if dist_sma < -0.25:
            reasons["gate_200ma"] = f"FAIL: Distance {dist_sma:.1%} < -25%"
            return CrashGuardResult(False, 0, 0.0, reasons)
        else:
            reasons["gate_200ma"] = "PASS"
            
        # Gate 2: Circuit Breaker
        # For backtesting, we rely on VIX/Regime metrics.
        # In live trading, this would tie into the redis circuit breaker state.
            
        # --- TIER 2: SCORING ENGINE (Max 100 pts) ---
        
        # Factor 1: RSI-2 Depth (Intraday) [Max 25 pts]
        rsi_2 = intraday_row.get("rsi_2", latest_daily.get("rsi_2", 50))
        if rsi_2 < 5:
            pts = 25
        elif rsi_2 < 10:
            pts = 20
        elif rsi_2 < 15:
            pts = 15
        elif rsi_2 < 20:
            pts = 10
        else:
            pts = 0
        score += pts
        reasons["factor_rsi2"] = f"RSI-2={rsi_2:.1f} (+{pts} pts)"
        
        # Factor 2: Distance from 200 SMA [Max 20 pts]
        if dist_sma >= 0:
            pts = 20
        elif dist_sma >= -0.05:
            pts = 15
        elif dist_sma >= -0.15:
            pts = 10
        else:  # -0.15 to -0.25
            pts = 5
        score += pts
        reasons["factor_sma"] = f"DistSMA={dist_sma:.1%} (+{pts} pts)"
        
        # Factor 3: Hurst Exponent (Mean Reversion) [Max 15 pts]
        hurst = latest_daily.get("hurst_100", 0.5)
        if pd.isna(hurst): hurst = 0.5
        
        if hurst < 0.35:
            pts = 15
        elif hurst < 0.45:
            pts = 12
        elif hurst <= 0.50:
            pts = 8
        elif hurst <= 0.55:
            pts = 3
        else:
            pts = 0
        score += pts
        reasons["factor_hurst"] = f"Hurst={hurst:.3f} (+{pts} pts)"
        
        # Factor 4: VIX Term Structure / Ratio [Max 15 pts]
        vix_ratio = latest_daily.get("vix_sma_ratio", 1.0)
        if pd.isna(vix_ratio): vix_ratio = 1.0
        
        if vix_ratio < 1.0:
            pts = 15
        elif vix_ratio < 1.10:
            pts = 10
        elif vix_ratio < 1.20:
            pts = 5
        else:
            pts = 0
        score += pts
        reasons["factor_vix"] = f"VIX Ratio={vix_ratio:.2f} (+{pts} pts)"
        
        # Factor 5: Volume Capitulation (Intraday) [Max 10 pts]
        vol_ratio = intraday_row.get("vol_ratio", 1.0)
        if pd.isna(vol_ratio): vol_ratio = 1.0
        
        if vol_ratio > 2.0:
            pts = 10
        elif vol_ratio > 1.5:
            pts = 7
        elif vol_ratio > 1.0:
            pts = 3
        else:
            pts = 0
        score += pts
        reasons["factor_vol"] = f"Vol Ratio={vol_ratio:.1f}x (+{pts} pts)"
        
        # Factor 6: ML Probability [Max 15 pts]
        if ml_prob > 0.75:
            pts = 15
        elif ml_prob >= 0.65:
            pts = 10
        elif ml_prob >= 0.55:
            pts = 5
        else:
            pts = 0
        score += pts
        reasons["factor_ml"] = f"ML={ml_prob:.2%} (+{pts} pts)"

        # --- POSITION SIZING ---
        # 55-65 -> 1.0x size
        # 65-75 -> 1.2x size
        # 75-85 -> 1.6x size
        # 85+   -> 2.0x size
        passed = False
        multiplier = 0.0
        
        if score >= 85:
            passed = True
            multiplier = 2.0
        elif score >= 75:
            passed = True
            multiplier = 1.6
        elif score >= 65:
            passed = True
            multiplier = 1.2
        elif score >= 55:
            passed = True
            multiplier = 1.0

        return CrashGuardResult(passed, score, multiplier, reasons)
