"""
Delta Calculation Engine for the Two-Tier Subscription Model.
Translates universal target percentages into personalized, concrete integer-share orders.
"""
import math
from typing import Dict, List

def calculate_delta_orders(
    target_matrix: Dict[str, float],
    current_net_liq: float,
    current_positions: Dict[str, int],
    live_prices: Dict[str, float]
) -> List[Dict]:
    """
    Calculates the exact integer shares to buy or sell to align the portfolio with the target matrix.
    
    Args:
        target_matrix: e.g. {"TQQQ": 0.8, "SGOV": 0.2, "QQQ": 0.0, "QLD": 0.0}
        current_net_liq: Total account value in dollars (e.g., 50000.0)
        current_positions: Current share counts for each symbol, e.g. {"TQQQ": 100, "SGOV": 50}
        live_prices: Current market prices for each symbol, e.g. {"TQQQ": 45.50, "SGOV": 100.25}
        
    Returns:
        List of order dictionaries sorted with SELL orders first, then BUY orders.
        e.g. [{"action": "SELL", "symbol": "SGOV", "quantity": 10}, {"action": "BUY", "symbol": "TQQQ", "quantity": 15}]
    """
    orders = []
    
    # Process each symbol in the target matrix
    for symbol, target_pct in target_matrix.items():
        if symbol not in live_prices:
            raise ValueError(f"Missing live price for symbol: {symbol}")
            
        live_price = live_prices[symbol]
        current_shares = current_positions.get(symbol, 0)
        
        # 1. Calculate the target dollar value for this asset
        target_dollar_value = current_net_liq * target_pct
        
        # 2. Convert to target integer shares (always round down to prevent margin calls)
        target_shares = math.floor(target_dollar_value / live_price)
        
        # 3. Calculate the delta
        delta_shares = target_shares - current_shares
        
        # 4. Generate the order if delta is non-zero
        if delta_shares < 0:
            orders.append({
                "action": "SELL",
                "symbol": symbol,
                "quantity": abs(delta_shares),
                "estimated_price": live_price
            })
        elif delta_shares > 0:
            orders.append({
                "action": "BUY",
                "symbol": symbol,
                "quantity": delta_shares,
                "estimated_price": live_price
            })

    # Liquidate any current positions that are NOT in the target matrix at all (Target = 0%)
    for symbol, current_shares in current_positions.items():
        if symbol not in target_matrix and current_shares > 0:
            if symbol in live_prices:
                orders.append({
                    "action": "SELL",
                    "symbol": symbol,
                    "quantity": current_shares,
                    "estimated_price": live_prices[symbol]
                })
            else:
                # If we don't have a live price, we still want to sell it if possible, 
                # but for this engine we assume we need a price to estimate.
                # We'll generate a market sell or use 0.0 as placeholder.
                orders.append({
                    "action": "SELL",
                    "symbol": symbol,
                    "quantity": current_shares,
                    "estimated_price": 0.0
                })

    # Sequence Strategy: SELL orders MUST execute before BUY orders to free up Buying Power.
    # Sort orders: "SELL" comes before "BUY" alphabetically anyway, but let's be explicit and robust.
    orders.sort(key=lambda x: 0 if x["action"] == "SELL" else 1)
    
    return orders

