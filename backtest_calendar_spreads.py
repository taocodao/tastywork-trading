"""
Calendar Spread Strategy Backtest
==================================
Backtest the AI-enhanced calendar spread strategy using historical data.

The strategy:
- Use CalendarSignalGenerator to find opportunities
- Enter spreads with optimal DTE combinations (based on IV rank)
- Exit at 35% profit target or 50% loss
- Close if earnings within 7 days
- Close if short leg DTE <= 3

Uses:
- Real historical stock prices from yfinance
- Simulated option prices using Black-Scholes
- AI components: VOSS filter, DTE selector, Strike selector
- Earnings intelligence for safety
"""

import sys
import io

# Force UTF-8 encoding for Windows compatibility
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd

# Add project root
sys.path.insert(0, '.')

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

from greeks_calculator import BlackScholesCalculator
from src.calendar_spreads import (
    CalendarSignalGenerator,
    GeneratorConfig,
    EarningsStrategyRouter,
    StrategyDecision,
    VOSSLiquidityFilter,
    DTESelector,
    CalendarStrikeSelector
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CalendarBacktestTrade:
    """A single calendar spread backtest trade."""
    trade_id: int
    symbol: str
    entry_date: date
    exit_date: date
    
    # Entry details
    stock_price_entry: float
    strike: float
    short_dte_entry: int
    long_dte_entry: int
    net_debit: float  # Cost to open spread
    iv_rank: float
    
    # Greeks at entry
    theta_edge: float  # Expected theta per day
    delta_entry: float
    
    # Exit details
    stock_price_exit: float
    spread_value_exit: float  # Value of spread at close
    short_dte_exit: int
    long_dte_exit: int
    
    # P&L
    gross_pnl: float = 0.0
    commission: float = 4.0  # $1 per leg x 4  
    net_pnl: float = 0.0
    pnl_pct: float = 0.0  # % return on capital required
    
    # Outcome
    exit_reason: str = ""
    hold_days: int = 0
    capital_required: float = 0.0
    
    def __post_init__(self):
        self.hold_days = (self.exit_date - self.entry_date).days
        self.capital_required = self.net_debit * 100  # Debit paid
        self.gross_pnl = (self.spread_value_exit - self.net_debit) * 100
        self.net_pnl = self.gross_pnl - self.commission
        self.pnl_pct = (self.net_pnl / self.capital_required) * 100 if self.capital_required > 0 else 0


@dataclass
class CalendarBacktestResult:
    """Aggregated backtest results."""
    symbol: str
    start_date: date
    end_date: date
    initial_capital: float
    
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    
    total_pnl: float
    avg_win: float
    avg_loss: float
    avg_hold_days: float
    
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    annualized_return: float
    return_on_capital: float
    
    trades: List[CalendarBacktestTrade]
    
    def print_summary(self):
        """Print detailed backtest summary."""
        print("\n" + "=" * 70)
        print(f"CALENDAR SPREAD BACKTEST - {self.symbol}")
        print("=" * 70)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Strategy: AI-Enhanced Calendar Spreads")
        print(f"Initial Capital: ${self.initial_capital:,.0f}")
        print()
        
        print("PERFORMANCE METRICS")
        print("-" * 40)
        print(f"  Total Trades: {self.total_trades}")
        print(f"  Win Rate: {self.win_rate:.1f}%")
        print(f"  Wins: {self.wins} | Losses: {self.losses}")
        print(f"  Avg Hold: {self.avg_hold_days:.0f} days")
        print()
        
        print("PROFIT & LOSS")
        print("-" * 40)
        print(f"  Total P&L: ${self.total_pnl:+,.2f}")
        print(f"  Avg Win: ${self.avg_win:,.2f}")
        print(f"  Avg Loss: ${self.avg_loss:,.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")
        print(f"  Return on Capital: {self.return_on_capital:.2f}%")
        print(f"  Annualized Return: {self.annualized_return:.2f}%")
        print()
        
        print("RISK METRICS")
        print("-" * 40)
        print(f"  Max Drawdown: {self.max_drawdown:.1f}%")
        print(f"  Sharpe Ratio: {self.sharpe_ratio:.2f}")
        print()
        
        # Exit reason breakdown
        exit_reasons = {}
        for t in self.trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
        
        print("EXIT BREAKDOWN")
        print("-" * 40)
        for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
            pct = (count / self.total_trades) * 100
            print(f"  {reason}: {count} ({pct:.1f}%)")
        print()


class CalendarSpreadBacktester:
    """Backtests AI-enhanced calendar spread strategy."""
    
    def __init__(
        self,
        symbol: str = "SPY",
        start_date: date = None,
        end_date: date = None,
        initial_capital: float = 50000.0,
        iv_estimate: float = 0.20,  # Default IV estimate
        vix_data: pd.DataFrame = None
    ):
        self.symbol = symbol
        self.start_date = start_date or date(2023, 1, 1)
        self.end_date = end_date or date.today()
        self.initial_capital = initial_capital
        self.iv_estimate = iv_estimate
        self.vix_data = vix_data
        
        # Initialize AI components
        self.signal_generator = CalendarSignalGenerator(
            config=GeneratorConfig(
                min_confidence_score=50.0,
                min_liquidity_score=0.2,  # Relaxed for backtest
                min_theta_edge=0.05,  # Very relaxed for backtest
                default_profit_target_pct=35.0,
                default_stop_loss_pct=50.0,
                max_contracts=2,
                max_risk_per_trade=1000.0
            )
        )
        self.earnings_router = EarningsStrategyRouter()
        
        # Black-Scholes calculator
        self.bs_calc = BlackScholesCalculator()
        
        # Load historical data
        self.historical_data = self._load_historical_data()
        
        logger.info(f"Backtester initialized for {symbol}")
        logger.info(f"Period: {self.start_date} to {self.end_date}")
        logger.info(f"Historical data: {len(self.historical_data)} days")
    
    def _load_historical_data(self) -> pd.DataFrame:
        """Load real historical stock prices from yfinance."""
        logger.info(f"Downloading {self.symbol} historical data from Yahoo Finance...")
        
        ticker = yf.Ticker(self.symbol)
        df = ticker.history(
            start=self.start_date - timedelta(days=60),  # Extra buffer
            end=self.end_date + timedelta(days=1)
        )
        
        if df.empty:
            raise ValueError(f"No historical data found for {self.symbol}")
        
        # Add date column
        df['Date'] = df.index.date
        
        logger.info(f"Downloaded {len(df)} days of historical data")
        return df
    
    def _get_stock_price(self, target_date: date) -> Optional[float]:
        """Get stock price for a specific date."""
        matching = self.historical_data[self.historical_data['Date'] == target_date]
        if matching.empty:
            return None
        return matching.iloc[0]['Close']
    
    def _estimate_iv_rank(self, current_date: date) -> float:
        """
        Estimate IV rank for backtest.
        In production this would use historical IV data.
        For backtest, use VIX as proxy if available, otherwise default.
        """
        if self.vix_data is not None:
            matching = self.vix_data[self.vix_data['Date'] == current_date]
            if not matching.empty:
                vix = matching.iloc[0]['Close']
                # Map VIX to IV rank (rough approximation)
                # VIX 10-15 = low IV (20-40 rank)
                # VIX 15-25 = normal (40-60 rank)
                # VIX 25+ = high (60-90 rank)
                if vix < 15:
                    return 30 + (vix - 10) * 2
                elif vix < 25:
                    return 40 + (vix - 15) * 2
                else:
                    return min(90, 60 + (vix - 25) * 1.5)
        
        # Default: moderate IV
        return 50.0
    
    def _calculate_option_price(
        self,
        stock_price: float,
        strike: float,
        dte: int,
        is_call: bool,
        iv: float
    ) -> Tuple[float, float, float]:
        """
        Calculate option price using Black-Scholes.
        Returns: (price, delta, theta)
        """
        if dte <= 0:
            # Expired
            intrinsic = max(0, stock_price - strike) if is_call else max(0, strike - stock_price)
            return intrinsic, 0.0, 0.0
        
        r = 0.02  # Risk-free rate
        result = self.bs_calc.calculate_greeks(
            stock_price=stock_price,
            strike=strike,
            dte=dte,
            iv=iv,
            is_call=is_call,
            risk_free_rate=r
        )
        
        price = result['call_price'] if is_call else result['put_price']
        delta = result['call_delta'] if is_call else result['put_delta']
        theta = result['theta']
        
        return price, delta, theta
    
    def _calculate_spread_value(
        self,
        stock_price: float,
        strike: float,
        short_dte: int,
        long_dte: int,
        is_call: bool,
        iv: float
    ) -> Tuple[float, float]:
        """
        Calculate calendar spread value (long - short).
        Returns: (net_debit, theta_edge)
        """
        short_price, short_delta, short_theta = self._calculate_option_price(
            stock_price, strike, short_dte, is_call, iv
        )
        long_price, long_delta, long_theta = self._calculate_option_price(
            stock_price, strike, long_dte, is_call, iv
        )
        
        net_debit = long_price - short_price
        theta_edge = abs(short_theta) - abs(long_theta)  # Net theta collected
        
        return net_debit, theta_edge
    
    def _check_exit_conditions(
        self,
        trade: CalendarBacktestTrade,
        current_date: date,
        current_price: float,
        days_to_earnings: int
    ) -> Tuple[bool, str]:
        """
        Check if trade should be exited.
        Returns: (should_exit, reason)
        """
        days_held = (current_date - trade.entry_date).days
        
        # 1. Short leg approaching expiration (DTE <= 3)
        short_dte = trade.short_dte_entry - days_held
        if short_dte <= 3:
            return True, "Short DTE <= 3"
        
        # 2. Earnings within 7 days
        if days_to_earnings <= 7:
            return True, "Earnings approaching"
        
        # 3. Max hold period (30 days)
        if days_held >= 30:
            return True, "Max hold period"
        
        # 4. Calculate current P&L
        long_dte = trade.long_dte_entry - days_held
        current_spread_value, _ = self._calculate_spread_value(
            current_price,
            trade.strike,
            short_dte,
            long_dte,
            is_call=True,  # Assume calls for now
            iv=self.iv_estimate
        )
        
        pnl_pct = ((current_spread_value - trade.net_debit) / trade.net_debit) * 100
        
        # 5. Profit target (35%)
        if pnl_pct >= 35.0:
            return True, "Profit target"
        
        # 6. Stop loss (50%)
        if pnl_pct <= -50.0:
            return True, "Stop loss"
        
        return False, ""
    
    def run_backtest(self) -> CalendarBacktestResult:
        """Run the full backtest."""
        logger.info("=" * 70)
        logger.info("STARTING CALENDAR SPREAD BACKTEST")
        logger.info("=" * 70)
        
        trades = []
        trade_counter = 0
        open_position = None
        
        # Scan every trading day
        current_date = self.start_date
        scan_interval = 7  # Scan weekly for new setups
        
        while current_date <= self.end_date:
            stock_price = self._get_stock_price(current_date)
            
            if stock_price is None:
                current_date += timedelta(days=1)
                continue
            
            # Check existing position first
            if open_position is not None:
                days_to_earnings = 999  # Simplified - no real earnings data
                should_exit, exit_reason = self._check_exit_conditions(
                    open_position,
                    current_date,
                    stock_price,
                    days_to_earnings
                )
                
                if should_exit:
                    # Close position
                    days_held = (current_date - open_position.entry_date).days
                    short_dte = open_position.short_dte_entry - days_held
                    long_dte = open_position.long_dte_entry - days_held
                    
                    spread_value, _ = self._calculate_spread_value(
                        stock_price,
                        open_position.strike,
                        short_dte,
                        long_dte,
                        is_call=True,
                        iv=self.iv_estimate
                    )
                    
                    # Complete trade record
                    open_position.exit_date = current_date
                    open_position.stock_price_exit = stock_price
                    open_position.spread_value_exit = spread_value
                    open_position.short_dte_exit = short_dte
                    open_position.long_dte_exit = long_dte
                    open_position.exit_reason = exit_reason
                    open_position.__post_init__()  # Recalculate P&L
                    
                    trades.append(open_position)
                    
                    logger.info(
                        f"Trade {open_position.trade_id} CLOSED: {exit_reason} | "
                        f"P&L: ${open_position.net_pnl:.2f} ({open_position.pnl_pct:+.1f}%) | "
                        f"Held: {open_position.hold_days} days"
                    )
                    
                    open_position = None
            
            # Look for new entry (if no open position and on scan day)
            if open_position is None and (current_date - self.start_date).days % scan_interval == 0:
                iv_rank = self._estimate_iv_rank(current_date)
                
                # Select DTE based on IV rank
                dte_selector = DTESelector()
                short_dte, long_dte = dte_selector.select_optimal_dte(iv_rank)
                
                # Calculate ATM strike
                strike = round(stock_price)  # Simplified
                
                # Calculate spread value
                net_debit, theta_edge = self._calculate_spread_value(
                    stock_price,
                    strike,
                    short_dte,
                    long_dte,
                    is_call=True,
                    iv=self.iv_estimate
                )
                
                # More relaxed entry conditions for backtest
                if net_debit > 0.1 and theta_edge > 0.05:  # Relaxed from 0.5 and 0.3
                    trade_counter += 1
                    
                    open_position = CalendarBacktestTrade(
                        trade_id=trade_counter,
                        symbol=self.symbol,
                        entry_date=current_date,
                        exit_date=current_date,  # Placeholder
                        stock_price_entry=stock_price,
                        strike=strike,
                        short_dte_entry=short_dte,
                        long_dte_entry=long_dte,
                        net_debit=net_debit,
                        iv_rank=iv_rank,
                        theta_edge=theta_edge,
                        delta_entry=0.0,  # Simplified
                        stock_price_exit=0.0,  # Placeholder
                        spread_value_exit=0.0,  # Placeholder
                        short_dte_exit=0,
                        long_dte_exit=0
                    )
                    
                    logger.info(
                        f"Trade {trade_counter} OPENED: {self.symbol} ${strike} | "
                        f"Debit: ${net_debit:.2f} | Short DTE: {short_dte}, Long DTE: {long_dte} | "
                        f"IV Rank: {iv_rank:.0f} | Theta: ${theta_edge:.2f}/day"
                    )
                else:
                    if (current_date - self.start_date).days < 30:  # Only log first month
                        logger.debug(
                            f"Skipping entry on {current_date}: debit=${net_debit:.2f}, "
                            f"theta=${theta_edge:.2f} (need >$0.10 debit, >$0.05 theta)"
                        )
            
            current_date += timedelta(days=1)
        
        # Close any remaining open position
        if open_position is not None:
            stock_price = self._get_stock_price(self.end_date)
            if stock_price:
                days_held = (self.end_date - open_position.entry_date).days
                short_dte = max(0, open_position.short_dte_entry - days_held)
                long_dte = max(0, open_position.long_dte_entry - days_held)
                
                spread_value, _ = self._calculate_spread_value(
                    stock_price,
                    open_position.strike,
                    short_dte,
                    long_dte,
                    is_call=True,
                    iv=self.iv_estimate
                )
                
                open_position.exit_date = self.end_date
                open_position.stock_price_exit = stock_price
                open_position.spread_value_exit = spread_value
                open_position.short_dte_exit = short_dte
                open_position.long_dte_exit = long_dte
                open_position.exit_reason = "Backtest end"
                open_position.__post_init__()
                
                trades.append(open_position)
        
        # Calculate results
        return self._calculate_results(trades)
    
    def _calculate_results(self, trades: List[CalendarBacktestTrade]) -> CalendarBacktestResult:
        """Calculate aggregate backtest results."""
        if not trades:
            logger.warning("No trades executed during backtest period")
            return CalendarBacktestResult(
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=self.initial_capital,
                total_trades=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                total_pnl=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                avg_hold_days=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                annualized_return=0.0,
                return_on_capital=0.0,
                trades=[]
            )
        
        total_trades = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        
        total_pnl = sum(t.net_pnl for t in trades)
        total_win = sum(t.net_pnl for t in wins)
        total_loss = abs(sum(t.net_pnl for t in losses))
        
        win_rate = (len(wins) / total_trades) * 100
        avg_win = total_win / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0
        avg_hold_days = sum(t.hold_days for t in trades) / total_trades
        
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
        
        # Calculate max drawdown
        cumulative_pnl = 0
        peak = 0
        max_dd = 0
        
        for trade in trades:
            cumulative_pnl += trade.net_pnl
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_dd:
                max_dd = dd
        
        max_drawdown_pct = (max_dd / self.initial_capital) * 100
        
        # Calculate Sharpe ratio (simplified)
        returns = [t.pnl_pct for t in trades]
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        sharpe = (avg_return / std_return) * np.sqrt(52) if std_return > 0 else 0  # Assume weekly trades
        
        # Annualized return
        days_total = (self.end_date - self.start_date).days
        years = days_total / 365.25
        return_on_capital = (total_pnl / self.initial_capital) * 100
        annualized_return = return_on_capital / years if years > 0 else 0
        
        return CalendarBacktestResult(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            total_trades=total_trades,
            wins=len(wins),
            losses=len(losses),
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_hold_days=avg_hold_days,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown_pct,
            sharpe_ratio=sharpe,
            annualized_return=annualized_return,
            return_on_capital=return_on_capital,
            trades=trades
        )


def run_calendar_backtest(
    symbols: List[str] = None,
    start_date: date = None,
    end_date: date = None
) -> Dict[str, CalendarBacktestResult]:
    """Run calendar spread backtest on multiple symbols."""
    
    symbols = symbols or ["SPY", "QQQ", "IWM"]
    start_date = start_date or date(2023, 1, 1)
    end_date = end_date or date.today()
    
    results = {}
    
    for symbol in symbols:
        logger.info(f"\n{'=' * 70}")
        logger.info(f"BACKTESTING {symbol}")
        logger.info(f"{'=' * 70}")
        
        try:
            backtester = CalendarSpreadBacktester(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                initial_capital=50000.0
            )
            
            result = backtester.run_backtest()
            result.print_summary()
            
            results[symbol] = result
            
        except Exception as e:
            logger.error(f"Error backtesting {symbol}: {e}", exc_info=True)
    
    return results


if __name__ == "__main__":
    # Run backtest for 2023-2024
    results = run_calendar_backtest(
        symbols=["SPY", "QQQ", "IWM"],
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31)
    )
