#!/usr/bin/env python3
"""
Create a simulated test position for testing position tracking
WITHOUT placing a real trade (useful for testing after hours)
"""

from datetime import datetime, timedelta
import json
import uuid

def create_test_position():
    """Create a simulated position for testing."""
    
    print("\n" + "="*70)
    print("🧪 SIMULATED TEST POSITION - Testing Position Tracking")
    print("="*70 + "\n")
    
    # Create test position (simulate filled trade)
    entry_price = 5.25
    entry_date = datetime.now()
    exp_date = datetime(2026, 3, 20)
    dte = (exp_date - entry_date).days
    
    position = {
        "id": str(uuid.uuid4())[:8],
        "symbol": "SPY",
        "strike": 580.0,
        "expiration": "2026-03-20",
        "dte": dte,
        "contracts": 1,
        "entry_price": entry_price,
        "entry_date": entry_date.isoformat(),
        "total_premium": entry_price * 100,
        "status": "open",
        "exit_targets": {
            "target_50": round(entry_price * 0.50, 2),
            "target_60": round(entry_price * 0.60, 2),
            "target_75": round(entry_price * 0.75, 2),
            "target_90": round(entry_price * 0.90, 2)
        },
        "test_mode": True  # Flag to indicate this is a test position
    }
    
    # Load existing positions or create new file
    positions_file = 'theta_positions.json'
    try:
        with open(positions_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"positions": [], "last_updated": datetime.now().isoformat()}
    
    # Add new position
    data["positions"].append(position)
    data["last_updated"] = datetime.now().isoformat()
    
    # Save to file
    with open(positions_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Simulated position created successfully!\n")
    print(f"📝 Position Details:")
    print(f"   ID: {position['id']}")
    print(f"   Symbol: {position['symbol']} {position['strike']}P")
    print(f"   Expiration: {position['expiration']} ({dte} DTE)")
    print(f"   Entry Price: ${position['entry_price']:.2f}")
    print(f"   Total Premium: ${position['total_premium']:.2f}")
    print(f"   Test Mode: {position['test_mode']}")
    print(f"\n🎯 Exit Targets:")
    print(f"   50% profit @ ${position['exit_targets']['target_50']:.2f}")
    print(f"   60% profit @ ${position['exit_targets']['target_60']:.2f}")
    print(f"   75% profit @ ${position['exit_targets']['target_75']:.2f}")
    print(f"   90% profit @ ${position['exit_targets']['target_90']:.2f}")
    
    print(f"\n✅ Position saved to {positions_file}")
    
    # Show positions summary
    open_positions = [p for p in data["positions"] if p["status"] == "open"]
    print(f"\n📊 Portfolio Summary:")
    print(f"   Total positions: {len(data['positions'])}")
    print(f"   Open positions: {len(open_positions)}")
    print(f"   Total premium collected: ${sum(p['total_premium'] for p in open_positions):.2f}")
    
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("1. View position file:")
    print("   cat theta_positions.json | jq '.'")
    print("")
    print("2. Run scheduler to test exit monitoring:")
    print("   python3 run_theta_scheduler.py --once")
    print("   (It will check if current price hits exit targets)")
    print("")
    print("3. Check scheduler logs:")
    print("   tail -f theta_scheduler.log")
    print("")
    print("4. To simulate profit, manually edit the position's current price")
    print("   or wait for the scheduler to check real market prices")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        create_test_position()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
