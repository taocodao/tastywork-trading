---
description: Deploy backend to EC2 and frontend to Vercel
---

# Deployment Workflow

## Backend → EC2 (`tastywork-trading-1`)

1. Stage and commit backend changes (PowerShell — separate commands):
```powershell
cd D:\Projects\tastywork-trading-1
git add config.py run_tqqq_scheduler.py tasty_api_server.py signal_publisher/ src/tqqq/ tests/
git commit -m "TurboBounce Options: Phase D live integration"
git push
```

// turbo
2. SSH to EC2 — git pull + restart TQQQ scheduler:
```powershell
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "ubuntu@34.235.119.67"
ssh -i $PEM -o StrictHostKeyChecking=no $HOST "cd ~/tastywork-trading ; git pull ; sudo systemctl restart tqqq-scheduler 2>/dev/null || (pkill -f run_tqqq_scheduler || true) ; sleep 1 ; nohup python3 run_tqqq_scheduler.py > logs/tqqq_scheduler.log 2>&1 &"
```

// turbo
3. (First-time only) Install TQQQ scheduler as a permanent systemd service:
```powershell
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "ubuntu@34.235.119.67"
$SVC = "[Unit]`nDescription=TurboBounce TQQQ Scheduler`nAfter=network.target`n`n[Service]`nUser=ubuntu`nWorkingDirectory=/home/ubuntu/tastywork-trading`nExecStart=/usr/bin/python3 run_tqqq_scheduler.py`nRestart=always`nRestartSec=30`n`n[Install]`nWantedBy=multi-user.target"
ssh -i $PEM -o StrictHostKeyChecking=no $HOST "echo '$SVC' | sudo tee /etc/systemd/system/tqqq-scheduler.service ; sudo systemctl daemon-reload ; sudo systemctl enable tqqq-scheduler ; sudo systemctl start tqqq-scheduler"
```

// turbo
4. Verify EC2 services are running:
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $HOST "sudo systemctl status tqqq-scheduler --no-pager -l | tail -20"
```

---

## Frontend → Vercel (`trademind-app`)

5. Commit and push frontend (Vercel auto-deploys on push):
```powershell
cd D:\Projects\trademind-app
git add src/components/dashboard/SignalCard.tsx src/components/settings/TQQQAutoApproveSettings.tsx
git commit -m "TurboBounce Options: risk level UI + backtest stats"
git push
```

---

## Quick Health Check (Post Deploy)

// turbo
6. Verify TQQQ signals API on EC2:
```powershell
ssh -i $PEM -o StrictHostKeyChecking=no $HOST "curl -s http://localhost:8002/api/tqqq/signals"
```
