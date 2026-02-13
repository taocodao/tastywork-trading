"""
End-to-End Strategy Test
========================
Creates one REAL test signal per strategy, saves to DB, and auto-executes on Tastytrade.

Strategies tested:
  1. Theta Cash-Secured Put (SELL PUT)
  2. Calendar/Diagonal Spread (BUY back-month call, SELL front-month call)

Usage:
  python test_e2e_strategies.py                # Dry-run mode (validates only, no real orders)
  python test_e2e_strategies.py --live          # LIVE mode (places real orders on Tastytrade!)
  python test_e2e_strategies.py --live --theta  # Only test theta strategy
  python test_e2e_strategies.py --live --calendar  # Only test calendar strategy

Requirements:
  - IB Gateway running (for option chain lookup)
  - .env with TASTYTRADE_CLIENT_SECRET and TASTYTRADE_REFRESH_TOKEN
"""

import os
import sys
import json
import uuid
import logging
import argparse
import requests
from datetime import datetime, date, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# Setup logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_e2e.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# API endpoints
PYTHON_API = os.getenv("TASTYTRADE_API_URL", "http://34.235.119.67:8002")
SIGNAL_API = f"{PYTHON_API}/api/signals"


def find_theta_option():
    """
    Find a REAL, cheap, liquid put option for theta strategy test.
    Uses IB Gateway to get actual option chains.
    Returns signal dict or None.
    """
    logger.info("=" * 60)
    logger.info("THETA: Finding real put option from IB...")
    logger.info("=" * 60)
    
    try:
        from ib_data_provider import IBDataProvider
        
        ib = IBDataProvider()
        ib.connect()
        
        try:
            # Get SPY price
            spy_price = ib.get_price("SPY")
            if spy_price <= 0:
                logger.error("Could not get SPY price")
                return None
            
            logger.info(f"SPY current price: ${spy_price:.2f}")
            
            # Find a put ~5% OTM, ~30 days out (cheap, high probability OTM)
            target_expiry = date.today() + timedelta(days=30)
            
            puts = ib.get_put_chain_for_theta("SPY", target_expiry, 0.15, 0.35)
            
            if not puts:
                logger.error("No puts found from IB")
                return None
            
            # Pick the cheapest one with decent liquidity (lowest delta = most OTM = cheapest)
            puts.sort(key=lambda p: abs(p["delta"]))
            selected = puts[0]  # Lowest delta = most OTM = cheapest premium
            
            logger.info(f"Selected: SPY {selected['strike']}P exp {selected['expiration']}")
            logger.info(f"  Bid: ${selected['bid']:.2f}, Ask: ${selected['ask']:.2f}")
            logger.info(f"  Delta: {selected['delta']:.3f}, IV: {selected['iv']:.2%}")
            
            # Build signal - use 1 contract for minimum risk
            exp = selected['expiration']
            exp_str = exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp)
            dte = (exp - date.today()).days if hasattr(exp, 'year') else 30
            
            signal = {
                "id": f"test_theta_{uuid.uuid4().hex[:8]}",
                "symbol": "SPY",
                "strategy": "theta",
                "strike": selected["strike"],
                "expiration": exp_str,
                "dte": dte,
                "entry_price": round(selected["bid"] * 0.95, 2),  # 95% of bid for likely fill
                "bid": selected["bid"],
                "ask": selected["ask"],
                "mid": round((selected["bid"] + selected["ask"]) / 2, 2),
                "delta": selected["delta"],
                "theta": selected.get("theta", -0.05),
                "vega": selected.get("vega", 0.10),
                "iv": selected.get("iv", 0.20),
                "confidence": 80,
                "probability_otm": round((1 - abs(selected["delta"])) * 100, 1),
                "contracts": 1,  # Minimum for testing
                "total_premium": round(selected["bid"] * 0.95 * 100, 2),
                "capital_required": round(selected["strike"] * 100, 2),
                "cost": round(selected["strike"] * 100, 2),
                "potentialReturn": round(selected["bid"] * 0.95 * 100, 2),
                "returnPercent": round(selected["bid"] * 0.95 / selected["strike"] * 100, 2),
                "riskLevel": "Low",
                "status": "pending",
                "signalType": "theta",
                "created_at": datetime.utcnow().isoformat(),
            }
            
            logger.info(f"Theta signal created: {signal['symbol']} {signal['strike']}P @ ${signal['entry_price']}")
            logger.info(f"  Capital required: ${signal['capital_required']:.2f}")
            logger.info(f"  Max premium: ${signal['total_premium']:.2f}")
            
            return signal
            
        finally:
            ib.disconnect()
            
    except Exception as e:
        logger.error(f"Error finding theta option: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_calendar_option():
    """
    Find a REAL calendar spread (same strike, two expirations) for SPY.
    Uses IB Gateway to verify contracts exist.
    Returns signal dict or None.
    """
    logger.info("=" * 60)
    logger.info("CALENDAR: Finding real calendar spread from IB...")
    logger.info("=" * 60)
    
    try:
        from ib_data_provider import IBDataProvider
        from ib_insync import Stock, Option
        
        ib = IBDataProvider()
        ib.connect()
        
        try:
            # Get SPY price
            spy_price = ib.get_price("SPY")
            if spy_price <= 0:
                logger.error("Could not get SPY price")
                return None
            
            logger.info(f"SPY current price: ${spy_price:.2f}")
            
            # Get option chain to find valid expirations
            underlying = Stock("SPY", "SMART", "USD")
            ib.ib.qualifyContracts(underlying)
            chains = ib.ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
            
            if not chains:
                logger.error("No chains found")
                return None
            
            # Use SMART chains only AND find the right trading class
            # SPY options use "SPY" as trading class (not SPYW weeklies with fewer strikes)
            smart_chains = [c for c in chains if c.exchange == 'SMART']
            
            if not smart_chains:
                logger.error("No SMART chains found")
                return None
            
            # Collect ALL expirations and strikes from all chains
            today = date.today()
            all_exps = set()
            all_strikes = set()
            
            for c in smart_chains:
                all_exps.update(c.expirations)
                all_strikes.update(c.strikes)
            
            logger.info(f"Found {len(all_exps)} expirations, {len(all_strikes)} strikes across {len(smart_chains)} chain(s)")
            
            # Filter expirations 14-45 days out 
            future_exps = []
            for exp_str in sorted(all_exps):
                exp_date = datetime.strptime(exp_str, '%Y%m%d').date()
                days_out = (exp_date - today).days
                if 14 <= days_out <= 45:
                    future_exps.append((exp_date, exp_str))
            
            if len(future_exps) < 2:
                logger.error(f"Need at least 2 expirations 14-45 days out, found {len(future_exps)}")
                return None
            
            # Pick front (~14-21 days) and back (~28-45 days) — at least 7 days apart
            front_exp = future_exps[0]
            back_exp = None
            for exp_date, exp_str in future_exps[1:]:
                if (exp_date - front_exp[0]).days >= 7:
                    back_exp = (exp_date, exp_str)
                    break
            
            if not back_exp:
                back_exp = future_exps[-1]
            
            logger.info(f"Front expiry: {front_exp[0]} ({(front_exp[0] - today).days} DTE)")
            logger.info(f"Back expiry:  {back_exp[0]} ({(back_exp[0] - today).days} DTE)")
            
            # Find ATM strike — try $5 increments near SPY price
            # SPY weeklies only have $5 strikes, monthlies have $1 strikes
            base_strike = round(spy_price / 5) * 5  # Round to nearest $5
            
            # Generate candidate strikes: nearest $5 first, then expand outward
            candidate_strikes = [base_strike]
            for offset in [5, -5, 10, -10, 15, -15]:
                candidate_strikes.append(base_strike + offset)
            
            logger.info(f"SPY @ ${spy_price:.2f}, trying strikes: {candidate_strikes}")
            
            # Try each strike until BOTH front and back contracts qualify
            atm_strike = None
            front_contract = None
            back_contract = None
            
            for try_strike in candidate_strikes:
                fc = Option("SPY", front_exp[1], try_strike, 'C', 'SMART')
                bc = Option("SPY", back_exp[1], try_strike, 'C', 'SMART')
                
                ib.ib.qualifyContracts(fc, bc)
                
                if fc.conId and bc.conId:
                    atm_strike = try_strike
                    front_contract = fc
                    back_contract = bc
                    logger.info(f"Strike ${try_strike} qualifies on BOTH expirations!")
                    break
                else:
                    logger.info(f"  ${try_strike}: front={'OK' if fc.conId else 'MISSING'}, back={'OK' if bc.conId else 'MISSING'}")
            
            if not atm_strike:
                logger.error("Could not find any strike valid on both expirations!")
                return None
            
            logger.info(f"ATM strike: ${atm_strike}")
            logger.info(f"  Front: conId={front_contract.conId}")
            logger.info(f"  Back:  conId={back_contract.conId}")
            
            # Get live quotes
            front_ticker = ib.ib.reqMktData(front_contract, '106', False, False)
            back_ticker = ib.ib.reqMktData(back_contract, '106', False, False)
            
            import time
            import math
            
            def valid_price(val):
                """Check if IB price is valid (not None, not NaN, positive)."""
                return val is not None and not math.isnan(val) and val > 0
            
            start = time.time()
            while time.time() - start < 10:  # 10 second timeout
                ib.ib.sleep(0.3)
                if valid_price(front_ticker.bid) and valid_price(back_ticker.ask):
                    break
            
            front_bid = front_ticker.bid if valid_price(front_ticker.bid) else None
            front_ask = front_ticker.ask if valid_price(front_ticker.ask) else None
            back_bid = back_ticker.bid if valid_price(back_ticker.bid) else None
            back_ask = back_ticker.ask if valid_price(back_ticker.ask) else None
            
            # Cancel market data
            try:
                ib.ib.cancelMktData(front_contract)
                ib.ib.cancelMktData(back_contract)
            except:
                pass
            
            if front_bid is None or back_ask is None:
                logger.warning(f"IB quotes not available (may need market data subscription)")
                logger.warning(f"  Front: bid={front_ticker.bid}, ask={front_ticker.ask}")
                logger.warning(f"  Back: bid={back_ticker.bid}, ask={back_ticker.ask}")
                # Use fallback — will be overridden by Tastytrade data in _execute_calendar
                net_debit = 0  # Flag: no valid IB price
                logger.info(f"  Will attempt to get price from Tastytrade API instead")
            else:
                # Calendar debit = buy back (ask) - sell front (bid)
                net_debit = round(back_ask - front_bid, 2)
                logger.info(f"Front leg: bid ${front_bid:.2f}, ask ${front_ask:.2f}")
                logger.info(f"Back leg:  bid ${back_bid:.2f}, ask ${back_ask:.2f}")
                logger.info(f"Net debit: ${net_debit:.2f}")
            
            signal = {
                "id": f"test_calendar_{uuid.uuid4().hex[:8]}",
                "symbol": "SPY",
                "strategy": "calendar-spread",
                "direction": "bullish",
                "strike": atm_strike,
                "frontExpiry": front_exp[0].strftime('%Y-%m-%d'),
                "backExpiry": back_exp[0].strftime('%Y-%m-%d'),
                "cost": round(net_debit * 100, 2),
                "potentialReturn": round((front_bid or 1.0) * 100, 2),
                "returnPercent": round((front_bid or 1.0) / max(net_debit, 0.01) * 100, 1),
                "confidence": 75,
                "winRate": 75,
                "riskLevel": "Medium",
                "status": "pending",
                "signalType": "calendar",
                "contracts": 1,
                "price": net_debit,
                "net_debit": net_debit,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            logger.info(f"Calendar signal: SPY ${atm_strike}C")
            logger.info(f"  SELL {signal['frontExpiry']}, BUY {signal['backExpiry']}")
            logger.info(f"  Net debit: ${net_debit:.2f}/contract (${signal['cost']:.2f} total)")
            
            return signal
            
        finally:
            ib.disconnect()
            
    except Exception as e:
        logger.error(f"Error finding calendar spread: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_signal_to_db(signal):
    """
    Save signal to the database.
    Prioritizes direct DB access via SQLAlchemy, falls back to API.
    """
    logger.info(f"Saving signal: {signal['id']}")
    
    # 1. Try DIRECT DB access first (most reliable for local scripts)
    try:
        sys.path.append(os.getcwd())
        from src.earnings_intelligence.database import SignalRepository, get_session
        
        # Ensure regex format matches what DB expects
        # DB model expects 'expires_at' (snake_case) for the column
        if "expiresAt" in signal and "expires_at" not in signal:
            # Parse ISO string back to datetime if needed, or pass string if DB handles it?
            # Model defines expires_at as DateTime.
            # signal["expiresAt"] is a string/ISO format from earlier.
            # SignalRepository.save_signal expects signal_data.
            try:
                # If it's a string, convert to datetime
                if isinstance(signal["expiresAt"], str):
                    dt = datetime.fromisoformat(signal["expiresAt"].replace("Z", "+00:00"))
                    signal["expires_at"] = dt
                else:
                    signal["expires_at"] = signal["expiresAt"]
            except:
                pass

        repo = SignalRepository()
        saved_signal = repo.save_signal(signal)
        logger.info(f"  ✅ Saved to DB (Direct SQL) - ID: {saved_signal.id}")
        return True
        
    except ImportError:
        logger.warning("  Could not import database module. Falling back to API.")
    except Exception as e:
        logger.warning(f"  Direct DB save failed: {e}. Falling back to API.")

    # 2. Fallback to API
    endpoints = [
        "http://localhost:8002/api/signals",
        "http://localhost:8000/api/signals",
        f"{PYTHON_API}/api/signals"
    ]
    
    for url in endpoints:
        try:
            # JSON serializer might fail on datetime objects if we added them above
            # so we use a safe copy for API
            api_payload = signal.copy()
            if "expires_at" in api_payload and isinstance(api_payload["expires_at"], datetime):
                api_payload["expires_at"] = api_payload["expires_at"].isoformat()
                
            response = requests.post(
                url,
                json=api_payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            
            if response.ok:
                logger.info(f"  ✅ Saved to DB at {url}")
                return True
            else:
                logger.debug(f"  DB save failed at {url} ({response.status_code})")
        except Exception:
            pass
            
    logger.error("Could not save signal to any DB endpoint!")
    return False


def execute_on_tastytrade(signal, dry_run=True):
    """
    Execute signal on Tastytrade using the SDK.
    Uses Option.build_leg() for proper leg construction.
    """
    logger.info(f"{'DRY-RUN' if dry_run else 'LIVE'} execution: {signal['id']}")
    
    client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
    refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
    
    if not client_secret or not refresh_token:
        logger.error("Missing TASTYTRADE_CLIENT_SECRET or TASTYTRADE_REFRESH_TOKEN in .env")
        return None
    
    try:
        from tastytrade import Session, Account
        from tastytrade.instruments import Option as TastyOption
        from tastytrade.order import (
            NewOrder, Leg, OrderAction,
            OrderType, OrderTimeInForce, PriceEffect
        )
        
        # Create session
        logger.info("Creating Tastytrade session...")
        session = Session(client_secret, refresh_token)
        logger.info("Session created!")
        
        # Get account
        accounts = Account.get(session)
        if not accounts:
            logger.error("No accounts found!")
            return None
        
        account = accounts[0]
        logger.info(f"Account: {account.account_number}")
        
        # Get balances
        balances = account.get_balances(session)
        logger.info(f"Net Liq: ${balances.net_liquidating_value}")
        
        strategy = signal.get("strategy", "").lower()
        
        if "theta" in strategy or "put" in strategy:
            return _execute_theta(signal, session, account, dry_run)
        else:
            return _execute_calendar(signal, session, account, dry_run)
            
    except Exception as e:
        logger.error(f"Tastytrade execution failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _build_occ_symbol(symbol, expiration, strike, right='P'):
    """Build OCC option symbol: SYMBOL  YYMMDDP00STRIKE000"""
    exp_date = expiration.replace("-", "")[2:]  # YYMMDD
    strike_fmt = f"{int(strike * 1000):08d}"
    return f"{symbol.ljust(6)}{exp_date}{right}{strike_fmt}"


def _execute_theta(signal, session, account, dry_run):
    """Execute theta (sell put) on Tastytrade using Option.build_leg()."""
    from tastytrade.instruments import Option as TastyOption
    from tastytrade.order import (
        NewOrder, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    )
    
    symbol = signal["symbol"]
    strike = float(signal["strike"])
    expiration = signal["expiration"]
    contracts = signal.get("contracts", 1)
    price = Decimal(str(signal.get("entry_price", signal.get("bid", 1.00))))
    
    occ_symbol = _build_occ_symbol(symbol, expiration, strike, 'P')
    
    logger.info(f"Theta Order: SELL {symbol} {strike}P @ ${price}")
    logger.info(f"  OCC symbol: {occ_symbol}")
    logger.info(f"  Contracts: {contracts}")
    
    # Use Option.get() + build_leg() pattern (proven working in TastytradeClient)
    try:
        option_instrument = TastyOption.get(session, occ_symbol)
        leg = option_instrument.build_leg(Decimal(str(contracts)), OrderAction.SELL_TO_OPEN)
        logger.info(f"  Instrument found: {option_instrument.symbol}")
    except Exception as e:
        logger.error(f"  Could not find instrument '{occ_symbol}': {e}")
        logger.info("  Falling back to manual Leg construction...")
        # Fallback: build Leg manually
        from tastytrade.order import Leg, InstrumentType
        leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=occ_symbol,
            quantity=Decimal(str(contracts)),
            action=OrderAction.SELL_TO_OPEN
        )
    
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=[leg],
        price=price,
        price_effect=PriceEffect.CREDIT
    )
    
    logger.info(f"  {'DRY-RUN' if dry_run else 'LIVE'}: Submitting order...")
    response = account.place_order(session, order, dry_run=dry_run)
    
    if dry_run:
        logger.info(f"  DRY-RUN PASSED! Order would be accepted.")
        # Check for warnings
        if hasattr(response, 'warnings') and response.warnings:
            for w in response.warnings:
                logger.warning(f"  Warning: {w}")
        return {"status": "dry_run_passed", "signal": signal["id"]}
    else:
        order_id = str(response.order.id) if hasattr(response, 'order') else "submitted"
        logger.info(f"  LIVE ORDER PLACED! Order ID: {order_id}")
        return {"status": "submitted", "orderId": order_id, "signal": signal["id"]}


def _execute_calendar(signal, session, account, dry_run):
    """Execute calendar spread on Tastytrade using Option.build_leg()."""
    from tastytrade.instruments import Option as TastyOption
    from tastytrade.order import (
        NewOrder, OrderAction, OrderType, OrderTimeInForce, PriceEffect
    )
    
    symbol = signal["symbol"]
    strike = float(signal["strike"])
    front_expiry = signal["frontExpiry"]
    back_expiry = signal["backExpiry"]
    
    short_occ = _build_occ_symbol(symbol, front_expiry, strike, 'C')
    long_occ = _build_occ_symbol(symbol, back_expiry, strike, 'C')
    
    logger.info(f"Calendar Order: {symbol} ${strike}C")
    logger.info(f"  SELL (front): {short_occ}")
    logger.info(f"  BUY (back):   {long_occ}")
    
    # Get instruments via Tastytrade SDK
    try:
        short_instrument = TastyOption.get(session, short_occ)
        long_instrument = TastyOption.get(session, long_occ)
        short_leg = short_instrument.build_leg(Decimal('1'), OrderAction.SELL_TO_OPEN)
        long_leg = long_instrument.build_leg(Decimal('1'), OrderAction.BUY_TO_OPEN)
        logger.info(f"  Both instruments found!")
    except Exception as e:
        logger.error(f"  Could not find instruments: {e}")
        logger.info("  Falling back to manual Leg construction...")
        from tastytrade.order import Leg, InstrumentType
        short_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=short_occ,
            quantity=Decimal('1'),
            action=OrderAction.SELL_TO_OPEN
        )
        long_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=long_occ,
            quantity=Decimal('1'),
            action=OrderAction.BUY_TO_OPEN
        )
    
    # Fetch LIVE prices from Tastytrade API
    net_debit = Decimal(str(signal.get("price", signal.get("net_debit", 0))))
    try:
        # Use get_option_chain to find streamer symbols, then query market data
        from tastytrade.instruments import get_option_chain
        
        front_date = datetime.strptime(front_expiry, '%Y-%m-%d').date()
        back_date = datetime.strptime(back_expiry, '%Y-%m-%d').date()
        
        chain = get_option_chain(session, symbol)
        
        # Find matching options in chain (dict[date, list[Option]])
        short_option = None
        long_option = None
        
        for exp_date, options_list in chain.items():
            for opt in options_list:
                if (abs(float(opt.strike_price) - strike) < 0.01 and 
                    opt.option_type and 'C' in str(opt.option_type).upper()):
                    if exp_date == front_date:
                        short_option = opt
                    elif exp_date == back_date:
                        long_option = opt
        
        if short_option and long_option:
            logger.info(f"  Found chain options:")
            logger.info(f"    Short: {short_option.symbol} (streamer: {short_option.streamer_symbol})")
            logger.info(f"    Long: {long_option.symbol} (streamer: {long_option.streamer_symbol})")
            
            # Use Tastytrade REST API for market data
            # Option instruments have active_price or we can request market metrics
            try:
                # Try to get market data via the session's market data endpoint
                symbols_query = f"{short_option.symbol},{long_option.symbol}"
                data = session._get(f"/market-data?symbols={symbols_query}")
                
                if data and 'items' in data:
                    prices = {}
                    for item in data['items']:
                        sym = item.get('symbol', '')
                        prices[sym] = {
                            'bid': float(item.get('bid', 0) or 0),
                            'ask': float(item.get('ask', 0) or 0),
                            'mid': float(item.get('mid', 0) or 0),
                        }
                    
                    short_bid = prices.get(short_option.symbol, {}).get('bid', 0)
                    long_ask = prices.get(long_option.symbol, {}).get('ask', 0)
                    
                    if short_bid > 0 and long_ask > 0:
                        net_debit = Decimal(str(round(long_ask - short_bid, 2)))
                        logger.info(f"  Tastytrade LIVE: sell front @ ${short_bid:.2f}, buy back @ ${long_ask:.2f}")
                        logger.info(f"  Net debit: ${net_debit}")
            except Exception as md_err:
                logger.info(f"  Market data endpoint not available: {md_err}")
        else:
            logger.warning(f"  Could not find matching options in chain for strike ${strike}")
    except Exception as price_err:
        logger.warning(f"  Price fetch error: {price_err}")
    
    # If we still don't have a valid price, try to compute from signal's IB data
    if net_debit <= 0 or net_debit == Decimal('2.00'):
        sig_price = signal.get("price", signal.get("net_debit", 0))
        if sig_price and float(sig_price) > 0 and float(sig_price) != 2.00:
            net_debit = Decimal(str(sig_price))
            logger.info(f"  Using IB-sourced price from signal: ${net_debit}")
        else:
            # Last resort: estimate a reasonable price for ATM SPY calendar ~14-23 DTE
            # Typical ATM SPY calendar spread costs ~$3-6
            net_debit = Decimal('4.50')
            logger.warning(f"  No live prices available, using estimated ATM calendar price: ${net_debit}")
    
    # Ensure we have a valid price
    if net_debit <= 0:
        logger.error(f"  Net debit ${net_debit} is invalid")
        return {"status": "invalid_price", "signal": signal["id"]}
    
    # CRITICAL: Tastytrade SDK convention for calendar spreads:
    # Price must be NEGATIVE for debit trades (matching tastytrade_client.py pattern)
    # Do NOT set price_effect — let the SDK determine it from the sign
    # Also ensure strict quantization to 2 decimal places
    order_price = (-net_debit).quantize(Decimal("0.01"))
    
    logger.info(f"  Final order price: ${order_price} (Negative = Debit, No PriceEffect set)")
    
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=[short_leg, long_leg],
        price=order_price
    )
    
    logger.info(f"  {'DRY-RUN' if dry_run else 'LIVE'}: Submitting order...")
    response = account.place_order(session, order, dry_run=dry_run)
    
    if dry_run:
        logger.info(f"  DRY-RUN PASSED! Calendar spread is valid.")
        if hasattr(response, 'warnings') and response.warnings:
            for w in response.warnings:
                logger.warning(f"  Warning: {w}")
        return {"status": "dry_run_passed", "signal": signal["id"]}
    else:
        order_id = str(response.order.id) if hasattr(response, 'order') else "submitted"
        logger.info(f"  LIVE ORDER PLACED! Order ID: {order_id}")
        return {"status": "submitted", "orderId": order_id, "signal": signal["id"]}


