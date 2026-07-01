"""
Phase 1 Validation Backtest
Runs isolated single-year backtests for 2018, 2020, 2022, 2024 with Phase 1 changes:
  - Bug fix: cash accounting corrected
  - Sizing: 4% per trade (from 2.5%)
  - 21-DTE forced exit (from 7 DTE)
  - SGOV cash sweep: 4.5% on idle cash

Prints a summary table and writes per-year trade logs.
"""
import subprocess
import pandas as pd

years  = [2018, 2020, 2022, 2024]
labels = {
    2018: "Volmageddon / Bear",
    2020: "COVID Crash & V-Shape",
    2022: "Deep Bear / High IV",
    2024: "Choppy Bull",
}
INITIAL_CAPITAL = 50_000.0
output_file = "HILO-IV Seller/Phase1_Validation_Trades.md"


def run_year(year):
    print(f"  Running {year}...", flush=True)
    result = subprocess.run(
        ["python", "backtest_otm_naked.py",
         "--start", f"{year}-01-01",
         "--end",   f"{year}-12-31",
         "--capital", str(int(INITIAL_CAPITAL)),
         "--no-ml"],
        capture_output=True, text=True, cwd="."
    )
    all_output = result.stdout + result.stderr

    # Parse summary lines
    summary = {}
    for line in all_output.split("\n"):
        line = line.strip()
        if "Final Value" in line:
            try: summary["final"] = float(line.split("$")[1].replace(",",""))
            except: pass
        elif "CAGR" in line and "%" in line:
            try: summary["cagr"] = float(line.split(":")[1].strip().replace("%",""))
            except: pass
        elif "Max Drawdown" in line:
            try: summary["max_dd"] = float(line.split(":")[1].strip().replace("%",""))
            except: pass
        elif "Total Trades" in line:
            try: summary["trades"] = int(line.split(":")[1].strip())
            except: pass
        elif "Win Rate" in line:
            try: summary["win_rate"] = float(line.split(":")[1].strip().replace("%",""))
            except: pass
        elif "Profit Factor" in line:
            try: summary["pf"] = float(line.split(":")[1].strip())
            except: pass

    # Load trades CSV
    try:
        df = pd.read_csv("backtest_otm_naked_trades.csv")
        df["entry_date"]  = pd.to_datetime(df["entry_date"])
        df["expiry_date"] = pd.to_datetime(df["expiry_date"])
        df["exit_date"]   = pd.to_datetime(df["exit_date"])
        df["DTE"]        = (df["expiry_date"] - df["entry_date"]).dt.days
        df["held_days"]  = (df["exit_date"]   - df["entry_date"]).dt.days
    except Exception as e:
        print(f"    Warning: Could not load trades CSV: {e}")
        df = pd.DataFrame()

    return summary, df


# ── Run all years ──────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  HILO-IV Phase 1 Validation Backtest")
print("  Changes: Bug fix + 4% sizing + 21-DTE exit + SGOV sweep")
print("="*65)

all_results = {}
for year in years:
    summary, df = run_year(year)
    all_results[year] = (summary, df)

# ── Print comparison table ─────────────────────────────────────────────────────
print()
print(f"  {'Year':<6} {'Market':<24} {'CAGR':>7} {'MaxDD':>7} {'Trades':>7} {'WinRate':>8} {'PF':>6} {'FinalNAV':>12}")
print("  " + "-"*84)

acceptance = []
for year in years:
    s, df = all_results[year]
    cagr     = s.get("cagr", 0)
    max_dd   = s.get("max_dd", 0)
    trades   = s.get("trades", 0)
    win_rate = s.get("win_rate", 0)
    pf       = s.get("pf", 0)
    final    = s.get("final", INITIAL_CAPITAL)

    # Acceptance criteria from Phase 1 plan
    accept = (
        (year == 2018 and cagr > 0   and abs(max_dd) < 8)  or
        (year == 2020 and cagr > 6   and abs(max_dd) < 10) or
        (year == 2022 and cagr > 10  and abs(max_dd) < 10) or
        (year == 2024 and cagr > 8   and abs(max_dd) < 8)
    )
    acceptance.append(accept)
    status = "PASS" if accept else "FAIL"

    print(f"  {year:<6} {labels[year]:<24} {cagr:>6.1f}% {max_dd:>6.1f}% {trades:>7} "
          f"{win_rate:>7.1f}% {pf:>6.3f} ${final:>11,.0f}  [{status}]")

