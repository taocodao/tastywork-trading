
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import modules to test
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.zebra.zebra_selector import ZebraSelector, ZebraCandidate
from src.zebra.perplexity_enrichment import PerplexityEnricher, NewsSentimentResult

class TestZebraSelector(unittest.TestCase):
    
    def setUp(self):
        self.mock_ib = MagicMock()
        self.selector = ZebraSelector(ib_provider=self.mock_ib)
        
        # Create mock market data
        dates = pd.date_range(end=datetime.now(), periods=50)
        self.mock_hist = pd.DataFrame({
            'Open': np.linspace(100, 110, 50),
            'High': np.linspace(101, 111, 50),
            'Low': np.linspace(99, 109, 50),
            'Close': np.linspace(100, 110, 50),
            'Volume': [1000000] * 50
        }, index=dates)

    def test_fundamental_health(self):
        # Good company
        info = {
            'forwardPE': 20,
            'freeCashflow': 1000000,
            'revenueGrowth': 0.10,
            'debtToEquity': 50,
            'profitMargins': 0.15
        }
        checks = self.selector._check_fundamental_health_detailed(info)
        self.assertTrue(sum(checks.values()) >= 4)
        
        # Bad company
        bad_info = {'forwardPE': 100, 'freeCashflow': -100}
        checks_bad = self.selector._check_fundamental_health_detailed(bad_info)
        self.assertFalse(sum(checks_bad.values()) >= 4)

    def test_dip_detection(self):
        # Using the mock history with a drop
        # Last 5 days drop 10%
        df = self.mock_hist.copy()
        df.iloc[-5:, 3] = df.iloc[-5:, 3] * 0.90
        
        health = {'pe': True} # Dummy
        score, details = self.selector._calculate_dip_score(df, {}, health)
        
        # print(f"Dip Score: {score}, Details: {details}")
        
        self.assertTrue(score > 0, "Dip score should be positive for a 10% drop")
        self.assertTrue(details['drop_pct'] > 5.0)

if __name__ == '__main__':
    unittest.main()
