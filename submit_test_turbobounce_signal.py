import os
import sys
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

# Load env before importing DB
load_dotenv()

from src.earnings_intelligence.database import SignalRepository

def main():
    repo = SignalRepository()
    
    signal_id = f"test-nugt-{int(datetime.now().timestamp())}"
    
    # User's request:
    # Action 1: Sell to Open (STO) 1 Apr 17 $230 Put (NUGT)
    # Action 2: Buy to Open (BTO) 1 Apr 17 $220 Put (NUGT)
    # OCC Symbol format: NUGT  YYMMDD T Strike(x1000)
    # April 17, 2026 -> 260417
    # 230 Put -> P00230000
    # 220 Put -> P00220000
    
    short_leg = 'NUGT  260417P00230000'
    long_leg = 'NUGT  260417P00220000'
    
    signal_data = {
        'id': signal_id,
        'symbol': 'NUGT',
        'strategy': 'turbobounce',
        'direction': 'BULLISH',
        'signalType': 'Bull Put Spread',
        'status': 'pending',
        'confidence': 95.0,
        'cost': -1.50, # Net credit of $1.50
        'capital_required': 850.0, # (230-220)*100 - 150 = $850 max loss
        'expiresAt': (datetime.utcnow() + timedelta(hours=4)).isoformat() + 'Z',
        'rationale': 'Test Bull Put Spread from user request.',
        
        # New explicit legs format for the execute handler
        'legs': [
            {'action': 'SELL_TO_OPEN', 'symbol': short_leg, 'quantity': 1},
            {'action': 'BUY_TO_OPEN', 'symbol': long_leg, 'quantity': 1}
        ]
    }
    
    try:
        repo.save_signal(signal_data)
        print(f"✅ Successfully injected test signal: {signal_id}")
        print(json.dumps(signal_data, indent=2))
    except Exception as e:
        print(f"❌ Failed to inject test signal: {e}")

if __name__ == "__main__":
    main()
