"""
Generate detailed trade logs for specific years (No Strangle).
Runs backtest_otm_naked.py per-year via --start/--end CLI args.
"""
import subprocess
import pandas as pd

years = [2018, 2020, 2022, 2024]
labels = {2018: "Volmageddon / Bear", 2020: "COVID Crash & V-Shape",
           2022: "Deep Bear / High IV", 2024: "Choppy Bull"}
output_file = "scratch_No_Strangle_Detailed_Trades.md"


def run_year(year):
    print(f"Running {year}...")
    result = subprocess.run(
        ["python", "backtest_otm_naked.py",
         "--start", f"{year}-01-01",
         "--end", f"{year}-12-31",
         "--capital", "50000",
         "--no-ml"],
        capture_output=True, text=True, cwd="."
    )

    # Extract summary block from stdout
    stdout = result.stdout + result.stderr  # logging goes to stderr
    lines = stdout.split('\n')
    summary_lines = []
    in_summary = False
    for line in lines:
        if "BACKTEST RESULTS" in line:
            in_summary = True
        if in_summary:
            summary_lines.append(line.strip())
            if "Avg Loss" in line:
                break

    # Also capture exit reasons and by-symbol blocks
    in_exit = False
    for line in lines:
        if "Exit Reasons:" in line:
            in_exit = True
        if in_exit:
            summary_lines.append(line.strip())
            if line.strip() == "" and in_exit:
                in_exit = False

    summary = "\n".join(summary_lines)

    # Read the trades CSV
    trades = pd.read_csv("backtest_otm_naked_trades.csv")
    return summary, trades


with open(output_file, "w", encoding="utf-8") as f:
    f.write("# HILO-IV Pure Put-Selling Strategy (No Strangle) — Detailed Trade Log\n\n")
    f.write("**Strategy:** 52W HILO + IV-Rank gated naked OTM options selling\n")
    f.write("**Capital:** $50,000 | **Quantity:** 1+ contracts (sized by notional risk)\n")
    f.write("**Strangles:** DISABLED — pure put/call selling only\n\n")
    f.write("> **Note on Real-World Execution:** All prices below are mid-price fills. "
            "In live trading, bid/ask spreads (typically $0.02–$0.10 on liquid options) "
            "will reduce net credits and increase net debits, lowering realized PnL by "
            "an estimated 10–20%. Commission is $0.65/contract (TastyTrade).\n\n")
    f.write("---\n\n")

for year in years:
    res = run_year(year)
    if not res:
        print(f"  FAILED for {year}")
        continue
    summary, df = res

    # Calculate DTE and holding period
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    df['expiry_date'] = pd.to_datetime(df['expiry_date'])
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    df['DTE'] = (df['expiry_date'] - df['entry_date']).dt.days
    df['held_days'] = (df['exit_date'] - df['entry_date']).dt.days

    # Year stats
    wins = df[df['trade_won'] == True]
    losses = df[df['trade_won'] == False]
    total_pnl = df['pnl'].sum()
    win_rate = len(wins) / len(df) * 100 if len(df) > 0 else 0

    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"## {year} — {labels.get(year, '')}\n\n")

        # Summary table
        f.write("| Metric | Value |\n")
        f.write("| :--- | :--- |\n")
        f.write(f"| Total Trades | {len(df)} |\n")
        f.write(f"| Winning Trades | {len(wins)} ({win_rate:.1f}%) |\n")
        f.write(f"| Losing Trades | {len(losses)} ({100 - win_rate:.1f}%) |\n")
        f.write(f"| Total PnL | ${total_pnl:,.2f} |\n")
        f.write(f"| Avg Win | ${wins['pnl'].mean():,.2f} |\n") if len(wins) > 0 else None
        f.write(f"| Avg Loss | ${losses['pnl'].mean():,.2f} |\n") if len(losses) > 0 else None
        f.write(f"| Avg DTE at Entry | {df['DTE'].mean():.0f} days |\n")
        f.write(f"| Avg Holding Period | {df['held_days'].mean():.1f} days |\n")
        f.write("\n")

        # Exit reason breakdown
        exit_counts = df['exit_reason'].value_counts()
        f.write("**Exit Reasons:**\n\n")
        f.write("| Reason | Count | % |\n")
        f.write("| :--- | :--- | :--- |\n")
        for reason, count in exit_counts.items():
            f.write(f"| {reason} | {count} | {count / len(df) * 100:.1f}% |\n")
        f.write("\n")

        # Full trade table
        f.write(f"### All {len(df)} Trades\n\n")
        f.write("| # | Entry Date | Exit Date | Days Held | Symbol | Type | Strike | DTE | Qty | Entry Credit | Exit Debit | Net PnL | Exit Reason |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")

        for idx, row in df.iterrows():
            trade_num = idx + 1
            entry_str = row['entry_date'].strftime('%Y-%m-%d')
            exit_str = row['exit_date'].strftime('%Y-%m-%d') if pd.notnull(row['exit_date']) else "OPEN"
            pnl_val = row['pnl']
            if pnl_val >= 0:
                pnl_str = f"+${pnl_val:,.2f}"
            else:
                pnl_str = f"-${abs(pnl_val):,.2f}"

            f.write(
                f"| {trade_num} "
                f"| {entry_str} "
                f"| {exit_str} "
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

        f.write("\n---\n\n")

    print(f"  {year}: {len(df)} trades, PnL=${total_pnl:,.2f}")

print(f"\nDone! Output: {output_file}")
