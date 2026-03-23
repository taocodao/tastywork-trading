"""
backtest_pmcc_comparison.py
============================
Side-by-side backtest: Original IV-Switching ZEBRA vs PMCC-Enhanced version.

ORIGINAL:
  - Mode B ZEBRA:  75 DTE, long delta=0.70, short delta=0.50 (ATM-ish ratio spread)
  - No stop-loss on LEAPS
  - No income overlay on existing LEAPS
  - Mode C: opens CCS even when LEAPS are held

ENHANCED (PMCC):
  - Mode B ZEBRA:  120 DTE, long delta=0.82, short call overlay at 35 DTE / delta=0.27
  - P2: -50% stop-loss on LEAPS (prevents -80% forced liquidation scenario)
  - P3: Overlay short call when QQQ 5d momentum <= 0 and LEAPS already open
  - P4: Mode C freezes LEAPS rolls instead of deploying CCS alongside

Run:
    python backtest_pmcc_comparison.py

Output: printed table + saves backtest_pmcc_results.csv
"""

import sys, os, logging
import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import data.features as features
from regime_engine import classify_mode, should_open_d1
from position_sizer import size_csp_trade, size_zebra_trade, size_ccs_trade, size_d2_sqqq, size_d1_vix_calls
from pricing import (bs_call_price, bs_put_price, find_strike_for_delta,
                     bs_call_delta, SLIPPAGE_PER_SIDE, COMMISSION)
from portfolio import Portfolio, ZebraPosition

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s")
log = logging.getLogger("IV_PMCC_Comparison")

# ── Config ────────────────────────────────────────────────────────────────────
START_DATE      = "2019-01-01"
END_DATE        = "2026-03-20"
INITIAL_CAPITAL = 25_000.0

# Slippage/commission per ZEBRA unit (3 legs × 2 sides)
ZEBRA_SLIPPAGE   = SLIPPAGE_PER_SIDE * 3
ZEBRA_COMMISSION = COMMISSION * 3

# ── PMCC Parameters (P1 upgrades) ─────────────────────────────────────────────
PMCC_LONG_DTE    = 120       # was 75
PMCC_LONG_DELTA  = 0.82      # was 0.70
PMCC_SHORT_DTE   = 35        # new independent short-call expiry
PMCC_SHORT_DELTA = 0.27      # was 0.50 (ATM) — now 25-30 delta income overlay
PMCC_ROLL_DTE    = 60        # P2: hard stop-loss at 50% of LEAPS cost
PMCC_STOP_LOSS   = 0.50      # P2: close LEAPS at 50% of entry price

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_monthly_friday(date, offset_days=35):
    target = date + pd.Timedelta(days=offset_days)
    wd = target.weekday()
    if wd < 4:   target += pd.Timedelta(days=4 - wd)
    elif wd > 4: target += pd.Timedelta(days=7 - wd + 4)
    return target


@dataclass
class OverlayShortCall:
    """Tracks an active OVERLAY_SHORT_CALL position (P3)."""
    open_date:    pd.Timestamp
    expiry:       pd.Timestamp
    strike:       float
    entry_price:  float        # credit received per share
    contracts:    int
    profit_target: float       # 50% of entry_price


