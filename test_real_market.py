"""
Real Market Data Test for Earnings Intelligence.
Uses Tastytrade API for live options/IV data + Perplexity for earnings context.
"""

import os
import sys
from pathlib import Path

# Add project root
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_tastytrade_client():
    """Initialize Tastytrade client with OAuth tokens."""
    try:
        from tastytrade_client import TastytradeClient
        client = TastytradeClient()
        if client.connect():
            print("[OK] Tastytrade connected")
            return client
        else:
            print("[WARN] Tastytrade connection failed")
            return None
    except Exception as e:
        print(f"[WARN] Tastytrade unavailable: {e}")
        return None


def get_live_iv_data(symbol: str, tasty_client) -> dict:
    """Fetch real IV data from Tastytrade."""
    if not tasty_client:
        return {"iv": 30.0, "iv_percentile": 50, "source": "mock"}
    
    try:
        # Get option chain for the symbol
        chain = tasty_client.get_option_chain(symbol)
        
        if chain and "data" in chain:
            # Find ATM options and get IV
            items = chain.get("data", {}).get("items", [])
            if items:
                # Use first available option's IV
                atm_iv = items[0].get("implied-volatility", 0.30)
                return {
                    "iv": round(atm_iv * 100, 2),
                    "iv_percentile": 50,  # Would need historical data
                    "source": "tastytrade"
                }
    except Exception as e:
        print(f"[WARN] Failed to get IV from Tastytrade: {e}")
    
    return {"iv": 30.0, "iv_percentile": 50, "source": "fallback"}


def test_real_market_data(symbols: list = None):
    """
    Test earnings intelligence with real market data.
    
    Uses:
    - Perplexity API for earnings context
    - Tastytrade for real IV data
    - Trained ML model for predictions
    """
    if symbols is None:
        symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "TSLA"]
    
    print("=" * 70)
    print("REAL MARKET DATA TEST - Earnings Intelligence")
    print("=" * 70)
    
    # Initialize clients
    from src.earnings_intelligence import (
        PerplexityClient,
        EarningsStrategyRouter,
        IVCrushPredictor
    )
    
    perplexity = PerplexityClient()
    router = EarningsStrategyRouter()
    predictor = IVCrushPredictor()
    
    print(f"\n[CONFIG]")
    print(f"  Perplexity API: {'OK' if perplexity.api_key else 'MISSING'}")
    print(f"  ML Model Trained: {predictor.is_trained}")
    print(f"  Model Status: {router.get_model_status()}")
    
    # Try to connect Tastytrade
    tasty = get_tastytrade_client()
    
    print(f"\n{'='*70}")
    print("TESTING SYMBOLS")
    print(f"{'='*70}")
    
    results = []
    
    for symbol in symbols:
        print(f"\n[{symbol}] Fetching data...")
        
        # Get earnings context from Perplexity
        earnings = perplexity.get_earnings_context(symbol, use_cache=False)
        
        # Get real IV from Tastytrade (if available)
        iv_data = get_live_iv_data(symbol, tasty)
        
        # Enrich earnings context with real IV
        earnings["current_iv"] = iv_data.get("iv")
        earnings["iv_source"] = iv_data.get("source")
        
        # Get ML prediction
        prediction = predictor.predict(earnings)
        
        # Get routing decision
        decision = router.decide(symbol, earnings)
        
        # Display results
        print(f"\n  --- {symbol} EARNINGS ANALYSIS ---")
        print(f"  Days to Earnings: {earnings.get('days_to_earnings', 'N/A')}")
        print(f"  Expected Move: {earnings.get('expected_move_pct', 'N/A')}%")
        print(f"  Historical Move: {earnings.get('historical_move_avg_pct', 'N/A')}%")
        print(f"  Crush Probability: {earnings.get('crush_probability', 'N/A')}")
        print(f"  Current IV: {iv_data.get('iv')}% (source: {iv_data.get('source')})")
        
        print(f"\n  --- ML PREDICTION ---")
        print(f"  Predicted Class: {prediction.get('predicted_class')}")
        print(f"  Confidence: {prediction.get('confidence')}%")
        print(f"  Predicted Crush: {prediction.get('predicted_crush_pct')}%")
        print(f"  Model Version: {prediction.get('model_version')}")
        
        print(f"\n  --- TRADING DECISION ---")
        print(f"  ACTION: {decision.action}")
        print(f"  Position Multiplier: {decision.multiplier}")
        print(f"  Risk Factor: {decision.risk_factor}")
        print(f"  Reason: {decision.reason}")
        
        results.append({
            "symbol": symbol,
            "days_to_earnings": earnings.get("days_to_earnings"),
            "expected_move": earnings.get("expected_move_pct"),
            "predicted_class": prediction.get("predicted_class"),
            "confidence": prediction.get("confidence"),
            "decision": decision.action,
            "reason": decision.reason
        })
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    approve_count = sum(1 for r in results if r["decision"] == "APPROVE")
    reject_count = sum(1 for r in results if r["decision"] == "REJECT")
    reduce_count = sum(1 for r in results if r["decision"] == "REDUCE_SIZE")
    
    print(f"\n  APPROVE: {approve_count}")
    print(f"  REJECT: {reject_count}")
    print(f"  REDUCE_SIZE: {reduce_count}")
    
    print(f"\n  Symbol Details:")
    for r in results:
        status = "✓" if r["decision"] == "APPROVE" else "⚠" if r["decision"] == "REDUCE_SIZE" else "✗"
        print(f"    {status} {r['symbol']}: {r['decision']} ({r['days_to_earnings']} days, {r['predicted_class']})")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test with real market data")
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "NVDA", "GOOGL", "TSLA"],
                        help="Symbols to test")
    
    args = parser.parse_args()
    test_real_market_data(args.symbols)
