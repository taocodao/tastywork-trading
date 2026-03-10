"""
Shared utilities for Tastytrade API operations.
Provides consistent session and account management across the application.
"""
import os
import logging
from typing import Optional, List

# Try newer OAuthSession, fall back to Session for older versions
try:
    from tastytrade import OAuthSession as Session, Account
except ImportError:
    from tastytrade import Session, Account

logger = logging.getLogger(__name__)


def _get_accounts_safe(session) -> list:
    """
    Version-safe account fetcher for the tastytrade SDK.
    
    Different SDK versions use different class method names.
    This tries each known method name and falls back to raw HTTP.
    """
    # Try known SDK class methods
    for method_name in ['get_accounts', 'a_get_accounts', 'get_customer_accounts']:
        if hasattr(Account, method_name):
            method = getattr(Account, method_name)
            try:
                return method(session)
            except Exception as e:
                logger.debug(f"Account.{method_name} failed: {e}")
                continue
    
    # Fall back to raw HTTP using the session token
    logger.warning("No SDK method for get_accounts found, using raw HTTP fallback")
    try:
        import httpx
        token = getattr(session, 'session_token', None) or getattr(session, 'token', None)
        if not token:
            raise ValueError("Could not extract session token for HTTP fallback")
        headers = {'Authorization': token}
        
        # Use environment variable to support paper trading (cert) vs production
        base_url = os.getenv('TASTYTRADE_API_URL', 'https://api.tastyworks.com').rstrip('/')
        
        resp = httpx.get(
            f'{base_url}/customers/me/accounts',
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        items = resp.json().get('data', {}).get('items', [])
        logger.info(f"✅ Fetched {len(items)} accounts via HTTP fallback")
        return items
    except Exception as e:
        logger.error(f"❌ HTTP fallback for accounts also failed: {e}")
        raise


def create_user_session(refresh_token: str) -> Session:
    """
    Create an OAuth session for a user with their refresh token.
    
    Args:
        refresh_token: User's Tastytrade OAuth refresh token
        
    Returns:
        OAuthSession instance authenticated for the user
        
    Raises:
        ValueError: If TASTYTRADE_CLIENT_SECRET is not configured or session init fails
    """
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
    
    # DEBUG: Log what we're getting from environment
    if client_secret:
        logger.info(f"✅ TASTYTRADE_CLIENT_SECRET loaded: {client_secret[:4]}...{client_secret[-4:]}")
    else:
        logger.error("❌ TASTYTRADE_CLIENT_SECRET is None or empty!")
        logger.error(f"   All env vars: {[k for k in os.environ.keys() if 'TASTY' in k.upper()]}")
    
    if not client_secret:
        raise ValueError(
            "TASTYTRADE_CLIENT_SECRET not set in environment. "
            "Check .env file or systemd EnvironmentFile directive."
        )
    
    # Try modern signature: Session(client_secret, refresh_token)
    try:
        session = Session(
            client_secret=client_secret,
            refresh_token=refresh_token
        )
        logger.info(f"✅ Created user session (modern) expires: {getattr(session, 'session_expiration', 'unknown')}")
        return session
    except TypeError:
        pass
        
    # Try positional arguments (client_secret, refresh_token) - typical for older versions
    try:
        session = Session(client_secret, refresh_token)
        logger.info(f"✅ Created user session (positional) expires: {getattr(session, 'session_expiration', 'unknown')}")
        return session
    except TypeError:
        pass
        
    # Try just passing valid token (some very old or alternative wrappers)
    try:
        session = Session(refresh_token)
        logger.info(f"✅ Created user session (token-only) expires: {getattr(session, 'session_expiration', 'unknown')}")
        return session
    except TypeError:
        pass

    # If all fail, inspect and log to help debug
    import inspect
    try:
        sig = inspect.signature(Session.__init__)
        logger.error(f"❌ Session.__init__ failed. Signature detected: {sig}")
    except Exception:
        logger.error("❌ Session.__init__ failed. Could not inspect signature.")
        
    raise ValueError("Could not initialize Tastytrade Session with installed library version.")


def get_user_account(
    session: Session, 
    account_number: Optional[str] = None
) -> Account:
    """
    Get a user's trading account from their session.
    
    Args:
        session: Authenticated OAuthSession
        account_number: Optional specific account number to retrieve.
                       If None, returns the first account.
        
    Returns:
        Account instance for the user
        
    Raises:
        ValueError: If no accounts are found or specified account doesn't exist
    """
    accounts = _get_accounts_safe(session)
    
    if not accounts:
        raise ValueError("No accounts found for user")
    
    if account_number:
        account = next(
            (a for a in accounts if a.account_number == account_number), 
            None
        )
        if not account:
            raise ValueError(f"Account {account_number} not found for user")
        logger.info(f"📊 Using specified account: {account_number}")
        return account
    
    # Return first account if no specific account requested
    logger.info(f"📊 Using account: {accounts[0].account_number}")
    return accounts[0]


def get_all_user_accounts(session: Session) -> List[Account]:
    """
    Get all trading accounts for a user.
    
    Args:
        session: Authenticated OAuthSession
        
    Returns:
        List of Account instances
        
    Raises:
        ValueError: If no accounts are found
    """
    accounts = _get_accounts_safe(session)
    
    if not accounts:
        raise ValueError("No accounts found for user")
    
    logger.info(f"📊 Found {len(accounts)} account(s)")
    return accounts
