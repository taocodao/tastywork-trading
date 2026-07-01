#!/usr/bin/env python3
"""
Live TastyTrade Position Checker
=================================
Connects to the live account (x5WI28023) and diagnoses every open position
against the 5 known risk categories:

  1. SHORT EQUITY  — net-short QQQ/QLD/TQQQ (uncapped upside risk at ATH)
  2. ORPHANED LEGS — option leg with no paired counterpart (spread broken)
  3. EXPIRY DANGER — option spread expiring within 14 calendar days (assignment risk)
  4. ITM SPREADS   — call spread with short leg deep in the money (>5% ITM)
  5. OPEN SQQQ     — long SQQQ while regime is not bear (time/profit stop check)

Outputs a prioritized action table.
"""

import os, sys, math, logging
from datetime import date, datetime
from collections import defaultdict
from dotenv import load_dotenv

# ── Load env ─────────────────────────────────────────────────────────────────
load_dotenv(r"D:\Projects\tastywork-trading-1\.env")
sys.path.insert(0, r"D:\Projects\tastywork-trading-1")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# ── Connect to TastyTrade ─────────────────────────────────────────────────────
print("=" * 70)
print("CONNECTING TO TASTYTRADE...")
print("=" * 70)

from tastytrade_utils import create_user_session, get_user_account

REFRESH_TOKEN  = os.getenv("TASTYTRADE_REFRESH_TOKEN")
ACCOUNT_NUMBER = "x5WI28023"

session = create_user_session(REFRESH_TOKEN)
account = get_user_account(session, ACCOUNT_NUMBER)
print(f"Connected: {account.account_number}")

# ── Fetch live data ───────────────────────────────────────────────────────────
balances  = account.get_balances(session)
positions = account.get_positions(session)

nlv          = float(getattr(balances, 'net_liquidating_value', 0) or 0)
cash         = float(getattr(balances, 'cash_balance', 0) or 0)
buying_power = float(getattr(balances, 'derivative_buying_power', 0) or 0)

print(f"\nAccount NLV:    ${nlv:>12,.2f}")
print(f"Cash Balance:   ${cash:>12,.2f}")
print(f"Buying Power:   ${buying_power:>12,.2f}")

# ── Get live QQQ price for ITM checks ────────────────────────────────────────
try:
    import yfinance as yf
    qqq_px = float(yf.Ticker("QQQ").fast_info.last_price)
    qld_px = float(yf.Ticker("QLD").fast_info.last_price)
    tqqq_px = float(yf.Ticker("TQQQ").fast_info.last_price)
    sqqq_px = float(yf.Ticker("SQQQ").fast_info.last_price)
    vix_px  = float(yf.Ticker("^VIX").fast_info.last_price)
    print(f"\nLive Prices: QQQ=${qqq_px:.2f}  QLD=${qld_px:.2f}  TQQQ=${tqqq_px:.2f}  SQQQ=${sqqq_px:.2f}  VIX={vix_px:.1f}")
except Exception as e:
    print(f"WARNING: Could not fetch live prices: {e}")
    qqq_px = qld_px = tqqq_px = sqqq_px = 0.0
    vix_px = 20.0

today = date.today()

# ── Parse all positions ───────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("ALL OPEN POSITIONS")
print(f"{'='*70}")

equity_positions = []
option_positions = []

