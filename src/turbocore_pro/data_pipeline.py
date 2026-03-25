import pandas as pd
import yfinance as yf
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# FRED data access (optional — graceful fallback if not installed)
try:
    import pandas_datareader.data as web
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False
    logger.info("pandas_datareader not installed. FRED macro features will be 0.0. "
                "Install with: pip install pandas-datareader")


class TurboCoreDataPipeline:
    def __init__(self, tickers: List[str] = ['QQQ', 'TQQQ', 'SQQQ', 'QLD', 'SGOV', '^VIX', '^VIX3M', 'HYG', 'TLT']):
        self.tickers = tickers
        self.data: Dict[str, pd.DataFrame] = {}
        
    def fetch_data(self, period: str = "10y") -> Dict[str, pd.DataFrame]:
        logger.info(f"Fetching {period} data for {self.tickers}")
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, period=period, progress=False)
                if df.empty:
                    logger.warning(f"No data fetched for {ticker}")
                    continue
                
                # Handle multi-index columns from yfinance >= 0.2.0
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                
                if 'Close' in df.columns:
                    df = df.dropna(subset=['Close'])
                    self.data[ticker] = df
                else:
                    logger.warning(f"No Close price found for {ticker}")
                    
            except Exception as e:
                logger.error(f"Error fetching data for {ticker}: {e}")
                
        return self.data
        
    def fetch_fred_data(self, start: str = '2018-01-01') -> Dict[str, pd.Series]:
        """
        Fetch Phase 2 macro leading indicators from FRED.
        Requires: pip install pandas-datareader

        Returns dict of {series_name: pd.Series} aligned to trading days.
        Falls back gracefully to empty dict if unavailable.
        """
        fred_series = {
            'FEDFUNDS':        'fed_funds',       # Effective Federal Funds Rate (monthly)
            'ISM/MAN_PMI':     'ism_mfg',         # ISM Manufacturing PMI (monthly)
            'ICSA':            'initial_claims',  # Initial Jobless Claims (weekly)
            # ── NEW (2026-03-21): HY OAS — ICE BofA US High Yield Option-Adjusted Spread
            # Perplexity research: "single best macro leading indicator for NASDAQ regime
            # deterioration — widening from ~287bps toward 600bps+ signals regime breakdown
            # with 15–30 day lead time on price."
            # FRED series: https://fred.stlouisfed.org/series/BAMLH0A0HYM2
            'BAMLH0A0HYM2':    'hy_oas',          # HY OAS in basis points (daily, 1997–)
        }
        result = {}
        if not FRED_AVAILABLE:
            return result

        import datetime
        for fred_code, name in fred_series.items():
            try:
                series = web.DataReader(fred_code, 'fred', start=start)
                result[name] = series.iloc[:, 0]
                logger.info(f"Fetched FRED {fred_code} ({len(series)} obs)")
            except Exception as e:
                logger.warning(f"Failed fetching FRED {fred_code}: {e}")

        return result

    def prepare_core_features(self, fetch_fred: bool = True) -> pd.DataFrame:
        """
        Prepares all QQQ/TQQQ base features + Phase 2 macro leading indicators.
        Returns a master dataframe indexed by Date.
        """
        if 'QQQ' not in self.data or 'TQQQ' not in self.data:
            raise ValueError("QQQ and TQQQ data required for core features")

        qqq_df  = self.data['QQQ'].copy()
        tqqq_df = self.data['TQQQ'].copy()

        master = pd.DataFrame(index=qqq_df.index)
        master['qqq_close']  = qqq_df['Close']
        master['qqq_volume'] = qqq_df['Volume']
        master['tqqq_close'] = tqqq_df['Close'].reindex(master.index).ffill()

        if '^VIX' in self.data:
            master['vix_close'] = self.data['^VIX']['Close'].reindex(master.index).ffill()
        else:
            master['vix_close'] = np.nan

        if '^VIX3M' in self.data and '^VIX' in self.data:
            master['vix_3m']  = self.data['^VIX3M']['Close'].reindex(master.index).ffill()
            raw_vts           = (master['vix_3m'] - master['vix_close']) / master['vix_close']
            master['vix_term_slope'] = (
                (raw_vts - raw_vts.rolling(63).mean()) / raw_vts.rolling(63).std()
            ).fillna(0.0)
        else:
            master['vix_term_slope'] = 0.0

        if 'HYG' in self.data:
            master['hyg_close']   = self.data['HYG']['Close'].reindex(master.index).ffill()
            hyg_zscore            = (master['hyg_close'] - master['hyg_close'].rolling(60).mean()) / \
                                    master['hyg_close'].rolling(60).std()
            master['hyg_5d_change'] = hyg_zscore.diff(5).fillna(0.0)
        else:
            master['hyg_5d_change'] = 0.0

        if 'TLT' in self.data:
            master['tlt_close'] = self.data['TLT']['Close'].reindex(master.index).ffill()
        else:
            master['tlt_close'] = np.nan

        # ── Phase 2: FRED Macro Leading Indicators ────────────────────────────
        if fetch_fred:
            start_date = str(master.index.min().date())
            fred_data  = self.fetch_fred_data(start=start_date)
        else:
            fred_data  = {}

        # Fed Funds 3-month change (bps)
        if 'fed_funds' in fred_data:
            ff = fred_data['fed_funds'].reindex(master.index).ffill()
            master['fed_funds_3m_change'] = ff.diff(63).fillna(0.0)
        else:
            master['fed_funds_3m_change'] = 0.0

        # ISM Manufacturing delta (month-over-month)
        if 'ism_mfg' in fred_data:
            ism = fred_data['ism_mfg'].reindex(master.index, method='ffill')
            master['ism_mfg_delta'] = ism.diff(21).fillna(0.0)
        else:
            master['ism_mfg_delta'] = 0.0

        # Initial Claims 4-week slope (regression slope of log claims)
        if 'initial_claims' in fred_data:
            ic  = np.log(fred_data['initial_claims'].reindex(master.index).ffill().replace(0, np.nan))
            master['initial_claims_slope'] = ic.diff(21).fillna(0.0)
        else:
            master['initial_claims_slope'] = 0.0

        # ── HY OAS (ICE BofA — BAMLH0A0HYM2) ────────────────────────────────
        # Perplexity research 2026-03-21: "The single best macro leading indicator
        # for NASDAQ-100 regime deterioration. Spreads widening from ~287bps toward
        # 600bps+ signal regime breakdown 15–30 days before price."
        # Stored as 60-day z-score so XGBoost sees regime-relative stress, not absolute level.
        # Positive z-score = spreads wider than normal (risk-off signal).
        # Negative z-score = spreads tighter than normal (risk-on, confirms bull regime).
        if 'hy_oas' in fred_data:
            hy_oas_raw = fred_data['hy_oas'].reindex(master.index).ffill()
            hy_oas_mu  = hy_oas_raw.rolling(60).mean()
            hy_oas_std = hy_oas_raw.rolling(60).std().replace(0, np.nan)
            master['hy_oas_zscore']    = ((hy_oas_raw - hy_oas_mu) / hy_oas_std).fillna(0.0)
            # Also store 5-day change in z-score to capture acceleration (rapid widening = urgent risk)
            master['hy_oas_5d_change'] = master['hy_oas_zscore'].diff(5).fillna(0.0)
            logger.info(f"HY OAS loaded: last value = {hy_oas_raw.iloc[-1]:.1f}bps, "
                        f"z-score = {master['hy_oas_zscore'].iloc[-1]:.2f}")
        else:
            # Graceful fallback: use HYG price change as proxy (already computed above)
            master['hy_oas_zscore']    = -master.get('hyg_5d_change', pd.Series(0.0, index=master.index))  # inverted: HYG up = OAS down
            master['hy_oas_5d_change'] = 0.0
            logger.info("HY OAS fallback: using inverted HYG z-score as proxy")

        # ── IV Rank approximation (HV-based proxy) ────────────────────────────
        log_ret       = np.log(master['qqq_close'] / master['qqq_close'].shift(1))
        hv30          = log_ret.rolling(30).std() * np.sqrt(252) * 100
        hv_min_52w    = hv30.rolling(252).min()
        hv_max_52w    = hv30.rolling(252).max()
        denom         = (hv_max_52w - hv_min_52w).replace(0, np.nan)
        master['iv_rank_approx'] = ((hv30 - hv_min_52w) / denom * 100).fillna(50.0).clip(0, 100)

        # ── Core strategy signals ─────────────────────────────────────────────
        master['tqqq_ema_5']  = master['tqqq_close'].ewm(span=5,  adjust=False).mean()
        master['tqqq_ema_30'] = master['tqqq_close'].ewm(span=30, adjust=False).mean()
        master['qqq_sma_200'] = master['qqq_close'].rolling(window=200).mean()

        master['tqqq_bull_cross']       = master['tqqq_ema_5'] > master['tqqq_ema_30']
        master['qqq_above_sma200_buy']  = master['qqq_close'] > (master['qqq_sma_200'] * 1.05)
        master['qqq_below_sma200_sell'] = master['qqq_close'] < (master['qqq_sma_200'] * 0.97)

        # Distance from SMA200 (positive = above, negative = below)
        master['qqq_sma200_pct'] = (
            (master['qqq_close'] - master['qqq_sma_200']) / master['qqq_sma_200']
        ).fillna(0.0)

        # Regime detection features
        master['qqq_log_return'] = np.log(master['qqq_close'] / master['qqq_close'].shift(1))
        master['qqq_vol_20d']    = master['qqq_log_return'].rolling(window=20).std()

        # ATH Drawdown
        master['qqq_ath']         = master['qqq_close'].cummax()
        master['qqq_drawdown_ath'] = (master['qqq_close'] - master['qqq_ath']) / master['qqq_ath']

        return master.dropna()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("2y")
    master_df = pipeline.prepare_core_features()
    print("Master DataFrame tail:")
    print(master_df[['qqq_close', 'tqqq_close', 'vix_close', 'tqqq_ema_5', 'tqqq_ema_30', 'qqq_sma_200', 'tqqq_bull_cross']].tail())
