"""
Perplexity Client for Earnings Intelligence.
Fetches earnings dates, expected moves, and historical moves using Perplexity API.
Enhanced with historical data collection for ML training.
"""

import os
import json
import requests
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

logger = logging.getLogger(__name__)



class PerplexityClient:
    """
    Client for fetching earnings intelligence from Perplexity API.
    Supports both real-time queries and historical data collection for ML training.
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self._db_session = None
    
    def query(self, prompt: str, model: str = "sonar-pro") -> str:
        """
        Generic query to Perplexity API.
        
        Args:
            prompt: The question to ask
            model: Model to use (default: sonar-pro)
            
        Returns:
            Response text from Perplexity
        """
        if not self.api_key:
            logger.warning("No Perplexity API Key provided.")
            return ""
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            logger.error(f"Perplexity query failed: {e}")
            return ""
        
    def get_earnings_context(self, symbol: str, use_cache: bool = True) -> dict:
        """
        Queries Perplexity for earnings intelligence.
        Returns a dictionary with keys:
         - announcement_date (iso str)
         - days_to_earnings (int)
         - expected_move_pct (float)
         - historical_move_avg_pct (float)
         - crush_probability (float)
         - iv_crush_risk (str: 'LOW', 'MEDIUM', 'HIGH')
        """
        # Check cache first if enabled
        if use_cache:
            cached = self._get_cached_earnings(symbol)
            if cached:
                logger.debug(f"Using cached earnings data for {symbol}")
                return cached
        
        if not self.api_key:
            logger.warning("No Perplexity API Key provided. Using mock data.")
            return self._get_mock_data(symbol)

        prompt = f"""
        Analyze the upcoming earnings and market sentiment for {symbol}.
        Return ONLY a JSON object with the following fields:
        - "announcement_date": Best estimate of next earnings date (ISO 8601 YYYY-MM-DD).
        - "days_to_earnings": Number of days from now (integer).
        - "expected_move_pct": The implied market move percentage for this earnings (float, e.g. 5.5).
        - "historical_move_avg_pct": Average actual stock move over last 4 earnings (float).
        - "crush_probability": Estimated probability (0.0-1.0) of significant IV crush (>20% IV decline) after earnings.
        - "iv_rank": Current IV rank percentile (0-100).
        - "analysis_summary": A very brief 1-sentence summary of volatility expectations.
        - "analyst_rating": Object with recent analyst actions:
            - "consensus": Current consensus (BUY/HOLD/SELL/STRONG_BUY)
            - "price_target": Average analyst price target (float)
            - "recent_changes": List of recent analyst rating changes in past 30 days, each with:
                - "analyst": Firm name
                - "action": (upgrade/downgrade/maintain/initiate)
                - "from_rating": Previous rating
                - "to_rating": New rating
                - "date": Date of change (YYYY-MM-DD)
        - "significant_news": List of up to 3 recent news items that could significantly move the stock:
            - "headline": Brief headline
            - "impact": (bullish/bearish/neutral)
            - "date": Date (YYYY-MM-DD)
        
        If precise data is unavailable, provide best estimates based on recent news or historical patterns.
        """

        payload = {
            "model": "sonar-pro", 
            "messages": [
                {"role": "system", "content": "You are a financial data analyst helper. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Clean content if it has markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
                
            result = json.loads(content)
            result["symbol"] = symbol
            result["raw_response"] = data
            enriched = self._enrich_analysis(result)
            
            # Save to database cache
            self._save_to_cache(symbol, enriched)
            
            return enriched
            
        except Exception as e:
            logger.error(f"Perplexity API error for {symbol}: {e}")
            return self._get_mock_data(symbol)

    def get_historical_earnings(self, symbol: str, num_quarters: int = 4) -> List[Dict[str, Any]]:
        """
        Fetch historical earnings data for ML training.
        
        Args:
            symbol: Stock symbol
            num_quarters: Number of past earnings to fetch
        
        Returns:
            List of historical earnings events with outcomes
        """
        if not self.api_key:
            logger.warning("No Perplexity API Key. Cannot fetch historical data.")
            return []

        prompt = f"""
        Provide historical earnings data for {symbol} for the last {num_quarters} quarters.
        Return ONLY a JSON array where each element has:
        - "earnings_date": Date of earnings announcement (YYYY-MM-DD)
        - "expected_move_pct": Implied move before earnings
        - "actual_move_pct": Actual stock move after earnings
        - "iv_before": IV level before earnings (as percentage, e.g. 35.0)
        - "iv_after": IV level after earnings
        - "beat_miss": "beat", "miss", or "inline"
        - "surprise_pct": EPS surprise percentage
        
        Use real historical data. If exact IV data unavailable, estimate based on typical patterns.
        """

        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "You are a financial data analyst. Output only valid JSON array."},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=45)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Clean markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
            
            historical = json.loads(content)
            
            # Enrich with calculated fields
            for event in historical:
                event["symbol"] = symbol
                iv_before = event.get("iv_before", 30)
                iv_after = event.get("iv_after", 20)
                if iv_before and iv_after:
                    event["actual_crush_pct"] = ((iv_after - iv_before) / iv_before) * 100
                else:
                    event["actual_crush_pct"] = -15  # Default estimate
            
            return historical
            
        except Exception as e:
            logger.error(f"Failed to fetch historical earnings for {symbol}: {e}")
            return []

    def collect_training_data(
        self,
        symbols: List[str],
        quarters_per_symbol: int = 4,
        save_to_db: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Collect historical earnings data for multiple symbols for ML training.
        
        Args:
            symbols: List of stock symbols
            quarters_per_symbol: Number of quarters to fetch per symbol
            save_to_db: Whether to save to database
        
        Returns:
            Complete training dataset
        """
        all_data = []
        
        for symbol in symbols:
            logger.info(f"Collecting historical data for {symbol}...")
            try:
                historical = self.get_historical_earnings(symbol, quarters_per_symbol)
                all_data.extend(historical)
                
                if save_to_db and historical:
                    self._save_training_data(historical)
                    
            except Exception as e:
                logger.warning(f"Error collecting data for {symbol}: {e}")
                continue
        
        logger.info(f"Collected {len(all_data)} training samples from {len(symbols)} symbols")
        return all_data

    def _enrich_analysis(self, data: dict) -> dict:
        """Add derived fields like risk levels."""
        try:
            exp_move = data.get("expected_move_pct", 0)
            hist_move = data.get("historical_move_avg_pct", 0)
            days = data.get("days_to_earnings", 90)
            crush_prob = data.get("crush_probability", 0.5)
            
            # Determine risk level
            if days <= 3:
                risk = "HIGH"
            elif days <= 7 and crush_prob >= 0.6:
                risk = "HIGH"
            elif days <= 7:
                risk = "MEDIUM"
            else:
                risk = "LOW"
            
            data["earnings_risk_level"] = risk
            
            # Add move ratio
            if hist_move and hist_move > 0:
                data["move_ratio"] = exp_move / hist_move
            else:
                data["move_ratio"] = 1.0
                
            return data
        except:
            return data

    def _get_mock_data(self, symbol: str) -> dict:
        """Fallback mock data for testing."""
        return {
            "symbol": symbol,
            "announcement_date": (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d"),
            "days_to_earnings": 45,
            "expected_move_pct": 3.5,
            "historical_move_avg_pct": 4.0,
            "crush_probability": 0.3,
            "iv_rank": 40,
            "analysis_summary": "Mock data: Earnings far away.",
            "earnings_risk_level": "LOW",
            "move_ratio": 0.875
        }

    def _get_db_session(self):
        """Get database session lazily."""
        if self._db_session is None:
            try:
                from .database import get_session
                self._db_session = get_session()
            except Exception as e:
                logger.debug(f"Database not available: {e}")
        return self._db_session

    def _get_cached_earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Check database cache for recent earnings data."""
        session = self._get_db_session()
        if not session:
            return None
            
        try:
            from .database import EarningsCalendar
            
            # Get most recent entry for symbol, less than 24 hours old
            cutoff = datetime.utcnow() - timedelta(hours=24)
            cached = session.query(EarningsCalendar).filter(
                EarningsCalendar.symbol == symbol,
                EarningsCalendar.updated_at >= cutoff
            ).order_by(EarningsCalendar.updated_at.desc()).first()
            
            if cached:
                return cached.to_dict()
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")
        
        return None

    def _save_to_cache(self, symbol: str, data: Dict[str, Any]):
        """Save earnings data to database cache."""
        session = self._get_db_session()
        if not session:
            return
            
        try:
            from .database import EarningsRepository
            
            repo = EarningsRepository(session)
            
            # Parse announcement date
            ann_date = data.get("announcement_date")
            if isinstance(ann_date, str):
                try:
                    ann_date = datetime.fromisoformat(ann_date.replace("Z", "+00:00"))
                except:
                    ann_date = None
            
            repo.save_earnings({
                "symbol": symbol,
                "announcement_date": ann_date,
                "expected_move_pct": data.get("expected_move_pct"),
                "historical_move_pct": data.get("historical_move_avg_pct"),
                "iv_rank": data.get("iv_rank"),
                "crush_probability": data.get("crush_probability"),
                "analysis_summary": data.get("analysis_summary"),
                "raw_response": data.get("raw_response"),
                "data_source": "perplexity"
            })
        except Exception as e:
            logger.debug(f"Failed to cache earnings: {e}")

    def _save_training_data(self, historical_data: List[Dict[str, Any]]):
        """Save historical earnings to training data table."""
        session = self._get_db_session()
        if not session:
            return
            
        try:
            from .database import TrainingDataRepository
            from .features import IVCrushClass
            
            repo = TrainingDataRepository(session)
            
            for event in historical_data:
                crush_pct = event.get("actual_crush_pct", -15)
                actual_class = IVCrushClass.from_crush_pct(crush_pct)
                
                # Parse date
                earnings_date = event.get("earnings_date")
                if isinstance(earnings_date, str):
                    try:
                        earnings_date = datetime.fromisoformat(earnings_date)
                    except:
                        earnings_date = datetime.now()
                
                repo.save_training_point({
                    "symbol": event.get("symbol"),
                    "earnings_date": earnings_date,
                    "expected_move_pct": event.get("expected_move_pct"),
                    "historical_move_pct": event.get("actual_move_pct"),
                    "actual_crush_pct": crush_pct,
                    "actual_class": actual_class,
                    "actual_price_move_pct": event.get("actual_move_pct"),
                    "all_features": event,
                    "data_source": "perplexity"
                })
        except Exception as e:
            logger.debug(f"Failed to save training data: {e}")
