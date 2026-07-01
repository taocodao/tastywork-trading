"""
Side-by-side comparison: same 8 years, with vs without strangles.
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
import logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '.')

from backtest_otm_naked import download_data
from src.otm_naked.config import OTMNakedConfig, OTM_NAKED_UNIVERSE
from src.otm_naked.backtest_engine import OTMNakedBacktestEngine
import pandas as pd

years = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
market_labels = {
    2018: "Volmageddon / Bear",
    2019: "Strong Bull",
    2020: "COVID Crash & V-Shape",
    2021: "Spec Bull / High Beta",
    2022: "Deep Bear / High IV",
    2023: "Recovery Bull",
    2024: "Choppy Bull",
    2025: "Mixed / Current",
}

results = {}

for year in years:
    print(f"\n{'='*60}")
    print(f"  Year {year} — {market_labels[year]}")
    print(f"{'='*60}")

    # Download data once
    price_data, vix, vix3m, rf = download_data(OTM_NAKED_UNIVERSE, f"{year}-01-01", f"{year}-12-31")
    vix3m_arg = vix3m if len(vix3m) > 0 else None
    rf_arg    = rf    if len(rf)    > 0 else None

    row = {}

    # ── Without strangles ──────────────────────────────────────
    config_off = OTMNakedConfig(
        backtest_start=f"{year}-01-01",
        backtest_end=f"{year}-12-31",
        strangle_enabled=False,
    )
    engine_off = OTMNakedBacktestEngine(config_off)
    res_off = engine_off.run(price_data=price_data, vix=vix, vix3m=vix3m_arg, rf=rf_arg,
                              initial_capital=50_000, use_ml=False)
    m_off = res_off["metrics"]
    row["cagr_off"]   = m_off.get("cagr_pct", 0.0)
    row["dd_off"]     = m_off.get("max_drawdown_pct", 0.0)
    row["trades_off"] = m_off.get("n_trades", 0)
    row["win_off"]    = m_off.get("win_rate_pct", 0.0)
    print(f"  [NO STRANGLES] CAGR={row['cagr_off']:.1f}%  DD={row['dd_off']:.1f}%  "
          f"trades={row['trades_off']}  win={row['win_off']:.1f}%")

    # ── With strangles ─────────────────────────────────────────
    config_on = OTMNakedConfig(
        backtest_start=f"{year}-01-01",
        backtest_end=f"{year}-12-31",
        strangle_enabled=True,
    )
    engine_on = OTMNakedBacktestEngine(config_on)
    res_on = engine_on.run(price_data=price_data, vix=vix, vix3m=vix3m_arg, rf=rf_arg,
                            initial_capital=50_000, use_ml=False)
    m_on  = res_on["metrics"]
    t_on  = res_on.get("trades", pd.DataFrame())
    row["cagr_on"]    = m_on.get("cagr_pct", 0.0)
    row["dd_on"]      = m_on.get("max_drawdown_pct", 0.0)
    row["trades_on"]  = m_on.get("n_trades", 0)
    row["win_on"]     = m_on.get("win_rate_pct", 0.0)

    # Count strangle pairs
    if not t_on.empty and "strangle_id" in t_on.columns:
        strang_legs  = t_on["strangle_id"].notna().sum()
        strang_pairs = t_on["strangle_id"].dropna().nunique()
    else:
        strang_legs, strang_pairs = 0, 0
    row["strang_legs"]  = strang_legs
    row["strang_pairs"] = strang_pairs

    print(f"  [WITH STRANGLES] CAGR={row['cagr_on']:.1f}%  DD={row['dd_on']:.1f}%  "
          f"trades={row['trades_on']}  win={row['win_on']:.1f}%  "
          f"strangles={strang_pairs} pairs")

    results[year] = row

# ── Final comparison table ────────────────────────────────────────────────────
print()
print("=" * 108)
print("  STRANGLE IMPACT — Side-by-Side Comparison (8 Years)")
print("=" * 108)
print(f"  {'Year':<6}  {'Market Condition':<24}  {'No-Strang':>10}  {'W/Strang':>9}  "
      f"{'CAGR Δ':>7}  {'Trades (no→w)':>14}  {'DD (no→w)':>12}  {'Pairs':>6}")
print("  " + "-" * 104)
for year in years:
    r = results[year]
    delta = r["cagr_on"] - r["cagr_off"]
    delta_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
    print(f"  {year:<6}  {market_labels[year]:<24}  "
          f"{r['cagr_off']:>8.1f}%  "
          f"{r['cagr_on']:>7.1f}%  "
          f"{delta_str:>8}  "
          f"{r['trades_off']:>5} -> {r['trades_on']:<7}  "
          f"{r['dd_off']:>4.1f}% -> {r['dd_on']:.1f}%  "
          f"{r['strang_pairs']:>6} pairs")
print("=" * 108)
print()
print("  Notes:")
print("   • CAGR Δ = improvement from adding strangle call legs on qualifying put signals")
print("   • Strangle pairs fired only when IV rank ≥ 0.50 AND VIX ≤ 25 AND not HIGH/CRISIS regime")
