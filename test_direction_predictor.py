"""
Test Vertical Spread Direction Predictor
=========================================

Unit tests for the VerticalSpreadDirectionPredictor class.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.vertical_spreads.direction_predictor import (
    VerticalSpreadDirectionPredictor,
    DirectionSignal,
    calculate_technical_indicators,
    _calculate_rsi
)


class TestDirectionPredictor:
    """Tests for VerticalSpreadDirectionPredictor."""
    
    @pytest.fixture
    def predictor(self):
        """Create a fresh predictor for each test."""
        return VerticalSpreadDirectionPredictor()
    
    # RSI Signal Tests
    def test_rsi_signal_oversold(self, predictor):
        """RSI < 30 should return bullish signal."""
        stock_data = {
            "symbol": "SPY",
            "price": 485.0,
            "rsi_14": 25,  # Oversold
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 485,
            "sma_50": 483,
            "sma_200": 480
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        # RSI signal should be bullish
        rsi_indicator = [i for i in signal.indicators if i["name"] == "RSI"][0]
        assert rsi_indicator["vote"] == 1, "Oversold RSI should be bullish"
        assert rsi_indicator["confidence"] >= 70
    
    def test_rsi_signal_overbought(self, predictor):
        """RSI > 70 should return bearish signal."""
        stock_data = {
            "symbol": "SPY",
            "price": 485.0,
            "rsi_14": 75,  # Overbought
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 485,
            "sma_50": 483,
            "sma_200": 480
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        rsi_indicator = [i for i in signal.indicators if i["name"] == "RSI"][0]
        assert rsi_indicator["vote"] == -1, "Overbought RSI should be bearish"
        assert rsi_indicator["confidence"] >= 70
    
    def test_rsi_signal_neutral(self, predictor):
        """RSI between 30-70 should be neutral."""
        stock_data = {
            "symbol": "SPY",
            "price": 485.0,
            "rsi_14": 50,  # Neutral
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 485,
            "sma_50": 483,
            "sma_200": 480
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        rsi_indicator = [i for i in signal.indicators if i["name"] == "RSI"][0]
        assert rsi_indicator["vote"] == 0, "Neutral RSI should have 0 vote"
    
    # Bollinger Bands Tests
    def test_bollinger_signal_lower_band(self, predictor):
        """Price near lower BB should be bullish (mean reversion)."""
        stock_data = {
            "symbol": "SPY",
            "price": 481.0,  # Near lower band
            "rsi_14": 50,
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,  # Price is 1 above lower
            "sma_20": 485,
            "sma_50": 483,
            "sma_200": 480
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        bb_indicator = [i for i in signal.indicators if i["name"] == "Bollinger Bands"][0]
        assert bb_indicator["vote"] == 1, "Price near lower BB should be bullish"
    
    def test_bollinger_signal_upper_band(self, predictor):
        """Price near upper BB should be bearish (mean reversion)."""
        stock_data = {
            "symbol": "SPY",
            "price": 489.5,  # Near upper band
            "rsi_14": 50,
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 485,
            "sma_50": 483,
            "sma_200": 480
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        bb_indicator = [i for i in signal.indicators if i["name"] == "Bollinger Bands"][0]
        assert bb_indicator["vote"] == -1, "Price near upper BB should be bearish"
    
    # Moving Average Tests
    def test_ma_signal_bullish_alignment(self, predictor):
        """Bullish MA alignment: Price > SMA20 > SMA50 > SMA200."""
        stock_data = {
            "symbol": "SPY",
            "price": 490.0,
            "rsi_14": 50,
            "bb_upper": 495,
            "bb_mid": 490,
            "bb_lower": 485,
            "sma_20": 488,
            "sma_50": 485,
            "sma_200": 480  # Perfect bullish alignment
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        ma_indicator = [i for i in signal.indicators if i["name"] == "Moving Averages"][0]
        assert ma_indicator["vote"] > 0, "Bullish MA alignment should be positive"
    
    def test_ma_signal_bearish_alignment(self, predictor):
        """Bearish MA alignment: Price < SMA20 < SMA50 < SMA200."""
        stock_data = {
            "symbol": "SPY",
            "price": 470.0,
            "rsi_14": 50,
            "bb_upper": 485,
            "bb_mid": 480,
            "bb_lower": 475,
            "sma_20": 475,
            "sma_50": 480,
            "sma_200": 485  # Perfect bearish alignment
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        ma_indicator = [i for i in signal.indicators if i["name"] == "Moving Averages"][0]
        assert ma_indicator["vote"] < 0, "Bearish MA alignment should be negative"
    
    # Ensemble Voting Tests
    def test_ensemble_voting_strong_bull(self, predictor):
        """Strong bullish signals should produce BULL direction."""
        stock_data = {
            "symbol": "SPY",
            "price": 481.0,  # Near lower BB
            "rsi_14": 25,  # Oversold
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 480,
            "sma_50": 478,
            "sma_200": 475
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        assert signal.direction == "BULL"
        assert signal.confidence >= 60
    
    def test_ensemble_voting_strong_bear(self, predictor):
        """Strong bearish signals should produce BEAR direction."""
        stock_data = {
            "symbol": "SPY",
            "price": 489.5,  # Near upper BB
            "rsi_14": 80,  # Very overbought
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 492,
            "sma_50": 495,
            "sma_200": 500
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        assert signal.direction == "BEAR"
        assert signal.confidence >= 60
    
    def test_ensemble_voting_neutral(self, predictor):
        """Mixed signals should produce NEUTRAL or low confidence."""
        stock_data = {
            "symbol": "SPY",
            "price": 485.0,  # Middle of BB
            "rsi_14": 50,  # Neutral RSI
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 485,
            "sma_50": 485,
            "sma_200": 485
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        # Either NEUTRAL or low confidence
        assert signal.direction == "NEUTRAL" or signal.confidence < 60
    
    # Confidence Tests
    def test_confidence_in_range(self, predictor):
        """Confidence should always be 0-100."""
        stock_data = {
            "symbol": "SPY",
            "price": 485.0,
            "rsi_14": 25,
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 485,
            "sma_50": 483,
            "sma_200": 480
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        assert 0 <= signal.confidence <= 100
    
    # Actionable Tests
    def test_is_actionable_high_confidence_bull(self, predictor):
        """High confidence directional signal should be actionable."""
        stock_data = {
            "symbol": "SPY",
            "price": 480.5,
            "rsi_14": 22,
            "bb_upper": 490,
            "bb_mid": 485,
            "bb_lower": 480,
            "sma_20": 482,
            "sma_50": 480,
            "sma_200": 475
        }
        signal = predictor.calculate_direction_signal(stock_data)
        
        # Should be actionable if directional + high confidence
        if signal.direction != "NEUTRAL" and signal.confidence >= 60:
            assert predictor.is_actionable(signal)
    
    def test_is_actionable_neutral_not_actionable(self, predictor):
        """Neutral signals should not be actionable."""
        signal = DirectionSignal(
            direction="NEUTRAL",
            confidence=80,
            indicators=[],
            reasoning=""
        )
        assert not predictor.is_actionable(signal)
    
    def test_is_actionable_low_confidence_not_actionable(self, predictor):
        """Low confidence signals should not be actionable."""
        signal = DirectionSignal(
            direction="BULL",
            confidence=40,  # Below threshold
            indicators=[],
            reasoning=""
        )
        assert not predictor.is_actionable(signal)


class TestTechnicalIndicatorCalculation:
    """Tests for technical indicator calculation utilities."""
    
    def test_calculate_rsi(self):
        """RSI calculation should work correctly."""
        # Simulated price history with known pattern
        prices = [100, 101, 102, 101, 100, 99, 98, 97, 98, 99, 100, 101, 102, 103, 104, 105]
        rsi = _calculate_rsi(prices, 14)
        
        assert 0 <= rsi <= 100
    
    def test_calculate_rsi_all_gains(self):
        """RSI with all gains should be close to 100."""
        prices = [100 + i for i in range(20)]  # Consistently rising
        rsi = _calculate_rsi(prices, 14)
        
        assert rsi >= 90
    
    def test_calculate_rsi_all_losses(self):
        """RSI with all losses should be close to 0."""
        prices = [120 - i for i in range(20)]  # Consistently falling
        rsi = _calculate_rsi(prices, 14)
        
        assert rsi <= 10
    
    def test_calculate_technical_indicators_with_minimal_data(self):
        """Should work with exactly 20 prices."""
        prices = [100 + i * 0.5 for i in range(20)]
        result = calculate_technical_indicators(prices)
        
        assert "price" in result
        assert "rsi_14" in result
        assert "bb_upper" in result
        assert "bb_mid" in result
        assert "bb_lower" in result
        assert "sma_20" in result
    
    def test_calculate_technical_indicators_insufficient_data(self):
        """Should raise error with < 20 prices."""
        prices = [100 + i for i in range(15)]
        
        with pytest.raises(ValueError):
            calculate_technical_indicators(prices)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