for pos in positions:
    sym     = getattr(pos, 'symbol', '') or ''
    und     = getattr(pos, 'underlying_symbol', '') or ''
    qty     = float(getattr(pos, 'quantity', 0) or 0)
    itype   = getattr(pos, 'instrument_type', '') or ''
    opt_type= getattr(pos, 'option_type', '') or ''
    avg_px  = float(getattr(pos, 'average_open_price', 0) or 0)
    close_px= float(getattr(pos, 'close_price', 0) or 0)
    mtm     = float(getattr(pos, 'multiplier', 100) or 100)

    if itype in ('Equity', '') and 'Option' not in itype:
        equity_positions.append({
            'symbol': sym, 'qty': qty, 'avg_px': avg_px,
            'close_px': close_px, 'itype': itype,
        })
        direction = "LONG" if qty > 0 else "SHORT"
        print(f"  EQUITY  {sym:<8}  qty={qty:>+8.2f}  avg=${avg_px:>8.2f}  close=${close_px:>8.2f}  [{direction}]")
    elif 'Option' in itype or itype == 'Equity Option':
        # Parse OCC symbol
        expiry_str = sym[6:12] if len(sym) >= 15 else ''
        try:
            exp_y = 2000 + int(expiry_str[:2])
            exp_m = int(expiry_str[2:4])
            exp_d = int(expiry_str[4:6])
            exp_date = date(exp_y, exp_m, exp_d)
            dte = (exp_date - today).days
        except Exception:
            exp_date = None
            dte = 999
        try:
            strike = int(sym[13:]) / 1000.0
        except Exception:
            strike = 0.0

        option_positions.append({
            'symbol': sym, 'underlying': und, 'qty': qty,
            'opt_type': opt_type, 'strike': strike,
            'expiry_str': expiry_str, 'exp_date': exp_date, 'dte': dte,
            'avg_px': avg_px, 'close_px': close_px,
        })
        direction = f"{'LONG' if qty > 0 else 'SHORT'}"
        itm_flag = ""
        if und == 'QQQ' and qqq_px > 0 and opt_type in ('C','CALL') and strike < qqq_px:
            pct_itm = (qqq_px - strike) / strike * 100
            itm_flag = f"  <<< {pct_itm:.1f}% ITM"
        expiry_flag = ""
        if dte <= 14:
            expiry_flag = f"  *** DTE={dte} DANGER ***"
        elif dte <= 30:
            expiry_flag = f"  ! DTE={dte}"
        print(f"  OPTION  {sym.strip():<40}  qty={qty:>+5.0f}  strike=${strike:>7.2f}  exp={expiry_str}  DTE={dte:>3d}  [{direction}]{itm_flag}{expiry_flag}")

# ── ISSUE 1: Short Equity Positions ─────────────────────────────────────────
print(f"\n{'='*70}")
print("ISSUE #1: SHORT EQUITY POSITIONS (Uncapped Risk)")
print(f"{'='*70}")

short_equity = [p for p in equity_positions if p['qty'] < 0 and p['symbol'] in ('QQQ','QLD','TQQQ','SQQQ','QQQM')]
if not short_equity:
    print("  CLEAR — No short equity positions found.")
else:
    for p in short_equity:
        sym = p['symbol']
        qty = p['qty']
        live_px = {'QQQ': qqq_px, 'QLD': qld_px, 'TQQQ': tqqq_px, 'QQQM': qqq_px}.get(sym, 0)
        unrealized = (p['avg_px'] - live_px) * abs(qty) if live_px > 0 else 0
        print(f"  CRITICAL: SHORT {abs(qty):.0f} shares of {sym}  avg=${p['avg_px']:.2f}  live=${live_px:.2f}  Unrealized={'LOSS' if unrealized < 0 else 'GAIN'} ${unrealized:+,.2f}")
        print(f"  ACTION: BUY TO CLOSE {abs(qty):.0f} {sym} immediately")

# ── ISSUE 2: Orphaned Option Legs ────────────────────────────────────────────
print(f"\n{'='*70}")
print("ISSUE #2: ORPHANED OPTION LEGS (No Paired Counterpart)")
print(f"{'='*70}")

# Group QQQ calls by expiry → separate shorts and longs
qqq_call_shorts = defaultdict(list)
qqq_call_longs  = defaultdict(list)
for p in option_positions:
    if p['underlying'] == 'QQQ' and p['opt_type'] in ('C','CALL'):
        exp = p['expiry_str']
        if p['qty'] < 0:
            qqq_call_shorts[exp].append(p)
        else:
            qqq_call_longs[exp].append(p)

