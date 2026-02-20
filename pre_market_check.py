"""
Pre-Market Readiness Check
===========================
Comprehensive system check before market open.
"""
import sys
import os

# Fix encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

results = []

def check(name, status, detail=""):
    icon = "PASS" if status else "FAIL"
    msg = f"[{icon}] {name}: {detail}"
    print(msg)
    results.append((name, status, detail))

print("=" * 60)
print("PRE-MARKET READINESS CHECK")
print(f"Time: {__import__('datetime').datetime.now()}")
print("=" * 60)

# 1. Python Version
print("\n--- SYSTEM ---")
check("Python Version", True, sys.version.split()[0])

# 2. Critical Imports
print("\n--- IMPORTS ---")
for mod_name in ['ib_insync', 'requests', 'websockets', 'psycopg2', 'sqlalchemy']:
    try:
        m = __import__(mod_name)
        v = getattr(m, '__version__', 'installed')
        check(f"Import {mod_name}", True, v)
    except ImportError as e:
        check(f"Import {mod_name}", False, str(e))

# 3. Signal Publisher
print("\n--- SIGNAL PUBLISHER ---")
try:
    from signal_publisher import publish_zebra_entry_signal, publish_theta_entry_signal
    check("Signal Publisher (Theta)", True, "imported")
    check("Signal Publisher (ZEBRA)", True, "imported")
except Exception as e:
    check("Signal Publisher", False, str(e))

try:
    from signal_publisher.dvo import publish_dvo_entry_signal
    check("Signal Publisher (DVO)", True, "imported")
except Exception as e:
    check("Signal Publisher (DVO)", False, str(e))

try:
    from signal_publisher.calendar import publish_calendar_signal
    check("Signal Publisher (Calendar)", True, "imported")
except Exception as e:
    check("Signal Publisher (Calendar)", False, str(e))

# 4. Config
print("\n--- CONFIG ---")
try:
    import config
    check("Config loaded", True)
    check("Theta Universe", True, f"{len(config.THETA_UNIVERSE)} symbols")
    check("ZEBRA Enabled", config.ZEBRA_ENABLED, str(config.ZEBRA_ENABLED))
    check("ZEBRA Watchlist", True, f"{len(config.ZEBRA_WATCHLIST)} symbols")
    check("ZEBRA Auto-Trade", True, f"{'ON' if config.ZEBRA_AUTO_TRADE else 'OFF (manual approval)'}")
    check("Tastytrade Client ID", bool(config.TASTYTRADE_CLIENT_ID), 
          config.TASTYTRADE_CLIENT_ID[:8] + "..." if config.TASTYTRADE_CLIENT_ID else "MISSING")
    check("Tastytrade Client Secret", bool(config.TASTYTRADE_CLIENT_SECRET),
          config.TASTYTRADE_CLIENT_SECRET[:8] + "..." if config.TASTYTRADE_CLIENT_SECRET else "MISSING")
    check("Tastytrade Refresh Token", bool(config.TASTYTRADE_REFRESH_TOKEN),
          config.TASTYTRADE_REFRESH_TOKEN[:20] + "..." if config.TASTYTRADE_REFRESH_TOKEN else "MISSING")
    check("Perplexity API Key", bool(config.PERPLEXITY_API_KEY),
          "configured" if config.PERPLEXITY_API_KEY else "MISSING")
except Exception as e:
    check("Config", False, str(e))

# 5. Database
print("\n--- DATABASE ---")
try:
    db_url = os.getenv('DATABASE_URL', '')
    if not db_url:
        try:
            db_url = config.DATABASE_URL
        except:
            pass
    check("DATABASE_URL", bool(db_url), "configured" if db_url else "MISSING")
except:
    pass

try:
    from src.earnings_intelligence.database import SignalRepository
    repo = SignalRepository()
    check("SignalRepository", True, "connected")
    
    # Check for active signals
    try:
        signals = repo.get_active_signals()
        check("Active Signals", True, f"{len(signals)} signals in DB")
        for s in signals[:5]:
            sym = s.get('symbol', '?')
            strat = s.get('strategy', '?')
            status = s.get('status', '?')
            print(f"        {sym} ({strat}) - {status}")
    except Exception as e:
        check("Active Signals query", False, str(e))
except Exception as e:
    check("Database Connection", False, str(e))

# 6. EC2 API Server
print("\n--- EC2 API SERVER ---")
try:
    import requests
    r = requests.get('http://34.235.119.67:8002/account', timeout=10)
    if r.status_code == 200:
        d = r.json()
        acct = d.get('account_number', 'N/A')
        nl = d.get('net_liq', d.get('cash_balance', 'N/A'))
        check("API Server (Account)", True, f"Account: {acct}, Net Liq: ${nl}")
    else:
        check("API Server (Account)", False, f"Status {r.status_code}")
except requests.exceptions.ConnectionError:
    check("API Server", False, "Connection refused - server may be down")
except requests.exceptions.Timeout:
    check("API Server", False, "Timeout - server may be unresponsive")
