"""
Combined Signal Generator
=========================

Simplified orchestrator for the unified Diagonal Spread strategy.

The Diagonal Spread strategy handles both:
- Directional trades (PMCC/PMCP) when confidence is high (70%+)
- Neutral trades (Calendar-like) when confidence is lower

It also supports Theta Sprint for larger accounts.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class StrategyRecommendation:
    """Recommended strategy with confidence and reasoning."""
    strategy: str  # "THETA_SPRINT" or "DIAGONAL_SPREAD"
    confidence: float
    reasoning: str
    signal: Optional[Any] = None  # The actual signal object


@dataclass  
class MarketConditions:
    """Current market conditions for strategy selection."""
    iv_rank: float  # 0-100
    iv_percentile: float  # 0-100
    trend_direction: str  # "BULL", "BEAR", "NEUTRAL"
    trend_strength: int  # 0-100
    vix_level: float
    days_to_earnings: int
    liquidity_score: float


class CombinedSignalGenerator:
    """
    Generates signals using the unified Diagonal Spread strategy.
    
    Strategy Selection:
    
    1. THETA SPRINT (Cash-secured puts) - For larger accounts
       - Best when: IV Rank > 50, Neutral-Bullish, Far from earnings
       - Capital: $5K-$50K
       - Win rate: ~97%
       
    2. DIAGONAL SPREAD (Unified: PMCC/PMCP + Calendar)
       - Directional (70%+ confidence): BULL_DIAGONAL or BEAR_DIAGONAL
       - Neutral (<70% confidence): NEUTRAL_DIAGONAL (Calendar-like)
       - Capital: $500-$5K
       - Win rate: ~66-75%
    """
    
    def __init__(
        self,
        theta_enabled: bool = True,
        diagonal_enabled: bool = True
    ):
        """
        Initialize combined generator.
        
        Args:
            theta_enabled: Enable Theta Sprint strategy (large accounts)
            diagonal_enabled: Enable Diagonal Spread strategy (unified)
        """
        self.theta_enabled = theta_enabled
        self.diagonal_enabled = diagonal_enabled
        
        # Initialize individual generators
        self.generators = {}
        
        if theta_enabled:
            try:
                from src.theta_spreads.signal_generator import ThetaSprintSignalGenerator
                self.generators["THETA_SPRINT"] = ThetaSprintSignalGenerator()
                logger.info("Theta Sprint generator initialized")
            except ImportError as e:
                logger.warning(f"Could not import Theta Sprint generator: {e}")
        
        if diagonal_enabled:
            try:
                from src.diagonal_spreads.signal_generator import DiagonalSpreadSignalGenerator
                self.generators["DIAGONAL_SPREAD"] = DiagonalSpreadSignalGenerator()
                logger.info("Diagonal Spread generator initialized")
            except ImportError as e:
                logger.warning(f"Could not import Diagonal generator: {e}")
    
    def analyze_conditions(
        self,
        symbol: str,
        stock_data: Dict,
        account_data: Dict
    ) -> MarketConditions:
        """
        Analyze current market conditions for a symbol.
        
        Args:
            symbol: Stock symbol
            stock_data: Price, IV, technicals
            account_data: Balance, risk settings
        
        Returns:
            MarketConditions object
        """
        iv_rank = stock_data.get("iv_rank", stock_data.get("ivRank", 50))
        iv_percentile = stock_data.get("iv_percentile", iv_rank)
        
        # Determine trend from technicals
        rsi = stock_data.get("rsi", 50)
        ma_50 = stock_data.get("ma_50", stock_data.get("price", 0))
        ma_200 = stock_data.get("ma_200", stock_data.get("price", 0))
        price = stock_data.get("price", 0)
        
        # Simple trend detection
        if price > ma_50 > ma_200 and rsi > 50:
            trend_direction = "BULL"
            trend_strength = min(int((rsi - 50) * 2), 100)
        elif price < ma_50 < ma_200 and rsi < 50:
            trend_direction = "BEAR"
            trend_strength = min(int((50 - rsi) * 2), 100)
        else:
            trend_direction = "NEUTRAL"
            trend_strength = 50 - abs(rsi - 50)
        
        return MarketConditions(
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            vix_level=stock_data.get("vix", 20),
            days_to_earnings=stock_data.get("days_to_earnings", 999),
            liquidity_score=stock_data.get("liquidity_score", 0.7)
        )
    
    def select_strategy(
        self,
        conditions: MarketConditions,
        account_size: float
    ) -> str:
        """
        Select optimal strategy based on conditions.
        
        Args:
            conditions: Current market conditions
            account_size: Account balance
        
        Returns:
            Strategy name
        """
        scores = {}
        
        # Score Theta Sprint (only for larger accounts)
        if self.theta_enabled and "THETA_SPRINT" in self.generators:
            theta_score = 0
            
            # IV rank (higher = better for selling premium)
            if conditions.iv_rank >= 70:
                theta_score += 30
            elif conditions.iv_rank >= 50:
                theta_score += 20
            else:
                theta_score += 5
            
            # Trend (neutral to bullish is good)
            if conditions.trend_direction in ("NEUTRAL", "BULL"):
                theta_score += 25
            else:
                theta_score += 5
            
            # Account size (need $5K+, this is the key differentiator)
            if account_size >= 10000:
                theta_score += 30
            elif account_size >= 5000:
                theta_score += 20
            else:
                theta_score -= 100  # Too small for Theta Sprint
            
            # Earnings (stay away)
            if conditions.days_to_earnings > 14:
                theta_score += 20
            elif conditions.days_to_earnings > 7:
                theta_score += 10
            else:
                theta_score -= 20
            
            scores["THETA_SPRINT"] = max(theta_score, 0)
        
        # Score Diagonal Spread (works for all account sizes)
        if self.diagonal_enabled and "DIAGONAL_SPREAD" in self.generators:
            diagonal_score = 50  # Base score - unified strategy always available
            
            # Account size (works with smaller accounts)
            if account_size >= 2000:
                diagonal_score += 20
            elif account_size >= 500:
                diagonal_score += 15
            
            # Earnings (avoid)
            if conditions.days_to_earnings > 14:
                diagonal_score += 20
            elif conditions.days_to_earnings > 7:
                diagonal_score += 10
            else:
                diagonal_score -= 10
            
            scores["DIAGONAL_SPREAD"] = max(diagonal_score, 0)
        
        # Select highest score
        if not scores:
            return "NONE"
        
        best_strategy = max(scores, key=scores.get)
        logger.info(f"Strategy scores: {scores} -> Selected: {best_strategy}")
        
        return best_strategy
    
    def generate_signal(
        self,
        symbol: str,
        stock_data: Dict,
        account_data: Dict,
        force_strategy: Optional[str] = None
    ) -> Optional[StrategyRecommendation]:
        """
        Generate signal using optimal strategy.
        
        Args:
            symbol: Stock symbol
            stock_data: Price, IV, technicals
            account_data: Balance, risk settings
            force_strategy: Optional strategy override
        
        Returns:
            StrategyRecommendation with signal
        """
        # Analyze conditions
        conditions = self.analyze_conditions(symbol, stock_data, account_data)
        
        # Select strategy
        if force_strategy and force_strategy in self.generators:
            strategy = force_strategy
        else:
            strategy = self.select_strategy(
                conditions, 
                account_data.get("balance", 5000)
            )
        
        if strategy == "NONE" or strategy not in self.generators:
            logger.info(f"{symbol}: No suitable strategy found")
            return None
        
        # Generate signal with selected strategy
        generator = self.generators[strategy]
        signal = None
        
        try:
            signal = generator.generate_signal(symbol, stock_data, account_data)
        except Exception as e:
            logger.error(f"Error generating {strategy} signal for {symbol}: {e}")
            return None
        
        if not signal:
            logger.debug(f"{symbol}: {strategy} generated no signal")
            return None
        
        # Build recommendation
        reasoning = self._build_reasoning(strategy, conditions)
        
        return StrategyRecommendation(
            strategy=strategy,
            confidence=getattr(signal, 'confidence', conditions.iv_rank),
            reasoning=reasoning,
            signal=signal
        )
    
    def generate_all_signals(
        self,
        symbols: List[str],
        stock_data_provider,  # Function(symbol) -> Dict
        account_data: Dict
    ) -> List[StrategyRecommendation]:
        """
        Generate signals for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            stock_data_provider: Function returning stock data
            account_data: Account information
        
        Returns:
            List of recommendations sorted by confidence
        """
        recommendations = []
        
        for symbol in symbols:
            try:
                stock_data = stock_data_provider(symbol)
                rec = self.generate_signal(symbol, stock_data, account_data)
                
                if rec:
                    recommendations.append(rec)
                    
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
        
        # Sort by confidence
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        
        return recommendations
    
    def _build_reasoning(
        self,
        strategy: str,
        conditions: MarketConditions
    ) -> str:
        """Build human-readable reasoning for strategy selection."""
        parts = []
        
        if strategy == "THETA_SPRINT":
            parts.append(f"IV Rank {conditions.iv_rank:.0f}% (good for premium selling)")
            if conditions.trend_direction in ("NEUTRAL", "BULL"):
                parts.append(f"{conditions.trend_direction} trend supports put selling")
        
        elif strategy == "DIAGONAL_SPREAD":
            if conditions.trend_strength >= 70:
                parts.append(f"{conditions.trend_direction} trend with {conditions.trend_strength}% strength (PMCC/PMCP)")
            else:
                parts.append(f"Neutral mode (Calendar-like) with {conditions.trend_strength}% trend strength")
            parts.append(f"IV Rank {conditions.iv_rank:.0f}%")
        
        if conditions.days_to_earnings < 999:
            parts.append(f"Earnings in {conditions.days_to_earnings} days")
        
        return " | ".join(parts)
    
    def get_strategy_summary(self) -> Dict[str, Any]:
        """Get summary of available strategies and their status."""
        return {
            "strategies": {
                "THETA_SPRINT": {
                    "enabled": self.theta_enabled,
                    "available": "THETA_SPRINT" in self.generators,
                    "description": "Cash-secured puts for income",
                    "capital_required": "$5K-$50K",
                    "best_for": "High IV, neutral-bullish, larger accounts"
                },
                "DIAGONAL_SPREAD": {
                    "enabled": self.diagonal_enabled,
                    "available": "DIAGONAL_SPREAD" in self.generators,
                    "description": "Unified: PMCC/PMCP (directional) + Calendar (neutral)",
                    "capital_required": "$500-$5K",
                    "best_for": "All market conditions, smaller accounts"
                }
            },
            "generators_loaded": list(self.generators.keys())
        }
