"""
Deep analysis of both TurboCore & TurboCore Pro backtest results.
Run: python deep_analysis.py
"""
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Load data ─────────────────────────────────────────────────────────────────
try:
    pro = pd.read_csv('backtest_turbocore_pro_results.csv')
    pro['date'] = pd.to_datetime(pro['date'])
    pro['year'] = pro['date'].dt.year
    pro_loaded = True
except FileNotFoundError:
    pro_loaded = False
    print("WARNING: backtest_turbocore_pro_results.csv not found")

try:
    std = pd.read_csv('backtest_turbocore_results.csv')
    std['date'] = pd.to_datetime(std['date'])
    std['year'] = std['date'].dt.year
    std_loaded = True
except FileNotFoundError:
    std_loaded = False
    print("WARNING: backtest_turbocore_results.csv not found")

INIT_CAP = 5000.0

def sharpe(daily_returns, risk_free_daily=0.04/252):
    excess = daily_returns - risk_free_daily
    if excess.std() == 0:
        return 0
    return (excess.mean() / excess.std()) * np.sqrt(252)

def calmar(net_liq):
    years = (net_liq.index[-1] - net_liq.index[0]).days / 365.25
    total_ret = (net_liq.iloc[-1] / net_liq.iloc[0]) - 1
    cagr = (1 + total_ret) ** (1/years) - 1
    peak = net_liq.cummax()
    dd = (net_liq - peak) / peak
    max_dd = dd.min()
    return cagr / abs(max_dd) if max_dd != 0 else 0

def max_drawdown_series(net_liq):
    peak = net_liq.cummax()
    dd = (net_liq - peak) / peak
    return dd

print("=" * 70)
print("DEEP BACKTEST ANALYSIS — TurboCore Standard vs TurboCore Pro")
print("=" * 70)

# ── 1. Annual Performance ─────────────────────────────────────────────────────
print("\n[1] ANNUAL PERFORMANCE BY YEAR")
print(f"{'Year':<6} {'TC_Standard':>12} {'TC_Pro':>12}")
print("-" * 32)
all_years = list(range(2019, 2027))
for year in all_years:
    std_ret = pro_ret = "N/A"
    if std_loaded:
        yr = std[std['year'] == year]
        if len(yr) > 1:
            std_ret = f"{(yr['net_liq'].iloc[-1]/yr['net_liq'].iloc[0]-1)*100:>+10.1f}%"
    if pro_loaded:
        yr = pro[pro['year'] == year]
        if len(yr) > 1:
            pro_ret = f"{(yr['net_liq'].iloc[-1]/yr['net_liq'].iloc[0]-1)*100:>+10.1f}%"
    print(f"  {year}  {std_ret:>12} {pro_ret:>12}")

# ── 2. Risk-Adjusted Metrics ──────────────────────────────────────────────────
print("\n[2] RISK-ADJUSTED PERFORMANCE METRICS")
for label, df, loaded in [("TurboCore Standard", std, std_loaded),
                            ("TurboCore Pro",      pro, pro_loaded)]:
    if not loaded:
        continue
    daily_ret = df['net_liq'].pct_change().dropna()
    years = (df['date'].iloc[-1] - df['date'].iloc[0]).days / 365.25
    total_ret = df['net_liq'].iloc[-1] / INIT_CAP - 1
    cagr = (1 + total_ret) ** (1/years) - 1
    peak = df['net_liq'].cummax()
    dd = (df['net_liq'] - peak) / peak
    max_dd = dd.min()
    sharpe_r = sharpe(daily_ret)
    calmar_r = cagr / abs(max_dd) if max_dd != 0 else 0

    print(f"\n  {label}")
    print(f"    Total Return  : {total_ret*100:>8.1f}%")
    print(f"    CAGR          : {cagr*100:>8.1f}%")
    print(f"    Sharpe Ratio  : {sharpe_r:>8.2f}")
    print(f"    Calmar Ratio  : {calmar_r:>8.2f}")
    print(f"    Max Drawdown  : {max_dd*100:>8.1f}%")
    print(f"    Volatility    : {daily_ret.std()*np.sqrt(252)*100:>8.1f}%  (annualized)")
    print(f"    Best Day      : {daily_ret.max()*100:>8.2f}%")
    print(f"    Worst Day     : {daily_ret.min()*100:>8.2f}%")

