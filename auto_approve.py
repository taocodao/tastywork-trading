"""
Auto-Approve Module
===================
Automatically executes high-confidence signals based on user settings.
"""

import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# Default auto-approve settings with per-strategy risk profiles
DEFAULT_AUTO_APPROVE_SETTINGS = {
    "enabled": True,  # Master switch for auto-approve
    "max_daily_trades": 5,  # Max auto-approved trades per day
    
    # Theta Sprint settings (cash-secured puts)
    "theta": {
        "enabled": True,
        "risk_level": "MEDIUM",  # LOW, MEDIUM, or HIGH
        "risk_profiles": {
            "LOW": {
                "min_confidence": 75,
                "max_capital_per_trade": 1000,
                "max_contracts": 5,
                "max_positions": 3,
                "breach_threshold_pct": 0.02,
                "breach_confirmation_days": 3,
                "dte_exit_threshold": 5,
                "max_loss_pct": 200.0,
                "vix_block_trading": 30,
                "vix_reduce_size": 25,
            },
            "MEDIUM": {
                "min_confidence": 70,
                "max_capital_per_trade": 2000,
                "max_contracts": 8,
                "max_positions": 5,
                "breach_threshold_pct": 0.02,
                "breach_confirmation_days": 3,
                "dte_exit_threshold": 3,
                "max_loss_pct": 200.0,
                "vix_block_trading": 35,
                "vix_reduce_size": 28,
            },
            "HIGH": {
                "min_confidence": 65,
                "max_capital_per_trade": 5000,
                "max_contracts": 10,
                "max_positions": 6,
                "breach_threshold_pct": 0.03,
                "breach_confirmation_days": 2,
                "dte_exit_threshold": 2,
                "max_loss_pct": 200.0,
                "vix_block_trading": 40,
                "vix_reduce_size": 32,
            },
        },
        "custom_overrides": {},
    },
    
    # Diagonal Spread settings (PMCC)
    "diagonal": {
        "enabled": False,
        "risk_level": "MEDIUM",
        "risk_profiles": {
            "LOW": {
                "min_confidence": 80,
                "max_capital_per_trade": 500,
                "max_contracts": 1,
                "max_positions": 2,
            },
            "MEDIUM": {
                "min_confidence": 75,
                "max_capital_per_trade": 1000,
                "max_contracts": 2,
                "max_positions": 3,
            },
            "HIGH": {
                "min_confidence": 70,
                "max_capital_per_trade": 2000,
                "max_contracts": 3,
                "max_positions": 4,
            },
        },
        "custom_overrides": {},
    },
}

# Track daily auto-approve count
_daily_auto_approve_count = 0
_last_reset_date = datetime.now().date()


def get_auto_approve_settings() -> Dict[str, Any]:
    """Load auto-approve settings from file or return defaults."""
    try:
        import json
        from pathlib import Path
        
        settings_file = Path("data/auto_approve_settings.json")
        if settings_file.exists():
            with open(settings_file) as f:
                saved = json.load(f)
                # Deep merge with defaults
                merged = {**DEFAULT_AUTO_APPROVE_SETTINGS}
                for key in ("theta", "diagonal"):
                    if key in saved:
                        merged[key] = {**DEFAULT_AUTO_APPROVE_SETTINGS[key], **saved[key]}
                        # Preserve risk profiles from defaults if not in saved
                        if "risk_profiles" not in saved[key]:
                            merged[key]["risk_profiles"] = DEFAULT_AUTO_APPROVE_SETTINGS[key]["risk_profiles"]
                for key in saved:
                    if key not in ("theta", "diagonal"):
                        merged[key] = saved[key]
                return merged
    except Exception as e:
        logger.warning(f"Could not load auto-approve settings: {e}")
    
    return DEFAULT_AUTO_APPROVE_SETTINGS


def _get_active_strategy_settings(settings: Dict, strategy_key: str) -> Dict[str, Any]:
    """
    Resolve active settings for a strategy by merging risk profile with custom overrides.
    """
    strategy = settings.get(strategy_key, {})
    risk_level = strategy.get("risk_level", "MEDIUM")
    risk_profiles = strategy.get("risk_profiles", {})
    profile = risk_profiles.get(risk_level, {})
    custom = strategy.get("custom_overrides", {})
    
    # Custom overrides take precedence over profile defaults
    return {**profile, **custom}