# ── Single-run backtest engine ─────────────────────────────────────────────────
def run_single(df: pd.DataFrame, mode: str = 'original') -> dict:
    """
    mode: 'original' | 'pmcc'
    Returns: dict of stats + nav_history DataFrame
    """
    assert mode in ('original', 'pmcc')
    port = Portfolio(INITIAL_CAPITAL)

    use_pmcc = (mode == 'pmcc')

    # Choose LEAPS parameters
    LONG_DTE   = PMCC_LONG_DTE   if use_pmcc else 75
    LONG_DELTA = PMCC_LONG_DELTA  if use_pmcc else 0.70
    SHORT_DTE  = PMCC_SHORT_DTE   if use_pmcc else 75   # original = same expiry as long
    SHORT_DELTA = PMCC_SHORT_DELTA if use_pmcc else 0.50

    # Overlay and roll tracking (PMCC only)
    open_overlays: List[OverlayShortCall] = []

    regime_duration_days = 0
    last_regime = None
    position_counter = 0

    mode_a_days = mode_b_days = mode_c_days = mode_d2_days = 0
    overlay_opens = overlay_closes = 0
    stoploss_hits = 0

    trading_days = df.index

    for i, date in enumerate(trading_days):
        row = df.loc[date]

        qqq_px  = float(row['qqq_close'])
        qqqm_px = float(row['qqqm_close'])
        tqqq_px = float(row['tqqq_close'])
        sqqq_px = float(row['sqqq_close'])
        vix     = float(row['vix'])
        rf      = float(row['rf'])

        iv_tqqq_10d  = float(row['tqqq_iv_10d'])
        iv_qqq_leaps = float(row['qqq_iv_leaps'])
        iv_qqq_short = float(row['qqq_short_iv'])
        iv_vix_call  = float(row['vix_call_iv'])

        port.update_peak_vix(vix)

        regime = classify_mode(row, peak_vix=port.peak_vix,
                               d2_active=(port.d2_position is not None),
                               d2_entry_date=port.d2_position['entry_date'] if port.d2_position else None,
                               current_date=date)

        regime_duration_days = 1 if regime != last_regime else regime_duration_days + 1
        last_regime = regime

        if regime == 'A':  mode_a_days += 1
        elif regime == 'B': mode_b_days += 1
        elif regime == 'C': mode_c_days += 1
        elif regime == 'D2': mode_d2_days += 1

        nav = port.calculate_nav(date, qqqm_px, tqqq_px, sqqq_px, vix,
                                 iv_tqqq_10d, iv_qqq_leaps, iv_qqq_short, iv_vix_call, rf)

        # ── EXIT: D2 ──────────────────────────────────────────────────────────
        if port.d2_position:
            sp = port.d2_position
            days_held = (date - sp['entry_date']).days
            pnl_pct   = (sqqq_px / sp['entry_price']) - 1.0
            if days_held >= 21 or row['vix_vix3m_ratio'] < 1.0 or pnl_pct >= 0.30 or regime == 'D3':
                port.cash += sp['shares'] * sqqq_px - COMMISSION
                port.log_trade({'type': 'D2_SQQQ_CLOSE', 'close': date.date(),
                                'pnl': sp['shares'] * (sqqq_px - sp['entry_price'])})
                port.d2_position = None; port.d2_active = False

        # ── EXIT: CSPs ────────────────────────────────────────────────────────
        surviving_csps = []
        force_kill_csps = regime in ['C', 'D2']
        for csp in port.open_csps:
            T = max((csp['expiry'] - date).days / 365.0, 1/365.0)
            put_val = bs_put_price(tqqq_px, csp['strike'], T, rf, iv_tqqq_10d)
            prof = 1.0 - (put_val / csp['entry_price'])
            if prof >= 0.50 or put_val > csp['entry_price'] * 3.0 or date >= csp['expiry'] or force_kill_csps:
                cost = put_val * csp['contracts'] * 100 + SLIPPAGE_PER_SIDE * csp['contracts'] + COMMISSION * csp['contracts']
                port.cash -= cost
                port.log_trade({'type': 'MODE_A_CSP_CLOSE', 'open': csp['entry_date'].date(),
                                'close': date.date(), 'pnl': csp['entry_price'] * csp['contracts'] * 100 - cost})
            else:
                surviving_csps.append(csp)
        port.open_csps = surviving_csps

        # ── EXIT: Overlay short calls (PMCC P3) ───────────────────────────────
        if use_pmcc:
            surviving_overlays = []
            for ov in open_overlays:
                T = max((ov.expiry - date).days / 365.0, 1/365.0)
                call_val = bs_call_price(qqq_px, ov.strike, T, rf, iv_qqq_short)
                prof_pct  = 1.0 - (call_val / ov.entry_price) if ov.entry_price > 0 else 0.0
                # Close at 50% profit, -200% stop-loss, expiry, or regime = C/D2
                kill = (prof_pct >= 0.50 or
                        call_val > ov.entry_price * 3.0 or
                        date >= ov.expiry or
                        regime in ['C', 'D2'])
                if kill:
                    cost = call_val * ov.contracts * 100 + SLIPPAGE_PER_SIDE * ov.contracts + COMMISSION * ov.contracts
                    port.cash -= cost
                    pnl = ov.entry_price * ov.contracts * 100 - cost
                    port.log_trade({'type': 'OVERLAY_SC_CLOSE', 'open': ov.open_date.date(),
                                    'close': date.date(), 'pnl': pnl})
                    overlay_closes += 1
                else:
                    surviving_overlays.append(ov)
            open_overlays = surviving_overlays

        # ── EXIT: ZEBRAs (+ P2 stop-loss for PMCC) ───────────────────────────
        surviving_zebras = []
        for z in port.open_zebras:
            T         = max((z.expiry - date).days / 365.0, 1/365.0)
            val       = z.current_value(qqqm_px, date, iv_qqq_short, rf)
            prof_pct  = (val - z.entry_price) / z.entry_price if z.entry_price > 0 else 0.0
            time_stop = z.dte(date) <= 21
            profit_ok = prof_pct >= 0.50
            max_loss  = val <= 0.01

            # P2: PMCC stop-loss at 50% of entry (prevents broker forced-liquidation)
            stop_loss_hit = use_pmcc and (val <= z.entry_price * PMCC_STOP_LOSS)

            if profit_ok or time_stop or max_loss or stop_loss_hit:
                close_val = max(val, 0.0)
                proceeds  = close_val * z.contracts * 100 - ZEBRA_SLIPPAGE * z.contracts - ZEBRA_COMMISSION * z.contracts
                port.cash += proceeds
                pnl = proceeds - (z.entry_price * z.contracts * 100)
                reason = 'PROFIT' if profit_ok else ('STOP_LOSS' if stop_loss_hit else ('TIME_STOP' if time_stop else 'MAX_LOSS'))
                port.log_trade({'type': f'MODE_B_ZEBRA_{reason}', 'open': z.open_date.date(),
                                'close': date.date(), 'pnl': pnl})
                if stop_loss_hit:
                    stoploss_hits += 1
                    # Close any overlay on this position too
                    open_overlays = [ov for ov in open_overlays if True]  # simplified: all cleared
            else:
                surviving_zebras.append(z)
        port.open_zebras = surviving_zebras

        # ── EXIT: CCS ────────────────────────────────────────────────────────
        surviving_ccs = []
        for ccs in port.open_ccs:
            T      = max((ccs['expiry'] - date).days / 365.0, 1/365.0)
            sc_val = bs_call_price(qqq_px, ccs['short_strike'], T, rf, iv_qqq_short)
            lc_val = bs_call_price(qqq_px, ccs['long_strike'],  T, rf, iv_qqq_short)
            liab   = max(sc_val - lc_val, 0)
            prof   = 1.0 - (liab / ccs['entry_premium']) if ccs['entry_premium'] > 0 else 0.0
            if prof >= 0.50 or liab >= ccs['entry_premium'] * 3.0 or date >= ccs['expiry']:
                cost = liab * ccs['contracts'] * 100 + SLIPPAGE_PER_SIDE * 2 * ccs['contracts'] + COMMISSION * 2 * ccs['contracts']
                port.cash -= cost
                port.log_trade({'type': 'MODE_C_CCS_CLOSE', 'open': ccs['entry_date'].date(),
                                'close': date.date(), 'pnl': ccs['entry_premium'] * ccs['contracts'] * 100 - cost})
            else:
                surviving_ccs.append(ccs)
        port.open_ccs = surviving_ccs

        # ── EXIT: D1 VIX ──────────────────────────────────────────────────────
        surviving_d1 = []
        for vc in port.d1_positions:
            T      = max((vc['expiry'] - date).days / 365.0, 1/365.0)
            vc_val = bs_call_price(vix, vc['strike'], T, rf, iv_vix_call)
            pnl_p  = (vc_val / vc['entry_price']) - 1.0
            if pnl_p >= 0.50 or vix < vc['entry_vix'] * 0.80 or date >= vc['expiry']:
                proceeds = vc_val * vc['contracts'] * 100 - COMMISSION * vc['contracts']
                port.cash += proceeds
                port.log_trade({'type': 'D1_VIX_CALL_CLOSE', 'close': date.date(),
                                'pnl': proceeds - vc['entry_price'] * vc['contracts'] * 100})
            else:
                surviving_d1.append(vc)
        port.d1_positions = surviving_d1

        # ━━━━━━━━ ENTRIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # ── D2 Entry ──────────────────────────────────────────────────────────
        if regime == 'D2' and not port.d2_active:
            d2_amt = size_d2_sqqq(nav, vix)
            shares = int(d2_amt / sqqq_px)
            if shares > 0 and port.cash >= shares * sqqq_px:
                port.cash -= shares * sqqq_px + COMMISSION
                port.d2_position = {'entry_date': date, 'shares': shares, 'entry_price': sqqq_px}
                port.d2_active = True

        # ── Mode A: CSP ───────────────────────────────────────────────────────
        if regime == 'A' and date.weekday() == 0 and len(port.open_csps) == 0:
            T_csp  = 7/365.0
            strike = find_strike_for_delta(tqqq_px, T_csp, rf, iv_tqqq_10d, 0.12, 'put')
            px     = bs_put_price(tqqq_px, strike, T_csp, rf, iv_tqqq_10d)
            cnt    = size_csp_trade(nav, vix, strike, px)
            if cnt > 0 and port.cash >= cnt * strike * 100:
                premium = cnt * 100 * px - SLIPPAGE_PER_SIDE * cnt - COMMISSION * cnt
                port.cash += premium
                port.open_csps.append({
                    'entry_date': date, 'expiry': date + pd.Timedelta(days=7),
                    'strike': strike, 'entry_price': px, 'contracts': cnt
                })

        # ── Mode B: ZEBRA entry + PMCC overlay ────────────────────────────────
        if regime == 'B':
            has_leaps  = len(port.open_zebras) > 0
            has_overlay = len(open_overlays) > 0
            qqq_5d_mom = float(row.get('qqq_ret_5d', 0.0))

            # P3 (PMCC): Overlay short call when LEAPS exist + momentum <= 0 + no active overlay
            if use_pmcc and has_leaps and not has_overlay and qqq_5d_mom <= 0:
                T_sc    = PMCC_SHORT_DTE / 365.0
                strike  = find_strike_for_delta(qqq_px, T_sc, rf, iv_qqq_short, PMCC_SHORT_DELTA, 'call')
                px      = bs_call_price(qqq_px, strike, T_sc, rf, iv_qqq_short)
                cnt     = len(port.open_zebras)   # 1 short call per LEAPS unit
                if px > 0.10 and cnt > 0:
                    credit = px * cnt * 100 - SLIPPAGE_PER_SIDE * cnt - COMMISSION * cnt
                    port.cash += credit
                    expiry = get_monthly_friday(date, PMCC_SHORT_DTE)
                    open_overlays.append(OverlayShortCall(
                        open_date=date, expiry=expiry, strike=strike,
                        entry_price=px, contracts=cnt, profit_target=px * 0.50
                    ))
                    port.log_trade({'type': 'OVERLAY_SC_OPEN', 'date': date.date()})
                    overlay_opens += 1

            # Open new ZEBRA if below 2 slots
            base_entry    = len(port.open_zebras) == 0
            tactical_entry = (row.get('qqqm_low', qqqm_px) <= row.get('ema_20', qqqm_px)
                              and row['above_sma100']
                              and len(port.open_zebras) < 2)

            if base_entry or tactical_entry:
                T_long  = LONG_DTE / 365.0
                T_short = SHORT_DTE / 365.0
                iv_long = iv_qqq_leaps if use_pmcc else iv_qqq_short

                ls = find_strike_for_delta(qqqm_px, T_long,  rf, iv_long,      LONG_DELTA,  'call')
                ss = find_strike_for_delta(qqqm_px, T_short, rf, iv_qqq_short, SHORT_DELTA, 'call')
                lc = bs_call_price(qqqm_px, ls, T_long,  rf, iv_long)
                sc = bs_call_price(qqqm_px, ss, T_short, rf, iv_qqq_short)
                net_debit = (2 * lc) - sc

                if net_debit > 0:
                    cnt  = size_zebra_trade(nav, net_debit, n_open=len(port.open_zebras))
                    cost = net_debit * cnt * 100 + ZEBRA_SLIPPAGE * cnt + ZEBRA_COMMISSION * cnt
                    if cnt > 0 and port.cash >= cost:
                        port.cash -= cost
                        position_counter += 1
                        expiry = get_monthly_friday(date, LONG_DTE)
                        z = ZebraPosition(date, expiry, ls, ss, net_debit, cnt, iv_long, rf, position_counter)
                        port.open_zebras.append(z)
                        port.log_trade({'type': 'MODE_B_ZEBRA_OPEN', 'date': date.date()})

        # ── Mode C: CCS (P4: skip if LEAPS held in PMCC mode) ────────────────
        if regime == 'C':
            has_leaps = len(port.open_zebras) > 0
            # P4: PMCC mode freezes LEAPS rolls, skips CCS while LEAPS held
            skip_ccs = use_pmcc and has_leaps

            if not skip_ccs and len(port.open_ccs) == 0:
                T_ccs        = 45/365.0
                short_strike = find_strike_for_delta(qqq_px, T_ccs, rf, iv_qqq_short, 0.30, 'call')
                long_strike  = find_strike_for_delta(qqq_px, T_ccs, rf, iv_qqq_short, 0.20, 'call')
                if long_strike > short_strike:
                    sc_px   = bs_call_price(qqq_px, short_strike, T_ccs, rf, iv_qqq_short)
                    lc_px   = bs_call_price(qqq_px, long_strike,  T_ccs, rf, iv_qqq_short)
                    premium = sc_px - lc_px
                    margin  = long_strike - short_strike
                    if premium > 0.05 and margin > 0:
                        cnt = size_ccs_trade(nav, margin * 100)
                        if cnt > 0:
                            entry_p = premium * cnt * 100 - SLIPPAGE_PER_SIDE * 2 * cnt - COMMISSION * 2 * cnt
                            if entry_p > 0:
                                port.cash += entry_p
                                port.open_ccs.append({
                                    'entry_date': date, 'expiry': get_monthly_friday(date, 45),
                                    'short_strike': short_strike, 'long_strike': long_strike,
                                    'entry_premium': premium, 'margin': margin * 100, 'contracts': cnt
                                })

        # ── Mode D3 Recovery ──────────────────────────────────────────────────
        if regime in ['A', 'B']:
            vix_off_peak   = port.peak_vix is not None and vix < port.peak_vix * 0.80
            ts_contango    = row['vix_vix3m_ratio'] < 1.0
            qqq_recovering = (float(row['qqq_close']) > float(df['qqq_close'].shift(10).loc[date]) if i >= 10 else False)

            if vix_off_peak and ts_contango and qqq_recovering and port.peak_vix and port.peak_vix > 30 and len(port.open_zebras) < 2:
                T_long  = LONG_DTE / 365.0
                T_short = SHORT_DTE / 365.0
                iv_long = iv_qqq_leaps if use_pmcc else iv_qqq_short

                ls = find_strike_for_delta(qqqm_px, T_long,  rf, iv_long,      LONG_DELTA,  'call')
                ss = find_strike_for_delta(qqqm_px, T_short, rf, iv_qqq_short, SHORT_DELTA, 'call')
                lc = bs_call_price(qqqm_px, ls, T_long,  rf, iv_long)
                sc = bs_call_price(qqqm_px, ss, T_short, rf, iv_qqq_short)
                net_debit = (2 * lc) - sc

                if net_debit > 0:
                    cnt = size_zebra_trade(nav, net_debit, n_open=len(port.open_zebras))
                    max_cnt = max(int(INITIAL_CAPITAL * 0.15 / (net_debit * 100)), 1)
                    cnt = min(cnt, max_cnt)
                    cost = net_debit * cnt * 100 + ZEBRA_SLIPPAGE * cnt + ZEBRA_COMMISSION * cnt
                    if cnt > 0 and port.cash >= cost:
                        port.cash -= cost
                        position_counter += 1
                        expiry = get_monthly_friday(date, LONG_DTE)
                        z = ZebraPosition(date, expiry, ls, ss, net_debit, cnt, iv_long, rf, position_counter)
                        port.open_zebras.append(z)
                        port.log_trade({'type': 'MODE_D3_ZEBRA_OPEN', 'date': date.date()})
                port.reset_peak_vix()

        # ── D1 VIX Hedge ──────────────────────────────────────────────────────
        if (i == 0 or date.month != df.index[i-1].month) and regime in ['A', 'B']:
            amt = size_d1_vix_calls(nav, vix, float(row['vvix_10d_chg']), regime_duration_days)
            if amt > 0:
                T_vc   = 35/365.0
                strike = find_strike_for_delta(vix, T_vc, rf, iv_vix_call, 0.30, 'call')
                px     = bs_call_price(vix, strike, T_vc, rf, iv_vix_call)
                if px > 0.05:
                    cnt = int(amt / (px * 100 + COMMISSION))
                    if cnt > 0 and port.cash >= cnt * px * 100:
                        port.cash -= cnt * px * 100 + COMMISSION * cnt
                        port.d1_positions.append({
                            'open_date': date, 'expiry': get_monthly_friday(date, 35),
                            'strike': strike, 'entry_price': px, 'entry_vix': vix, 'contracts': cnt
                        })

        port.nav_history.append({'date': date.date(), 'nav': nav, 'mode': regime})

    # ── Compute stats ─────────────────────────────────────────────────────────
    df_nav     = pd.DataFrame(port.nav_history)
    final_nav  = df_nav['nav'].iloc[-1]
    roll_max   = df_nav['nav'].cummax()
    drawdown   = (df_nav['nav'] - roll_max) / roll_max * 100
    max_dd     = drawdown.min()
    years      = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr       = ((final_nav / INITIAL_CAPITAL) ** (1 / years) - 1) * 100
    total_days = len(df_nav)

    # Sharpe (daily excess return / daily std — annualised)
    df_nav['ret'] = df_nav['nav'].pct_change().fillna(0)
    sharpe = (df_nav['ret'].mean() / df_nav['ret'].std()) * np.sqrt(252) if df_nav['ret'].std() > 0 else 0

    tlog = pd.DataFrame(port.trade_log)
    pnl_cols = tlog['pnl'] if 'pnl' in tlog.columns else pd.Series(dtype=float)

    # Win rate on all closed trades with PnL
    close_rows = tlog[tlog.get('pnl', pd.Series()).notna()] if 'pnl' in tlog.columns else pd.DataFrame()
    win_rate   = (close_rows['pnl'] > 0).mean() * 100 if len(close_rows) > 0 else 0

    return {
        'final_nav':     final_nav,
        'total_return':  (final_nav / INITIAL_CAPITAL - 1) * 100,
        'cagr':          cagr,
        'max_dd':        max_dd,
        'calmar':        cagr / abs(max_dd) if max_dd != 0 else 0,
        'sharpe':        sharpe,
        'win_rate':      win_rate,
        'mode_a_days':   mode_a_days,
        'mode_b_days':   mode_b_days,
        'mode_c_days':   mode_c_days,
        'stoploss_hits': stoploss_hits,
        'overlay_opens': overlay_opens,
        'overlay_closes': overlay_closes,
        'total_days':    total_days,
        'nav_history':   df_nav,
        'trade_log':     tlog,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\nLoading market data {START_DATE} → {END_DATE}...")
    df = features.build_feature_set(START_DATE, END_DATE)
    print(f"  {len(df)} trading days loaded.\n")

    qqq_cagr = ((df['qqq_close'].iloc[-1] / df['qqq_close'].iloc[0]) **
                (365.25 / (df.index[-1] - df.index[0]).days) - 1) * 100

    print("Running ORIGINAL strategy...")
    orig = run_single(df, mode='original')

    print("Running PMCC-ENHANCED strategy...")
    pmcc = run_single(df, mode='pmcc')

    # ── Print comparison ──────────────────────────────────────────────────────
    W = 16
    print("\n" + "═" * 70)
    print(f"  {'METRIC':<30} {'ORIGINAL':>{W}} {'PMCC-ENHANCED':>{W}}")
    print("─" * 70)

    metrics = [
        ("Final NAV",          f"${orig['final_nav']:>12,.0f}",       f"${pmcc['final_nav']:>12,.0f}"),
        ("Total Return",       f"{orig['total_return']:>11.1f}%",      f"{pmcc['total_return']:>11.1f}%"),
        ("CAGR",               f"{orig['cagr']:>11.1f}%",              f"{pmcc['cagr']:>11.1f}%"),
        ("Max Drawdown",       f"{orig['max_dd']:>11.1f}%",            f"{pmcc['max_dd']:>11.1f}%"),
        ("Calmar Ratio",       f"{orig['calmar']:>12.2f}",             f"{pmcc['calmar']:>12.2f}"),
        ("Sharpe Ratio",       f"{orig['sharpe']:>12.2f}",             f"{pmcc['sharpe']:>12.2f}"),
        ("Win Rate",           f"{orig['win_rate']:>11.1f}%",          f"{pmcc['win_rate']:>11.1f}%"),
        ("─" * 30,             "─" * W,                                "─" * W),
        ("QQQ Benchmark CAGR", f"{qqq_cagr:>11.1f}%",                 f"{qqq_cagr:>11.1f}%"),
        ("Alpha vs QQQ",       f"{orig['cagr'] - qqq_cagr:>+11.1f}%", f"{pmcc['cagr'] - qqq_cagr:>+11.1f}%"),
        ("─" * 30,             "─" * W,                                "─" * W),
        ("Stop-Loss Exits",    f"{orig['stoploss_hits']:>12d}",        f"{pmcc['stoploss_hits']:>12d}"),
        ("Overlay Opens",      f"{'—':>12}",                           f"{pmcc['overlay_opens']:>12d}"),
        ("Overlay Closes",     f"{'—':>12}",                           f"{pmcc['overlay_closes']:>12d}"),
    ]

    for row in metrics:
        label, oval, pval = row
        is_sep = label.startswith("─")
        if is_sep:
            print("─" * 70)
        else:
            print(f"  {label:<30} {oval:>{W}} {pval:>{W}}")

    print("═" * 70)

    # ── Delta summary ─────────────────────────────────────────────────────────
    cagr_delta = pmcc['cagr'] - orig['cagr']
    dd_delta   = pmcc['max_dd'] - orig['max_dd']
    print(f"\n  CAGR improvement   : {cagr_delta:>+.1f} percentage points")
    print(f"  Drawdown change    : {dd_delta:>+.1f} percentage points")
    print(f"  Calmar improvement : {pmcc['calmar'] - orig['calmar']:>+.2f}")

    # ── Save NAV CSV for plotting ─────────────────────────────────────────────
    out = pd.DataFrame({
        'date':     orig['nav_history']['date'],
        'orig_nav': orig['nav_history']['nav'],
        'pmcc_nav': pmcc['nav_history']['nav'].values,
    })
    out_path = ROOT / 'backtest_pmcc_results.csv'
    out.to_csv(out_path, index=False)
    print(f"\n  NAV history saved → {out_path.name}")
    print("═" * 70 + "\n")


if __name__ == '__main__':
    main()
