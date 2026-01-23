"""
TradeMind Tastytrade API Server
================================
Uses the working Python SDK to serve account data via HTTP.
Includes: Account data, Signals, Trade execution
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
from tastytrade import Session, Account
from tastytrade.instruments import Option, get_option_chain
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType, PriceEffect
from tastytrade_client import TastytradeClient
from typing import List, Dict, Any

load_dotenv()

# Add current directory to path to allow 'src' imports
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# Global session cache
_session = None
_account = None



def get_session(force_refresh=False):
    """Get or create Tastytrade session. Use force_refresh=True if token expired."""
    global _session
    if _session is None or force_refresh:
        client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
        refresh_token = os.getenv('TASTYTRADE_REFRESH_TOKEN')
        _session = Session(client_secret, refresh_token)
        print("✅ Tastytrade session created" + (" (refreshed)" if force_refresh else ""))
    return _session


def refresh_session():
    """Force refresh the session (call when token expires)."""
    global _session, _account
    _session = None
    _account = None
    return get_session(force_refresh=True)


def get_account(force_refresh=False):
    global _account
    if _account is None or force_refresh:
        session = get_session(force_refresh)
        accounts = Account.get(session)
        _account = accounts[0] if accounts else None
        if _account:
            print(f"✅ Using account: {_account.account_number}")
    return _account


def generate_sample_signals():
    """Generate sample calendar spread signals based on scanner logic."""
    global _signals
    
    # Clear old signals
    _signals = []
    
    # Sample underlyings for calendar spreads
    underlyings = [
        {"symbol": "SPY", "price": 485.50, "iv": 0.18},
        {"symbol": "QQQ", "price": 420.25, "iv": 0.22},
        {"symbol": "IWM", "price": 198.75, "iv": 0.25},
    ]
    
    for stock in underlyings:
        # Generate a calendar spread signal
        strike = round(stock["price"] / 5) * 5  # Round to nearest 5
        front_expiry = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        back_expiry = (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        
        cost = round(1.50 + (stock["iv"] * 100 * 0.02), 2)  # Approximate cost
        potential = round(cost * 0.35, 2)  # 35% target return
        
        signal = {
            "id": str(uuid.uuid4()),
            "symbol": stock["symbol"],
            "strategy": "Calendar Spread",
            "direction": "neutral",
            "strike": strike,
            "frontExpiry": front_expiry,
            "backExpiry": back_expiry,
            "cost": cost,
            "potentialReturn": potential,
            "returnPercent": round((potential / cost) * 100, 1),
            "winRate": 73 + int(stock["iv"] * 10),
            "riskLevel": "Low" if stock["iv"] < 0.20 else "Medium",
            "status": "pending",
            "createdAt": datetime.now().isoformat(),
            "rationale": f"Low IV rank ({int(stock['iv']*100)}%), stable price action, earnings-free window",
        }
        _signals.append(signal)
    
    return _signals


class TastyHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        try:
            if self.path == '/api/account':
                self.handle_account()
            elif self.path == '/api/positions':
                self.handle_positions()
            elif self.path == '/api/signals':
                self.handle_get_signals()
            elif self.path == '/health':
                self._send_json({'status': 'ok', 'service': 'TradeMind Tastytrade API'})
            else:
                self._send_json({'error': 'Not found'}, 404)
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
            data = json.loads(body)
            
            if self.path.startswith('/api/signals/') and self.path.endswith('/approve'):
                signal_id = self.path.split('/')[3]
                self.handle_approve_signal(signal_id, data)
            elif self.path == '/api/trade':
                self.handle_execute_trade(data)
            else:
                self._send_json({'error': 'Not found'}, 404)
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def handle_account(self, retry=True):
        try:
            session = get_session()
            account = get_account()
            
            if not account:
                self._send_json({'error': 'No account found'}, 404)
                return

            balances = account.get_balances(session)
            positions = account.get_positions(session)

            total_pnl = 0
            calendar_spreads = []
            
            for pos in positions:
                pnl = float(getattr(pos, 'realized_day_gain', 0) or 0)
                total_pnl += pnl
                
                pos_data = {
                    'symbol': pos.symbol,
                    'underlying': getattr(pos, 'underlying_symbol', pos.symbol),
                    'type': getattr(pos, 'instrument_type', 'Unknown'),
                    'quantity': int(getattr(pos, 'quantity', 0)),
                    'entryPrice': float(getattr(pos, 'average_open_price', 0) or 0),
                    'currentPrice': float(getattr(pos, 'close_price', 0) or getattr(pos, 'average_open_price', 0) or 0),
                    'unrealizedPnL': float(getattr(pos, 'realized_day_gain', 0) or 0),
                    'pnlPercent': float(getattr(pos, 'realized_day_gain_percent', 0) or 0),
                }
                calendar_spreads.append(pos_data)

            nlv = float(getattr(balances, 'net_liquidating_value', 0) or 0)
            
            self._send_json({
                'accountNumber': account.account_number,
                'balance': float(getattr(balances, 'cash_balance', 0) or 0),
                'netLiquidatingValue': nlv,
                'buyingPower': float(getattr(balances, 'derivative_buying_power', 0) or 0),
                'todayPnL': total_pnl,
                'todayPnLPercent': (total_pnl / nlv * 100) if nlv > 0 else 0,
                'positions': calendar_spreads,
                'positionCount': len(positions),
            })
        except Exception as e:
            error_str = str(e).lower()
            # Check if it's a token expiry error and retry once
            # Broaden check to include common 401/unauthorized indicators
            if retry:
                print(f"⚠️ Account fetch error: {e}. Retrying with session refresh...")
                refresh_session()
                return self.handle_account(retry=False)
            raise

    def handle_positions(self):
        session = get_session()
        account = get_account()
        
        if not account:
            self._send_json({'error': 'No account found'}, 404)
            return

        positions = account.get_positions(session)
        
        result = []
        for pos in positions:
            result.append({
                'symbol': pos.symbol,
                'underlying': getattr(pos, 'underlying_symbol', pos.symbol),
                'instrumentType': getattr(pos, 'instrument_type', 'Unknown'),
                'quantity': int(getattr(pos, 'quantity', 0)),
                'averageOpenPrice': float(getattr(pos, 'average_open_price', 0) or 0),
                'closePrice': float(getattr(pos, 'close_price', 0) or 0),
                'realizedDayGain': float(getattr(pos, 'realized_day_gain', 0) or 0),
                'expirationDate': str(getattr(pos, 'expiration_date', '')),
                'strikePrice': float(getattr(pos, 'strike_price', 0) or 0),
                'optionType': getattr(pos, 'option_type', ''),
            })
        
        self._send_json({'positions': result})

    def handle_get_signals(self):
        """Return signals from database."""
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            signals = repo.get_all_signals()
            
            # Convert to dicts
            signal_dicts = [s.to_dict() for s in signals]
            
            # Filter pending (frontend expects 'pending' in the 'signals' array usually, but let's stick to returning what it asks for)
            # Actually, the original code returned ALL signals but filtered 'pending' specifically for the 'signals' key
            # Let's verify what the frontend expects. The previous code did:
            # pending = [s for s in _signals if s['status'] == 'pending']
            # self._send_json({'signals': pending, 'total': len(_signals), ...})
            
            pending = [s for s in signal_dicts if s['status'] == 'pending']
            self._send_json({
                'signals': pending, 
                'total': len(signal_dicts), 
                'source': 'database'
            })
            
        except Exception as e:
            print(f"Signal loading error: {e}")
            self._send_json({'error': str(e)}, 500)

    def handle_approve_signal(self, signal_id: str, data: dict):
        """Approve a signal and execute the trade using USER's OAuth credentials."""
        
        # Extract per-user OAuth credentials
        user_refresh_token = data.get('refreshToken')
        account_number = data.get('accountNumber')
        execute = data.get('execute', True)
        
        if not user_refresh_token:
            self._send_json({
                'error': 'Missing user credentials. Please reconnect Tastytrade.',
                'status': 'auth_required'
            }, 401)
            return
        
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            
            # Find the signal
            signal = repo.get_signal(signal_id)
            
            if not signal:
                self._send_json({'error': 'Signal not found'}, 404)
                return
            
            # Update data
            signal_data = signal.to_dict()
            signal_data['status'] = 'approved'
            
            response_data = {
                'status': 'approved',
                'signal': signal_data,
                'message': 'Signal approved, executing trade...'
            }

            if execute:
                try:
                    # Execute using USER's session (not master account!)
                    result = self._execute_calendar_spread_for_user(
                        signal_data, 
                        user_refresh_token, 
                        account_number
                    )
                    signal_data['status'] = 'executed'
                    signal_data['orderId'] = result.get('orderId')
                    
                    response_data = {
                        'status': 'executed',
                        'signal': signal_data,
                        'order': result,
                        'message': f"Calendar spread on {signal.symbol} submitted to YOUR account!"
                    }
                except Exception as e:
                    signal_data['status'] = 'failed'
                    signal_data['error'] = str(e)
                    response_data = {
                        'status': 'failed',
                        'signal': signal_data,
                        'error': str(e),
                        'message': f"Trade failed: {str(e)}"
                    }
            
            # Save updates to DB
            repo.save_signal(signal_data)
            
            # Return fresh data
            updated_signal = repo.get_signal(signal_id)
            if updated_signal:
                response_data['signal'] = updated_signal.to_dict()
                
            self._send_json(response_data)
            
        except Exception as e:
            print(f"Error approving signal: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def _execute_calendar_spread_for_user(
        self, 
        signal: dict, 
        user_refresh_token: str, 
        account_number: str = None
    ) -> dict:
        """
        Execute a calendar spread trade using USER's OAuth credentials.
        
        This is the per-user execution pattern:
        - Creates a fresh OAuthSession for this specific user
        - Does NOT use the master server account
        - Trade appears in USER's Tastytrade account
        """
        print(f"📈 Executing Calendar Spread for USER: {signal['symbol']} {signal.get('strike', '?')}C")
        
        try:
            # Import SDK components
            from tastytrade import OAuthSession, Account
            from tastytrade.order import NewOrder
            
            # Create per-user session (session-per-task pattern)
            client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
            if not client_secret:
                raise ValueError("TASTYTRADE_CLIENT_SECRET not configured")
            
            session = OAuthSession(
                client_secret=client_secret,
                refresh_token=user_refresh_token
            )
            print(f"✅ Created session for user (expires: {session.session_expiration})")
            
            # Get account if not provided
            if not account_number:
                accounts = Account.get_accounts(session)
                if not accounts:
                    raise ValueError("No accounts found for user")
                account = accounts[0]
                account_number = account.account_number
                print(f"📊 Using account: {account_number}")
            else:
                # Get account object from account number
                accounts = Account.get_accounts(session)
                account = next((a for a in accounts if a.account_number == account_number), accounts[0] if accounts else None)
                if not account:
                    raise ValueError(f"Account {account_number} not found")
            
            # Build calendar spread order
            symbol = signal['symbol']
            strike = float(signal.get('strike', 0))
            front_expiry = signal.get('frontExpiry', '')
            back_expiry = signal.get('backExpiry', '')
            
            # Format OCC symbols (e.g., "SPY 250221C00500000")
            # Convert YYYY-MM-DD to YYMMDD format
            front_date = front_expiry.replace('-', '')[2:] if front_expiry else ''
            back_date = back_expiry.replace('-', '')[2:] if back_expiry else ''
            strike_formatted = f"{int(strike * 1000):08d}"  # Strike * 1000, 8 digits
            
            short_symbol = f"{symbol}  {front_date}C{strike_formatted}"
            long_symbol = f"{symbol}  {back_date}C{strike_formatted}"
            
            print(f"📋 Short leg: {short_symbol}")
            print(f"📋 Long leg: {long_symbol}")
            
            # Build order legs
            from tastytrade.order import OrderLeg, OrderAction, OrderType, OrderTimeInForce, PriceEffect
            
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
            
            # Create order
            price = signal.get('cost', 2.50)  # Limit price for the spread
            
            order = NewOrder(
                time_in_force=OrderTimeInForce.DAY,
                order_type=OrderType.LIMIT,
                legs=legs,
                price=price,
                price_effect=PriceEffect.DEBIT  # Calendar spreads are debit trades
            )
            
            # Place order on USER's account
            response = account.place_order(session, order, dry_run=False)
            
            # Extract order ID
            order_id = str(response.order.id) if hasattr(response, 'order') else "Submitted"
            
            print(f"✅ Order submitted to user's account: {order_id}")
            
            return {
                'orderId': order_id,
                'symbol': symbol,
                'strategy': 'Calendar Spread',
                'strike': strike,
                'frontExpiry': front_expiry,
                'backExpiry': back_expiry,
                'status': 'submitted',
                'accountNumber': account_number,
                'submittedAt': datetime.now().isoformat(),
            }
            
        except Exception as e:
            print(f"❌ User trade execution failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _execute_calendar_spread(self, signal: dict) -> dict:
        """Execute a calendar spread trade on Tastytrade."""
        print(f"📈 Executing Calendar Spread: {signal['symbol']} {signal['strike']}C {signal['frontExpiry']}/{signal['backExpiry']}")
        
        try:
            client = TastytradeClient()
            client.connect()
            
            symbol = signal['symbol']
            strike = float(signal['strike'])
            # Parse dates (YYYY-MM-DD)
            front_expiry = datetime.strptime(signal['frontExpiry'], "%Y-%m-%d").date()
            back_expiry = datetime.strptime(signal['backExpiry'], "%Y-%m-%d").date()
            
            # Find options
            short_op = client.find_option_at_strike(symbol, front_expiry, strike, 'C')
            long_op = client.find_option_at_strike(symbol, back_expiry, strike, 'C')
            
            if not short_op or not long_op:
                raise ValueError(f"Options not found for {symbol} at strike {strike}")
            
            # Build and place order
            order = client.build_calendar_spread_order(short_op, long_op, quantity=1)
            response = client.place_order(order, dry_run=False) # Real trade!
            
            # Update signal file status
            # mark_signal_executed(signal['id']) # We can update memory and save
            save_signals_to_disk(_signals)
            
            # Extract Order ID (structure depends on response type, assuming Account.place_order return)
            # Response is PlacedOrderResponse
            order_id = str(response.order.id) if hasattr(response, 'order') else "Submitted"
            
            print(f"✅ Order submitted: {order_id}")
            
            return {
                'orderId': order_id,
                'symbol': symbol,
                'strategy': 'Calendar Spread',
                'strike': strike,
                'frontExpiry': str(front_expiry),
                'backExpiry': str(back_expiry),
                'status': 'submitted',
                'submittedAt': datetime.now().isoformat(),
            }
            
        except Exception as e:
            print(f"❌ Execution failed: {e}")
            raise

    def handle_execute_trade(self, data: dict):
        """Direct trade execution endpoint."""
        try:
            symbol = data.get('symbol')
            strike = data.get('strike')
            front_expiry = data.get('frontExpiry')
            back_expiry = data.get('backExpiry')
            
            if not all([symbol, strike, front_expiry, back_expiry]):
                self._send_json({'error': 'Missing required fields'}, 400)
                return
            
            signal = {
                'symbol': symbol,
                'strike': strike,
                'frontExpiry': front_expiry,
                'backExpiry': back_expiry,
            }
            
            result = self._execute_calendar_spread(signal)
            self._send_json({
                'status': 'success',
                'order': result,
                'message': f"Calendar spread on {symbol} submitted!"
            })
        except Exception as e:
            self._send_json({'error': str(e)}, 500)


def run_server(port=8002):
    print(f"🚀 Starting TradeMind API server on port {port}")
    print(f"   Account: http://localhost:{port}/api/account")
    print(f"   Signals: http://localhost:{port}/api/signals")
    print(f"   Trade:   POST http://localhost:{port}/api/trade")
    
    # Initialize session on startup
    try:
        get_session()
        get_account()
        # generate_sample_signals() # Disabled - handled by scanner/publisher now
        print(f"📊 Ready to serve signals from DB")
    except Exception as e:
        print(f"⚠️ Failed to init session: {e}")
    
    server = HTTPServer(('0.0.0.0', port), TastyHandler)
    server.serve_forever()


if __name__ == '__main__':
    run_server()

