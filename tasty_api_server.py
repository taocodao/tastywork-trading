"""
TradeMind Tastytrade API Server
================================
Uses the working Python SDK to serve account data via HTTP.
Includes: Account data, Signals, Trade execution
"""


print("DEBUG: Script starting", flush=True)
from http.server import HTTPServer, BaseHTTPRequestHandler
print("DEBUG: HTTP Server imported", flush=True)
import json
import os
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
print("DEBUG: Standard libs imported", flush=True)
from tastytrade import Session, Account
print("DEBUG: tastytrade SDK imported", flush=True)
from tastytrade.instruments import Option, get_option_chain
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType, PriceEffect
from tastytrade_client import TastytradeClient
from tastytrade_utils import create_user_session, get_user_account
from typing import List, Dict, Any, Optional

# ZEBRA Strategy Imports
from src.zebra.client import ZebraClient
from src.zebra.construction_engine import ZebraConstructionEngine


# CRITICAL: Use absolute path for systemd service compatibility
# load_dotenv() without path fails in systemd because it searches relative to Python file location
# See: https://github.com/theskumar/python-dotenv/issues/194
ENV_FILE = '/home/ubuntu/tastywork-trading/.env'
load_dotenv(ENV_FILE)

# Verify critical environment variables are loaded
TASTYTRADE_CLIENT_ID = os.getenv('TASTYTRADE_CLIENT_ID')
TASTYTRADE_CLIENT_SECRET = os.getenv('TASTYTRADE_CLIENT_SECRET')

if not TASTYTRADE_CLIENT_SECRET:
    raise Exception(
        f"CRITICAL: TASTYTRADE_CLIENT_SECRET not loaded from {ENV_FILE}\n"
        f"Check that .env file exists and contains TASTYTRADE_CLIENT_SECRET=..."
    )

print(f"✅ Environment loaded from {ENV_FILE}")
print(f"✅ TASTYTRADE_CLIENT_ID: {TASTYTRADE_CLIENT_ID[:10] if TASTYTRADE_CLIENT_ID else 'NOT SET'}...")
print(f"✅ TASTYTRADE_CLIENT_SECRET: {TASTYTRADE_CLIENT_SECRET[:4] if TASTYTRADE_CLIENT_SECRET else 'NOT SET'}...")

# Validate OAuth credentials at startup
try:
    from credential_enforcement import startup_credential_check
    startup_credential_check()
except ImportError:
    print("⚠️  credential_enforcement.py not found - skipping startup validation")
    print("   This check ensures frontend/backend OAuth credentials match")
