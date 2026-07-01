"""
OTM Naked Options — Signal Engine
====================================
Composite entry signal combining three independent layers:
  1. 52-Week Proximity Filter   — structural overbought/oversold anchor
  2. Momentum Confirmation      — RSI + Bollinger %B + SMA distance
  3. Market Regime Filter       — VIX level + term structure + SPX trend

All three layers must align to generate a CALL or PUT signal.
"""
import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import OTMNakedConfig, REGIME_DELTA_MAP, VIX_LOW, VIX_NORMAL, VIX_HIGH

logger = logging.getLogger(__name__)


class SignalType(Enum):
    NONE = "NONE"
    SELL_CALL = "SELL_CALL"   # Overbought → sell OTM call
    SELL_PUT  = "SELL_PUT"    # Oversold   → sell OTM put
    BOTH      = "BOTH"        # Rare: both conditions (handle conservatively)


@dataclass
class EntrySignal:
    symbol:          str
    signal_type:     SignalType
    vix_regime:      str          # LOW_VOL / NORMAL / HIGH_VOL / CRISIS
    # Layer scores (True = condition met)
    l1_proximity:    bool         # 52W high/low proximity
    l2_momentum:     bool         # RSI + BB + SMA momentum
    l3_regime:       bool         # Market regime allows trading
    # Metrics driving the signal
    pct_from_52w_high: float
    pct_from_52w_low:  float
    rsi_14:          float
    pct_b:           float
    dist_sma20:      float
    vix:             float
    iv_rank:         float
    iv_hv_ratio:     float
    # Composite confidence (0.0–1.0 based on signal strength)
    raw_confidence:  float
    # Pathway tag (Phase 2)
    pathway:         str = "A"    # "A" = HILO signal; "B" = VIX-conditional


def classify_vix_regime(vix_level: float) -> str:
    """Map current VIX to regime string."""
    if vix_level < VIX_LOW:
        return "LOW_VOL"
    elif vix_level < VIX_NORMAL:
        return "NORMAL"
    elif vix_level < VIX_HIGH:
        return "HIGH_VOL"
    else:
        return "CRISIS"


