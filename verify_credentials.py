#!/usr/bin/env python3
"""
Tastytrade Credential Verification Script

This script verifies that frontend and backend have matching OAuth credentials.
Run this before deploying to catch credential mismatches early.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

def load_env_file(file_path: Path) -> dict:
    """Load environment variables from a file."""
    env_vars = {}
    if not file_path.exists():
        return env_vars
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

def verify_credentials():
    """Verify that frontend and backend credentials match."""
    print(f"\n{BLUE}{BOLD}🔍 Tastytrade Credential Verification{RESET}\n")
    
    # Paths
    frontend_env = Path("d:/Projects/trademind-app/.env.local")
    backend_env = Path("d:/Projects/tastywork-trading-1/.env")
    
    # Load environment files
    frontend_vars = load_env_file(frontend_env)
    backend_vars = load_env_file(backend_env)
    
    # Check if files exist
    if not frontend_env.exists():
        print(f"{RED}❌ Frontend .env.local not found at: {frontend_env}{RESET}")
        return False
    
    if not backend_env.exists():
        print(f"{RED}❌ Backend .env not found at: {backend_env}{RESET}")
        return False
    
    print(f"{GREEN}✓{RESET} Found frontend .env.local: {frontend_env}")
    print(f"{GREEN}✓{RESET} Found backend .env: {backend_env}\n")
    
    # Extract credentials
    frontend_client_id = frontend_vars.get('NEXT_PUBLIC_TASTYTRADE_CLIENT_ID') or frontend_vars.get('TASTYTRADE_CLIENT_ID')
    frontend_client_secret = frontend_vars.get('TASTYTRADE_CLIENT_SECRET')
    
    backend_client_id = backend_vars.get('TASTYTRADE_CLIENT_ID')
    backend_client_secret = backend_vars.get('TASTYTRADE_CLIENT_SECRET')
    
    # Validation results
    all_checks_passed = True
    
    # Check CLIENT_ID
    print(f"{BOLD}1. CLIENT_ID Verification:{RESET}")
    if not frontend_client_id:
        print(f"   {RED}❌ Frontend CLIENT_ID not found{RESET}")
        all_checks_passed = False
    elif not backend_client_id:
        print(f"   {RED}❌ Backend CLIENT_ID not found{RESET}")
        all_checks_passed = False
    elif frontend_client_id != backend_client_id:
        print(f"   {RED}❌ CLIENT_ID MISMATCH!{RESET}")
        print(f"   Frontend: {frontend_client_id[:10]}...{frontend_client_id[-10:]}")
        print(f"   Backend:  {backend_client_id[:10]}...{backend_client_id[-10:]}")
        all_checks_passed = False
    else:
        print(f"   {GREEN}✅ CLIENT_ID matches:{RESET} {frontend_client_id[:10]}...{frontend_client_id[-10:]}")
    
    # Check CLIENT_SECRET
    print(f"\n{BOLD}2. CLIENT_SECRET Verification:{RESET}")
    if not frontend_client_secret:
        print(f"   {RED}❌ Frontend CLIENT_SECRET not found{RESET}")
        all_checks_passed = False
    elif not backend_client_secret:
        print(f"   {RED}❌ Backend CLIENT_SECRET not found{RESET}")
        all_checks_passed = False
    elif frontend_client_secret != backend_client_secret:
        print(f"   {RED}❌ CLIENT_SECRET MISMATCH! THIS WILL CAUSE invalid_credentials ERROR!{RESET}")
        print(f"   Frontend: {frontend_client_secret[:4]}...{frontend_client_secret[-4:]}")
        print(f"   Backend:  {backend_client_secret[:4]}...{backend_client_secret[-4:]}")
        all_checks_passed = False
    else:
        print(f"   {GREEN}✅ CLIENT_SECRET matches:{RESET} {frontend_client_secret[:4]}...{frontend_client_secret[-4:]}")
    
    # Summary
    print(f"\n{BOLD}{'='*60}{RESET}")
    if all_checks_passed:
        print(f"{GREEN}{BOLD}✅ ALL CHECKS PASSED{RESET}")
        print(f"\nYour OAuth credentials are synchronized correctly.")
        print(f"Frontend and backend are using the same OAuth application.")
        print(f"\n{BLUE}Next steps:{RESET}")
        print(f"  1. Clear Redis tokens: redis-cli FLUSHDB")
        print(f"  2. Have users reconnect Tastytrade accounts")
        print(f"  3. Test signal approval")
        return True
    else:
        print(f"{RED}{BOLD}❌ VERIFICATION FAILED{RESET}")
        print(f"\n{YELLOW}Action Required:{RESET}")
        print(f"  1. Ensure frontend and backend have IDENTICAL credentials")
        print(f"  2. Copy credentials from: https://my.tastytrade.com/settings/api")
        print(f"  3. Update BOTH .env files with the same values")
        print(f"  4. Redeploy frontend to Vercel")
        print(f"  5. Restart backend service on EC2")
        print(f"  6. Run this script again to verify")
        return False

if __name__ == "__main__":
    success = verify_credentials()
    sys.exit(0 if success else 1)
