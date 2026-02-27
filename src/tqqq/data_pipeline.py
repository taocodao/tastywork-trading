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

        # Compute Mean Reversion / Swing Trade features
        df = self._add_mean_reversion_features(df)

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
        right: str = "P",
    ) -> List[Dict[str, Any]]:
        """
        Fetches the live options chain for TQQQ from the IB provider.
        Falls back to an empty list if IB is not connected.

        Args:
            right: "P" for puts (default), "C" for calls.
        """
        if self.ib_provider is None:
            logger.warning("No IB provider — options chain unavailable.")
            return []

        try:
            # Delegates to the existing ib_data_provider infrastructure
            chain = self.ib_provider.get_options_chain(
                symbol=symbol,
                right=right,
                dte_min=dte_min,
                dte_max=dte_max,
            )
            return chain or []
        except Exception as exc:
            logger.error(f"Failed to fetch {right} options chain: {exc}")
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
            
            # Determine format of MultiIndex (if multi-index, we need to extract correctly)
            if isinstance(raw.columns, pd.MultiIndex):
                if "Close" in raw.columns.levels[0]:
                    close = raw["Close"].copy()
                elif "Close" in raw.columns.levels[1]:
                    close = raw.xs("Close", level=1, axis=1).copy()
                else:
                    close = raw["Close"].copy()
            else:
                close = raw["Close"].copy()

            # Save old columns mapping
            close.columns = [f"{s.lower()}_close" for s in symbols]

            if "TQQQ" in symbols and isinstance(raw.columns, pd.MultiIndex):
                try:
                    close["tqqq_open"] = raw["Open"]["TQQQ"]
                    close["tqqq_high"] = raw["High"]["TQQQ"]
                    close["tqqq_low"]  = raw["Low"]["TQQQ"]
                    close["tqqq_volume"] = raw["Volume"]["TQQQ"]
                except KeyError:
                    # Alternate yf format where Ticker is level 0
                    close["tqqq_open"] = raw["TQQQ"]["Open"]
                    close["tqqq_high"] = raw["TQQQ"]["High"]
                    close["tqqq_low"]  = raw["TQQQ"]["Low"]
                    close["tqqq_volume"] = raw["TQQQ"]["Volume"]

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

    @staticmethod
    def _add_mean_reversion_features(df: pd.DataFrame) -> pd.DataFrame:
        """Adds all indicators needed for the hybrid swing diagonal strategy."""
        try:
            import ta
        except ImportError:
            logger.error("The 'ta' library is missing. Run 'pip install ta'")
            return df
            
        c = df.get("tqqq_close")
        if c is None:
            return df
            
        h = df.get("tqqq_high", c)
        l = df.get("tqqq_low", c)
        v = df.get("tqqq_volume", pd.Series(1.0, index=df.index))
        
        # 1. RSI-2
        df["rsi_2"] = ta.momentum.RSIIndicator(c, window=2).rsi()
        
        below_10 = (df["rsi_2"] < 10).astype(int)
        groups = below_10.ne(below_10.shift()).cumsum()
        df["rsi2_consec"] = below_10.groupby(groups).cumsum()
        
        is_oversold = df["rsi_2"] < 10
        days_since = pd.Series(np.nan, index=df.index)
        last_idx = -9999
        for i, val in enumerate(is_oversold):
            if pd.isna(val): continue
            if val: last_idx = i
            days_since.iloc[i] = i - last_idx if last_idx != -9999 else np.nan
        df["days_since_oversold"] = days_since
        
        # 2. Bollinger %B (20, 2)
        df["bb_pct_b"] = ta.volatility.BollingerBands(c, window=20, window_dev=2).bollinger_pband()
        
        # 3. Volume ratio (current / 20-day avg)
        df["vol_ratio"] = v / v.rolling(20).mean()
        
        # 4. MFI-14 and ADX-14
        df["mfi_14"] = ta.volume.MFIIndicator(h, l, c, v, window=14).money_flow_index()
        df["adx_14"] = ta.trend.ADXIndicator(h, l, c, window=14).adx()
        
        # 6. SMAs
        df["sma_200"] = c.rolling(200).mean()
        df["sma_50"] = c.rolling(50).mean()
        df["sma_20"] = c.rolling(20).mean()
        df["sma_10"] = c.rolling(10).mean()
        df["sma_5"] = c.rolling(5).mean()
        
        df["sma20_slope"] = df["sma_20"] - df["sma_20"].shift(5)
        df["sma20_slope_positive"] = (df["sma_20"].diff() > 0).astype(int)
        pos_groups = df["sma20_slope_positive"].ne(df["sma20_slope_positive"].shift()).cumsum()
        df["sma20_slope_positive_days"] = df["sma20_slope_positive"].groupby(pos_groups).cumsum()
        
        # 7. ATR %
        df["atr_pct"] = ta.volatility.AverageTrueRange(h, l, c, window=14).average_true_range() / c
        
        # 8. Rolling Hurst Exponent (100d, 60d) & OU Half-life (60d)
        df["hurst_100"] = TQQQDataPipeline._rolling_hurst(c, window=100)
        df["hurst_60"] = TQQQDataPipeline._rolling_hurst(c, window=60)
        df["ou_half_life"] = TQQQDataPipeline._rolling_ou_halflife(c, window=60)
        
        # 9. VIX features
        v_idx = df.get("vix")
        if v_idx is not None:
            v_sma_50 = v_idx.rolling(50).mean()
            df["vix_sma_ratio"] = v_idx / v_sma_50
            below_sma = (v_idx < v_sma_50).astype(int)
            vix_groups = below_sma.ne(below_sma.shift()).cumsum()
            df["vix_below_sma_consecutive"] = below_sma.groupby(vix_groups).cumsum()
            
        # 10. Drawdown
        rolling_high = c.rolling(252, min_periods=1).max()
        df["drawdown_from_high"] = (c - rolling_high) / rolling_high
        
        return df

    @staticmethod
    def _hurst_exponent(price_series: np.ndarray) -> float:
        log_returns = np.diff(np.log(price_series))
        lags = range(2, min(len(log_returns) // 2 + 1, 100))
        if len(list(lags)) < 3: return 0.5
        rs_values = []
        for lag in lags:
            subseries = [log_returns[i:i+lag] for i in range(0, len(log_returns) - lag, lag) if i+lag <= len(log_returns)]
            rs_per_lag = []
            for sub in subseries:
                if len(sub) < 2: continue
                R = np.max(np.cumsum(sub - np.mean(sub))) - np.min(np.cumsum(sub - np.mean(sub)))
                S = np.std(sub, ddof=1)
                if S > 0: rs_per_lag.append(R / S)
            if rs_per_lag: rs_values.append((np.log(lag), np.log(np.mean(rs_per_lag))))
        if len(rs_values) < 3: return 0.5
        x = np.array([v[0] for v in rs_values])
        y = np.array([v[1] for v in rs_values])
        return np.polyfit(x, y, 1)[0]

    @staticmethod
    def _rolling_hurst(series: pd.Series, window: int = 100) -> pd.Series:
        return series.rolling(window).apply(lambda x: np.nan if np.isnan(x).any() else TQQQDataPipeline._hurst_exponent(x), raw=True)

    @staticmethod
    def _ou_half_life(price_series: np.ndarray) -> float:
        log_prices = np.log(price_series)
        y = np.diff(log_prices)
        x = np.column_stack([log_prices[:-1], np.ones(len(log_prices)-1)])
        try:
            lam = np.linalg.lstsq(x, y, rcond=None)[0][0]
            if lam >= 0: return np.inf
            return -np.log(2) / lam
        except:
            return np.inf

    @staticmethod
    def _rolling_ou_halflife(series: pd.Series, window: int = 60) -> pd.Series:
        return series.rolling(window).apply(lambda x: np.nan if np.isnan(x).any() else TQQQDataPipeline._ou_half_life(x), raw=True)
