"""Deep analysis of backtest trade history."""
import json
from collections import Counter, defaultdict

with open('data/last_backtest_trades.json') as f:
    trades = json.load(f)

print(f"Total trade events: {len(trades)}")
actions = Counter(t['action'] for t in trades)
print(f"Action breakdown: {dict(actions)}")

opens = [t for t in trades if t['action'] == 'OPEN']
close_anchors = [t for t in trades if t['action'] == 'CLOSE_ANCHOR']
close_hedges = [t for t in trades if t['action'] == 'CLOSE_HEDGE']
rehedges = [t for t in trades if t['action'] == 'REHEDGE']

print(f"\nOPENs: {len(opens)}")
print(f"CLOSE_ANCHOR: {len(close_anchors)}")
print(f"CLOSE_HEDGE: {len(close_hedges)}")
print(f"REHEDGE: {len(rehedges)}")

if opens:
    credits = [t['net_credit'] for t in opens]
    print(f"\n--- OPEN Analysis ---")
    print(f"Avg net credit: ${sum(credits)/len(credits)*100:.2f} per contract")
    print(f"Min/Max credit: ${min(credits)*100:.2f} / ${max(credits)*100:.2f}")

if close_anchors:
    costs = [t['cost'] for t in close_anchors]
    print(f"\n--- CLOSE ANCHOR Analysis ---")
    print(f"Avg anchor close cost: ${sum(costs)/len(costs)*100:.2f}")
    print(f"Min/Max cost: ${min(costs)*100:.2f} / ${max(costs)*100:.2f}")

if close_hedges:
    hcredits = [t['credit'] for t in close_hedges]
    print(f"\n--- CLOSE HEDGE Analysis ---")
    print(f"Avg hedge close credit: ${sum(hcredits)/len(hcredits)*100:.2f}")

# Per-position PnL (match opens to close_anchors by pid)
print(f"\n--- Position-Level PnL ---")
open_by_pid = {t['pid']: t for t in opens}
close_by_pid = {t['pid']: t for t in close_anchors}
hedge_by_pid = defaultdict(list)
for t in close_hedges:
    hedge_by_pid[t['pid']].append(t)
rehedge_by_pid = defaultdict(list)
for t in rehedges:
    rehedge_by_pid[t['pid']].append(t)

pnls = []
for pid in open_by_pid:
    o = open_by_pid[pid]
    # Cash flow: +net_credit at open (anchor credit - hedge debit)
    cash = o['net_credit'] * 100
    
    # Cash flow from hedge closes: +credit
    for h in hedge_by_pid.get(pid, []):
        cash += h['credit'] * 100
    
    # Cash flow from rehedges: -cost
    for r in rehedge_by_pid.get(pid, []):
        cash -= r['cost'] * 100
    
    # Cash flow from anchor close: -cost
    if pid in close_by_pid:
        cash -= close_by_pid[pid]['cost'] * 100
    
    pnls.append(cash)

if pnls:
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p <= 0)
    print(f"Total positions: {len(pnls)}")
    print(f"Win rate: {wins}/{len(pnls)} = {wins/len(pnls)*100:.1f}%")
    print(f"Avg PnL: ${sum(pnls)/len(pnls):.2f}")
    print(f"Total PnL: ${sum(pnls):.2f}")
    print(f"Best: ${max(pnls):.2f}")
    print(f"Worst: ${min(pnls):.2f}")
    
    # Sort to see distribution
    sorted_pnls = sorted(pnls)
    print(f"\nPnL Distribution (per position):")
    print(f"  Bottom 5: {['${:.2f}'.format(p) for p in sorted_pnls[:5]]}")
    print(f"  Top 5:    {['${:.2f}'.format(p) for p in sorted_pnls[-5:]]}")

# Opens by year
yearly = defaultdict(int)
for t in opens:
    yearly[t['date'][:4]] += 1
print(f"\nOpens by year: {dict(sorted(yearly.items()))}")

# First/Last trade
dates = sorted(set(t['date'] for t in trades))
print(f"First trade: {dates[0]}")
print(f"Last trade: {dates[-1]}")

# Show 3 sample full position lifecycles
print(f"\n--- Sample Position Lifecycles ---")
sample_pids = list(open_by_pid.keys())[:3]
for pid in sample_pids:
    print(f"\nPosition {pid}:")
    pos_trades = [t for t in trades if t.get('pid') == pid]
    for t in pos_trades:
        print(f"  {t['date']}: {t['action']} ", end="")
        if 'net_credit' in t: print(f"net_credit={t['net_credit']:.4f}")
        elif 'cost' in t: print(f"cost={t['cost']:.4f}")
        elif 'credit' in t: print(f"credit={t['credit']:.4f}")
        else: print()
