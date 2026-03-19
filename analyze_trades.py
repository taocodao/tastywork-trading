import pandas as pd

df = pd.read_csv('turbobounce_options_15k_all_trades.csv')

print("=" * 80)
print("DEEP ANALYSIS OF TURBOBOUNCE BACKTEST RESULTS")
print("=" * 80)

print("\n=== BY STRATEGY ===")
for strat, g in df.groupby('Strategy'):
    wins = (g['PnL $'] > 0).sum()
    losses = (g['PnL $'] <= 0).sum()
    wr = wins / len(g) * 100
    total_pnl = g['PnL $'].sum()
    avg_w = g[g['PnL $'] > 0]['PnL $'].mean() if wins > 0 else 0
    avg_l = g[g['PnL $'] <= 0]['PnL $'].mean() if losses > 0 else 0
    avg_days = g['Days Held'].mean()
    print(f"\n  {strat}: {len(g)} trades | Win Rate: {wr:.0f}% ({wins}W/{losses}L)")
    print(f"    Total PnL: ${total_pnl:+,.2f} | Avg Win: ${avg_w:+,.2f} | Avg Loss: ${avg_l:+,.2f}")
    print(f"    Avg Days Held: {avg_days:.1f}")

print("\n\n=== BY EXIT REASON ===")
for exit_r, g in df.groupby('Exit'):
    total = g['PnL $'].sum()
    avg = g['PnL $'].mean()
    cnt = len(g)
    wr = (g['PnL $'] > 0).sum() / cnt * 100
    print(f"  {exit_r}")
    print(f"    Count: {cnt} | Total PnL: ${total:+,.2f} | Avg PnL: ${avg:+,.2f} | Win Rate: {wr:.0f}%")

print("\n\n=== BIGGEST LOSSES (> $500) ===")
big = df[df['PnL $'] < -500].sort_values('PnL $')
for _, row in big.iterrows():
    print(f"  {row['Symbol']:6s} {row['Strategy']:18s} {row['Exit'][:50]:50s} | ${row['PnL $']:+,.2f} ({row['PnL %']:+.1f}%) | {row['Days Held']}d")

print("\n\n=== BIGGEST WINS (> $500) ===")
big_w = df[df['PnL $'] > 500].sort_values('PnL $', ascending=False)
for _, row in big_w.iterrows():
    print(f"  {row['Symbol']:6s} {row['Strategy']:18s} {row['Exit'][:50]:50s} | ${row['PnL $']:+,.2f} ({row['PnL %']:+.1f}%) | {row['Days Held']}d")

print("\n\n=== THETA KICKER ANALYSIS ===")
tk = df[df['Exit'].str.contains('THETA_KICKER', na=False)]
print(f"  Total Theta Kicker exits: {len(tk)}")
print(f"  Win Rate: {(tk['PnL $'] > 0).mean()*100:.0f}%")
print(f"  Total PnL: ${tk['PnL $'].sum():+,.2f}")
print(f"  Avg PnL: ${tk['PnL $'].mean():+,.2f}")

print("\n\n=== TIME STOP ANALYSIS ===")
ts = df[df['Exit'].str.contains('TIME_STOP', na=False)]
print(f"  Total Time Stop exits: {len(ts)}")
print(f"  Win Rate: {(ts['PnL $'] > 0).mean()*100:.0f}%")
print(f"  Total PnL: ${ts['PnL $'].sum():+,.2f}")
print(f"  Avg PnL: ${ts['PnL $'].mean():+,.2f}")

print("\n\n=== STOP LOSS ANALYSIS ===")
sl = df[df['Exit'].str.contains('BP_STOP_LOSS', na=False)]
print(f"  Total Stop Loss exits: {len(sl)}")
print(f"  Total PnL: ${sl['PnL $'].sum():+,.2f}")
print(f"  Avg PnL: ${sl['PnL $'].mean():+,.2f}")
print(f"  This = {sl['PnL $'].sum() / df['PnL $'].sum() * 100:.0f}% of total losses") if df['PnL $'].sum() != 0 else None

print("\n\n=== ENTRY VAL vs EXIT VAL ANALYSIS ===")
avg_entry = df['Entry $'].mean()
avg_exit = df['Exit $'].mean()
print(f"  Avg Entry Value: ${avg_entry:,.2f}")
print(f"  Avg Exit Value:  ${avg_exit:,.2f}")
print(f"  Avg PnL per trade: ${df['PnL $'].mean():+,.2f}")

# IV analysis: did we overpay at entry?
print("\n\n=== DIAGONAL SPREAD IV DRAG ===")
diag = df[df['Strategy'] == 'DIAGONAL']
if len(diag) > 0:
    diag_tk = diag[diag['Exit'].str.contains('THETA_KICKER', na=False)]
    diag_he = diag[diag['Exit'].str.contains('HEDGE_EXPIRING', na=False)]
    diag_other = diag[~diag['Exit'].str.contains('THETA_KICKER|HEDGE_EXPIRING', na=False)]
    print(f"  Theta Kicker rolls: {len(diag_tk)} trades, PnL ${diag_tk['PnL $'].sum():+,.2f}")
    print(f"  Hedge Expiring:     {len(diag_he)} trades, PnL ${diag_he['PnL $'].sum():+,.2f}")
    print(f"  Other exits:        {len(diag_other)} trades, PnL ${diag_other['PnL $'].sum():+,.2f}")
