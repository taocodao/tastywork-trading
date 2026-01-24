# Verified Guide: Starting IB Gateway & Generating Signals
**Date:** 2026-01-23
**Context:** Based on review of `Enable Automatic Signal Generation.md` and project history.

## 1. Start IB Gateway (Real-Time Data Source)
The scanner requires a running IB Gateway to fetch live option chains. This runs as a Docker container.

**On your EC2 Server:**
```bash
# 1. Go to the infrastructure repository
cd ~/IB-program-trading

# 2. Start the specific IB Gateway service
docker-compose up -d ib-gateway-data

# 3. Wait 60 seconds for initialization and login
sleep 60

# 4. Verify it is healthy (should see 'Up' status)
docker ps | grep ib-gateway
```
*Note: If `docker ps` is empty, check logs with `docker logs <container_id>`—it may require a paper trading login if not fully configured with env vars.*

## 2. Run the Signal Scanner
Once IB Gateway is running on port **4004**, run the scanner.

**On your EC2 Server:**
```bash
# 1. Go to the trading logic repository
cd ~/tastywork-trading

# 2. Ensure dependencies are installed (one-time)
pip3 install -r requirements.txt

# 3. Run the scanner (Real Data Mode)
python3 scheduled_scanner.py
```

### Expected Output
```
INFO: Connecting to Data Provider...
INFO: ✅ Connected to IB Gateway for Market Data (Option Chains)
INFO: 📊 Scanning for calendar spread opportunities...
INFO: Found 5 potential setups
INFO: ✅ Published 5 signals to WebSocket
```

## 3. Troubleshooting
- **Connection Refused:** IB Gateway container is down. Re-run Step 1.
- **Empty Scan:** Check `docker logs` for IB Gateway. It might be waiting for 2FA or disconnected.
- **"Scanner exited with error":** Check `logs/calendar_spreads.log` for Python errors.

---

## 4. Alternative: Mock Mode (If Market Closed/IB Down)
If you cannot get IB Gateway running immediately, use mock data to test the dashboard flow:
```bash
cd ~/tastywork-trading
python3 scheduled_scanner.py --mock
```
