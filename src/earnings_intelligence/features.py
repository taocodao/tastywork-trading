"""
Feature Engineering for IV Crush Prediction.
Extracts features from earnings data and market conditions for ML model training.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import math

logger = logging.getLogger(__name__)


# IV Crush class definitions
class IVCrushClass:
    """Classification labels for IV crush magnitude."""
    NORMAL = "NORMAL"         # 10-20% IV decline (expected)
    SEVERE = "SEVERE"         # >30% IV decline (unexpected, dangerous)
    EXPANSION = "EXPANSION"   # IV increases post-earnings (rare)
    NO_CRUSH = "NO_CRUSH"     # <5% IV change (flat)

    @classmethod
    def from_crush_pct(cls, crush_pct: float) -> str:
        """Classify based on IV crush percentage (negative = crush)."""
        if crush_pct > 5:  # IV increased
            return cls.EXPANSION
        elif crush_pct > -5:  # Minimal change
            return cls.NO_CRUSH
        elif crush_pct > -20:  # Normal crush
            return cls.NORMAL
        else:  # Severe crush
            return cls.SEVERE


@dataclass
class FeatureVector:
    """Complete feature vector for ML model."""
    # Core earnings features
    days_to_earnings: int
    expected_move_pct: float
    historical_move_pct: float
    crush_probability: float
    
    # Derived earnings features
    move_ratio: float  # expected / historical
    iv_rank_bucket: int  # 0-3 (LOW, MEDIUM, HIGH, EXTREME)
    earnings_week: int  # Week of year (seasonality)
    is_mega_cap: bool  # Large cap stocks behave differently
    
    # Technical indicators
    rsi_14: float
    bb_position: float  # -1 to 1 (lower to upper band)
    ma_trend: float  # -1 to 1 (bearish to bullish)
    
    # Volatility features
    atm_iv: float
    vix_level: float
    iv_percentile: float
    
    # Market context
    sector_momentum: float
    market_trend: float
    
    def to_array(self) -> List[float]:
        """Convert to numeric array for ML model."""
        return [
            float(self.days_to_earnings),
            self.expected_move_pct,
            self.historical_move_pct,
            self.crush_probability,
            self.move_ratio,
            float(self.iv_rank_bucket),
            float(self.earnings_week),
            float(self.is_mega_cap),
            self.rsi_14,
            self.bb_position,
            self.ma_trend,
            self.atm_iv,
            self.vix_level,
            self.iv_percentile,
            self.sector_momentum,
            self.market_trend,
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "days_to_earnings": self.days_to_earnings,
            "expected_move_pct": self.expected_move_pct,
            "historical_move_pct": self.historical_move_pct,
            "crush_probability": self.crush_probability,
            "move_ratio": self.move_ratio,
            "iv_rank_bucket": self.iv_rank_bucket,
            "earnings_week": self.earnings_week,
            "is_mega_cap": self.is_mega_cap,
            "rsi_14": self.rsi_14,
            "bb_position": self.bb_position,
            "ma_trend": self.ma_trend,
            "atm_iv": self.atm_iv,
            "vix_level": self.vix_level,
            "iv_percentile": self.iv_percentile,
            "sector_momentum": self.sector_momentum,
            "market_trend": self.market_trend,
        }

    @classmethod
    def feature_names(cls) -> List[str]:
        """Get ordered list of feature names."""
        return [
            "days_to_earnings",
            "expected_move_pct",
            "historical_move_pct",
            "crush_probability",
            "move_ratio",
            "iv_rank_bucket",
            "earnings_week",
            "is_mega_cap",
            "rsi_14",
            "bb_position",
            "ma_trend",
            "atm_iv",
            "vix_level",
            "iv_percentile",
            "sector_momentum",
            "market_trend",
        ]


class FeatureEngineer:
    """
    Extracts and transforms features for IV crush prediction.
    Combines Perplexity API data with technical indicators.
    """

    # Mega-cap stocks (market cap > $100B)
    MEGA_CAPS = {
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
        "BRK.A", "BRK.B", "UNH", "JNJ", "JPM", "V", "XOM", "PG", "MA",
        "HD", "CVX", "LLY", "ABBV", "MRK", "AVGO", "PEP", "KO", "COST"
    }

    # Sector ETF mapping for momentum calculation
    SECTOR_ETFS = {
        "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ADBE", "CRM", "CSCO"],
        "XLF": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK"],
        "XLY": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW"],
        "XLV": ["UNH", "JNJ", "PFE", "ABBV", "MRK", "TMO", "ABT"],
        "XLE": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX"],
    }

    def __init__(self):
        self.default_vix = 18.0  # Average VIX level

    def extract_features(
        self,
        earnings_context: Dict[str, Any],
        technical_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None
    ) -> FeatureVector:
        """
        Extract complete feature vector from available data.
        
        Args:
            earnings_context: Data from Perplexity API
            technical_data: RSI, Bollinger Bands, MAs (optional)
            market_data: VIX, sector momentum (optional)
        
        Returns:
            FeatureVector ready for ML model
        """
        technical_data = technical_data or {}
        market_data = market_data or {}
        symbol = earnings_context.get("symbol", "")

        # Core earnings features
        days_to_earnings = earnings_context.get("days_to_earnings", 30)
        expected_move = earnings_context.get("expected_move_pct", 3.0)
        historical_move = earnings_context.get("historical_move_avg_pct", 4.0)
        crush_prob = earnings_context.get("crush_probability", 0.5)

        # Derived features
        move_ratio = self._safe_divide(expected_move, historical_move, 1.0)
        iv_rank = earnings_context.get("iv_rank", 50)
        iv_rank_bucket = self._bucket_iv_rank(iv_rank)
        
        # Seasonality
        earnings_date = earnings_context.get("announcement_date")
        if isinstance(earnings_date, str):
            try:
                earnings_date = datetime.fromisoformat(earnings_date.replace("Z", "+00:00"))
            except:
                earnings_date = datetime.now()
        elif not earnings_date:
            earnings_date = datetime.now()
        earnings_week = earnings_date.isocalendar()[1] if earnings_date else 1

        # Technical indicators (with defaults)
        rsi_14 = technical_data.get("rsi", technical_data.get("rsi_14", 50))
        bb_position = self._normalize_bb_position(
            technical_data.get("bb_position", 0),
            technical_data.get("price", 0),
            technical_data.get("bb_upper", 0),
            technical_data.get("bb_lower", 0)
        )
        ma_trend = self._calculate_ma_trend(technical_data)

        # Volatility features
        atm_iv = earnings_context.get("iv", technical_data.get("atm_iv", 0.25))
        vix_level = market_data.get("vix", self.default_vix)
        iv_percentile = earnings_context.get("iv_percentile", iv_rank)

        # Market context
        sector_momentum = market_data.get("sector_momentum", 0)
        market_trend = market_data.get("market_trend", market_data.get("spy_momentum", 0))

        return FeatureVector(
            days_to_earnings=days_to_earnings,
            expected_move_pct=expected_move,
            historical_move_pct=historical_move,
            crush_probability=crush_prob,
            move_ratio=move_ratio,
            iv_rank_bucket=iv_rank_bucket,
            earnings_week=earnings_week,
            is_mega_cap=symbol.upper() in self.MEGA_CAPS,
            rsi_14=rsi_14,
            bb_position=bb_position,
            ma_trend=ma_trend,
            atm_iv=atm_iv,
            vix_level=vix_level,
            iv_percentile=iv_percentile,
            sector_momentum=sector_momentum,
            market_trend=market_trend,
        )

    def _safe_divide(self, a: float, b: float, default: float = 0) -> float:
        """Safe division with default for zero denominator."""
        try:
            if b == 0 or b is None:
                return default
            return a / b
        except:
            return default

    def _bucket_iv_rank(self, iv_rank: float) -> int:
        """Convert IV rank to bucket (0-3)."""
        if iv_rank is None:
            return 1  # Medium
        if iv_rank < 25:
            return 0  # Low
        elif iv_rank < 50:
            return 1  # Medium
        elif iv_rank < 75:
            return 2  # High
        else:
            return 3  # Extreme

    def _normalize_bb_position(
        self,
        position: float,
        price: float,
        upper: float,
        lower: float
    ) -> float:
        """
        Normalize Bollinger Band position to -1 to 1 range.
        -1 = at lower band, 0 = at middle, 1 = at upper band
        """
        if position != 0:
            return max(-1, min(1, position))
        
        if price == 0 or upper == lower:
            return 0
        
        try:
            middle = (upper + lower) / 2
            half_width = (upper - lower) / 2
            return (price - middle) / half_width if half_width > 0 else 0
        except:
            return 0

    def _calculate_ma_trend(self, technical_data: Dict[str, Any]) -> float:
        """
        Calculate MA trend from -1 (bearish) to 1 (bullish).
        Uses relationship between short and long MAs.
        """
        short_ma = technical_data.get("ma_20", technical_data.get("sma_20", 0))
        long_ma = technical_data.get("ma_50", technical_data.get("sma_50", 0))
        price = technical_data.get("price", 0)

        if short_ma == 0 or long_ma == 0 or price == 0:
            return 0

        # Price above both MAs = bullish, below both = bearish
        score = 0
        if price > short_ma:
            score += 0.5
        else:
            score -= 0.5
        
        if price > long_ma:
            score += 0.3
        else:
            score -= 0.3
        
        if short_ma > long_ma:
            score += 0.2
        else:
            score -= 0.2

        return max(-1, min(1, score))

    def create_training_features(
        self,
        historical_earnings: List[Dict[str, Any]]
    ) -> List[tuple]:
        """
        Create training feature vectors from historical data.
        
        Args:
            historical_earnings: List of historical earnings events with outcomes
        
        Returns:
            List of (FeatureVector, label) tuples
        """
        training_data = []

        for event in historical_earnings:
            try:
                features = self.extract_features(event)
                actual_crush = event.get("actual_crush_pct", 0)
                label = IVCrushClass.from_crush_pct(actual_crush)
                training_data.append((features, label))
            except Exception as e:
                logger.warning(f"Error extracting features: {e}")
                continue

        return training_data


# Utility function for quick feature extraction
def extract_features_from_perplexity(
    perplexity_response: Dict[str, Any],
    symbol: str
) -> FeatureVector:
    """
    Quick helper to extract features from Perplexity API response.
    """
    engineer = FeatureEngineer()
    perplexity_response["symbol"] = symbol
    return engineer.extract_features(perplexity_response)
