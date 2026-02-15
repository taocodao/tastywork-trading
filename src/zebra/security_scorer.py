import pandas as pd
import numpy as np
import logging

try:
    import ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

class ZebraSecurityScorer:
    """
    Multi-factor scoring engine for ZEBRA candidate selection.
    
    Factors:
    1. Trend Strength (25%)
    2. Momentum Quality (20%)
    3. Volatility Context (20%)
    4. Volume Confirmation (15%)
    5. Mean Reversion Risk (10%)
    6. Sector Momentum (10%)
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def score_symbol(self, symbol: str, df: pd.DataFrame) -> dict:
        """
        Compute composite score (0-100).
        """
        if df is None or df.empty:
            return {'symbol': symbol, 'composite_score': 0, 'rationale': 'No Data'}
            
        # Ensure sufficient history
        if len(df) < 200:
            return {'symbol': symbol, 'composite_score': 0, 'rationale': 'Insufficient History (<200d)'}
            
        # Compute Indicators if not present
        df = self._compute_indicators(df.copy())
        
        # Get latest row
        latest = df.iloc[-1]
        
        # 1. Trend Strength (25%)
        trend_score = self._calc_trend_strength(latest)
        
        # 2. Momentum Quality (20%)
        momentum_score = self._calc_momentum_quality(latest)
        
        # 3. Volatility Context (20%)
        vol_score = self._calc_volatility_context(latest)
        
        # 4. Volume Confirmation (15%)
        vol_conf_score = self._calc_volume_confirmation(latest)
        
        # 5. Mean Reversion Risk (10%)
        mr_score = self._calc_mean_reversion_risk(latest)
        
        # 6. Sector Momentum (10%) - Placeholder (requires sector data)
        sector_score = 50 # Neutral default
        
        # Weighted Composite
        composite = (
            trend_score * 0.25 +
            momentum_score * 0.20 +
            vol_score * 0.20 +
            vol_conf_score * 0.15 +
            mr_score * 0.10 +
            sector_score * 0.10
        )
        
        rationale = []
        if trend_score > 70: rationale.append("Strong Trend")
        if momentum_score > 70: rationale.append("Good Momentum")
        if vol_score < 40: rationale.append("Low Volatility")
        if composite > 65: rationale.append("BUY Candidate")
        
        return {
            'symbol': symbol,
            'composite_score': composite,
            'trend_score': trend_score,
            'momentum_score': momentum_score,
            'vol_score': vol_score,
            'volume_score': vol_conf_score,
            'mr_score': mr_score,
            'sector_score': sector_score,
            'rationale': ", ".join(rationale)
        }

    def _compute_indicators(self, df):
        # Use TA library if available for robust indicators
        if HAS_TA:
            # Trend
            df['SMA20'] = ta.trend.sma_indicator(df['Close'], window=20)
            df['SMA50'] = ta.trend.sma_indicator(df['Close'], window=50)
            df['SMA200'] = ta.trend.sma_indicator(df['Close'], window=200)
            df['ADX'] = ta.trend.adx(df['High'], df['Low'], df['Close'], window=14)
            
            # Momentum
            df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
            df['MACD'] = ta.trend.macd_diff(df['Close'])
            
            # Volatility
            df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            df['BB_High'] = ta.volatility.bollinger_hband(df['Close'], window=20, window_dev=2)
            df['BB_Low'] = ta.volatility.bollinger_lband(df['Close'], window=20, window_dev=2)
            df['BB_P'] = ta.volatility.bollinger_pband(df['Close'], window=20, window_dev=2)
            
            # Volume
            df['OBV'] = ta.volume.on_balance_volume(df['Close'], df['Volume'])
            df['VolSMA20'] = ta.trend.sma_indicator(df['Volume'], window=20)
            
        else:
            # Fallback simple pandas implementation
            df['SMA20'] = df['Close'].rolling(window=20).mean()
            df['SMA50'] = df['Close'].rolling(window=50).mean()
            df['SMA200'] = df['Close'].rolling(window=200).mean()
            # Simplified ADX proxy (True Range approx)
            df['TR'] = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
            df['ATR'] = df['TR'].rolling(window=14).mean()
            
            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = df['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = exp1 - exp2
            
            # Bollinger %B
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['STD20'] = df['Close'].rolling(window=20).std()
            df['BB_High'] = df['MA20'] + (df['STD20'] * 2)
            df['BB_Low'] = df['MA20'] - (df['STD20'] * 2)
            df['BB_P'] = (df['Close'] - df['BB_Low']) / (df['BB_High'] - df['BB_Low'])
            
            # Volume
            df['VolSMA20'] = df['Volume'].rolling(window=20).mean()
            
        return df

    def _calc_trend_strength(self, row):
        score = 0
        close = row['Close']
        if close > row.get('SMA20', 0): score += 20
        if row.get('SMA20', 0) > row.get('SMA50', 0): score += 20
        if row.get('SMA50', 0) > row.get('SMA200', 0): score += 20
        if row.get('ADX', 0) > 25: score += 20 # Strong trend
        if row.get('SMA50', 0) > 0: # Slope positive check (simplified)
             pass 
        return min(100, score)

    def _calc_momentum_quality(self, row):
        score = 50 # Base
        rsi = row.get('RSI', 50)
        # Pullback zone: 40-60 is good for entry in trend
        if 40 <= rsi <= 60: score += 30
        elif rsi > 70: score -= 20 # Overbought
        elif rsi < 30: score -= 20 # Oversold (or strong down momentum)
        
        if row.get('MACD', 0) > 0: score += 10
        
        return min(100, max(0, score))

    def _calc_volatility_context(self, row):
        # ATR %
        atr = row.get('ATR', 0)
        close = row['Close']
        if close == 0: return 50
        atr_pct = (atr / close) * 100
        
        # Ideal: 1.5% - 3.5%
        if 1.5 <= atr_pct <= 3.5: return 100
        elif atr_pct < 1.5: return 60 # Low vol
        elif atr_pct > 3.5: return 40 # High vol
        return 50

    def _calc_volume_confirmation(self, row):
        vol = row['Volume']
        if vol > row.get('VolSMA20', vol):
            return 80
        return 50

    def _calc_mean_reversion_risk(self, row):
        # Inverse score: High risk = low score
        bb_p = row.get('BB_P', 0.5)
        
        # %B > 1.0 (Above upper band) -> High risk -> Score 0
        if bb_p > 1.0: return 10
        # %B < 0.0 (Below lower band) -> Oversold -> Score 80 (good entry)
        if bb_p < 0.2: return 80
        
        # Middle range 0.2 - 0.8 -> decent
        return 60
