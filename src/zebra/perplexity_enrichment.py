
"""
Perplexity Enrichment Module
============================

This module integrates with the Perplexity Sonar API to provide real-time
fundamental and sentiment analysis for ZEBRA candidates.

It implements three specific enrichment functions:
1. News Sentiment (with litigation/regulatory checks)
2. SEC Filing Analysis (Revenue/Margin trends)
3. Analyst Consensus (Upgrades/Downgrades)

It returns a composite score and veto flags.
"""

import logging
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# Try to import openai, but handle if not installed (though strictly it should be)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

import config

logger = logging.getLogger(__name__)

# --- Data Models (from Strategy Doc) ---

class NewsTag(BaseModel):
    headline: str
    category: str  # PRODUCT, REGULATORY, LITIGATION, MACRO, EARNINGS
    sentiment: str  # POSITIVE, NEGATIVE, NEUTRAL
    impact_score: float  # 0-1

class NewsSentimentResult(BaseModel):
    symbol: str
    news_tags: List[NewsTag]
    overall_sentiment_score: float  # -1 to 1
    risk_flags: List[str]
    veto: bool
    veto_reason: Optional[str] = None

class SECInsight(BaseModel):
    filing_type: str  # 10-K, 10-Q, 8-K
    period: str
    revenue_trend: str  # UP, DOWN, FLAT
    margin_trend: str
    guidance_change: Optional[str] = None  # UP, DOWN, MAINTAINED, NONE
    risk_factors_new: List[str]
    insider_transactions: Optional[str] = None

class SECResult(BaseModel):
    symbol: str
    filings: List[SECInsight]
    fundamental_risk_score: float  # 0-1 (0=safe, 1=risky)

class AnalystAction(BaseModel):
    firm: str
    action: str  # UPGRADE, DOWNGRADE, INITIATE, REITERATE
    rating: str  # BUY, HOLD, SELL, OVERWEIGHT, etc.
    price_target: Optional[float] = None
    date: str

class AnalystResult(BaseModel):
    symbol: str
    actions_60d: List[AnalystAction]
    net_upgrades: int
    net_downgrades: int
    consensus_trend: str  # UP, DOWN, STABLE
    avg_price_target: Optional[float] = None

# --- Main Enrichment Service ---

