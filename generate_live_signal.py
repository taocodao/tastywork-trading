#!/usr/bin/env python3
"""
Generate a real TurboBounce signal with tradeable legs and push to DB.
The auto-approve hook will pick it up and execute via Tastytrade.

Usage: python3 generate_live_signal.py
"""

import os
import sys
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.earnings_intelligence.database import SignalRepository

def get_next_friday():
    """Get next Friday's date for option expiration."""
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7  # Next week's Friday
    return (today + timedelta(days=days_until_friday)).strftime('%y%m%d')

def build_occ_symbol(underlying: str, exp_date: str, option_type: str, strike: float) -> str:
    """
    Build OCC option symbol.
    Format: SYMBOL  YYMMDDCSSSSSSSS (padded to 6 chars for symbol, 8 digits for strike * 1000)
    """
    sym = underlying.ljust(6)
    strike_int = int(strike * 1000)
    strike_str = str(strike_int).zfill(8)
    return f"{sym}{exp_date}{option_type}{strike_str}"

def generate_signal():
    """Generate a GLD Bull Put Spread signal with real OCC legs."""
    
    # GLD (Gold ETF) - very liquid, good for testing
    # Current GLD ~$270-280 range (March 2026)
    # Bull Put Spread: Sell higher put, buy lower put for net credit
    
    underlying = "GLD"
    exp_date = get_next_friday()
    
    # Conservative OTM puts - these should be safe
    short_strike = 260.0  # Sell the $260 put (OTM)
    long_strike = 255.0   # Buy the $255 put (further OTM, protection)
    
    short_occ = build_occ_symbol(underlying, exp_date, "P", short_strike)
    long_occ = build_occ_symbol(underlying, exp_date, "P", long_strike)
    
    signal_id = str(uuid.uuid4())
    
    signal_data = {
        "id": signal_id,
        "symbol": underlying,
        "strategy": "turbobounce",
        "status": "pending",
        "type": "CREDIT_SPREAD",
        "direction": "BULLISH",
        "signalType": "Bull Put Spread",
        "confidence": 85.0,
        "total_score": 85.0,
        "win_rate": 85.0,
        "winRate": 85.0,
        "cost": -0.50,  # Expected credit
        "capital_required": 450.0,  # $5 wide spread - credit = max risk
        "rsi_2": 25.0,
        "iv_rank": 35.0,
        "category": "COMMODITIES",
        "pool": "MULTI_TICKER",
        "strategy_name": "TurboBounce Multi-Ticker",
        "rationale": f"GLD Bull Put Spread ${short_strike}/{long_strike} — conservative OTM credit spread for live execution test",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z",
        "legs": [
            {
                "action": "SELL_TO_OPEN",
                "symbol": short_occ,
                "quantity": 1
            },
            {
                "action": "BUY_TO_OPEN",
                "symbol": long_occ,
                "quantity": 1
            }
        ]
    }
    
    print(f"=== Generating GLD Bull Put Spread Signal ===")
    print(f"Signal ID: {signal_id}")
    print(f"Short Leg: STO {short_occ} (${short_strike} Put)")
    print(f"Long Leg:  BTO {long_occ} (${long_strike} Put)")
    print(f"Expiry: {exp_date}")
    print(f"Confidence: {signal_data['confidence']}%")
    print(f"Capital Required: ${signal_data['capital_required']}")
    print()
    
    # Save to DB
    repo = SignalRepository()
    repo.save_signal(signal_data)
    print(f"✅ Signal saved to database: {signal_id}")
    
    # Trigger auto-approve
    print(f"\n🤖 Triggering auto-approve...")
    try:
        from auto_approve import auto_approve_signal
        result = auto_approve_signal(signal_data)
        if result:
            print(f"✅ AUTO-APPROVED! Order ID: {result.get('order_id', 'unknown')}")
            print(f"   Net Price: ${result.get('net_price', 'N/A')}")
            print(f"   Price Effect: {result.get('price_effect', 'N/A')}")
            
            # Update signal status in DB
            signal_data['status'] = 'executed'
            signal_data['orderId'] = result.get('order_id')
            repo.save_signal(signal_data)
            print(f"✅ Signal status updated to 'executed' in DB")
        else:
            print(f"⚠️ Auto-approve returned None (criteria not met or no credentials)")
            print(f"   Signal remains 'pending' — user can approve from dashboard")
    except Exception as e:
        print(f"❌ Auto-approve error: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n   Signal is still 'pending' in DB — can be approved from dashboard")
    
    return signal_data

if __name__ == "__main__":
    generate_signal()
