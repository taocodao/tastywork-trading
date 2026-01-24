"""Quick test for earnings intelligence module."""
import sys
import os

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure output is visible
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None


print("=" * 60)
print("EARNINGS INTELLIGENCE MODULE TEST")
print("=" * 60)

try:
    from src.earnings_intelligence import PerplexityClient, EarningsStrategyRouter, IVCrushPredictor
    print("[OK] All imports successful")
except Exception as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)

# Test 1: Check API key
client = PerplexityClient()
print(f"\n[1] Perplexity API Key configured: {bool(client.api_key)}")

# Test 2: Fetch AAPL earnings
print("\n[2] Fetching AAPL earnings context...")
try:
    context = client.get_earnings_context("AAPL", use_cache=False)
    print(f"    Days to Earnings: {context.get('days_to_earnings')}")
    print(f"    Expected Move: {context.get('expected_move_pct')}%")
    print(f"    Historical Move: {context.get('historical_move_avg_pct')}%")
    print(f"    Crush Probability: {context.get('crush_probability')}")
    print(f"    Risk Level: {context.get('earnings_risk_level')}")
    print(f"    Summary: {context.get('analysis_summary', 'N/A')[:100]}")
except Exception as e:
    print(f"    [ERROR] {e}")
    context = None

# Test 3: ML Predictor
print("\n[3] Testing IV Crush Predictor...")
try:
    predictor = IVCrushPredictor()
    print(f"    Model trained: {predictor.is_trained}")
    if context:
        prediction = predictor.predict(context)
        print(f"    Predicted Class: {prediction.get('predicted_class')}")
        print(f"    Confidence: {prediction.get('confidence')}%")
        print(f"    Predicted Crush: {prediction.get('predicted_crush_pct')}%")
        print(f"    Model Version: {prediction.get('model_version')}")
except Exception as e:
    print(f"    [ERROR] {e}")

# Test 4: Strategy Router
print("\n[4] Testing Strategy Router...")
try:
    router = EarningsStrategyRouter()
    if context:
        decision = router.decide("AAPL", context)
        print(f"    Action: {decision.action}")
        print(f"    Multiplier: {decision.multiplier}")
        print(f"    Reason: {decision.reason}")
        print(f"    Risk Factor: {decision.risk_factor}")
        status = router.get_model_status()
        print(f"    Model Status: {status}")
except Exception as e:
    print(f"    [ERROR] {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