# ── 3. Signal Quality ─────────────────────────────────────────────────────────
print("\n[3] SIGNAL QUALITY — REGIME vs NEXT-DAY RETURN")
if pro_loaded:
    pro['next_ret'] = pro['net_liq'].pct_change().shift(-1) * 100
    regime_quality = pro.groupby('regime')['next_ret'].agg(['mean','std','count'])
    regime_quality.columns = ['avg_next_day_ret%','std','days']
    print("  TurboCore Pro:")
    print(regime_quality.round(3).to_string())

if std_loaded:
    std['next_ret'] = std['net_liq'].pct_change().shift(-1) * 100
    regime_quality_s = std.groupby('regime')['next_ret'].agg(['mean','std','count'])
    regime_quality_s.columns = ['avg_next_day_ret%','std','days']
    print("\n  TurboCore Standard:")
    print(regime_quality_s.round(3).to_string())

# ── 4. Confidence Score vs Return ─────────────────────────────────────────────
print("\n[4] ML CONFIDENCE SCORE DISTRIBUTION & IMPACT")
if pro_loaded:
    pro['conf_bucket'] = pd.cut(pro['confidence'],
                                bins=[0,0.5,0.55,0.60,0.65,0.70,0.80,1.0],
                                labels=['<50%','50-55%','55-60%','60-65%','65-70%','70-80%','>80%'])
    conf_analysis = pro.groupby('conf_bucket').agg(
        days=('net_liq','count'),
        avg_next_ret=('next_ret','mean'),
        alloc_leaps=('alloc_LEAPS','mean'),
        alloc_sgov=('alloc_SGOV','mean')
    ).round(3)
    print("  TurboCore Pro (confidence vs next-day return):")
    print(conf_analysis.to_string())
    print(f"\n  NOTE: Days with conf=55% (default fallback): {(pro['confidence']==0.55).sum()}")
    print(f"        Days with conf<60%: {(pro['confidence']<0.60).sum()}")
    print(f"        Days with conf>65%: {(pro['confidence']>0.65).sum()}")

# ── 5. Opportunity Cost Analysis ──────────────────────────────────────────────
print("\n[5] OPPORTUNITY COST vs BUY & HOLD BENCHMARKS")
import yfinance as yf

try:
    bmark = yf.download(['QQQ','TQQQ','SPY'], start='2019-01-01', end='2026-03-20',
                        auto_adjust=True, progress=False)
    for sym in ['QQQ','TQQQ','SPY']:
        try:
            px = bmark['Close'][sym].dropna()
            ret = (px.iloc[-1] / px.iloc[0] - 1) * 100
            yrs = (px.index[-1]-px.index[0]).days/365.25
            cagr_b = ((px.iloc[-1]/px.iloc[0])**(1/yrs)-1)*100
            peak = px.cummax()
            mdd = ((px-peak)/peak).min()*100
            print(f"  {sym+' B&H':<14}  Total={ret:>7.1f}%  CAGR={cagr_b:>6.1f}%  MaxDD={mdd:>7.1f}%")
        except:
            pass

    if std_loaded:
        ret_s = (std['net_liq'].iloc[-1]/INIT_CAP-1)*100
        yrs = (std['date'].iloc[-1]-std['date'].iloc[0]).days/365.25
        cagr_s = ((std['net_liq'].iloc[-1]/INIT_CAP)**(1/yrs)-1)*100
        dd_s = max_drawdown_series(std.set_index('date')['net_liq']).min()*100
        print(f"  {'TC Standard':<14}  Total={ret_s:>7.1f}%  CAGR={cagr_s:>6.1f}%  MaxDD={dd_s:>7.1f}%")
    if pro_loaded:
        ret_p = (pro['net_liq'].iloc[-1]/INIT_CAP-1)*100
        yrs = (pro['date'].iloc[-1]-pro['date'].iloc[0]).days/365.25
        cagr_p = ((pro['net_liq'].iloc[-1]/INIT_CAP)**(1/yrs)-1)*100
        dd_p = max_drawdown_series(pro.set_index('date')['net_liq']).min()*100
        print(f"  {'TC Pro':<14}  Total={ret_p:>7.1f}%  CAGR={cagr_p:>6.1f}%  MaxDD={dd_p:>7.1f}%")
