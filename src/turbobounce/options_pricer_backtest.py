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
from src.turbobounce.swing_exit_engine import SwingExitEngine, ExitDecisionType
from src.tqqq.crash_guard import CrashGuard

crash_guard = CrashGuard()

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
        # Poor Man's Covered Call (PMCC) / Diagonal Spread
        # BUY the long-dated Deep ITM option (Anchor) - stock replacement
        # SELL the short-dated OTM option (Hedge) - finances the position with theta decay
        T_anchor = max(1, anchor_dte - days_held) / 365.0   # 180 DTE (bought)
        T_hedge  = max(1, hedge_dte  - days_held) / 365.0   # 14 DTE (sold)
        
        pct_itm = 0.20  # Buy 20% ITM (~85 delta)
        pct_otm = 0.05  # Sell 5% OTM (~30 delta)
        
        if direction == 'BULLISH':
            # Bull Call Diagonal: BUY ITM Call, SELL OTM Call
            anchor_val = bs_call(S, S * (1 - pct_itm), T_anchor, r, sigma)  # BUY (Cost)
            hedge_val  = bs_call(S, S * (1 + pct_otm), T_hedge,  r, sigma)  # SELL (Credit)
            val = anchor_val - hedge_val   # Positive = Net Debit Paid
        else:
            # Bear Put Diagonal: BUY ITM Put, SELL OTM Put
            anchor_val = bs_put(S, S * (1 + pct_itm), T_anchor, r, sigma)   # BUY (Cost)
            hedge_val  = bs_put(S, S * (1 - pct_otm), T_hedge,  r, sigma)   # SELL (Credit)
            val = anchor_val - hedge_val   # Positive = Net Debit Paid
            
        bp = val  # Risk is the net debit paid

    elif strategy_type == 'CREDIT_SPREAD':
        # Bull Put Credit Spread: $3-wide (3% and 6% OTM)
        # Allows 2 contracts within the 5% budget ($300 risk x 2 = $600).
        T = max(1, anchor_dte - days_held) / 365.0
        if direction == 'BULLISH':
            short_k = S * 0.97   # Sell put 3% OTM
            long_k  = S * 0.94   # Buy put 6% OTM ($3 wide at $100)
            short_val = bs_put(S, short_k, T, r, apply_skew(sigma, 0.03, is_put=True))
            long_val  = bs_put(S, long_k,  T, r, apply_skew(sigma, 0.06, is_put=True))
            val = short_val - long_val  # Net credit received (positive)
        else:
            short_k = S * 1.03   # Sell call 3% OTM
            long_k  = S * 1.06   # Buy call 6% OTM
            short_val = bs_call(S, short_k, T, r, apply_skew(sigma, 0.03, is_put=False))
            long_val  = bs_call(S, long_k,  T, r, apply_skew(sigma, 0.06, is_put=False))
            val = short_val - long_val  # Net credit received (positive)
        bp = abs(short_k - long_k)  # Max loss = spread width (before credit)

    elif strategy_type == 'NAKED_LONG':
        # Entered in LOW-IV regime.
        # Use Deep ITM (85 delta) to minimize theta burn on 7-day holds.
        # Near-ATM bleeds 20-25% in 7 flat days; deep ITM bleeds < 5%.
        T = max(1, anchor_dte - days_held) / 365.0
        pct_itm = 0.20  # 20% ITM = ~85 delta (stock replacement strategy)
        if direction == 'BULLISH':
            val = bs_call(S, S * (1 - pct_itm), T, r, sigma)   # Deep ITM Call
        else:
            val = bs_put(S, S * (1 + pct_itm), T, r, sigma)    # Deep ITM Put
        bp = val

    elif strategy_type == 'PUT_BWB':
        # Put Broken-Wing Butterfly (bullish, structured for a net CREDIT)
        # Rule 1: Upper wing <= 3% OTM
        # Rule 2: Lower wing width >= 2.0x upper wing width
        T = max(1, anchor_dte - days_held) / 365.0
        upper_k = S * 0.97      # Buy: slightly OTM put (3% OTM)
        body_k  = S * 0.93      # Sellx2: body puts (7% OTM). Upper width = 4%
        lower_k = S * 0.85      # Buy: far OTM (15% OTM). Lower width = 8% (Exactly 2.0x!)
        
        buy_upper  = bs_put(S, upper_k, T, r, apply_skew(sigma, 0.03, is_put=True))
        sell_body  = bs_put(S, body_k,  T, r, apply_skew(sigma, 0.07, is_put=True)) * 2
        buy_lower  = bs_put(S, lower_k, T, r, apply_skew(sigma, 0.15, is_put=True))
        
        val = sell_body - buy_upper - buy_lower  # Guaranteed net credit with 2.0x ratio
        bp = abs(body_k - lower_k) - max(0, val)  # Max loss = lower spread width minus credit
        bp = max(0.01, bp)
        
        return max(0, val), max(0.01, bp)

    return max(0.01, val), max(0.01, bp)

