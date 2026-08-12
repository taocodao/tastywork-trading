#!/bin/bash
# =============================================================
# deploy_crons_to_ec2.sh
# Run from LOCAL machine (Git Bash / WSL) to push the cron
# installer to EC2 and execute it via SSH.
#
# EC2:  ubuntu@34.203.194.137
# Key:  D:\Projects\IB-program-trading\tradecoin-bot-key.pem
# =============================================================

EC2_USER="ubuntu"
EC2_HOST="34.203.194.137"
EC2_KEY="D:/Projects/IB-program-trading/tradecoin-bot-key.pem"
REMOTE_DIR="~/tastywork-trading"

echo "=== Deploying Cron Installer to EC2 ($EC2_HOST) ==="
echo ""

# 1. Push latest code via git (preferred over SCP)
echo "[1/3] Pushing code to remote via git..."
git add install_signal_crons.sh
git commit -m "ops: add signal cron installer for 3PM ET daily scans" || echo "(nothing new to commit)"
git push origin main

# 2. Pull on EC2
echo "[2/3] Pulling latest code on EC2..."
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "$EC2_USER@$EC2_HOST" \
    "cd $REMOTE_DIR && git pull origin main"

# 3. Run the cron installer
echo "[3/3] Installing cron jobs on EC2..."
ssh -i "$EC2_KEY" "$EC2_USER@$EC2_HOST" \
    "cd $REMOTE_DIR && bash install_signal_crons.sh"

echo ""
echo "✅ Done. Crons are live on EC2."
echo ""
echo "Verify with:"
echo "  ssh -i \"$EC2_KEY\" $EC2_USER@$EC2_HOST 'crontab -l'"
