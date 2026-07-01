import csv
import re
from collections import defaultdict
from datetime import datetime

filepath = r"d:\Projects\echoads\tastytrade_transactions_history_x5WI28023_260101_to_260529.csv"

rows = []
with open(filepath, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

# Parse value helper
def parse_val(s):
    s = s.strip().replace(',', '').replace('"', '')
    if not s or s == '--':
        return 0.0
    return float(s)

# ============ 1. OPTION TRADES SUMMARY ============
print("="*80)
print("OPTION TRADES ANALYSIS")
print("="*80)

option_trades = [r for r in rows if r['Instrument Type'] == 'Equity Option' and r['Type'] == 'Trade']
option_positions = defaultdict(list)

for t in option_trades:
    symbol = t['Symbol'].strip()
    option_positions[symbol].append(t)

print(f"\nTotal option trades: {len(option_trades)}")
print(f"Unique option symbols: {len(option_positions)}")

# Group options by strategy/underlying
print("\n--- Option P&L by Symbol ---")
for sym, trades in sorted(option_positions.items()):
    total = 0
    for t in trades:
        total += parse_val(t['Total'])
    underlying = trades[0].get('Underlying Symbol', '')
    strike = trades[0].get('Strike Price', '')
    cp = trades[0].get('Call or Put', '')
    exp = trades[0].get('Expiration Date', '')
    print(f"  {sym:40s}  Net: ${total:>10,.2f}  ({underlying} {strike} {cp} exp:{exp})")

# ============ 2. QQQ LEAPS / CALL SPREADS ============
print("\n" + "="*80)
print("QQQ CALL SPREAD (LEAPS) ANALYSIS")
print("="*80)

qqq_calls = [r for r in option_trades if r.get('Underlying Symbol') == 'QQQ' and r.get('Call or Put') == 'CALL']
qqq_puts = [r for r in option_trades if r.get('Underlying Symbol') == 'QQQ' and r.get('Call or Put') == 'PUT']

print("\n--- QQQ CALL trades ---")
total_qqq_call_pnl = 0
for t in qqq_calls:
    val = parse_val(t['Total'])
    total_qqq_call_pnl += val
    action = t['Action']
    sym = t['Symbol'].strip()
    qty = t['Quantity']
    price = t['Average Price']
    dt = t['Date'][:10]
    print(f"  {dt}  {action:20s}  {sym:35s}  qty:{qty:>3s}  price:{price:>10s}  total:{val:>10,.2f}")
print(f"  QQQ CALLS NET: ${total_qqq_call_pnl:,.2f}")

print("\n--- QQQ PUT trades ---")
total_qqq_put_pnl = 0
for t in qqq_puts:
    val = parse_val(t['Total'])
    total_qqq_put_pnl += val
    action = t['Action']
    sym = t['Symbol'].strip()
    qty = t['Quantity']
    price = t['Average Price']
    dt = t['Date'][:10]
    print(f"  {dt}  {action:20s}  {sym:35s}  qty:{qty:>3s}  price:{price:>10s}  total:{val:>10,.2f}")
print(f"  QQQ PUTS NET: ${total_qqq_put_pnl:,.2f}")

# ============ 3. ASSIGNMENT / EXERCISE EVENTS ============
print("\n" + "="*80)
print("ASSIGNMENT / EXERCISE EVENTS")
print("="*80)

assigns = [r for r in rows if r['Type'] == 'Receive Deliver' and r['Sub Type'] in ('Assignment', 'Exercise', 'Expiration')]
for a in assigns:
    dt = a['Date'][:10]
    sym = a['Symbol'].strip()
    sub = a['Sub Type']
    desc = a['Description']
    val = parse_val(a['Total'])
    print(f"  {dt}  {sub:15s}  {sym:35s}  ${val:>12,.2f}  {desc}")

# The resulting stock transactions from assignments
assign_stock = [r for r in rows if r['Type'] == 'Receive Deliver' and r['Sub Type'] in ('Sell to Close', 'Buy to Open', 'Buy to Close')]
print("\n--- Stock from Assignment/Exercise ---")
for a in assign_stock:
    dt = a['Date'][:10]
    sym = a['Symbol'].strip()
    sub = a['Sub Type']
    action = a['Action']
    qty = a['Quantity']
    price = a['Average Price']
    val = parse_val(a['Total'])
    print(f"  {dt}  {action:20s}  {sym:10s}  qty:{qty:>5s}  price:{price:>10s}  ${val:>12,.2f}")

# ============ 4. IV SWITCH ANALYSIS (QQQ/QLD/TQQQ rotation) ============
print("\n" + "="*80)
print("IV SWITCH ANALYSIS - QQQ / QLD / TQQQ ROTATION")
print("="*80)

# Track equity trades by date for QQQ, QLD, TQQQ, SGOV
equity_trades = [r for r in rows if r['Instrument Type'] == 'Equity' and r['Type'] == 'Trade']

# Group by date
from collections import OrderedDict
daily_flows = OrderedDict()
for t in equity_trades:
    dt = t['Date'][:10]
    sym = t['Symbol'].strip()
    action = t['Action']
    val = parse_val(t['Total'])
    qty = parse_val(t['Quantity'])
    
    if dt not in daily_flows:
        daily_flows[dt] = defaultdict(lambda: {'buy': 0, 'sell': 0, 'buy_qty': 0, 'sell_qty': 0})
    
    if action in ('BUY_TO_OPEN', 'BUY_TO_CLOSE'):
        daily_flows[dt][sym]['buy'] += val
        daily_flows[dt][sym]['buy_qty'] += qty
    else:
        daily_flows[dt][sym]['sell'] += val
        daily_flows[dt][sym]['sell_qty'] += qty

print("\n--- Daily Net Flows (QQQ, QLD, TQQQ, SGOV) ---")
total_qqq_net = 0
total_qld_net = 0
total_tqqq_net = 0
total_sgov_net = 0
for dt, syms in daily_flows.items():
    line = f"  {dt}: "
    parts = []
    for sym in ['QQQ', 'QLD', 'TQQQ', 'SGOV']:
        if sym in syms:
            net = syms[sym]['sell'] + syms[sym]['buy']  # buy is negative, sell is positive
            net_qty = syms[sym]['sell_qty'] - syms[sym]['buy_qty']
            parts.append(f"{sym}: ${net:>10,.0f} ({net_qty:>+8,.0f} shares)")
            if sym == 'QQQ': total_qqq_net += net
            elif sym == 'QLD': total_qld_net += net
            elif sym == 'TQQQ': total_tqqq_net += net
            elif sym == 'SGOV': total_sgov_net += net
    print(line + "  |  ".join(parts))

print(f"\n  TOTALS: QQQ=${total_qqq_net:>12,.2f}  QLD=${total_qld_net:>12,.2f}  TQQQ=${total_tqqq_net:>12,.2f}  SGOV=${total_sgov_net:>12,.2f}")
print(f"  COMBINED EQUITY NET: ${total_qqq_net + total_qld_net + total_tqqq_net + total_sgov_net:>12,.2f}")

# ============ 5. TOTAL ACCOUNT P&L ============
print("\n" + "="*80)
print("TOTAL ACCOUNT P&L")
print("="*80)

deposits = 0
withdrawals = 0
dividends = 0
interest = 0
fees = 0
trade_total = 0

for r in rows:
    val = parse_val(r['Total'])
    typ = r['Type']
    sub = r['Sub Type']
    
    if typ == 'Money Movement':
        if sub == 'Deposit':
            deposits += val
        elif sub == 'Dividend':
            dividends += val
        elif sub == 'Debit Interest':
            interest += val
        elif sub == 'Balance Adjustment':
            fees += val
        elif sub == 'Transfer':
            fees += val
    elif typ == 'Trade':
        trade_total += val
    elif typ == 'Receive Deliver':
        trade_total += val

print(f"  Deposits: ${deposits:>12,.2f}")
print(f"  Dividends: ${dividends:>12,.2f}")
print(f"  Interest: ${interest:>12,.2f}")
print(f"  Reg Fees/Transfer: ${fees:>12,.2f}")
print(f"  Trade P&L (incl assign): ${trade_total:>12,.2f}")
print(f"  ---")
print(f"  Net Change: ${deposits + dividends + interest + fees + trade_total:>12,.2f}")

# ============ 6. QQQ 05/15 CALL SPREAD DEEP DIVE ============
print("\n" + "="*80)
print("QQQ 05/15/26 CALL SPREAD - DEEP DIVE (THE LIKELY BIGGEST LOSS)")
print("="*80)

# Find all QQQ 05/15 option trades
qqq_0515_trades = [r for r in rows if 'QQQ' in r.get('Symbol', '') and '260515' in r.get('Symbol', '') and r.get('Instrument Type') == 'Equity Option']
for t in qqq_0515_trades:
    dt = t['Date'][:16]
    action = t['Action']
    sym = t['Symbol'].strip()
    qty = t['Quantity']
    price = t['Average Price']
    val = parse_val(t['Total'])
    print(f"  {dt}  {action:20s}  {sym:35s}  qty:{qty}  price:{price}  total:{val:>10,.2f}")

total_0515 = sum(parse_val(t['Total']) for t in qqq_0515_trades)
print(f"  NET on QQQ 05/15 options: ${total_0515:,.2f}")

# Stock assignment from 05/15
qqq_0515_assign = [r for r in rows if 'QQQ' in r.get('Symbol', '') and '260515' in r.get('Symbol', '') and r['Type'] == 'Receive Deliver']
assign_stock_0515 = [r for r in rows if r['Type'] == 'Receive Deliver' and '2026-05-15' in r['Date'] and r.get('Symbol', '').strip() == 'QQQ']

print("\n--- 05/15 Assignment/Exercise events ---")
for t in qqq_0515_assign + assign_stock_0515:
    dt = t['Date'][:16]
    sub = t['Sub Type']
    sym = t['Symbol'].strip()
    desc = t['Description']
    val = parse_val(t['Total'])
    qty = t['Quantity']
    price = t['Average Price']
    print(f"  {dt}  {sub:15s}  {sym:35s}  qty:{qty}  price:{price}  ${val:>12,.2f}  {desc}")

# ============ 7. QQQ 06/18 CALL SPREAD ANALYSIS ============
print("\n" + "="*80)
print("QQQ 06/18/26 CALL SPREAD ANALYSIS")
print("="*80)

qqq_0618_trades = [r for r in rows if 'QQQ' in r.get('Symbol', '') and '260618' in r.get('Symbol', '') and r.get('Instrument Type') == 'Equity Option']
for t in qqq_0618_trades:
    dt = t['Date'][:16]
    action = t['Action']
    sym = t['Symbol'].strip()
    qty = t['Quantity']
    price = t['Average Price']
    val = parse_val(t['Total'])
    print(f"  {dt}  {action:20s}  {sym:35s}  qty:{qty}  price:{price}  total:{val:>10,.2f}")

total_0618 = sum(parse_val(t['Total']) for t in qqq_0618_trades)
print(f"  NET on QQQ 06/18 options: ${total_0618:,.2f}")

# ============ 8. OTHER OPTIONS (NUGT, ASML, SNDK, etc) ============
print("\n" + "="*80)
print("OTHER OPTIONS DEEP DIVE")
print("="*80)

other_option_syms = set()
for t in option_trades:
    und = t.get('Underlying Symbol', '')
    if und not in ('QQQ', 'TQQQ', ''):
        other_option_syms.add(und)

for und in sorted(other_option_syms):
    trades = [t for t in option_trades if t.get('Underlying Symbol') == und]
    total = sum(parse_val(t['Total']) for t in trades)
    print(f"\n  {und}: Net = ${total:>10,.2f}")
    for t in trades:
        dt = t['Date'][:10]
        action = t['Action']
        sym = t['Symbol'].strip()
        qty = t['Quantity']
        price = t['Average Price']
        val = parse_val(t['Total'])
        print(f"    {dt}  {action:20s}  {sym:35s}  qty:{qty}  price:{price}  ${val:>10,.2f}")
