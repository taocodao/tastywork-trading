#!/usr/bin/env python3
"""
Redis Token Cleanup Script

Clears all Tastytrade tokens from Redis to force users to re-authenticate.
Use this after changing OAuth credentials.
"""

import os
import sys
from redis import Redis
from dotenv import load_dotenv

load_dotenv()

def clear_tastytrade_tokens():
    """Clear all Tastytrade tokens from Redis."""
    
    # Get Redis connection from environment
    redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
    redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    if not redis_url or not redis_token:
        print("❌ Error: UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be set")
        print("   These should be in your .env file")
        sys.exit(1)
    
    print("\n🔍 Connecting to Redis...")
    
    try:
        # Note: Upstash uses REST API, not direct Redis connection
        # For Upstash, we need to use their REST API or upstash-redis client
        print("⚠️  This script requires the upstash-redis Python client")
        print("   Install with: pip install upstash-redis")
        print("\n   Alternative: Use Upstash console to clear keys manually:")
        print(f"   1. Go to: {redis_url.replace('https://', 'https://console.upstash.com/')}")
        print("   2. Navigate to Data Browser")
        print("   3. Search for keys matching: tastytrade:*")
        print("   4. Delete all matching keys")
        
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Tastytrade Token Cleanup")
    print("="*60)
    print("\nThis will clear all user Tastytrade tokens from Redis.")
    print("Users will need to reconnect their accounts after this.")
    print("\n⚠️  WARNING: This cannot be undone!")
    
    confirm = input("\nType 'YES' to confirm: ")
    
    if confirm != 'YES':
        print("\n❌ Cancelled")
        sys.exit(0)
    
    clear_tastytrade_tokens()
