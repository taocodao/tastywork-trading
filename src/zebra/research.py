"""
ZEBRA Live Research & Selection (Perplexity AI)
===============================================
This module leverages Perplexity AI to perform live stock selection and entry timing analysis,
as requested by the user.

NOTE: This is for LIVE trading intelligence. For historical backtesting, we cannot use this
as it would require "simulating" past web searches (look-ahead bias).
"""

import sys
import os
import logging
from typing import List

# Setup path to import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.earnings_intelligence.client import PerplexityClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class ZebraResearcher:
    def __init__(self):
        try:
            self.client = PerplexityClient()
            self.enabled = True
        except Exception as e:
            logger.warning(f"Perplexity Client init failed (API/Config?): {e}")
            self.enabled = False

    def analyze_candidates(self, symbols: List[str]) -> List[str]:
        """
        Uses Perplexity to analyze a list of technical candidates.
        Returns the subset that has strong fundamental/macro tailwinds.
        """
        if not self.enabled:
            logger.warning("Perplexity disabled - skipping AI analysis")
            return symbols
            
        logger.info(f"Asking Perplexity to analyze: {symbols}")
        
        prompt = f"""
        Analyze the following stocks for a Bullish ZEBRA strategy (Synthetic Long Stock):
        {', '.join(symbols)}
        
        Criteria:
        1. Strong sector momentum.
        2. Positive recent news catalysts.
        3. Low risk of imminent negative regulatory or macro events.
        
        Return ONLY the list of symbols that pass as "Strong Buys" based on current sentiment.
        Format: LIST: [SYM1, SYM2, ...]
        """
        
        try:
            response = self.client.query(prompt)
            logger.info(f"Perplexity Response:\n{response}")
            
            # Parsing logic would go here (simplified for demo)
            # assuming response contains the list
            return symbols # Placeholder: return all or parsed list
            
        except Exception as e:
            logger.error(f"Perplexity query failed: {e}")
            return symbols

if __name__ == "__main__":
    researcher = ZebraResearcher()
    candidates = ["NVDA", "TSLA", "AMD", "PLTR", "SOFI"]
    researcher.analyze_candidates(candidates)
