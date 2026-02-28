"""
TurboBounce Options Pricer Backtest
====================================
Uses Black-Scholes to price diagonal spreads at entry and exit.
IV is estimated from 20-day historical realized volatility.
Covers MODE_B (Unified 100%) for one user-specified year.

Run:
    python src/turbobounce/options_pricer_backtest.py
"""

import sys, os, logging
# Silence all loggers before any imports
logging.disable(logging.CRITICAL)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import math
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm
from datetime import datetime, timedelta
from tqdm import tqdm

from src.turbobounce.universe import get_turbobounce_symbols, get_category_for_symbol
from src.turbobounce.risk_manager import TurboBounceRiskManager
from src.turbobounce.strategy_router import StrategyRouter

# ─── Black-Scholes Engine ─────────────────────────────────────────────────────

def bs_call(S, K, T, r, sigma):
    """Black-Scholes call price. T in years."""
    if T <= 0 or sigma <= 0: return max(S - K, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

def bs_put(S, K, T, r, sigma):
    """Black-Scholes put price."""
    if T <= 0 or sigma <= 0: return max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def realized_vol(prices, window=20):
    """Annualized historical volatility from the last N daily returns."""
    if len(prices) < window + 1: return 0.30
    log_returns = np.log(prices / prices.shift(1)).dropna()
    return float(log_returns.iloc[-window:].std() * math.sqrt(252))

def risk_free_rate(date):
    """Approximate risk-free rate by year."""
    year = date.year
    if year <= 2021: return 0.015
    if year == 2022: return 0.025
    if year == 2023: return 0.052
    return 0.053  # 2024+

def price_trade(S, sigma, r, strategy_type, direction, days_held=0,
                anchor_dte=45, hedge_dte=10):
    """
    Price an options structure using Black-Scholes.
    anchor_dte / hedge_dte come from the StrategyRouter output.
    """
    val, bp = 0.0, 0.0

    if strategy_type == 'DIAGONAL':
        # Put Diagonal (Bullish) — or Call Diagonal (Bearish):
        #   SELL the longer-dated option (anchor) — collects rich premium (more time value)
        #   BUY  the shorter-dated option (hedge)  — cheap protection
        # Net result: credit-like position that profits from IV crush + time decay on anchor
        T_anchor = max(1, anchor_dte - days_held) / 365.0   # longer DTE = the leg we SELL
        T_hedge  = max(1, hedge_dte  - days_held) / 365.0   # shorter DTE = the leg we BUY
        pct_otm  = 0.05   # 5% OTM — keeps structure out-of-money for bigger premium differential
        if direction == 'BULLISH':
            # Bull Put Diagonal: SELL longer-dated OTM put, BUY shorter-dated OTM put
            anchor_val = bs_put(S, S * (1 - pct_otm), T_anchor, r, sigma)  # SELL (income)
            hedge_val  = bs_put(S, S * (1 - pct_otm), T_hedge,  r, sigma)  # BUY  (cost)
            val = anchor_val - hedge_val   # positive = net credit (anchor has more time value)
        else:
            # Bear Call Diagonal: SELL longer-dated OTM call, BUY shorter-dated OTM call
            anchor_val = bs_call(S, S * (1 + pct_otm), T_anchor, r, sigma)
            hedge_val  = bs_call(S, S * (1 + pct_otm), T_hedge,  r, sigma)
            val = anchor_val - hedge_val
        bp = anchor_val  # max risk approximately = anchor value if assignment

    elif strategy_type == 'CREDIT_SPREAD':
        T = max(1, anchor_dte - days_held) / 365.0
        if direction == 'BULLISH':
            short_k, long_k = S * 0.97, S * 0.93
            val = bs_put(S, short_k, T, r, sigma) - bs_put(S, long_k, T, r, sigma)
        else:
            short_k, long_k = S * 1.03, S * 1.07
            val = bs_call(S, short_k, T, r, sigma) - bs_call(S, long_k, T, r, sigma)
        bp = abs(short_k - long_k)

    elif strategy_type == 'NAKED_LONG':
        # Entered in LOW-IV regime.
        # FIX: Buying 21 DTE ATM options resulted in 30-40% theta loss over a 5-7 day hold.
        # To mimic true leverage safely, buy longer-dated (anchor_dte) ITM options (approx 70 delta).
        # Less extrinsic value = less theta burn.
        T = max(1, anchor_dte - days_held) / 365.0
        pct_itm = 0.04  # 4% in-the-money
        if direction == 'BULLISH':
            val = bs_call(S, S * (1 - pct_itm), T, r, sigma)   # ITM Call (strike below S)
        else:
            val = bs_put(S, S * (1 + pct_itm), T, r, sigma)    # ITM Put (strike above S)
        bp = val

    return max(0.01, val), max(0.01, bp)

# ─── Scanner / Scoring (inline - no logging) ──────────────────────────────────

def calc_rsi(series, period=2):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

def get_metrics(sub_df):
    close   = float(sub_df['Close'].iloc[-1])
    vol_20  = float(sub_df['Volume'].rolling(20).mean().iloc[-1])
    sma_200 = float(sub_df['Close'].rolling(200).mean().iloc[-1])
    sma_20  = float(sub_df['Close'].rolling(20).mean().iloc[-1])
    std_20  = float(sub_df['Close'].rolling(20).std().iloc[-1])

    pct_b       = (close - (sma_20 - 2*std_20)) / (4*std_20) if std_20 > 0 else 0.5
    dist_sma200 = (close - sma_200) / sma_200 if sma_200 > 0 else 0.0
    rsi_2       = calc_rsi(sub_df['Close'], 2)
    ret_3d_raw  = sub_df['Close'].pct_change(3).iloc[-1]
    ret_3d      = float(ret_3d_raw) if not pd.isna(ret_3d_raw) else 0.0
    rvol        = realized_vol(sub_df['Close'])

    rv_252 = sub_df['Close'].pct_change().rolling(20).std() * math.sqrt(252)
    min_v = rv_252.rolling(252).min().iloc[-1]
    max_v = rv_252.rolling(252).max().iloc[-1]
    iv_rank = ((rvol - min_v) / (max_v - min_v) * 100) if (not pd.isna(min_v)) and (max_v - min_v > 0) else 50.0

    return {
        'close': close, 'avg_volume': vol_20, 'rsi_2': rsi_2,
        'pct_b': pct_b, 'ret_3d': ret_3d, 'dist_sma_200': dist_sma200,
        'realized_vol': rvol, 'iv_rank': iv_rank
    }

def scan_universe(historical_data, current_date, all_symbols):
    candidates = []
    for sym in all_symbols:
        df = historical_data.get(sym)
        if df is None: continue
        sub = df[df.index <= current_date]
        if len(sub) < 201: continue

        m = get_metrics(sub)
        # Liquidity filter
        if m['avg_volume'] < 2_000_000: continue
        # Regime filter: not a falling knife
        if m['dist_sma_200'] < -0.25: continue
        # Signal filter
        is_oversold   = m['rsi_2'] < 10 or m['pct_b'] < 0 or m['ret_3d'] < -0.08
        is_overbought = m['rsi_2'] > 90 or m['pct_b'] > 1.0 or m['ret_3d'] > 0.10
        if not (is_oversold or is_overbought): continue

        direction = 'BULLISH' if is_oversold else 'BEARISH'
        # Score: RSI extremity is main driver
        rsi_score = abs(m['rsi_2'] - 50) / 50 * 40  # 0-40 pts
        candidates.append({'symbol': sym, 'direction': direction,
                           'category': get_category_for_symbol(sym),
                           'score': rsi_score, **m})

    oversold   = sorted([c for c in candidates if c['direction'] == 'BULLISH'], key=lambda x: -x['score'])[:3]
    overbought = sorted([c for c in candidates if c['direction'] == 'BEARISH'], key=lambda x: -x['score'])[:3]
    return oversold + overbought

# ─── Main Backtest ────────────────────────────────────────────────────────────

def run_backtest(start_date='2023-01-01', end_date='2024-01-01', initial_capital=50_000):
    all_symbols = get_turbobounce_symbols()
    risk_mgr   = TurboBounceRiskManager(mode='MODE_B')

    # Download data (extra year back for 200-SMA warmup)
    fetch_start = pd.to_datetime(start_date) - pd.DateOffset(years=1)
    raw = yf.download(all_symbols, start=fetch_start, end=end_date,
                      group_by='ticker', progress=False, auto_adjust=True)

    historical_data = {}
    for sym in all_symbols:
        try:
            historical_data[sym] = raw[sym].dropna()
        except Exception:
            pass

    ref = historical_data.get('SPY', next(iter(historical_data.values())))
    trading_days = ref[ref.index >= start_date].index

    # VIX Data
    vix_df = yf.download('^VIX', start=fetch_start, end=end_date, progress=False, auto_adjust=True)
    vix_close = vix_df['Close'] if 'Close' in vix_df else vix_df

    capital       = initial_capital
    open_positions = []
    trade_log      = []
    MAX_SLOTS      = 6

    # Strategy-specific hold days (realistic for each structure)
    HOLD_DAYS = {
        'DIAGONAL':      15,  # Time spread needs days for theta/vega edge
        'CREDIT_SPREAD': 15,  # Credit spread is also theta-based
        'NAKED_LONG':     5,  # 14 DTE option — must exit quickly before decay kills it
    }

    # Exit thresholds
    STOP_LOSS_PCT      = -0.50  # Close if unrealized loss > 50% of capital deployed
    PROFIT_TARGET_LONG =  0.40  # 40% gain on capital for DIAGONAL / NAKED_LONG
    PROFIT_TARGET_CRED =  0.60  # 60% of credit captured for CREDIT_SPREAD

    router = StrategyRouter()

    for current_date in tqdm(trading_days, desc='Simulating', leave=False):
        vidx = vix_close.index.get_indexer([current_date], method='pad')[0]
        if vidx >= 0:
            vix_lvl = float(vix_close.iloc[vidx])
            vix_sma = float(vix_close.iloc[:vidx+1].rolling(50).mean().iloc[-1]) if vidx >= 50 else 20.0
        else:
            vix_lvl, vix_sma = 20.0, 20.0
        # ── 1. Evaluate open positions for exit ──────────────────────────────
        remaining = []
        for pos in open_positions:
            days_held = (current_date - pos['entry_date']).days
            strategy_hold = HOLD_DAYS.get(pos['strategy_type'], 15)

            exit_df  = historical_data.get(pos['symbol'])
            if exit_df is None:
                remaining.append(pos); continue
            exit_sub = exit_df[exit_df.index <= current_date]
            if len(exit_sub) < 201:
                remaining.append(pos); continue

            exit_S   = float(exit_sub['Close'].iloc[-1])
            exit_r   = risk_free_rate(current_date)
            exit_sig = realized_vol(exit_sub['Close'])

            # IV normalizes after bounce — modest premium over realized at exit
            adjusted_exit_sig = exit_sig * 1.05

            exit_val, _ = price_trade(exit_S, adjusted_exit_sig, exit_r,
                                      strategy_type=pos['strategy_type'],
                                      direction=pos['direction'],
                                      days_held=days_held,
                                      anchor_dte=pos.get('anchor_dte', 30),
                                      hedge_dte=pos.get('hedge_dte', 10))

            if pos['strategy_type'] == 'CREDIT_SPREAD':
                pnl = (pos['entry_val'] - exit_val) * pos['contracts'] * 100
            else:
                pnl = (exit_val - pos['entry_val']) * pos['contracts'] * 100

            pnl_pct = pnl / pos['capital_allocated']

            # Determine exit trigger
            should_exit, exit_reason = False, ''
            if days_held >= strategy_hold:
                should_exit, exit_reason = True, 'TIME'
            elif pnl_pct <= STOP_LOSS_PCT:
                should_exit, exit_reason = True, 'STOP'
            elif pos['strategy_type'] == 'CREDIT_SPREAD' and pnl_pct >= PROFIT_TARGET_CRED:
                should_exit, exit_reason = True, 'PROFIT'
            elif pos['strategy_type'] in ('DIAGONAL', 'NAKED_LONG') and pnl_pct >= PROFIT_TARGET_LONG:
                should_exit, exit_reason = True, 'PROFIT'

            if should_exit:
                capital += pos['capital_allocated'] + pnl
                trade_log.append({
                    'Symbol':     pos['symbol'],
                    'Strategy':   pos['strategy_type'],
                    'Direction':  pos['direction'],
                    'Exit':       exit_reason,
                    'Entry Date': pos['entry_date'].date(),
                    'Exit Date':  current_date.date(),
                    'Days Held':  days_held,
                    'Entry $':    round(pos['entry_val'] * pos['contracts'] * 100, 2),
                    'Exit $':     round(exit_val * pos['contracts'] * 100, 2),
                    'PnL $':      round(pnl, 2),
                    'PnL %':      round(pnl_pct * 100, 1),
                })
            else:
                remaining.append(pos)
        open_positions = remaining

        # ── 2. Scan ───────────────────────────────────────────────────────────
        picks = scan_universe(historical_data, current_date, all_symbols)

        # ── 3. Enter new positions ────────────────────────────────────────────
        for pick in picks:
            is_tqqq   = pick['symbol'] == 'TQQQ'
            pool      = 'TQQQ' if is_tqqq else 'MULTI_TICKER'
            tqqq_open = sum(1 for p in open_positions if p['symbol'] == 'TQQQ')
            ml_open   = sum(1 for p in open_positions if p['pool'] == 'MULTI_TICKER')
            total     = len(open_positions)

            if total >= MAX_SLOTS: continue
            if not risk_mgr.check_correlation_guard(pick['category'], open_positions): continue

            S     = pick['close']
            sigma = pick['realized_vol']
            r     = risk_free_rate(current_date)
            
            # Route strategy via StrategyRouter
            dir_str = "OVERSOLD" if pick['direction'] == 'BULLISH' else "OVERBOUGHT"
            score_obj = type('ScoreObj', (), {'symbol': pick['symbol'], 'direction': dir_str, 'iv_rank': pick['iv_rank']})()
            routed = router.route_candidate(score_obj, vix_lvl, vix_sma)
            strategy_type = routed.strategy_type
            # Pull DTE params from router, but override NAKED_LONG to 60 DTE to survive multi-day holds
            route_anchor = routed.target_anchor_dte or 30
            if strategy_type == 'NAKED_LONG': route_anchor = 60
            anchor_dte = route_anchor
            hedge_dte  = routed.target_hedge_dte  or 10

            # IV multiplier is strategy + regime aware:
            # DIAGONAL     → high VIX regime, implied vol materially above realized
            # CREDIT_SPREAD → moderately elevated IV
            # NAKED_LONG   → router only picks this in LOW-IV; IV ≈ realized (no markup)
            if strategy_type == 'DIAGONAL':
                entry_sigma = sigma * 1.35
            elif strategy_type == 'CREDIT_SPREAD':
                entry_sigma = sigma * 1.20
            else:  # NAKED_LONG — low IV regime
                entry_sigma = sigma * 1.05

            val, bp = price_trade(S, entry_sigma, r, strategy_type, pick['direction'],
                                  days_held=0, anchor_dte=anchor_dte, hedge_dte=hedge_dte)

            if val <= 0: continue  # Avoid zero-cost artifacts

            slot_capital = initial_capital / MAX_SLOTS
            contracts    = max(1, int(slot_capital / (bp * 100)))

            capital -= slot_capital
            open_positions.append({
                'symbol':            pick['symbol'],
                'pool':              pool,
                'category':          pick['category'],
                'direction':         pick['direction'],
                'strategy_type':     strategy_type,
                'entry_date':        current_date,
                'entry_val':         val,
                'contracts':         contracts,
                'capital_allocated': slot_capital,
                'anchor_dte':        anchor_dte,
                'hedge_dte':         hedge_dte,
            })

    # ── Output ────────────────────────────────────────────────────────────────
    df_log = pd.DataFrame(trade_log)

    if df_log.empty:
        print("No trades completed in the period.")
        return

    # ── Trade Table ───────────────────────────────────────────────────────────
    pd.set_option('display.max_rows', None)
    pd.set_option('display.width', 130)
    pd.set_option('display.float_format', '{:,.2f}'.format)
    print("\n" + "="*105)
    print(f"  TURBOBOUNCE MODE B — Options-Priced Backtest  |  {start_date}  to  {end_date}")
    print("="*105)
    print(df_log.to_string(index=False))

    # ── Summary ───────────────────────────────────────────────────────────────
    total_pnl      = df_log['PnL $'].sum()
    wins           = (df_log['PnL $'] > 0).sum()
    losses         = (df_log['PnL $'] <= 0).sum()
    win_rate       = wins / len(df_log) * 100
    avg_win        = df_log[df_log['PnL $'] > 0]['PnL $'].mean()
    avg_loss       = df_log[df_log['PnL $'] <= 0]['PnL $'].mean()
    profit_factor  = abs(df_log[df_log['PnL $'] > 0]['PnL $'].sum() /
                         df_log[df_log['PnL $'] <= 0]['PnL $'].sum()) if losses > 0 else float('inf')
    final_capital  = capital + sum(p['capital_allocated'] for p in open_positions) + total_pnl

    print("\n" + "-"*105)
    print(f"  SUMMARY")
    print(f"  Total Trades    : {len(df_log)}")
    print(f"  Wins / Losses   : {wins} / {losses}  ({win_rate:.1f}% win rate)")
    print(f"  Avg Win         : ${avg_win:>+,.2f}")
    print(f"  Avg Loss        : ${avg_loss:>+,.2f}")
    print(f"  Profit Factor   : {profit_factor:.2f}x")
    print(f"  Total PnL       : ${total_pnl:>+,.2f}")
    print(f"  Return          : {total_pnl/initial_capital*100:>+.2f}%")
    print(f"  Final Capital   : ${final_capital:>,.2f}")

    tqqq_trades = df_log[df_log['Symbol'] == 'TQQQ']
    multi_trades = df_log[df_log['Symbol'] != 'TQQQ']
    print(f"\n  TQQQ trades     : {len(tqqq_trades)} | PnL ${tqqq_trades['PnL $'].sum():>+,.2f}")
    print(f"  Multi-T trades  : {len(multi_trades)} | PnL ${multi_trades['PnL $'].sum():>+,.2f}")
    print("="*105)

if __name__ == "__main__":
    run_backtest(start_date='2023-01-01', end_date='2024-01-01')
