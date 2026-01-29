"""
End-of-Day P&L Analysis
========================
Analyzes daily trading performance and generates summary report.

Runs at 4:05 PM ET (after market close).
"""

import logging
from datetime import datetime, date
from typing import List, Dict
import json

from src.theta_spreads.portfolio_manager import ThetaPortfolioManager, ThetaPosition
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/eod_analysis.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EODAnalyzer:
    """End-of-day performance analyzer."""
    
    def __init__(self):
        self.portfolio = ThetaPortfolioManager(total_capital=config.THETA_TOTAL_CAPITAL)
        self.today = date.today()
    
    def generate_report(self):
        """Generate comprehensive EOD report."""
        logger.info("=" * 70)
        logger.info(f"📊 END-OF-DAY ANALYSIS - {self.today.strftime('%Y-%m-%d')}")
        logger.info("=" * 70 + "\n")
        
        # Get all positions
        all_positions = self.portfolio.get_all_positions()
        open_positions = [p for p in all_positions if p.status == "OPEN"]
        
        # Closed positions (from history file)
        closed_today = self._get_closed_positions_today()
        
        # Portfolio state
        state = self.portfolio.get_portfolio_state()
        
        # Summary metrics
        self._print_portfolio_summary(state, open_positions, closed_today)
        
        # Open positions detail
        if open_positions:
            self._print_open_positions(open_positions)
        
        # Closed positions detail
        if closed_today:
            self._print_closed_positions(closed_today)
        
        # Performance metrics
        self._print_performance_metrics(open_positions, closed_today)
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 EOD ANALYSIS COMPLETE")
        logger.info("=" * 70 + "\n")
    
    def _print_portfolio_summary(self, state, open_positions, closed_today):
        """Print portfolio summary."""
        logger.info("📈 PORTFOLIO SUMMARY")
        logger.info("-" * 70)
        logger.info(f"Total Capital: ${state.total_capital:,.0f}")
        logger.info(f"Reserved Capital: ${state.reserved_capital:,.0f}")
        logger.info(f"Available Capital: ${state.available_capital:,.0f}")
        logger.info(f"Portfolio Heat: {state.heat_pct:.1f}%")
        logger.info(f"")
        logger.info(f"Open Positions: {len(open_positions)}")
        logger.info(f"Closed Today: {len(closed_today)}")
        logger.info(f"Total Unrealized P&L: ${state.total_unrealized_pnl:+,.2f}")
        
        # Calculate realized P&L from closed positions
        realized_pnl = sum(p.get('realized_pnl', 0) for p in closed_today)
        logger.info(f"Total Realized P&L Today: ${realized_pnl:+,.2f}")
        logger.info("")
    
    def _print_open_positions(self, positions: List[ThetaPosition]):
        """Print open positions detail."""
        logger.info("📂 OPEN POSITIONS")
        logger.info("-" * 70)
        
        # Sort by unrealized P&L %
        sorted_positions = sorted(positions, key=lambda p: p.unrealized_pnl_pct, reverse=True)
        
        for pos in sorted_positions:
            trailing_status = "TRAILING ✅" if hasattr(pos, 'trailing_active') and pos.trailing_active else "MONITORING"
            
            logger.info(f"\n{pos.symbol} {pos.strike}P (Exp: {pos.expiration})")
            logger.info(f"  Entry: ${pos.entry_price:.2f} | Current: ${pos.current_ask:.2f}")
            logger.info(f"  P&L: ${pos.unrealized_pnl:+,.2f} ({pos.unrealized_pnl_pct:+.1f}%)")
            
            if hasattr(pos, 'peak_pnl_pct'):
                logger.info(f"  Peak: {pos.peak_pnl_pct:.1f}%")
            
            logger.info(f"  Status: {trailing_status}")
            logger.info(f"  Days Held: {pos.days_held} | DTE: {pos.days_to_expiration}")
        
        logger.info("")
    
    def _print_closed_positions(self, positions: List[Dict]):
        """Print closed positions detail."""
        logger.info("✅ POSITIONS CLOSED TODAY")
        logger.info("-" * 70)
        
        for pos in positions:
            logger.info(f"\n{pos['symbol']} {pos['strike']}P")
            logger.info(f"  Entry: ${pos['entry_price']:.2f} → Exit: ${pos['exit_price']:.2f}")
            logger.info(f"  Realized P&L: ${pos['realized_pnl']:+,.2f} ({pos['realized_pnl_pct']:+.1f}%)")
            logger.info(f"  Peak Profit: {pos.get('peak_pnl_pct', 0):.1f}%")
            logger.info(f"  Exit Reason: {pos['exit_reason']}")
            logger.info(f"  Days Held: {pos['days_held']}")
        
        logger.info("")
    
    def _print_performance_metrics(self, open_positions, closed_today):
        """Print performance metrics."""
        logger.info("📊 PERFORMANCE METRICS")
        logger.info("-" * 70)
        
        if closed_today:
            # Win rate
            winners = [p for p in closed_today if p['realized_pnl'] > 0]
            win_rate = (len(winners) / len(closed_today)) * 100
            
            # Average profit
            avg_profit_pct = sum(p['realized_pnl_pct'] for p in closed_today) / len(closed_today)
            
            # Average hold time
            avg_hold_time = sum(p['days_held'] for p in closed_today) / len(closed_today)
            
            logger.info(f"Win Rate: {win_rate:.1f}% ({len(winners)}/{len(closed_today)})")
            logger.info(f"Average Profit: {avg_profit_pct:+.1f}%")
            logger.info(f"Average Hold Time: {avg_hold_time:.1f} days")
        else:
            logger.info("No positions closed today")
        
        logger.info("")
    
    def _get_closed_positions_today(self) -> List[Dict]:
        """Get positions closed today from history file."""
        try:
            with open('theta_closed_positions.json', 'r') as f:
                all_closed = json.load(f)
            
            # Filter for today
            today_str = self.today.isoformat()
            closed_today = [
                p for p in all_closed 
                if p.get('closed_at', '').startswith(today_str)
            ]
            
            return closed_today
            
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.error(f"Error loading closed positions: {e}")
            return []


def main():
    """Run EOD analysis."""
    analyzer = EODAnalyzer()
    analyzer.generate_report()


if __name__ == "__main__":
    main()
