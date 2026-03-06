import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

def execute_turbobounce_trade(signal: Dict[str, Any], session, account, account_number: Optional[str] = None) -> Dict[str, Any]:
    """
    Unified execution logic for TurboBounce signals.
    Supports multi-leg spreads with live pricing from IB.
    """
    from tastytrade.order import NewOrder, OrderLeg, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    
    symbol = signal.get('symbol', 'UNKNOWN')
    strategy_type = signal.get('type', 'BULL_PUT_SPREAD')
    legs = signal.get('legs', [])
    
    if not legs:
        raise ValueError(f"No legs found in signal for {symbol}")
        
    logger.info(f"🚀 Executing TurboBounce {strategy_type} for {symbol} ({len(legs)} legs)")
    
    # Pricing logic: Try IB first
    net_price = 0.0
    try:
        from ib_data_provider import IBDataProvider
        ib = IBDataProvider()
        
        leg_prices = []
        for leg in legs:
            occ_symbol = leg['symbol'].strip()
            # ib_data_provider.get_option_quote returns {bid, ask, mid}
            quote = ib.get_option_quote(occ_symbol)
            if quote and 'mid' in quote:
                leg_prices.append(quote['mid'])
                logger.info(f"   Live quote for {occ_symbol}: {quote['mid']}")
            else:
                logger.warning(f"   Could not get live quote for {occ_symbol}")
        
        if len(leg_prices) == len(legs):
            # For a 2-leg spread like Bull Put: Net = Short - Long
            # We assume legs[0] is short, legs[1] is long for vertical spreads
            # More generally: sum(price * -1 if action indicates selling)
            net_price = 0.0
            for i, leg in enumerate(legs):
                action = leg['action'].upper()
                if 'SELL' in action:
                    net_price += leg_prices[i]
                else:
                    net_price -= leg_prices[i]
            
            logger.info(f"   Using live IB pricing for {symbol} spread: {net_price:.2f}")
        else:
            # Fallback to signal provided cost
            net_price = abs(float(signal.get('cost', 1.0)))
            logger.warning(f"   Falling back to signal cost for {symbol}: {net_price}")
    except Exception as e:
        logger.error(f"   Error fetching live prices: {e}")
        net_price = abs(float(signal.get('cost', 1.0)))
        
    # Construct Tastytrade legs
    tt_legs = []
    for leg in legs:
        action = OrderAction.SELL_TO_OPEN if 'SELL' in leg['action'].upper() else OrderAction.BUY_TO_OPEN
        tt_legs.append(
            OrderLeg(
                instrument_type='Equity Option',
                symbol=leg['symbol'].strip(),
                quantity=leg.get('quantity', 1),
                action=action
            )
        )
        
    # Build order
    price_effect = PriceEffect.CREDIT if net_price >= 0 else PriceEffect.DEBIT
    
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=tt_legs,
        price=abs(net_price),
        price_effect=price_effect
    )
    
    # Place order
    logger.info(f"   Placing {price_effect.value} order @ ${abs(net_price):.2f}")
    result = account.place_order(session, order, dry_run=False)
    order_id = str(result.order.id) if hasattr(result, 'order') else "unknown"
    
    return {
        "status": "success",
        "order_id": order_id,
        "symbol": symbol,
        "strategy": "turbobounce",
        "type": strategy_type,
        "net_price": net_price,
        "price_effect": price_effect.value,
        "timestamp": datetime.now().isoformat()
    }
