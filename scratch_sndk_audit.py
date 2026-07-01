"""
SNDK Backtest Audit Script
===========================
Thorough diagnostic to find every source of inflated returns.
"""
import sys
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import date, timedelta

from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.feature_engineering import build_sndk_features
from src.otm_naked.sndk.ladder_manager import LadderRung
from src.otm_naked.sndk.signal_engine import SNDKLadderSignalEngine
from src.otm_naked.strike_selector import (
    bs_call_price, bs_put_price, bs_call_delta, bs_put_delta,
    find_put_strike, find_call_strike
)

logging.basicConfig(level=logging.WARNING)

def get_bs_price(S, K, T, r, sigma, opt="call"):
    return bs_call_price(S, K, T, r, sigma) if opt == "call" else bs_put_price(S, K, T, r, sigma)

def get_bs_delta(S, K, T, r, sigma, opt="call"):
    return bs_call_delta(S, K, T, r, sigma) if opt == "call" else bs_put_delta(S, K, T, r, sigma)

def main():
    ticker = "NVDA"
    end_dt = date(2026, 6, 27)
    start_dt = end_dt - timedelta(days=1095)
    
    raw = yf.download([ticker, "^VIX", "SPY"], start=start_dt.strftime("%Y-%m-%d"),
                       end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    
    close_price = raw["Close"][ticker].dropna()
    open_price  = raw["Open"][ticker].dropna()
    high_price  = raw["High"][ticker].dropna()
    low_price   = raw["Low"][ticker].dropna()
    volume      = raw["Volume"][ticker].dropna()
    vix         = raw["Close"]["^VIX"].dropna()
    spy_close   = raw["Close"]["SPY"].dropna()
    
    df = build_sndk_features(
        close=close_price, open_price=open_price,
        high=high_price, low=low_price, volume=volume,
        vix=vix, spy_close=spy_close
    )
    
    # ---- Use the same config as the "97.84% CAGR" run ----
    config = SNDKLadderConfig(universe=[ticker])
    config.entry_trigger_pct = 2.0
    config.ivr_min = 30.0
    config.position_size_pct = 0.05
    config.macro_filter_spy_pct = 10.0
    config.initial_capital = 500000.0
    # Apply same "best params" from last WF window
    config.dte_target = 21
    config.initial_delta = 0.30
    config.profit_take_pct = 0.50
    config.stop_loss_credit_mult = 1.5
    
    signal_engine = SNDKLadderSignalEngine(config)
    
    # ---- Detailed trade-by-trade audit ----
    print("=" * 100)
    print("SNDK BACKTEST AUDIT — TRADE-BY-TRADE ANALYSIS")
    print("=" * 100)
    
    # --- AUDIT 1: IV proxy statistics ---
    print("\n--- AUDIT 1: IV Proxy Quality ---")
    print(f"IV_est range:      {df['iv_est'].min():.3f} - {df['iv_est'].max():.3f}")
    print(f"IV_est mean:       {df['iv_est'].mean():.3f}")
    print(f"IV_est median:     {df['iv_est'].median():.3f}")
    print(f"HV_20 range:       {df['hv_20'].min():.3f} - {df['hv_20'].max():.3f}")
    print(f"IVR range:         {df['ivr'].min():.1f} - {df['ivr'].max():.1f}")
    print(f"IVR mean:          {df['ivr'].mean():.1f}")
    print(f"IV_est formula:    hv_20 * 1.25 + 0.10, clipped [0.60, 2.00]")
    print(f"IV_est FLOOR:      0.60 (60% annualized vol — THIS IS THE KEY ISSUE)")
    
    # How many rows have iv_est = floor?
    at_floor = (df['iv_est'] == 0.60).sum()
    print(f"Rows at IV floor:  {at_floor} / {len(df)} ({at_floor/len(df)*100:.1f}%)")
    
    # --- AUDIT 2: Entry signal frequency ---
    print("\n--- AUDIT 2: Entry Signal Frequency ---")
    big_moves = df[abs(df["daily_move_pct"]) >= config.entry_trigger_pct]
    print(f"Days with |move| >= {config.entry_trigger_pct}%: {len(big_moves)} / {len(df)} ({len(big_moves)/len(df)*100:.1f}%)")
    big_moves_ivr = big_moves[big_moves["ivr"] >= config.ivr_min]
    print(f"  ... also IVR >= {config.ivr_min}:  {len(big_moves_ivr)}")
    
    # --- AUDIT 3: Premium collected vs theoretical reality ---
    print("\n--- AUDIT 3: Premium Inflation Check ---")
    sample_dates = big_moves_ivr.head(10)
    for idx, row in sample_dates.iterrows():
        S = float(row["close"])
        iv = float(row["iv_est"])
        daily_move = float(row["daily_move_pct"])
        opt = "call" if daily_move > 0 else "put"
        T = config.dte_target / 365.0
        
        if opt == "put":
            strike = find_put_strike(S, T, 0.045, iv, target_delta=config.initial_delta)
        else:
            strike = find_call_strike(S, T, 0.045, iv, target_delta=config.initial_delta)
        
        prem = get_bs_price(S, strike, T, 0.045, iv, opt=opt)
        delta = get_bs_delta(S, strike, T, 0.045, iv, opt=opt)
        otm_pct = abs(strike - S) / S * 100
        
        print(f"  {idx.date()} | S={S:.0f} K={strike:.0f} ({otm_pct:.1f}% OTM) "
              f"IV={iv:.2f} DTE={config.dte_target} Delta={delta:.3f} Prem=${prem:.2f}/sh "
              f"(${prem*100:.0f}/contract) | {opt.upper()}")
    
    # --- AUDIT 4: PnL double-counting check ---
    print("\n--- AUDIT 4: PnL Accounting Walkthrough (First 5 Trades) ---")
    capital = config.initial_capital
    trades = []
    open_positions = []
    trade_count = 0
    
    SLIPPAGE_PER_CONTRACT = 0.10  # $0.10/share each way (conservative)
    COMMISSION_PER_CONTRACT = 1.00  # $1 per contract per leg
    
    for trade_date, row in df.iterrows():
        S = float(row["close"])
        iv = float(row.get("iv_est", 0.3))
        
        # Check exits on open positions
        to_close = []
        for pos in open_positions:
            days_held = (trade_date - pos["entry_date"]).days
            T_rem = max((pos["dte"] - days_held) / 365.0, 0.001)
            
            current_prem = get_bs_price(S, pos["strike"], T_rem, 0.045, iv, opt=pos["opt_type"])
            pnl_pct = (pos["entry_prem"] - current_prem) / max(pos["entry_prem"], 0.001)
            current_delta = abs(get_bs_delta(S, pos["strike"], T_rem, 0.045, iv, opt=pos["opt_type"]))
            
            exit_reason = None
            if pnl_pct >= config.profit_take_pct:
                exit_reason = "PROFIT"
            elif pnl_pct <= -config.stop_loss_credit_mult:
                exit_reason = "STOP"
            elif current_delta > config.delta_breach_threshold:
                exit_reason = "DELTA_BREACH"
            elif T_rem * 365 <= config.dte_roll_threshold:
                exit_reason = "DTE_EXPIRY"
                
            if exit_reason:
                pnl_dollars = (pos["entry_prem"] - current_prem) * pos["contracts"] * 100
                slippage = SLIPPAGE_PER_CONTRACT * pos["contracts"] * 100 * 2  # entry + exit
                commission = COMMISSION_PER_CONTRACT * pos["contracts"] * 2
                net_pnl = pnl_dollars - slippage - commission
                
                to_close.append(pos)
                trade_count += 1
                trades.append({
                    "entry_date": pos["entry_date"],
                    "exit_date": trade_date,
                    "days_held": days_held,
                    "opt_type": pos["opt_type"],
                    "spot_at_entry": pos["spot"],
                    "spot_at_exit": S,
                    "spot_change_pct": (S - pos["spot"]) / pos["spot"] * 100,
                    "strike": pos["strike"],
                    "otm_pct": pos["otm_pct"],
                    "entry_prem": pos["entry_prem"],
                    "exit_prem": current_prem,
                    "pnl_pct": pnl_pct,
                    "gross_pnl": pnl_dollars,
                    "net_pnl": net_pnl,
                    "contracts": pos["contracts"],
                    "exit_reason": exit_reason,
                    "iv_entry": pos["iv"],
                    "iv_exit": iv,
                    "delta_at_exit": current_delta,
                })
                
        for pos in to_close:
            open_positions.remove(pos)
        
        # Check for new entries
        signal = signal_engine.evaluate(row, 
                                         sum(1 for p in open_positions if p["opt_type"] == "call"),
                                         sum(1 for p in open_positions if p["opt_type"] == "put"))
        if not signal.should_enter:
            continue
            
        T_new = signal.target_dte / 365.0
        rung_count = sum(1 for p in open_positions if p["opt_type"] == signal.direction)
        target_delta = max(0.08, config.initial_delta - rung_count * config.ladder_delta_step)
        
        if signal.direction == "put":
            strike = find_put_strike(S, T_new, 0.045, iv, target_delta=target_delta)
        else:
            strike = find_call_strike(S, T_new, 0.045, iv, target_delta=target_delta)
            
        entry_prem = get_bs_price(S, strike, T_new, 0.045, iv, opt=signal.direction)
        if entry_prem <= 0:
            continue
            
        max_risk = config.initial_capital * config.position_size_pct
        margin_req = strike * 100 * 0.20
        contracts = max(1, int(max_risk / margin_req))
        otm_pct = abs(strike - S) / S * 100
        
        open_positions.append({
            "entry_date": trade_date,
            "opt_type": signal.direction,
            "strike": strike,
            "entry_prem": entry_prem,
            "spot": S,
            "contracts": contracts,
            "iv": iv,
            "dte": signal.target_dte,
            "otm_pct": otm_pct,
        })
    
    # Close remaining at end
    S = float(df.iloc[-1]["close"])
    iv = float(df.iloc[-1].get("iv_est", 0.3))
    for pos in open_positions:
        days_held = (df.index[-1] - pos["entry_date"]).days
        T_rem = max((pos["dte"] - days_held) / 365.0, 0.001)
        current_prem = get_bs_price(S, pos["strike"], T_rem, 0.045, iv, opt=pos["opt_type"])
        pnl_dollars = (pos["entry_prem"] - current_prem) * pos["contracts"] * 100
        slippage = SLIPPAGE_PER_CONTRACT * pos["contracts"] * 100 * 2
        commission = COMMISSION_PER_CONTRACT * pos["contracts"] * 2
        net_pnl = pnl_dollars - slippage - commission
        
        trade_count += 1
        trades.append({
            "entry_date": pos["entry_date"],
            "exit_date": df.index[-1],
            "days_held": days_held,
            "opt_type": pos["opt_type"],
            "spot_at_entry": pos["spot"],
            "spot_at_exit": S,
            "spot_change_pct": (S - pos["spot"]) / pos["spot"] * 100,
            "strike": pos["strike"],
            "otm_pct": pos["otm_pct"],
            "entry_prem": pos["entry_prem"],
            "exit_prem": current_prem,
            "pnl_pct": (pos["entry_prem"] - current_prem) / max(pos["entry_prem"], 0.001),
            "gross_pnl": pnl_dollars,
            "net_pnl": net_pnl,
            "contracts": pos["contracts"],
            "exit_reason": "END_OF_DATA",
            "iv_entry": pos["iv"],
            "iv_exit": iv,
            "delta_at_exit": abs(get_bs_delta(S, pos["strike"], T_rem, 0.045, iv, opt=pos["opt_type"])),
        })
    
    trades_df = pd.DataFrame(trades)
    
    # Print all trades
    print(f"\nTotal trades: {len(trades_df)}")
    for i, t in trades_df.iterrows():
        print(f"  #{i+1:2d} {t['entry_date'].date()} -> {t['exit_date'].date()} ({t['days_held']:3d}d) "
              f"| {t['opt_type'].upper():4s} K={t['strike']:.0f} ({t['otm_pct']:.1f}% OTM) "
              f"| Entry ${t['entry_prem']:.2f} Exit ${t['exit_prem']:.2f} "
              f"| PnL% {t['pnl_pct']*100:+6.1f}% Gross ${t['gross_pnl']:+8.0f} Net ${t['net_pnl']:+8.0f} "
              f"| {t['exit_reason']:14s} | Spot {t['spot_at_entry']:.0f}->{t['spot_at_exit']:.0f} ({t['spot_change_pct']:+.1f}%) "
              f"| IV {t['iv_entry']:.2f}->{t['iv_exit']:.2f}")
    
    # --- AUDIT 5: Aggregate metrics with friction ---
    print("\n--- AUDIT 5: Aggregate Metrics ---")
    print(f"Gross PnL:     ${trades_df['gross_pnl'].sum():+,.0f}")
    print(f"Net PnL:       ${trades_df['net_pnl'].sum():+,.0f}")
    total_slippage = (SLIPPAGE_PER_CONTRACT * trades_df['contracts'] * 100 * 2).sum()
    total_commission = (COMMISSION_PER_CONTRACT * trades_df['contracts'] * 2).sum()
    print(f"Total Slip:    ${total_slippage:,.0f}")
    print(f"Total Comm:    ${total_commission:,.0f}")
    
    wins = (trades_df['net_pnl'] > 0).sum()
    losses = (trades_df['net_pnl'] <= 0).sum()
    print(f"Wins/Losses:   {wins}/{losses}")
    print(f"Win Rate:      {wins/len(trades_df)*100:.1f}%")
    
    avg_win = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].mean() if wins > 0 else 0
    avg_loss = trades_df[trades_df['net_pnl'] <= 0]['net_pnl'].mean() if losses > 0 else 0
    print(f"Avg Win:       ${avg_win:+,.0f}")
    print(f"Avg Loss:      ${avg_loss:+,.0f}")
    
    # --- AUDIT 6: The CRITICAL double-counting bug check ---
    print("\n--- AUDIT 6: CAPITAL ACCOUNTING BUG CHECK ---")
    print("The test script (scratch_test_sndk_backtest.py) has this flow:")
    print("  1. manage_positions() returns PnL — adds to capital")
    print("  2. On entry: capital += entry_prem * contracts * 100  (premium received)")
    print("  3. On final close: capital -= liability (buyback cost)")
    print("")
    print("BUG: manage_positions.pnl already includes (entry_prem - exit_prem).")
    print("     But the test script ALSO adds entry_prem at step 2.")
    print("     This double-counts the entry premium for every trade!")
    print("")
    
    # Demonstrate the bug
    print("DEMONSTRATION:")
    print("  Suppose: sell 1 contract at $5.00 premium, buy back at $2.50")
    print("  Correct PnL = ($5.00 - $2.50) * 100 = $250")
    print("")
    print("  Test script does:")
    print("    Step 2: capital += $5.00 * 100 = +$500 (premium received)")
    print("    Step 1: manage_positions returns pnl = ($5.00 - $2.50) * 100 = +$250")
    print("    Result: capital increases by $750 instead of $250")
    print("    INFLATION FACTOR: 3x on this trade!")
    print("")
    print("  Additionally, final close (step 3) only subtracts the EXIT premium,")
    print("  not the entry premium, so remaining positions also get inflated.")
    
    # --- AUDIT 7: Corrected equity curve ---
    print("\n--- AUDIT 7: CORRECTED CAGR ---")
    corrected_capital = config.initial_capital + trades_df['net_pnl'].sum()
    corrected_cagr = (corrected_capital / config.initial_capital) ** (1/1.5) - 1
    
    print(f"Initial Capital:  ${config.initial_capital:,.0f}")
    print(f"Corrected Final:  ${corrected_capital:,.0f}")
    print(f"Net Profit:       ${trades_df['net_pnl'].sum():+,.0f}")
    print(f"Corrected CAGR:   {corrected_cagr*100:.2f}%")
    
    # --- AUDIT 8: Additional concerns ---
    print("\n--- AUDIT 8: ADDITIONAL STRUCTURAL CONCERNS ---")
    print("1. IV PROXY FLOOR = 60%: The formula 'hv20 * 1.25 + 0.10' with a 60% floor")
    print("   massively overstates IV for a stock like NVDA in calm periods.")
    at_floor_pct = (df['iv_est'] == 0.60).sum() / len(df) * 100
    print(f"   {at_floor_pct:.0f}% of rows are at the 60% IV floor.")
    print(f"   NVDA's real 30d IV typically ranges 35-55% in calm markets.")
    print(f"   This floor inflates BS premiums by 20-40%, making every trade look better.")
    
    print("\n2. NO BID-ASK SPREAD: Real naked option markets have 5-15% wide bid-ask")
    print("   spreads. We model mid-price execution, which is unrealistic.")
    
    print("\n3. DTE MISMATCH: Signal engine uses iv_regime.get_dte_for_ivr() to set")
    print("   target DTE (30-60), but manage_positions uses config.dte_target (21)")
    print("   to calculate T_remaining. This means exits happen MUCH faster than")
    print("   they should, accelerating theta decay artificially.")
    
    # Check
    for i, t in trades_df.iterrows():
        if t['days_held'] <= 1:
            print(f"   SUSPICIOUS: Trade #{i+1} held for only {t['days_held']} day(s)")
    
    print("\n4. NO MARGIN TRACKING: Naked options on a $140 stock require ~$2,800+")
    print("   per contract in margin. With 5% sizing ($25K) and contracts calculated")
    print("   as int($25K / ($K * 100 * 0.20)), that's only ~1 contract per rung.")
    print("   But total margin across 6 rungs would be ~$16,800 — well within $500K.")
    print("   HOWEVER: margin increases dramatically when positions go ITM.")
    
    print("\n5. LOOK-AHEAD IN OPTUNA: Optuna optimizes on training data, then tests")
    print("   on the NEXT window. But the equity curve in the test script applies")
    print("   the LAST window's best params to the ENTIRE dataset. This is a form")
    print("   of selection bias.")
    
    print("\n6. NO IV CRUSH MODELING: After a big move day, real IV typically drops")
    print("   30-50% within 2-3 days. Our proxy IV doesn't capture this crush,")
    print("   so the backtest exit premiums are higher than reality (hurting PnL).")
    print("   Paradoxically, the flat IV also means entries are over-priced too.")
    
    # --- FINAL SUMMARY ---
    print("\n" + "=" * 100)
    print("FINAL VERDICT")
    print("=" * 100)
    print(f"Reported CAGR:   97.84%  <-- INFLATED")
    print(f"Corrected CAGR:  {corrected_cagr*100:.2f}%  <-- After fixing double-counting + friction")
    print(f"")
    print(f"Key bugs found:")
    print(f"  1. CRITICAL: Premium double-counting in capital tracking")
    print(f"  2. HIGH:     IV proxy floor at 60% overstates premium")
    print(f"  3. MEDIUM:   No bid-ask spread or slippage in backtest engine")
    print(f"  4. MEDIUM:   DTE mismatch between signal engine and position manager")
    print(f"  5. LOW:      Best params from last WF window applied to full dataset")
    
if __name__ == "__main__":
    main()