except SystemExit:
    # startup_credential_check() calls sys.exit(1) on failure
    raise

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
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
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
            elif self.path == '/api/tracked-positions':
                self.handle_get_tracked_positions()
            elif self.path == '/api/settings/risk-level':
                self.handle_get_risk_level()
            elif self.path == '/api/settings/risk-profiles':
                self.handle_get_risk_profiles()
            elif self.path == '/api/settings/auto-approve':
                self.handle_get_auto_approve_settings()
            elif self.path == '/health':
                self._send_json({'status': 'ok', 'service': 'TradeMind Tastytrade API'})
            # ============================================
            # DIAGONAL SPREAD ROUTES
            # ============================================
            elif self.path == '/diagonal/status':
                self._handle_diagonal_status()
            elif self.path == '/diagonal/universe':
                self._handle_diagonal_universe()
            elif self.path == '/diagonal/signals':
                self._handle_diagonal_signals()
            elif self.path == '/diagonal/signals':
                self._handle_diagonal_signals()
            # =============================================================================
            # ZEBRA STRATEGY ROUTES
            # =============================================================================
            elif self.path == '/api/zebra/scan':
                self._handle_zebra_scan_trigger()
            elif self.path == '/api/zebra/watchlist':
                self._handle_zebra_watchlist_get()
            elif self.path == '/api/zebra/revalidate':
                self._handle_zebra_revalidate()
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
            elif self.path.startswith('/api/positions/') and self.path.endswith('/close'):
                position_id = self.path.split('/')[3]
                self.handle_close_position(position_id, data)
            elif self.path == '/api/trade':
                self.handle_execute_trade(data)
            # ============================================
            # ZEBRA STRATEGY ROUTES
            # ============================================
            elif self.path == '/api/zebra/construct':
                self._handle_zebra_construct(data)
            elif self.path == '/api/zebra/order':
                self._handle_zebra_order(data)
            else:
                self._send_json({'error': 'Not found'}, 404)
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def do_PUT(self):
        """Handle PUT requests."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
            data = json.loads(body)
            
            if self.path == '/api/settings/risk-level':
                self.handle_set_risk_level(data)
            elif self.path == '/api/settings/auto-approve':
                self.handle_set_auto_approve_settings(data)
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

    def handle_get_tracked_positions(self):
        """Return tracked positions from our database (for risk management)."""
        try:
            from src.earnings_intelligence.database import PositionRepository
            repo = PositionRepository()
            
            # Get open positions
            positions = repo.get_open_positions()
            
            # Convert to dicts
            position_dicts = [pos.to_dict() for pos in positions]
            
            self._send_json({
                'positions': position_dicts,
                'total': len(position_dicts),
                'source': 'database'
            })
            
        except Exception as e:
            print(f"Tracked positions loading error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def handle_get_risk_level(self):
        """Get current risk level and profile details."""
        try:
            from pathlib import Path
            import json as json_lib
            
            from src.theta_spreads.risk_profiles import (
                LOW_RISK_PROFILE, MEDIUM_RISK_PROFILE, HIGH_RISK_PROFILE
            )
            
            # Load from settings file
            settings_file = Path("data/theta_settings.json")
            current_level = "MEDIUM"
            if settings_file.exists():
                with open(settings_file) as f:
                    settings = json_lib.load(f)
                    current_level = settings.get("risk_level", "MEDIUM").upper()
            
            def profile_to_dict(profile):
                return {
                    "level": profile.level.value.upper(),
                    "name": profile.name,
                    "description": profile.description,
                    "max_positions": profile.max_positions,
                    "max_capital_deployed_pct": profile.max_capital_deployed_pct,
                    "cash_reserve_pct": profile.cash_reserve_pct,
                    "max_portfolio_heat": profile.max_portfolio_heat,
                    "contracts_per_trade": profile.contracts_per_trade,
                    "breach_confirmation_days": profile.breach_confirmation_days,
                    "vix_block_trading": profile.vix_block_trading,
                    "vix_close_all": profile.vix_close_all,
                    "expected_max_loss_pct": profile.expected_max_loss_pct,
                    "expected_annual_roi_pct": profile.expected_annual_roi_pct,
                    "recovery_time_months": profile.recovery_time_months,
                }
            
            self._send_json({
                "current_level": current_level,
                "profiles": {
                    "LOW": profile_to_dict(LOW_RISK_PROFILE),
                    "MEDIUM": profile_to_dict(MEDIUM_RISK_PROFILE),
                    "HIGH": profile_to_dict(HIGH_RISK_PROFILE),
                }
            })
            
        except Exception as e:
            print(f"Risk level error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def handle_get_risk_profiles(self):
        """Get all risk profiles with summaries for display."""
        try:
            from src.theta_spreads.risk_profiles import (
                LOW_RISK_PROFILE, MEDIUM_RISK_PROFILE, HIGH_RISK_PROFILE
            )
            
            def profile_summary(profile, icon):
                return {
                    "level": profile.level.value.upper(),
                    "name": profile.name,
                    "icon": icon,
                    "description": profile.description,
                    "highlights": {
                        "max_positions": profile.max_positions,
                        "capital_deployed": f"{int(profile.max_capital_deployed_pct * 100)}%",
                        "cash_reserve": f"{int(profile.cash_reserve_pct * 100)}%",
                        "vix_close_all": f">{int(profile.vix_close_all)}",
                        "expected_roi": f"{int(profile.expected_annual_roi_pct * 100)}%",
                        "max_loss": f"-{int(profile.expected_max_loss_pct * 100)}%",
                        "recovery": profile.recovery_time_months
                    }
                }
            
            self._send_json({
                "profiles": [
                    profile_summary(LOW_RISK_PROFILE, "🛡️"),
                    profile_summary(MEDIUM_RISK_PROFILE, "⚖️"),
                    profile_summary(HIGH_RISK_PROFILE, "🚀"),
                ]
            })
            
        except Exception as e:
            print(f"Risk profiles error: {e}")
            self._send_json({'error': str(e)}, 500)

    def handle_set_risk_level(self, data: dict):
        """Set the Theta strategy risk level."""
        try:
            from pathlib import Path
            import json as json_lib
            
            level = data.get("level", "").upper()
            
            if level not in ["LOW", "MEDIUM", "HIGH"]:
                self._send_json({
                    'error': f"Invalid risk level '{level}'. Must be LOW, MEDIUM, or HIGH."
                }, 400)
                return
            
            # Save to settings file
            settings_file = Path("data/theta_settings.json")
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            
            settings = {}
            if settings_file.exists():
                with open(settings_file) as f:
                    settings = json_lib.load(f)
            
            settings["risk_level"] = level
            
            with open(settings_file, 'w') as f:
                json_lib.dump(settings, f, indent=2)
            
            # Also update environment variable for current session
            os.environ["THETA_RISK_LEVEL"] = level
            
            print(f"✅ Risk level changed to: {level}")
            
            self._send_json({
                "status": "success",
                "message": f"Risk level set to {level}",
                "current_level": level
            })
            
        except Exception as e:
            print(f"Set risk level error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)


    def handle_get_auto_approve_settings(self):
        """Get auto-approve settings from local JSON file."""
        try:
            from auto_approve import get_auto_approve_settings
            settings = get_auto_approve_settings()
            
            # Convert to frontend format (camelCase)
            response = {
                "enabled": settings.get("enabled", False),
                "maxDailyTrades": settings.get("max_daily_trades", 5),
                "theta": {
                    "enabled": settings.get("theta", {}).get("enabled", True),
                    "riskLevel": settings.get("theta", {}).get("risk_level", "MEDIUM"),
                    "customOverrides": settings.get("theta", {}).get("custom_overrides", {}),
                },
                "diagonal": {
                    "enabled": settings.get("diagonal", {}).get("enabled", False),
                    "riskLevel": settings.get("diagonal", {}).get("risk_level", "MEDIUM"),
                    "customOverrides": settings.get("diagonal", {}).get("custom_overrides", {}),
                },
            }
            self._send_json(response)
        except Exception as e:
            print(f"Auto-approve settings error: {e}")
            self._send_json({'error': str(e)}, 500)


    def handle_set_auto_approve_settings(self, data: dict):
        """Update auto-approve settings and save to local JSON file."""
        try:
            from auto_approve import get_auto_approve_settings
            import json as json_mod
            from pathlib import Path
            
            # Load current settings
            settings = get_auto_approve_settings()
            
            # Update from request data (handle both camelCase and snake_case)
            if "enabled" in data:
                settings["enabled"] = data["enabled"]
            if "maxDailyTrades" in data or "max_daily_trades" in data:
                settings["max_daily_trades"] = data.get("maxDailyTrades", data.get("max_daily_trades", 5))
            
            # Update theta settings
            if "theta" in data:
                theta = data["theta"]
                settings["theta"]["enabled"] = theta.get("enabled", settings["theta"]["enabled"])
                settings["theta"]["risk_level"] = theta.get("riskLevel", theta.get("risk_level", settings["theta"]["risk_level"]))
                if "customOverrides" in theta or "custom_overrides" in theta:
                    settings["theta"]["custom_overrides"] = theta.get("customOverrides", theta.get("custom_overrides", {}))
            
            # Update diagonal settings
            if "diagonal" in data:
                diag = data["diagonal"]
                settings["diagonal"]["enabled"] = diag.get("enabled", settings["diagonal"]["enabled"])
                settings["diagonal"]["risk_level"] = diag.get("riskLevel", diag.get("risk_level", settings["diagonal"]["risk_level"]))
                if "customOverrides" in diag or "custom_overrides" in diag:
                    settings["diagonal"]["custom_overrides"] = diag.get("customOverrides", diag.get("custom_overrides", {}))
            
            # Save to file
            settings_file = Path("data/auto_approve_settings.json")
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, 'w') as f:
                json_mod.dump(settings, f, indent=2)
            
            print(f"✅ Auto-approve settings updated: enabled={settings['enabled']}, "
                  f"theta={settings['theta']['enabled']}, diagonal={settings['diagonal']['enabled']}")
            
            self._send_json({
                "status": "success",
                "message": "Auto-approve settings updated",
                "settings": settings
            })
            
        except Exception as e:
            print(f"Set auto-approve error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)


    def handle_close_position(self, position_id: str, data: dict):
        """Close a tracked position.
        
        This will:
        1. Look up the position in our database
        2. Build a closing order via Tastytrade
        3. Place the order
        4. Update the position status in our database
        """
        # Extract user credentials
        user_refresh_token = data.get('refreshToken')
        account_number = data.get('accountNumber')
        user_id = data.get('userId', 'anonymous')
        limit_price = data.get('limitPrice')  # Optional limit price override
        
        if not user_refresh_token:
            self._send_json({
                'error': 'Missing user credentials. Please reconnect Tastytrade.',
                'status': 'auth_required'
            }, 401)
            return
        
        try:
            from src.earnings_intelligence.database import PositionRepository
            from tastytrade import Account
            from tastytrade_client import TastytradeClient
            
            pos_repo = PositionRepository()
            
            # Find the position
            position = pos_repo.get_position(position_id)
            
            if not position:
                self._send_json({'error': 'Position not found'}, 404)
                return
            
            if position.status != 'open':
                self._send_json({
                    'error': f'Position already {position.status}',
                    'status': position.status
                }, 400)
                return
            
            # Get user session using their OAuth token
            try:
                user_session = create_user_session(user_refresh_token)
                account = get_user_account(user_session, account_number)
            except ValueError as e:
                self._send_json({
                    'error': str(e),
                    'status': 'auth_error'
                }, 401)
                return
            except Exception as e:
                self._send_json({
                    'error': f'Failed to create session: {str(e)}',
                    'status': 'auth_error'
                }, 401)
                return
            
            # Build the closing order
            client = TastytradeClient()
            client._session = user_session  # Use user's session
            client._account = account
            
            # Get the option symbols from the position
            # front_symbol = short (sold), back_symbol = long (bought)
            short_symbol = position.front_symbol
            long_symbol = position.back_symbol
            quantity = position.quantity
            
            if not short_symbol or not long_symbol:
                self._send_json({
                    'error': 'Position missing option symbols for close order',
                    'status': 'data_error'
                }, 400)
                return
            
            # Build and place the close order
            close_response = client.close_calendar_spread_position(
                short_option_symbol=short_symbol,
                long_option_symbol=long_symbol,
                quantity=quantity,
                limit_price=limit_price,
                dry_run=False
            )
            
            # Extract closing details
            close_order_id = None
            exit_pnl = None
            if hasattr(close_response, 'fee_calculation') and close_response.fee_calculation:
                if hasattr(close_response.fee_calculation, 'order'):
                    close_order_id = str(close_response.fee_calculation.order.id)
                if hasattr(close_response.fee_calculation, 'price'):
                    # Calculate P&L: exit credit - entry debit
                    exit_credit = float(close_response.fee_calculation.price)
                    entry_debit = position.entry_debit or 0
                    exit_pnl = (exit_credit - entry_debit) * (position.quantity or 1) * 100
            
            # Update position in database
            pos_repo.close_position(
                position_id=position_id,
                exit_reason=data.get('reason', 'manual'),
                exit_pnl=exit_pnl or 0,
                exit_order_id=close_order_id
            )
            
            self._send_json({
                'status': 'closed',
                'message': 'Position closed successfully',
                'close_order_id': close_order_id,
                'exit_credit': close_credit,
                'position_id': position_id
            })
            
        except Exception as e:
            print(f"Close position error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def handle_approve_signal(self, signal_id: str, data: dict):
        """Approve a signal and execute the trade using USER's OAuth credentials.
        
        Multi-user design: Each user's execution is tracked separately.
        The signal's global status stays 'pending' so other users can also execute.
        """
        
        # Extract per-user OAuth credentials
        user_refresh_token = data.get('refreshToken')
        account_number = data.get('accountNumber')
        user_id = data.get('userId', 'anonymous')  # Frontend should pass Privy user ID
        execute = data.get('execute', True)
        
        if not user_refresh_token:
            self._send_json({
                'error': 'Missing user credentials. Please reconnect Tastytrade.',
                'status': 'auth_required'
            }, 401)
            return
        
        try:
            from src.earnings_intelligence.database import SignalRepository, UserSignalRepository
            signal_repo = SignalRepository()
            user_repo = UserSignalRepository()
            
            # Find the signal
            signal = signal_repo.get_signal(signal_id)
            
            if not signal:
                self._send_json({'error': 'Signal not found'}, 404)
                return
            
            # Check if signal is expired
            if signal.is_expired():
                self._send_json({
                    'error': 'Signal has expired',
                    'status': 'expired'
                }, 400)
                return
            
            # Check if this user already executed this signal
            existing_execution = user_repo.get_user_execution(user_id, signal_id)
            if existing_execution and existing_execution.status == 'executed':
                self._send_json({
                    'error': 'You have already executed this signal',
                    'status': 'already_executed',
                    'execution': existing_execution.to_dict()
                }, 400)
                return
            
            # Get signal data for execution
            signal_data = signal.to_dict()
            
            response_data = {
                'status': 'approved',
                'signal': signal_data,
                'message': 'Signal approved, executing trade...'
            }
            
            # Track user's approval
            user_execution = user_repo.create_or_update_execution(
                user_id=user_id,
                signal_id=signal_id,
                status='approved'
            )

            if execute:
                try:
                    # Execute using USER's session (not master account!)
                    result = self._execute_calendar_spread_for_user(
                        signal_data, 
                        user_refresh_token, 
                        account_number
                    )
                    
                    # Update user's execution status (NOT the global signal status!)
                    user_repo.create_or_update_execution(
                        user_id=user_id,
                        signal_id=signal_id,
                        status='executed',
                        order_id=result.get('orderId')
                    )
                    
                    execution_count = user_repo.get_signal_execution_count(signal_id)
                    
                    response_data = {
                        'status': 'executed',
                        'signal': signal_data,
                        'order': result,
                        'executionCount': execution_count,
                        'message': f"Calendar spread on {signal.symbol} submitted to YOUR account!"
                    }
                except Exception as e:
                    # Update user's execution status to failed
                    user_repo.create_or_update_execution(
                        user_id=user_id,
                        signal_id=signal_id,
                        status='failed',
                        error_message=str(e)
                    )
                    
                    response_data = {
                        'status': 'failed',
                        'signal': signal_data,
                        'error': str(e),
                        'message': f"Trade failed: {str(e)}"
                    }
            
            # Note: We do NOT update the Signal's global status anymore
            # The signal stays 'pending' so other users can execute it too
                
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
            from tastytrade.order import NewOrder
            
            # Create per-user session using shared utility (session-per-task pattern)
            session = create_user_session(user_refresh_token)
            print(f"✅ Created session for user (expires: {session.session_expiration})")
            
            # Get user's account using shared utility
            account = get_user_account(session, account_number)
            account_number = account.account_number
            print(f"📊 Using account: {account_number}")
            
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
            
            # ✅ FETCH LIVE PRICES FROM IB GATEWAY - Critical fix for order fills!
            try:
                from ib_data_provider import IBDataProvider
                ib_data = IBDataProvider()
                
                # Get live quotes for both legs
                short_quote = ib_data.get_option_price_by_symbol(short_symbol.strip())
                long_quote = ib_data.get_option_price_by_symbol(long_symbol.strip())
                
                if short_quote and long_quote:
                    # Calendar spread: SELL front (bid), BUY back (ask)
                    # Net debit = back ask - front bid
                    net_debit = long_quote[1] - short_quote[0]  # ask - bid
                    price = round(net_debit, 2)
                    print(f"✅ Using LIVE IB prices: Sell @ ${short_quote[0]:.2f} / Buy @ ${long_quote[1]:.2f}")
                    print(f"   Net debit: ${price:.2f}")
                else:
                    # Fallback to signal price with warning
                    price = signal.get('cost', 2.50)
                    print(f"⚠️ Could not fetch IB quotes, using signal price: ${price}")
            except Exception as ib_err:
                print(f"⚠️ IB data fetch failed: {ib_err}, using signal price")
                price = signal.get('cost', 2.50)
            
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
            
            # Save position to database for risk management tracking
            try:
                from src.earnings_intelligence.database import PositionRepository
                from datetime import datetime as dt
                
                position_data = {
                    'order_id': order_id,
                    'user_id': signal.get('userId', 'unknown'),
                    'signal_id': signal.get('id'),
                    'symbol': symbol,
                    'strategy': 'Calendar Spread',
                    'front_expiry': dt.fromisoformat(front_expiry) if front_expiry else None,
                    'back_expiry': dt.fromisoformat(back_expiry) if back_expiry else None,
                    'strike': strike,
                    'quantity': 1,
                    'front_symbol': short_symbol.strip(),
                    'back_symbol': long_symbol.strip(),
                    'entry_debit': price,
                    'entry_stock_price': signal.get('stockPrice'),
                }
                
                pos_repo = PositionRepository()
                pos_repo.save_position(position_data)
                print(f"📊 Position saved for risk management: {order_id}")
                
            except Exception as pos_err:
                print(f"⚠️ Could not save position (non-blocking): {pos_err}")
            
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

    # ========================================================================
    # DIAGONAL SPREAD HANDLERS
    # ========================================================================
    
    def _handle_diagonal_status(self):
        """
        Get circuit breaker status for diagonal spreads.
        
        Returns VIX-VXV term structure analysis:
        - can_trade: Boolean - whether trading is allowed
        - regime: contango/flat/backwardation
        - early_warning: True when ratio > 0.95
        """
        try:
            from src.diagonal_spreads import check_term_structure_circuit_breaker
            status = check_term_structure_circuit_breaker()
            
            self._send_json({
                'regime': str(status.regime.value),
                'can_trade': bool(status.can_trade),
                'vix': float(round(status.vix, 2)),
                'vxv': float(round(status.vxv, 2)),
                'diff': float(round(status.diff, 2)),
                'ratio': float(round(status.ratio, 4)),
                'early_warning': bool(status.early_warning),
                'position_multiplier': float(status.position_size_multiplier),
                'message': str(status.message),
                'timestamp': status.timestamp.isoformat() if status.timestamp else None
            })
        except Exception as e:
            print(f"Error in diagonal status: {e}")
            import traceback
            traceback.print_exc()
            # Return safe default on error
            self._send_json({
                'regime': 'unknown',
                'can_trade': False,
                'vix': 0,
                'vxv': 0,
                'diff': 0,
                'ratio': 1.0,
                'early_warning': True,
                'position_multiplier': 0,
                'message': f'Error checking circuit breaker: {str(e)}',
                'timestamp': None
            }, 500)
    
    def _handle_diagonal_universe(self):
        """
        Get the ETF universe for diagonal spreads.
        
        Returns tiered universe with symbols grouped by allocation.
        """
        try:
            from src.diagonal_spreads import get_etf_universe, LiquidityScreener
            
            universe = get_etf_universe()
            screener = LiquidityScreener()
            
            # Get symbols by tier
            tier1 = [s for s, info in universe.securities.items() if info.tier == 1]
            tier2 = [s for s, info in universe.securities.items() if info.tier == 2]
            tier3 = [s for s, info in universe.securities.items() if info.tier == 3]
            
            self._send_json({
                'total_symbols': len(universe.get_all_symbols()),
                'tiers': {
                    'tier1_core': {
                        'symbols': tier1,
                        'count': len(tier1),
                        'allocation': '60-70%',
                        'description': 'Always included, no earnings risk'
                    },
                    'tier2_rotation': {
                        'symbols': tier2,
                        'count': len(tier2),
                        'allocation': '20-25%',
                        'description': 'Sector rotation, quarterly updates'
                    },
                    'tier3_opportunistic': {
                        'symbols': tier3,
                        'count': len(tier3),
                        'allocation': '5-15%',
                        'description': 'High IV opportunities only'
                    }
                },
                'iv_floors': screener.asset_class_iv_floors,
                'prioritized_scan_list': universe.get_prioritized_scan_list(
                    include_tier2=True, include_tier3=False
                )
            })
        except Exception as e:
            print(f"Error in diagonal universe: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)
    
    def _handle_diagonal_signals(self):
        """
        Get current diagonal spread opportunities.
        
        Combines circuit breaker check with universe filtering.
        """
        try:
            from src.diagonal_spreads import check_term_structure_circuit_breaker, get_etf_universe
            
            # Check circuit breaker first
            status = check_term_structure_circuit_breaker()
            
            if not status.can_trade:
                self._send_json({
                    'signals': [],
                    'circuit_breaker': {
                        'blocked': True,
                        'reason': status.message,
                        'regime': status.regime.value
                    },
                    'message': 'Trading halted by circuit breaker'
                })
                return
            
            # Get universe
            universe = get_etf_universe()
            scan_list = universe.get_prioritized_scan_list(include_tier2=True)
            
            # For now, return placeholder signals (real signals come from scheduler)
            signals = []
            for symbol in scan_list[:5]:  # Top 5 for display
                signals.append({
                    'id': f'diag-{symbol.lower()}-{status.timestamp.strftime("%Y%m%d") if status.timestamp else "today"}',
                    'symbol': symbol,
                    'strategy': 'diagonal_spread',
                    'status': 'opportunity',
                    'direction': 'bullish',
                    'term_structure': status.regime.value,
                    'position_size_multiplier': status.position_size_multiplier
                })
            
            self._send_json({
                'signals': signals,
                'circuit_breaker': {
                    'blocked': False,
                    'regime': status.regime.value,
                    'ratio': status.ratio,
                    'early_warning': status.early_warning
                },
                'total_symbols_available': len(scan_list)
            })
        except Exception as e:
            print(f"Error in diagonal signals: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)


    def _handle_zebra_candidates(self):
        """Return pending ZEBRA strategy signals from database."""
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            
            # Fetch all signals
            all_signals = repo.get_all_signals()
            
            # Filter for ZEBRA strategy and pending status
            zebra_signals = [
                s.to_dict() for s in all_signals 
                if s.strategy.lower() == 'zebra' and s.status == 'pending'
            ]
            
            self._send_json({
                'candidates': zebra_signals,
                'total': len(zebra_signals),
                'source': 'database'
            })
            
        except Exception as e:
            print(f"ZEBRA candidates error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def _handle_zebra_construct(self, data: dict):
        """Construct ZEBRA trade structures for a given symbol."""
        try:
            symbol = data.get('symbol')
            if not symbol:
                self._send_json({'error': 'Symbol required'}, 400)
                return

            direction = data.get('direction', 'LONG').upper()
            horizon = int(data.get('horizon', 30))
            
            # Use global session for construction (market data only)
            session = get_session()
            if not session:
                self._send_json({'error': 'Market data session unavailable'}, 503)
                return
                
            # Initialize Client & Engine
            client = ZebraClient()
            client._session = session
            
            # Create engine
            engine = ZebraConstructionEngine(client)
            
            # Fetch price
            price = client.get_stock_price(symbol)
            if price <= 0:
                self._send_json({'error': f'Could not fetch price for {symbol}'}, 404)
                return

            print(f"Constructing ZEBRA for {symbol} @ ${price:.2f} ({direction})")
            
            # Construct
            structures = engine.construct(
                symbol=symbol,
                stock_price=price,
                thesis_horizon_days=horizon,
                direction=direction
            )
            
            # Serialize structures
            serialized = []
            for s in structures:
                s_dict = {
                    'symbol': s.symbol,
                    'direction': s.direction,
                    'expiry': s.expiry.isoformat(),
                    'dte': s.dte,
                    'net_debit': float(s.net_debit),
                    'max_loss': float(s.max_loss),
                    'breakeven': float(s.breakeven),
                    'net_delta': float(s.net_delta),
                    'net_theta': float(s.net_theta),
                    'net_eval': float(s.net_extrinsic),
                    'construction_score': float(s.construction_score),
                    'legs': [
                        {
                            'side': 'md_long',
                            'strike': float(s.long_leg.strike),
                            'option_type': s.long_leg.option_type,
                            'quantity': 2,
                            'delta': float(s.long_leg.delta or 0)
                        },
                        {
                            'side': 'md_short',
                            'strike': float(s.short_leg.strike),
                            'option_type': s.short_leg.option_type,
                            'quantity': 1,
                            'delta': float(s.short_leg.delta or 0)
                        }
                    ]
                }
                serialized.append(s_dict)
                
            self._send_json({
                'symbol': symbol,
                'price': price,
                'count': len(serialized),
                'structures': serialized
            })
            
        except Exception as e:
            print(f"ZEBRA verify error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def _handle_zebra_order(self, data: dict):
        """Execute a ZEBRA trade for a user."""
        try:
            # Extract credentials
            user_refresh_token = data.get('refreshToken')
            account_number = data.get('accountNumber')
            
            if not user_refresh_token:
                self._send_json({'error': 'Missing user credentials'}, 401)
                return
            
            # Extract trade parameters
            symbol = data.get('symbol')
            long_strike = float(data.get('longStrike', 0))
            short_strike = float(data.get('shortStrike', 0))
            expiry_str = data.get('expiry')
            direction = data.get('direction', 'LONG')
            quantity = int(data.get('quantity', 1))
            limit_price = float(data.get('limitPrice', 0)) if data.get('limitPrice') else None
            
            if not (symbol and long_strike and short_strike and expiry_str):
                self._send_json({'error': 'Missing trade parameters'}, 400)
                return
                
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            
            # Authenticate User
            try:
                user_session = create_user_session(user_refresh_token)
                account = get_user_account(user_session, account_number)
            except Exception as e:
                self._send_json({'error': str(e)}, 401)
                return
                
            # Initialize Client with User Session
            client = ZebraClient()
            client._session = user_session
            client._account = account
            
            # Execute
            print(f"Executing ZEBRA {symbol} {direction} for account {account.account_number}")
            order_response = client.execute_zebra_entry(
                symbol=symbol,
                long_strike=long_strike,
                short_strike=short_strike,
                expiry=expiry,
                direction=direction,
                quantity=quantity,
                limit_price=limit_price,
                dry_run=False
            )
            
            # Extract order ID if possible
            order_id = None
            if hasattr(order_response, 'id'):
                order_id = str(order_response.id)
            elif isinstance(order_response, dict) and 'id' in order_response:
                order_id = str(order_response['id'])
                
            self._send_json({
                'status': 'submitted',
                'symbol': symbol,
                'order_id': order_id,
                'message': 'ZEBRA order submitted successfully'
            })
            
        except Exception as e:
            print(f"ZEBRA execution error: {e}")
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)


def run_server(port=8002):
    print(f"🚀 Starting TradeMind API server on port {port}")
    print(f"   Account: http://localhost:{port}/api/account")
    print(f"   Signals: http://localhost:{port}/api/signals")
    print(f"   Trade:   POST http://localhost:{port}/api/trade")
    print(f"   ── Diagonal Spreads ──")
    print(f"   Status:   http://localhost:{port}/diagonal/status")
    print(f"   Universe: http://localhost:{port}/diagonal/universe")
    print(f"   Signals:  http://localhost:{port}/diagonal/signals")
    
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
    try:
        run_server()
    except Exception as e:
        import traceback
        with open('server_crash.log', 'w') as f:
            f.write(f"Server crashed: {e}\n")
            traceback.print_exc(file=f)
        print(f"CRITICAL ERROR: {e}")


