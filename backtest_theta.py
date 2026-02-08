"""
Theta Strategy Backtest
========================
Backtest the cash-secured put selling strategy using historical data.

The strategy:
- Sell 30-delta puts
- 28-35 DTE at entry
- Time-based exits (Week 1: 50%, Week 2: 60%, Week 3: 75%, Week 4: 90%)
- Close if underlying breaches strike * 0.98

Uses:
- Real historical stock prices from yfinance
- Simulated option prices using Black-Scholes
- Realistic Greeks and IV data
"""

import sys
import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
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
from src.theta_spreads import ThetaPortfolioManager
from src.theta_spreads.symbol_profiles import get_symbol_profile, SYMBOL_PROFILES
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ThetaBacktestTrade:
    """A single backtest trade for cash-secured put."""
    trade_id: int
    symbol: str
    entry_date: date
    exit_date: date
    
    # Entry details
    stock_price_entry: float
    strike: float
    dte_entry: int
    premium_collected: float  # Credit received
    iv_entry: float
    delta_entry: float
    
    # Exit details  
    stock_price_exit: float
    premium_paid: float  # Debit to close
    dte_exit: int
    
    # P&L
    gross_pnl: float = 0.0  # Will be calculated in __post_init__
    commission: float = 2.0  # $1 per leg x 2
    net_pnl: float = 0.0
    pnl_pct: float = 0.0  # % return on capital required
    
    # Outcome
    exit_reason: str = ""
    hold_days: int = 0
    capital_required: float = 0.0
    
    def __post_init__(self):
        self.hold_days = (self.exit_date - self.entry_date).days
        self.capital_required = self.strike * 100  # Cash-secured requirement
        self.gross_pnl = (self.premium_collected - self.premium_paid) * 100
        self.net_pnl = self.gross_pnl - self.commission
        self.pnl_pct = (self.net_pnl / self.capital_required) * 100


@dataclass
class ThetaBacktestResult:
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
    total_premium_collected: float
    avg_win: float
    avg_loss: float
    avg_hold_days: float
    
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    return_on_capital: float
    
    trades: List[ThetaBacktestTrade]
    
    def print_summary(self):
        """Print detailed backtest summary."""
        print("\n" + "=" * 70)
        print(f"THETA STRATEGY BACKTEST - {self.symbol}")
        print("=" * 70)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Strategy: Sell 30-delta puts, time-based exits")
        print(f"Initial Capital: ${self.initial_capital:,.0f}")
        print()
        
        print("📊 PERFORMANCE METRICS")
        print("-" * 40)
        print(f"  Total Trades: {self.total_trades}")
        print(f"  Win Rate: {self.win_rate:.1f}%")
        print(f"  Wins: {self.wins} | Losses: {self.losses}")
        print(f"  Avg Hold: {self.avg_hold_days:.0f} days")
        print()
        
        print("💰 PROFIT & LOSS")
        print("-" * 40)
        print(f"  Total P&L: ${self.total_pnl:+,.2f}")
        print(f"  Total Premium Collected: ${self.total_premium_collected:,.2f}")
        print(f"  Avg Win: ${self.avg_win:,.2f}")
        print(f"  Avg Loss: ${self.avg_loss:,.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")
        print(f"  Return on Capital: {self.return_on_capital:.2f}%")
        print()
        
        print("📈 RISK METRICS")
        print("-" * 40)
        print(f"  Max Drawdown: {self.max_drawdown:.1f}%")
        print(f"  Sharpe Ratio: {self.sharpe_ratio:.2f}")
        print()
        
        # Exit reason breakdown
        exit_reasons = {}
        for t in self.trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
        
        print("📋 EXIT BREAKDOWN")
        print("-" * 40)
        for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
            pct = count / self.total_trades * 100
            print(f"  {reason}: {count} ({pct:.0f}%)")
        print()


