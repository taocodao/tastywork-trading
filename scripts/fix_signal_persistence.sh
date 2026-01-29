#!/bin/bash
# Fix Signal Persistence - Comprehensive diagnostic and fix script

cd ~/tastywork-trading

echo "=== 1. Checking src directory ==="
ls -la src/earnings_intelligence/database.py
ls -la src/calendar_spreads/

echo ""
echo "=== 2. Initializing database ==="
python3 << 'PYTHON_EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

from src.earnings_intelligence.database import init_db, SignalRepository, Signal
from datetime import datetime, timedelta
import uuid

# Initialize database
print("Initializing database...")
init_db()
print("✅ Database initialized")

# Check existing signals
repo = SignalRepository()
signals = repo.get_all_signals()
print(f"\nSignals in database: {len(signals)}")

if len(signals) > 0:
    print("\nExisting signals:")
    for s in signals[:5]:
        print(f"  - {s.symbol} ({s.id[:8]}) - {s.status}")
else:
    print("\n⚠️  No signals found in database!")
    print("Creating test signal...")
    
    # Create test signal
    test_signal = {
        'id': str(uuid.uuid4()),
        'symbol': 'TEST',
        'strategy': 'Calendar Spread',
        'strike': 100.0,
        'cost': 250,
        'potentialReturn': 25.0,
        'returnPercent': 10,
        'winRate': 75,
        'riskLevel': 'Medium',
        'status': 'pending',
        'frontExpiry': (datetime.now() + timedelta(days=7)).isoformat(),
        'backExpiry': (datetime.now() + timedelta(days=14)).isoformat(),
    }
    
    saved = repo.save_signal(test_signal)
    print(f"✅ Test signal created: {saved.id}")

PYTHON_EOF

echo ""
echo "=== 3. Testing API endpoint ==="
curl -s http://localhost:8002/api/signals | python3 -m json.tool | head -20

echo ""
echo "=== 4. Restarting services ==="
sudo systemctl restart trademind-api
sleep 2
sudo systemctl status trademind-api --no-pager -l | head -20

echo ""
echo "=== 5. Checking recent logs ==="
sudo journalctl -u trademind-api -n 20 --no-pager

echo ""
echo "=== Done ==="
