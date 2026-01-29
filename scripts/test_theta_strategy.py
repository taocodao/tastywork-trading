"""
Theta Strategy Example Usage
=============================

This script demonstrates how to use the Theta strategy components.

Run this to:
1. Select daily watchlist (top 12 symbols)
2. Analyze options chains
3. Generate entry signals
4. Track portfolio state
5. Generate exit signals

Usage:
    python scripts/test_theta_strategy.py
"""

import logging
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.theta_spreads import (
    SymbolSelector,
    OptionsAnalyzer,
    ThetaSignalGenerator,
    ThetaPortfolioManager,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mock_market_data(symbol: str) -> Dict:
    """Create mock market data for testing."""
    # In production, this would come from IB Gateway
    import random
    
    return {
        "price": random.uniform(50, 500),
        "volume": random.randint(1_000_000, 10_000_000),
        "iv_percentile": random.uniform(20, 80),
        "bid_ask_spread_pct": random.uniform(0.02, 0.10),
        "trend": random.choice(["UPTREND", "SIDEWAYS", "DOWNTREND"]),
        "price_vs_sma200": random.uniform(0.95, 1.15),
        "rsi": random.uniform(30, 70),
        "puts_30delta_count": random.randint(1, 3),
    }


def create_mock_options_chain(symbol: str, stock_price: float) -> List[Dict]:
    """Create mock options chain for testing."""
    # In production, this would come from IB Gateway
    import random
    from datetime import timedelta
    
    options = []
    expiration = date.today() + timedelta(days=30)
    
    # Create puts at various strikes around current price
    for strike_offset in range(-20, 5, 5):
        strike = round(stock_price + strike_offset)
        delta = abs(random.uniform(0.20, 0.40))
        
        options.append({
            "strike": strike,
            "expiration": expiration,
            "bid": random.uniform(0.50, 3.00),
            "ask": random.uniform(0.55, 3.20),
            "delta": delta,
            "theta": -random.uniform(0.04, 0.12),
            "vega": random.uniform(0.15, 0.30),
            "gamma": random.uniform(0.01, 0.05),
            "iv": random.uniform(0.20, 0.50),
            "volume": random.randint(50, 1000),
            "open_interest": random.randint(100, 5000),
        })
    
    return options


def main():
    """Run Theta strategy example."""
    logger.info("="*80)
    logger.info("THETA STRATEGY - EXAMPLE USAGE")
    logger.info("="*80)
    
    # Step 1: Symbol Selection
    logger.info("\n" + "="*80)
    logger.info("STEP 1: SYMBOL SELECTION")
    logger.info("="*80)
    
    selector = SymbolSelector(
        min_iv_percentile=20,
        min_volume=100_000,
        select_top_n=12
    )
    
    # Mock: Select from subset of universe
    candidates = selector.UNIVERSE[:20]  # Test with first 20 symbols
    watchlist = selector.select_daily_watchlist(candidates=candidates)
    
    logger.info(f"\nSelected watchlist: {watchlist}")
    
    # Step 2: Options Analysis
    logger.info("\n" + "="*80)
    logger.info("STEP 2: OPTIONS CHAIN ANALYSIS")
    logger.info("="*80)
    
    analyzer = OptionsAnalyzer(
        target_delta=0.30,
        delta_tolerance=0.05,
        min_confidence=60
    )
    
    all_scored_puts = []
    
    for symbol in watchlist[:5]:  # Analyze first 5 symbols
        market_data = create_mock_market_data(symbol)
        symbol_score = 75  # Mock score
        
        options_chain = create_mock_options_chain(symbol, market_data["price"])
        scored_puts = analyzer.analyze_symbol(symbol, symbol_score, options_chain)
        
        all_scored_puts.extend(scored_puts)
    
    # Rank all puts
    all_scored_puts.sort(key=lambda x: x.total_score, reverse=True)
    logger.info(f"\nTotal qualified puts: {len(all_scored_puts)}")
    
    if all_scored_puts:
        logger.info(f"Top put: {all_scored_puts[0].symbol} {all_scored_puts[0].strike}P @ {all_scored_puts[0].total_score} confidence")
    
    # Step 3: Generate Entry Signals
    logger.info("\n" + "="*80)
    logger.info("STEP 3: ENTRY SIGNAL GENERATION")
    logger.info("="*80)
    
    generator = ThetaSignalGenerator(
        contracts_per_trade=10,
        max_positions=6,
        max_portfolio_heat=50000,
        min_confidence=60
    )
    
    # Mock portfolio state
    portfolio_state = {
        "available_capital": 100000,
        "current_heat": 0,
        "open_positions": [],
        "position_count": 0,
    }
    
    entry_signals = generator.generate_entry_signals(all_scored_puts, portfolio_state)
    
    logger.info(f"\nGenerated {len(entry_signals)} entry signals")
    
    # Step 4: Portfolio Management
    logger.info("\n" + "="*80)
    logger.info("STEP 4: PORTFOLIO MANAGEMENT")
    logger.info("="*80)
    
    portfolio_manager = ThetaPortfolioManager(total_capital=100000)
    
    # Simulate adding positions from entry signals
    if entry_signals:
        for signal in entry_signals[:3]:  # Add first 3
            position = portfolio_manager.add_position(
                symbol=signal.symbol,
                strike=signal.strike,
                expiration=signal.expiration,
                entry_price=signal.entry_price,
                contracts=signal.contracts,
                delta=signal.delta,
                theta=signal.theta,
                vega=signal.vega,
                iv=signal.iv
            )
            logger.info(f"Added position: {position.symbol} {position.strike}P")
    
    # Check portfolio state
    state = portfolio_manager.get_portfolio_state()
    logger.info(f"\nPortfolio State:")
    logger.info(f"  Total Capital: ${state.total_capital:,.0f}")
    logger.info(f"  Reserved: ${state.reserved_capital:,.0f}")
    logger.info(f"  Available: ${state.available_capital:,.0f}")
    logger.info(f"  Positions: {state.position_count}")
    logger.info(f"  Heat: {state.heat_pct:.1f}%")
    
    # Step 5: Exit Signal Generation
    logger.info("\n" + "="*80)
    logger.info("STEP 5: EXIT SIGNAL GENERATION")
    logger.info("="*80)
    
    # Mock: Update position Greeks and generate exits
    open_positions = []
    for position in portfolio_manager.get_all_positions():
        # Simulate position with some profit
        pos_dict = {
            "position_id": position.position_id,
            "symbol": position.symbol,
            "strike": position.strike,
            "entry_price": position.entry_price,
            "entry_date": position.entry_date,
            "expiration": position.expiration,
            "contracts": position.contracts,
            "current_bid": position.entry_price * 0.5,  # Mock 50% profit
            "current_ask": position.entry_price * 0.5,
        }
        open_positions.append(pos_dict)
    
    exit_signals = generator.generate_exit_signals(open_positions)
    logger.info(f"\nGenerated {len(exit_signals)} exit signals")
    
    # Step 6: Signal Publishing (mock)
    if entry_signals or exit_signals:
        logger.info("\n" + "="*80)
        logger.info("STEP 6: SIGNAL PUBLISHING")
        logger.info("="*80)
        
        try:
            from signal_publisher import publish_theta_entry_signal, publish_theta_exit_signal
            
            # Publish entry signals
            for signal in entry_signals:
                logger.info(f"Would publish entry: {signal.symbol} {signal.strike}P @ ${signal.entry_price:.2f}")
                # publish_theta_entry_signal(signal)  # Uncomment to actually publish
            
            # Publish exit signals
            for signal in exit_signals:
                logger.info(f"Would publish exit: {signal.symbol} {signal.strike}P (P&L: {signal.unrealized_pnl_pct:.1f}%)")
                # publish_theta_exit_signal(signal)  # Uncomment to actually publish
                
        except Exception as e:
            logger.warning(f"Signal publishing skipped: {e}")
    
    logger.info("\n" + "="*80)
    logger.info("EXAMPLE COMPLETE")
    logger.info("="*80)
    logger.info("\nTo integrate with IB Gateway:")
    logger.info("1. Replace mock data with ib_data_provider.get_options()")
    logger.info("2. Replace mock portfolio with actual tasty account data")
    logger.info("3. Uncomment signal publishing calls")
    logger.info("4. Add scheduler for automated execution (see scheduler.py)")
    

if __name__ == "__main__":
    main()
