import math
from typing import Dict, List
from .portfolio import SimPortfolio

def calculate_delta_orders(
    target_matrix: Dict[str, float],
    current_net_liq: float,
    current_positions: Dict[str, int],
    live_prices: Dict[str, float]
) -> List[Dict]:
    """
    Exact mirror of production src/tqqq_turbocore/executor.py calculate_delta_orders.
    Returns integer shares to align portfolio with target matrix.
    """
    orders = []
    
    for symbol, target_pct in target_matrix.items():
        if symbol == 'SGOV' and target_pct > 0.99:
            target_pct = 1.0  # Force 100% allocation if intended
            
        if symbol not in live_prices:
            continue
            
        live_price = live_prices[symbol]
        current_shares = current_positions.get(symbol, 0)
        
        target_dollar_value = current_net_liq * target_pct
        target_shares = math.floor(target_dollar_value / live_price)
        delta_shares = target_shares - current_shares
        
        if delta_shares < 0:
            orders.append({
                "action": "SELL",
                "symbol": symbol,
                "quantity": abs(delta_shares)
            })
        elif delta_shares > 0:
            orders.append({
                "action": "BUY",
                "symbol": symbol,
                "quantity": delta_shares
            })

    # Liquidate positions not in target matrix
    for symbol, current_shares in current_positions.items():
        if symbol not in target_matrix and current_shares > 0:
            if symbol in live_prices:
                orders.append({
                    "action": "SELL",
                    "symbol": symbol,
                    "quantity": current_shares
                })

    # Sort: SELLs first, then BUYs
    return sorted(orders, key=lambda o: 1 if o['action'] == 'BUY' else 0)

def execute_rebalance(
    portfolio: SimPortfolio,
    target_alloc: Dict[str, float],
    live_prices: Dict[str, float],
    date_str: str,
    slippage_pct: float = 0.001
):
    """Calculate and apply delta orders to the virtual portfolio."""
    # Production handles LEAPS separately from equity allocator
    equity_alloc = {k: v for k, v in target_alloc.items() if not k.endswith('LEAPS')}
    leaps_alloc = {k: v for k, v in target_alloc.items() if k.endswith('LEAPS')}
    
    # We pass 0.0 for leaps_bs_price here because we deal with LEAPS explicitly later
    # But we need the LEAPS value to correctly size equity allocations out of total account value.
    # In this simulation, we'll track 'Cash + Equity' for the delta executor, 
    # since LEAPS are usually long-hold (365 DTE) and we don't delta-hedge them daily.
    
    # 1. Handle LEAPS first. If we need QQQ_LEAPS and don't have it, buy dynamically based on allocation.
    if 'QQQ_LEAPS' in leaps_alloc and leaps_alloc['QQQ_LEAPS'] > 0:
        if 'QQQ' not in portfolio.options:
            if 'QQQ_LEAPS' in live_prices:
                opt_price = live_prices['QQQ_LEAPS']
                strike = live_prices.get('QQQ', 400.0) 
                
                # Dynamic sizing
                target_pct = leaps_alloc['QQQ_LEAPS']
                total_nav = portfolio.cash + sum(portfolio.positions.get(s, 0) * live_prices.get(s, 0) for s in portfolio.positions)
                target_dollar = total_nav * target_pct
                contract_cost = opt_price * 100.0
                contracts = math.floor(target_dollar / contract_cost)
                
                if contracts >= 1:
                    portfolio.apply_leaps_order("BUY_TO_OPEN", "QQQ", contracts, opt_price, strike, 365, date_str)
                    print(f"[{date_str}] BUY TO OPEN {contracts} QQQ LEAPS Call(s) @ ${opt_price:.2f} (Target=${target_dollar:,.0f})")
    else:
        if 'QQQ' in portfolio.options:
            if 'QQQ_LEAPS' in live_prices:
                opt_price = live_prices['QQQ_LEAPS']
                contracts = portfolio.options['QQQ']['qty']
                portfolio.apply_leaps_order("SELL_TO_CLOSE", "QQQ", contracts, opt_price, 0, 0, date_str)
                print(f"[{date_str}] SELL TO CLOSE {contracts} QQQ LEAPS Call(s) @ ${opt_price:.2f}")

    # 2. Rebalance Equities
    current_eq_liq = portfolio.cash + sum(portfolio.positions.get(s, 0) * live_prices.get(s, 0) for s in portfolio.positions)
    
    orders = calculate_delta_orders(equity_alloc, current_eq_liq, portfolio.positions, live_prices)
    
    for order in orders:
        sym = order['symbol']
        qty = order['quantity']
        base_price = live_prices[sym]
        
        # Apply Slippage
        if order['action'] == 'BUY':
            fill_price = base_price * (1 + slippage_pct)
            # Prevent margin call due to slippage by rounding quantity down if necessary
            if fill_price * qty > portfolio.cash:
                qty = math.floor(portfolio.cash / fill_price)
                if qty <= 0: continue
            portfolio.apply_order("BUY", sym, qty, fill_price, date_str)
        else:
            fill_price = base_price * (1 - slippage_pct)
            portfolio.apply_order("SELL", sym, qty, fill_price, date_str)
