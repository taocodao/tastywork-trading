
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
from datetime import datetime, date, timedelta

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.dvo.gravity_engine import GravityEngine, ValuationResult
from src.dvo.risk_guardian import RiskGuardian
from src.dvo.trade_constructor import TradeConstructor
from src.dvo.position_monitor import DVOPositionMonitor
from models.dvo_position import DVOPosition

# Synchronous Tests
class TestDVOCore(unittest.TestCase):

    # --- RiskGuardian Tests ---
    def test_risk_guardian_profiles(self):
        guardian_low = RiskGuardian("LOW")
        guardian_high = RiskGuardian("HIGH")
        
        # Correct values from risk_guardian.py
        self.assertEqual(guardian_low.profile.max_portfolio_leverage, 0.20)
        self.assertEqual(guardian_high.profile.max_portfolio_leverage, 0.50)
        
    def test_risk_guardian_check_entry(self):
        guardian = RiskGuardian("MEDIUM") # Max leverage 0.35, Max pos 5, Min MoS 0.20
        
        # Should pass
        allowed, reason = guardian.check_entry(
            current_leverage=0.1, 
            current_positions=2,
            margin_of_safety=0.25,
            current_vix=20
        )
        self.assertTrue(allowed, f"Failed: {reason}")
        
        # Fail on VIX
        allowed, reason = guardian.check_entry(
            current_leverage=0.1,
            current_positions=2,
            margin_of_safety=0.25,
            current_vix=50 # > 40 (Medium VIX kill switch)
        )
        self.assertFalse(allowed)
        self.assertIn("VIX", reason)
        
        # Fail on MoS
        allowed, reason = guardian.check_entry(
            current_leverage=0.1,
            current_positions=2,
            margin_of_safety=0.10, # < 0.20
            current_vix=20
        )
        self.assertFalse(allowed)
        self.assertIn("MoS", reason)

    # --- TradeConstructor Tests ---
    def test_trade_constructor_short_put(self):
        constructor = TradeConstructor("MEDIUM")
        
        # Mock Option Chain
        today = datetime.now()
        exp_date = today + timedelta(days=400)
        exp_str = exp_date.strftime('%Y-%m-%d')
        
        mock_chain = {
            exp_str: {
                'strikes': {
                    80.0: {'put': {'mid': 5.0, 'delta': -0.20}}, # Delta -0.20 OK
                    90.0: {'put': {'mid': 8.0, 'delta': -0.30}}, # Delta -0.30 OK
                    100.0: {'put': {'mid': 12.0, 'delta': -0.45}}
                }
            }
        }
        
        # Scenario: Fair Value 120, Current Price 100
        # Risk profile "MEDIUM": Min MoS 0.20.
        # Max acceptable strike = Fair Value * (1 - 0.20) = 120 * 0.8 = 96.0.
        # Also cap at current price * 0.95 = 95.0 (buffer).
        # So look for strikes <= 95.0. 
        # Available: 80, 90. 100 is > 95.
        # Prefer higher premium/closer to target? 
        # Usually we want closest to target strike without exceeding.
        # 90.0 is closest to 95.0.
        
        trade = constructor.find_short_put_candidate(
            chain=mock_chain,
            fair_value=120.0,
            current_price=100.0,
            min_dte=300
        )
        
        self.assertIsNotNone(trade)
        self.assertEqual(trade.structure_type, "SHORT_PUT")
        self.assertEqual(trade.strike, 90.0)
        self.assertEqual(trade.expiration, exp_str)

    # --- GravityEngine Tests ---
    @patch('src.dvo.gravity_engine.yf.Ticker')
    @patch('src.dvo.gravity_engine.requests.post')
    def test_gravity_engine_analyze(self, mock_post, mock_ticker):
        import pandas as pd
        df = pd.DataFrame({'Close': [100.0]})
        mock_ticker.return_value.history.return_value = df
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"fair_value": 120.0, "confidence": 0.9}'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        engine = GravityEngine()
        engine._save_signal = MagicMock()
        
        result = engine.analyze("AAPL")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.current_price, 100.0)
        self.assertEqual(result.fair_value_price, 120.0)
        # 1/6 = 0.16666...
        self.assertAlmostEqual(result.margin_of_safety_pct, 0.1666, places=3) 


# Asynchronous Tests
class TestDVOAsync(unittest.IsolatedAsyncioTestCase): # Python 3.8+

    # --- PositionMonitor Tests ---
    async def test_position_monitor_logic(self):
        monitor = DVOPositionMonitor(MagicMock(), MagicMock())
        monitor._signal_exit = AsyncMock() 
        monitor.gravity.analyze = MagicMock(return_value=ValuationResult(
             symbol="TEST", analysis_date=date.today(), current_price=100,
             fair_value_price=100, margin_of_safety_pct=0, 
             trailing_eps=1, forward_eps=1, hist_growth_rate=0, regime_tag="FAIR", confidence_score=0.9
        )) 
 
        # Case 1: Velocity Exit (50% profit, >180 DTE)
        pos = DVOPosition(
            symbol="TEST",
            strategy_type="SHORT_PUT",
            entry_price=10.0,
            fair_value_at_entry=100.0,
            status="OPEN"
        )
        
        # Current price 4.0 -> 60% profit
        # DTE 200
        await monitor._check_short_put_exit(pos, 100.0, 4.0, 200)
        
        monitor._signal_exit.assert_called_with(pos, "VELOCITY_EXIT_50PCT")


if __name__ == "__main__":
    unittest.main()
