# Create Test Signal - Copy/Paste into SSH Terminal

# Make sure you're in the right directory
cd ~/tastywork-trading

# Create a test signal using signal_publisher
python3 <<'EOF'
from signal_publisher import spread_setup_to_signal, save_signal_to_db
from datetime import datetime, timedelta

# Create a mock setup for testing
class MockSetup:
    def __init__(self):
        self.symbol = 'AAPL'
        self.strike = 150.0
        self.short_expiry = (datetime.now() + timedelta(days=7)).date()
        self.long_expiry = (datetime.now() + timedelta(days=30)).date()
        self.net_debit = 2.50
        self.stock_price = 150.5
        self.score = 75.0
        self.iv = 0.25
        self.theta_edge = 0.15

setup = MockSetup()
signal = spread_setup_to_signal(setup)
save_signal_to_db(signal)
print(f'✅ Created test signal: {signal["id"]} for {signal["symbol"]}')
EOF

# Then pull latest code which now includes the scanner
git pull origin main

# Restart scanner service
sudo systemctl restart trademind-scanner
sudo systemctl status trademind-scanner --no-pager
