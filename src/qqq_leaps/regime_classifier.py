"""
QQQ LEAPS — Layer A: Regime Classifier
========================================
Wraps the TurboCore 2-state HMM + SMA rule-based regime detection and maps
regime states to LEAPS structure parameters (delta, DTE, position sizing).
"""
import logging
from dataclasses import dataclass
import pandas as pd

from .config import QQQLeapsConfig

logger = logging.getLogger(__name__)


@dataclass
class LeapsParams:
    """LEAPS structure parameters for a given regime."""
    regime: str
    allow_entry: bool
    delta: float
    dte: int
    max_contracts: int
    size_multiplier: float      # Scales max_position_pct
    protective_put: bool        # Layer E: immediately hedge
    description: str


REGIME_PARAMS = {
    "BULL_STRONG": LeapsParams(
        regime="BULL_STRONG",
        allow_entry=True,
        delta=0.85,
        dte=365,
        max_contracts=2,
        size_multiplier=1.0,
        protective_put=False,
        description="Strong bull — aggressive delta, 12M LEAPS, full size",
    ),
    "BULL_MODERATE": LeapsParams(
        regime="BULL_MODERATE",
        allow_entry=True,
        delta=0.80,
        dte=365,
        max_contracts=1,
        size_multiplier=0.75,
        protective_put=False,
        description="Moderate bull — standard delta, 12M LEAPS, 75% size",
    ),
    "CHOPPY": LeapsParams(
        regime="CHOPPY",
        allow_entry=True,
        delta=0.80,
        dte=540,
        max_contracts=1,
        size_multiplier=0.60,
        protective_put=False,
        description="Choppy/neutral — defensive delta, 18M LEAPS, 60% size",
    ),
    "BEAR": LeapsParams(
        regime="BEAR",
        allow_entry=False,
        delta=0.65,
        dte=730,
        max_contracts=0,
        size_multiplier=0.0,
        protective_put=True,
        description="Bear — NO new entries; protective put overlay on open positions",
    ),
    "BEAR_SMA_FORCED": LeapsParams(
        regime="BEAR_SMA_FORCED",
        allow_entry=False,
        delta=0.65,
        dte=730,
        max_contracts=0,
        size_multiplier=0.0,
        protective_put=True,
        description="Bear (SMA200 forced) — NO new entries; emergency hedge",
    ),
}


class LeapsRegimeClassifier:
    """
    Layer A: Maps market regime to LEAPS entry parameters.

    Uses a two-source ensemble:
      1. TurboCore 2-state HMM bull probability (from `hmm_p_bull` feature)
      2. Rule-based SMA/VIX classification (fallback + hard gate)

    Smoothing: 5-day rolling mode prevents whipsawing between regimes.
    """

    def __init__(self, config: QQQLeapsConfig):
        self.config = config

    def classify_regime(self, row: pd.Series) -> str:
        """
        Classify regime for a single row of the master feature DataFrame.
        Combines HMM signal with SMA hard gates.
        """
        hmm_p_bull = float(row.get("hmm_p_bull", 0.5))
        rule_regime = str(row.get("rule_regime", "BULL_MODERATE"))
        vix = float(row.get("vix", 20))
        above_sma200 = bool(row.get("above_sma200", True))
        above_sma100 = bool(row.get("above_sma100", True))

        # Hard override: below SMA200 with buffer = always BEAR
        if not above_sma200 and float(row.get("dist_sma200", 0)) < -0.03:
            return "BEAR_SMA_FORCED"

        # Below SMA100 = BEAR
        if not above_sma100:
            return "BEAR"

        # HMM-driven classification with rule fallback
        if hmm_p_bull >= 0.70 and vix < 25:
            return "BULL_STRONG"
        elif hmm_p_bull >= 0.55 and vix < 35:
            return "BULL_MODERATE"
        elif hmm_p_bull < 0.35 or vix > 35:
            return "BEAR"
        else:
            return "CHOPPY"

    def get_params(self, regime: str) -> LeapsParams:
        """Returns LeapsParams for a given regime string."""
        return REGIME_PARAMS.get(regime, REGIME_PARAMS["CHOPPY"])

    def apply_to_master(self, master: pd.DataFrame) -> pd.DataFrame:
        """
        Applies regime classification to the entire master DataFrame.
        Adds columns: `leaps_regime`, `leaps_allow_entry`, `leaps_delta`, `leaps_dte`.
        """
        out = master.copy()
        regimes = out.apply(self.classify_regime, axis=1)

        # 5-day rolling mode smoothing (eliminate single-day whipsaws)
        encode = {"BULL_STRONG": 4, "BULL_MODERATE": 3, "CHOPPY": 2, "BEAR": 1, "BEAR_SMA_FORCED": 0}
        decode = {v: k for k, v in encode.items()}
        encoded   = regimes.map(encode).astype(float)
        smoothed  = encoded.rolling(5, min_periods=1).apply(
            lambda x: pd.Series(x).mode().iloc[0]
        )
        out["leaps_regime"]      = smoothed.map(decode).fillna("CHOPPY")
        out["leaps_allow_entry"] = out["leaps_regime"].apply(
            lambda r: REGIME_PARAMS.get(r, REGIME_PARAMS["CHOPPY"]).allow_entry
        )
        out["leaps_delta"] = out["leaps_regime"].apply(
            lambda r: REGIME_PARAMS.get(r, REGIME_PARAMS["CHOPPY"]).delta
        )
        out["leaps_dte"] = out["leaps_regime"].apply(
            lambda r: REGIME_PARAMS.get(r, REGIME_PARAMS["CHOPPY"]).dte
        )
        out["leaps_size_mult"] = out["leaps_regime"].apply(
            lambda r: REGIME_PARAMS.get(r, REGIME_PARAMS["CHOPPY"]).size_multiplier
        )
        return out