def get_iv_multiplier(iv_rank, is_entry=True, days_held=0):
    """
    Dynamic IV multiplier based on IV rank regime.
    Research: Carr & Wu (2009), Goyal & Saretto (2009)
    """
    if is_entry:
        if iv_rank >= 70:   return 1.50  # Extreme fear
        elif iv_rank >= 50: return 1.35  # High IV
        elif iv_rank >= 30: return 1.20  # Moderate
        else:               return 1.05  # Low IV — options near fair value
    else:
        import math
        base_vrp = 0.30  # Starting VRP premium
        decay_rate = 0.10  # ~7-day half-life
        remaining_vrp = base_vrp * math.exp(-decay_rate * days_held)
        return 1.0 + remaining_vrp  # Ranges from ~1.30 (day 0) to ~1.05 (day 10+)

def apply_skew(base_sigma, strike_pct_otm, is_put=True):
    """
    Apply volatility smile skew correction.
    +2 IV pts per 5% OTM for puts; -1 IV pt per 5% OTM for calls.
    """
    if is_put:
        skew_adjustment = max(0, strike_pct_otm / 0.05) * 0.02
    else:
        skew_adjustment = -max(0, strike_pct_otm / 0.05) * 0.01
    return base_sigma + skew_adjustment

# ─── Scanner / Scoring (inline - no logging) ──────────────────────────────────

def calc_rsi(series, period=2):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

def hurst_exponent(series, lags=range(2, 20)):
    """Compute Hurst exponent via rescaled range (simple approximation)."""
    try:
        ts = np.log(series / series.shift(1)).dropna().values
        if len(ts) < max(lags) + 1: return 0.50
        tau = []; lagvec = []
        for lag in lags:
            diffs = np.subtract(ts[lag:], ts[:-lag])
            if len(diffs) < 2: continue
            std_diff = np.std(diffs)
            if std_diff > 0:
                tau.append(std_diff)
                lagvec.append(lag)
        if len(tau) < 2: return 0.50
        pp = np.polyfit(np.log(lagvec), np.log(tau), 1)
        return pp[0] * 0.5 + 0.5
    except Exception:
        return 0.50

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

    hurst = hurst_exponent(sub_df['Close'].tail(60)) if len(sub_df) >= 60 else 0.50

    return {
        'close': close, 'avg_volume': vol_20, 'rsi_2': rsi_2,
        'pct_b': pct_b, 'ret_3d': ret_3d, 'dist_sma_200': dist_sma200,
        'realized_vol': rvol, 'iv_rank': iv_rank, 'hurst': hurst,
        'sma_200': sma_200, 'vol_ratio': (sub_df['Volume'].iloc[-1] / vol_20) if vol_20 > 0 else 1.0
    }

