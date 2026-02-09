"""
IV Term Structure Backtest with VIX-VXV Proxy
==============================================
Validates the hypothesis:
  "Calendar/diagonal spreads entered during backwardation have better performance 
   than those entered during contango"

Uses:
- VIX-VXV daily data as term structure proxy
- Existing calendar backtest infrastructure
- Black-Scholes option pricing

Output:
- Win rate by regime (backwardation vs contango vs flat)
- Avg P&L by regime
- Statistical significance of difference
"""

import sys
import io
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from scipy import stats

# Force UTF-8 encoding for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

from greeks_calculator import BlackScholesCalculator


@dataclass
class RegimeBacktestTrade:
    """A single calendar spread trade with regime information."""
    trade_id: int
    symbol: str
    entry_date: date
    exit_date: date
    regime: str  # "Backwardation", "Contango", "Flat"
    vix_vxv_diff: float  # Entry day VIX - VXV
    
    # Trade details
    strike: float
    net_debit: float
    short_dte_entry: int
    long_dte_entry: int
    
    # Result
    gross_pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    hold_days: int = 0
    is_win: bool = False


@dataclass
class RegimeBacktestResult:
    """Results for a single regime."""
    regime: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    trades: List[RegimeBacktestTrade]


class IVTermStructureBacktest:
    """
    Backtest calendar spreads with VIX-VXV term structure regime filter.
    """
    
    def __init__(
        self,
        symbol: str = "SPY",
        start_date: date = None,
        end_date: date = None,
        vix_vxv_path: str = None
    ):
        self.symbol = symbol
        self.start_date = start_date or date(2010, 1, 1)  # VIX-VXV starts 2007-12
        self.end_date = end_date or date(2024, 12, 31)
        
        # Load VIX-VXV term structure data
        self.vix_vxv_path = vix_vxv_path or os.path.join(
            os.path.dirname(__file__),
            "new/IV term structure/vix_vxv_daily.csv"
        )
        self.term_structure_data = self._load_term_structure_data()
        
        # Load stock price data
        self.stock_data = self._load_stock_data()
        
        # Black-Scholes calculator
        self.bs_calc = BlackScholesCalculator()
        
        print(f"Initialized backtest for {symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Term structure data: {len(self.term_structure_data)} days")
        print(f"Stock data: {len(self.stock_data)} days")
    
    def _load_term_structure_data(self) -> pd.DataFrame:
        """Load VIX-VXV term structure proxy data."""
        try:
            df = pd.read_csv(self.vix_vxv_path)
            df['date'] = pd.to_datetime(df['date']).dt.date
            df = df.set_index('date')
            print(f"Loaded term structure data: {len(df)} rows")
            return df
        except Exception as e:
            print(f"ERROR loading term structure data: {e}")
            return pd.DataFrame()
    
    def _load_stock_data(self) -> pd.DataFrame:
        """Load historical stock prices."""
        print(f"Downloading {self.symbol} price data...")
        ticker = yf.Ticker(self.symbol)
        df = ticker.history(
            start=self.start_date - timedelta(days=60),
            end=self.end_date + timedelta(days=1)
        )
        if df.empty:
            raise ValueError(f"No data for {self.symbol}")
        df['Date'] = df.index.date
        return df
    
    def _get_regime(self, target_date: date) -> Tuple[str, float]:
        """Get term structure regime for a date."""
        if target_date in self.term_structure_data.index:
            row = self.term_structure_data.loc[target_date]
            return row['Regime'], row['diff']
        return "Unknown", 0.0
    
    def _get_stock_price(self, target_date: date) -> Optional[float]:
        """Get stock price for a date."""
        matching = self.stock_data[self.stock_data['Date'] == target_date]
        if matching.empty:
            return None
        return matching.iloc[0]['Close']
    
    def _estimate_iv(self, regime: str, vix_level: float = None) -> float:
        """
        Estimate IV based on regime and VIX.
        In backwardation, IV is typically higher.
        """
        if vix_level is not None:
            return vix_level / 100.0  # VIX is already annualized %
        
        # Default estimates by regime
        if regime == "Backwardation":
            return 0.25  # Higher IV in stress
        elif regime == "Contango":
            return 0.18  # Normal low IV
        else:
            return 0.20  # Flat/neutral
    
    def _calculate_spread_value(
        self,
        stock_price: float,
        strike: float,
        short_dte: int,
        long_dte: int,
        iv: float
    ) -> Tuple[float, float]:
        """Calculate calendar spread value using Black-Scholes."""
        if short_dte <= 0 or long_dte <= 0:
            return 0.0, 0.0
        
        # Short option (sell)
        short_price = self.bs_calc.call_price(
            S=stock_price, K=strike, 
            T=short_dte/365.0, sigma=iv
        )
        
        # Long option (buy)
        long_price = self.bs_calc.call_price(
            S=stock_price, K=strike,
            T=long_dte/365.0, sigma=iv
        )
        
        net_debit = long_price - short_price
        
        # Theta edge
        short_theta = self.bs_calc.theta(
            S=stock_price, K=strike,
            T=short_dte/365.0, sigma=iv
        )
        long_theta = self.bs_calc.theta(
            S=stock_price, K=strike,
            T=long_dte/365.0, sigma=iv
        )
        theta_edge = abs(short_theta) - abs(long_theta)
        
        return net_debit, theta_edge
    
    def run_backtest(self, scan_interval: int = 7) -> Dict[str, RegimeBacktestResult]:
        """
        Run backtest comparing regime-based entries.
        
        Args:
            scan_interval: Days between scanning for new entries
        
        Returns:
            Dictionary of results per regime
        """
        print("\n" + "=" * 70)
        print("RUNNING IV TERM STRUCTURE BACKTEST")
        print("=" * 70)
        
        trades: List[RegimeBacktestTrade] = []
        trade_counter = 0
        open_position: Optional[RegimeBacktestTrade] = None
        
        current_date = self.start_date
        
        while current_date <= self.end_date:
            stock_price = self._get_stock_price(current_date)
            regime, vix_vxv_diff = self._get_regime(current_date)
            
            if stock_price is None or regime == "Unknown":
                current_date += timedelta(days=1)
                continue
            
            # Check existing position
            if open_position is not None:
                days_held = (current_date - open_position.entry_date).days
                short_dte = open_position.short_dte_entry - days_held
                
                # Exit conditions
                should_exit = False
                exit_reason = ""
                
                if short_dte <= 3:
                    should_exit = True
                    exit_reason = "Short DTE <= 3"
                elif days_held >= 21:  # Max hold 21 days
                    should_exit = True
                    exit_reason = "Max hold"
                
                if should_exit:
                    # Calculate exit value
                    long_dte = open_position.long_dte_entry - days_held
                    iv = self._estimate_iv(regime)
                    
                    exit_value, _ = self._calculate_spread_value(
                        stock_price, open_position.strike,
                        max(1, short_dte), max(short_dte + 1, long_dte), iv
                    )
                    
                    # Calculate P&L
                    gross_pnl = (exit_value - open_position.net_debit) * 100
                    pnl_pct = (gross_pnl / (open_position.net_debit * 100)) * 100 if open_position.net_debit > 0 else 0
                    
                    open_position.exit_date = current_date
                    open_position.gross_pnl = gross_pnl
                    open_position.pnl_pct = pnl_pct
                    open_position.exit_reason = exit_reason
                    open_position.hold_days = days_held
                    open_position.is_win = gross_pnl > 0
                    
                    trades.append(open_position)
                    open_position = None
            
            # Look for new entry
            if open_position is None and (current_date - self.start_date).days % scan_interval == 0:
                # Skip unknown regimes
                if regime not in ["Backwardation", "Contango", "Flat"]:
                    current_date += timedelta(days=1)
                    continue
                
                # DTE selection (based on typical calendar spread)
                short_dte = 14
                long_dte = 45
                
                # ATM strike
                strike = round(stock_price)
                
                # Get VIX level for IV estimate
                vix_level = None
                if current_date in self.term_structure_data.index:
                    vix_level = self.term_structure_data.loc[current_date]['VIXCLS']
                
                iv = self._estimate_iv(regime, vix_level)
                
                # Calculate spread
                net_debit, theta_edge = self._calculate_spread_value(
                    stock_price, strike, short_dte, long_dte, iv
                )
                
                if net_debit > 0.1 and theta_edge > 0.01:
                    trade_counter += 1
                    open_position = RegimeBacktestTrade(
                        trade_id=trade_counter,
                        symbol=self.symbol,
                        entry_date=current_date,
                        exit_date=current_date,  # Placeholder
                        regime=regime,
                        vix_vxv_diff=vix_vxv_diff,
                        strike=strike,
                        net_debit=net_debit,
                        short_dte_entry=short_dte,
                        long_dte_entry=long_dte
                    )
                    
                    if trade_counter <= 10 or trade_counter % 50 == 0:
                        print(f"Trade {trade_counter}: {current_date} | "
                              f"Regime: {regime} | VIX-VXV: {vix_vxv_diff:+.2f}")
            
            current_date += timedelta(days=1)
        
        # Close any remaining position
        if open_position is not None:
            open_position.exit_date = self.end_date
            open_position.exit_reason = "Backtest end"
            open_position.hold_days = (self.end_date - open_position.entry_date).days
            trades.append(open_position)
        
        print(f"\nTotal trades executed: {len(trades)}")
        
        # Analyze by regime
        return self._analyze_by_regime(trades)
    
    def _analyze_by_regime(self, trades: List[RegimeBacktestTrade]) -> Dict[str, RegimeBacktestResult]:
        """Analyze trades grouped by entry regime."""
        results = {}
        
        for regime in ["Backwardation", "Contango", "Flat"]:
            regime_trades = [t for t in trades if t.regime == regime]
            
            if not regime_trades:
                results[regime] = RegimeBacktestResult(
                    regime=regime,
                    total_trades=0, wins=0, losses=0,
                    win_rate=0.0, total_pnl=0.0, avg_pnl=0.0,
                    avg_win=0.0, avg_loss=0.0, profit_factor=0.0,
                    trades=[]
                )
                continue
            
            wins = [t for t in regime_trades if t.is_win]
            losses = [t for t in regime_trades if not t.is_win]
            
            total_pnl = sum(t.gross_pnl for t in regime_trades)
            total_win = sum(t.gross_pnl for t in wins)
            total_loss = abs(sum(t.gross_pnl for t in losses))
            
            results[regime] = RegimeBacktestResult(
                regime=regime,
                total_trades=len(regime_trades),
                wins=len(wins),
                losses=len(losses),
                win_rate=(len(wins) / len(regime_trades)) * 100 if regime_trades else 0,
                total_pnl=total_pnl,
                avg_pnl=total_pnl / len(regime_trades) if regime_trades else 0,
                avg_win=total_win / len(wins) if wins else 0,
                avg_loss=total_loss / len(losses) if losses else 0,
                profit_factor=total_win / total_loss if total_loss > 0 else float('inf'),
                trades=regime_trades
            )
        
        return results
    
    def print_results(self, results: Dict[str, RegimeBacktestResult]):
        """Print formatted comparison of regimes."""
        print("\n" + "=" * 80)
        print("IV TERM STRUCTURE BACKTEST RESULTS")
        print("=" * 80)
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print()
        
        # Summary table
        print("REGIME COMPARISON")
        print("-" * 80)
        print(f"{'Regime':<15} {'Trades':>8} {'Win Rate':>10} {'Total P&L':>12} "
              f"{'Avg P&L':>10} {'Avg Win':>10} {'Avg Loss':>10} {'PF':>6}")
        print("-" * 80)
        
        for regime in ["Backwardation", "Contango", "Flat"]:
            r = results[regime]
            print(f"{regime:<15} {r.total_trades:>8} {r.win_rate:>9.1f}% "
                  f"${r.total_pnl:>10,.0f} ${r.avg_pnl:>9,.0f} "
                  f"${r.avg_win:>9,.0f} ${r.avg_loss:>9,.0f} {r.profit_factor:>5.2f}")
        
        print("-" * 80)
        
        # Statistical test
        self._run_statistical_test(results)
    
    def _run_statistical_test(self, results: Dict[str, RegimeBacktestResult]):
        """Run t-test comparing backwardation vs contango performance."""
        print("\nSTATISTICAL ANALYSIS")
        print("-" * 40)
        
        back_trades = results["Backwardation"].trades
        cont_trades = results["Contango"].trades
        
        if len(back_trades) < 5 or len(cont_trades) < 5:
            print("Insufficient trades for statistical test")
            return
        
        back_pnls = [t.pnl_pct for t in back_trades]
        cont_pnls = [t.pnl_pct for t in cont_trades]
        
        # Two-sample t-test
        t_stat, p_value = stats.ttest_ind(back_pnls, cont_pnls)
        
        print(f"Backwardation mean P&L%: {np.mean(back_pnls):+.2f}%")
        print(f"Contango mean P&L%: {np.mean(cont_pnls):+.2f}%")
        print(f"T-statistic: {t_stat:.3f}")
        print(f"P-value: {p_value:.4f}")
        
        if p_value < 0.05:
            print("✅ SIGNIFICANT: Regime affects performance (p < 0.05)")
        else:
            print("❌ NOT SIGNIFICANT: No statistically significant difference")
        
        # Effect size (Cohen's d)
        pooled_std = np.sqrt((np.std(back_pnls)**2 + np.std(cont_pnls)**2) / 2)
        cohens_d = (np.mean(back_pnls) - np.mean(cont_pnls)) / pooled_std if pooled_std > 0 else 0
        
        print(f"Cohen's d (effect size): {cohens_d:.3f}")
        if abs(cohens_d) < 0.2:
            print("Effect size: Negligible")
        elif abs(cohens_d) < 0.5:
            print("Effect size: Small")
        elif abs(cohens_d) < 0.8:
            print("Effect size: Medium")
        else:
            print("Effect size: Large")


