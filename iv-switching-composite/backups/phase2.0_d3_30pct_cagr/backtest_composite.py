import sys, os, logging
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import data.features as features
from regime_engine import classify_mode, should_open_d1
from position_sizer import size_csp_trade, size_zebra_trade, size_ccs_trade, size_d2_sqqq, size_d1_vix_calls
from pricing import bs_call_price, bs_put_price, find_strike_for_delta, bs_call_delta, SLIPPAGE_PER_SIDE, COMMISSION
from portfolio import Portfolio, ZebraPosition

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("IV_Composite")

# Config
START_DATE      = "2019-01-01"
END_DATE        = "2026-03-20"
INITIAL_CAPITAL = 25000.0

# Leg slippage per ZEBRA unit = 3 legs x 2 sides = 6 half-spreads
ZEBRA_SLIPPAGE = SLIPPAGE_PER_SIDE * 3
ZEBRA_COMMISSION = COMMISSION * 3

def get_monthly_friday(date, offset_days=35):
    target = date + pd.Timedelta(days=offset_days)
    weekday = target.weekday()
    if weekday < 4:
        target += pd.Timedelta(days=4 - weekday)
    elif weekday > 4:
        target += pd.Timedelta(days=7 - weekday + 4)
    return target

def run_backtest():
    df = features.build_feature_set(START_DATE, END_DATE)
    port = Portfolio(INITIAL_CAPITAL)

    regime_duration_days = 0
    last_regime = None
    position_counter = 0

    mode_a_days  = 0
    mode_b_days  = 0
    mode_c_days  = 0
    mode_d2_days = 0

    log.info("Starting Phase 2.0 ZEBRA simulation...")

    trading_days = df.index
    for i, date in enumerate(trading_days):
        row = df.loc[date]

        # Current prices
        qqq_px   = float(row['qqq_close'])
        qqqm_px  = float(row['qqqm_close'])
        tqqq_px  = float(row['tqqq_close'])
        sqqq_px  = float(row['sqqq_close'])
        vix      = float(row['vix'])
        rf       = float(row['rf'])

        iv_tqqq_10d  = float(row['tqqq_iv_10d'])
        iv_qqq_leaps = float(row['qqq_iv_leaps'])   # used for ZEBRA IV (same term structure ref)
        iv_qqq_short = float(row['qqq_short_iv'])
        iv_vix_call  = float(row['vix_call_iv'])

        port.update_peak_vix(vix)

        # ── Mode Classification ──
        mode = classify_mode(row, peak_vix=port.peak_vix, d2_active=(port.d2_position is not None),
                             d2_entry_date=port.d2_position['entry_date'] if port.d2_position else None,
                             current_date=date)

        if mode == last_regime:
            regime_duration_days += 1
        else:
            regime_duration_days = 1
            last_regime = mode

        if mode == 'A': mode_a_days += 1
        elif mode == 'B': mode_b_days += 1
        elif mode == 'C': mode_c_days += 1
        elif mode == 'D2': mode_d2_days += 1

        # NAV (uses qqqm_px for ZEBRA valuation)
        nav = port.calculate_nav(date, qqqm_px, tqqq_px, sqqq_px, vix,
                                 iv_tqqq_10d, iv_qqq_leaps, iv_qqq_short, iv_vix_call, rf)

        # ── 1. D2 EXITS ──
        if port.d2_position:
            sqqq_pos = port.d2_position
            days_held = (date - sqqq_pos['entry_date']).days
            pnl_pct = (sqqq_px / sqqq_pos['entry_price']) - 1.0

            if days_held >= 21 or row['vix_vix3m_ratio'] < 1.0 or pnl_pct >= 0.30 or mode == 'D3':
                val = sqqq_pos['shares'] * sqqq_px
                port.cash += val - COMMISSION
                port.log_trade({
                    'type': 'D2_SQQQ_CLOSE', 'close': date.date(),
                    'pnl': val - (sqqq_pos['shares'] * sqqq_pos['entry_price'])
                })
                port.d2_position = None
                port.d2_active = False

        # ── 2. CSP (MODE A) EXITS ──
        surviving_csps = []
        force_close_csps = mode in ['C', 'D2']
        for csp in port.open_csps:
            T = max((csp['expiry'] - date).days / 365.0, 1/365.0)
            put_val = bs_put_price(tqqq_px, csp['strike'], T, rf, iv_tqqq_10d)
            profit_pct = 1.0 - (put_val / csp['entry_price'])

            if profit_pct >= 0.50 or put_val > csp['entry_price'] * 3.0 or date >= csp['expiry'] or force_close_csps:
                cost = put_val * csp['contracts'] * 100 + SLIPPAGE_PER_SIDE * csp['contracts'] + COMMISSION * csp['contracts']
                port.cash -= cost
                pnl  = (csp['entry_price'] * csp['contracts'] * 100) - cost
                port.log_trade({
                    'type': 'MODE_A_CSP_CLOSE', 'open': csp['entry_date'].date(),
                    'close': date.date(), 'pnl': pnl,
                    'reason': 'kill' if force_close_csps else 'normal'
                })
            else:
                surviving_csps.append(csp)
        port.open_csps = surviving_csps

        # ── 3. ZEBRA (MODE B) EXITS ──
        surviving_zebras = []
        for z in port.open_zebras:
            T = max((z.expiry - date).days / 365.0, 1/365.0)
            val = z.current_value(qqqm_px, date, iv_qqq_short, rf)

            profit_pct = (val - z.entry_price) / z.entry_price if z.entry_price > 0 else 0.0

            # Exit conditions: 50% profit OR time-stop at 21 DTE OR max-loss floor (val approaches 0)
            time_stop = z.dte(date) <= 21
            profit_hit = profit_pct >= 0.50
            max_loss   = val <= 0.01  # Fully burnt ZEBRA

            if profit_hit or time_stop or max_loss:
                close_val = max(val, 0.0)
                proceeds  = close_val * z.contracts * 100 - ZEBRA_SLIPPAGE * z.contracts - ZEBRA_COMMISSION * z.contracts
                port.cash += proceeds
                pnl = proceeds - (z.entry_price * z.contracts * 100)
                close_type = 'PROFIT' if profit_hit else ('TIME_STOP' if time_stop else 'MAX_LOSS')
                port.log_trade({
                    'type': f'MODE_B_ZEBRA_{close_type}', 'open': z.open_date.date(),
                    'close': date.date(), 'pnl': pnl
                })
            else:
                surviving_zebras.append(z)
        port.open_zebras = surviving_zebras

        # ── 4. MODE C BEAR CALL SPREAD EXITS ──
        surviving_ccs = []
        for ccs in port.open_ccs:
            T = max((ccs['expiry'] - date).days / 365.0, 1/365.0)
            sc_val = bs_call_price(qqq_px, ccs['short_strike'], T, rf, iv_qqq_short)
            lc_val = bs_call_price(qqq_px, ccs['long_strike'],  T, rf, iv_qqq_short)
            liability  = max(sc_val - lc_val, 0)
            profit_pct = 1.0 - (liability / ccs['entry_premium']) if ccs['entry_premium'] > 0 else 0.0

            # Close at 50% profit, -200% stop-loss, or expiry
            if profit_pct >= 0.50 or liability >= ccs['entry_premium'] * 3.0 or date >= ccs['expiry']:
                cost = liability * ccs['contracts'] * 100 + SLIPPAGE_PER_SIDE * 2 * ccs['contracts'] + COMMISSION * 2 * ccs['contracts']
                port.cash -= cost
                pnl = (ccs['entry_premium'] * ccs['contracts'] * 100) - cost
                port.log_trade({'type': 'MODE_C_CCS_CLOSE', 'open': ccs['entry_date'].date(), 'close': date.date(), 'pnl': pnl})
            else:
                surviving_ccs.append(ccs)
        port.open_ccs = surviving_ccs

        # ── 5. D1 VIX HEDGE EXITS ──
        surviving_d1 = []
        for vc in port.d1_positions:
            T = max((vc['expiry'] - date).days / 365.0, 1/365.0)
            vc_val = bs_call_price(vix, vc['strike'], T, rf, iv_vix_call)
            pnl_pct = (vc_val / vc['entry_price']) - 1.0

            if pnl_pct >= 0.50 or vix < vc['entry_vix'] * 0.80 or date >= vc['expiry']:
                proceeds = vc_val * vc['contracts'] * 100 - COMMISSION * vc['contracts']
                port.cash += proceeds
                pnl = proceeds - (vc['entry_price'] * vc['contracts'] * 100)
                port.log_trade({'type': 'D1_VIX_CALL_CLOSE', 'close': date.date(), 'pnl': pnl})
            else:
                surviving_d1.append(vc)
        port.d1_positions = surviving_d1

        # ━━━━━━━ ENTRIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # ── D2 Entry ──
        if mode == 'D2' and not port.d2_active:
            d2_amt = size_d2_sqqq(nav, vix)
            shares = int(d2_amt / sqqq_px)
            if shares > 0 and port.cash >= shares * sqqq_px:
                cost = shares * sqqq_px + COMMISSION
                port.cash -= cost
                port.d2_position = {'entry_date': date, 'shares': shares, 'entry_price': sqqq_px}
                port.d2_active = True
                port.log_trade({'type': 'D2_SQQQ_OPEN', 'date': date.date()})

        # ── Mode A: CSP Entry (weekly, Monday) ──
        if mode == 'A' and date.weekday() == 0 and len(port.open_csps) == 0:
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
                port.log_trade({'type': 'MODE_A_CSP_OPEN', 'date': date.date()})

        # ── Mode B: ZEBRA Entry ──
        if mode == 'B':
            base_entry     = len(port.open_zebras) == 0
            tactical_entry = (row.get('qqqm_low', qqqm_px) <= row.get('ema_20', qqqm_px)
                              and row['above_sma100']
                              and len(port.open_zebras) < 2)

            if base_entry or tactical_entry:
                T_z          = 75/365.0   # 75 DTE target
                long_strike  = find_strike_for_delta(qqqm_px, T_z, rf, iv_qqq_short, 0.70, 'call')
                short_strike = find_strike_for_delta(qqqm_px, T_z, rf, iv_qqq_short, 0.50, 'call')
                lc_px        = bs_call_price(qqqm_px, long_strike,  T_z, rf, iv_qqq_short)
                sc_px        = bs_call_price(qqqm_px, short_strike, T_z, rf, iv_qqq_short)
                net_debit    = (2 * lc_px) - sc_px   # per unit cost

                if net_debit > 0:
                    cnt = size_zebra_trade(nav, net_debit, n_open=len(port.open_zebras))
                    cost = net_debit * cnt * 100 + ZEBRA_SLIPPAGE * cnt + ZEBRA_COMMISSION * cnt
                    if cnt > 0 and port.cash >= cost:
                        port.cash -= cost
                        position_counter += 1
                        expiry = get_monthly_friday(date, 75)
                        z = ZebraPosition(date, expiry, long_strike, short_strike,
                                          net_debit, cnt, iv_qqq_short, rf, position_counter)
                        port.open_zebras.append(z)
                        port.log_trade({'type': 'MODE_B_ZEBRA_OPEN', 'date': date.date()})

        # ── Mode C: Bear Call Spread Income ──
        if mode == 'C' and len(port.open_ccs) == 0:
            T_ccs       = 45/365.0
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
                        entry_premium = premium * cnt * 100 - SLIPPAGE_PER_SIDE * 2 * cnt - COMMISSION * 2 * cnt
                        if entry_premium > 0:
                            port.cash += entry_premium
                            port.open_ccs.append({
                                'entry_date': date, 'expiry': get_monthly_friday(date, 45),
                                'short_strike': short_strike, 'long_strike': long_strike,
                                'entry_premium': premium, 'margin': margin * 100, 'contracts': cnt
                            })
                            port.log_trade({'type': 'MODE_C_CCS_OPEN', 'date': date.date()})

        # ── MODE D3: Crash Recovery Aggressive Re-Entry ──
        # Trigger: VIX 20%+ off peak AND term structure back to contango AND QQQ turning positive
        if mode in ['A', 'B']:
            vix_off_peak  = port.peak_vix is not None and vix < port.peak_vix * 0.80
            ts_contango   = row['vix_vix3m_ratio'] < 1.0
            qqq_recovering = float(row.get('qqq_close', qqq_px)) > float(df['qqq_close'].shift(10).loc[date] if i >= 10 else qqq_px)

            d3_active = vix_off_peak and ts_contango and qqq_recovering

            if d3_active and port.peak_vix and port.peak_vix > 30 and len(port.open_zebras) < 2:
                # Aggressive double entry: open up to 2 ZEBRA units back-to-back
                T_z          = 75/365.0
                long_strike  = find_strike_for_delta(qqqm_px, T_z, rf, iv_qqq_short, 0.70, 'call')
                short_strike = find_strike_for_delta(qqqm_px, T_z, rf, iv_qqq_short, 0.50, 'call')
                lc_px        = bs_call_price(qqqm_px, long_strike,  T_z, rf, iv_qqq_short)
                sc_px        = bs_call_price(qqqm_px, short_strike, T_z, rf, iv_qqq_short)
                net_debit    = (2 * lc_px) - sc_px

                if net_debit > 0:
                    # D3: allow up to 20% NAV per slot (extra aggressive)
                    max_outlay = nav * 0.20
                    cnt = max(int(max_outlay / (net_debit * 100)), 0)
                    while len(port.open_zebras) < 2 and cnt > 0:
                        cost = net_debit * cnt * 100 + ZEBRA_SLIPPAGE * cnt + ZEBRA_COMMISSION * cnt
                        if port.cash >= cost:
                            port.cash -= cost
                            position_counter += 1
                            expiry = get_monthly_friday(date, 75)
                            z = ZebraPosition(date, expiry, long_strike, short_strike,
                                              net_debit, cnt, iv_qqq_short, rf, position_counter)
                            port.open_zebras.append(z)
                            port.log_trade({'type': 'MODE_D3_ZEBRA_OPEN', 'date': date.date()})
                        break  # one shot per day
                port.reset_peak_vix()

        # ── D1 VIX Hedge (first business day of month) ──
        if (i == 0 or date.month != df.index[i-1].month) and mode in ['A', 'B']:
            amt = size_d1_vix_calls(nav, vix, float(row['vvix_10d_chg']), regime_duration_days)
            if amt > 0:
                T_vc    = 35/365.0
                strike  = find_strike_for_delta(vix, T_vc, rf, iv_vix_call, 0.30, 'call')
                px      = bs_call_price(vix, strike, T_vc, rf, iv_vix_call)
                if px > 0.05:
                    cnt = int(amt / (px * 100 + COMMISSION))
                    if cnt > 0 and port.cash >= cnt * px * 100:
                        cost = cnt * px * 100 + COMMISSION * cnt
                        port.cash -= cost
                        port.d1_positions.append({
                            'open_date': date, 'expiry': get_monthly_friday(date, 35),
                            'strike': strike, 'entry_price': px, 'entry_vix': vix, 'contracts': cnt
                        })

        port.nav_history.append({'date': date.date(), 'nav': nav, 'mode': mode})

        if i % 250 == 0 or i == len(trading_days) - 1:
            log.info("  %s | NAV=$%.0f | Mode=%s | Ret=%.1f%%",
                     date.date(), nav, mode, (nav / INITIAL_CAPITAL - 1) * 100)

    # ── Output Stats ──
    df_nav   = pd.DataFrame(port.nav_history)
    final_nav = df_nav['nav'].iloc[-1]
    roll_max  = df_nav['nav'].cummax()
    drawdown  = (df_nav['nav'] - roll_max) / roll_max * 100
    max_dd    = drawdown.min()
    years     = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr      = ((final_nav / INITIAL_CAPITAL) ** (1 / years) - 1) * 100

    qqq_benchmark = (df['qqq_close'].iloc[-1] / df['qqq_close'].iloc[0]) ** (1 / years) - 1
    total_days    = len(trading_days)

    print("\n" + "=" * 65)
    print("  COMPOSITE STRATEGY — PHASE 2.0 (ZEBRA Architecture)")
    print("=" * 65)
    print(f"  Period: {START_DATE} to {END_DATE} ({years:.1f} years)")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:>10,.2f}")
    print(f"\nPORTFOLIO PERFORMANCE:")
    print(f"  Final NAV          : ${final_nav:>10,.2f}")
    print(f"  Total Return       : {(final_nav/INITIAL_CAPITAL-1)*100:>10.1f}%")
    print(f"  CAGR (portfolio)   : {cagr:>10.1f}%")
    print(f"  Max Drawdown       : {max_dd:>10.1f}%")
    print(f"  Calmar Ratio       : {cagr / abs(max_dd) if max_dd != 0 else 0:>10.2f}")
    print(f"\nBENCHMARK (QQQ):")
    print(f"  QQQ CAGR           : {qqq_benchmark*100:>10.1f}%")
    print(f"  Alpha              : {cagr - qqq_benchmark*100:>+10.1f} pp")
    print("\nMODE ATTRIBUTION:")
    print(f"  Mode A (CSP) active days  : {mode_a_days:>4d} ({mode_a_days/total_days*100:.1f}%)")
    print(f"  Mode B (ZEBRA) active days: {mode_b_days:>4d} ({mode_b_days/total_days*100:.1f}%)")
    print(f"  Mode C (CCS) active days  : {mode_c_days:>4d} ({mode_c_days/total_days*100:.1f}%)")
    print(f"  Mode D2 (Bear) active days: {mode_d2_days:>4d} ({mode_d2_days/total_days*100:.1f}%)")

    tlog = pd.DataFrame(port.trade_log)
    if 'type' in tlog.columns and 'pnl' in tlog.columns:
        csp_t  = tlog[tlog['type'] == 'MODE_A_CSP_CLOSE']
        csp_w  = csp_t[csp_t['pnl'] > 0]
        print(f"\nMODE A (CSP) STATS:")
        print(f"  Total CSPs closed : {len(csp_t)}")
        if len(csp_t): print(f"  Win rate          : {len(csp_w)/len(csp_t)*100:.1f}%")

        zeb_t  = tlog[tlog['type'].str.startswith('MODE_B_ZEBRA')]
        zeb_pr = tlog[tlog['type'] == 'MODE_B_ZEBRA_PROFIT']
        zeb_ts = tlog[tlog['type'] == 'MODE_B_ZEBRA_TIME_STOP']
        print(f"\nMODE B (ZEBRA) STATS:")
        print(f"  Total ZEBRAs closed: {len(zeb_t)}")
        print(f"  Profit exits       : {len(zeb_pr)}")
        print(f"  Time-stop exits    : {len(zeb_ts)}")

        ccs_t  = tlog[tlog['type'] == 'MODE_C_CCS_CLOSE']
        ccs_w  = ccs_t[ccs_t['pnl'] > 0]
        if len(ccs_t):
            print(f"\nMODE C (BEAR CALL SPREADS) STATS:")
            print(f"  Total CCS closed  : {len(ccs_t)}")
            print(f"  Win rate          : {len(ccs_w)/len(ccs_t)*100:.1f}%")

        print("\nTOP 10 WORST LOSING TRADES:")
        worst = tlog.sort_values('pnl').head(10)
        for _, t in worst.iterrows():
            close_dt = t['close'].strftime('%Y-%m-%d') if hasattr(t['close'], 'strftime') else str(t['close'])
            print(f"  {close_dt} | {t['type']:<28} | PnL: ${t['pnl']:<8.2f}")

    print("=" * 65)

if __name__ == "__main__":
    run_backtest()
