import os
import pandas as pd
from src.turbobounce.options_pricer_backtest import run_backtest

def run_multiyear(start_year, end_year, initial_capital, accumulate=True):
    print(f"\n========================================================")
    print(f"  STARTING MULTI-YEAR BACKTEST: ${initial_capital:,.2f} INITIAL")
    print(f"========================================================")
    
    results = []
    all_trades = []
    current_capital = initial_capital
    
    for year in range(start_year, end_year):
        start_date = f"{year}-01-01"
        end_date = f"{year+1}-01-01"
        
        print(f"\nRunning {start_date} to {end_date} with ${current_capital:,.2f}...")
        try:
            year_data, df_log = run_backtest(start_date=start_date, end_date=end_date, initial_capital=current_capital)
            
            if len(df_log) > 0:
                all_trades.append(df_log)
                
            # Format to row
            results.append({
                'Year': year,
                'Start Capital $': round(current_capital, 2),
                'Total Trades': year_data['total_trades'],
                'Wins': year_data['wins'],
                'Losses': year_data['losses'],
                'Win Rate %': round(year_data['win_rate'] * 100, 1),
                'Avg Win $': round(year_data['avg_win'], 2),
                'Avg Loss $': round(year_data['avg_loss'], 2),
                'TQQQ Trades': year_data['tqqq_trades'],
                'TQQQ PnL $': round(year_data['tqqq_pnl'], 2),
                'Net PnL $': round(year_data['total_pnl'], 2),
                'End Capital $': round(year_data['final_capital'], 2),
                'Return %': round(year_data['return_pct'], 2),
            })
            
            if accumulate:
                current_capital = year_data['final_capital']
                
        except Exception as e:
            print(f"Error running {year}: {e}")
            import traceback
            traceback.print_exc()
            
    # Save yearly summary to DataFrame
    df = pd.DataFrame(results)
    
    # Process exhaustive trade log
    max_drawdown_pct = 0.0
    if all_trades:
        full_log = pd.concat(all_trades, ignore_index=True)
        csv_filename = f"turbobounce_options_{initial_capital // 1000}k_all_trades.csv"
        full_log.to_csv(csv_filename, index=False)
        print(f"\nExhaustive Trade Log saved to: {csv_filename}")
        
    # Calculate totals
    total_trades = df['Total Trades'].sum()
    total_pnl = current_capital - initial_capital
    avg_win_rate = df['Win Rate %'].mean()
    total_return = (total_pnl / initial_capital) * 100
    
    # Create final report string
    comp_str = "Compounding (Accumulated)" if accumulate else "Non-Compounding (Resetting)"
    report = f"TURBOBOUNCE OPTIONS BACKTEST - ${initial_capital:,.2f} INITIAL CAPITAL\n"
    report += f"Years: {start_year} to {end_year} ({comp_str})\n"
    report += f"Strategy: NAKED_LONG (Deep ITM LEAPS), DIAGONAL (PMCC), CREDIT_SPREAD\n\n"
    
    report += df.to_string(index=False)
    
    report += f"\n\n--- 6-YEAR AGGREGATE SUMMARY ---\n"
    report += f"Starting Capital      : ${initial_capital:,.2f}\n"
    report += f"Ending Capital        : ${current_capital:,.2f}\n"
    report += f"Total Trades (6 yrs)  : {total_trades}\n"
    report += f"Average Win Rate      : {avg_win_rate:.1f}%\n"
    report += f"Cumulative Net PnL    : ${total_pnl:,.2f}\n"
    report += f"Total Return on Base  : {total_return:+.1f}%\n"
    
    report_filename = f"turbobounce_options_{initial_capital // 1000}k_accumulated_report.txt"
    with open(report_filename, 'w') as f:
        f.write(report)
        
    print(f"Summary Report saved to: {report_filename}")
    return report

if __name__ == "__main__":
    # The user requested to just test one year to save time (2025-2026) with $15,000 capital
    report_25k = run_multiyear(2025, 2026, 15000, accumulate=True)
    
    print("\nALL BACKTESTS COMPLETE.")
