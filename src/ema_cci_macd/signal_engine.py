"""
Signal Engine — 5-Condition Entry Evaluator
=============================================
Applies the Traderversity EMA-CCI-MACD strategy rules.
Returns BUY, SELL, or NONE.
"""

import logging
import logging
from typing import Optional
import pandas as pd

from .types import SignalCandidate

logger = logging.getLogger(__name__)

def evaluate_signal(df: pd.DataFrame, symbol: str, timeframe: str,
                    ema_layers: list, proximity_pct: float = 0.003,
                    cci_lookback: int = 10) -> Optional[SignalCandidate]:
    """
    Evaluate the 5-condition entry filter stack on the latest bars.
    Returns a SignalCandidate if all conditions are met, otherwise None.
    """
    if len(df) < cci_lookback + 2:
        return None

    cur  = df.iloc[-1]
    prev = df.iloc[-2]

    e1 = f"ema_{ema_layers[0]}"
    e2 = f"ema_{ema_layers[1]}"
    e3 = f"ema_{ema_layers[2]}" if len(ema_layers) > 2 else e2

    for col in [e1, e2, "cci", "macd_hist"]:
        if col not in df.columns:
            return None

    price    = float(cur["close"])
    ema1     = float(cur[e1])
    ema2     = float(cur[e2])
    ema3     = float(cur[e3]) if e3 in df.columns else ema2
    cci_now  = float(cur["cci"])
    cci_prev = float(prev["cci"])
    hist_now = float(cur["macd_hist"])
    hist_prev= float(prev["macd_hist"])

    cci_win  = df["cci"].iloc[-(cci_lookback + 1):-1]

    def near(p, v1, v2, pct):
        d1 = abs(p - v1) / v1 if v1 > 0 else 999
        d2 = abs(p - v2) / v2 if v2 > 0 else 999
        return d1 <= pct or d2 <= pct

    # BUY
    b1 = price > ema1
    b2 = near(price, ema1, ema2, proximity_pct)
    b3 = float(cci_win.min()) < -100
    b4 = cci_prev < 0 and cci_now >= 0
    b5 = hist_now > 0 and hist_prev > 0

    if all([b1, b2, b3, b4, b5]):
        stop = ema2 if price > ema2 else ema3
        ts = str(df.index[-1])
        return SignalCandidate(
            symbol=symbol, timeframe=timeframe, direction="BUY",
            timestamp=ts, entry_price=round(price, 4), stop_loss=round(stop, 4),
            ema1_value=round(ema1, 4), ema2_value=round(ema2, 4), ema3_value=round(ema3, 4),
            cci_value=round(cci_now, 2), macd_hist=round(hist_now, 4), conditions_met=5
        )

    # SELL
    s1 = price < ema1
    s2 = near(price, ema1, ema2, proximity_pct)
    s3 = float(cci_win.max()) > 100
    s4 = cci_prev > 0 and cci_now <= 0
    s5 = hist_now < 0 and hist_prev < 0

    if all([s1, s2, s3, s4, s5]):
        stop = ema2 if price < ema2 else ema3
        ts = str(df.index[-1])
        return SignalCandidate(
            symbol=symbol, timeframe=timeframe, direction="SELL",
            timestamp=ts, entry_price=round(price, 4), stop_loss=round(stop, 4),
            ema1_value=round(ema1, 4), ema2_value=round(ema2, 4), ema3_value=round(ema3, 4),
            cci_value=round(cci_now, 2), macd_hist=round(hist_now, 4), conditions_met=5
        )

    return None
