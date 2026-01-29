"""
Quick Theta Strategy Test with IB Gateway
==========================================

This script tests the core workflow:
1. Connect to IB Gateway
2. Select watchlist symbols
3. Analyze options chains
4. Generate entry signals
5. Print results

Run: python scripts/quick_theta_test.py
"""

import sys
import os
from datetime import date, timedelta

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging to file
import logging
log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'theta_test_output.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Log file: {log_file}")


def main():
    print("="*70)
    print("THETA STRATEGY - QUICK TEST WITH IB GATEWAY")
    print("="*70)
    
    # Import components individually to avoid scheduler dependency
    from src.theta_spreads.symbol_selector import SymbolSelector
    from src.theta_spreads.options_analyzer import OptionsAnalyzer
    from src.theta_spreads.signal_generator import ThetaSignalGenerator
    from src.theta_spreads.portfolio_manager import ThetaPortfolioManager
    from ib_data_provider import IBDataProvider
    import config
    
    # Step 1: Connect to IB Gateway
    print("\n[1/5] Connecting to IB Gateway...")
    ib = IBDataProvider()
    
    if not ib.connect(timeout=10):
        print("❌ Failed to connect to IB Gateway")
        print("   Make sure IB Gateway is running at", ib.host, ":", ib.port)
        return
    
    print("✅ Connected to IB Gateway")
    
    try:
        # Step 2: Symbol Selection (quick test with 5 symbols)
        print("\n[2/5] Selecting test symbols...")
        test_symbols = ["SPY", "QQQ", "IWM", "TLT", "GLD"]
        selector = SymbolSelector(select_top_n=3)
        
        # Get scores for test symbols
        selected = []
        for symbol in test_symbols:
            try:
                price = ib.get_price(symbol)
                if price > 0:
                    iv = ib.get_atm_iv(symbol, days_out=30)
                    iv_pct = ib.get_iv_percentile(iv, symbol)
                    print(f"  {symbol}: ${price:.2f}, IV: {iv*100:.1f}%, IV%: {iv_pct:.0f}")
                    selected.append(symbol)
            except Exception as e:
                print(f"  {symbol}: Error - {e}")
        
        if not selected:
            print("❌ No symbols available")
            return
        
        print(f"✅ Selected: {selected}")
        
        # Step 3: Options Analysis
        print("\n[3/5] Analyzing options chains...")
        analyzer = OptionsAnalyzer(
            target_delta=0.30,
            delta_tolerance=0.05,
            dte_min=7,      # More flexible for testing
            dte_max=45,     # More flexible for testing
            min_premium=config.THETA_MIN_PREMIUM,
            confidence_threshold=50  # Lower for testing
        )
        
        # Get target expiry - use simple date arithmetic instead of third Friday logic
        from datetime import timedelta
        target_date = date.today() + timedelta(days=30)  # ~30 days out
        print(f"  Target expiration: ~{target_date}")
        
        all_puts = []
        for symbol in selected[:3]:  # Test with first 3
            try:
                print(f"  Fetching puts for {symbol}...")
                puts = ib.get_put_chain_for_theta(symbol, target_date, 0.20, 0.40)  # Wider delta range
                print(f"    -> Got {len(puts)} raw puts")
                if puts:
                    # Show sample puts
                    for p in puts[:3]:
                        print(f"       {p['strike']}P @ ${p['bid']:.2f}/${p['ask']:.2f} delta={p['delta']:.2f}")
                    scored = analyzer.analyze_symbol(symbol, 80, puts)
                    all_puts.extend(scored)
                    print(f"    -> {len(scored)} qualified puts after scoring")
            except Exception as e:
                print(f"  {symbol}: Error - {e}")
                import traceback
                traceback.print_exc()
        
        if not all_puts:
            print("❌ No qualified puts found")
            print("   (This may be normal if market is closed or IV is low)")
            return
        
        # Sort by score
        all_puts.sort(key=lambda x: x.total_score, reverse=True)
        print(f"\n✅ Found {len(all_puts)} qualified puts")
        
        # Show top 3
        print("\nTop Puts:")
        for i, put in enumerate(all_puts[:3], 1):
            print(f"  {i}. {put.symbol} {put.strike}P exp {put.expiration} | "
                  f"Score: {put.total_score} | Bid: ${put.bid:.2f}")
        
        # Step 4: Generate Entry Signals
        print("\n[4/5] Generating entry signals...")
        generator = ThetaSignalGenerator(
            contracts_per_trade=config.THETA_CONTRACTS_PER_TRADE,
            max_positions=config.THETA_MAX_POSITIONS,
            min_confidence=50  # Lower for testing
        )
        
        portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
        state = portfolio.get_portfolio_state()
        
        portfolio_dict = {
            "available_capital": state.available_capital,
            "current_heat": state.current_heat,
            "open_positions": state.open_symbols,
            "position_count": state.position_count
        }
        
        signals = generator.generate_entry_signals(all_puts, portfolio_dict)
        
        if signals:
            print(f"\n✅ Generated {len(signals)} entry signals:")
            for sig in signals:
                print(f"\n   📊 {sig.symbol} {sig.strike}P")
                print(f"      Expiration: {sig.expiration}")
                print(f"      Entry Price: ${sig.entry_price:.2f}")
                print(f"      Contracts: {sig.contracts}")
                print(f"      Total Premium: ${sig.total_premium:.0f}")
                print(f"      Capital Required: ${sig.total_capital_required:,.0f}")
                print(f"      Confidence: {sig.confidence}%")
        else:
            print("   No signals generated (may need to adjust thresholds)")
        
        # Step 5: Summary
        print("\n" + "="*70)
        print("[5/5] TEST COMPLETE")
        print("="*70)
        print(f"\nPortfolio Status:")
        print(f"  Total Capital: ${state.total_capital:,.0f}")
        print(f"  Available: ${state.available_capital:,.0f}")
        print(f"  Open Positions: {state.position_count}")
        
        if signals:
            print(f"\n🎯 {len(signals)} signals ready for approval!")
            print("   Use API: POST /signals/theta/{id}/approve")
        
    finally:
        ib.disconnect()
        print("\n✅ Disconnected from IB Gateway")


if __name__ == "__main__":
    main()