orphans_found = False
all_exps = set(qqq_call_shorts.keys()) | set(qqq_call_longs.keys())
for exp in sorted(all_exps):
    shorts = sorted(qqq_call_shorts[exp], key=lambda x: x['strike'])
    longs  = list(sorted(qqq_call_longs[exp], key=lambda x: x['strike']))
    exp_dt = date(2000+int(exp[:2]), int(exp[2:4]), int(exp[4:6]))
    dte    = (exp_dt - today).days

    for sl in shorts:
        paired = None
        for ll in longs:
            if ll['strike'] > sl['strike']:
                paired = ll
                break
        if not paired:
            orphans_found = True
            qty_short = abs(sl['qty'])
            print(f"  ORPHANED SHORT: {sl['symbol'].strip()}  qty={qty_short:.0f}  DTE={dte}")
            print(f"  ACTION: BUY TO CLOSE {qty_short:.0f} {sl['symbol'].strip()} {'(URGENT — near expiry)' if dte<=14 else ''}")
        else:
            longs.remove(paired)

    for ll in longs:
        orphans_found = True
        qty_long = abs(ll['qty'])
        print(f"  ORPHANED LONG: {ll['symbol'].strip()}  qty={qty_long:.0f}  DTE={dte}")
        print(f"  ACTION: SELL TO CLOSE {qty_long:.0f} {ll['symbol'].strip()} {'(URGENT — near expiry)' if dte<=14 else ''}")

if not orphans_found:
    print("  CLEAR — All QQQ call legs are properly paired.")

# ── ISSUE 3: Expiry Danger (DTE <= 14) ───────────────────────────────────────
print(f"\n{'='*70}")
print("ISSUE #3: POSITIONS EXPIRING WITHIN 14 DAYS (Assignment Risk)")
print(f"{'='*70}")

danger_opts = [p for p in option_positions if p['dte'] <= 14 and p['dte'] >= 0]
if not danger_opts:
    print("  CLEAR — No options expiring within 14 days.")
else:
    for p in sorted(danger_opts, key=lambda x: x['dte']):
        direction = "SHORT" if p['qty'] < 0 else "LONG"
        live_px_str = ""
        if p['underlying'] == 'QQQ' and qqq_px > 0:
            itm = "ITM" if (p['opt_type'] in ('C','CALL') and qqq_px > p['strike']) or \
                           (p['opt_type'] in ('P','PUT')  and qqq_px < p['strike']) else "OTM"
            pct_dist = abs(qqq_px - p['strike']) / p['strike'] * 100
            live_px_str = f"  QQQ=${qqq_px:.2f} vs K=${p['strike']:.0f} [{itm}, {pct_dist:.1f}% away]"
        print(f"  DTE={p['dte']:>3d}  {direction:5}  {p['symbol'].strip():<40}{live_px_str}")
        action = "BUY_TO_CLOSE" if p['qty'] < 0 else "SELL_TO_CLOSE"
        print(f"  ACTION: {action} {abs(p['qty']):.0f} contracts by {p['exp_date']}")

# ── ISSUE 4: Deep ITM Call Spreads ───────────────────────────────────────────
print(f"\n{'='*70}")
print("ISSUE #4: DEEP ITM CALL SPREADS (Will Settle at Max Loss)")
print(f"{'='*70}")