def main():
    """Run the IV term structure backtest."""
    
    # Find the VIX-VXV data file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    vix_vxv_path = os.path.join(
        script_dir,
        "vertical spread option implementation/new/IV term structure/vix_vxv_daily.csv"
    )
    
    # Alternative path if running from project root
    if not os.path.exists(vix_vxv_path):
        vix_vxv_path = "vertical spread option implementation/new/IV term structure/vix_vxv_daily.csv"
    
    if not os.path.exists(vix_vxv_path):
        print(f"ERROR: Cannot find VIX-VXV data at {vix_vxv_path}")
        print("Please ensure the file exists.")
        return
    
    # Run backtest for multiple symbols
    symbols = ["SPY", "QQQ"]
    all_results = {}
    
    for symbol in symbols:
        print(f"\n{'='*80}")
        print(f"BACKTESTING {symbol}")
        print(f"{'='*80}")
        
        try:
            backtester = IVTermStructureBacktest(
                symbol=symbol,
                start_date=date(2010, 1, 1),
                end_date=date(2024, 12, 31),
                vix_vxv_path=vix_vxv_path
            )
            
            results = backtester.run_backtest(scan_interval=7)
            backtester.print_results(results)
            all_results[symbol] = results
            
        except Exception as e:
            print(f"Error backtesting {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary across all symbols
    print("\n" + "=" * 80)
    print("AGGREGATE SUMMARY")
    print("=" * 80)
    
    for regime in ["Backwardation", "Contango", "Flat"]:
        total_trades = sum(r[regime].total_trades for r in all_results.values())
        total_wins = sum(r[regime].wins for r in all_results.values())
        total_pnl = sum(r[regime].total_pnl for r in all_results.values())
        
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        print(f"{regime:<15}: {total_trades:>4} trades | "
              f"Win Rate: {win_rate:>5.1f}% | "
              f"Avg P&L: ${avg_pnl:>+8.0f}")


if __name__ == "__main__":
    main()
