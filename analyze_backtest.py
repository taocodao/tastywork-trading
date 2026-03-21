"""
Deep diagnostic analysis of the TurboCore Pro backtest results.
Run with: python analyze_backtest.py
"""
import pandas as pd
import numpy as np

df = pd.read_csv('backtest_turbocore_pro_results.csv')
df['date'] = pd.to_datetime(df['date'])
df['year'] = df['date'].dt.year

print("=" * 70)
print("ROOT CAUSE ANALYSIS — TurboCore Pro Backtest")
print("=" * 70)

# 1. Per-year performance
print("\n[1] ANNUAL PERFORMANCE")
annual = df.groupby('year')['net_liq'].agg(['first', 'last'])
annual['ret_pct'] = ((annual['last'] / annual['first']) - 1) * 100
print(annual.round(2).to_string())

# 2. Regime distribution
print("\n[2] REGIME DISTRIBUTION")
rc = df['regime'].value_counts()
for name, count in rc.items():
    print(f"  {name:<25} {count:>5} days ({count/len(df)*100:.1f}%)")

# 3. BUG CHECK: BEAR_SMA_FORCED allocator giving LEAPS instead of SGOV
print("\n[3] BEAR_SMA_FORCED ALLOCATIONS (BUG CHECK — should be 100% SGOV)")
bear_forced = df[df['regime'] == 'BEAR_SMA_FORCED']
print(f"  Days in BEAR_SMA_FORCED: {len(bear_forced)}")
print("  Avg allocation:")
print(bear_forced[['alloc_QQQ','alloc_QLD','alloc_LEAPS','alloc_SGOV']].mean().round(1).to_string())
bad = bear_forced[bear_forced['alloc_LEAPS'] > 0]
print(f"\n  Days BEAR_SMA_FORCED with LEAPS > 0%: {len(bad)}  <-- SHOULD BE 0")

# 4. LEAPS churn (constant rebalancing = slippage/frictions in real life)
print("\n[4] LEAPS CHURN (daily contract count changes)")
leaps_changes = df['LEAPS_contracts'].diff().abs()
print(f"  Days LEAPS count changed: {(leaps_changes > 0).sum()} out of {len(df)}")
print(f"  Avg daily LEAPS size swing: {leaps_changes.mean():.1f} contracts")
print(f"  Max single-day swing: {leaps_changes.max():.0f} contracts")
print(f"  Min contracts held: {df[df['LEAPS_contracts']>0]['LEAPS_contracts'].min()}")
print(f"  Max contracts held: {df['LEAPS_contracts'].max()}")

# 5. LEAPS are called 'per contract' but executor uses dollar value / price
# The leaps_price in the CSV is the TOTAL call contract price (not per-share)
# Check if we're confusing per-share price vs per-contract price
print("\n[5] LEAPS PRICING CHECK")
print(f"  Avg LEAPS price: ${df['leaps_price'].mean():.2f}")
print(f"  Min LEAPS price: ${df['leaps_price'].min():.2f}")
print(f"  Max LEAPS price: ${df['leaps_price'].max():.2f}")
print(f"  Avg contracts held when active: {df[df['LEAPS_contracts']>0]['LEAPS_contracts'].mean():.1f}")
leaps_value = df['LEAPS_contracts'] * df['leaps_price']
print(f"  Avg LEAPS position value: ${leaps_value[leaps_value>0].mean():.0f}")
print(f"  Avg net_liq when LEAPS held: ${df[df['LEAPS_contracts']>0]['net_liq'].mean():.0f}")
leaps_pct_of_liq = leaps_value / df['net_liq']
print(f"  Avg LEAPS as % of portfolio: {leaps_pct_of_liq[leaps_pct_of_liq>0].mean()*100:.1f}%")

# 6. Are LEAPS actually generating returns vs pure SGOV?
print("\n[6] RETURN COMPARISON: Days with vs without LEAPS")
leaps_on = df[df['LEAPS_contracts'] > 0]['net_liq']
leaps_off = df[df['LEAPS_contracts'] == 0]['net_liq']
if len(leaps_on) > 1:
    leaps_on_ret = leaps_on.pct_change().dropna()
    leaps_off_ret = leaps_off.pct_change().dropna()
    print(f"  Avg daily ret when LEAPS held: {leaps_on_ret.mean()*100:.4f}%")
    print(f"  Avg daily ret when no LEAPS:   {leaps_off_ret.mean()*100:.4f}%")

# 7. Cash drag — are we not deploying capital?
print("\n[7] CASH DRAG ANALYSIS")
df['cash_pct'] = df['cash'] / df['net_liq'] * 100
print(f"  Avg cash % of portfolio: {df['cash_pct'].mean():.1f}%")
print(f"  Days with >50% cash: {(df['cash_pct'] > 50).sum()}")
print(f"  Days with >80% cash: {(df['cash_pct'] > 80).sum()}")
high_cash = df[df['cash_pct'] > 90]
print(f"  Days with >90% cash: {len(high_cash)}")

# 8. Failed LEAPS buys (alloc > 0 but 0 contracts)
print("\n[8] FAILED LEAPS PURCHASES (alloc > 0 but 0 contracts held)")
failed = df[(df['alloc_LEAPS'] > 0) & (df['LEAPS_contracts'] == 0)]
print(f"  Total days: {len(failed)}")
print("  Sample (cash available vs leaps price):")
print(failed[['date','regime','alloc_LEAPS','cash','leaps_price','net_liq']].head(10).to_string())

# 9. Is the LEAPS price confusing contract price vs per-share price?
# In real market: 1 contract = 100 underlying shares. Price is quoted per share.
# So if QQQ=$460, strike=$370, Black-Scholes gives ~$95 per share -> contract = $9500
# Our B-S formula returns price per share, but simulation treats it as full contract price
print("\n[9] LEAPS PER-SHARE vs PER-CONTRACT PRICING BUG CHECK")
print("  If B-S returns price PER UNDERLYING SHARE, then a 'contract' costs:")
leaps_sample = df[df['leaps_price'] > 0][['date','leaps_price']].head(5)
for _, row in leaps_sample.iterrows():
    print(f"    {row['date'].date()} leaps_price=${row['leaps_price']:.2f} "
          f"| as-used (per unit) | contract value (x100) = ${row['leaps_price']*100:.0f}")

# 10. QQQ price reference point
qqq_df = pd.read_csv('backtest_turbocore_pro_results.csv')
print("\n[10] QQQ PRICE vs LEAPS PRICE")
qqq_ref = df[df['leaps_price'] > 0][['date','leaps_price','net_liq']].head(10)
print(qqq_ref.to_string())
print("\n  NOTE: A deep ITM QQQ LEAPS (80% strike) on $460 QQQ should be ~$90-100 PER SHARE")
print("  meaning the *contract* (x100 shares) = $9,000-10,000.")
print("  If leaps_price shown is ~$40-84, we may be using it as a per-unit price (contract)")
print("  rather than multiplying by 100 for the real contract cost.")

print("\n" + "=" * 70)
print("KEY BUG CANDIDATES:")
print("  1. BEAR_SMA_FORCED allocator incorrectly returns 70% LEAPS (should be 100% SGOV)")
print("  2. LEAPS churning every single day (no threshold/rebalance band)")
print("  3. LEAPS price may be treated as per-unit vs per-contract (factor of 100x error)")
print("  4. No rebalance threshold means tiny price movements trigger constant trades")
print("  5. Regime stays in BEAR/SIDEWAYS 70% of time = opportunity cost")
print("=" * 70)