def main():
    parser = argparse.ArgumentParser(description="End-to-End Strategy Test")
    parser.add_argument("--live", action="store_true", help="Place REAL orders (default: dry-run)")
    parser.add_argument("--theta", action="store_true", help="Only test theta strategy")
    parser.add_argument("--calendar", action="store_true", help="Only test calendar strategy")
    parser.add_argument("--no-db", action="store_true", help="Skip saving to database")
    parser.add_argument("--signal-only", action="store_true", help="Generate and save signal but DO NOT execute (for UI approval)")
    args = parser.parse_args()
    
    # If neither --theta nor --calendar specified, do both
    do_theta = args.theta or (not args.theta and not args.calendar)
    do_calendar = args.calendar or (not args.theta and not args.calendar)
    dry_run = not args.live
    
    logger.info("=" * 70)
    logger.info("END-TO-END STRATEGY TEST")
    if args.signal_only:
        logger.info("Mode: SIGNAL GENERATION ONLY (No Execution)")
    else:
        logger.info(f"Mode: {'LIVE (REAL ORDERS!)' if not dry_run else 'DRY-RUN (validation only)'}")
    logger.info(f"Strategies: {'Theta ' if do_theta else ''}{'Calendar' if do_calendar else ''}")
    logger.info("=" * 70)
    
    if not dry_run and not args.signal_only:
        logger.info("")
        logger.info("!!! WARNING: LIVE MODE - REAL ORDERS WILL BE PLACED !!!")
        logger.info("!!! Using 1 contract per strategy for minimum risk !!!")
        logger.info("")
        confirm = input("Type 'YES' to confirm: ")
        if confirm != "YES":
            logger.info("Cancelled.")
            return
    
    results = {}
    
    # -- Test 1: Theta Cash-Secured Put -------
    if do_theta:
        logger.info("")
        theta_signal = find_theta_option()
        
        if theta_signal:
            if not args.no_db:
                save_signal_to_db(theta_signal)
                if args.signal_only:
                    logger.info(f"✅ Signal saved to DB! ID: {theta_signal['id']}")
                    logger.info("Go to the UI to approve/reject this signal.")
            
            if not args.signal_only:
                result = execute_on_tastytrade(theta_signal, dry_run=dry_run)
                results["theta"] = result
            else:
                 results["theta"] = {"status": "saved_only", "signal": theta_signal["id"]}
        else:
            logger.error("THETA: Could not find suitable option")
            results["theta"] = {"status": "no_option_found"}
    
    # -- Test 2: Calendar Spread -------
    if do_calendar:
        logger.info("")
        calendar_signal = find_calendar_option()
        
        if calendar_signal:
            if not args.no_db:
                save_signal_to_db(calendar_signal)
                if args.signal_only:
                    logger.info(f"✅ Signal saved to DB! ID: {calendar_signal['id']}")
                    logger.info("Go to the UI to approve/reject this signal.")
            
            if not args.signal_only:
                result = execute_on_tastytrade(calendar_signal, dry_run=dry_run)
                results["calendar"] = result
            else:
                results["calendar"] = {"status": "saved_only", "signal": calendar_signal["id"]}
        else:
            logger.error("CALENDAR: Could not find suitable options")
            results["calendar"] = {"status": "no_option_found"}
    
    # -- Summary -------
    logger.info("")
    logger.info("=" * 70)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 70)
    
    all_passed = True
    for strategy, result in results.items():
        status = result.get("status", "unknown") if result else "failed"
        order_id = result.get("orderId", "N/A") if result else "N/A"
        passed = "PASS" if "passed" in status or "submitted" in status else "FAIL"
        if passed == "FAIL":
            all_passed = False
        logger.info(f"  {strategy.upper():12} | {passed:4} | Status: {status:20} | Order: {order_id}")
    
    logger.info("=" * 70)
    logger.info(f"Overall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    logger.info(f"Log saved to: test_e2e.log")
    
    return results


if __name__ == "__main__":
    main()
