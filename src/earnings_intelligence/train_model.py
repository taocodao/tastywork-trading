"""
Training Script for IV Crush Predictor.
Collects historical data via Perplexity API and trains the Random Forest model.

Usage:
    python -m src.earnings_intelligence.train_model
    
Or import and run:
    from src.earnings_intelligence.train_model import train_iv_crush_model
    results = train_iv_crush_model()
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Default symbols for training data collection
DEFAULT_TRAINING_SYMBOLS = [
    # Mega caps (behave differently)
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Large caps tech
    "CRM", "ADBE", "ORCL", "CSCO", "AMD", "INTC", "QCOM",
    # Financials
    "JPM", "BAC", "GS", "MS", "WFC",
    # Healthcare
    "JNJ", "UNH", "PFE", "MRK", "ABBV",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX",
    # ETFs for sector diversification
    "SPY", "QQQ", "IWM"
]


def collect_training_data(
    symbols: List[str] = None,
    quarters_per_symbol: int = 4,
    save_to_db: bool = True,
    use_yfinance: bool = False
) -> List[Dict[str, Any]]:
    """
    Collect historical earnings data for training.
    
    Args:
        symbols: List of symbols to collect data for
        quarters_per_symbol: Number of historical quarters per symbol
        save_to_db: Save to PostgreSQL database
        use_yfinance: Use Yahoo Finance instead of Perplexity (free, no API key)
    
    Returns:
        List of training data points
    """
    if symbols is None:
        symbols = DEFAULT_TRAINING_SYMBOLS
    
    logger.info(f"Collecting training data for {len(symbols)} symbols...")
    
    if use_yfinance:
        # Use free Yahoo Finance data
        return collect_yfinance_data(symbols, quarters_per_symbol)
    else:
        # Use Perplexity API
        return collect_perplexity_data(symbols, quarters_per_symbol, save_to_db)


def collect_yfinance_data(symbols: List[str], quarters: int) -> List[Dict[str, Any]]:
    """Collect training data from Yahoo Finance (free, no API key)."""
    try:
        from src.earnings_intelligence.yfinance_collector import YFinanceCollector
        collector = YFinanceCollector()
        all_data = collector.collect_batch(symbols, quarters)
        logger.info(f"Collected {len(all_data)} samples from Yahoo Finance (FREE)")
        return all_data
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        return []
    except Exception as e:
        logger.error(f"yfinance collection failed: {e}")
        return []


def collect_perplexity_data(
    symbols: List[str],
    quarters: int,
    save_to_db: bool
) -> List[Dict[str, Any]]:
    """Collect training data from Perplexity API."""
    from src.earnings_intelligence.client import PerplexityClient
    
    client = PerplexityClient()
    
    if not client.api_key:
        logger.error("PERPLEXITY_API_KEY not set. Try --yfinance for free data.")
        return []
    
    all_data = client.collect_training_data(
        symbols=symbols,
        quarters_per_symbol=quarters,
        save_to_db=save_to_db
    )
    
    logger.info(f"Collected {len(all_data)} samples from Perplexity")
    return all_data


def collect_combined_data(
    symbols: List[str] = None,
    quarters: int = 8
) -> List[Dict[str, Any]]:
    """
    Collect training data from BOTH sources for maximum coverage.
    yfinance provides historical data, Perplexity adds enrichment.
    """
    if symbols is None:
        symbols = DEFAULT_TRAINING_SYMBOLS
    
    # Start with free yfinance data (bulk historical)
    yf_data = collect_yfinance_data(symbols, quarters)
    
    # Add Perplexity data if API key available
    try:
        from src.earnings_intelligence.client import PerplexityClient
        client = PerplexityClient()
        if client.api_key:
            # Only use Perplexity for select symbols (saves API calls)
            priority_symbols = symbols[:10]  # Top 10 only
            pplx_data = collect_perplexity_data(priority_symbols, 4, save_to_db=True)
            
            # Dedupe and combine
            seen = set()
            combined = []
            for item in yf_data + pplx_data:
                key = (item.get("symbol"), str(item.get("earnings_date", ""))[:10])
                if key not in seen:
                    seen.add(key)
                    combined.append(item)
            
            logger.info(f"Combined data: {len(combined)} unique samples")
            return combined
    except Exception as e:
        logger.warning(f"Perplexity enrichment failed: {e}")
    
    return yf_data



def prepare_training_data(raw_data: List[Dict[str, Any]]) -> List[tuple]:
    """
    Convert raw historical data into feature vectors for training.
    
    Args:
        raw_data: List of historical earnings events
    
    Returns:
        List of (FeatureVector, label) tuples
    """
    from src.earnings_intelligence.features import FeatureEngineer, IVCrushClass
    
    engineer = FeatureEngineer()
    training_pairs = []
    
    for event in raw_data:
        try:
            # Create earnings context from historical event
            earnings_context = {
                "symbol": event.get("symbol"),
                "announcement_date": event.get("earnings_date"),
                "days_to_earnings": 1,  # Historical data is at earnings
                "expected_move_pct": event.get("expected_move_pct", 4.0),
                "historical_move_avg_pct": event.get("actual_move_pct", 4.0),
                "crush_probability": 0.5,  # Unknown at time of earnings
                "iv_rank": event.get("iv_rank", 50),
            }
            
            # Extract features
            features = engineer.extract_features(earnings_context)
            
            # Get actual outcome label
            actual_crush = event.get("actual_crush_pct", -15)
            label = IVCrushClass.from_crush_pct(actual_crush)
            
            training_pairs.append((features, label))
            
        except Exception as e:
            logger.warning(f"Error processing event: {e}")
            continue
    
    logger.info(f"Prepared {len(training_pairs)} training pairs")
    return training_pairs


def train_iv_crush_model(
    symbols: List[str] = None,
    quarters: int = 4,
    n_estimators: int = 100,
    max_depth: int = 10
) -> Dict[str, Any]:
    """
    Full training pipeline: collect data, prepare features, train model.
    
    Args:
        symbols: List of symbols for training data
        quarters: Number of historical quarters per symbol
        n_estimators: Number of trees in Random Forest
        max_depth: Maximum tree depth
    
    Returns:
        Training results with metrics
    """
    logger.info("Starting IV Crush model training pipeline...")
    
    # Step 1: Collect data
    raw_data = collect_training_data(symbols, quarters)
    
    if len(raw_data) < 50:
        logger.warning(f"Only {len(raw_data)} samples collected. Model may not be reliable.")
    
    # Step 2: Prepare training data
    training_data = prepare_training_data(raw_data)
    
    if len(training_data) < 10:
        logger.error("Insufficient training data. Aborting.")
        return {"error": "Insufficient training data", "samples": len(training_data)}
    
    # Step 3: Train model
    from src.earnings_intelligence.iv_crush_model import IVCrushPredictor
    
    predictor = IVCrushPredictor()
    results = predictor.train(
        training_data,
        n_estimators=n_estimators,
        max_depth=max_depth
    )
    
    # Step 4: Save model
    predictor.save_model()
    
    logger.info(f"Training complete. F1-score: {results.get('f1_score', 'N/A')}")
    
    return results


def load_training_data_from_db() -> List[Dict[str, Any]]:
    """Load training data from PostgreSQL database."""
    try:
        from src.earnings_intelligence.database import TrainingDataRepository, get_session
        
        session = get_session()
        repo = TrainingDataRepository(session)
        
        data_points = repo.get_all_training_data()
        
        if not data_points:
            logger.info("No training data in database")
            return []
        
        raw_data = []
        for point in data_points:
            raw_data.append({
                "symbol": point.symbol,
                "earnings_date": point.earnings_date,
                "expected_move_pct": point.expected_move_pct,
                "actual_move_pct": point.historical_move_pct,
                "actual_crush_pct": point.actual_crush_pct,
                "iv_rank": point.iv_rank,
            })
        
        logger.info(f"Loaded {len(raw_data)} training samples from database")
        return raw_data
        
    except Exception as e:
        logger.error(f"Failed to load from database: {e}")
        return []


def train_from_db(n_estimators: int = 100, max_depth: int = 10) -> Dict[str, Any]:
    """Train model using data already in database."""
    logger.info("Training from database...")
    
    # Load from DB
    raw_data = load_training_data_from_db()
    
    if not raw_data:
        return {"error": "No training data in database"}
    
    # Prepare features
    training_data = prepare_training_data(raw_data)
    
    if len(training_data) < 10:
        return {"error": "Insufficient training data", "samples": len(training_data)}
    
    # Train
    from src.earnings_intelligence.iv_crush_model import IVCrushPredictor
    
    predictor = IVCrushPredictor()
    results = predictor.train(training_data, n_estimators=n_estimators, max_depth=max_depth)
    predictor.save_model()
    
    return results


def quick_test():
    """Quick test of the Perplexity API and model."""
    logger.info("Running quick test...")
    
    from src.earnings_intelligence.client import PerplexityClient
    from src.earnings_intelligence.iv_crush_model import IVCrushPredictor
    from src.earnings_intelligence.router import EarningsStrategyRouter
    
    # Test Perplexity API
    client = PerplexityClient()
    logger.info(f"Perplexity API key set: {bool(client.api_key)}")
    
    # Test with AAPL
    logger.info("Fetching earnings context for AAPL...")
    context = client.get_earnings_context("AAPL")
    logger.info(f"Earnings context: {context}")
    
    # Test predictor
    predictor = IVCrushPredictor()
    prediction = predictor.predict(context)
    logger.info(f"Prediction: {prediction}")
    
    # Test router
    router = EarningsStrategyRouter()
    decision = router.decide("AAPL", context)
    logger.info(f"Routing decision: {decision}")
    
    return {
        "context": context,
        "prediction": prediction,
        "decision": decision
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train IV Crush Predictor")
    parser.add_argument("--test", action="store_true", help="Run quick test")
    parser.add_argument("--collect", action="store_true", help="Collect training data only")
    parser.add_argument("--train", action="store_true", help="Train model with Perplexity data")
    parser.add_argument("--from-db", action="store_true", help="Train from database")
    parser.add_argument("--yfinance", action="store_true", help="Use Yahoo Finance (FREE, no API key)")
    parser.add_argument("--combined", action="store_true", help="Use BOTH yfinance + Perplexity")
    parser.add_argument("--symbols", nargs="+", help="Symbols to use")
    parser.add_argument("--quarters", type=int, default=8, help="Quarters per symbol (default 8)")
    parser.add_argument("--estimators", type=int, default=200, help="Number of trees (default 200)")
    parser.add_argument("--depth", type=int, default=12, help="Max tree depth (default 12)")
    
    args = parser.parse_args()
    
    if args.test:
        quick_test()
    elif args.collect:
        if args.yfinance:
            data = collect_yfinance_data(args.symbols or DEFAULT_TRAINING_SYMBOLS, args.quarters)
        else:
            data = collect_training_data(args.symbols, args.quarters, use_yfinance=False)
        print(f"\nCollected {len(data)} samples")
    elif args.from_db:
        results = train_from_db(args.estimators, args.depth)
        print(f"\nTraining Results:\n{results}")
    elif args.yfinance:
        # Train using FREE Yahoo Finance data
        print("\n=== Training with Yahoo Finance (FREE) ===")
        raw_data = collect_yfinance_data(args.symbols or DEFAULT_TRAINING_SYMBOLS, args.quarters)
        if len(raw_data) >= 10:
            training_data = prepare_training_data(raw_data)
            from src.earnings_intelligence.iv_crush_model import IVCrushPredictor
            predictor = IVCrushPredictor()
            results = predictor.train(training_data, n_estimators=args.estimators, max_depth=args.depth)
            predictor.save_model()
            print(f"\nTraining Results:\n{results}")
        else:
            print(f"Insufficient data: {len(raw_data)} samples")
    elif args.combined:
        # Train using BOTH sources
        print("\n=== Training with Combined Data (yfinance + Perplexity) ===")
        raw_data = collect_combined_data(args.symbols or DEFAULT_TRAINING_SYMBOLS, args.quarters)
        if len(raw_data) >= 10:
            training_data = prepare_training_data(raw_data)
            from src.earnings_intelligence.iv_crush_model import IVCrushPredictor
            predictor = IVCrushPredictor()
            results = predictor.train(training_data, n_estimators=args.estimators, max_depth=args.depth)
            predictor.save_model()
            print(f"\nTraining Results:\n{results}")
        else:
            print(f"Insufficient data: {len(raw_data)} samples")
    else:
        # Default: Perplexity only
        results = train_iv_crush_model(
            symbols=args.symbols,
            quarters=args.quarters,
            n_estimators=args.estimators,
            max_depth=args.depth
        )
        print(f"\nTraining Results:\n{results}")

