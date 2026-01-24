"""
Google Secret Manager Integration
=================================

Helper module to fetch secrets from Google Cloud Secret Manager.
Requires:
1. Google Cloud Project with Secret Manager API enabled.
2. Authenticated environment (gcloud auth application-default login).
"""

import os
import logging
from typing import Optional
from google.cloud import secretmanager
from google.auth.exceptions import DefaultCredentialsError

logger = logging.getLogger(__name__)

# Cache secrets to avoid redundant API calls
_SECRET_CACHE = {}

def get_secret(
    secret_id: str,
    project_id: str = None,
    version_id: str = "latest"
) -> Optional[str]:
    """
    Fetch a secret from Google Secret Manager.
    
    Args:
        secret_id: Name of the secret (e.g. 'tastytrade_password')
        project_id: Google Cloud Project ID. Defaults to env GOOGLE_CLOUD_PROJECT.
        version_id: Version to fetch (default: 'latest')
        
    Returns:
        Secret value as string, or None if failed.
    """
    global _SECRET_CACHE
    
    # Check cache first
    cache_key = f"{secret_id}:{version_id}"
    if cache_key in _SECRET_CACHE:
        return _SECRET_CACHE[cache_key]
    
    # Determine project ID
    if not project_id:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
    if not project_id:
        logger.warning(
            f"Cannot fetch secret '{secret_id}': "
            "GOOGLE_CLOUD_PROJECT environment variable not set."
        )
        return None
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        
        logger.info(f"Fetching secret: {name}")
        response = client.access_secret_version(request={"name": name})
        
        secret_value = response.payload.data.decode("UTF-8")
        _SECRET_CACHE[cache_key] = secret_value
        return secret_value
        
    except DefaultCredentialsError:
        logger.error(
            "Google Cloud credentials not found. "
            "Run 'gcloud auth application-default login' to authenticate."
        )
        return None
    except Exception as e:
        logger.error(f"Failed to fetch secret '{secret_id}': {e}")
        return None


def get_tastytrade_creds(project_id: str = None) -> dict:
    """
    Convenience function to get Tastytrade credentials (OAuth or Legacy).
    
    Returns dict with keys: 'client_id', 'client_secret', 'refresh_token', 'username', 'password'.
    """
    return {
        'client_id': get_secret('tastytrade_client_id', project_id),
        'client_secret': get_secret('tastytrade_client_secret', project_id),
        'refresh_token': get_secret('tastytrade_refresh_token', project_id),
        # Legacy support
        'username': get_secret('tastytrade_username', project_id),
        'password': get_secret('tastytrade_password', project_id)
    }

def create_or_update_secret(
    secret_id: str,
    secret_value: str,
    project_id: str = None
) -> bool:
    """
    Create a new secret or add a new version to an existing secret.
    
    Args:
        secret_id: Name of the secret
        secret_value: Value to store
        project_id: Google Cloud Project ID
        
    Returns:
        True if successful, False otherwise.
    """
    # Determine project ID
    if not project_id:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT not set, cannot save secret.")
        return False

    try:
        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{project_id}"
        
        # 1. Try to create the secret (ignoring if it exists)
        try:
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
            logger.info(f"Created new secret: {secret_id}")
        except Exception as e:
            # If it already exists, that's fine (409 Conflict)
            if "already exists" not in str(e).lower():
                logger.warning(f"Error checking secret {secret_id}: {e}")
        
        # 2. Add the secret version
        parent_secret = f"{parent}/secrets/{secret_id}"
        payload = secret_value.encode("UTF-8")
        
        client.add_secret_version(
            request={
                "parent": parent_secret,
                "payload": {"data": payload},
            }
        )
        
        logger.info(f"✅ Saved secret '{secret_id}' to Google Secret Manager")
        
        # Update cache
        global _SECRET_CACHE
        _SECRET_CACHE[f"{secret_id}:latest"] = secret_value
        return True
        
    except Exception as e:
        logger.error(f"Failed to save secret '{secret_id}': {e}")
        return False
