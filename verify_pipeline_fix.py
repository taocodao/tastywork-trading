import sys
import os
import json

# Mock the environment
sys.path.append(os.path.join(os.getcwd(), 'signal_publisher'))

# Mock Signal Data (Snake Case from Backend)
theta_signal = {
    "id": "test_theta_1",
    "symbol": "IWM",
    "strategy": "theta",
    "entry_price": 2.15,
    "confidence": 87,
    "probability_otm": 0.82
}

zebra_signal = {
    "id": "test_zebra_1",
    "symbol": "SPY",
    "strategy": "zebra",
    "cost": 1500,
    "win_rate": 75
}

dvo_signal = {
    "id": "test_dvo_1",
    "symbol": "SLV",
    "strategy": "dvo_value",
    "pnl_potential": 500
}

# Test 1: Channel Routing Logic (Replicating websocket_server.py logic)
def get_channel(strategy):
    strategy = strategy.lower()
    if 'theta' in strategy:
        return 'theta_entry'
    elif 'zebra' in strategy:
        return 'zebra_entry'
    elif 'dvo' in strategy or 'value' in strategy:
        return 'dvo_entry'
    elif 'iron_condor' in strategy:
        return 'iron_condor'
    elif 'vertical' in strategy:
        return 'vertical_spread'
    else:
        return 'calendar_spread'

print(f"Theta Channel: {get_channel(theta_signal['strategy'])} (Expected: theta_entry)")
print(f"Zebra Channel: {get_channel(zebra_signal['strategy'])} (Expected: zebra_entry)")
print(f"DVO Channel:   {get_channel(dvo_signal['strategy'])} (Expected: dvo_entry)")

# Test 2: Frontend Normalization Logic (Replicating useSignalSocket.ts logic in Python)
def normalize_signal(raw):
    return {
        "symbol": raw.get('symbol', ''),
        "cost": raw.get('cost') or raw.get('entry_price') or raw.get('capital_required') or 0,
        "winRate": raw.get('winRate') or raw.get('win_rate') or raw.get('confidence') or raw.get('probability_otm') or 0
    }

norm_theta = normalize_signal(theta_signal)
norm_zebra = normalize_signal(zebra_signal)

print(f"\nNormalized Theta: Cost=${norm_theta['cost']}, WinRate={norm_theta['winRate']}%")
print(f"Normalized Zebra: Cost=${norm_zebra['cost']}, WinRate={norm_zebra['winRate']}%")