class PerplexityEnricher:
    """
    Handles interactions with Perplexity Sonar API.
    Includes caching to minimize costs and latency.
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.client = None
        
        if self.api_key and OpenAI:
            self.client = OpenAI(
                api_key=self.api_key, 
                base_url="https://api.perplexity.ai"
            )
        else:
            logger.warning("Perplexity API key not found or openai package missing. Enrichment disabled.")

        # Simple in-memory cache: { "SYMBOL_TYPE": (timestamp, data) }
        self._cache = {}
        self.cache_ttl_hours = getattr(config, 'ZEBRA_PERPLEXITY_CACHE_HOURS', 6)

    def _get_cached(self, key: str) -> Optional[Any]:
        if key in self._cache:
            ts, data = self._cache[key]
            if (datetime.now() - ts).total_seconds() < (self.cache_ttl_hours * 3600):
                return data
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = (datetime.now(), data)

    def enrich_news_sentiment(self, symbol: str) -> NewsSentimentResult:
        """Fetch latest news and compute sentiment."""
        if not self.client:
            return NewsSentimentResult(symbol=symbol, news_tags=[], overall_sentiment_score=0, risk_flags=[], veto=False)

        cache_key = f"{symbol}_NEWS"
        cached = self._get_cached(cache_key)
        if cached: return cached

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a financial analyst. Extract news events and classify each by category, sentiment, and impact. Flag any litigation, regulatory action, or imminent binary events (FDA, merger vote). Return structured JSON only."
                },
                {
                    "role": "user",
                    "content": f"Analyze the latest news and events for {symbol} in the past 90 days. Classify each major event by category, sentiment, and potential stock price impact."
                }
            ]
            
            completion = self.client.chat.completions.create(
                model="sonar-pro",
                messages=messages,
                # Note: Parameters adjusted for current API support
                # search_recency_filter not standard in OpenAI client, handled via prompt usually or supported custom params
                # We'll rely on the prompt "past 90 days" + model capabilities for now
            )
            
            # Parse response - assume generic JSON extraction if schema enforcement not natively perfect via client
            content = completion.choices[0].message.content
            # Clean content if it contains markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
                
            data = json.loads(content)
            result = NewsSentimentResult(**data)
            
            self._set_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"News enrichment failed for {symbol}: {e}")
            # Return neutral fallback
            return NewsSentimentResult(symbol=symbol, news_tags=[], overall_sentiment_score=0, risk_flags=[], veto=False)

    def enrich_sec_filings(self, symbol: str) -> SECResult:
        """Analyze latest SEC filings."""
        if not self.client:
            return SECResult(symbol=symbol, filings=[], fundamental_risk_score=0)

        cache_key = f"{symbol}_SEC"
        cached = self._get_cached(cache_key)
        if cached: return cached

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a SEC filing analyst. Extract key financial trends, guidance changes, and new risk factors from recent filings. Return structured JSON."
                },
                {
                    "role": "user",
                    "content": f"Summarize the last 2 quarterly filings (10-Q) and most recent annual filing (10-K) for {symbol}. Focus on revenue trends, margin trends, guidance changes, and any new risk factors."
                }
            ]
            
            completion = self.client.chat.completions.create(
                model="sonar-pro",
                messages=messages
            )
            
            content = completion.choices[0].message.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()

            data = json.loads(content)
            result = SECResult(**data)
            
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"SEC enrichment failed for {symbol}: {e}")
            return SECResult(symbol=symbol, filings=[], fundamental_risk_score=0)

    def enrich_analyst_consensus(self, symbol: str) -> AnalystResult:
        """Track analyst upgrades/downgrades."""
        if not self.client:
            return AnalystResult(symbol=symbol, actions_60d=[], net_upgrades=0, net_downgrades=0, consensus_trend="STABLE")

        cache_key = f"{symbol}_ANALYST"
        cached = self._get_cached(cache_key)
        if cached: return cached

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a sell-side research tracker. Extract analyst rating changes, price target changes, and consensus trends. Return structured JSON."
                },
                {
                    "role": "user",
                    "content": f"List all analyst upgrades, downgrades, initiations, and price target changes for {symbol} in the last 60 days. Compute net upgrades vs downgrades and consensus trend."
                }
            ]
            
            completion = self.client.chat.completions.create(
                model="sonar-pro",
                messages=messages
            )
            
            content = completion.choices[0].message.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()

            data = json.loads(content)
            result = AnalystResult(**data)
            
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Analyst enrichment failed for {symbol}: {e}")
            return AnalystResult(symbol=symbol, actions_60d=[], net_upgrades=0, net_downgrades=0, consensus_trend="STABLE")

    def compute_perplexity_composite(self, symbol: str) -> Dict[str, Any]:
        """
        Aggregate all enrichment functions into a composite score and decision.
        """
        news = self.enrich_news_sentiment(symbol)
        sec = self.enrich_sec_filings(symbol)
        analyst = self.enrich_analyst_consensus(symbol)

        # 1. Veto Checks
        if news.veto:
            return {"symbol": symbol, "action": "VETO", "reason": f"News Veto: {news.veto_reason}"}

        if sec.fundamental_risk_score > 0.7:
             return {"symbol": symbol, "action": "VETO", "reason": "High Fundamental Risk (SEC)"}

        # 2. Composite Score Calculation
        # Normalize sentiment (-1 to 1) -> (0 to 1)
        sent_norm = (news.overall_sentiment_score + 1) / 2
        
        # Risk score (0 to 1), invert so 1 is safe
        sec_safe = 1 - sec.fundamental_risk_score
        
        # Analyst trend
        trend_score = 1.0 if analyst.consensus_trend == "UP" else \
                      0.5 if analyst.consensus_trend == "STABLE" else 0.0

        # Weighted Sum
        composite = (
            0.35 * sent_norm +
            0.35 * sec_safe +
            0.30 * trend_score
        )

        return {
            "symbol": symbol,
            "action": "PASS",
            "composite_score": round(composite, 3),
            "details": {
                "news_sentiment": news.overall_sentiment_score,
                "fundamental_risk": sec.fundamental_risk_score,
                "analyst_trend": analyst.consensus_trend,
                "net_upgrades": analyst.net_upgrades
            },
            "veto_flags": news.risk_flags
        }

# Global singleton
_enricher = None

def get_enricher() -> PerplexityEnricher:
    global _enricher
    if _enricher is None:
        _enricher = PerplexityEnricher()
    return _enricher
