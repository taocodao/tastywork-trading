# Server Inventory & Infrastructure

**Last Updated:** 2026-01-23
**Environment:** Production (AWS EC2)

## EC2 Instance Details
- **Name:** tradecoinbot
- **Instance ID:** `i-0b10eeefed7f2481b`
- **Instance Type:** c5.large
- **Region:** us-east-1 (N. Virginia)
- **Public IPv4:** `34.235.119.67`
- **Private IPv4:** `172.31.34.178`
- **Public DNS:** `ec2-34-235-119-67.compute-1.amazonaws.com`
- **VPC ID:** `vpc-0729fe1236920b1f4`

## Connection Details
- **User:** ubuntu
- **Key File:** `D:\Projects\IB-program-trading\tradecoin-bot-key.pem`
- **SSH Command:**
  ```powershell
  ssh -i "D:\Projects\IB-program-trading\tradecoin-bot-key.pem" ubuntu@34.235.119.67
  ```

## Deployed Services (Backend)
**CRITICAL PATH:** `~/tastywork-trading` (NOT -1)

| Service | Script | Port | Logs |
|---------|--------|------|------|
| **WebSocket Server** | `websocket_server.py` | 8003 (WS) | `websocket.log` |
| **API Server** | `tasty_api_server.py` | 8002 (HTTP) | `api.log` |
| **Scanner** | `scheduled_scanner.py` | N/A (Systemd) | `journalctl -u trademind-scanner` |

## Deployment Commands
To update and restart services:

```powershell
# Run the automated deployment script locally
.\scripts\deploy_production.ps1
```
