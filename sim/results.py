import numpy as np
import pandas as pd
from typing import Dict

def compute_results(equity_curve: pd.Series) -> Dict[str, float]:
    """
    Compute daily trading backtest results.
    
    :param equity_curve: Series of daily portfolio total values
    """
    if len(equity_curve) < 2:
        return {"CAGR": 0.0, "Sharpe": 0.0, "MaxDrawdown": 0.0, "TotalReturn": 0.0}
        
    start_val = equity_curve.iloc[0]
    end_val = equity_curve.iloc[-1]
    
    # Calculate years (assuming 252 trading days per year, but dates might have gaps. Use len/252)
    n_years = max(1.0, len(equity_curve) / 252.0)
    
    # CAGR
    cagr = (end_val / start_val) ** (1 / n_years) - 1.0
    
    # Daily returns
    daily_returns = equity_curve.pct_change().dropna()
    
    # Sharpe Ratio (annualized, assuming ~4.5% risk-free rate)
    mean_ret = daily_returns.mean()
    std_ret = daily_returns.std()
    
    if std_ret > 0:
        # Annualize by multiplying by sqrt(252)
        sharpe = (mean_ret - (0.045 / 252)) / std_ret * np.sqrt(252)
    else:
        sharpe = 0.0
        
    # Max Drawdown
    cumulative_max = equity_curve.cummax()
    drawdown = (equity_curve - cumulative_max) / cumulative_max
    max_dd = drawdown.min()
    
    return {
        "CAGR": cagr * 100.0,
        "Sharpe": sharpe,
        "MaxDrawdown": max_dd * 100.0,
        "TotalReturn": ((end_val / start_val) - 1.0) * 100.0
    }
