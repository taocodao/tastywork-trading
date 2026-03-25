import sys

with open('d:/Projects/tastywork-trading-1/iv-switching-composite/backtest_composite.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if "        # ── 4. PMCC MANAGEMENT ──" in line:
        skip = True
        new_lines.append("""        # ── 4. PMCC / COLLAR MANAGEMENT ──
        for pos in port.open_leaps:
            if pos.short_call:
                sc = pos.short_call
                T_sc = max((sc['expiry'] - date).days / 365.0, 1/365.0)
                sc_val = bs_call_price(qqqm_px, sc['strike'], T_sc, rf, iv_qqq_short)
                profit_pct = 1.0 - (sc_val / sc['entry_price'])
                dist_pct = (sc['strike'] - qqqm_px) / qqqm_px
                force_close = dist_pct <= 0.03
                
                if profit_pct >= 0.50 or force_close or T_sc <= 1/365.0:
                    cost = sc_val * sc['contracts'] * 100 + COMMISSION * sc['contracts']
                    port.cash -= cost
                    inc = sc['premium'] - cost
                    pos.pmcc_income += max(inc, 0)
                    pos.short_call = None
                    port.log_trade({'type': 'PMCC_CLOSE', 'date': date.date(), 'pnl': inc})
            elif pos.dte(date) > 60 and mode != 'C': # open cc (Gear 1 only, Mode C uses Collars)
                target_delta = 0.20
                
                T_pmcc = 35/365.0
                sc_strike = find_strike_for_delta(qqqm_px, T_pmcc, rf, iv_qqq_short, target_delta, 'call')
                sc_strike = max(sc_strike, pos.strike * 1.01)
                sc_px = bs_call_price(qqqm_px, sc_strike, T_pmcc, rf, iv_qqq_short)
                sc_px = max(sc_px, 0.01)
                premium = sc_px * pos.contracts * 100 - SLIPPAGE_PER_SIDE * pos.contracts - COMMISSION * pos.contracts
                port.cash += premium
                pos.short_call = {
                    'expiry': get_monthly_friday(date, 35),
                    'strike': sc_strike,
                    'entry_price': sc_px,
                    'premium': premium,
                    'contracts': pos.contracts
                }
                
        # ── 4.5. MODE C DELTA NEUTRALIZER (COLLAR ENTRY) ──
        if mode == 'C':
            for pos in port.open_leaps:
                if pos.long_put is None:
                    # Buy 90-DTE QQQM Put with matching delta
                    T_leaps = max((pos.expiry - date).days / 365.0, 1/365.0)
                    leaps_delta = bs_call_delta(qqqm_px, pos.strike, T_leaps, rf, iv_qqq_leaps)
                    
                    T_put = 90/365.0
                    lp_strike = find_strike_for_delta(qqqm_px, T_put, rf, iv_qqq_short, leaps_delta, 'put')
                    lp_px = bs_put_price(qqqm_px, lp_strike, T_put, rf, iv_qqq_short)
                    
                    cost = lp_px * pos.contracts * 100 + SLIPPAGE_PER_SIDE * pos.contracts + COMMISSION * pos.contracts
                    port.cash -= cost
                    
                    pos.long_put = {
                        'expiry': get_monthly_friday(date, 90),
                        'strike': lp_strike,
                        'entry_price': lp_px,
                        'contracts': pos.contracts
                    }
                    port.log_trade({'type': 'MODE_C_HEDGE_OPEN', 'date': date.date()})
                
                if pos.short_call is None:
                    # Sell 30-DTE 30-delta collar call to finance
                    T_sc = 30/365.0
                    sc_strike = find_strike_for_delta(qqqm_px, T_sc, rf, iv_qqq_short, 0.30, 'call')
                    sc_strike = max(sc_strike, pos.strike * 1.01)
                    sc_px = bs_call_price(qqqm_px, sc_strike, T_sc, rf, iv_qqq_short)
                    sc_px = max(sc_px, 0.01)
                    
                    premium = sc_px * pos.contracts * 100 - SLIPPAGE_PER_SIDE * pos.contracts - COMMISSION * pos.contracts
                    port.cash += premium
                    pos.short_call = {
                        'expiry': get_monthly_friday(date, 30),
                        'strike': sc_strike,
                        'entry_price': sc_px,
                        'premium': premium,
                        'contracts': pos.contracts
                    }
                    port.log_trade({'type': 'MODE_C_COLLAR_OPEN', 'date': date.date()})
""")
    elif "        # ── 5. D1 VIX HEDGE MANAGEMENT ──" in line:
        skip = False

    if not skip:
        new_lines.append(line)

with open('d:/Projects/tastywork-trading-1/iv-switching-composite/backtest_composite.py', 'w', encoding='utf-8') as f:
    f.write("".join(new_lines))
