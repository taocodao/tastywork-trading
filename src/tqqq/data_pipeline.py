"""
TQQQ Data Pipeline
==================
Fetches and prepares all data needed by the TQQQ VIX-Adaptive strategy:
  - VIX time-series (yfinance + FRED fallback)
  - TQQQ / QQQ / SPY price data (yfinance)
  - TQQQ Options chain (IB API via ib_data_provider.py)
  - Derived feature dataframes for HMM + VIX predictor
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

from src.tqqq.ml.regime_detector import VIXRegimeDetector
from src.tqqq.ml.vix_predictor   import VIXEnsemblePredictor

logger = logging.getLogger(__name__)

# Optional imports
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    yf = None
    YF_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False


class TQQQDataPipeline:
    """
    One-stop data provider for the TQQQ strategy.
    """

    FRED_VIX_URL = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        "?id=VIXCLS"
    )
    LOOKBACK_YEARS = 3   # how many years of history to fetch initially

    def __init__(self, ib_provider=None):
        """
        Args:
            ib_provider: existing IB data provider (from ib_data_provider.py).
                         Used to fetch live options chain. May be None.
        """
        self.ib_provider = ib_provider
        self._cache: Dict[str, Any] = {}

    # ─────────────────────── Public API ──────────────────────────────────

    def get_ml_feature_dataframe(
        self, lookback_days: int = 252
    ) -> pd.DataFrame:
        """
        Returns a single merged DataFrame with all features required by both
        the HMM regime detector and the VIX ensemble predictor.
        """
        end   = datetime.today()
        start = end - timedelta(days=lookback_days + 60)   # extra buffer for rolling windows

        prices = self._fetch_prices(["TQQQ", "QQQ", "SPY"], start, end)
        vix    = self._fetch_vix(start, end)

        if prices is None or vix is None:
            logger.error("Failed to retrieve market data for feature build.")
            return pd.DataFrame()

        df = vix.join(prices, how="inner")

        # Compute HMM features
        df = self._add_hmm_features(df)

        # Compute XGBoost / LSTM features
        df = self._add_predictor_features(df)

        return df.dropna().tail(lookback_days)

    def get_live_snapshot(self) -> Dict[str, Any]:
        """
        Returns a dict of the latest VIX, TQQQ price, and derived scalars
        for the rule-based strategy evaluation.
        """
        if YF_AVAILABLE:
            tickers = yf.download(
                ["^VIX", "TQQQ", "QQQ", "SPY"],
                period="5d",
                progress=False,
                auto_adjust=True,
            )
            close = tickers["Close"]
            return {
                "vix":         float(close["^VIX"].dropna().iloc[-1]),
                "tqqq_price":  float(close["TQQQ"].dropna().iloc[-1]),
                "qqq_price":   float(close["QQQ"].dropna().iloc[-1]),
                "spy_price":   float(close["SPY"].dropna().iloc[-1]),
                "date":        str(date.today()),
            }
        else:
            logger.warning("yfinance unavailable — returning stub snapshot.")
            return {"vix": 20.0, "tqqq_price": 50.0, "qqq_price": 450.0,
                    "spy_price": 500.0, "date": str(date.today())}

    def get_options_chain(
        self,
        symbol: str = "TQQQ",
        dte_min: int = 21,
        dte_max: int = 45,
    ) -> List[Dict[str, Any]]:
        """
        Fetches the live options chain for TQQQ from the IB provider.
        Falls back to an empty list if IB is not connected.
        """
        if self.ib_provider is None:
            logger.warning("No IB provider — options chain unavailable.")
            return []

        try:
            # Delegates to the existing ib_data_provider infrastructure
            chain = self.ib_provider.get_options_chain(
                symbol=symbol,
                right="P",
                dte_min=dte_min,
                dte_max=dte_max,
            )
            return chain or []
        except Exception as exc:
            logger.error(f"Failed to fetch options chain: {exc}")
            return []

    # ─────────────────────── Internal Helpers ────────────────────────────

    def _fetch_prices(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
    ) -> Optional[pd.DataFrame]:
        if not YF_AVAILABLE:
            return None
        try:
            raw  = yf.download(symbols, start=start, end=end,
                               progress=False, auto_adjust=True)
            close = raw["Close"].copy()
            close.columns = [f"{s.lower()}_close" for s in symbols]
            return close
        except Exception as exc:
            logger.error(f"yfinance price fetch failed: {exc}")
            return None

    def _fetch_vix(
        self,
        start: datetime,
        end: datetime,
    ) -> Optional[pd.DataFrame]:
        """Primary: yfinance ^VIX.  Fallback: FRED CSV."""
        if YF_AVAILABLE:
            try:
                raw = yf.download("^VIX", start=start, end=end,
                                  progress=False, auto_adjust=True)
                vix = raw["Close"].rename("vix").to_frame()
                return vix
            except Exception:
                pass

        if REQUESTS_AVAILABLE:
            try:
                resp = requests.get(self.FRED_VIX_URL, timeout=10)
                from io import StringIO
                vix  = pd.read_csv(StringIO(resp.text),
                                   index_col=0, parse_dates=True,
                                   na_values=".").rename(columns={"VIXCLS": "vix"})
                vix  = vix.loc[start:end].dropna()
                return vix
            except Exception as exc:
                logger.error(f"FRED VIX fetch failed: {exc}")

        return None

    # ─── Feature builders ────────────────────────────────────────────────

    @staticmethod
    def _add_hmm_features(df: pd.DataFrame) -> pd.DataFrame:
        """Adds the 7 features expected by VIXRegimeDetector."""
        v = df["vix"]
        df["vix_close"] = v
        df["vix_ma5"]   = v.rolling(5).mean()
        df["vix_ma10"]  = v.rolling(10).mean()
        df["vix_ma20"]  = v.rolling(20).mean()
        df["vix_roc5"]  = v.pct_change(5)
        df["term_slope"] = 1.0   # placeholder (VIX3M not fetched by default)
        t = df.get("tqqq_close", pd.Series(50.0, index=df.index))
        df["tqqq_hv10"] = t.pct_change().rolling(10).std() * np.sqrt(252)
        return df

    @staticmethod
    def _add_predictor_features(df: pd.DataFrame) -> pd.DataFrame:
        """Mirrors VIXEnsemblePredictor.build_xgb_features key fields."""
        v = df["vix"]
        df["vix_lag1"]   = v.shift(1)
        df["vix_lag2"]   = v.shift(2)
        df["vix_roc1"]   = v.pct_change(1)
        df["vix_roc10"]  = v.pct_change(10)
        df["vix_std5"]   = v.rolling(5).std()
        df["vix_zscore"] = (v - v.rolling(60).mean()) / v.rolling(60).std()
        if "tqqq_close" in df.columns:
            t = df["tqqq_close"]
            df["tqqq_ret1"]   = t.pct_change(1)
            df["tqqq_hv20"]   = t.pct_change().rolling(20).std() * np.sqrt(252)
        return df
