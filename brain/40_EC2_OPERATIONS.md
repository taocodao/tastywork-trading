# EC2 Server & WebSocket Startup Guide

## Issue
- EC2 instance `34.235.119.67` is unreachable
- SSH connection timing out on port 22
- WebSocket server at `wss://ws.trademind.bot` is down

## Step 1: Check EC2 Instance Status

### Option A: AWS Console
1. Go to [AWS EC2 Console](https://console.aws.amazon.com/ec2/)
2. Select **US East (N. Virginia)** region
3. Click **Instances** in left sidebar
4. Look for instance with IP `34.235.119.67`
5. Check **Instance State**:
   - ✅ **Running** - Instance is up (proceed to Step 2)
   - ❌ **Stopped** - Instance is stopped (see below)
   - ⚠️ **Stopping/Pending** - Wait for state to stabilize

### Option B: AWS CLI (if installed)
```bash
aws ec2 describe-instances --instance-ids <instance-id> --region us-east-1
```

## Step 2: Start EC2 Instance (if stopped)

### Via AWS Console:
1. Select the stopped instance
2. Click **Instance state** → **Start instance**
3. Wait 2-3 minutes for instance to boot
4. Note the new Public IP (it may change if you don't have Elastic IP)

### Via AWS CLI:
```bash
aws ec2 start-instances --instance-ids <instance-id> --region us-east-1
```

## Step 3: Update DNS (if IP changed)

If EC2 public IP changed after restart:
1. Go to your DNS provider (where `trademind.bot` is hosted)
2. Update A records:
   - `ws.trademind.bot` → new IP
   - `34.235.119.67` references → new IP
3. Wait 5-10 minutes for DNS propagation

## Step 4: SSH into EC2

Once instance is running:

```bash
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" ubuntu@ec2-34-235-119-67.compute-1.amazonaws.com
```

Or use the IP directly:
```bash
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" ubuntu@34.235.119.67
```

## Step 5: Start WebSocket Server

Once connected via SSH:

```bash
# Navigate to project directory
cd ~/tastywork-trading

# Check if WebSocket server is already running
ps aux | grep websocket_server

# If not running, start it
# Option A: Direct (blocks terminal)
python3 websocket_server.py

# Option B: Background with nohup (recommended)
nohup python3 websocket_server.py > websocket.log 2>&1 &

# Option C: Using screen (allows detaching)
screen -S websocket
python3 websocket_server.py
# Press Ctrl+A then D to detach
```

## Step 6: Verify WebSocket is Running

Check if WebSocket ports are listening:
```bash
# On EC2
netstat -tulpn | grep -E "8003|8004"

# Should show:
# tcp  0.0.0.0:8003  LISTEN  (WebSocket)
# tcp  0.0.0.0:8004  LISTEN  (HTTP broadcast)
```

## Step 7: Test Signal Sending

From your local machine:

```bash
cd D:\Projects\tastywork-trading-1
python send_calendar_signal_to_production.py
```

Or use the theta signal script:
```bash
python submit_test_signal_to_production.py
```

## Step 8: Verify in Browser

1. Open https://trademind.bot/signals
2. Check browser console - should see:
   - `🔌 WebSocket connected`
   - `✅ Subscribed to: calendar_spread, theta_entry, ...`
3. Signal should appear in UI

## Alternative: Use Elastic IP

To prevent IP changes on restart:

1. AWS Console → **Elastic IPs**
2. **Allocate Elastic IP address**
3. **Associate Elastic IP** with your instance
4. Update DNS to point to Elastic IP
5. Instance will keep same IP on restarts

## Troubleshooting

### SSH still times out after starting instance
- Check **Security Group** rules:
  - Port 22 (SSH) should allow your IP
  - Port 8003 (WebSocket) should allow 0.0.0.0/0
  - Port 8004 (HTTP) should allow 0.0.0.0/0
- Check **Network ACLs**
- Verify instance has public IP assigned

### WebSocket won't start
```bash
# Check for errors
python3 websocket_server.py

# Check if port is already in use
lsof -i :8003
lsof -i :8004

# Kill existing process if needed
kill <PID>
```

### Can't connect from browser
- Verify DNS points to correct IP:
  ```bash
  nslookup ws.trademind.bot
  ```
- Check firewall allows WSS (port 443) if using reverse proxy
- Check SSL certificate if using HTTPS/WSS

## Quick Commands Reference

```bash
# Check EC2 instance status
aws ec2 describe-instance-status --instance-ids <id>

# Start EC2
aws ec2 start-instances --instance-ids <id>

# SSH into EC2
ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" ubuntu@34.235.119.67

# Start WebSocket server (on EC2)
cd ~/tastywork-trading
nohup python3 websocket_server.py > websocket.log 2>&1 &

# Check WebSocket is running
ps aux | grep websocket_server
netstat -tulpn | grep -E "8003|8004"

# Send test signal (from local)
python send_calendar_signal_to_production.py
```
