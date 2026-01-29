#!/usr/bin/env python3
"""
Credential Enforcement Middleware

This module provides runtime validation that frontend and backend 
are using the same OAuth credentials. Add this to your backend startup.
"""

import os
import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CredentialMismatchError(Exception):
    """Raised when OAuth credentials don't match between frontend and backend."""
    pass

def validate_oauth_credentials(
    expected_client_id: Optional[str] = None,
    expected_client_secret_hash: Optional[str] = None
) -> bool:
    """
    Validate that backend OAuth credentials match expected values.
    
    This should be called at startup to ensure credential consistency.
    
    Args:
        expected_client_id: The client_id that should be used (optional)
        expected_client_secret_hash: SHA256 hash of the expected client_secret (optional)
        
    Returns:
        True if validation passes
        
    Raises:
        CredentialMismatchError if credentials don't match
    """
    
    backend_client_id = os.getenv('TASTYTRADE_CLIENT_ID')
    backend_client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
    
    # Check if credentials are set
    if not backend_client_id:
        raise CredentialMismatchError(
            "TASTYTRADE_CLIENT_ID not set in backend environment. "
            "This must match the frontend OAuth application."
        )
    
    if not backend_client_secret:
        raise CredentialMismatchError(
            "TASTYTRADE_CLIENT_SECRET not set in backend environment. "
            "This must match the frontend OAuth application."
        )
    
    # Validate against expected values if provided
    if expected_client_id and backend_client_id != expected_client_id:
        raise CredentialMismatchError(
            f"Backend CLIENT_ID mismatch!\n"
            f"Expected: {expected_client_id[:10]}...{expected_client_id[-10:]}\n"
            f"Got:      {backend_client_id[:10]}...{backend_client_id[-10:]}\n"
            f"All refresh_token operations will fail with invalid_credentials!"
        )
    
    # For secret, we compare hashes to avoid logging the actual secret
    if expected_client_secret_hash:
        import hashlib
        actual_hash = hashlib.sha256(backend_client_secret.encode()).hexdigest()
        if actual_hash != expected_client_secret_hash:
            raise CredentialMismatchError(
                "Backend CLIENT_SECRET mismatch! "
                "This will cause all OAuth operations to fail with invalid_credentials. "
                "Ensure frontend and backend are using the SAME OAuth application."
            )
    
    logger.info(
        f"✅ OAuth credentials validated: CLIENT_ID={backend_client_id[:10]}...{backend_client_id[-10:]}"
    )
    return True


def startup_credential_check():
    """
    Run this at application startup to catch credential issues early.
    
    Example usage in FastAPI:
        @app.on_event("startup")
        async def on_startup():
            from credential_enforcement import startup_credential_check
            startup_credential_check()
    """
    
    try:
        validate_oauth_credentials()
        print("✅ OAuth credential validation passed")
    except CredentialMismatchError as e:
        print(f"\n{'='*60}")
        print("❌ CRITICAL: OAuth Credential Mismatch Detected")
        print(f"{'='*60}")
        print(f"\n{e}\n")
        print("Action Required:")
        print("  1. Check frontend .env.local for TASTYTRADE_CLIENT_SECRET")
        print("  2. Check backend .env for TASTYTRADE_CLIENT_SECRET")
        print("  3. Ensure they are IDENTICAL")
        print("  4. Restart the application")
        print(f"\n{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    # Test the validation
    startup_credential_check()
