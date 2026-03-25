"""
Delta Calculation Engine for the Two-Tier Subscription Model.
Translates universal target percentages into personalized, concrete integer-share orders.
"""
import math
from typing import Dict, List

# Only rebalance if a position drifts more than this fraction of net_liq.
# Prevents daily micro-churn from normal price movements, which is especially
# costly for LEAPS with wide bid-ask spreads.
REBALANCE_DRIFT_THRESHOLD = 0.05

def calculate_delta_orders(
    target_matrix: Dict[str, float],
    current_net_liq: float,
    current_positions: Dict[str, int],
    live_prices: Dict[str, float],
    drift_threshold: float = REBALANCE_DRIFT_THRESHOLD,
    fractional_shares: bool = False,
) -> List[Dict]:
    """
    Calculates the exact shares to buy or sell to align the portfolio with the target matrix.
    
    Args:
        target_matrix: e.g. {"TQQQ": 0.8, "SGOV": 0.2, "QQQ": 0.0, "QLD": 0.0}
        current_net_liq: Total account value in dollars (e.g., 50000.0)
        current_positions: Current share counts for each symbol
        live_prices: Current market prices for each symbol
        drift_threshold: Minimum drift (as fraction of net_liq) before generating a trade.
                         Default 5% prevents daily micro-rebalancing from normal price movements.
        fractional_shares: If True, allows fractional share quantities (Tastytrade ETF mode).
                           If False (default), rounds down to whole integer shares (production mode).
        
    Returns:
        List of order dictionaries sorted with SELL orders first, then BUY orders.
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
        
        # 2. Calculate current dollar value
        current_dollar_value = current_shares * live_price
        
        # 3. Drift check: skip trade if within tolerance band.
        #    Full exits (target=0%) always proceed regardless of threshold.
        drift = abs(target_dollar_value - current_dollar_value)
        if target_pct > 0 and current_net_liq > 0 and drift / current_net_liq < drift_threshold:
            continue
        
        # 4. Convert to target shares — fractional or integer
        if fractional_shares:
            target_shares = target_dollar_value / live_price  # exact fractional
        else:
            target_shares = math.floor(target_dollar_value / live_price)  # integer only
        
        # 5. Calculate the delta
        delta_shares = target_shares - current_shares
        
        # 6. Generate the order if delta is non-zero
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

    # Liquidate any current positions NOT in the target matrix at all (Target = 0%).
    # Full exits always execute — no drift threshold applied.
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
                orders.append({
                    "action": "SELL",
                    "symbol": symbol,
                    "quantity": current_shares,
                    "estimated_price": 0.0
                })

    # Sequence Strategy: SELL orders MUST execute before BUY orders to free up Buying Power.
    orders.sort(key=lambda x: 0 if x["action"] == "SELL" else 1)
    
    return orders