print("  " + "-"*84)
overall = "ALL PASS - Proceed to Phase 2" if all(acceptance) else "REVIEW FAILURES before Phase 2"
print(f"  Overall: {overall}")
print()

# ── Write detailed trade log ───────────────────────────────────────────────────
with open(output_file, "w", encoding="utf-8") as f:
    f.write("# HILO-IV Phase 1 Validation — Detailed Trade Log\n\n")
    f.write("**Phase 1 Changes Applied:**\n")
    f.write("- Bug Fix: Cash accounting double-count corrected in backtest_engine.py\n")
    f.write("- Sizing: `max_risk_per_trade_pct` 2.5% → 4.0% (below quarter-Kelly)\n")
    f.write("- Exit: `time_exit_dte` 7 → 21 DTE forced close\n")
    f.write("- Income: SGOV cash sweep @ 4.5% annualized on idle cash\n\n")
    f.write("> **Note:** All fills at mid-price. Real execution will see 10–20% haircut from bid/ask spreads.\n\n")
    f.write("---\n\n")

    for year in years:
        s, df = all_results[year]
        cagr     = s.get("cagr", 0)
        max_dd   = s.get("max_dd", 0)
        trades   = s.get("trades", 0)
        win_rate = s.get("win_rate", 0)
        pf       = s.get("pf", 0)
        final    = s.get("final", INITIAL_CAPITAL)

        accept = (
            (year == 2018 and cagr > 0   and abs(max_dd) < 8)  or
            (year == 2020 and cagr > 6   and abs(max_dd) < 10) or
            (year == 2022 and cagr > 10  and abs(max_dd) < 10) or
            (year == 2024 and cagr > 8   and abs(max_dd) < 8)
        )

        f.write(f"## {year} — {labels[year]}\n\n")
        f.write(f"**Phase 1 Status:** {'✅ PASS' if accept else '❌ FAIL'}\n\n")
        f.write("| Metric | Value |\n| :--- | :--- |\n")
        f.write(f"| CAGR | {cagr:.1f}% |\n")
        f.write(f"| Max Drawdown | {max_dd:.1f}% |\n")
        f.write(f"| Final NAV | ${final:,.0f} |\n")
        f.write(f"| Total Trades | {trades} |\n")
        f.write(f"| Win Rate | {win_rate:.1f}% |\n")
        f.write(f"| Profit Factor | {pf:.3f} |\n")

        if not df.empty:
            avg_dte  = df["DTE"].mean()
            avg_hold = df["held_days"].mean()
            exit_counts = df["exit_reason"].value_counts()
            f.write(f"| Avg DTE at Entry | {avg_dte:.0f} days |\n")
            f.write(f"| Avg Holding Period | {avg_hold:.1f} days |\n\n")

            f.write("**Exit Reasons:**\n\n| Reason | Count | % |\n| :--- | :--- | :--- |\n")
            for reason, count in exit_counts.items():
                f.write(f"| {reason} | {count} | {count/len(df)*100:.1f}% |\n")
            f.write("\n")

            f.write(f"### All {len(df)} Trades\n\n")
            f.write("| # | Entry | Exit | Held | Symbol | Type | Strike | DTE | Qty | Credit | Debit | PnL | Exit Reason |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            for idx, row in df.iterrows():
                pnl_val = row["pnl"]
                pnl_str = f"+${pnl_val:,.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):,.2f}"
                f.write(
                    f"| {idx+1} "
                    f"| {row['entry_date'].strftime('%Y-%m-%d')} "
                    f"| {row['exit_date'].strftime('%Y-%m-%d')} "
                    f"| {row['held_days']} "
                    f"| {row['symbol']} "
                    f"| {row['option_type']} "
                    f"| ${row['strike']:.2f} "
                    f"| {row['DTE']} "
                    f"| {int(row['contracts'])} "
                    f"| ${row['entry_premium']:.2f} "
                    f"| ${row['exit_premium']:.2f} "
                    f"| {pnl_str} "
                    f"| {row['exit_reason']} |\n"
                )
        else:
            f.write("\n*No trade data available for this year.*\n")

        f.write("\n---\n\n")

print(f"Detailed trade log -> {output_file}")
