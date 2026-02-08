#!/usr/bin/env python3
"""
IB Paper Trade Test Script
===========================
Forces trade submission bypassing confidence checks for testing.
Submits both theta puts and calendar spreads.

Usage: python3 force_test_trades.py
"""

import logging
import sys
from datetime import datetime, timedelta, date

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def submit_theta_trades():
    """Force submit theta trades bypassing confidence check."""
    logger.info("=" * 70)
    logger.info("THETA TRADES - FORCED TEST MODE")
    logger.info("=" * 70)
    
    try:
        from ib_data_provider import IBDataProvider
        from ib_order_executor import IBOrderExecutor
        from src.theta_spreads import SymbolSelector, OptionsAnalyzer
        # signal_publisher not needed for IB paper testing
        import config
        
        # Connect to IB
        ib = IBDataProvider()
        ib.connect()
        logger.info("✅ Connected to IB Gateway")
        
        try:
            # Step 1: Symbol Selection
            logger.info("[1/4] Selecting symbols...")
            selector = SymbolSelector(min_iv_percentile=0, select_top_n=5)  # Lower threshold
            
            # Use ETF universe
            symbols = ['SPY', 'QQQ', 'IWM']  # Focus on liquid ETFs
            logger.info(f"  Using symbols: {symbols}")
            
            # Step 2: Options Analysis
            logger.info("[2/4] Analyzing options chains...")
            analyzer = OptionsAnalyzer(
                target_delta=0.30,
                delta_tolerance=0.10,  # Wider tolerance
                dte_min=7,
                dte_max=45,
                min_premium=0.10,  # Lower min premium
                confidence_threshold=0  # DISABLED for testing
            )
            
            target_date = date.today() + timedelta(days=30)
            
            all_puts = []
            for symbol in symbols:
                try:
                    puts = ib.get_put_chain_for_theta(symbol, target_date, 0.20, 0.40)
                    if puts:
                        scored = analyzer.analyze_symbol(symbol, 50, puts)  # Use 50 IV rank
                        all_puts.extend(scored)
                        logger.info(f"  {symbol}: {len(scored)} puts found")
                except Exception as e:
                    logger.warning(f"  {symbol}: Error - {e}")
            
            logger.info(f"  Total puts found: {len(all_puts)}")
            
            if not all_puts:
                logger.warning("No puts found! Check IB connection and market hours.")
                return 0
            
            # Step 3: Force generate signals (bypass confidence)
            logger.info("[3/4] FORCE generating signals (no confidence check)...")
            
            # Sort by score and take top 3
            all_puts.sort(key=lambda x: x.total_score, reverse=True)
            top_puts = all_puts[:3]
            
            for put in top_puts:
                logger.info(f"  Selected: {put.symbol} ${put.strike}P score={put.total_score:.1f}")
            
            # Step 4: Execute trades
            logger.info("[4/4] Placing IB orders...")
            executor = IBOrderExecutor(ib)
            
            executed_count = 0
            for put in top_puts:
                try:
                    # Create signal-like object
                    class FakeSignal:
                        def __init__(self, p):
                            self.symbol = p.symbol
                            self.strike = p.strike
                            # Convert expiration to string format YYYY-MM-DD
                            if hasattr(p.expiration, 'strftime'):
                                self.expiration = p.expiration.strftime('%Y-%m-%d')
                            else:
                                self.expiration = str(p.expiration)
                            self.entry_price = p.bid
                            self.delta = p.delta
                            self.contracts = 1  # Just 1 for testing
                            self.total_premium = p.bid * 100
                            self.total_capital_required = p.strike * 100
                    
                    signal = FakeSignal(put)
                    
                    # Publish to WebSocket
                    # publish_theta_entry_signal(signal)
                    
                    # Execute on IB
                    order_id = executor.place_theta_entry(signal, dry_run=False)
                    if order_id:
                        executed_count += 1
                        logger.info(f"  ✅ Order #{order_id}: SELL {put.symbol} ${put.strike}P @ ${put.bid:.2f}")
                    
                except Exception as e:
                    logger.error(f"  ❌ Failed: {put.symbol} - {e}")
            
            logger.info("=" * 70)
            logger.info(f"✅ THETA TEST COMPLETE: {executed_count} orders placed")
            logger.info("=" * 70)
            return executed_count
            
        finally:
            ib.disconnect()
            
    except Exception as e:
        logger.error(f"❌ Theta test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0


def submit_calendar_trades():
    """Force submit calendar spread trades."""
    logger.info("=" * 70)
    logger.info("CALENDAR SPREADS - FORCED TEST MODE")
    logger.info("=" * 70)
    
    try:
        from ib_data_provider import IBDataProvider
        from datetime import date, timedelta
        
        # Connect to IB
        ib = IBDataProvider()
        ib.connect()
        logger.info("✅ Connected to IB Gateway")
        
        try:
            symbols = ['SPY', 'QQQ', 'IWM']
            executed_count = 0
            
            # Import executor
            from ib_order_executor import IBOrderExecutor
            executor = IBOrderExecutor(ib)
            
            for symbol in symbols:
                logger.info(f"\nScanning {symbol} for calendar spreads...")
                
                try:
                    # Get current price
                    price = ib.get_price(symbol)
                    if not price:
                        logger.warning(f"  Cannot get price for {symbol}")
                        continue
                    
                    logger.info(f"  Current price: ${price:.2f}")
                    
                    # Calculate ATM strike
                    atm_strike = round(price / 5) * 5  # Round to nearest $5
                    
                    # Calculate expirations - find valid Fridays
                    today = date.today()
                    
                    # Front expiry: Next Friday or Friday after (~7-14 DTE)
                    days_until_friday = (4 - today.weekday()) % 7  # 4 = Friday
                    if days_until_friday < 2:  # Too close, get next Friday
                        days_until_friday += 7
                    front_expiry = today + timedelta(days=days_until_friday)
                    
                    # Back expiry: ~4-5 weeks out, find a Friday
                    back_target = today + timedelta(days=35)
                    days_to_friday = (4 - back_target.weekday()) % 7
                    back_expiry = back_target + timedelta(days=days_to_friday)
                    
                    # Format as YYYYMMDD
                    front_str = front_expiry.strftime('%Y%m%d')
                    back_str = back_expiry.strftime('%Y%m%d')
                    
                    logger.info(f"  Strike: ${atm_strike}, Front: {front_str}, Back: {back_str}")
                    
                    # Execute calendar spread order
                    logger.info(f"  📋 Placing: SELL {symbol} {front_str} ${atm_strike}C / BUY {symbol} {back_str} ${atm_strike}C")
                    
                    order_id = executor.place_calendar_spread(
                        symbol=symbol,
                        strike=atm_strike,
                        front_expiry=front_str,
                        back_expiry=back_str,
                        quantity=1,
                        net_debit=None,  # Market order for testing
                        dry_run=False
                    )
                    
                    if order_id:
                        executed_count += 1
                        logger.info(f"  ✅ Calendar Order #{order_id} placed!")
                    else:
                        logger.warning(f"  ⚠️ Order placement returned None")
                    
                except Exception as e:
                    logger.warning(f"  Error with {symbol}: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
            
            logger.info("=" * 70)
            logger.info(f"✅ CALENDAR SPREAD COMPLETE: {executed_count} orders placed")
            logger.info("=" * 70)
            return executed_count
            
        finally:
            ib.disconnect()
            
    except Exception as e:
        logger.error(f"❌ Calendar test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0


if __name__ == "__main__":
    logger.info("🚀 IB PAPER TRADE TEST - STARTING")
    logger.info(f"Time: {datetime.now()}")
    logger.info("")
    
    # Run theta trades
    theta_count = submit_theta_trades()
    
    logger.info("")
    
    # Run calendar spreads
    calendar_count = submit_calendar_trades()
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info(f"  Theta Orders: {theta_count}")
    logger.info(f"  Calendar Orders: {calendar_count}")
    logger.info("=" * 70)
