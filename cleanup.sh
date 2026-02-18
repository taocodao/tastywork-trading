#!/bin/bash
# Disk Cleanup Script to Prevent "No space left on device" errors

echo "🧹 Starting Disk Cleanup..."

# 1. Clean APT cache
echo "  - Cleaning APT cache..."
sudo apt-get clean
sudo apt-get autoremove -y > /dev/null 2>&1

# 2. Vacuum Journal Logs (>1 day)
echo "  - Vacuuming systemd journals..."
sudo journalctl --vacuum-time=1d > /dev/null 2>&1

# 3. Prune Docker (if installed)
if command -v docker &> /dev/null; then
    echo "  - Pruning Docker system..."
    docker system prune -f > /dev/null 2>&1
fi

echo "✅ Cleanup Complete."
echo "Current Usage:"
df -h / | grep /
