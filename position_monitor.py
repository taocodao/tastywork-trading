"""
Position Monitor - Automated Exit Management
=============================================
Monitors open theta positions and executes exits based on trailing stop logic.

Exit Strategy:
- Start trailing at 50% profit
- Exit if retraces 30% from peak
- Force close after 21 days max hold
"""

import logging
import time
from datetime import datetime, date
from typing import Optional, List

from src.theta_spreads.portfolio_manager import ThetaPortfolioManager, ThetaPosition, PositionStatus
from ib_order_executor import IBOrderExecutor

logger = logging.getLogger(__name__)


class OptimizedExitManager:
    """
    Simple trailing stop exit strategy for IB testing.
    
    Rules:
    1. Activate trailing when profit >= 50%
    2. Exit if retraces 30% from peak
    3. Max hold time: 21 days
    """
    
    def __init__(self):
        # Trailing stop parameters
        self.trailing_activation_pct = 50.0  # Start trailing at 50% profit
        self.trailing_stop_pct = 30.0        # Exit if retraces 30% from peak
        
        # Time backstop
        self.max_hold_days = 21
    
    def should_exit(self, position: ThetaPosition) -> Optional[str]:
        """
        Check if position should exit.
        
        Returns:
            Exit reason string if should close, None otherwise
        """
        # Update peak P&L tracking
        self._update_peak_pnl(position)
        
        # Check trailing stop
        if position.trailing_active:
            retracement = position.peak_pnl_pct - position.unrealized_pnl_pct
            retracement_pct = (
                (retracement / position.peak_pnl_pct) * 100 
                if position.peak_pnl_pct > 0 
                else 0
            )
            
            if retracement_pct >= self.trailing_stop_pct:
                logger.info(
                    f"📉 {position.symbol}: Trailing stop triggered\\n"
                    f"   Peak: {position.peak_pnl_pct:.1f}%\\n"
                    f"   Current: {position.unrealized_pnl_pct:.1f}%\\n"
                    f"   Retracement: {retracement_pct:.1f}%\\n"
                    f"   Threshold: {self.trailing_stop_pct:.1f}%"
                )
                return f"trailing_stop_retraced_{retracement_pct:.0f}pct"
        
        # Time backstop
        if position.days_held >= self.max_hold_days:
            logger.info(
                f"⏰ {position.symbol}: Max hold time reached\\n"
                f"   Days held: {position.days_held}\\n"
                f"   Current P&L: {position.unrealized_pnl_pct:.1f}%"
            )
            return "max_hold_time"
        
        return None
    
    def _update_peak_pnl(self, position: ThetaPosition):
        """Track peak P&L and activate trailing stop."""
        if not hasattr(position, 'peak_pnl_pct'):
            position.peak_pnl_pct = 0.0
            position.trailing_active = False
        
        # Update peak
        if position.unrealized_pnl_pct > position.peak_pnl_pct:
            position.peak_pnl_pct = position.unrealized_pnl_pct
        
        # Activate trailing at threshold
        if position.unrealized_pnl_pct >= self.trailing_activation_pct:
            if not position.trailing_active:
                position.trailing_active = True
                logger.info(
                    f"✅ {position.symbol}: Trailing stop ACTIVATED\\n"
                    f"   Profit: {position.unrealized_pnl_pct:.1f}%\\n"
                    f"   Will exit if retraces {self.trailing_stop_pct:.1f}% from peak"
                )


