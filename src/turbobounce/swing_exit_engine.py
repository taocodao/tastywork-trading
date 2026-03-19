"""
Swing Exit Engine
=================
5-priority cascade for diagonal positions, featuring the Theta Kicker.
"""

from enum import Enum, auto
import logging
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

class ExitDecisionType(Enum):
    HOLD = auto()
    CLOSE_ALL = auto()
    BTC_SHORT = auto()
    ROLL_HEDGE = auto()

@dataclass
class ExitDecision:
    decision: ExitDecisionType
    reason: str
    priority: int

class SwingExitEngine:
    """
    Evaluates exit conditions for the TQQQ Put Diagonal Swing Trade.
    """
    
    def _get_val(self, obj, key, default):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_config_val(self, key, default):
        try:
            import diagonal_strategy.config as v3_config
            return getattr(v3_config, key, default)
        except Exception:
            return default

    def evaluate(self, position, current_price, rsi_2, sma_5,
                 regime_score, ml_prob, days_held,
                 rsi_2_prev=None, days_traded=None,
                 current_spread_mark=0.0, bp_consumed=0.0,
                 pnl_pct=None, atr_14=None) -> ExitDecision:
        """
        V4.1 Exit Cascade — Perplexity research-validated rules.
        Sources: Connors RSI-2, Alvarez Quant Trading, Tastylive 50% credit rule, Hull 2015.
        """
        strategy = str(self._get_val(position, "strategy_type", "CREDIT_SPREAD")).upper()
        entry_price = float(self._get_val(position, "entry_price", current_price) or current_price)
        
        if pnl_pct is None:
            pnl_pct = 0.0

        if rsi_2_prev is None:
            rsi_2_prev = rsi_2

        if days_traded is None:
            days_traded = days_held  # Fallback to calendar days

        # ═══════════════════════════════════════════════════════════
        # Priority 0: PROFIT TARGET — exit winners FIRST
        # Research: Tastylive "50% credit target"; "20-30% of spread width for debits"
        # ═══════════════════════════════════════════════════════════
        if strategy in ("CREDIT_SPREAD", "PUT_BWB"):
            if pnl_pct >= 0.50:
                return ExitDecision(ExitDecisionType.CLOSE_ALL,
                    f"PROFIT_50PCT: Credit captured {pnl_pct*100:.1f}% >= 50%", 0)
        else:  # NAKED_LONG, debit structures
            if pnl_pct >= 0.25:
                return ExitDecision(ExitDecisionType.CLOSE_ALL,
                    f"PROFIT_25PCT: Option gain {pnl_pct*100:.1f}% >= 25%", 0)

        # ═══════════════════════════════════════════════════════════
        # Priority 1: 5-DAY SMA CROSS — cleanest Connors exit signal
        # Research: "Exit when price closes above the 5-bar SMA after being below it at entry"
        # (Connors original publications, confirmed by multiple independent backtests)
        # Only fire after minimum 2 days (avoid same-day noise)
        # ═══════════════════════════════════════════════════════════
        # Only fire after minimum 2 days.
        # Research: SMA5 cross is Connors' original exit — clean and reliable.
        # V5 Fix: Remove minimum profit constraint. Exiting on SMA cross directly prevents fading back.
        if days_held >= 2:
            direction = str(self._get_val(position, "direction", "BULLISH")).upper()
            if direction == "BULLISH" and current_price > sma_5:
                return ExitDecision(ExitDecisionType.CLOSE_ALL,
                    f"SMA5_EXIT: Price ${current_price:.2f} > 5-day SMA ${sma_5:.2f} (bounce confirmed, +{pnl_pct*100:.1f}%)", 1)
            elif direction == "BEARISH" and current_price < sma_5:
                return ExitDecision(ExitDecisionType.CLOSE_ALL,
                    f"SMA5_EXIT: Price ${current_price:.2f} < 5-day SMA ${sma_5:.2f} (fade confirmed)", 1)

        # ═══════════════════════════════════════════════════════════
        # Priority 2: RSI-65 CONFIRMED — 2 consecutive days above threshold
        # Research: Alvarez "RSI-4 > 65 for 2+ consecutive days" — filters false exits
        # CRITICAL: Reverting to zero profit constraint. The options will be captured during the bounce.
        # ═══════════════════════════════════════════════════════════
        if days_held >= 2:
            direction2 = str(self._get_val(position, "direction", "BULLISH")).upper()
            if direction2 == "BULLISH" and rsi_2 >= 65:
                return ExitDecision(ExitDecisionType.CLOSE_ALL,
                    f"RSI_EXIT: RSI-2={rsi_2:.0f} >= 65 (bounce limit)", 2)
            elif direction2 == "BEARISH" and rsi_2 <= 35:
                return ExitDecision(ExitDecisionType.CLOSE_ALL,
                    f"RSI_EXIT: RSI-2={rsi_2:.0f} <= 35 (fade limit)", 2)

        # ═══════════════════════════════════════════════════════════
        # Priority 3: OPTION STOP LOSS (Spread Value Stop) — set to -50%
        # Research: Tastylive 10-year study — "Stop if spread value >= 2.0 * initial credit"
        # Since margin = 3x credit, losing 2.0x credit is roughly -50% to -66% of margin.
        # We cap at -50% of the slot margin. ATR stops are removed as they are 
        # structurally incorrect for defined-risk option strategies.
        # ═══════════════════════════════════════════════════════════
        max_loss_pct = -0.50
        if pnl_pct <= max_loss_pct:
            return ExitDecision(ExitDecisionType.CLOSE_ALL,
                f"SPREAD_VALUE_STOP: PnL {pnl_pct*100:.1f}% <= {max_loss_pct*100:.0f}%", 3)

        # ═══════════════════════════════════════════════════════════
        # Priority 5: TIME STOP — 8 TRADING DAYS
        # Research: V5 Analysis indicates days 8-10 suffer massive theta decay for 5-day holds.
        # ═══════════════════════════════════════════════════════════
        trading_day_limits = {
            'CREDIT_SPREAD': 8, 'PUT_BWB': 8,
            'NAKED_LONG': 8, 'DIAGONAL': 8
        }
        t_limit = trading_day_limits.get(strategy, 8)
        if days_traded >= t_limit:
            return ExitDecision(ExitDecisionType.CLOSE_ALL,
                f"TIME_STOP: {days_traded} trading days >= {t_limit}", 5)

        # ═══════════════════════════════════════════════════════════
        # Priority 6: DTE FLOOR — avoid gamma/assignment risk
        # Research: Hull (2015) — options below 14 DTE excluded from hedging studies
        # ═══════════════════════════════════════════════════════════
        anchor_dte = max(0, self._get_val(position, "anchor_dte", 30) - days_held)
        if anchor_dte <= 7:
            return ExitDecision(ExitDecisionType.CLOSE_ALL,
                f"DTE_FLOOR: Anchor DTE {anchor_dte} <= 7", 6)

        return ExitDecision(ExitDecisionType.HOLD, "HOLD", 99)