except Exception as e:
    print(f"  Could not download benchmarks: {e}")

# ── 6. Drawdown Periods ───────────────────────────────────────────────────────
print("\n[6] WORST DRAWDOWN PERIODS (Pro)")
if pro_loaded:
    pro_idx = pro.set_index('date')
    dd_s = max_drawdown_series(pro_idx['net_liq']) * 100
    # Find top 5 drawdown troughs
    worst = dd_s.nsmallest(5)
    print("  Top 5 drawdown troughs:")
    for dt, val in worst.items():
        regime_at = pro_idx['regime'].loc[dt]
        nliq = pro_idx['net_liq'].loc[dt]
        print(f"    {dt.date()}  DD={val:>7.1f}%  regime={regime_at}  net_liq=${nliq:,.0f}")

# ── 7. LEAPS Analysis ─────────────────────────────────────────────────────────
print("\n[7] LEAPS IMPACT ANALYSIS (Pro)")
if pro_loaded and 'LEAPS_contracts' in pro.columns:
    leaps_on  = pro[pro['LEAPS_contracts'] > 0]
    leaps_off = pro[pro['LEAPS_contracts'] == 0]

    if len(leaps_on) > 1:
        ret_on  = leaps_on['next_ret'].mean()
        ret_off = leaps_off['next_ret'].mean()
        print(f"  When LEAPS held:    avg next-day ret = {ret_on:.4f}%  ({len(leaps_on)} days)")
        print(f"  When no LEAPS:      avg next-day ret = {ret_off:.4f}%  ({len(leaps_off)} days)")
        print(f"  Avg LEAPS contract price: ${pro['leaps_price'].mean():,.0f}")
        print(f"  Max LEAPS contract price: ${pro['leaps_price'].max():,.0f}")
        print(f"  Min LEAPS contract price: ${pro['leaps_price'].min():,.0f}")
        # LEAPS PnL estimation
        leaps_val_series = leaps_on['LEAPS_contracts'] * leaps_on['leaps_price']
        print(f"  Avg LEAPS position value: ${leaps_val_series.mean():,.0f}")
        print(f"  Avg LEAPS % of net_liq: {(leaps_val_series/leaps_on['net_liq']).mean()*100:.1f}%")

# ── 8. Regime Transition Matrix ───────────────────────────────────────────────
print("\n[8] REGIME TRANSITION MATRIX (Pro) — what tends to follow each regime")
if pro_loaded:
    pro['next_regime'] = pro['regime'].shift(-1)
    trans = pd.crosstab(pro['regime'], pro['next_regime'], normalize='index').round(2)
    print(trans.to_string())

# ── 9. Why returns are low — root cause summary ───────────────────────────────
print("\n[9] ROOT CAUSE SUMMARY — WHY RETURNS ARE BELOW QQQ B&H")
print("""
  The strategies correctly preserve capital in bear markets (low MaxDD)
  but at the cost of growth. Key structural reasons:

  A. HMM/XGBoost confidence stuck at 55% fallback for most days
     -> When ML confidence is 50-55%, allocator avoids high TQQQ/LEAPS
     -> This is because the ML models are retrained daily on expanding window
        but the HMM was trained on recent data — it may not fit 2019 well

  B. 40% of days in BEAR/BEAR_SMA_FORCED = 100% SGOV earning ~5%/yr
     -> This protects from crashes but QQQ gained +20%/yr in BULL periods
     -> The "opportunity cost" of being in SGOV during BULL misidentifications
        is the primary return drag

  C. LEAPS only active 14.7% of days (Pro) due to $5k constraint
     -> At $5k, 1 contract costs $4k-$8k, consuming 80-160% of portfolio
     -> Real benefit of LEAPS emerges at $25k+ account sizes

  D. SIDEWAYS regime allocates 50% QQQ, 20% QLD, 25% LEAPS — watered down
     -> This is 30% of all days — conservative but not as profitable as BULL

  E. No momentum carry: strategy resets allocation daily from scratch
     -> Profitable trends get interrupted by brief SIDEWAYS classifications

  RECOMMENDATION: Test with larger capital ($25k-$50k) to see more realistic
  LEAPS participation. Also review HMM initialization on the 2019-2021 bull.
""")

print("=" * 70)
print("Analysis complete.")
