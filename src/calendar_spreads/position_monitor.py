"""
Position Monitoring Service for Calendar Spreads.

This service periodically checks open positions and applies risk management rules:
- Profit targets
- Stop losses
- DTE alerts (close before front month expires)
- Price movement alerts

It can run in alert-only mode or auto-exit mode.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from src.earnings_intelligence.database import PositionRepository, Position
from src.calendar_spreads.stop_manager import CalendarSpreadStopManager, ExitAnalysis

logger = logging.getLogger(__name__)


@dataclass
class MonitorConfig:
    """Configuration for position monitoring."""
    check_interval_seconds: int = 60  # How often to check positions
    auto_exit_enabled: bool = False  # If True, auto-close positions on exit signals
    alert_callback: Optional[Callable[[Position, ExitAnalysis], None]] = None
    exit_callback: Optional[Callable[[Position, ExitAnalysis], None]] = None


class PositionMonitor:
    """
    Background service for monitoring calendar spread positions.
    
    Responsibilities:
    - Periodically fetch open positions from database
    - Get current pricing for each position
    - Apply CalendarSpreadStopManager rules
    - Trigger alerts or auto-exit based on configuration
    """
    
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.stop_manager = CalendarSpreadStopManager()
        self.pos_repo = PositionRepository()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the monitoring loop."""
        if self._running:
            logger.warning("Position monitor already running")
            return
            
        self._running = True
        logger.info("Starting position monitor...")
        
        self._task = asyncio.create_task(self._monitor_loop())
        
    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Position monitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_all_positions()
            except Exception as e:
                logger.error(f"Error in position monitor: {e}")
                import traceback
                traceback.print_exc()
            
            await asyncio.sleep(self.config.check_interval_seconds)
            
    async def _check_all_positions(self):
        """Check all open positions."""
        positions = self.pos_repo.get_open_positions()
        
        if not positions:
            return
            
        logger.info(f"Checking {len(positions)} open positions...")
        
        for position in positions:
            try:
                await self._check_position(position)
            except Exception as e:
                logger.error(f"Error checking position {position.id}: {e}")
                
    async def _check_position(self, position: Position):
        """
        Check a single position against risk rules.
        
        Args:
            position: The position to check
        """
        # Get current pricing
        current_value = await self._get_current_spread_value(position)
        
        if current_value is None:
            logger.warning(f"Could not get pricing for position {position.id}")
            return
            
        # Update position in database
        pnl = position.calculate_pnl(current_value)
        self.pos_repo.update_position_value(
            position_id=position.id,
            current_value=current_value,
            unrealized_pnl=pnl
        )
        
        # Get current stock price
        current_stock_price = await self._get_current_stock_price(position.symbol)
        
        # Analyze against exit rules
        analysis = self.stop_manager.analyze_position(
            entry_debit=position.entry_debit,
            current_spread_value=current_value,
            current_stock_price=current_stock_price,
            strike_price=position.strike,
            front_expiry=position.front_expiry.date() if position.front_expiry else None,
            entry_stock_price=position.entry_stock_price
        )
        
        if analysis.should_exit:
            logger.warning(
                f"EXIT SIGNAL for {position.symbol}: "
                f"{analysis.triggered_rule} - {analysis.exit_reason}"
            )
            
            # Trigger alert callback
            if self.config.alert_callback:
                self.config.alert_callback(position, analysis)
                
            # Auto-exit if enabled
            if self.config.auto_exit_enabled:
                await self._execute_exit(position, analysis)
        else:
            logger.debug(
                f"Position {position.symbol} OK: "
                f"P&L ${pnl:.2f}, Value ${current_value:.2f}"
            )
            
    async def _get_current_spread_value(self, position: Position) -> Optional[float]:
        """
        Get current market value for the calendar spread.
        
        Primary: IB Gateway (already connected and subscribed)
        Fallback: Tastytrade API
        
        Returns:
            Current spread mid-price per contract
        """
        # Try IB Gateway first (primary source)
        try:
            spread_value = await self._get_ib_spread_value(position)
            if spread_value is not None:
                return spread_value
        except Exception as e:
            logger.warning(f"IB pricing failed: {e}")
            
        # Fallback to Tastytrade
        try:
            return await self._get_tastytrade_spread_value(position)
        except Exception as e:
            logger.warning(f"Tastytrade pricing failed: {e}")
            
        return None
        
    async def _get_tastytrade_spread_value(self, position: Position) -> Optional[float]:
        """Get spread value using Tastytrade market data."""
        try:
            from tastytrade import Session
            from tastytrade.dxfeed import DXFeed
            import os
            
            # Create session
            username = os.getenv('TASTYTRADE_USERNAME')
            password = os.getenv('TASTYTRADE_PASSWORD')
            
            if not username or not password:
                return None
                
            session = Session(username, password, remember_me=True)
            
            # Get quotes for both legs
            symbols = [position.front_symbol, position.back_symbol]
            
            # Use DXFeed for real-time quotes
            async with DXFeed(session).create_quote_subscription(symbols) as sub:
                quotes = await asyncio.wait_for(sub.get_event_async(), timeout=5.0)
                
            if len(quotes) >= 2:
                front_quote = next((q for q in quotes if q.event_symbol == position.front_symbol), None)
                back_quote = next((q for q in quotes if q.event_symbol == position.back_symbol), None)
                
                if front_quote and back_quote:
                    # Spread value = back mid - front mid
                    # (We're long back, short front)
                    front_mid = (front_quote.bid + front_quote.ask) / 2
                    back_mid = (back_quote.bid + back_quote.ask) / 2
                    return back_mid - front_mid
                    
        except Exception as e:
            logger.debug(f"Tastytrade quote error: {e}")
            
        return None
        
    async def _get_ib_spread_value(self, position: Position) -> Optional[float]:
        """Get spread value using IB Gateway."""
        try:
            from ib_data_provider import IBDataProvider
            
            # Connect to IB Gateway
            provider = IBDataProvider()
            if not provider._connected:
                provider.connect()
                
            if not provider._connected:
                logger.warning("Could not connect to IB Gateway")
                return None
                
            # Fetch option prices for both legs
            front_data = provider.get_option_price_by_symbol(position.front_symbol)
            back_data = provider.get_option_price_by_symbol(position.back_symbol)
            
            if not front_data or not back_data:
                logger.warning(f"Could not get prices for calendar spread legs")
                return None
            
            # Extract mid prices
            front_mid = front_data[2]  # (bid, ask, mid)
            back_mid = back_data[2]
            
            # Calendar spread value = long leg - short leg
            # We're long the back month, short the front month
            spread_value = back_mid - front_mid
            
            logger.debug(
                f"IB Pricing: {position.symbol} spread = ${spread_value:.2f} "
                f"(back ${back_mid:.2f} - front ${front_mid:.2f})"
            )
            
            return spread_value
            
        except Exception as e:
            logger.debug(f"IB quote error: {e}")
            return None
        
    async def _get_current_stock_price(self, symbol: str) -> Optional[float]:
        """Get current stock price for the underlying."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if not data.empty:
                return float(data['Close'].iloc[-1])
        except Exception as e:
            logger.debug(f"Could not get stock price for {symbol}: {e}")
            
        return None
        
    async def _execute_exit(self, position: Position, analysis: ExitAnalysis):
        """
        Execute an exit order for the position.
        
        This calls the close position API endpoint or directly
        places the closing order.
        """
        logger.info(f"Auto-exiting position {position.id}: {analysis.exit_reason}")
        
        try:
            from tastytrade_client import TastytradeClient
            
            # Note: For auto-exit, we need to use stored credentials
            # This is a simplified version - in production, you'd use
            # the user's stored OAuth refresh token
            
            client = TastytradeClient()
            client.connect()
            
            result = client.close_calendar_spread_position(
                short_option_symbol=position.front_symbol,
                long_option_symbol=position.back_symbol,
                quantity=position.quantity,
                dry_run=False
            )
            
            # Update position status
            close_order_id = None
            exit_pnl = None
            
            if hasattr(result, 'fee_calculation') and result.fee_calculation:
                if hasattr(result.fee_calculation, 'order'):
                    close_order_id = str(result.fee_calculation.order.id)
                if hasattr(result.fee_calculation, 'price'):
                    exit_credit = float(result.fee_calculation.price)
                    entry_debit = position.entry_debit or 0
                    exit_pnl = (exit_credit - entry_debit) * (position.quantity or 1) * 100
                    
            self.pos_repo.close_position(
                position_id=position.id,
                exit_reason=analysis.exit_reason,
                exit_pnl=exit_pnl or 0,
                exit_order_id=close_order_id
            )
            
            logger.info(f"Position {position.id} closed successfully")
            
            # Trigger exit callback
            if self.config.exit_callback:
                self.config.exit_callback(position, analysis)
                
        except Exception as e:
            logger.error(f"Failed to auto-exit position {position.id}: {e}")
            import traceback
            traceback.print_exc()


class PositionMonitorService:
    """
    Service wrapper for running position monitor as a background task.
    
    Can be started alongside the main application or as a standalone service.
    """
    
    def __init__(
        self,
        check_interval: int = 60,
        auto_exit: bool = False,
        websocket_alerts: bool = True
    ):
        self.check_interval = check_interval
        self.auto_exit = auto_exit
        self.websocket_alerts = websocket_alerts
        self.monitor: Optional[PositionMonitor] = None
        
    def _on_alert(self, position: Position, analysis: ExitAnalysis):
        """Handle exit alerts via WebSocket."""
        # Log the alert
        self._log_alert(position, analysis)
        
        # Send WebSocket alert (primary notification method)
        if self.websocket_alerts:
            self._send_websocket_alert(position, analysis)
            
    def _log_alert(self, position: Position, analysis: ExitAnalysis):
        """Log alert to console."""
        logger.warning(
            f"🚨 EXIT ALERT: {position.symbol} | "
            f"Rule: {analysis.triggered_rule} | "
            f"Reason: {analysis.exit_reason} | "
            f"Action: {analysis.recommended_action}"
        )
    
    def _send_websocket_alert(self, position: Position, analysis: ExitAnalysis):
        """Send alert via WebSocket to connected clients."""
        try:
            import asyncio
            
            alert_data = {
                'type': 'position_alert',
                'position_id': position.id,
                'symbol': position.symbol,
                'rule': analysis.triggered_rule,
                'reason': analysis.exit_reason,
                'action': analysis.recommended_action,
                'pnl_percent': analysis.pnl_percent,
                'current_value': position.current_value,
                'entry_debit': position.entry_debit,
                'unrealized_pnl': position.unrealized_pnl,
                'urgency': 'high' if analysis.urgency >= 4 else 'medium',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Import and use publish_alert (sync function, run in thread pool if needed)
            from signal_publisher import publish_alert
            publish_alert(alert_data)
            
        except Exception as e:
            logger.error(f"Failed to send WebSocket alert: {e}")
            import traceback
            traceback.print_exc()

            
    async def start(self):
        """Start the position monitoring service."""
        config = MonitorConfig(
            check_interval_seconds=self.check_interval,
            auto_exit_enabled=self.auto_exit,
            alert_callback=self._on_alert
        )
        
        self.monitor = PositionMonitor(config)
        await self.monitor.start()
        
    async def stop(self):
        """Stop the position monitoring service."""
        if self.monitor:
            await self.monitor.stop()


# Convenience function for running standalone
async def run_monitor(
    check_interval: int = 60,
    auto_exit: bool = False
):
    """Run the position monitor as a standalone service."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    service = PositionMonitorService(
        check_interval=check_interval,
        auto_exit=auto_exit
    )
    
    try:
        await service.start()
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await service.stop()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Position Monitor Service")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--auto-exit",
        action="store_true",
        help="Enable automatic position closing on exit signals"
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_monitor(
        check_interval=args.interval,
        auto_exit=args.auto_exit
    ))