class PositionMonitor:
    """
    Monitors open theta positions and executes exits.
    Runs every 60 seconds during market hours.
    
    Uses symbol-specific defensive exit logic with optimized parameters:
    - QQQ: Tighter profit targets, earlier DTE exit
    - IWM: Aggressive settings
    - SPY: Balanced approach
    """
    
    def __init__(self, ib_provider, portfolio_manager: ThetaPortfolioManager, ib_executor: IBOrderExecutor):
        self.ib = ib_provider
        self.portfolio = portfolio_manager
        self.executor = ib_executor
        
        # Symbol-specific exit managers (lazy loaded per symbol)
        self.exit_managers = {}
        
        logger.info("Position Monitor initialized with symbol-specific exit logic")
    
    def _get_exit_manager(self, symbol: str):
        """Get or create exit manager for symbol."""
        if symbol not in self.exit_managers:
            try:
                from src.theta_spreads.defensive_exits import create_exit_manager_from_symbol
                self.exit_managers[symbol] = create_exit_manager_from_symbol(symbol)
                logger.info(f"Created symbol-specific exit manager for {symbol}")
            except ImportError:
                # Fallback to old trailing stop if new modules not available
                logger.warning(f"Symbol-specific exits not available, using trailing stop for {symbol}")
                self.exit_managers[symbol] = OptimizedExitManager()
        
        return self.exit_managers[symbol]
    
    def check_all_positions(self):
        """
        Monitor all open positions and execute exits.
        Should be called every 60 seconds during market hours.
        """
        logger.info("=" * 70)
        logger.info("🔍 POSITION MONITORING CHECK")
        logger.info("=" * 70)
        
        open_positions = self.portfolio.get_open_positions()
        
        if not open_positions:
            logger.info("No open positions to monitor")
            logger.info("=" * 70)
            return
        
        logger.info(f"Monitoring {len(open_positions)} open position(s)\\n")
        
        for position in open_positions:
            try:
                self._check_position(position)
            except Exception as e:
                logger.error(f"Error checking {position.symbol}: {e}", exc_info=True)
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info(f"✅ Monitoring complete - {len(open_positions)} position(s) checked")
        logger.info("=" * 70)
    
    def _check_position(self, position: ThetaPosition):
        """Check a single position for exit criteria using symbol-specific logic."""
        logger.info(f"\n--- {position.symbol} {position.strike}P ---")
        
        # Get symbol-specific exit manager
        exit_manager = self._get_exit_manager(position.symbol)
        
        # Fetch current option price
        current_price = self._get_current_price(position)
        
        if current_price is None:
            logger.warning(f"Could not fetch current price for {position.symbol}")
            return
        
        # Update position state
        self.portfolio.update_position_state(position.id, current_price)
        
        # Check symbol-specific exit criteria
        exit_reason = None
        
        # Try defensive exits if available
        if hasattr(exit_manager, 'check_all_exits'):
            # New symbol-specific defensive exit logic
            try:
                # Get current stock price for breach checking
                stock_price = self._get_stock_price(position.symbol)
                
                should_exit, reason, exit_type = exit_manager.check_all_exits(
                    position_id=position.id,
                    symbol=position.symbol,
                    strike=position.strike,
                    current_stock_price=stock_price if stock_price else position.strike * 1.05,
                    days_to_expiration=position.days_to_expiration,
                    current_vix=None  # Could add VIX fetching
                )
                
                if should_exit:
                    exit_reason = f"{exit_type}_{reason}" if exit_type else reason
                    
            except Exception as e:
                logger.warning(f"Defensive exit check failed: {e}, falling back to trailing stop")
                exit_reason = exit_manager.should_exit(position)
        else:
            # Fallback to trailing stop
            exit_reason = exit_manager.should_exit(position)
        
        if exit_reason:
            logger.info(f"🚨 EXIT TRIGGERED: {exit_reason}")
            self._execute_exit(position, exit_reason)
        else:
            # Log monitoring status
            status = getattr(position, 'trailing_active', False)
            status_str = "TRAILING" if status else "MONITORING"
            
            logger.info(
                f"Status: {status_str}\n"
                f"  Entry: ${position.entry_price:.2f} → Current: ${current_price:.2f}\n"
                f"  P&L: {position.unrealized_pnl_pct:+.1f}% (${position.unrealized_pnl:+.2f})\n"
                f"  Peak: {getattr(position, 'peak_pnl_pct', 0):.1f}%\n"
                f"  DTE: {position.days_to_expiration} days | Held: {position.days_held} days"
            )
    
    def _get_stock_price(self, symbol: str) -> Optional[float]:
        """Fetch current stock price for breach checking."""
        try:
            from ib_insync import Stock
            
            stock = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(stock)
            ticker = self.ib.reqMktData(stock, '', False, False)
            
            time.sleep(0.5)
            
            price = ticker.last or ticker.close or ticker.bid
            
            try:
                self.ib.cancelMktData(stock)
            except:
                pass
            
            return price
            
        except Exception as e:
            logger.debug(f"Could not fetch stock price for {symbol}: {e}")
            return None
    
    def _execute_exit(self, position: ThetaPosition, exit_reason: str):
        """Close position by buying back the put, with smart fill monitoring."""
        logger.info(f"\n{'=' * 70}")
        logger.info(f"🔴 EXECUTING EXIT: {position.symbol} {position.strike}P")
        logger.info(f"{'=' * 70}")
        
        # Mark as closing
        position.status = PositionStatus.CLOSING
        position.exit_reason = exit_reason
        self.portfolio.save()
        
        # Execute exit order (buy to close)
        try:
            exit_price = position.current_price
            
            logger.info(
                f"Placing BUY TO CLOSE order:\\n"
                f"  Price: ${exit_price:.2f}\\n"
                f"  Contracts: {position.contracts}\\n"
                f"  Reason: {exit_reason}"
            )
            
            # Place order via IB
            order_id = self.executor.place_theta_exit(
                symbol=position.symbol,
                strike=position.strike,
                expiration=position.expiration,
                contracts=position.contracts,
                exit_price=exit_price,
                dry_run=False  # Real order
            )
            
            if order_id:
                position.exit_order_id = order_id
                logger.info(f"✅ Exit order #{order_id} placed successfully")
                
                # Smart fill monitoring via Tastytrade API
                actual_exit_price = exit_price
                try:
                    from tastytrade_client import TastytradeClient
                    client = TastytradeClient()
                    client.connect()
                    fill_result = client.monitor_and_fill(
                        order_id=str(order_id),
                        initial_price=exit_price,
                        is_credit=False,  # BTC = debit order
                    )
                    client.disconnect()
                    
                    if fill_result.get("filled"):
                        actual_exit_price = fill_result.get("fill_price", exit_price)
                        logger.info(
                            f"✅ Exit order filled @ ${actual_exit_price:.2f} | "
                            f"Adjustments: {fill_result.get('adjustments_made', 0)}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Exit order not filled: {fill_result.get('final_status')} | "
                            f"Using estimated price ${exit_price:.2f}"
                        )
                        # Revert status if not filled
                        position.status = PositionStatus.OPEN
                        self.portfolio.save()
                        return
                        
                except Exception as e:
                    logger.warning(f"Smart fill monitoring unavailable: {e}, using estimated price")
                    # Fallback: wait briefly like before
                    time.sleep(2)
                
                # Finalize position with actual fill price
                self._finalize_exit(position, actual_exit_price)
            else:
                logger.error(f"❌ Failed to place exit order for {position.symbol}")
                # Revert status
                position.status = PositionStatus.OPEN
                self.portfolio.save()
        
        except Exception as e:
            logger.error(f"Error executing exit: {e}", exc_info=True)
            position.status = PositionStatus.OPEN
            self.portfolio.save()
    
    def _finalize_exit(self, position: ThetaPosition, exit_price: float):
        """Record final exit details after fill."""
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.now()
        position.exit_price = exit_price
        
        # Calculate realized P&L
        exit_cost = exit_price * 100 * position.contracts
        position.realized_pnl = position.premium_collected - exit_cost
        position.realized_pnl_pct = (
            (position.realized_pnl / position.premium_collected) * 100
            if position.premium_collected > 0
            else 0
        )
        
        self.portfolio.save()
        
        # Log detailed exit summary
        logger.info(f"\\n{'=' * 70}")
        logger.info("📊 POSITION CLOSED")
        logger.info(f"{'=' * 70}")
        logger.info(
            f"Symbol: {position.symbol} {position.strike}P\\n"
            f"\\n"
            f"Entry Details:\\n"
            f"  Price: ${position.entry_price:.2f}\\n"
            f"  Premium Collected: ${position.premium_collected:.2f}\\n"
            f"  Opened: {position.opened_at.strftime('%Y-%m-%d %H:%M')}\\n"
            f"\\n"
            f"Exit Details:\\n"
            f"  Price: ${exit_price:.2f}\\n"
            f"  Exit Cost: ${exit_cost:.2f}\\n"
            f"  Reason: {position.exit_reason}\\n"
            f"  Closed: {position.closed_at.strftime('%Y-%m-%d %H:%M')}\\n"
            f"\\n"
            f"Performance:\\n"
            f"  Realized P&L: ${position.realized_pnl:+.2f} ({position.realized_pnl_pct:+.1f}%)\\n"
            f"  Peak Profit: {position.peak_pnl_pct:.1f}%\\n"
            f"  Days Held: {position.days_held}\\n"
        )
        logger.info(f"{'=' * 70}\\n")
    
    def _get_current_price(self, position: ThetaPosition) -> Optional[float]:
        """Fetch current ask price for the put option."""
        try:
            # Create option contract
            from ib_insync import Option
            
            contract = Option(
                symbol=position.symbol,
                lastTradeDateOrContractMonth=position.expiration.replace('-', ''),
                strike=position.strike,
                right='P',
                exchange='SMART',
                currency='USD'
            )
            
            # Request market data
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract, '', False, False)
            
            # Wait for data
            time.sleep(1)
            
            # Get ask price (we're buying to close)
            if ticker.ask and ticker.ask > 0:
                return ticker.ask
            elif ticker.last and ticker.last > 0:
                return ticker.last
            elif ticker.close and ticker.close > 0:
                return ticker.close
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching price for {position.symbol}: {e}")
            return None
        finally:
            # Cancel market data
            try:
                self.ib.cancelMktData(contract)
            except:
                pass
"""
<parameter name="Complexity">7
