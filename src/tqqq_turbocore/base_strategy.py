import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class BaseStrategy:
    """
    Implements the core deterministic logic for TQQQ TurboCore — v2.

    Layer 1 rules:
      1. QQQ SMA200 Hysteresis Gate (+5% Buy / -3% Sell) → sma200_regime
      2. TQQQ 5/30 EMA Crossover → tqqq_bull_cross
      3. QQQ 10/50 EMA Dual-Confirmation → dual_ema_confirmed / partial_confirm
      4. RSI(2) Position-Size Overlay → rsi_add_signal / rsi_trim_signal

    Outputs base_signal (1/0/-1) plus soft-modifier columns consumed by AllocationOptimizer.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def evaluate(self) -> pd.DataFrame:
        if self.df.empty:
            logger.warning("Empty dataframe provided to BaseStrategy")
            return self.df

        logger.info("Evaluating Base Strategy rules (v2)...")

        # ── 1. SMA200 Hysteresis Regime ───────────────────────────────────────
        # +1 = Risk-On, 0 = Transitional, -1 = Risk-Off
        current_state = 0
        regimes = []
        for _, row in self.df.iterrows():
            if row.get('qqq_above_sma200_buy', False):
                current_state = 1
            elif row.get('qqq_below_sma200_sell', False):
                current_state = -1
            regimes.append(current_state)
        self.df['sma200_regime'] = regimes

        # ── 2. Base Signal from SMA200 gate + TQQQ 5/30 cross ────────────────
        signals = []
        for _, row in self.df.iterrows():
            if row['sma200_regime'] == 1 and row.get('tqqq_bull_cross', False):
                signals.append(1)   # Aggressive Bull
            elif row['sma200_regime'] == 1 and not row.get('tqqq_bull_cross', False):
                signals.append(0)   # Defensive Bull (Death cross inside Risk-On)
            elif row['sma200_regime'] == -1:
                signals.append(-1)  # Hard Bear / Exit
            else:
                signals.append(0)   # Transitional
        self.df['base_signal'] = signals

        # ── 3. Dual EMA Confirmation (QQQ 10/50 gate) ────────────────────────
        if 'qqq_10_50_bull_cross' in self.df.columns:
            # dual_ema_confirmed: TQQQ 5/30 AND QQQ 10/50 both bullish
            self.df['dual_ema_confirmed'] = (
                self.df['tqqq_bull_cross'] & self.df['qqq_10_50_bull_cross']
            )
            # partial_confirm: TQQQ fired but broader QQQ trend not confirmed
            self.df['partial_confirm'] = (
                self.df['tqqq_bull_cross'] & ~self.df['qqq_10_50_bull_cross']
            )
        else:
            # Fallback when pipeline didn't compute QQQ EMAs
            self.df['dual_ema_confirmed'] = self.df['tqqq_bull_cross']
            self.df['partial_confirm'] = pd.Series(False, index=self.df.index)

        # ── 4. RSI(2) Position-Size Overlay ──────────────────────────────────
        close = self.df['tqqq_close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(2).mean()
        rs = gain / loss.replace(0, np.nan)
        self.df['tqqq_rsi_2'] = (100 - (100 / (1 + rs))).clip(0, 100)

        # Only valid signals when inside a Risk-On macro regime
        in_bull = self.df['sma200_regime'] == 1
        self.df['rsi_add_signal'] = in_bull & (self.df['tqqq_rsi_2'] < 10)
        self.df['rsi_trim_signal'] = in_bull & (self.df['tqqq_rsi_2'] > 90)

        logger.info(
            f"BaseStrategy v2 complete: "
            f"dual_confirmed={self.df['dual_ema_confirmed'].sum()} days, "
            f"partial={self.df['partial_confirm'].sum()} days, "
            f"rsi_add={self.df['rsi_add_signal'].sum()} days, "
            f"rsi_trim={self.df['rsi_trim_signal'].sum()} days"
        )
        return self.df
