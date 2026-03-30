---
description: Generate TurboCore and/or TurboCore Pro signals on EC2 (equivalent to the 3:00 PM ET cron job)
---

# Generate Signals Workflow

Kick off signal generation on EC2 exactly as the 3:00 PM ET cron does.
- **TurboCore** → `run_turbocore_scheduler.py --once` (cron: `0 15 * * 1-5`)
- **TurboCore Pro** → `run_turbocore_pro_scheduler.py --once` (cron: `1 15 * * 1-5`)

**EC2 details:**
- Host: `ubuntu@34.235.119.67`
- PEM: `D:\Projects\IB-program-trading\tradecoin-bot-key.pem`
- Project dir: `~/tastywork-trading`
- Logs dir: `~/tastywork-trading/logs/`

> **⚠️ Windows SSH Output Note**: SSH output does not surface through PowerShell stdout in this environment.
> Use the **nohup + log file pattern** below — launch detached, then read the log in a second SSH call.

---

## Run Both Signals (TurboCore + TurboCore Pro)

// turbo
1. Launch both schedulers in the background on EC2 (appends to their log files):
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "cd ~/tastywork-trading && nohup /usr/bin/python3 run_turbocore_scheduler.py --once >> logs/run_turbocore_scheduler.log 2>&1 & nohup /usr/bin/python3 run_turbocore_pro_scheduler.py --once >> logs/run_turbocore_pro_scheduler.log 2>&1 &"
```

2. Wait ~2 minutes for ML pipelines to complete, then check both logs:
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "echo '=== TURBOCORE ===' && tail -15 ~/tastywork-trading/logs/run_turbocore_scheduler.log && echo '=== TURBOCORE PRO ===' && tail -15 ~/tastywork-trading/logs/run_turbocore_pro_scheduler.log"
```

---

## Run TurboCore Only

// turbo
1. Launch in background and log:
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "cd ~/tastywork-trading && nohup /usr/bin/python3 run_turbocore_scheduler.py --once >> logs/run_turbocore_scheduler.log 2>&1 &"
```

2. Check log after ~2 min:
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "tail -20 ~/tastywork-trading/logs/run_turbocore_scheduler.log"
```

---

## Run TurboCore Pro Only

// turbo
1. Launch in background and log:
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "cd ~/tastywork-trading && nohup /usr/bin/python3 run_turbocore_pro_scheduler.py --once >> logs/run_turbocore_pro_scheduler.log 2>&1 &"
```

2. Check log after ~2 min:
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "tail -20 ~/tastywork-trading/logs/run_turbocore_pro_scheduler.log"
```

---

## Check EC2 Crontab (verify scheduled jobs)

// turbo
```powershell
cmd /c ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "crontab -l" > D:\Projects\tastywork-trading-1\ec2_cron.txt 2>&1
```
Then read file: `D:\Projects\tastywork-trading-1\ec2_cron.txt`

Expected active cron entries (installed 2026-03-19):
```
0 15 * * 1-5  run_turbocore_scheduler.py --once
1 15 * * 1-5  run_turbocore_pro_scheduler.py --once
2 15 * * 1-5  run_turbobounce_scheduler.py --once --mode MODE_A
```

