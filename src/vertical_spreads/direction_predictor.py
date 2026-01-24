"""
Vertical Spread Direction Predictor
====================================

ML-based direction prediction using ensemble voting of technical indicators.
Combines RSI, Bollinger Bands, and Moving Averages to predict directional bias.
"""

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DirectionSignal:
    """Output from direction prediction."""
    direction: str  # "BULL", "BEAR", or "NEUTRAL"
    confidence: int  # 0-100
    indicators: List[Dict]
    reasoning: str


class VerticalSpreadDirectionPredictor:
    """
    Predicts directional bias for vertical spreads using ensemble voting.
    
    Combines multiple technical indicators:
    - RSI mean reversion signals
    - Bollinger Bands position
    - Moving average crossovers
    
    Returns direction (BULL/BEAR/NEUTRAL) with confidence score (0-100).
    """
    
    def __init__(
        self,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70,
        bb_extreme_threshold: float = 0.1,  # Within 10% of band edges
        min_confidence_threshold: int = 60
    ):
        """
        Initialize predictor.
        
        Args:
            rsi_oversold: RSI level considered oversold (bullish signal)
            rsi_overbought: RSI level considered overbought (bearish signal)
            bb_extreme_threshold: Distance from band edge to trigger signal
            min_confidence_threshold: Minimum confidence for actionable signal
        """
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_extreme_threshold = bb_extreme_threshold
        self.min_confidence_threshold = min_confidence_threshold
    
    def calculate_direction_signal(self, stock_data: Dict) -> DirectionSignal:
        """
        Calculate directional signal from stock data.
        
        Args:
            stock_data: Dictionary with keys:
                - symbol: Stock symbol (str)
                - price: Current price (float)
                - rsi_14: 14-period RSI (float)
                - bb_upper: Bollinger Band upper (float)
                - bb_mid: Bollinger Band middle/SMA20 (float)
                - bb_lower: Bollinger Band lower (float)
                - sma_20: 20-day SMA (float)
                - sma_50: 50-day SMA (float)
                - sma_200: 200-day SMA (float, optional)
                - atr_14: 14-period ATR (float, optional)
        
        Returns:
            DirectionSignal with direction, confidence, indicators, and reasoning
        """
        signals = []
        
        # Signal 1: RSI Mean Reversion
        rsi = stock_data.get("rsi_14", 50)
        rsi_vote, rsi_conf = self._rsi_signal(rsi)
        signals.append({
            "name": "RSI",
            "vote": rsi_vote,
            "confidence": rsi_conf,
            "value": rsi
        })
        
        # Signal 2: Bollinger Bands
        price = stock_data.get("price", 0)
        bb_upper = stock_data.get("bb_upper", price * 1.02)
        bb_mid = stock_data.get("bb_mid", price)
        bb_lower = stock_data.get("bb_lower", price * 0.98)
        
        bb_vote, bb_conf = self._bollinger_signal(price, bb_upper, bb_mid, bb_lower)
        signals.append({
            "name": "Bollinger Bands",
            "vote": bb_vote,
            "confidence": bb_conf,
            "value": self._bb_position(price, bb_upper, bb_lower)
        })
        
        # Signal 3: Moving Averages
        sma_20 = stock_data.get("sma_20", price)
        sma_50 = stock_data.get("sma_50", price)
        sma_200 = stock_data.get("sma_200", sma_50)
        
        ma_vote, ma_conf = self._ma_signal(price, sma_20, sma_50, sma_200)
        signals.append({
            "name": "Moving Averages",
            "vote": ma_vote,
            "confidence": ma_conf,
            "value": f"Price vs SMA20: {((price/sma_20)-1)*100:.1f}%"
        })
        
        # Signal 4: Volatility context (informational, doesn't vote)
        atr = stock_data.get("atr_14", 0)
        if atr > 0 and price > 0:
            vol_pct = (atr / price) * 100
            signals.append({
                "name": "Volatility (ATR)",
                "vote": 0,  # Neutral - doesn't affect direction
                "confidence": 50,
                "value": f"{vol_pct:.1f}%"
            })
        
        # Ensemble Vote
        direction, confidence = self._ensemble_vote(signals)
        reasoning = self._explain_decision(signals, direction, stock_data.get("symbol", ""))
        
        return DirectionSignal(
            direction=direction,
            confidence=confidence,
            indicators=signals,
            reasoning=reasoning
        )
    
    def _rsi_signal(self, rsi: float) -> Tuple[float, int]:
        """
        RSI mean reversion signal.
        
        Returns:
            Tuple of (vote, confidence) where vote is:
            - 1 = BULL (oversold, expect bounce)
            - 0 = NEUTRAL
            - -1 = BEAR (overbought, expect pullback)
        """
        if rsi < 20:
            return (1, 85)  # Very oversold - strong bull
        elif rsi < self.rsi_oversold:
            return (1, 70)  # Oversold - moderate bull
        elif rsi > 80:
            return (-1, 85)  # Very overbought - strong bear
        elif rsi > self.rsi_overbought:
            return (-1, 70)  # Overbought - moderate bear
        else:
            return (0, 40)  # Neutral zone
    
    def _bollinger_signal(
        self, 
        price: float, 
        bb_upper: float, 
        bb_mid: float, 
        bb_lower: float
    ) -> Tuple[float, int]:
        """
        Bollinger Band mean reversion signal.
        
        Returns:
            Tuple of (vote, confidence)
        """
        if bb_upper == bb_lower:
            return (0, 30)  # No valid bands
        
        position = self._bb_position(price, bb_upper, bb_lower)
        
        # Near upper band - bearish (expect mean reversion down)
        if position > (1 - self.bb_extreme_threshold):
            confidence = int(70 + (position - 0.9) * 200)  # 70-90 range
            return (-1, min(90, max(70, confidence)))
        
        # Near lower band - bullish (expect mean reversion up)
        elif position < self.bb_extreme_threshold:
            confidence = int(70 + (0.1 - position) * 200)  # 70-90 range
            return (1, min(90, max(70, confidence)))
        
        # Middle zone - neutral
        else:
            return (0, 40)
    
    def _bb_position(self, price: float, bb_upper: float, bb_lower: float) -> float:
        """Calculate position within Bollinger Bands (0 = lower, 1 = upper)."""
        if bb_upper == bb_lower:
            return 0.5
        return (price - bb_lower) / (bb_upper - bb_lower)
    
    def _ma_signal(
        self, 
        price: float, 
        sma_20: float, 
        sma_50: float, 
        sma_200: float
    ) -> Tuple[float, int]:
        """
        Moving average trend signal.
        
        Returns:
            Tuple of (vote, confidence)
        """
        # All MAs aligned bullish: Price > SMA20 > SMA50 > SMA200
        if price > sma_20 > sma_50 > sma_200:
            return (1, 75)
        
        # All MAs aligned bearish: Price < SMA20 < SMA50 < SMA200
        elif price < sma_20 < sma_50 < sma_200:
            return (-1, 75)
        
        # Short-term bullish (20 > 50)
        elif sma_20 > sma_50:
            # Calculate strength based on distance
            pct_above = ((price / sma_20) - 1) * 100
            if pct_above > 2:
                return (0.5, 60)  # Mild bullish with good distance
            return (0.3, 50)  # Weak bullish
        
        # Short-term bearish (20 < 50)
        elif sma_20 < sma_50:
            pct_below = ((sma_20 / price) - 1) * 100
            if pct_below > 2:
                return (-0.5, 60)  # Mild bearish with good distance
            return (-0.3, 50)  # Weak bearish
        
        else:
            return (0, 40)  # Neutral
    
    def _ensemble_vote(self, signals: List[Dict]) -> Tuple[str, int]:
        """
        Combine all signals using weighted voting.
        
        Returns:
            Tuple of (direction, confidence)
        """
        total_weight = 0
        total_vote = 0
        
        for signal in signals:
            weight = signal.get("confidence", 50)
            vote = signal.get("vote", 0)
            
            total_weight += weight
            total_vote += vote * weight
        
        if total_weight == 0:
            return ("NEUTRAL", 0)
        
        avg_vote = total_vote / total_weight
        
        # Map average vote to direction
        if avg_vote > 0.3:
            direction = "BULL"
        elif avg_vote < -0.3:
            direction = "BEAR"
        else:
            direction = "NEUTRAL"
        
        # Confidence is based on vote magnitude
        confidence = int(min(100, abs(avg_vote) * 100 + 30))
        
        return (direction, confidence)
    
    def _explain_decision(
        self, 
        signals: List[Dict], 
        direction: str,
        symbol: str
    ) -> str:
        """Generate human-readable explanation of the decision."""
        bullish = [s for s in signals if s.get("vote", 0) > 0]
        bearish = [s for s in signals if s.get("vote", 0) < 0]
        
        explanation = f"{symbol} Direction: {direction}\n"
        
        if bullish:
            explanation += f"Bullish signals ({len(bullish)}): "
            explanation += ", ".join([f"{s['name']} ({s['value']})" for s in bullish])
            explanation += "\n"
        
        if bearish:
            explanation += f"Bearish signals ({len(bearish)}): "
            explanation += ", ".join([f"{s['name']} ({s['value']})" for s in bearish])
            explanation += "\n"
        
        neutral = [s for s in signals if s.get("vote", 0) == 0]
        if neutral:
            explanation += f"Neutral: " + ", ".join([s['name'] for s in neutral])
        
        return explanation.strip()
    
    def is_actionable(self, signal: DirectionSignal) -> bool:
        """Check if signal has sufficient confidence for trading."""
        return (
            signal.direction != "NEUTRAL" and 
            signal.confidence >= self.min_confidence_threshold
        )


