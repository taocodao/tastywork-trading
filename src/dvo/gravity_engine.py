
"""
Gravity Engine (Valuation Model)
================================
Calculates the 'Intrinsic Value' (EPS Gravity Line) for symbols using fundamental data.
Uses Perplexity API for unstructured financial data (EPS, Estimates) and yfinance for price.
"""

import logging
import yfinance as yf
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional, Dict

# Import existing Perplexity client pattern if available, or use requests
import requests
import os
import json

from ..earnings_intelligence.database import get_db
from models.valuation_signal import ValuationSignal

logger = logging.getLogger(__name__)

@dataclass
class ValuationResult:
    symbol: str
    current_price: float
    fair_value_price: float          # "EPS Gravity Line"
    margin_of_safety_pct: float      # (fair_value - price) / fair_value
    trailing_eps: float
    forward_eps: float
    hist_growth_rate: float
    regime_tag: str                  # UNDERVALUED | FAIR | OVERVALUED | BUBBLE
    confidence_score: float          # 0.0 - 1.0
    analysis_date: date

class GravityEngine:
    def __init__(self):
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.perplexity.ai/chat/completions"

    def analyze(self, symbol: str) -> Optional[ValuationResult]:
        """
        Full analysis pipeline:
        1. Get current price (yfinance)
        2. Get fundamentals (Perplexity)
        3. Compute Fair Value
        4. Save to DB
        """
        try:
            # 1. Price Data
            ticker = yf.Ticker(symbol)
            todays_data = ticker.history(period='1d')
            if todays_data.empty:
                logger.error(f"No price data for {symbol}")
                return None
            current_price = todays_data['Close'].iloc[-1]
            
            # 2. Fundamental Data (Prompting Perplexity)
            fundamentals = self._fetch_fundamentals(symbol, current_price)
            if not fundamentals:
                return None
            
            # 3. Compute Metrics
            fair_value = fundamentals.get('fair_value', current_price)
            margin_of_safety = (fair_value - current_price) / fair_value if fair_value > 0 else 0
            
            # Determine Regime
            if margin_of_safety >= 0.20:
                regime = "UNDERVALUED"
            elif margin_of_safety <= -0.20:
                regime = "BUBBLE"
            elif margin_of_safety <= -0.10:
                regime = "OVERVALUED"
            else:
                regime = "FAIR"
                
            result = ValuationResult(
                symbol=symbol,
                current_price=current_price,
                fair_value_price=fair_value,
                margin_of_safety_pct=margin_of_safety,
                trailing_eps=fundamentals.get('trailing_eps', 0),
                forward_eps=fundamentals.get('forward_eps', 0),
                hist_growth_rate=fundamentals.get('cagr', 0),
                regime_tag=regime,
                confidence_score=fundamentals.get('confidence', 0.5),
                analysis_date=datetime.utcnow().date()
            )
            
            # 4. Save to DB
            self._save_signal(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Gravity analysis failed for {symbol}: {e}")
            return None

    def _fetch_fundamentals(self, symbol: str, price: float) -> Optional[Dict]:
        """
        Query Perplexity for EPS data and Fair Value estimate.
        """
        prompt = f"""
        Analyze the valuation of {symbol} (Current Price: ${price:.2f}).
        
        1. Find Trailing 12M EPS and Forward 12M EPS estimate.
        2. Find historical 5Y EPS CAGR.
        3. Determine a fair P/E multiple based on historical average and sector peers.
        4. Calculate 'Fair Value' = Forward EPS * Fair P/E.
        
        Return JSON ONLY with keys:
        {{
            "trailing_eps": float,
            "forward_eps": float,
            "cagr": float,
            "fair_pe": float,
            "fair_value": float,
            "confidence": float (0.0-1.0 based on data consistency)
        }}
        """
        
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "You are a financial analyst. Return JSON only. No markdown."},
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            
            # Parse JSON
            # Clean possible markdown code blocks
            clean_content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_content)
            return data
            
        except Exception as e:
            logger.error(f"Perplexity API error for {symbol}: {e}")
            return None

    def _save_signal(self, res: ValuationResult):
        """Persist to database."""
        try:
            with next(get_db()) as db:
                signal = ValuationSignal(
                    symbol=res.symbol,
                    analysis_date=res.analysis_date,
                    current_price=res.current_price,
                    fair_value_price=res.fair_value_price,
                    margin_of_safety_pct=res.margin_of_safety_pct,
                    trailing_eps=res.trailing_eps,
                    forward_eps_estimate=res.forward_eps,
                    regime_tag=res.regime_tag,
                    confidence_score=res.confidence_score
                )
                db.add(signal)
                db.commit()
        except Exception as e:
            logger.error(f"DB save failed: {e}")
