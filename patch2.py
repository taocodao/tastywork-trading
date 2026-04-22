import sys
import re

with open('auto_approve.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We will replace the entire function defined at the end
match = re.search(r'def _execute_qqq_leaps_auto_approve\(.*?$', content, re.DOTALL)
if not match:
    print('Function not found!')
    sys.exit(1)

old_func_src = match.group(0)

new_func = '''def _execute_qqq_leaps_auto_approve(signal: Dict, session, account) -> Optional[Dict[str, Any]]:
    \"\"\"
    Execute a QQQ LEAPS long call entry or exit on a real Tastytrade account.
    Uses strategy-specific virtual balance instead of real account NLV.
    \"\"\"
    from tastytrade.order import NewOrder, OrderLeg, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    import tastytrade_utils
    from datetime import datetime
    import os
    import psycopg2
    from psycopg2.extras import RealDictCursor

    action = signal.get("action", "ENTER").upper()
    strike = float(signal.get("strike", 0))
    expiry = signal.get("expiry", signal.get("expiry_date", ""))
    user_id = signal.get("user_id")

    if not user_id:
        logger.error("QQQ LEAPS auto-approve missing user_id in signal (failed to map virtual balance)")
        return None

    if strike == 0 or not expiry:
        logger.error("QQQ LEAPS signal missing required fields (strike/expiry)")
        return None
        
    exp_dt = expiry.replace("-", "")[2:]
    strike_fmt = f"{int(strike * 1000):08d}"
    occ_symbol = f"QQQ  {exp_dt}C{strike_fmt}"
    
    # Get virtual balance and held positions from shadow DB instead of live Tasty account
    db_url = os.getenv("DATABASE_URL")
    shadow_cash = 25000.0
    held_qty = 0
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT cash_balance FROM virtual_accounts WHERE user_id = %s AND strategy = 'QQQ_LEAPS'", (user_id,))
            row = cur.fetchone()
            if row:
                shadow_cash = float(row["cash_balance"])
            
            cur.execute("SELECT quantity FROM shadow_positions WHERE user_id = %s AND strategy = 'QQQ_LEAPS' AND symbol = %s", (user_id, occ_symbol.strip()))
            pos_row = cur.fetchone()
            if pos_row:
                held_qty = int(pos_row["quantity"])
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch shadow portfolio for {user_id}: {e}")
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
        
        # 33% formula correctly sized against their SPECIFIC virtual QQQ_LEAPS balance
        max_outlay = shadow_cash * 0.33
        raw_contracts = int(max_outlay / (100 * entry_px))
        contracts = max(1, min(raw_contracts, 5))
        risk_max = signal.get("max_contracts_override", 99)
        contracts = min(contracts, risk_max)
        
        o_action = OrderAction.BUY_TO_OPEN
        price_eff = PriceEffect.DEBIT
        logger.info(f"QQQ LEAPS ENTRY for {user_id}: VirtualCash=\ -> {contracts} contracts @ \")
    else:
        # EXIT: explicitly use the shadow position we retrieved from DB above
        contracts = held_qty if held_qty > 0 else int(signal.get("contracts", 1))
        o_action = OrderAction.SELL_TO_CLOSE
        price_eff = PriceEffect.CREDIT
        logger.info(f"QQQ LEAPS EXIT for {user_id}: closing shadow-held {contracts} contracts @ \")

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
    
    order_id = "unknown"
    filled_price = limit_price
    
    try:
        response = account.place_order(session, order, dry_run=False)
        order_id = str(response.order.id) if hasattr(response, "order") else "auto-submitted"
        logger.info(f"✅ QQQ LEAPS {action} submitted for {user_id}! Order: {order_id}")
        
        # Monitor for execution price (Wait max 3-5 seconds to grab live executed fill, simplified here via TastytradeClient)
        try:
            from tastytrade_client import TastyTradeClient
            tt_c = TastyTradeClient(session)
            resp = tt_c.get_order(account, order_id)
            if resp and resp.get('status') == 'Filled':
                filled_price = float(resp.get('averagePrice', limit_price))
        except Exception as _e:
            logger.warning(f"Could not confirm fill price, using limit \: {_e}")
            
    except Exception as e:
        logger.error(f"❌ QQQ LEAPS order submission failed for {user_id}: {e}")
        return None

    # Sync to shadow_positions & virtual_accounts using EXECUTED price, not limit/signal
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            if action == "ENTER":
                cur.execute(
                    \"\"\"
                    INSERT INTO shadow_positions (user_id, strategy, symbol, quantity, avg_price, leg_action, instrument_type, executed_at)
                    VALUES (%s, 'QQQ_LEAPS', %s, %s, %s, 'BUY', 'OPTION', NOW())
                    \"\"\",
                    (user_id, occ_symbol.strip(), contracts, filled_price)
                )
                cur.execute(
                    "UPDATE virtual_accounts SET cash_balance = cash_balance - %s WHERE user_id = %s AND strategy = 'QQQ_LEAPS'",
                    (contracts * 100 * filled_price, user_id)
                )
            else:
                cur.execute(
                    "DELETE FROM shadow_positions WHERE user_id = %s AND strategy = 'QQQ_LEAPS' AND symbol = %s",
                    (user_id, occ_symbol.strip())
                )
                cur.execute(
                    "UPDATE virtual_accounts SET cash_balance = cash_balance + %s WHERE user_id = %s AND strategy = 'QQQ_LEAPS'",
                    (contracts * 100 * filled_price, user_id)
                )
        conn.commit()
        conn.close()
        logger.info(f"â–¶ï¸ Synced {action} to DB shadow ledger for {user_id} @ executed \")
    except Exception as e:
        logger.error(f"❌ Failed to sync shadow position for {user_id}: {e}")

    return {
        "orderId": order_id,
        "symbol": "QQQ",
        "strategy": "QQQ_LEAPS",
        "action": action,
        "strike": strike,
        "expiry": expiry,
        "contracts": contracts,
        "limitPrice": limit_price,
        "fillPrice": filled_price,
        "netLiq": shadow_cash,
        "autoApproved": True,
        "timestamp": datetime.now().isoformat()
    }
'''

content = content.replace(old_func_src, new_func)

with open('auto_approve.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated auto_approve.py successfully.')
