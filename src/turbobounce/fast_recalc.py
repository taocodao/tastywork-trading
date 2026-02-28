import pandas as pd

def process_reports(filename, initial_capital):
    df = pd.read_csv(filename)
    # Parse dates
    df['Exit Date'] = pd.to_datetime(df['Exit Date'])
    df['Year'] = df['Exit Date'].dt.year
    
    current_capital = initial_capital
    results = []
    
    for year in sorted(df['Year'].unique()):
        year_trades = df[df['Year'] == year]
        
        wins = len(year_trades[year_trades['PnL $'] > 0])
        losses = len(year_trades[year_trades['PnL $'] <= 0])
        total = len(year_trades)
        net_pnl = year_trades['PnL $'].sum()
        
        # The trades already have their exact PnL, we just add it to the running total
        end_capital = current_capital + net_pnl
        
        results.append({
            'Year': year,
            'Start Capital $': round(current_capital, 2),
            'Total Trades': total,
            'Wins': wins,
            'Losses': losses,
            'Win Rate %': round((wins / total) * 100, 1) if total > 0 else 0,
            'Avg Win $': round(year_trades[year_trades['PnL $'] > 0]['PnL $'].mean(), 2) if wins > 0 else 0,
            'Avg Loss $': round(year_trades[year_trades['PnL $'] <= 0]['PnL $'].mean(), 2) if losses > 0 else 0,
            'Net PnL $': round(net_pnl, 2),
            'End Capital $': round(end_capital, 2),
            'Return %': round((net_pnl / current_capital) * 100, 2)
        })
        
        current_capital = end_capital
        
    res_df = pd.DataFrame(results)
    print(f"\n--- FAST RECALCULATION: ${initial_capital:,.2f} ---")
    print(res_df.to_string(index=False))
    
    total_return = ((current_capital - initial_capital) / initial_capital) * 100
    print(f"\nFINAL CUMULATIVE RETURN: {total_return:+.1f}% | ENDING BALANCE: ${current_capital:,.2f}\n")

process_reports('turbobounce_options_5k_all_trades.csv', 5000)
process_reports('turbobounce_options_20k_all_trades.csv', 20000)
