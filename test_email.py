import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from email_notifications.resend_sender import notify_signal_subscribers

# Provide an email to send the test alert to
TEST_EMAIL = "erichuang2005@gmail.com"

# Simulated TurboCore Pro Signal Data
mock_signal_data = {
    "strategy": "TQQQ_TURBOCORE_PRO",
    "regime": "BEAR",
    "confidence": 0.88,
    "action": "OPEN_CCS",
    "cost": 1.45,
    "capital_required": 5600,
    "rationale": "Mode C: VIX 18.2 · QQQ below SMA50 · Bear call spread activated.",
    "legs": [
        {
            "symbol": "QQQ   260516C00622000",
            "action": "SELL_TO_OPEN",
            "qty": 2
        },
        {
            "symbol": "QQQ   260516C00650000",
            "action": "BUY_TO_OPEN",
            "qty": 2
        }
    ]
}

subscribers = [
    {
        "email": TEST_EMAIL,
        "first_name": "Eric"
    }
]

print(f"Sending test email to {TEST_EMAIL}...")
notify_signal_subscribers(mock_signal_data, subscribers)
print("Done! Check your inbox.")