def should_auto_approve(signal: Dict[str, Any], user_refresh_token: str = None) -> bool:
    """
    Determine if a signal should be auto-approved.
    
    Uses per-strategy risk profiles to check confidence, capital, and strategy eligibility.
    
    Args:
        signal: Signal data dict
        user_refresh_token: User's OAuth token (required for execution)
        
    Returns:
        True if signal should be auto-approved
    """
    global _daily_auto_approve_count, _last_reset_date
    
    # Reset daily counter at midnight
    today = datetime.now().date()
    if today > _last_reset_date:
        _daily_auto_approve_count = 0
        _last_reset_date = today
    
    settings = get_auto_approve_settings()
    
    # Check master switch
    if not settings.get("enabled", False):
        logger.debug("Auto-approve: Disabled in settings")
        return False
    
    # Check if we have credentials
    if not user_refresh_token:
        env_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
        if not env_token:
            logger.debug("Auto-approve: No OAuth credentials available")
            return False
    
    # Check daily limit
    if _daily_auto_approve_count >= settings.get("max_daily_trades", 5):
        logger.info(f"Auto-approve: Daily limit reached ({_daily_auto_approve_count})")
        return False
    
    # Determine strategy type
    strategy = signal.get("strategy", "").lower()
    if "theta" in strategy or "put" in strategy:
        strategy_key = "theta"
    elif "diagonal" in strategy or "pmcc" in strategy:
        strategy_key = "diagonal"
    elif "calendar" in strategy:
        strategy_key = "diagonal"  # Calendar spreads map to diagonal
    else:
        logger.debug(f"Auto-approve: Unknown strategy '{strategy}'")
        return False
    
    # Check if strategy is enabled
    strategy_settings = settings.get(strategy_key, {})
    if not strategy_settings.get("enabled", False):
        logger.debug(f"Auto-approve: {strategy_key} strategy disabled")
        return False
    
    # Get active settings from risk profile + custom overrides
    active = _get_active_strategy_settings(settings, strategy_key)
    
    # Check confidence
    confidence = signal.get("confidence", signal.get("winRate", 0))
    min_confidence = active.get("min_confidence", 70)
    if confidence < min_confidence:
        logger.debug(f"Auto-approve: Confidence {confidence}% < {min_confidence}%")
        return False
    
    # Check capital limit
    capital = signal.get("capitalRequired", signal.get("cost", 0))
    max_capital = active.get("max_capital_per_trade", 5000)
    if capital > max_capital:
        logger.debug(f"Auto-approve: Capital ${capital} > ${max_capital}")
        return False
    
    logger.info(f"✅ Auto-approve criteria met for {signal.get('symbol')} ({strategy_key}/{strategy_settings.get('risk_level', 'MEDIUM')})")
    return True


def auto_approve_signal(
    signal: Dict[str, Any],
    user_refresh_token: str = None,
    account_number: str = None
) -> Optional[Dict[str, Any]]:
    """
    Auto-approve and execute a signal if criteria are met.
    
    Args:
        signal: Signal data dict
        user_refresh_token: User's OAuth token
        account_number: User's account number
        
    Returns:
        Execution result if approved and executed, None otherwise
    """
    global _daily_auto_approve_count
    
    # Use environment token if not provided
    if not user_refresh_token:
        user_refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
    
    if not should_auto_approve(signal, user_refresh_token):
        return None
    
    try:
        logger.info(f"🤖 Auto-approving signal: {signal.get('symbol')} {signal.get('strategy')}")
        
        # Import server handlers to execute trade
        from tasty_api_server import create_user_session, get_user_account
        from tastytrade import Account
        
        # Create session
        session = create_user_session(user_refresh_token)
        
        # Get account
        account = get_user_account(session, account_number)
        account_num = account.account_number
        
        # Determine strategy and execute
        strategy = signal.get("strategy", "").lower()
        
        if "theta" in strategy or "put" in strategy.lower():
            result = _execute_theta_auto_approve(signal, session, account)
        else:
            result = _execute_calendar_auto_approve(signal, session, account)
        
        # Increment daily counter
        _daily_auto_approve_count += 1
        logger.info(f"✅ Auto-approve execution complete! Daily count: {_daily_auto_approve_count}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Auto-approve execution failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _execute_theta_auto_approve(signal: Dict, session, account) -> Dict[str, Any]:
    """Execute auto-approved Theta trade with smart fill monitoring."""
    from tastytrade.order import NewOrder, OrderLeg, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    from ib_data_provider import IBDataProvider
    from tastytrade_client import TastytradeClient
    
    symbol = signal.get("symbol", "")
    strike = float(signal.get("strike", 0))
    expiration = signal.get("expiration", signal.get("expiry", ""))
    contracts = min(signal.get("contracts", 1), 2)  # Max 2 for auto-approve
    
    # Format OCC symbol
    exp_date = expiration.replace("-", "")[2:] if expiration else ""
    strike_fmt = f"{int(strike * 1000):08d}"
    occ_symbol = f"{symbol}  {exp_date}P{strike_fmt}"
    
    # Get live price from IB
    ib_data = IBDataProvider()
    quote = ib_data.get_option_price_by_symbol(occ_symbol.strip())
    
    if quote:
        price = round(quote[0] * 0.95, 2)  # 95% of bid for fill
        logger.info(f"✅ IB live price: bid ${quote[0]:.2f} → order @ ${price}")
    else:
        price = float(signal.get("entryPrice", signal.get("entry_price", 1.50)))
        logger.warning(f"⚠️ Using signal price: ${price}")
    
    # Build order
    legs = [
        OrderLeg(
            instrument_type='Equity Option',
            symbol=occ_symbol.strip(),
            quantity=contracts,
            action=OrderAction.SELL_TO_OPEN
        )
    ]
    
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=legs,
        price=price,
        price_effect=PriceEffect.CREDIT
    )
    
    response = account.place_order(session, order, dry_run=False)
    order_id = str(response.order.id) if hasattr(response, 'order') else "auto-submitted"
    
    logger.info(f"📡 Auto-approved Theta: {symbol} {strike}P @ ${price}, Order ID: {order_id}")
    
    # Monitor order until filled (with automatic price adjustments)
    client = TastytradeClient()
    client.connect()
    fill_result = client.monitor_and_fill(
        order_id=order_id,
        initial_price=price,
        is_credit=True,  # STO = credit order
    )
    client.disconnect()
    
    actual_price = fill_result.get("fill_price", price)
    
    return {
        "orderId": order_id,
        "symbol": symbol,
        "strategy": "Theta Cash-Secured Put",
        "strike": strike,
        "limitPrice": price,
        "fillPrice": actual_price,
        "filled": fill_result.get("filled", False),
        "adjustments": fill_result.get("adjustments_made", 0),
        "finalStatus": fill_result.get("final_status", "Unknown"),
        "contracts": contracts,
        "autoApproved": True,
        "timestamp": datetime.now().isoformat()
    }


