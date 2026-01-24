#!/usr/bin/env python3
"""Test script to broadcast a signal via WebSocket server."""
import requests

signal = {
    "id": "test-001",
    "symbol": "SPY",
    "strategy": "Calendar Spread",
    "direction": "neutral",
    "strike": 600,
    "frontExpiry": "2026-01-30",
    "backExpiry": "2026-02-13",
    "cost": 250,
    "potentialReturn": 87.5,
    "returnPercent": 35,
    "winRate": 75,
    "riskLevel": "Medium",
    "status": "pending",
    "rationale": "Test signal broadcast"
}

r = requests.post(
    "http://localhost:8004",
    json={"channel": "calendar_spread", "signal": signal}
)
print(f"Response: {r.status_code}")
print(r.text)
