# Credential Consistency Enforcement - README

## 🎯 Purpose

This directory contains enforcement mechanisms to ensure OAuth credentials remain synchronized between frontend and backend, preventing `invalid_credentials` errors.

---

## 📋 Files

### 1. **verify_credentials.py** - Pre-Deployment Verification
- **When to run**: Before every deployment
- **What it does**: Compares frontend `.env.local` with backend `.env`
- **Usage**:
  ```bash
  python verify_credentials.py
  ```
- **Exit code**: 0 = pass, 1 = fail

### 2. **credential_enforcement.py** - Runtime Validation
- **When it runs**: Automatically at backend startup
- **What it does**: Validates OAuth credentials are set and logs them
- **Integration**: Already added to `tasty_api_server.py`
- **Effect**: Server refuses to start if credentials missing

### 3. **clear_redis_tokens.py** - Token Cleanup
- **When to run**: After changing OAuth credentials
- **What it does**: Instructions to clear Tastytrade tokens from Redis
- **Usage**:
  ```bash
  python clear_redis_tokens.py
  ```
- **Note**: Requires Upstash console access

### 4. **pre_deploy_check.sh** - CI/CD Hook
- **When to run**: Before deploying to EC2
- **What it does**: Runs all verification checks
- **Usage**:
  ```bash
  chmod +x pre_deploy_check.sh
  ./pre_deploy_check.sh
  ```

---

## 🚀 Deployment Workflow

### Standard Deployment (With Verification)

```bash
# Step 1: Verify credentials match
python verify_credentials.py

# Step 2: Run all pre-deployment checks
./pre_deploy_check.sh

# Step 3: Deploy to EC2 (only if checks pass)
scp -i "path/to/key.pem" *.py ubuntu@server:~/tastywork-trading/
ssh -i "path/to/key.pem" ubuntu@server "sudo systemctl restart trademind-api"

# Step 4: Check logs for startup validation
ssh -i "path/to/key.pem" ubuntu@server "sudo journalctl -u trademind-api -n 50"
```

### Emergency Deployment (Skip Checks)

```bash
# NOT RECOMMENDED - Only use if you know credentials are correct
scp -i "path/to/key.pem" *.py ubuntu@server:~/tastywork-trading/
ssh -i "path/to/key.pem" ubuntu@server "sudo systemctl restart trademind-api"
```

---

## 🔧 Troubleshooting

### Error: "CLIENT_SECRET MISMATCH"

**Cause**: Frontend and backend have different OAuth credentials

**Solution**:
1. Get correct credentials from https://my.tastytrade.com/settings/api
2. Update BOTH files:
   - Frontend: `d:\Projects\trademind-app\.env.local`
   - Backend: `d:\Projects\tastywork-trading-1\.env`
3. Update Vercel environment variables
4. Run `verify_credentials.py` again

### Error: "Backend refused to start"

**Cause**: `credential_enforcement.py` detected missing credentials

**Solution**:
1. Check backend `.env` file has:
   - `TASTYTRADE_CLIENT_ID`
   - `TASTYTRADE_CLIENT_SECRET`
2. Ensure values are not empty
3. Restart service

### Error: "invalid_credentials" in production

**Diagnosis**:
1. Run `verify_credentials.py` locally
2. If pass: Old tokens in Redis → Clear and re-authenticate
3. If fail: Update credentials and redeploy

---

## 📊 Monitoring

### Check if enforcement is active

```bash
# SSH to server
ssh -i "path/to/key.pem" ubuntu@server

# Check startup logs
sudo journalctl -u trademind-api -b | grep "OAuth credential"

# Should see:
# ✅ OAuth credentials validated: CLIENT_ID=340d...55a5
```

### Verify credentials on server

```bash
# SSH to server
ssh -i "path/to/key.pem" ubuntu@server

# Run enforcement check
cd ~/tastywork-trading
python3 credential_enforcement.py
```

---

## 🔐 Security Notes

- Never commit `.env` files to git
- Credentials shown in logs are truncated (first 4 + last 4 chars only)
- `verify_credentials.py` only compares, never logs full secrets
- Runtime validation uses SHA256 hashes when comparing secrets

---

## 🎓 How It Works

### Token Binding (Why This Matters)

```
OAuth Flow:
1. Frontend exchanges code with client_secret=XYZ
   → Tastytrade returns refresh_token₁ (bound to XYZ)

2. Backend creates Session(client_secret=XYZ, refresh_token=refresh_token₁)
   → Tastytrade validates: refresh_token₁ issued to XYZ? ✅ Yes → Success

3. Backend creates Session(client_secret=ABC, refresh_token=refresh_token₁)
   → Tastytrade validates: refresh_token₁ issued to ABC? ❌ No → invalid_credentials
```

**Critical Rule**: The `client_secret` must match the one that issued the refresh token.

---

## 📚 References

- [OAuth Architecture Verification](file:///d:/Projects/tastywork-trading-1/tastytrade_oauth_architecture_verification.md)
- [Token Flow Explanation](file:///C:/Users/erich/.gemini/antigravity/brain/3c2a3d9b-1895-43b9-a0a5-89dd00734818/token_architecture_explained.md)
- [Task Plan](file:///C:/Users/erich/.gemini/antigravity/brain/3c2a3d9b-1895-43b9-a0a5-89dd00734818/task.md)