class ThetaStrategyBacktester:
    """Backtests Theta cash-secured put strategy."""
    
    def __init__(
        self,
        symbol: str = "SPY",
        start_date: date = None,
        end_date: date = None,
        initial_capital: float = None,
        target_delta: float = 0.30,
        dte_min: int = 28,
        dte_max: int = 35,
        use_profile: bool = True  # NEW: Use symbol-specific profile
    ):
        self.symbol = symbol
        self.start_date = start_date or date(2024, 1, 1)
        self.end_date = end_date or date(2025, 12, 31)
        self.initial_capital = initial_capital or config.ACCOUNT_SIZE
        self.target_delta = target_delta
        self.dte_min = dte_min
        self.dte_max = dte_max
        self.use_profile = use_profile
        
        # Get symbol profile if enabled
        if self.use_profile and symbol in SYMBOL_PROFILES:
            self.profile = get_symbol_profile(symbol)
            logger.info(f"Using optimized profile for {symbol}")
            logger.info(f"  Week1: {self.profile.week1_profit_pct}%, Breach: {self.profile.breach_threshold_pct*100}%")
        else:
            self.profile = None
            logger.info(f"Using default config parameters for {symbol}")
        
        self.bs_calc = BlackScholesCalculator()
        
        # Load historical data
        logger.info(f"Loading historical data for {symbol}...")
        self.prices, self.iv_series = self._load_historical_data()
        logger.info(f"Loaded {len(self.prices)} days of data")
    
    def _load_historical_data(self) -> tuple:
        """Load real historical stock prices from yfinance."""
        ticker = yf.Ticker(self.symbol)
        
        # Add buffer for option expiration calculations
        buffer_start = self.start_date - timedelta(days=60)
        buffer_end = self.end_date + timedelta(days=60)
        
        # Download data
        df = ticker.history(start=buffer_start, end=buffer_end, interval='1d')
        
        if df.empty:
            raise ValueError(f"No data found for {self.symbol}")
        
        # Clean data
        df = df[['Close', 'High', 'Low', 'Volume']].copy()
        df.columns = ['close', 'high', 'low', 'volume']
        df.index = pd.to_datetime(df.index).date
        
        # Calculate historical volatility as proxy for IV
        returns = pd.Series([df['close'].iloc[i] / df['close'].iloc[i-1] - 1 
                            for i in range(1, len(df))], 
                           index=df.index[1:])
        
        # 21-day rolling HV annualized
        hv = returns.rolling(21).std() * np.sqrt(252)
        
        # IV is typically higher than HV (add 10-30% premium)
        iv_premium = 1.20  # IV ~ 1.2x HV
        if self.symbol in ['QQQ', 'NVDA', 'AMD']:
            iv_premium = 1.30  # Tech has higher IV premium
        
        iv_series = hv * iv_premium
        iv_series = iv_series.bfill().fillna(0.25)
        
        # Clamp IV to reasonable range
        iv_series = iv_series.clip(0.10, 0.60)
        
        return df, iv_series
    
    def _calculate_put_price(
        self,
        stock_price: float,
        strike: float,
        dte: int,
        iv: float
    ) -> tuple:
        """
        Calculate put option price and delta using Black-Scholes.
        Returns: (premium, delta)
        """
        T = dte / 365
        
        # Get put price from BS calculator
        premium = self.bs_calc.put_price(stock_price, strike, T, iv)
        
        # Calculate put delta manually: delta_put = N(d1) - 1
        # For puts, delta is negative, so we take absolute value
        from scipy.stats import norm
        import math
        
        if T <= 0:
            delta = 0.0
        else:
            d1 = (math.log(stock_price / strike) + (self.bs_calc.r + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            delta = norm.cdf(d1) - 1  # Put delta formula
        
        return premium, abs(delta)
    
    def _find_target_strike(
        self,
        stock_price: float,
        dte: int,
        iv: float,
        target_delta: float = 0.30
    ) -> Optional[float]:
        """
        Find strike price that gives target delta (~30 delta).
        Returns strike price.
        """
        # Start with OTM strikes (below current price for puts)
        # 30-delta put is typically 5-10% OTM
        search_strikes = np.arange(
            stock_price * 0.85,  # 15% OTM
            stock_price * 0.995,  # Just below ATM
            stock_price * 0.01   # 1% increments
        )
        
        best_strike = None
        best_delta_diff = float('inf')
        
        for strike in search_strikes:
            _, delta = self._calculate_put_price(stock_price, strike, dte, iv)
            delta_diff = abs(delta - target_delta)
            
            if delta_diff < best_delta_diff:
                best_delta_diff = delta_diff
                best_strike = strike
        
        # Only accept if within tolerance
        if best_delta_diff <= config.THETA_DELTA_TOLERANCE:
            return round(best_strike, 2)
        
        return None
    
    def _calculate_exit_target(self, premium_collected: float, days_held: int) -> float:
        """
        Calculate profit target based on time-based exit rules.
        Uses symbol profile if available, otherwise falls back to config.
        Returns target closing price.
        """
        # Use profile-specific targets if available
        if self.profile:
            if days_held <= 7:
                target_pct = self.profile.week1_profit_pct / 100
            elif days_held <= 14:
                target_pct = self.profile.week2_profit_pct / 100
            elif days_held <= 21:
                target_pct = self.profile.week3_profit_pct / 100
            else:
                target_pct = self.profile.week4_profit_pct / 100
        else:
            # Fallback to config defaults
            if days_held <= 7:
                target_pct = config.THETA_WEEK1_PROFIT_PCT / 100
            elif days_held <= 14:
                target_pct = config.THETA_WEEK2_PROFIT_PCT / 100
            elif days_held <= 21:
                target_pct = config.THETA_WEEK3_PROFIT_PCT / 100
            else:
                target_pct = config.THETA_WEEK4_PROFIT_PCT / 100
        
        # We want to capture target_pct of the premium
        # Close when value decays to (1 - target_pct) * entry_premium
        target_close_price = premium_collected * (1 - target_pct)
        
        return target_close_price
    
    def run_backtest(self) -> ThetaBacktestResult:
        """Run the full backtest."""
        trades: List[ThetaBacktestTrade] = []
        trade_id = 0
        
        # Filter to backtest period
        mask = (self.prices.index >= self.start_date) & (self.prices.index <= self.end_date)
        trading_days = self.prices.index[mask].tolist()
        
        logger.info(f"Backtesting {len(trading_days)} trading days...")
        
        # Trade weekly (sell new put every ~7 days)
        i = 0
        while i < len(trading_days) - 35:  # Need at least 35 days ahead
            entry_date = trading_days[i]
            stock_price_entry = self.prices.loc[entry_date, 'close']
            iv_entry = self.iv_series.loc[entry_date]
            
            # Skip if IV too low (hard to find good premiums)
            if iv_entry < config.THETA_MIN_IV:
                i += 1
                continue
            
            # Find target DTE (28-35 days out)
            dte_entry = 30  # Target 30 DTE
            
            # Find 30-delta strike
            strike = self._find_target_strike(
                stock_price_entry,
                dte_entry,
                iv_entry,
                self.target_delta
            )
            
            if strike is None:
                i += 1
                continue
            
            # Calculate entry premium
            premium_entry, delta_entry = self._calculate_put_price(
                stock_price_entry, strike, dte_entry, iv_entry
            )
            
            # Check minimum premium
            if premium_entry < config.THETA_MIN_PREMIUM:
                i += 1
                continue
            
            # Simulate holding the position
            exit_date = None
            exit_reason = ""
            days_held = 0
            
            for j in range(i + 1, min(i + 35, len(trading_days))):
                current_date = trading_days[j]
                days_held = (current_date - entry_date).days
                dte_current = dte_entry - days_held
                
                stock_price_current = self.prices.loc[current_date, 'close']
                iv_current = self.iv_series.loc[current_date]
                
                # Calculate current put value
                premium_current, _ = self._calculate_put_price(
                    stock_price_current, strike, dte_current, iv_current
                )
                
                # Check exit conditions
                
                # 1. Defensive close (stock breached threshold)
                # Use profile-specific breach threshold if available
                if self.profile:
                    breach_threshold = 1 - self.profile.breach_threshold_pct
                else:
                    breach_threshold = 1 - (config.THETA_DEFENSIVE_BREACH_PCT / 100)
                
                if stock_price_current <= strike * breach_threshold:
                    exit_date = current_date
                    exit_reason = "DEFENSIVE_CLOSE"
                    premium_exit = premium_current
                    break
                
                # 2. Time-based profit target
                target_close = self._calculate_exit_target(premium_entry, days_held)
                if premium_current <= target_close:
                    exit_date = current_date
                    exit_reason = f"PROFIT_TARGET_W{(days_held // 7) + 1}"
                    premium_exit = premium_current
                    break
                
                # 3. Expiration (DTE <= threshold)
                # Use profile-specific DTE exit if available
                if self.profile:
                    dte_threshold = self.profile.dte_exit_threshold
                else:
                    dte_threshold = config.THETA_EXPIRATION_THRESHOLD
                
                if dte_current <= dte_threshold:
                    exit_date = current_date
                    exit_reason = "EXPIRATION"
                    premium_exit = premium_current
                    break
            
            # If no exit triggered, close at end of simulation
            if exit_date is None:
                exit_date = trading_days[min(i + 34, len(trading_days) - 1)]
                days_held = (exit_date - entry_date).days
                dte_current = max(0, dte_entry - days_held)
                stock_price_exit = self.prices.loc[exit_date, 'close']
                iv_exit = self.iv_series.loc[exit_date]
                premium_exit, _ = self._calculate_put_price(
                    stock_price_exit, strike, dte_current, iv_exit
                )
                exit_reason = "MAX_HOLD"
            else:
                stock_price_exit = self.prices.loc[exit_date, 'close']
            
            # Create trade record
            trade = ThetaBacktestTrade(
                trade_id=trade_id,
                symbol=self.symbol,
                entry_date=entry_date,
                exit_date=exit_date,
                stock_price_entry=stock_price_entry,
                strike=strike,
                dte_entry=dte_entry,
                premium_collected=premium_entry,
                iv_entry=iv_entry,
                delta_entry=delta_entry,
                stock_price_exit=stock_price_exit,
                premium_paid=premium_exit,
                dte_exit=max(0, dte_entry - (exit_date - entry_date).days),
                exit_reason=exit_reason
 )
            
            trades.append(trade)
            trade_id += 1
            
            logger.info(f"Trade {trade_id}: {self.symbol} {strike}P sold @ ${premium_entry:.2f}, "
                       f"closed @ ${premium_exit:.2f}, P&L: ${trade.net_pnl:+.2f} ({exit_reason})")
            
            # Move to next trade (weekly)
            i += 7
        
        # Calculate results
        return self._calculate_results(trades)
    
    def _calculate_results(self, trades: List[ThetaBacktestTrade]) -> ThetaBacktestResult:
        """Calculate aggregate backtest results."""
        if not trades:
            return ThetaBacktestResult(
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=self.initial_capital,
                total_trades=0,
                wins=0, losses=0, win_rate=0,
                total_pnl=0, total_premium_collected=0,
                avg_win=0, avg_loss=0, avg_hold_days=0,
                profit_factor=0, max_drawdown=0,
                sharpe_ratio=0, return_on_capital=0,
                trades=[]
            )
        
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        
        win_rate = len(wins) / len(trades) * 100
        total_pnl = sum(t.net_pnl for t in trades)
        total_premium = sum(t.premium_collected * 100 for t in trades)
        
        avg_win = np.mean([t.net_pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.net_pnl for t in losses]) if losses else 0
        avg_hold = np.mean([t.hold_days for t in trades])
        
        total_wins = sum(t.net_pnl for t in wins)
        total_losses = abs(sum(t.net_pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Drawdown
        equity_curve = np.cumsum([t.net_pnl for t in trades])
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / (self.initial_capital + peak) * 100
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
        
        # Sharpe ratio
        returns = [t.net_pnl / t.capital_required for t in trades]
        if len(returns) > 1:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(52)  # Weekly trades
        else:
            sharpe = 0
        
        return_on_capital = (total_pnl / self.initial_capital) * 100
        
        return ThetaBacktestResult(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_premium_collected=total_premium,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_hold_days=avg_hold,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            return_on_capital=return_on_capital,
            trades=trades
        )


def run_theta_backtest():
    """Run Theta strategy backtest on configured symbols."""
    print("\n" + "=" * 70)
    print("THETA STRATEGY HISTORICAL BACKTEST")
    print("=" * 70)
    print(f"Strategy: Sell 30-delta puts, time-based exits")
    print(f"Period: 2024-01-01 to 2025-12-31 (REAL DATA)")
    print()
    
    # Test on primary symbols
    symbols = ["SPY", "QQQ", "IWM"]
    all_results = []
    
    for symbol in symbols:
        logger.info(f"\nBacktesting {symbol}...")
        
        backtester = ThetaStrategyBacktester(
            symbol=symbol,
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 1),
            initial_capital=config.ACCOUNT_SIZE
        )
        
        result = backtester.run_backtest()
        result.print_summary()
        all_results.append(result)
    
    # Combined summary
    print("\n" + "=" * 70)
    print("COMBINED RESULTS (ALL SYMBOLS)")
    print("=" * 70)
    
    total_trades = sum(r.total_trades for r in all_results)
    total_pnl = sum(r.total_pnl for r in all_results)
    total_wins = sum(r.wins for r in all_results)
    overall_win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
    
    print(f"\n  Total Trades: {total_trades}")
    print(f"  Overall Win Rate: {overall_win_rate:.1f}%")
    print(f"  Total P&L: ${total_pnl:+,.2f}")
    print(f"  Initial Capital: ${config.ACCOUNT_SIZE:,.0f}")
    print(f"  Final Capital: ${config.ACCOUNT_SIZE + total_pnl:,.0f}")
    print(f"  Return: {total_pnl / config.ACCOUNT_SIZE * 100:+.2f}%")
    
    print("\n  Per Symbol:")
    for r in all_results:
        print(f"    {r.symbol}: {r.total_trades} trades, "
              f"{r.win_rate:.0f}% WR, "
              f"${r.total_pnl:+,.0f} ({r.return_on_capital:+.1f}%)")
    
    return all_results


if __name__ == "__main__":
    results = run_theta_backtest()
