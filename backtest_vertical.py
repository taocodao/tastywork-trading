"""
Vertical Spread Strategy Backtest
===================================
Backtest bull call spreads and bear put spreads using historical data.

Strategy:
- Bull Call Spreads: Buy ATM call + Sell OTM call (bullish bias)
- Bear Put Spreads: Buy ATM put + Sell OTM put (bearish bias)
- Entry: RSI oversold (<30) or overbought (>70)
- Exit: 50% profit target or 50% stop loss
- DTE: 14-21 days
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
import math
from scipy.stats import norm


@dataclass
class VerticalBacktestTrade:
    """A single vertical spread trade."""
    trade_id: int
    symbol: str
    trade_date: datetime
    strategy: str  # BULL_CALL_SPREAD or BEAR_PUT_SPREAD
    
    # Spread details
    buy_strike: float
    sell_strike: float
    stock_price: float
    
    # Entry
    entry_debit: float
    max_profit: float
    max_loss: float
    iv_entry: float
    
    # Exit
    exit_date: datetime
    exit_value: float
    hold_days: int
    
    # P&L
    gross_pnl: float
    commission: float = 4.0  # $2 per leg x 2
    slippage: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0
    
    # Outcome
    is_winner: bool = False
    exit_reason: str = ""
    
    def __post_init__(self):
        self.slippage = self.entry_debit * 0.02
        self.net_pnl = self.gross_pnl - self.commission - self.slippage
        self.pnl_pct = (self.net_pnl / self.entry_debit * 100) if self.entry_debit > 0 else 0
        self.is_winner = self.net_pnl > 0


class BlackScholesSimple:
    """Simplified Black-Scholes for option pricing."""
    
    def __init__(self, r=0.05):
        self.r = r
    
    def d1(self, S, K, T, sigma):
        if T <= 0:
            return 0
        return (np.log(S/K) + (self.r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    
    def call_price(self, S, K, T, sigma):
        if T <= 0:
            return max(0, S - K)
        d1 = self.d1(S, K, T, sigma)
        d2 = d1 - sigma*np.sqrt(T)
        return S*norm.cdf(d1) - K*np.exp(-self.r*T)*norm.cdf(d2)
    
    def put_price(self, S, K, T, sigma):
        if T <= 0:
            return max(0, K - S)
        d1 = self.d1(S, K, T, sigma)
        d2 = d1 - sigma*np.sqrt(T)
        return K*np.exp(-self.r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)


class VerticalSpreadBacktest:
    """Backtest engine for vertical spreads."""
    
    def __init__(self, symbol: str, start_date: str, end_date: str):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.bs = BlackScholesSimple()
        self.trades: List[VerticalBacktestTrade] = []
        self.trade_counter = 0
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def get_direction_signal(self, rsi: float) -> Optional[str]:
        """Get directional signal based on RSI."""
        if rsi < 30:
            return "BULL"  # Oversold - expect bounce
        elif rsi > 70:
            return "BEAR"  # Overbought - expect pullback
        return None
    
    def enter_bull_call_spread(self, stock_price: float, iv: float, dte: int = 14):
        """
        Enter bull call spread.
        Buy ATM call + Sell 5% OTM call
        """
        T = dte / 365
        
        # Strike selection
        buy_strike = round(stock_price / 5) * 5  # Round to nearest $5
        sell_strike = buy_strike + (buy_strike * 0.05)  # 5% higher
        sell_strike = round(sell_strike / 5) * 5
        
        # Price options
        buy_premium = self.bs.call_price(stock_price, buy_strike, T, iv)
        sell_premium = self.bs.call_price(stock_price, sell_strike, T, iv)
        
        entry_debit = (buy_premium - sell_premium) * 100  # Per contract
        max_profit = (sell_strike - buy_strike) * 100 - entry_debit
        max_loss = entry_debit
        
        return {
            "buy_strike": buy_strike,
            "sell_strike": sell_strike,
            "entry_debit": entry_debit,
            "max_profit": max_profit,
            "max_loss": max_loss
        }
    
    def enter_bear_put_spread(self, stock_price: float, iv: float, dte: int = 14):
        """
        Enter bear put spread.
        Buy ATM put + Sell 5% OTM put
        """
        T = dte / 365
        
        # Strike selection
        buy_strike = round(stock_price / 5) * 5
        sell_strike = buy_strike - (buy_strike * 0.05)  # 5% lower
        sell_strike = round(sell_strike / 5) * 5
        
        # Price options
        buy_premium = self.bs.put_price(stock_price, buy_strike, T, iv)
        sell_premium = self.bs.put_price(stock_price, sell_strike, T, iv)
        
        entry_debit = (buy_premium - sell_premium) * 100
        max_profit = (buy_strike - sell_strike) * 100 - entry_debit
        max_loss = entry_debit
        
        return {
            "buy_strike": buy_strike,
            "sell_strike": sell_strike,
            "entry_debit": entry_debit,
            "max_profit": max_profit,
            "max_loss": max_loss
        }
    
    def run_backtest(self, df: pd.DataFrame):
        """Run the backtest on historical data."""
        print(f"\nBacktesting {self.symbol} vertical spreads...")
        print(f"Period: {self.start_date} to {self.end_date}")
        print("=" * 70)
        
        # Calculate RSI
        df['rsi'] = self.calculate_rsi(df['Close'])
        
        # Calculate implied volatility (estimate from historical vol)
        df['returns'] = df['Close'].pct_change()
        df['iv'] = df['returns'].rolling(window=20).std() * np.sqrt(252)
        df['iv'] = df['iv'].fillna(0.20)  # Default 20% IV
        
        in_position = False
        position_data = None
        
        for i in range(20, len(df)-15):  # Need RSI warmup + exit buffer
            current_date = df.index[i]
            stock_price = df['Close'].iloc[i]
            rsi = df['rsi'].iloc[i]
            iv = df['iv'].iloc[i]
            
            # Entry logic
            if not in_position:
                direction = self.get_direction_signal(rsi)
                
                if direction == "BULL":
                    setup = self.enter_bull_call_spread(stock_price, iv, dte=14)
                    position_data = {
                        "entry_date": current_date,
                        "strategy": "BULL_CALL_SPREAD",
                        "direction": direction,
                        "stock_price": stock_price,
                        "iv": iv,
                        **setup
                    }
                    in_position = True
                    
                elif direction == "BEAR":
                    setup = self.enter_bear_put_spread(stock_price, iv, dte=14)
                    position_data = {
                        "entry_date": current_date,
                        "strategy": "BEAR_PUT_SPREAD",
                        "direction": direction,
                        "stock_price": stock_price,
                        "iv": iv,
                        **setup
                    }
                    in_position = True
            
            # Exit logic
            elif in_position and position_data:
                hold_days = (current_date - position_data["entry_date"]).days
                dte_remaining = 14 - hold_days
                
                if dte_remaining <= 0:
                    dte_remaining = 1
                
                T = dte_remaining / 365
                
                # Calculate current spread value
                if position_data["strategy"] == "BULL_CALL_SPREAD":
                    buy_value = self.bs.call_price(stock_price, position_data["buy_strike"], T, iv)
                    sell_value = self.bs.call_price(stock_price, position_data["sell_strike"], T, iv)
                else:  # BEAR_PUT_SPREAD
                    buy_value = self.bs.put_price(stock_price, position_data["buy_strike"], T, iv)
                    sell_value = self.bs.put_price(stock_price, position_data["sell_strike"], T, iv)
                
                current_value = (buy_value - sell_value) * 100
                pnl = current_value - position_data["entry_debit"]
                pnl_pct = (pnl / position_data["entry_debit"]) * 100
                
                # Exit conditions
                exit_reason = None
                
                if pnl_pct >= 50:  # 50% profit target
                    exit_reason = "PROFIT_TARGET"
                elif pnl_pct <= -50:  # 50% stop loss
                    exit_reason = "STOP_LOSS"
                elif dte_remaining <= 2:  # Exit 2 days before expiration
                    exit_reason = "DTE_EXIT"
                
                if exit_reason:
                    # Record trade
                    trade = VerticalBacktestTrade(
                        trade_id=self.trade_counter,
                        symbol=self.symbol,
                        trade_date=position_data["entry_date"],
                        strategy=position_data["strategy"],
                        buy_strike=position_data["buy_strike"],
                        sell_strike=position_data["sell_strike"],
                        stock_price=position_data["stock_price"],
                        entry_debit=position_data["entry_debit"],
                        max_profit=position_data["max_profit"],
                        max_loss=position_data["max_loss"],
                        iv_entry=position_data["iv"],
                        exit_date=current_date,
                        exit_value=current_value,
                        hold_days=hold_days,
                        gross_pnl=pnl,
                        exit_reason=exit_reason
                    )
                    
                    self.trades.append(trade)
                    self.trade_counter += 1
                    in_position = False
                    position_data = None
        
        return self.analyze_results()
    
    def analyze_results(self):
        """Analyze backtest results."""
        if not self.trades:
            print("No trades executed!")
            return
        
        winners = [t for t in self.trades if t.is_winner]
        losers = [t for t in self.trades if not t.is_winner]
        
        total_pnl = sum(t.net_pnl for t in self.trades)
        avg_win = np.mean([t.net_pnl for t in winners]) if winners else 0
        avg_loss = np.mean([t.net_pnl for t in losers]) if losers else 0
        win_rate = len(winners) / len(self.trades) * 100
        
        # Strategy breakdown
        bull_trades = [t for t in self.trades if t.strategy == "BULL_CALL_SPREAD"]
        bear_trades = [t for t in self.trades if t.strategy == "BEAR_PUT_SPREAD"]
        
        print("\n" + "=" * 70)
        print(f"VERTICAL SPREAD BACKTEST RESULTS - {self.symbol}")
        print("=" * 70)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Total Trades: {len(self.trades)}")
        print()
        print("PERFORMANCE METRICS")
        print("-" * 40)
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Wins: {len(winners)} | Losses: {len(losers)}")
        print(f"  Total P&L: ${total_pnl:.2f}")
        print(f"  Avg Win: ${avg_win:.2f}")
        print(f"  Avg Loss: ${avg_loss:.2f}")
        print()
        print("STRATEGY BREAKDOWN")
        print("-" * 40)
        print(f"  Bull Call Spreads: {len(bull_trades)} trades")
        print(f"  Bear Put Spreads: {len(bear_trades)} trades")
        print()
        
        # Calculate monthly P&L
        monthly_pnl = {}
        for trade in self.trades:
            month = trade.trade_date.strftime("%Y-%m")
            monthly_pnl[month] = monthly_pnl.get(month, 0) + trade.net_pnl
        
        print("MONTHLY P&L")
        print("-" * 40)
        for month, pnl in sorted(monthly_pnl.items()):
            bar = "█" * int(abs(pnl) / 50)
            sign = "+" if pnl >= 0 else "-"
            print(f"  {month}: {sign}${abs(pnl):.0f} {bar}")
        
        print("=" * 70)
        
        return {
            "total_trades": len(self.trades),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "winners": len(winners),
            "losers": len(losers)
        }


def main():
    """Run backtest on multiple symbols."""
    symbols = ["SPY", "QQQ", "IWM"]
    start_date = "2024-01-01"
    end_date = "2024-12-31"
    
    all_results = {}
    
    for symbol in symbols:
        print(f"\n{'=' * 70}")
        print(f"Fetching data for {symbol}...")
        print(f"{'=' * 70}")
        
        # Download data
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            print(f"No data for {symbol}")
            continue
        
        print(f"Loaded {len(df)} days of data")
        
        # Run backtest
        backtest = VerticalSpreadBacktest(symbol, start_date, end_date)
        results = backtest.run_backtest(df)
        all_results[symbol] = results
    
    # Combined summary
    print("\n" + "=" * 70)
    print("COMBINED RESULTS (ALL SYMBOLS)")
    print("=" * 70)
    
    total_trades = sum(r["total_trades"] for r in all_results.values())
    total_pnl = sum(r["total_pnl"] for r in all_results.values())
    total_winners = sum(r["winners"] for r in all_results.values())
    total_losers = sum(r["losers"] for r in all_results.values())
    overall_wr = (total_winners / total_trades * 100) if total_trades > 0 else 0
    
    print(f"\n  Total Trades: {total_trades}")
    print(f"  Overall Win Rate: {overall_wr:.1f}%")
    print(f"  Total P&L: ${total_pnl:.2f}")
    print(f"  Initial Capital: $50,000")
    print(f"  Final Capital: ${50000 + total_pnl:.0f}")
    print(f"  Return on Capital: {(total_pnl / 50000) * 100:.1f}%")
    print()
    print(f"  Per Symbol:")
    for symbol, r in all_results.items():
        wr = r["win_rate"]
        pnl = r["total_pnl"]
        trades = r["total_trades"]
        print(f"    {symbol}: {trades} trades, {wr:.0f}% win rate, ${pnl:+.0f} ({(pnl/50000)*100:+.1f}%)")


if __name__ == "__main__":
    main()