class OTMSignalEngine:
    """
    Three-layer composite signal engine for OTM naked option entry.

    Usage:
        engine = OTMSignalEngine(config)
        signal = engine.evaluate(symbol, feature_row)
        if signal.signal_type != SignalType.NONE:
            # Proceed to strike selection
    """

    def __init__(self, config: Optional[OTMNakedConfig] = None):
        self.config = config or OTMNakedConfig()

    def evaluate(self, symbol: str, row: pd.Series) -> EntrySignal:
        """
        Evaluate all three signal layers for a given feature row.

        Args:
            symbol: Ticker symbol
            row:    One row from the feature DataFrame (today's features)

        Returns:
            EntrySignal with signal_type, regime, and supporting metrics
        """
        cfg = self.config

        # ── Extract key features ──────────────────────────────────────────────
        vix             = float(row.get("vix",            20.0))
        pct_from_hi     = float(row.get("pct_from_52w_high", -0.10))  # ≤ 0
        pct_from_lo     = float(row.get("pct_from_52w_low",   0.20))  # ≥ 0
        rsi_14          = float(row.get("rsi_14",         50.0))
        pct_b           = float(row.get("pct_b",           0.5))
        dist_sma20      = float(row.get("dist_sma20",      0.0))
        vix_term_slope  = float(row.get("vix_term_slope",  0.0))
        above_sma200    = float(row.get("above_sma200",    1.0))
        iv_rank         = float(row.get("iv_rank",         0.5))
        iv_hv_ratio     = float(row.get("iv_hv_ratio",     1.0))
        earnings_near   = bool(row.get("earnings_near",    False))
        cci_20          = float(row.get("cci_20",          0.0))
        macd_hist_norm  = float(row.get("macd_hist_norm",  0.0))

        # ── VIX Regime ────────────────────────────────────────────────────────
        regime = classify_vix_regime(vix)

        # ── Layer 3: Market Regime (must pass first — circuit breaker) ────────
        l3_regime = self._check_regime(regime, vix, vix_term_slope,
                                       above_sma200, iv_rank, iv_hv_ratio,
                                       earnings_near)

        # ── Layer 1: 52-Week Proximity ────────────────────────────────────────
        call_l1 = self._check_52w_call(pct_from_hi)
        put_l1  = self._check_52w_put(pct_from_hi, pct_from_lo)

        # ── Layer 2: Momentum Confirmation ───────────────────────────────────
        call_l2 = self._check_momentum_call(rsi_14, pct_b, dist_sma20, cci_20, macd_hist_norm)
        put_l2  = self._check_momentum_put(rsi_14, pct_b, dist_sma20, cci_20, macd_hist_norm)

        # ── Pathway A: HILO signal (existing) ──────────────────────────────────────────────
        call_signal_a = l3_regime and call_l1 and call_l2
        put_signal_a  = l3_regime and put_l1  and put_l2

        # ── Pathway B: VIX-conditional (Phase 2) ──────────────────────────────────────────
        # Only fires when Pathway A is silent -- fills trade frequency gap in calm markets.
        call_signal_b = False
        put_signal_b  = False
        pathway = "A"
        if cfg.pathway_b_enabled and not (call_signal_a or put_signal_a):
            call_signal_b, put_signal_b = self._check_pathway_b(
                vix=vix, iv_rank=iv_rank, iv_hv_ratio=iv_hv_ratio,
                rsi_14=rsi_14, earnings_near=earnings_near, regime=regime,
            )
            if call_signal_b or put_signal_b:
                pathway = "B"

        call_signal = call_signal_a or call_signal_b
        put_signal  = put_signal_a  or put_signal_b

        if call_signal and put_signal:
            signal_type = SignalType.BOTH
        elif call_signal:
            signal_type = SignalType.SELL_CALL
        elif put_signal:
            signal_type = SignalType.SELL_PUT
        else:
            signal_type = SignalType.NONE

        # ── Raw confidence heuristic (pre-ML) ────────────────────────────────────────────
        raw_confidence = self._compute_raw_confidence(
            signal_type, pct_from_hi, pct_from_lo,
            rsi_14, pct_b, iv_rank, iv_hv_ratio
        )

        return EntrySignal(
            symbol=symbol,
            signal_type=signal_type,
            vix_regime=regime,
            l1_proximity=call_l1 or put_l1,
            l2_momentum=call_l2 or put_l2,
            l3_regime=l3_regime,
            pct_from_52w_high=pct_from_hi,
            pct_from_52w_low=pct_from_lo,
            rsi_14=rsi_14,
            pct_b=pct_b,
            dist_sma20=dist_sma20,
            vix=vix,
            iv_rank=iv_rank,
            iv_hv_ratio=iv_hv_ratio,
            raw_confidence=raw_confidence,
            pathway=pathway,
        )

    def evaluate_batch(self, symbol: str, features: pd.DataFrame) -> pd.DataFrame:
        """
        Evaluate signal for every row in a feature DataFrame (for backtesting).

        Returns:
            DataFrame with columns: signal_type, regime, raw_confidence, l1, l2, l3
        """
        records = []
        for date, row in features.iterrows():
            sig = self.evaluate(symbol, row)
            records.append({
                "date":             date,
                "signal_type":      sig.signal_type.value,
                "vix_regime":       sig.vix_regime,
                "l1_proximity":     sig.l1_proximity,
                "l2_momentum":      sig.l2_momentum,
                "l3_regime":        sig.l3_regime,
                "raw_confidence":   sig.raw_confidence,
                "pct_from_52w_high": sig.pct_from_52w_high,
                "pct_from_52w_low":  sig.pct_from_52w_low,
                "rsi_14":           sig.rsi_14,
                "pct_b":            sig.pct_b,
                "iv_rank":          sig.iv_rank,
                "iv_hv_ratio":      sig.iv_hv_ratio,
                "vix":              sig.vix,
            })
        return pd.DataFrame(records).set_index("date")

    # ── Private: Layer checks ─────────────────────────────────────────────────

    def _check_regime(self, regime: str, vix: float, vix_term_slope: float,
                      above_sma200: float, iv_rank: float, iv_hv_ratio: float,
                      earnings_near: bool) -> bool:
        """Layer 3: Must-pass gates for new entries."""
        # Crisis -> no trades
        if regime == "CRISIS":
            return False
        # Earnings proximity -> skip
        if earnings_near:
            return False
        # IV rank must be elevated (premium selling edge)
        if iv_rank < self.config.min_iv_rank:
            return False
        # IV must be elevated relative to HV
        if iv_hv_ratio < self.config.min_iv_hv_ratio:
            return False
        return True

    def _check_pathway_b(
        self, vix: float, iv_rank: float, iv_hv_ratio: float,
        rsi_14: float, earnings_near: bool, regime: str,
    ) -> tuple:
        """
        Pathway B: VIX-conditional entry when HILO signal (Pathway A) is quiet.
        Fires when VIX is elevated enough to confirm volatility risk premium
        AND RSI confirms the directional oversold/overbought condition.

        Returns: (call_signal_b, put_signal_b) booleans
        """
        cfg = self.config

        # Hard gates -- circuit breakers
        if regime == "CRISIS" or vix >= cfg.pathway_b_vix_pause:
            return False, False
        if earnings_near:
            return False, False

        # VIX must be >= threshold (volatility risk premium confirmed)
        if vix < cfg.pathway_b_vix_min:
            return False, False

        # Stricter IV rank gate (must be clearly elevated, not just marginal)
        if iv_rank < cfg.pathway_b_iv_rank_min:
            return False, False

        # IV/HV ratio gate (same as Pathway A -- premium must exceed realized vol)
        if iv_hv_ratio < cfg.min_iv_hv_ratio:
            return False, False

        # RSI momentum confirmation (strict -- must be genuinely oversold/overbought)
        put_b  = rsi_14 <= cfg.pathway_b_rsi_oversold    # RSI < 30: genuine oversold
        call_b = rsi_14 >= cfg.pathway_b_rsi_overbought  # RSI > 70: genuine overbought

        return call_b, put_b

    def _check_52w_call(self, pct_from_hi: float) -> bool:
        """Layer 1 CALL: Price near or above 52W high → overbought."""
        cfg = self.config
        # Near 52W high (within call_near_52w_high_pct below)
        near_hi = pct_from_hi >= -cfg.call_near_52w_high_pct
        # Already broken above 52W high (positive return from annual hi — rare)
        broken_above = pct_from_hi >= 0
        return near_hi or broken_above

    def _check_52w_put(self, pct_from_hi: float, pct_from_lo: float) -> bool:
        """Layer 1 PUT: Price near 52W low OR declined heavily from 52W high."""
        cfg = self.config
        # Near 52W low
        near_lo = pct_from_lo <= cfg.put_near_52w_low_pct
        # Heavy decline from 52W high (panic/oversold zone)
        big_decline = pct_from_hi <= -cfg.put_decline_from_high
        return near_lo or big_decline

    def _check_momentum_call(self, rsi_14: float, pct_b: float,
                              dist_sma20: float, cci_20: float = 0.0,
                              macd_hist_norm: float = 0.0) -> bool:
        """Layer 2 CALL: At least 1 of 4 overbought momentum indicators."""
        score = 0
        if rsi_14 >= self.config.rsi_overbought:           score += 1
        if pct_b >= self.config.bb_overbought:             score += 1
        if dist_sma20 >= 0.05:                             score += 1  # 5%+ above SMA20
        if cci_20 >= 100:                                  score += 1  # CCI overbought
        return score >= 1

    def _check_momentum_put(self, rsi_14: float, pct_b: float,
                             dist_sma20: float, cci_20: float = 0.0,
                             macd_hist_norm: float = 0.0) -> bool:
        """Layer 2 PUT: At least 1 of 4 oversold momentum indicators."""
        score = 0
        if rsi_14 <= self.config.rsi_oversold:             score += 1
        if pct_b <= self.config.bb_oversold:               score += 1
        if dist_sma20 <= -0.05:                            score += 1  # 5%+ below SMA20
        if cci_20 <= -100:                                 score += 1  # CCI oversold
        return score >= 1


    def _compute_raw_confidence(
        self, signal_type: SignalType,
        pct_from_hi: float, pct_from_lo: float,
        rsi_14: float, pct_b: float,
        iv_rank: float, iv_hv_ratio: float,
    ) -> float:
        """Heuristic confidence score 0–1 (pre-ML gate fallback)."""
        if signal_type == SignalType.NONE:
            return 0.0

        score = 0.5  # base

        if signal_type == SignalType.SELL_CALL:
            # Stronger signal if further above 52W high / more overbought
            score += min(abs(pct_from_hi) * 2, 0.20)
            score += min((rsi_14 - 70) / 30, 0.10) if rsi_14 > 70 else 0
            score += min((pct_b - 0.95) * 2, 0.05) if pct_b > 0.95 else 0

        elif signal_type == SignalType.SELL_PUT:
            score += min(pct_from_lo * 2, 0.20)
            score += min((30 - rsi_14) / 30, 0.10) if rsi_14 < 30 else 0
            score += min((0.05 - pct_b) * 2, 0.05) if pct_b < 0.05 else 0

        # IV rank bonus (higher IV → better premium selling environment)
        score += min(iv_rank * 0.10, 0.10)
        # IV/HV ratio bonus
        score += min((iv_hv_ratio - 1.0) * 0.05, 0.05)

        return float(np.clip(score, 0.0, 1.0))
