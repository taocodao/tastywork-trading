"""
RegimeBase Dynamic Ladder Strategy - Metrics
======================================
Calculates portfolio metrics, Sharpe, Kelly, etc.
"""
import pandas as pd
import numpy as np

def calculate_metrics(pnls: list) -> dict:
    if not pnls:
        return {}
    
    pnl_series = pd.Series(pnls)
    win_rate = (pnl_series > 0).mean()
    sharpe = pnl_series.mean() / (pnl_series.std() + 1e-9) * np.sqrt(252) if pnl_series.std() > 0 else 0
    max_dd = (pnl_series.cumsum() - pnl_series.cumsum().cummax()).min()
    profit_factor = pnl_series[pnl_series > 0].sum() / abs(pnl_series[pnl_series < 0].sum()) if pnl_series[pnl_series < 0].sum() != 0 else np.inf
    
    return {
        "n_trades": len(pnls),
        "win_rate_pct": round(win_rate * 100, 2),
        "sharpe": round(sharpe, 3),
        "max_dd_pct": round(max_dd * 100, 2),
        "profit_factor": round(profit_factor, 2)
    }