except Exception as e:
    check("API Server", False, str(e))

# 7. EC2 Positions
try:
    r = requests.get('http://34.235.119.67:8002/positions', timeout=10)
    if r.status_code == 200:
        d = r.json()
        pos = d.get('positions', [])
        check("Positions Endpoint", True, f"{len(pos)} open positions")
    else:
        check("Positions Endpoint", False, f"Status {r.status_code}")
except Exception as e:
    check("Positions Endpoint", False, str(e))

# 8. WebSocket Server
print("\n--- WEBSOCKET SERVER ---")
try:
    r = requests.post('http://34.235.119.67:8004/', json={"channel": "ping", "signal": {}}, timeout=5)
    check("WS Broadcast (EC2 :8004)", True, f"Status {r.status_code}")
except requests.exceptions.ConnectionError:
    check("WS Broadcast (EC2 :8004)", False, "Connection refused")
except Exception as e:
    check("WS Broadcast (EC2 :8004)", False, str(e))

# Also check the local WS broadcast URL from config
ws_url = os.getenv('WEBSOCKET_BROADCAST_URL', 'http://ec2-34-235-119-67.compute-1.amazonaws.com:8004/')
try:
    r = requests.post(ws_url, json={"channel": "ping", "signal": {}}, timeout=5)
    check(f"WS Broadcast (config URL)", True, f"Status {r.status_code}")
except requests.exceptions.ConnectionError:
    check(f"WS Broadcast (config URL)", False, "Connection refused")
except Exception as e:
    check(f"WS Broadcast (config URL)", False, str(e))

# 9. IB Gateway Connection
print("\n--- IB GATEWAY ---")
try:
    from ib_insync import IB
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=999, timeout=5)
        check("IB Gateway (local)", True, "Connected")
        acct_values = ib.accountSummary()
        if acct_values:
            check("IB Account Data", True, f"{len(acct_values)} values")
        ib.disconnect()
    except Exception as e:
        check("IB Gateway (local :7497)", False, f"Cannot connect: {e}")
        # Try paper trading port
        try:
            ib.connect('127.0.0.1', 4002, clientId=999, timeout=5)
            check("IB Gateway (local :4002)", True, "Connected")
            ib.disconnect()
        except:
            check("IB Gateway (local :4002)", False, "Cannot connect")
except Exception as e:
    check("IB Gateway", False, str(e))

# 10. Market Hours Check
print("\n--- MARKET STATUS ---")
from datetime import datetime, time as dtime
import pytz
try:
    et = pytz.timezone('US/Eastern')
    now_et = datetime.now(et)
    check("Current Time (ET)", True, now_et.strftime("%Y-%m-%d %H:%M:%S %Z"))
    
    market_open = dtime(9, 30)
    market_close = dtime(16, 0)
    is_weekday = now_et.weekday() < 5
    is_market_time = market_open <= now_et.time() <= market_close
    
    check("Is Weekday", is_weekday, now_et.strftime("%A"))
    
    if is_weekday and now_et.time() < market_open:
        mins_to_open = (datetime.combine(now_et.date(), market_open) - datetime.combine(now_et.date(), now_et.time())).seconds // 60
        check("Pre-Market", True, f"Market opens in {mins_to_open} minutes")
    elif is_weekday and is_market_time:
        check("Market Hours", True, "Market is OPEN")
    else:
        check("Market Status", False, "Outside market hours")
except Exception as e:
    check("Market Status", False, str(e))

# 11. Auto-Approve Settings
print("\n--- AUTO-APPROVE ---")
try:
    from auto_approve import get_auto_approve_settings
    settings = get_auto_approve_settings()
    master = settings.get('enabled', False)
    check("Auto-Approve Master", True, f"{'ENABLED' if master else 'DISABLED'}")
    
    for strat in ['theta', 'zebra', 'dvo', 'diagonal']:
        s = settings.get(strat, {})
        enabled = s.get('enabled', False)
        risk = s.get('risk_level', 'N/A')
        check(f"  {strat.upper()}", True, f"{'ON' if enabled else 'OFF'} (Risk: {risk})")
except Exception as e:
    check("Auto-Approve", False, str(e))

# 12. Scanner check
print("\n--- SCANNER ---")
try:
    from scheduled_scanner import is_market_hours
    check("Scheduled Scanner", True, "imported")
except Exception as e:
    check("Scheduled Scanner", False, str(e))

# Summary
print("\n" + "=" * 60)
total = len(results)
passed = sum(1 for _, s, _ in results if s)
failed = sum(1 for _, s, _ in results if not s)
print(f"SUMMARY: {passed}/{total} checks passed, {failed} failed")

if failed > 0:
    print("\nFAILED CHECKS:")
    for name, status, detail in results:
        if not status:
            print(f"  [FAIL] {name}: {detail}")

print("\n" + "=" * 60)
if failed == 0:
    print("ALL SYSTEMS GO - READY FOR MARKET OPEN!")
else:
    print(f"WARNING: {failed} issue(s) need attention before market open")
print("=" * 60)
