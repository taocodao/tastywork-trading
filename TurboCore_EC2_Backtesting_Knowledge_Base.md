# TurboCore & TurboCore Pro: Backtesting and EC2 Operations Knowledge Base

This document serves as a comprehensive guide consolidating all the processes around the TurboCore/TurboCore Pro options strategies, including local and remote backtesting, connecting to the EC2 server, generating daily signals, and deploying updates. It ensures consistency across environments.

---

## 1. Connecting to the EC2 Instance

The primary backend environment runs on an AWS EC2 instance containing the `tastywork-trading` repository. Since the environment is primarily managed via PowerShell on Windows, use the following variables and commands to connect.

### EC2 Connection Details
*   **Username & Host:** `ubuntu@34.203.194.137`
*   **SSH Key (PEM) Path:** `D:\Projects\IB-program-trading\tradecoin-bot-key.pem`
*   **Project Code Location:** `~/tastywork-trading`
*   **Background Logs Location:** `~/tastywork-trading/logs/`

### Open an Interactive SSH Session
To securely log in to the EC2 shell from your Windows terminal:
```powershell
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$EC2HOST = "ubuntu@34.203.194.137"
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST
```

---

## 2. Local Backtesting Guide

The IV-Switching Composite Options Strategy (Phase 1.9) logic and backtesting engines are located in the `iv-switching-composite` directory.

### Running the Backtest Natively
Open a terminal in the project directory and invoke the composite backtest script. This runs through historical data to evaluate performance, risk boundaries, and yield.

```powershell
cd D:\Projects\tastywork-trading-1\iv-switching-composite
python backtest_composite.py
```
*(Optionally, you can also run `backtest_pmcc_comparison.py` for evaluating PMCC alternatives.)*

---

## 3. Running Backtesting on EC2

When running intensive or long backtesting sequences, executing them on the EC2 ensures they are not interrupted if your local PC sleeps or disconnects. 

### Step 1: Sync Your Changes to EC2
Ensure the latest version of your backtesting scripts are pulled to the EC2 server before running:
```powershell
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$EC2HOST = "ubuntu@34.203.194.137"
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "cd ~/tastywork-trading && git pull origin main"
```

### Step 2: Run the Backtest Detached (`nohup`)
To prevent the backtest from being aborted if your SSH session times out, use `nohup` (no hangup) and send the process to the background (`&`), piping output to a log file.
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "cd ~/tastywork-trading/iv-switching-composite && nohup python3 backtest_composite.py > ~/tastywork-trading/logs/backtest_composite.log 2>&1 &"
```

### Step 3: Monitor the EC2 Backtest
You can check on the progress of the remote backtest by "tailing" (reading the end of) the log file:
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "tail -f ~/tastywork-trading/logs/backtest_composite.log"
```
*(Press `Ctrl+C` to stop watching the log; the backtest will continue running in the background).*

---

## 4. Signal Generation & EC2 Automation

On EC2, signal generation is automated via cron jobs that run just before the market closes (~3:00 PM ET). 

### Cron Schedule on EC2
The EC2 server automatically triggers `.py` files daily. If you inspect the crontab (`crontab -l`), you will see entries typically looking like:
*   `0 15 * * 1-5  run_turbocore_scheduler.py --once`
*   `1 15 * * 1-5  run_turbocore_pro_scheduler.py --once`

### How to Force Generate Signals Manually
You can invoke the 3:00 PM signal generators explicitly over SSH if the cron missed or you want to generate signals instantly.

**Run Both Pipelines Detached:**
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "cd ~/tastywork-trading && nohup /usr/bin/python3 run_turbocore_scheduler.py --once >> logs/run_turbocore_scheduler.log 2>&1 & nohup /usr/bin/python3 run_turbocore_pro_scheduler.py --once >> logs/run_turbocore_pro_scheduler.log 2>&1 &"
```

**Check Generation Logs:**
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "echo '=== TURBOCORE ===' && tail -15 ~/tastywork-trading/logs/run_turbocore_scheduler.log && echo '=== TURBOCORE PRO ===' && tail -15 ~/tastywork-trading/logs/run_turbocore_pro_scheduler.log"
```

---

## 5. Deployment and Service Restarts

If you alter API structures, scheduling behavior, or deploy new logic that runs as an actual real-time Linux Service `systemd` (e.g., `tasty_api_server` or `tqqq-scheduler`), you must pull the code and restart the daemons.

### Deploying the Backend
```powershell
# 1. Commit and push from local
cd D:\Projects\tastywork-trading-1
git add .
git commit -m "Updates to EC2 backend"
git push

# 2. SSH, pull, and restart relevant services (example: tqqq-scheduler)
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "cd ~/tastywork-trading ; git pull origin main ; sudo systemctl restart tqqq-scheduler"
```

### Viewing Scheduled Service Health
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $EC2HOST "sudo systemctl status tqqq-scheduler --no-pager -l | tail -20"
```