itm_issues = False
if qqq_px > 0:
    for exp in sorted(all_exps):
        shorts = sorted(qqq_call_shorts[exp], key=lambda x: x['strike'])
        longs  = list(sorted(qqq_call_longs[exp], key=lambda x: x['strike']))
        exp_dt = date(2000+int(exp[:2]), int(exp[2:4]), int(exp[4:6]))
        dte    = (exp_dt - today).days

        for sl in shorts:
            paired = None
            for ll in longs:
                if ll['strike'] > sl['strike']:
                    paired = ll
                    break
            if not paired:
                continue
            longs_tmp = longs[:]
            try:
                longs_tmp.remove(paired)
            except Exception:
                pass

            short_k = sl['strike']
            long_k  = paired['strike']
            spread_w = long_k - short_k

            if short_k < qqq_px:
                pct_itm = (qqq_px - short_k) / short_k * 100
                max_loss = spread_w * abs(sl['qty']) * 100
                credit   = (abs(sl['avg_px']) - paired['avg_px']) * abs(sl['qty']) * 100
                expected_loss = max_loss - credit
                itm_issues = True
                urgency = "CRITICAL" if dte <= 21 else "WARNING"
                print(f"  {urgency}: {short_k}/{long_k} CCS exp={exp} DTE={dte}")
                print(f"    QQQ=${qqq_px:.2f} — short strike {pct_itm:.1f}% ITM")
                print(f"    Max spread loss: ${max_loss:,.0f} | Credit collected: ${credit:,.0f} | Expected loss: ${expected_loss:,.0f}")
                print(f"    ACTION: Close spread ASAP — BTC {sl['symbol'].strip()} + STC {paired['symbol'].strip()}")

if not itm_issues:
    print("  CLEAR — No deep ITM call spreads found.")

# ── ISSUE 5: SQQQ / Bear Hedge Position ──────────────────────────────────────
print(f"\n{'='*70}")
print("ISSUE #5: SQQQ LONG POSITIONS (Bear Hedge Status Check)")
print(f"{'='*70}")

sqqq_positions = [p for p in equity_positions if p['symbol'] == 'SQQQ' and p['qty'] > 0]
if not sqqq_positions:
    print("  CLEAR — No SQQQ positions held.")
else:
    for p in sqqq_positions:
        qty = p['qty']
        avg = p['avg_px']
        pnl_pct = (sqqq_px / avg - 1) * 100 if avg > 0 and sqqq_px > 0 else 0
        print(f"  SQQQ Long: {qty:.0f} shares  avg=${avg:.2f}  live=${sqqq_px:.2f}  P&L={pnl_pct:+.1f}%")
        if vix_px < 20:
            print(f"  WARNING: VIX={vix_px:.1f} < 20 — bear hedge may not be needed. Consider exiting.")
        if pnl_pct >= 30:
            print(f"  ACTION: PROFIT TARGET HIT (30%) — SELL {qty:.0f} SQQQ")
        elif pnl_pct <= -15:
            print(f"  ACTION: STOP LOSS — SELL {qty:.0f} SQQQ (down {pnl_pct:.1f}%)")

# ── Summary Action List ───────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PRIORITY ACTION LIST")
print(f"{'='*70}")

actions = []

for p in short_equity:
    sym = p['symbol']
    actions.append((1, f"[P0] BUY TO CLOSE {abs(p['qty']):.0f} {sym} — eliminate naked short equity"))

for p in sorted(danger_opts, key=lambda x: x['dte']):
    direction = "SHORT" if p['qty'] < 0 else "LONG"
    action_verb = "BUY_TO_CLOSE" if p['qty'] < 0 else "SELL_TO_CLOSE"
    if p['dte'] <= 3:
        priority = 1
        tag = "P0 EMERGENCY"
    elif p['dte'] <= 7:
        priority = 2
        tag = "P1 URGENT"
    else:
        priority = 3
        tag = "P2 THIS WEEK"
    actions.append((priority, f"[{tag}] {action_verb} {abs(p['qty']):.0f} {p['symbol'].strip()} (DTE={p['dte']})"))

if not actions:
    print("  NO URGENT ACTIONS REQUIRED")
    print("  Portfolio appears clean of the 5 known risk categories.")
else:
    for priority, msg in sorted(actions):
        print(f"  {msg}")

print(f"\nScan complete: {today.isoformat()} | {len(positions)} total positions checked")
