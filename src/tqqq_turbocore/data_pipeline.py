import pandas as pd
import yfinance as yf
import numpy as np
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

# Extended ticker set — includes cross-asset regime features
DEFAULT_TICKERS = [
    'QQQ', 'TQQQ', 'SQQQ', 'QLD', 'SGOV',
    '^VIX',    # CBOE VIX (30-day implied vol)
    '^VIX3M',  # CBOE VIX3M (90-day implied vol) — for term structure slope
    '^VXN',    # CBOE Nasdaq-100 Volatility Index — QQQ-specific implied vol
    'HYG',     # iShares High-Yield Bond ETF — credit spread proxy
    'XLK',     # Technology sector ETF — for sector rotation signal
    'XLV',     # Healthcare/Defensive sector ETF — for sector rotation signal
    '^TNX',    # 10-Year Treasury Yield
    '^IRX',    # 13-Week T-Bill Yield (3-month proxy)
    'TLT',     # 20+ Year Treasury — existing
    'DX-Y.NYB' # US Dollar Index — existing
]


class TurboCoreDataPipeline:
    def __init__(self, tickers: List[str] = None):
        self.tickers = tickers if tickers is not None else DEFAULT_TICKERS
        self.data: Dict[str, pd.DataFrame] = {}

    def fetch_data(self, period: str = "10y") -> Dict[str, pd.DataFrame]:
        logger.info(f"Fetching {period} data for {len(self.tickers)} tickers")
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
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

        logger.info(f"Successfully fetched {len(self.data)}/{len(self.tickers)} tickers")
        return self.data

    def fetch_data_range(self, start: str, end: str) -> Dict[str, pd.DataFrame]:
        """Fetch data over an explicit date range (for backtesting)."""
        logger.info(f"Fetching data {start} -> {end} for {len(self.tickers)} tickers")
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
                if df.empty:
                    logger.warning(f"No data fetched for {ticker}")
                    continue

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)

                if 'Close' in df.columns:
                    df = df.dropna(subset=['Close'])
                    self.data[ticker] = df

            except Exception as e:
                logger.error(f"Error fetching {ticker}: {e}")

        return self.data

    def prepare_core_features(self) -> pd.DataFrame:
        """
        Prepares all TurboCore features — Layer 1 (EMA/SMA), Layer 2 (HMM macro),
        and cross-asset regime features for the upgraded 6-feature HMM and
        11-feature XGBoost scorer.

        New features added in v2:
          - vix3m_close, vix_term_slope (VIX/VIX3M ratio)
          - hyg_20d_slope (credit spread proxy)
          - qqq_sma200_zscore (distance from SMA200 as Z-score)
          - qqq_10_50_bull_cross (QQQ dual EMA confirmation gate)
          - tnx_irx_slope (10Y - 3M yield curve slope)
          - xlk_xlv_ratio_20d (sector rotation: tech vs defensive)
          - vxn_close (Nasdaq-100 implied vol)
          - iv_rv_spread (VXN - QQQ realized vol: variance risk premium)
        """
        if 'QQQ' not in self.data or 'TQQQ' not in self.data:
            raise ValueError("QQQ and TQQQ data required for core features")

        qqq_df = self.data['QQQ'].copy()
        tqqq_df = self.data['TQQQ'].copy()

        master = pd.DataFrame(index=qqq_df.index)
        master['qqq_close'] = qqq_df['Close']
        if 'High' in qqq_df.columns:
            master['qqq_high'] = qqq_df['High']
        if 'Low' in qqq_df.columns:
            master['qqq_low'] = qqq_df['Low']
        master['tqqq_close'] = tqqq_df['Close'].reindex(master.index).ffill()
        if 'High' in tqqq_df.columns:
            master['tqqq_high'] = tqqq_df['High'].reindex(master.index).ffill()
        if 'Low' in tqqq_df.columns:
            master['tqqq_low'] = tqqq_df['Low'].reindex(master.index).ffill()

        # ── VIX ──────────────────────────────────────────────────────────────
        if '^VIX' in self.data:
            master['vix_close'] = self.data['^VIX']['Close'].reindex(master.index).ffill()
        else:
            master['vix_close'] = np.nan

        # ── VIX3M (90-day) → term structure slope ────────────────────────────
        if '^VIX3M' in self.data:
            master['vix3m_close'] = self.data['^VIX3M']['Close'].reindex(master.index).ffill()
        else:
            # Proxy: VIX3M ≈ VIX × 1.05 in normal contango
            master['vix3m_close'] = master['vix_close'] * 1.05

        # VIX term slope: >1.0 = backwardation (stress), <1.0 = contango (calm)
        master['vix_term_slope'] = (
            master['vix_close'] / master['vix3m_close'].replace(0, np.nan)
        ).clip(0.5, 2.5)

        # ── HYG credit spread proxy ───────────────────────────────────────────
        if 'HYG' in self.data:
            hyg = self.data['HYG']['Close'].reindex(master.index).ffill()
            master['hyg_20d_slope'] = hyg.pct_change(20)
        else:
            master['hyg_20d_slope'] = 0.0

        # ── Yield curve slope (10Y - 3M) ─────────────────────────────────────
        tnx_available = '^TNX' in self.data
        irx_available = '^IRX' in self.data
        if tnx_available and irx_available:
            tnx = self.data['^TNX']['Close'].reindex(master.index).ffill()
            irx = self.data['^IRX']['Close'].reindex(master.index).ffill()
            master['tnx_irx_slope'] = tnx - irx  # positive = normal, negative = inverted
        elif tnx_available:
            tnx = self.data['^TNX']['Close'].reindex(master.index).ffill()
            master['tnx_irx_slope'] = tnx - 3.0  # rough 3M proxy
        else:
            master['tnx_irx_slope'] = 1.5  # historical average spread

        # ── VXN (Nasdaq-100 implied vol — QQQ-specific) ───────────────────────
        if '^VXN' in self.data:
            master['vxn_close'] = self.data['^VXN']['Close'].reindex(master.index).ffill()
        else:
            # Proxy: VXN historically ≈ VIX × 1.15
            master['vxn_close'] = master['vix_close'] * 1.15

        # ── XLK/XLV sector rotation ratio ────────────────────────────────────
        if 'XLK' in self.data and 'XLV' in self.data:
            xlk = self.data['XLK']['Close'].reindex(master.index).ffill()
            xlv = self.data['XLV']['Close'].reindex(master.index).ffill()
            xlk_xlv = (xlk / xlv.replace(0, np.nan)).ffill()
            master['xlk_xlv_ratio_20d'] = xlk_xlv.pct_change(20)
        else:
            master['xlk_xlv_ratio_20d'] = 0.0

        # ── TQQQ 5/30 EMA crossover (Layer 1 micro signal) ───────────────────
        master['tqqq_ema_5'] = master['tqqq_close'].ewm(span=5, adjust=False).mean()
        master['tqqq_ema_30'] = master['tqqq_close'].ewm(span=30, adjust=False).mean()
        master['tqqq_bull_cross'] = master['tqqq_ema_5'] > master['tqqq_ema_30']

        # ── QQQ SMA200 macro gate (+5%/-3% hysteresis) ───────────────────────
        master['qqq_sma_200'] = master['qqq_close'].rolling(window=200).mean()
        master['qqq_above_sma200_buy'] = master['qqq_close'] > (master['qqq_sma_200'] * 1.05)
        master['qqq_below_sma200_sell'] = master['qqq_close'] < (master['qqq_sma_200'] * 0.97)

        # ── QQQ SMA200 Z-score (regime persistence predictor) ─────────────────
        qqq_dist = master['qqq_close'] - master['qqq_sma_200']
        dist_std = qqq_dist.rolling(252).std()
        master['qqq_sma200_zscore'] = (qqq_dist / dist_std.replace(0, np.nan)).clip(-5, 5)

        # ── QQQ 10/50 EMA dual-confirmation gate ─────────────────────────────
        master['qqq_ema_10'] = master['qqq_close'].ewm(span=10, adjust=False).mean()
        master['qqq_ema_50'] = master['qqq_close'].ewm(span=50, adjust=False).mean()
        master['qqq_10_50_bull_cross'] = master['qqq_ema_10'] > master['qqq_ema_50']

        # ── QQQ realized volatility (Layer 2 HMM feature, existing) ─────────
        master['qqq_log_return'] = np.log(master['qqq_close'] / master['qqq_close'].shift(1))
        master['qqq_vol_20d'] = master['qqq_log_return'].rolling(window=20).std()

        # ── IV-RV spread (variance risk premium) ─────────────────────────────
        # VXN (annualized IV) - QQQ RV (annualized). Positive = options market fears more than realized.
        vxn_annualized = master['vxn_close'] / 100.0
        qqq_rv_annualized = master['qqq_vol_20d'] * np.sqrt(252)
        master['iv_rv_spread'] = vxn_annualized - qqq_rv_annualized

        return master.dropna(subset=['qqq_close', 'tqqq_close', 'vix_close'])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("2y")
    master_df = pipeline.prepare_core_features()
    print(f"\nMaster DataFrame shape: {master_df.shape}")
    print(f"Columns: {list(master_df.columns)}")
    print("\nTail sample:")
    print(master_df[['qqq_close', 'tqqq_close', 'vix_close', 'vix_term_slope',
                      'tnx_irx_slope', 'qqq_sma200_zscore',
                      'qqq_10_50_bull_cross', 'tqqq_bull_cross']].tail())