def calculate_technical_indicators(
    prices: List[float],
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None
) -> Dict:
    """
    Calculate technical indicators from price history.
    
    Args:
        prices: List of closing prices (most recent last)
        highs: List of high prices (optional, for ATR)
        lows: List of low prices (optional, for ATR)
    
    Returns:
        Dictionary with RSI, Bollinger Bands, SMAs, and ATR
    """
    if len(prices) < 20:
        raise ValueError("Need at least 20 prices for indicator calculation")
    
    current_price = prices[-1]
    
    # SMA calculations
    sma_20 = sum(prices[-20:]) / 20
    sma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else sma_20
    sma_200 = sum(prices[-200:]) / 200 if len(prices) >= 200 else sma_50
    
    # Bollinger Bands (20-period, 2 std dev)
    bb_prices = prices[-20:]
    bb_mean = sum(bb_prices) / 20
    bb_std = math.sqrt(sum((p - bb_mean) ** 2 for p in bb_prices) / 20)
    bb_upper = bb_mean + (2 * bb_std)
    bb_lower = bb_mean - (2 * bb_std)
    
    # RSI (14-period)
    rsi = _calculate_rsi(prices, 14)
    
    # ATR (14-period) - if high/low data available
    atr = 0
    if highs and lows and len(highs) >= 14:
        atr = _calculate_atr(highs, lows, prices, 14)
    
    return {
        "price": current_price,
        "rsi_14": rsi,
        "bb_upper": bb_upper,
        "bb_mid": bb_mean,
        "bb_lower": bb_lower,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "atr_14": atr
    }


def _calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI from price history."""
    if len(prices) < period + 1:
        return 50  # Default neutral
    
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent_changes = changes[-(period):]
    
    gains = [c if c > 0 else 0 for c in recent_changes]
    losses = [-c if c < 0 else 0 for c in recent_changes]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def _calculate_atr(
    highs: List[float], 
    lows: List[float], 
    closes: List[float], 
    period: int = 14
) -> float:
    """Calculate Average True Range."""
    if len(highs) < period + 1:
        return 0
    
    true_ranges = []
    for i in range(1, len(highs)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i-1])
        tr3 = abs(lows[i] - closes[i-1])
        true_ranges.append(max(tr1, tr2, tr3))
    
    return sum(true_ranges[-period:]) / period
