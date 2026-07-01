"""
Phase 3 Validation Backtest
Runs 4-year isolated backtests with Phase 1 + 2 + 3 changes:
  Phase 3a: Quarter Kelly sizing (5.5%)
  Phase 3b: Earnings IC Overlay (defined-risk, IV crush capture)
  Phase 3:  Drawdown kill-switch at 10% DD
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
output_file = "HILO-IV Seller/Phase3_Validation_Trades.md"

# Phase 2 baseline for comparison
phase2_cagr = {2018: 3.3, 2020: 8.5, 2022: 19.4, 2024: 13.9}
phase1_cagr = {2018: 3.2, 2020: 8.8, 2022: 16.9, 2024: 14.4}


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
            try: summary["final"] = float(line.split("$")[1].replace(",", ""))
            except: pass
        elif "CAGR" in line and "%" in line and "Total" not in line:
            try: summary["cagr"] = float(line.split(":")[1].strip().replace("%", ""))
            except: pass
        elif "Max Drawdown" in line:
            try: summary["max_dd"] = float(line.split(":")[1].strip().replace("%", ""))
            except: pass
        elif "Total Trades" in line:
            try: summary["trades"] = int(line.split(":")[1].strip())
            except: pass
        elif "Win Rate" in line:
            try: summary["win_rate"] = float(line.split(":")[1].strip().replace("%", ""))
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


# ── Run all years ──────────────────────────────────────────────────────────────
print("\n" + "="*72)
print("  HILO-IV Phase 3 Validation Backtest")
print("  Quarter Kelly (5.5%) + Earnings IC Overlay + Drawdown Kill-Switch")
print("="*72)

all_results = {}
for year in years:
    summary, df = run_year(year)
    all_results[year] = (summary, df)

# ── Comparison table ──────────────────────────────────────────────────────────
print()
print(f"  {'Year':<6} {'Market':<24} {'P1':>6} {'P2':>6} {'P3':>6} {'Delta':>7} {'MaxDD':>7} {'Trades':>7} {'Path A/B':>9}")
print("  " + "-"*90)

acceptance = []
for year in years:
    s, df   = all_results[year]
    cagr    = s.get("cagr", 0)
    max_dd  = s.get("max_dd", 0)
    trades  = s.get("trades", 0)
    p1      = phase1_cagr.get(year, 0)
    p2      = phase2_cagr.get(year, 0)
    delta   = cagr - p2

    ab_str = "N/A"
    if not df.empty and "pathway" in df.columns:
        a = (df["pathway"] == "A").sum()
        b = (df["pathway"] == "B").sum()
        ab_str = f"{a}A/{b}B"

    # Phase 3 acceptance criteria (tighter — quarter Kelly should deliver more)
    accept = (
        (year == 2018 and cagr > 3   and abs(max_dd) < 12) or
        (year == 2020 and cagr > 10  and abs(max_dd) < 12) or
        (year == 2022 and cagr > 18  and abs(max_dd) < 12) or
        (year == 2024 and cagr > 14  and abs(max_dd) < 10)
    )
    acceptance.append(accept)
    status  = "PASS" if accept else "FAIL"
    delta_s = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"

    print(f"  {year:<6} {labels[year]:<24} {p1:>5.1f}% {p2:>5.1f}% {cagr:>5.1f}% {delta_s:>7} "
          f"{max_dd:>6.1f}% {trades:>7} {ab_str:>9}  [{status}]")

print("  " + "-"*90)
overall = "ALL PASS" if all(acceptance) else "REVIEW FAILURES"
print(f"  Phase 3 Overall: {overall}")

# ── Pathway B breakdown ───────────────────────────────────────────────────────
print()
print("  Pathway B performance:")
print(f"  {'Year':<6} {'B Trades':>9} {'B WR':>7} {'B PnL':>10}")
print("  " + "-"*38)
for year in years:
    s, df = all_results[year]
    if not df.empty and "pathway" in df.columns:
        b = df[df["pathway"] == "B"]
        if len(b):
            print(f"  {year:<6} {len(b):>9} {b['trade_won'].mean()*100:>6.0f}% {b['pnl'].sum():>10.2f}")
        else:
            print(f"  {year:<6} {'0':>9} {'N/A':>7} {'N/A':>10}")

# ── Projected 4-year average ──────────────────────────────────────────────────
cagrs = [all_results[y][0].get("cagr", 0) for y in years]
dds   = [all_results[y][0].get("max_dd", 0) for y in years]
print(f"\n  4-Year Average CAGR: {sum(cagrs)/len(cagrs):.1f}%")
print(f"  Average Max DD:      {sum(dds)/len(dds):.1f}%")
print(f"  Target Range:        15-25% CAGR | <10% Max DD")
print()

# ── Write detailed report ─────────────────────────────────────────────────────
with open(output_file, "w", encoding="utf-8") as f:
    f.write("# HILO-IV Phase 3 Validation -- Full Strategy Results\n\n")
    f.write("**All Phases Active:**\n")
    f.write("- Phase 1: Bug fix, 4%->5.5% sizing, 21-DTE exit, SGOV sweep\n")
    f.write("- Phase 2: Pathway B (VIX>=16, IV Rank>=30%, RSI<35/65>)\n")
    f.write("- Phase 3a: Quarter Kelly sizing (5.5%)\n")
    f.write("- Phase 3b: Earnings IC Overlay (IV crush capture, defined-risk)\n")
    f.write("- Phase 3:  Drawdown kill-switch (10% DD -> revert to 2%)\n\n")
    f.write("---\n\n")

    for year in years:
        s, df = all_results[year]
        cagr    = s.get("cagr", 0)
        max_dd  = s.get("max_dd", 0)
        trades  = s.get("trades", 0)
        win_rate = s.get("win_rate", 0)
        pf      = s.get("pf", 0)
        final   = s.get("final", INITIAL_CAPITAL)
        p1      = phase1_cagr.get(year, 0)
        p2      = phase2_cagr.get(year, 0)

        accept = (
            (year == 2018 and cagr > 3   and abs(max_dd) < 12) or
            (year == 2020 and cagr > 10  and abs(max_dd) < 12) or
            (year == 2022 and cagr > 18  and abs(max_dd) < 12) or
            (year == 2024 and cagr > 14  and abs(max_dd) < 10)
        )

        a_t = (df["pathway"]=="A").sum() if (not df.empty and "pathway" in df.columns) else 0
        b_t = (df["pathway"]=="B").sum() if (not df.empty and "pathway" in df.columns) else 0

        f.write(f"## {year} -- {labels.get(year,'')}\n\n")
        f.write(f"**Phase 3 Status:** {'PASS' if accept else 'FAIL'}\n\n")
        f.write(f"| Phase | CAGR |\n| :--- | :--- |\n")
        f.write(f"| Phase 1 (Baseline corrected) | {p1:.1f}% |\n")
        f.write(f"| Phase 2 (+Pathway B) | {p2:.1f}% |\n")
        f.write(f"| **Phase 3 (Quarter Kelly + IC)** | **{cagr:.1f}%** |\n\n")
        f.write("| Metric | Value |\n| :--- | :--- |\n")
        f.write(f"| CAGR | {cagr:.1f}% |\n")
        f.write(f"| Max Drawdown | {max_dd:.1f}% |\n")
        f.write(f"| Final NAV | ${final:,.0f} |\n")
        f.write(f"| Total Trades | {trades} ({a_t}A + {b_t}B) |\n")
        f.write(f"| Win Rate | {win_rate:.1f}% |\n")
        f.write(f"| Profit Factor | {pf:.3f} |\n\n")

        if not df.empty:
            exit_counts = df["exit_reason"].value_counts()
            f.write("**Exit Reasons:**\n\n| Reason | Count | % |\n| :--- | :--- | :--- |\n")
            for reason, count in exit_counts.items():
                f.write(f"| {reason} | {count} | {count/len(df)*100:.1f}% |\n")
            f.write("\n")

            f.write(f"### All {len(df)} Core Trades\n\n")
            f.write("| # | Entry | Exit | Held | Symbol | Type | Strike | DTE | Qty | Credit | Debit | PnL | Path | Exit Reason |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            has_pathway = "pathway" in df.columns
            for idx, row in df.iterrows():
                pv = row["pnl"]
                ps = f"+${pv:,.2f}" if pv >= 0 else f"-${abs(pv):,.2f}"
                pw = row.get("pathway","A") if has_pathway else "A"
                f.write(
                    f"| {idx+1} | {row['entry_date'].strftime('%Y-%m-%d')} "
                    f"| {row['exit_date'].strftime('%Y-%m-%d')} "
                    f"| {row['held_days']} "
                    f"| {row['symbol']} | {row['option_type']} "
                    f"| ${row['strike']:.2f} | {row['DTE']} "
                    f"| {int(row['contracts'])} "
                    f"| ${row['entry_premium']:.2f} | ${row['exit_premium']:.2f} "
                    f"| {ps} | {pw} | {row['exit_reason']} |\n"
                )
        f.write("\n---\n\n")

    f.write("## 4-Year Summary\n\n")
    f.write("| Year | P1 CAGR | P2 CAGR | P3 CAGR | Max DD | Status |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for year in years:
        s, _ = all_results[year]
        cagr = s.get("cagr", 0)
        dd   = s.get("max_dd", 0)
        accept = (
            (year == 2018 and cagr > 3   and abs(dd) < 12) or
            (year == 2020 and cagr > 10  and abs(dd) < 12) or
            (year == 2022 and cagr > 18  and abs(dd) < 12) or
            (year == 2024 and cagr > 14  and abs(dd) < 10)
        )
        f.write(f"| {year} | {phase1_cagr[year]:.1f}% | {phase2_cagr[year]:.1f}% "
                f"| **{cagr:.1f}%** | {dd:.1f}% | {'PASS' if accept else 'FAIL'} |\n")
    avg_cagr = sum(all_results[y][0].get("cagr",0) for y in years) / len(years)
    f.write(f"| **Average** | **{sum(phase1_cagr.values())/4:.1f}%** "
            f"| **{sum(phase2_cagr.values())/4:.1f}%** | **{avg_cagr:.1f}%** | -- | -- |\n")

print(f"Report -> {output_file}")
