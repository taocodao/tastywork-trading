"""
Yahoo Finance Data Collector for Earnings Intelligence.
Provides historical earnings data as a supplement to Perplexity API.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Try to import yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not available. Install with: pip install yfinance")


class YFinanceCollector:
    """
    Collects historical earnings data from Yahoo Finance.
    Supplements Perplexity API for training data collection.
    """

    def __init__(self):
        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance not installed. Run: pip install yfinance")

    def get_earnings_history(self, symbol: str, num_quarters: int = 8) -> List[Dict[str, Any]]:
        """
        Get historical earnings data for a symbol.
        
        Args:
            symbol: Stock ticker
            num_quarters: Number of past quarters to fetch
        
        Returns:
            List of earnings events with dates and surprise data
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get earnings dates
            earnings_dates = ticker.earnings_dates
            
            if earnings_dates is None or len(earnings_dates) == 0:
                logger.warning(f"No earnings data for {symbol}")
                return []
            
            # Get historical price data for IV estimation
            history = ticker.history(period="2y")
            
            results = []
            count = 0
            
            for date, row in earnings_dates.iterrows():
                if count >= num_quarters:
                    break
                
                # Only include past earnings
                if date > datetime.now():
                    continue
                
                # Extract earnings info
                event = {
                    "symbol": symbol,
                    "earnings_date": date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)[:10],
                    "eps_estimate": row.get("EPS Estimate", None),
                    "eps_actual": row.get("Reported EPS", None),
                    "surprise_pct": row.get("Surprise(%)", None),
                }
                
                # Calculate price move around earnings
                price_move = self._calculate_price_move(history, date)
                if price_move:
                    event.update(price_move)
                
                # Estimate IV crush (simplified)
                event["actual_crush_pct"] = self._estimate_iv_crush(event)
                
                results.append(event)
                count += 1
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol}: {e}")
            return []

    def _calculate_price_move(self, history, earnings_date) -> Optional[Dict[str, float]]:
        """Calculate actual price move around earnings date."""
        try:
            # Convert to date for comparison
            if hasattr(earnings_date, 'date'):
                earn_date = earnings_date.date()
            else:
                earn_date = earnings_date
            
            # Find closest trading day before earnings
            pre_dates = history.index[history.index.date < earn_date]
            if len(pre_dates) == 0:
                return None
            pre_date = pre_dates[-1]
            
            # Find closest trading day after earnings
            post_dates = history.index[history.index.date > earn_date]
            if len(post_dates) == 0:
                return None
            post_date = post_dates[0]
            
            pre_close = history.loc[pre_date, "Close"]
            post_close = history.loc[post_date, "Close"]
            
            move_pct = ((post_close - pre_close) / pre_close) * 100
            
            return {
                "actual_move_pct": round(abs(move_pct), 2),
                "move_direction": "up" if move_pct > 0 else "down",
                "pre_price": round(pre_close, 2),
                "post_price": round(post_close, 2)
            }
            
        except Exception as e:
            logger.debug(f"Price move calculation error: {e}")
            return None

    def _estimate_iv_crush(self, event: Dict[str, Any]) -> float:
        """
        Estimate IV crush based on actual move vs surprise.
        This is a simplified estimation since yfinance doesn't provide IV data.
        """
        actual_move = event.get("actual_move_pct", 4.0)
        surprise = event.get("surprise_pct", 0)
        
        # Heuristic: larger moves with smaller surprises = normal crush
        # Smaller actual moves = larger crush
        if actual_move < 2:
            return -25.0  # Severe crush (stock didn't move much)
        elif actual_move < 4:
            return -15.0  # Normal crush
        elif actual_move > 8:
            return -5.0  # Minimal crush (stock moved a lot)
        else:
            return -12.0  # Average crush

    def collect_batch(
        self,
        symbols: List[str],
        quarters_per_symbol: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Collect earnings data for multiple symbols.
        
        Args:
            symbols: List of stock tickers
            quarters_per_symbol: Quarters to fetch per symbol
        
        Returns:
            Combined list of all earnings events
        """
        all_data = []
        
        for symbol in symbols:
            logger.info(f"Fetching yfinance earnings for {symbol}...")
            try:
                history = self.get_earnings_history(symbol, quarters_per_symbol)
                all_data.extend(history)
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                continue
        
        logger.info(f"Collected {len(all_data)} earnings events from yfinance")
        return all_data


def collect_yfinance_training_data(symbols: List[str] = None) -> List[Dict[str, Any]]:
    """
    Quick function to collect training data from Yahoo Finance.
    
    Args:
        symbols: List of symbols (defaults to major stocks)
    
    Returns:
        List of earnings events for training
    """
    if not YFINANCE_AVAILABLE:
        logger.error("yfinance not installed")
        return []
    
    if symbols is None:
        symbols = [
            # Mega caps
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
            # Large tech
            "CRM", "ADBE", "ORCL", "CSCO", "AMD", "INTC", "QCOM",
            # Financials
            "JPM", "BAC", "GS", "MS", "WFC", "C",
            # Healthcare
            "JNJ", "UNH", "PFE", "MRK", "ABBV",
            # Consumer
            "WMT", "COST", "HD", "MCD", "NKE", "SBUX",
            # Industrial
            "BA", "CAT", "GE", "UPS", "FDX"
        ]
    
    collector = YFinanceCollector()
    return collector.collect_batch(symbols, quarters_per_symbol=8)
