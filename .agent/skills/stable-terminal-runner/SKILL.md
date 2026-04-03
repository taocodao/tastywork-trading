---
name: stable-terminal-runner
description: Run terminal commands continuously without hanging in "Running..." state on Windows. Includes patterns for EC2 SSH operations and signal generation.
---

# Stable Terminal Runner Skill

## Goal
Run terminal commands continuously without hanging in "Running..." state on Windows. The skill must ensure every command is non-interactive and self-terminating.

## Environment Assumptions
- OS: Windows 11
- IDE: Antigravity VS Code plugin
- Default shell: PowerShell or CMD

## Skill Behavior
1. For every terminal command, automatically transform it to run as:
   - `cmd /c <command>` when using CMD, or
   - `powershell -NoProfile -Command "<command>"` when using PowerShell.
2. Never launch interactive shells or tools that wait for user input (no REPLs, no npm init, no prisma without `--yes`/`--accept-data-loss`, etc.). If a command usually asks questions, append the correct non-interactive flags.
3. Treat the command as finished when the process exits and EOF is reached; then immediately return a concise summary of:
   - Exit code
   - Stdout (trimmed)
   - Stderr (trimmed)
4. If a command runs longer than 300 seconds, automatically:
   - Kill the process
   - Return whatever output is available
   - Mark the run as "timed out" so the chat does not stay stuck.
5. For background tasks (servers, watchers), wrap them in a script that starts the process detached and then exits quickly, so the agent's terminal session still terminates.

## Trigger Phrase
To force the agent to use this skill, type:
"Use Stable Terminal Runner to execute: <command>"

## Examples
- **npm install**: `cmd /c npm install --no-fund --no-audit`
- **database migrations**: `powershell -NoProfile -Command "npx prisma migrate deploy --accept-data-loss"`
- **test runs**: `cmd /c npm test -- --watch=false`

---

## EC2 SSH Operations (Critical Notes)

### Known Issue: SSH stdout is silently dropped in this environment
SSH commands via PowerShell or `cmd /c ssh ...` return exit 0 but produce **no visible output** in the terminal. This is a persistent Windows terminal limitation with OpenSSH.

**What DOES work:**
- Running commands on EC2 (exit codes are correct)
- Launching background jobs with `nohup ... &`
- Writing output to a file ON EC2, then reading it back in a second SSH call

**What does NOT work:**
- `ssh ... "command"` → output appears empty in stdout
- `cmd /c ssh ... > local_file.txt` → local file is empty or has encoding issues
- `powershell -Command "& ssh ..."` → same issue

### EC2 Connection Details
- **Host**: `ubuntu@34.235.119.67`
- **PEM**: `D:\Projects\IB-program-trading\tradecoin-bot-key.pem`
- **Project dir**: `~/tastywork-trading`
- **Logs dir**: `~/tastywork-trading/logs/`

### Pattern: Run a job on EC2 and check output
```powershell
# Step 1 — Launch the job detached (exits immediately, job runs in background)
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "cd ~/tastywork-trading && nohup /usr/bin/python3 <script.py> --once >> logs/<script>.log 2>&1 &"

# Step 2 — After waiting (e.g., 2 min), read the log back on EC2
# Note: stdout still invisible, so write to /tmp and use a second ssh for /tmp read
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "tail -20 ~/tastywork-trading/logs/<script>.log > /tmp/out.txt && cat /tmp/out.txt"
# (still may not show — just verify via dashboard or DB)
```

### Pattern: Git pull + service restart on EC2
```powershell
# Git pull
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "cd ~/tastywork-trading && git pull origin main"

# Restart API service (if running as systemd)
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "sudo systemctl restart trademind-api"
```
Both return exit 0 on success even though stdout is invisible.

### Generate TurboCore + TurboCore Pro Signals (both at once)
The cron runs at 3:00 PM ET Mon–Fri. To run manually:
```powershell
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" -o StrictHostKeyChecking=no ubuntu@34.235.119.67 "cd ~/tastywork-trading && nohup /usr/bin/python3 run_turbocore_scheduler.py --once >> logs/run_turbocore_scheduler.log 2>&1 & nohup /usr/bin/python3 run_turbocore_pro_scheduler.py --once >> logs/run_turbocore_pro_scheduler.log 2>&1 &"
```
- Takes ~2 minutes to complete (ML pipeline + IV-Switching composite)
- Confirm via the live dashboard at trademind.bot
- Detailed steps: see `/generate-signals` workflow
