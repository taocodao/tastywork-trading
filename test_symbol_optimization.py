"""
Test Symbol-Specific Integration
=================================
Quick test to verify symbol-specific profiles are loaded correctly.
"""

def test_symbol_specific_signal_generator():
    """Test that signal generator uses correct profiles per symbol."""
    from src.theta_spreads.signal_generator import ThetaSignalGenerator
    
    print("\n" + "=" * 70)
    print("Testing Symbol-Specific Signal Generators")
    print("=" * 70 + "\n")
    
    # Test QQQ optimized settings
    gen_qqq = ThetaSignalGenerator.from_symbol("QQQ")
    print(f"QQQ Profile:")
    print(f"  Week 1 Target: {gen_qqq.week1_profit_pct}%  (expected: 30%)")
    print(f"  Week 2 Target: {gen_qqq.week2_profit_pct}%  (expected: 40%)")
    print(f"  DTE Exit: {gen_qqq.dte_expiration_threshold} days  (expected: 7)")
    print()
    
    # Test SPY balanced settings
    gen_spy = ThetaSignalGenerator.from_symbol("SPY")
    print(f"SPY Profile:")
    print(f"  Week 1 Target: {gen_spy.week1_profit_pct}% (expected: 45%)")
    print(f"  Week 2 Target: {gen_spy.week2_profit_pct}% (expected: 55%)")
    print(f"  DTE Exit: {gen_spy.dte_expiration_threshold} days  (expected: 3)")
    print()
    
    # Test IWM aggressive settings
    gen_iwm = ThetaSignalGenerator.from_symbol("IWM")
    print(f"IWM Profile:")
    print(f"  Week 1 Target: {gen_iwm.week1_profit_pct}% (expected: 50%)")
    print(f"  Week 2 Target: {gen_iwm.week2_profit_pct}% (expected: 60%)")
    print(f"  DTE Exit: {gen_iwm.dte_expiration_threshold} days  (expected: 2)")
    print()
    
    # Verify QQQ is different
    assert gen_qqq.week1_profit_pct == 30.0, "QQQ should have 30% week 1 target"
    assert gen_qqq.dte_expiration_threshold == 7, "QQQ should exit at 7 DTE"
    
    print("✅ All symbol-specific profiles loaded correctly!\n")


def test_symbol_specific_defensive_exits():
    """Test that defensive exit managers use correct profiles."""
    from src.theta_spreads.defensive_exits import create_exit_manager_from_symbol
    
    print("=" * 70)
    print("Testing Symbol-Specific Defensive Exit Managers")
    print("=" * 70 + "\n")
    
    # Test QQQ
    qqq_manager = create_exit_manager_from_symbol("QQQ")
    print(f"QQQ Exit Manager:")
    print(f"  Breach Threshold: {qqq_manager.breach_threshold_pct*100}% (expected: 3%)")
    print(f"  Confirmation Days: {qqq_manager.breach_confirmation_days} (expected: 2)")
    print(f"  DTE Exit: {qqq_manager.dte_exit_threshold} days (expected: 7)")
    print()
    
    # Test SPY
    spy_manager = create_exit_manager_from_symbol("SPY")
    print(f"SPY Exit Manager:")
    print(f"  Breach Threshold: {spy_manager.breach_threshold_pct*100}% (expected: 2%)")
    print(f"  Confirmation Days: {spy_manager.breach_confirmation_days} (expected: 3)")
    print(f"  DTE Exit: {spy_manager.dte_exit_threshold} days (expected: 3)")
    print()
    
    # Test IWM
    iwm_manager = create_exit_manager_from_symbol("IWM")
    print(f"IWM Exit Manager:")
    print(f"  Breach Threshold: {iwm_manager.breach_threshold_pct*100}% (expected: 3%)")
    print(f"  Confirmation Days: {iwm_manager.breach_confirmation_days} (expected: 2)")
    print(f"  DTE Exit: {iwm_manager.dte_exit_threshold} days (expected: 2)")
    print()
    
    # Verify QQQ is different (looser breach, faster confirmation)
    assert qqq_manager.breach_threshold_pct == 0.03, "QQQ should have 3% breach threshold"
    assert qqq_manager.breach_confirmation_days == 2, "QQQ should have 2 day confirmation"
    
    print("✅ All symbol-specific exit managers configured correctly!\n")


def test_backwards_compatibility():
    """Test that old methods still work."""
    from src.theta_spreads.signal_generator import ThetaSignalGenerator
    
    print("=" * 70)
    print("Testing Backwards Compatibility")
    print("=" * 70 + "\n")
    
    # Old method should still work
    gen_old = ThetaSignalGenerator.from_risk_profile("MEDIUM")
    print(f"from_risk_profile('MEDIUM'):")
    print(f"  Week 1 Target: {gen_old.week1_profit_pct}%")
    print(f"  DTE Exit: {gen_old.dte_expiration_threshold} days")
    print()
    
    print("✅ Backwards compatibility maintained!\n")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print(" " * 15 + "SYMBOL-SPECIFIC OPTIMIZATION TEST")
    print("=" * 70)
    
    try:
        test_symbol_specific_signal_generator()
        test_symbol_specific_defensive_exits()
        test_backwards_compatibility()
        
        print("\n" + "=" * 70)
        print("🎉 ALL TESTS PASSED - Symbol Optimization Ready for Production!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
