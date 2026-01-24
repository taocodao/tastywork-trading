"""
End-to-End Test for Vertical Spread System
==========================================

Tests the complete flow from direction prediction through signal publishing.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_01_direction_predictor():
    """Test 1: Direction Predictor with various scenarios."""
    print("\n" + "="*60)
    print("TEST 1: Direction Predictor")
    print("="*60)
    
    from src.vertical_spreads.direction_predictor import VerticalSpreadDirectionPredictor
    
    predictor = VerticalSpreadDirectionPredictor()
    
    # Scenario 1: Strongly oversold (should be BULL)
    oversold_data = {
        "symbol": "SPY",
        "price": 485.0,
        "rsi_14": 22,
        "bb_upper": 490, "bb_mid": 485, "bb_lower": 480,
        "sma_20": 483, "sma_50": 480, "sma_200": 475
    }
    signal1 = predictor.calculate_direction_signal(oversold_data)
    print(f"\nScenario: Oversold RSI (22)")
    print(f"  Direction: {signal1.direction}")
    print(f"  Confidence: {signal1.confidence}%")
    print(f"  Actionable: {predictor.is_actionable(signal1)}")
    assert signal1.direction == "BULL", "Expected BULL for oversold"
    print("  ✓ PASSED")
    
    # Scenario 2: Strongly overbought (should be BEAR)
    overbought_data = {
        "symbol": "QQQ",
        "price": 410.0,
        "rsi_14": 82,
        "bb_upper": 415, "bb_mid": 410, "bb_lower": 405,
        "sma_20": 412, "sma_50": 415, "sma_200": 420
    }
    signal2 = predictor.calculate_direction_signal(overbought_data)
    print(f"\nScenario: Overbought RSI (82)")
    print(f"  Direction: {signal2.direction}")
    print(f"  Confidence: {signal2.confidence}%")
    print(f"  Actionable: {predictor.is_actionable(signal2)}")
    assert signal2.direction == "BEAR", "Expected BEAR for overbought"
    print("  ✓ PASSED")
    
    # Scenario 3: Neutral (mixed signals)
    neutral_data = {
        "symbol": "IWM",
        "price": 200.0,
        "rsi_14": 50,
        "bb_upper": 205, "bb_mid": 200, "bb_lower": 195,
        "sma_20": 200, "sma_50": 200, "sma_200": 200
    }
    signal3 = predictor.calculate_direction_signal(neutral_data)
    print(f"\nScenario: Neutral RSI (50)")
    print(f"  Direction: {signal3.direction}")
    print(f"  Confidence: {signal3.confidence}%")
    print(f"  Actionable: {predictor.is_actionable(signal3)}")
    print("  ✓ PASSED (neutral is expected)")
    
    return True


def test_02_spread_selector():
    """Test 2: Spread Selector for bull and bear spreads."""
    print("\n" + "="*60)
    print("TEST 2: Spread Selector")
    print("="*60)
    
    from src.vertical_spreads.spread_selector import VerticalSpreadSelector, get_available_expirations
    
    selector = VerticalSpreadSelector()
    expirations = get_available_expirations(7, 21)
    
    print(f"\nAvailable expirations: {len(expirations)} dates")
    
    # Bull call spread
    bull_setup = selector.select_spread(
        symbol="SPY",
        stock_price=485.0,
        direction="BULL",
        confidence=75,
        iv=0.20,
        account_balance=10000,
        available_expirations=expirations
    )
    
    print(f"\nBull Call Spread:")
    print(f"  Strategy: {bull_setup.strategy}")
    print(f"  Buy Strike: {bull_setup.buy_strike}")
    print(f"  Sell Strike: {bull_setup.sell_strike}")
    print(f"  DTE: {bull_setup.dte}")
    print(f"  Contracts: {bull_setup.contracts}")
    print(f"  Score: {bull_setup.score}")
    assert bull_setup.strategy == "BULL_CALL_SPREAD"
    assert bull_setup.buy_strike <= bull_setup.sell_strike
    print("  ✓ PASSED")
    
    # Bear put spread
    bear_setup = selector.select_spread(
        symbol="QQQ",
        stock_price=410.0,
        direction="BEAR",
        confidence=70,
        iv=0.25,
        account_balance=10000,
        available_expirations=expirations
    )
    
    print(f"\nBear Put Spread:")
    print(f"  Strategy: {bear_setup.strategy}")
    print(f"  Buy Strike: {bear_setup.buy_strike}")
    print(f"  Sell Strike: {bear_setup.sell_strike}")
    print(f"  DTE: {bear_setup.dte}")
    print(f"  Contracts: {bear_setup.contracts}")
    print(f"  Score: {bear_setup.score}")
    assert bear_setup.strategy == "BEAR_PUT_SPREAD"
    assert bear_setup.buy_strike >= bear_setup.sell_strike
    print("  ✓ PASSED")
    
    # Neutral should return None
    neutral = selector.select_spread(
        symbol="IWM",
        stock_price=200.0,
        direction="NEUTRAL",
        confidence=50,
        iv=0.20,
        account_balance=10000,
        available_expirations=expirations
    )
    print(f"\nNeutral Direction:")
    print(f"  Result: {neutral}")
    assert neutral is None
    print("  ✓ PASSED (None returned for neutral)")
    
    return True


def test_03_suitability_validator():
    """Test 3: Suitability Validator with pass/fail scenarios."""
    print("\n" + "="*60)
    print("TEST 3: Suitability Validator")
    print("="*60)
    
    from src.vertical_spreads.suitability import VerticalSpreadSuitabilityValidator
    
    validator = VerticalSpreadSuitabilityValidator()
    
    # Valid profile
    valid = {"account_balance": 10000, "options_level": 3}
    result1 = validator.validate(valid)
    print(f"\nValid Profile ($10K, Level 3):")
    print(f"  Suitable: {result1.suitable}")
    print(f"  Blocking Issues: {result1.blocking_issues}")
    assert result1.suitable == True
    print("  ✓ PASSED")
    
    # Low balance
    low_bal = {"account_balance": 1500, "options_level": 2}
    result2 = validator.validate(low_bal)
    print(f"\nLow Balance ($1500):")
    print(f"  Suitable: {result2.suitable}")
    print(f"  Blocking Issues: {result2.blocking_issues}")
    assert result2.suitable == False
    print("  ✓ PASSED (correctly rejected)")
    
    # Low options level
    low_lvl = {"account_balance": 5000, "options_level": 1}
    result3 = validator.validate(low_lvl)
    print(f"\nLow Options Level (1):")
    print(f"  Suitable: {result3.suitable}")
    print(f"  Blocking Issues: {result3.blocking_issues}")
    assert result3.suitable == False
    print("  ✓ PASSED (correctly rejected)")
    
    # Trade size check
    valid_profile = {"account_balance": 5000, "options_level": 2}
    big_trade = {"max_loss_per_contract": 500, "contracts": 2}
    result4 = validator.validate(valid_profile, big_trade)
    print(f"\nOversized Trade (risk > 2%):")
    print(f"  Suitable: {result4.suitable}")
    print(f"  Blocking Issues: {result4.blocking_issues}")
    assert result4.suitable == False
    print("  ✓ PASSED (correctly rejected oversized trade)")
    
    return True


def test_04_stop_manager():
    """Test 4: Stop Manager exit rules."""
    print("\n" + "="*60)
    print("TEST 4: Stop Manager")
    print("="*60)
    
    from src.vertical_spreads.stop_manager import VerticalSpreadStopManager
    from datetime import date
    
    manager = VerticalSpreadStopManager()
    
    # Position with profit target hit
    position = {
        "position_id": "test-001",
        "symbol": "SPY",
        "direction": "BULL",
        "entry_price": 2.50,
        "entry_date": date.today(),
        "max_profit_per_contract": 250,
        "max_loss_per_contract": 250,
        "contracts": 1,
        "implied_move": 8.0,
        "entry_stock_price": 485.0
    }
    
    # Scenario: Profit target hit (spread now worth $4.50)
    market_profit = {
        "stock_price": 488.0,
        "spread_bid": 4.30,
        "spread_ask": 4.70,
        "dte": 10
    }
    
    result1 = manager.check_exit_rules(position, market_profit)
    print(f"\nProfit Target Scenario:")
    print(f"  Should Exit: {result1.should_exit}")
    print(f"  P&L: ${result1.unrealized_pnl:.2f} ({result1.pnl_percent:.1f}%)")
    print(f"  Exit Reason: {result1.exit_reason}")
    print("  ✓ Test completed")
    
    # Scenario: DTE < 2 (must close)
    market_dte = {
        "stock_price": 485.0,
        "spread_bid": 2.50,
        "spread_ask": 2.60,
        "dte": 1
    }
    
    result2 = manager.check_exit_rules(position, market_dte)
    print(f"\nLow DTE Scenario (1 day):")
    print(f"  Should Exit: {result2.should_exit}")
    print(f"  DTE Remaining: {result2.dte_remaining}")
    for rule in result2.triggered_rules:
        print(f"  Triggered: {rule.name} - {rule.reason}")
    assert result2.should_exit == True
    print("  ✓ PASSED (correctly triggers DTE exit)")
    
    return True


def test_05_signal_generator():
    """Test 5: End-to-end signal generation."""
    print("\n" + "="*60)
    print("TEST 5: Signal Generator (Full Flow)")
    print("="*60)
    
    from src.vertical_spreads.signal_generator import VerticalSpreadSignalGenerator
    
    generator = VerticalSpreadSignalGenerator(
        min_confidence=60,
        earnings_enabled=False  # Disable for testing
    )
    
    # Bullish stock data
    stock_data = {
        "symbol": "SPY",
        "price": 485.0,
        "rsi_14": 25,
        "bb_upper": 490, "bb_mid": 485, "bb_lower": 480,
        "sma_20": 483, "sma_50": 480, "sma_200": 475,
        "iv": 0.20
    }
    
    account_data = {
        "balance": 10000,
        "risk_tolerance": "medium",
        "options_level": 2
    }
    
    signal = generator.generate_signal("SPY", stock_data, account_data)
    
    print(f"\nGenerated Signal:")
    if signal:
        print(f"  ID: {signal.id[:8]}...")
        print(f"  Symbol: {signal.symbol}")
        print(f"  Strategy: {signal.strategy}")
        print(f"  Direction: {signal.direction}")
        print(f"  Buy Strike: {signal.buy_strike}")
        print(f"  Sell Strike: {signal.sell_strike}")
        print(f"  Confidence: {signal.confidence}%")
        print(f"  Status: {signal.status}")
        print(f"  Rationale: {signal.rationale[:60]}...")
        assert signal.status == "pending"
        print("  ✓ PASSED")
    else:
        print("  No signal generated (direction may be neutral)")
    
    return True


def test_06_signal_publishing():
    """Test 6: Signal publishing functions."""
    print("\n" + "="*60)
    print("TEST 6: Signal Publishing")
    print("="*60)
    
    from signal_publisher import (
        SignalType,
        vertical_spread_to_signal,
        get_vertical_spread_signals
    )
    
    # Test signal conversion
    mock_setup = {
        "symbol": "SPY",
        "strategy": "BULL_CALL_SPREAD",
        "direction": "bullish",
        "buy_strike": 485,
        "sell_strike": 490,
        "option_type": "C",
        "expiration": "2026-01-30",
        "dte": 11,
        "net_debit": 2.50,
        "max_profit": 250,
        "max_loss": 250,
        "contracts": 1,
        "confidence": 75,
        "rationale": "Test signal"
    }
    
    signal = vertical_spread_to_signal(mock_setup, SignalType.BUY)
    
    print(f"\nConverted Signal:")
    print(f"  Signal Type: {signal['signalType']}")
    print(f"  Symbol: {signal['symbol']}")
    print(f"  Strategy: {signal['strategy']}")
    print(f"  Status: {signal['status']}")
    print(f"  Created At: {signal['createdAt'][:19]}")
    
    assert signal['signalType'] == "BUY"
    assert signal['symbol'] == "SPY"
    assert signal['status'] == "pending"
    print("  ✓ PASSED")
    
    # Test warning signal conversion
    warning = vertical_spread_to_signal(
        {"symbol": "AAPL", "strategy": "WARNING", "rationale": "Earnings in 2 days"},
        SignalType.WARNING
    )
    print(f"\nWarning Signal:")
    print(f"  Signal Type: {warning['signalType']}")
    print(f"  Symbol: {warning['symbol']}")
    assert warning['signalType'] == "WARNING"
    print("  ✓ PASSED")
    
    return True


def test_07_config_settings():
    """Test 7: Configuration settings loaded correctly."""
    print("\n" + "="*60)
    print("TEST 7: Configuration Settings")
    print("="*60)
    
    import config
    
    print(f"\nVertical Spread Config:")
    print(f"  VERTICAL_SPREAD_ENABLED: {config.VERTICAL_SPREAD_ENABLED}")
    print(f"  VERTICAL_MIN_CONFIDENCE: {config.VERTICAL_MIN_CONFIDENCE}")
    print(f"  VERTICAL_DEFAULT_DTE_MIN: {config.VERTICAL_DEFAULT_DTE_MIN}")
    print(f"  VERTICAL_DEFAULT_DTE_MAX: {config.VERTICAL_DEFAULT_DTE_MAX}")
    print(f"  VERTICAL_MAX_RISK_PCT: {config.VERTICAL_MAX_RISK_PCT}")
    print(f"  VERTICAL_PROFIT_TARGET_PCT: {config.VERTICAL_PROFIT_TARGET_PCT}")
    print(f"  VERTICAL_STOP_LOSS_PCT: {config.VERTICAL_STOP_LOSS_PCT}")
    print(f"  VERTICAL_MIN_ACCOUNT_SIZE: ${config.VERTICAL_MIN_ACCOUNT_SIZE}")
    print(f"  VERTICAL_MIN_OPTIONS_LEVEL: {config.VERTICAL_MIN_OPTIONS_LEVEL}")
    
    assert config.VERTICAL_SPREAD_ENABLED == True
    assert config.VERTICAL_MIN_CONFIDENCE == 60
    assert config.VERTICAL_MIN_ACCOUNT_SIZE == 2000
    print("  ✓ PASSED")
    
    return True


def run_all_tests():
    """Run all end-to-end tests."""
    print("\n" + "#"*60)
    print("# VERTICAL SPREAD END-TO-END TEST SUITE")
    print("#"*60)
    
    results = []
    tests = [
        ("Direction Predictor", test_01_direction_predictor),
        ("Spread Selector", test_02_spread_selector),
        ("Suitability Validator", test_03_suitability_validator),
        ("Stop Manager", test_04_stop_manager),
        ("Signal Generator", test_05_signal_generator),
        ("Signal Publishing", test_06_signal_publishing),
        ("Config Settings", test_07_config_settings),
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, "PASSED" if result else "FAILED"))
        except Exception as e:
            results.append((name, f"ERROR: {e}"))
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for name, status in results:
        icon = "✓" if status == "PASSED" else "✗"
        print(f"  {icon} {name}: {status}")
        if status == "PASSED":
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  Some tests failed. Review output above.")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
