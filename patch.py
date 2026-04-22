import sys

with open('auto_approve.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch 1: Settings
old_settings = '''        "custom_overrides": {}
    },

    # DVO (Deep Value Overlay) settings
    "dvo": {'''

new_settings = '''        "custom_overrides": {}
    },

    # QQQ LEAPS Strategy settings
    "qqq_leaps": {
        "enabled": True,
        "risk_level": "MEDIUM",
        "risk_profiles": {
            "LOW": {
                "min_confidence": 0.60,
                "max_capital_per_trade": 3000,
                "max_contracts": 1
            },
            "MEDIUM": {
                "min_confidence": 0.45,
                "max_capital_per_trade": 8000,
                "max_contracts": 2
            },
            "HIGH": {
                "min_confidence": 0.40,
                "max_capital_per_trade": 20000,
                "max_contracts": 5
            }
        },
        "custom_overrides": {}
    },

    # DVO (Deep Value Overlay) settings
    "dvo": {'''

content = content.replace(old_settings, new_settings)

# Patch 2: strategy detection
old_strategy = '''    elif "turbobounce" in strategy:
        strategy_key = "turbobounce"
    elif "turbocore" in strategy:
        strategy_key = "turbocore"
    else:
        logger.debug(f"Auto-approve: Unknown strategy '{strategy}'")'''

new_strategy = '''    elif "turbobounce" in strategy:
        strategy_key = "turbobounce"
    elif "turbocore" in strategy:
        strategy_key = "turbocore"
    elif "qqq_leaps" in strategy or "leaps" in strategy:
        strategy_key = "qqq_leaps"
    else:
        logger.debug(f"Auto-approve: Unknown strategy '{strategy}'")'''

content = content.replace(old_strategy, new_strategy)

# Patch 3: routing
old_router = '''            else:
                # Standard TurboCore Pro equity rebalance
                result = _execute_turbocore_auto_approve(signal, session, account)
        else:
            result = _execute_calendar_auto_approve(signal, session, account)'''

new_router = '''            else:
                # Standard TurboCore Pro equity rebalance
                result = _execute_turbocore_auto_approve(signal, session, account)
        elif "qqq_leaps" in strategy.lower() or "leaps" in strategy.lower():
            result = _execute_qqq_leaps_auto_approve(signal, session, account)
        else:
            result = _execute_calendar_auto_approve(signal, session, account)'''

content = content.replace(old_router, new_router)

# Patch 4: Append the QQQ LEAPS executor function
new_func = '''
def _execute_qqq_leaps_auto_approve(signal: Dict, session, account) -> Optional[Dict[str, Any]]:
    \"\"\"
    Execute a QQQ LEAPS long call entry or exit on a real Tastytrade account.
    \"\"\"
    from tastytrade.order import NewOrder, OrderLeg, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    import tastytrade_utils
    from datetime import datetime

    action = signal.get("action", "ENTER").upper()
    strike = float(signal.get("strike", 0))
    expiry = signal.get("expiry", signal.get("expiry_date", ""))
    
    if strike == 0 or not expiry:
        logger.error("QQQ LEAPS signal missing required fields (strike/expiry)")
        return None
        
    exp_dt = expiry.replace("-", "")[2:]
    strike_fmt = f"{int(strike * 1000):08d}"
    occ_symbol = f"QQQ  {exp_dt}C{strike_fmt}"
    
    balance = tastytrade_utils.get_account_balance(session, account)
    net_liq = float(balance.get("netLiquidatingValue", 0))
    if net_liq <= 0:
        logger.error("Could not determine account NAV for LEAPS sizing")
        return None
        
    # Get live market price limit
    try:
        from ib_data_provider import IBDataProvider
        ib = IBDataProvider()
        quote = ib.get_option_price_by_symbol(occ_symbol.strip())
        if quote:
            if action == "ENTER":
                limit_price = round(quote[1], 2)  # Ask
            else:
                limit_price = round(quote[0], 2)  # Bid
        else:
            px = float(signal.get("entry_px", signal.get("exit_px", 0)))
            limit_price = round(px * (1.01 if action == "ENTER" else 0.99), 2)
    except Exception as e:
        px = float(signal.get("entry_px", signal.get("exit_px", 0)))
        limit_price = round(px * (1.01 if action == "ENTER" else 0.99), 2)

    if action == "ENTER":
        entry_px = float(signal.get("entry_px", limit_price))
        if entry_px <= 0: return None
        max_outlay = net_liq * 0.33
        raw_contracts = int(max_outlay / (100 * entry_px))
        contracts = max(1, min(raw_contracts, 5))
        risk_max = signal.get("max_contracts_override", 99)
        contracts = min(contracts, risk_max)
        
        o_action = OrderAction.BUY_TO_OPEN
        price_eff = PriceEffect.DEBIT
        logger.info(f"QQQ LEAPS ENTRY: NAV=\ -> {contracts} contracts @ \")
    else:
        # EXIT: Try to find how many contracts we currently own, else fallback to signal
        positions = tastytrade_utils.get_account_positions(session, account)
        held_qty = 0
        for p in positions:
            if p.get("symbol") == occ_symbol.strip():
                held_qty = int(p.get("quantity", 0))
        
        contracts = held_qty if held_qty > 0 else int(signal.get("contracts", 1))
        o_action = OrderAction.SELL_TO_CLOSE
        price_eff = PriceEffect.CREDIT
        logger.info(f"QQQ LEAPS EXIT: closing {contracts} contracts @ \")

    legs = [
        OrderLeg(
            instrument_type="Equity Option",
            symbol=occ_symbol.strip(),
            quantity=contracts,
            action=o_action,
        )
    ]
    
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=legs,
        price=limit_price,
        price_effect=price_eff,
    )
    
    try:
        response = account.place_order(session, order, dry_run=False)
        order_id = str(response.order.id) if hasattr(response, "order") else "auto-submitted"
        logger.info(f"✅ QQQ LEAPS {action} submitted! Order: {order_id}")
    except Exception as e:
        logger.error(f"❌ QQQ LEAPS order submission failed: {e}")
        return None
    
    return {
        "orderId": order_id,
        "symbol": "QQQ",
        "strategy": "QQQ_LEAPS",
        "action": action,
        "strike": strike,
        "expiry": expiry,
        "contracts": contracts,
        "limitPrice": limit_price,
        "netLiq": net_liq,
        "autoApproved": True,
        "timestamp": datetime.now().isoformat()
    }
'''

content += new_func

with open('auto_approve.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patch completed successfully.')