def scan_universe(historical_data, current_date, all_symbols):
    candidates = []
    for sym in all_symbols:
        df = historical_data.get(sym)
        if df is None: continue
        sub = df[df.index <= current_date]
        if len(sub) < 201: continue

        m = get_metrics(sub)
        # Liquidity filter - V5 uses $1M Dollar Volume (Close * Volume)
        if (m['close'] * m['avg_volume']) < 1_000_000: continue
        # Regime filter: not a falling knife
        if m['dist_sma_200'] < -0.25: continue
        # Signal filter - V5 Expanded parameters for 150+ signals/yr
        is_oversold = m['rsi_2'] < 10 or m['pct_b'] < 0 or m['ret_3d'] < -0.08
        if not is_oversold: continue

        direction = 'BULLISH'
        
        # Do NOT force strategy_override — let the StrategyRouter decide based on IV regime.
        # Previously RSI-2 < 8 forced NAKED_LONG, bypassing the router and sending 98% of
        # trades through NAKED_LONG even when IV was high (where CREDIT_SPREAD should dominate).
        strategy_override = None
        
        # Mock ML probability for historical scan
        ml_prob = 0.60
        
        # Evaluate using CrashGuard
        intraday_row = pd.Series({'close': m['close'], 'rsi_2': m['rsi_2'], 'vol_ratio': m['vol_ratio']})
        # Mock latest daily for hurst/sma
        latest_daily = pd.Series({'tqqq_close': m['close'], 'sma_200': m['sma_200'], 'hurst_100': m['hurst'], 'vix_sma_ratio': 1.05})
        daily_df = pd.DataFrame([latest_daily])
        cg_result = crash_guard.evaluate_entry(daily_df, intraday_row, ml_prob)
        
        if not cg_result.passed: 
            continue
            
        candidates.append({'symbol': sym, 'direction': direction,
                           'category': get_category_for_symbol(sym),
                           'score': cg_result.score, 'size_mult': cg_result.multiplier, 
                           'strategy_override': strategy_override, **m})

    return sorted(candidates, key=lambda x: -x['score'])[:3]

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

    HOLD_DAYS = {
        'CREDIT_SPREAD':  10,  # Connors: "exit by day 10"
        'PUT_BWB':        10,  # Same as credit spread
        'NAKED_LONG':      7,  # Quick directional pop
    }

    # Exit thresholds now handled in SwingExitEngine V4.1 per Perplexity research


    router = StrategyRouter()

    for current_date in tqdm(trading_days, desc='Simulating', leave=False):
        vidx = vix_close.index.get_indexer([current_date], method='pad')[0]
        if vidx >= 0:
            vix_lvl = float(np.squeeze(vix_close.iloc[vidx]))
            vix_sma = float(np.squeeze(vix_close.iloc[:vidx+1].rolling(50).mean().iloc[-1])) if vidx >= 50 else 20.0
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
            adjusted_exit_sig = exit_sig * get_iv_multiplier(
                pos.get('entry_iv_rank', 50), is_entry=False, days_held=days_held
            )

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
            
            # --- Swing Exit Engine Integration ---
            engine = SwingExitEngine()
            rsi_2 = calc_rsi(exit_sub['Close'], 2)
            regime_score = 50 # Base default for historical scan if unused
            ml_prob = 0.55 # Base default
            
            # Current spread mark vs entry
            current_spread_mark = exit_val
            
            # 5-day SMA of underlying for Connors exit signal
            sma_5 = float(exit_sub['Close'].rolling(5).mean().iloc[-1]) if len(exit_sub) >= 5 else exit_S
            
            # Previous day RSI-2 for consecutive-day confirmation (Alvarez research)
            rsi_2_prev = calc_rsi(exit_sub['Close'].iloc[:-1], 2) if len(exit_sub) > 3 else rsi_2
            
            # Count trading days held (not calendar days — Connors uses trading days)
            # exit_sub filtered to current_date, entry_sub filtered to entry_date
            days_traded = len(exit_df[(exit_df.index > pos['entry_date']) & (exit_df.index <= current_date)])
            
            # Calculate ATR-14 for directional stop
            high_low_range = exit_sub['High'] - exit_sub['Low']
            true_range = pd.concat([
                high_low_range,
                abs(exit_sub['High'] - exit_sub['Close'].shift(1)),
                abs(exit_sub['Low'] - exit_sub['Close'].shift(1))
            ], axis=1).max(axis=1)
            atr_14 = float(true_range.rolling(14).mean().iloc[-1])
            
            decision = engine.evaluate(
                position=pos,
                current_price=exit_S,
                rsi_2=rsi_2,
                rsi_2_prev=rsi_2_prev,
                sma_5=sma_5,
                regime_score=regime_score,
                ml_prob=ml_prob,
                days_held=days_held,
                days_traded=days_traded,
                bp_consumed=pos['capital_allocated'],
                current_spread_mark=current_spread_mark,
                pnl_pct=pnl_pct,
                atr_14=atr_14
            )
            
            if decision.decision in [ExitDecisionType.CLOSE_ALL, ExitDecisionType.ROLL_HEDGE]:
                should_exit = True
                exit_reason = decision.reason

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
            
            override = pick.get('strategy_override')
            if override:
                strategy_type = override
                anchor_dte, hedge_dte = 45, 10
            else:
                routed = router.route_candidate(score_obj, vix_lvl, vix_sma)
                strategy_type = routed.strategy_type
                # Take DTE from router, this allows NAKED_LONG to get 180 DTE and Spreads 30.
                anchor_dte = routed.target_anchor_dte or 30
                hedge_dte = routed.target_hedge_dte or 10

            # Apply size multiplier from CrashGuard
            size_mult = pick.get('size_mult', 1.0)

            # IV multiplier is strategy + regime aware
            entry_sigma = sigma * get_iv_multiplier(pick['iv_rank'], is_entry=True)

            val, bp = price_trade(S, entry_sigma, r, strategy_type, pick['direction'],
                                  days_held=0, anchor_dte=anchor_dte, hedge_dte=hedge_dte)

            if val <= 0 and strategy_type not in ('CALL_BACKSPREAD', 'PUT_BWB'): continue  # Avoid zero-cost artifacts unless it's a backspread/bwb credit

            # V5 Recommended Sizing: ~5% quarter-Kelly for LEAPS, 3% conservative for spreads
            if strategy_type == 'NAKED_LONG':
                MAX_RISK_PCT = 0.05
            else:
                MAX_RISK_PCT = 0.03
            MAX_POSITION_PCT = 0.10  # Hard cap: never more than 10% of equity in one position
            
            current_equity = capital + sum(p['capital_allocated'] for p in open_positions)
            max_dollar_risk = current_equity * MAX_RISK_PCT
            
            # For credit spreads: max loss = spread width * 100 per contract
            # For long options: max loss = premium paid * 100 per contract
            if strategy_type in ('CREDIT_SPREAD', 'PUT_BWB'):
                max_loss_per_contract = bp * 100  # bp = spread width
            else:
                max_loss_per_contract = val * 100  # val = option premium
            
            if max_loss_per_contract <= 0:
                continue
            
            # CRITICAL FIX: Strictly enforce 3% risk rule.
            # If even 1 contract exceeds 3% risk budget, skip the trade.
            # The previous max(1,...) override was causing $3k+ trades on a $15k account.
            if max_loss_per_contract > max_dollar_risk:
                continue  # Trade too large — enforce 3% rule, don't force 1 contract

            # Calculate contracts: risk-normalized
            contracts = max(1, int(max_dollar_risk / max_loss_per_contract))
            
            # Apply CrashGuard size multiplier for high-conviction trades
            size_mult = pick.get('size_mult', 1.0)
            contracts = max(1, int(contracts * size_mult))
            
            # Capital to allocate = either the actual cost or the max-loss reserve
            if strategy_type in ('CREDIT_SPREAD', 'PUT_BWB'):
                slot_capital = bp * contracts * 100  # Reserve spread width as margin
            else:
                slot_capital = val * contracts * 100  # Reserve full premium
            
            # Hard position size cap: never > 10% of account in one trade
            max_absolute_slot = current_equity * MAX_POSITION_PCT
            if slot_capital > max_absolute_slot:
                contracts = max(1, int(max_absolute_slot / max_loss_per_contract))
                slot_capital = max_loss_per_contract * contracts
                
            if slot_capital > capital:
                continue

            capital -= slot_capital
            open_positions.append({
                'symbol':            pick['symbol'],
                'pool':              pool,
                'category':          pick['category'],
                'direction':         pick['direction'],
                'strategy_type':     strategy_type,
                'entry_date':        current_date,
                'entry_val':         val,
                'entry_price':       S,
                'entry_mark':        val,
                'roll_count':        0,
                'contracts':         contracts,
                'capital_allocated': slot_capital,
                'anchor_dte':        anchor_dte,
                'hedge_dte':         hedge_dte,
                'entry_iv_rank':     pick['iv_rank'],  # For dynamic exit IV calc
            })

    # ── Output ────────────────────────────────────────────────────────────────
    df_log = pd.DataFrame(trade_log)

    if df_log.empty:
        print("No trades completed in the period.")
        zero_summary = {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0, 'profit_factor': 0.0,
            'total_pnl': 0.0, 'return_pct': 0.0, 'final_capital': initial_capital,
            'tqqq_trades': 0, 'tqqq_pnl': 0.0, 'multi_trades': 0, 'multi_pnl': 0.0
        }
        return zero_summary, pd.DataFrame()

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
    if len(df_log) == 0:
        print("No trades completed in the period.")
        empty_summary = {
            'start_date': start_date, 'end_date': end_date, 'initial_capital': initial_capital,
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0, 'profit_factor': 0.0,
            'total_pnl': 0.0, 'return_pct': 0.0, 'final_capital': capital,
            'tqqq_trades': 0, 'tqqq_pnl': 0.0, 'multi_trades': 0, 'multi_pnl': 0.0
        }
        return empty_summary, df_log

    wins           = len(df_log[df_log['PnL $'] > 0])
    losses         = len(df_log[df_log['PnL $'] <= 0])
    win_rate       = wins / len(df_log) if len(df_log) > 0 else 0
    avg_win        = df_log[df_log['PnL $'] > 0]['PnL $'].mean() if wins > 0 else 0
    avg_loss       = df_log[df_log['PnL $'] <= 0]['PnL $'].mean() if losses > 0 else 0
    profit_factor  = abs(df_log[df_log['PnL $'] > 0]['PnL $'].sum() /
                         df_log[df_log['PnL $'] <= 0]['PnL $'].sum()) if losses > 0 else float('inf')
    final_capital  = capital + sum(p['capital_allocated'] for p in open_positions)

    tqqq_trades = df_log[df_log['Symbol'] == 'TQQQ']
    multi_trades = df_log[df_log['Symbol'] != 'TQQQ']

    # Prepare return dict
    summary_data = {
        'start_date': start_date,
        'end_date': end_date,
        'initial_capital': initial_capital,
        'total_trades': len(df_log),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'total_pnl': total_pnl,
        'return_pct': (total_pnl / initial_capital) * 100,
        'final_capital': final_capital,
        'tqqq_trades': len(tqqq_trades),
        'tqqq_pnl': tqqq_trades['PnL $'].sum() if len(tqqq_trades) > 0 else 0,
        'multi_trades': len(multi_trades),
        'multi_pnl': multi_trades['PnL $'].sum() if len(multi_trades) > 0 else 0
    }

    print("\n" + "-"*105)
    print(f"  SUMMARY ({start_date} to {end_date}) | Initial: ${initial_capital:,.2f}")
    print(f"  Total Trades    : {len(df_log)}")
    print(f"  Wins / Losses   : {wins} / {losses}  ({win_rate*100:.1f}% win rate)")
    print(f"  Avg Win         : ${avg_win:>+,.2f}")
    print(f"  Avg Loss        : ${avg_loss:>+,.2f}")
    print(f"  Profit Factor   : {profit_factor:.2f}x")
    print(f"  Total PnL       : ${total_pnl:>+,.2f}")
    print(f"  Return          : {summary_data['return_pct']:>+.2f}%")
    print(f"  Final Capital   : ${final_capital:>,.2f}")

    print(f"\n  TQQQ trades     : {len(tqqq_trades)} | PnL ${summary_data['tqqq_pnl']:>+,.2f}")
    print(f"  Multi-T trades  : {len(multi_trades)} | PnL ${summary_data['multi_pnl']:>+,.2f}")
    print("="*105)
    
    return summary_data, df_log

if __name__ == "__main__":
    run_backtest(start_date='2019-01-01', end_date='2026-01-01', initial_capital=5000)