def _execute_calendar_auto_approve(signal: Dict, session, account) -> Dict[str, Any]:
    """Execute auto-approved Calendar Spread trade with smart fill monitoring."""
    from tastytrade.order import NewOrder, OrderLeg, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    from ib_data_provider import IBDataProvider
    from tastytrade_client import TastytradeClient
    
    symbol = signal.get("symbol", "")
    strike = float(signal.get("strike", 0))
    front_expiry = signal.get("frontExpiry", "")
    back_expiry = signal.get("backExpiry", "")
    
    # Format OCC symbols
    front_date = front_expiry.replace("-", "")[2:] if front_expiry else ""
    back_date = back_expiry.replace("-", "")[2:] if back_expiry else ""
    strike_fmt = f"{int(strike * 1000):08d}"
    
    short_symbol = f"{symbol}  {front_date}C{strike_fmt}"
    long_symbol = f"{symbol}  {back_date}C{strike_fmt}"
    
    # Get live prices from IB
    ib_data = IBDataProvider()
    short_quote = ib_data.get_option_price_by_symbol(short_symbol.strip())
    long_quote = ib_data.get_option_price_by_symbol(long_symbol.strip())
    
    if short_quote and long_quote:
        price = round(long_quote[1] - short_quote[0], 2)  # ask - bid = net debit
        logger.info(f"✅ IB live: Sell @ ${short_quote[0]:.2f}, Buy @ ${long_quote[1]:.2f} = ${price}")
    else:
        price = float(signal.get("cost", 2.50))
        logger.warning(f"⚠️ Using signal price: ${price}")
    
    # Build order
    legs = [
        OrderLeg(
            instrument_type='Equity Option',
            symbol=short_symbol.strip(),
            quantity=1,
            action=OrderAction.SELL_TO_OPEN
        ),
        OrderLeg(
            instrument_type='Equity Option',
            symbol=long_symbol.strip(),
            quantity=1,
            action=OrderAction.BUY_TO_OPEN
        )
    ]
    
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=legs,
        price=price,
        price_effect=PriceEffect.DEBIT
    )
    
    response = account.place_order(session, order, dry_run=False)
    order_id = str(response.order.id) if hasattr(response, 'order') else "auto-submitted"
    
    logger.info(f"📡 Auto-approved Calendar: {symbol} @ ${price}, Order ID: {order_id}")
    
    # Monitor order until filled (with automatic price adjustments)
    client = TastytradeClient()
    client.connect()
    fill_result = client.monitor_and_fill(
        order_id=order_id,
        initial_price=price,
        is_credit=False,  # Calendar spread = debit order
    )
    client.disconnect()
    
    actual_price = fill_result.get("fill_price", price)
    
    return {
        "orderId": order_id,
        "symbol": symbol,
        "strategy": "Calendar Spread",
        "strike": strike,
        "limitPrice": price,
        "fillPrice": actual_price,
        "filled": fill_result.get("filled", False),
        "adjustments": fill_result.get("adjustments_made", 0),
        "finalStatus": fill_result.get("final_status", "Unknown"),
        "autoApproved": True,
        "timestamp": datetime.now().isoformat()
    }


def enable_auto_approve():
    """Enable auto-approve feature."""
    save_auto_approve_setting("enabled", True)
    logger.info("✅ Auto-approve ENABLED")


def disable_auto_approve():
    """Disable auto-approve feature."""
    save_auto_approve_setting("enabled", False)
    logger.info("⛔ Auto-approve DISABLED")


def save_auto_approve_setting(key: str, value: Any):
    """Save a single auto-approve setting."""
    import json
    from pathlib import Path
    
    settings_file = Path("data/auto_approve_settings.json")
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    
    settings = get_auto_approve_settings()
    settings[key] = value
    
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
