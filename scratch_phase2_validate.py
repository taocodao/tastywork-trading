"""
Phase 2 Validation Backtest
Runs 4-year isolated backtests with Phase 1 + Phase 2 changes applied:
  Phase 1: Bug fix, 4% sizing, 21-DTE exit, SGOV sweep
  Phase 2: Pathway B (VIX >= 18 conditional entry), RSI sort priority,
            pathway-aware slot tracking (5 Pathway A + 3 Pathway B)
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
output_file = "HILO-IV Seller/Phase2_Validation_Trades.md"


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

    summary = {}
    for line in all_output.split("\n"):
        line = line.strip()
        if "Final Value" in line:
            try: summary["final"] = float(line.split("$")[1].replace(",",""))
            except: pass
        elif "CAGR" in line and "%" in line and "Total" not in line:
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

    try:
        df = pd.read_csv("backtest_otm_naked_trades.csv")
        df["entry_date"]  = pd.to_datetime(df["entry_date"])
        df["expiry_date"] = pd.to_datetime(df["expiry_date"])
        df["exit_date"]   = pd.to_datetime(df["exit_date"])
        df["DTE"]        = (df["expiry_date"] - df["entry_date"]).dt.days
        df["held_days"]  = (df["exit_date"]   - df["entry_date"]).dt.days
    except Exception as e:
        print(f"    Warning: {e}")
        df = pd.DataFrame()

    return summary, df


# ── Phase 1 baseline for comparison ───────────────────────────────────────────
phase1_cagr = {2018: 3.2, 2020: 8.8, 2022: 16.9, 2024: 14.4}

# ── Run all years ──────────────────────────────────────────────────────────────
print("\n" + "="*72)
print("  HILO-IV Phase 2 Validation Backtest")
print("  Phase 1 + Pathway B (VIX>=18 conditional entry)")
print("="*72)

all_results = {}
for year in years:
    summary, df = run_year(year)
    all_results[year] = (summary, df)

# ── Print comparison table ─────────────────────────────────────────────────────
print()
print(f"  {'Year':<6} {'Market':<24} {'P1 CAGR':>8} {'P2 CAGR':>8} {'Delta':>7} {'MaxDD':>7} {'Trades':>7} {'A/B Split':>10}")
print("  " + "-"*88)

acceptance = []
for year in years:
    s, df = all_results[year]
    cagr     = s.get("cagr", 0)
    max_dd   = s.get("max_dd", 0)
    trades   = s.get("trades", 0)
    p1_cagr  = phase1_cagr.get(year, 0)
    delta    = cagr - p1_cagr

    # Pathway A/B breakdown
    if not df.empty and "pathway" in df.columns:
        a_trades = (df["pathway"] == "A").sum()
        b_trades = (df["pathway"] == "B").sum()
        ab_str   = f"{a_trades}A/{b_trades}B"
    else:
        ab_str = "N/A"

    # Phase 2 acceptance criteria
    accept = (
        (year == 2018 and cagr > 3   and abs(max_dd) < 10) or
        (year == 2020 and cagr > 10  and abs(max_dd) < 12) or
        (year == 2022 and cagr > 15  and abs(max_dd) < 12) or
        (year == 2024 and cagr > 12  and abs(max_dd) < 10)
    )
    acceptance.append(accept)
    status  = "PASS" if accept else "FAIL"
    delta_s = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"

    print(f"  {year:<6} {labels[year]:<24} {p1_cagr:>7.1f}% {cagr:>7.1f}% {delta_s:>7} "
          f"{max_dd:>6.1f}% {trades:>7} {ab_str:>10}  [{status}]")

print("  " + "-"*88)
overall = "ALL PASS - Proceed to Phase 3 or Live Paper" if all(acceptance) else "REVIEW FAILURES"
print(f"  Overall: {overall}")
print()

# Pathway B win rate analysis
print("  Pathway B (VIX-conditional) Performance:")
print(f"  {'Year':<6} {'B Trades':>9} {'B Win Rate':>11} {'B Avg PnL':>10} {'B Total PnL':>12}")
print("  " + "-"*52)
for year in years:
    s, df = all_results[year]
    if not df.empty and "pathway" in df.columns:
        b_df = df[df["pathway"] == "B"]
        if len(b_df) > 0:
            b_win  = b_df["trade_won"].mean() * 100
            b_avg  = b_df["pnl"].mean()
            b_tot  = b_df["pnl"].sum()
            print(f"  {year:<6} {len(b_df):>9} {b_win:>10.1f}% {b_avg:>10.2f} {b_tot:>12.2f}")
        else:
            print(f"  {year:<6} {'0':>9} {'N/A':>11} {'N/A':>10} {'N/A':>12}")
    else:
        print(f"  {year:<6} {'N/A':>9}")
print()

# ── Write detailed trade log ───────────────────────────────────────────────────
with open(output_file, "w", encoding="utf-8") as f:
    f.write("# HILO-IV Phase 2 Validation -- Detailed Trade Log\n\n")
    f.write("**Phase 2 Changes Applied (on top of Phase 1):**\n")
    f.write("- Pathway B: VIX >= 18 + IV Rank >= 35% + RSI < 30/> 70 conditional entry\n")
    f.write("- Separate slot pool: max 3 concurrent Pathway B positions\n")
    f.write("- RSI sort priority: RSI < 30 puts / RSI > 70 calls get +0.5 sort bonus\n")
    f.write("- Pathway B size multiplier: 80% of normal sizing\n")
    f.write("- Pathway tag exported to trade log (A/B column)\n\n")
    f.write("---\n\n")

    for year in years:
        s, df = all_results[year]
        cagr     = s.get("cagr", 0)
        max_dd   = s.get("max_dd", 0)
        trades   = s.get("trades", 0)
        win_rate = s.get("win_rate", 0)
        pf       = s.get("pf", 0)
        final    = s.get("final", INITIAL_CAPITAL)
        p1_cagr  = phase1_cagr.get(year, 0)

        a_trades = (df["pathway"] == "A").sum() if (not df.empty and "pathway" in df.columns) else 0
        b_trades = (df["pathway"] == "B").sum() if (not df.empty and "pathway" in df.columns) else 0

        accept = (
            (year == 2018 and cagr > 3   and abs(max_dd) < 10) or
            (year == 2020 and cagr > 10  and abs(max_dd) < 12) or
            (year == 2022 and cagr > 15  and abs(max_dd) < 12) or
            (year == 2024 and cagr > 12  and abs(max_dd) < 10)
        )

        f.write(f"## {year} -- {labels.get(year, '')}\n\n")
        f.write(f"**Phase 2 Status:** {'PASS' if accept else 'FAIL'} "
                f"| Phase 1 CAGR: {p1_cagr:.1f}% -> Phase 2 CAGR: {cagr:.1f}% "
                f"({'+'if cagr>p1_cagr else ''}{cagr-p1_cagr:.1f}%)\n\n")
        f.write("| Metric | Value |\n| :--- | :--- |\n")
        f.write(f"| CAGR | {cagr:.1f}% |\n")
        f.write(f"| Max Drawdown | {max_dd:.1f}% |\n")
        f.write(f"| Final NAV | ${final:,.0f} |\n")
        f.write(f"| Total Trades | {trades} ({a_trades} Pathway A + {b_trades} Pathway B) |\n")
        f.write(f"| Win Rate | {win_rate:.1f}% |\n")
        f.write(f"| Profit Factor | {pf:.3f} |\n")

        if not df.empty:
            avg_dte  = df["DTE"].mean()
            avg_hold = df["held_days"].mean()
            f.write(f"| Avg DTE at Entry | {avg_dte:.0f} days |\n")
            f.write(f"| Avg Holding Period | {avg_hold:.1f} days |\n\n")

            if "pathway" in df.columns:
                b_df = df[df["pathway"] == "B"]
                if len(b_df) > 0:
                    f.write(f"**Pathway B Stats:** {len(b_df)} trades | "
                            f"Win rate: {b_df['trade_won'].mean()*100:.1f}% | "
                            f"Total PnL: ${b_df['pnl'].sum():,.2f}\n\n")

            exit_counts = df["exit_reason"].value_counts()
            f.write("**Exit Reasons:**\n\n| Reason | Count | % |\n| :--- | :--- | :--- |\n")
            for reason, count in exit_counts.items():
                f.write(f"| {reason} | {count} | {count/len(df)*100:.1f}% |\n")
            f.write("\n")

            f.write(f"### All {len(df)} Trades\n\n")
            has_pathway = "pathway" in df.columns
            header = "| # | Entry | Exit | Held | Symbol | Type | Strike | DTE | Qty | Credit | Debit | PnL | Path | Exit Reason |\n"
            sep    = "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f.write(header)
            f.write(sep)
            for idx, row in df.iterrows():
                pnl_val = row["pnl"]
                pnl_str = f"+${pnl_val:,.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):,.2f}"
                pw  = row.get("pathway", "A") if has_pathway else "A"
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
                    f"| {pw} "
                    f"| {row['exit_reason']} |\n"
                )
        f.write("\n---\n\n")

print(f"Detailed trade log -> {output_file}")
