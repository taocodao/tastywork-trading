"""
User Management Routes
======================
Handle user credential storage and Tastytrade linking.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from ..services.encryption import encrypt_credential, decrypt_credential

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory user credential storage (would be database in production)
_user_credentials: dict = {}


class LinkTastytradeRequest(BaseModel):
    """Request to link Tastytrade account."""
    user_id: str
    client_id: str
    client_secret: str
    refresh_token: str
    account_number: Optional[str] = None


class LinkStatusResponse(BaseModel):
    """Tastytrade link status."""
    user_id: str
    is_linked: bool
    account_number: Optional[str] = None
    linked_at: Optional[str] = None


@router.post("/link-tastytrade")
async def link_tastytrade_account(request: LinkTastytradeRequest):
    """
    Store encrypted Tastytrade OAuth credentials.
    
    Credentials are encrypted with AES-256 before storage.
    """
    try:
        # Encrypt sensitive credentials
        encrypted_secret = encrypt_credential(request.client_secret)
        encrypted_token = encrypt_credential(request.refresh_token)
        
        # Store encrypted credentials
        _user_credentials[request.user_id] = {
            "client_id": request.client_id,
            "client_secret_enc": encrypted_secret,
            "refresh_token_enc": encrypted_token,
            "account_number": request.account_number,
            "linked_at": "2026-01-19T00:00:00Z",  # Would be datetime.utcnow()
        }
        
        logger.info(f"Linked Tastytrade for user: {request.user_id}")
        
        return {
            "status": "linked",
            "message": "Tastytrade account linked successfully",
            "account_number": request.account_number,
        }
        
    except Exception as e:
        logger.error(f"Failed to link Tastytrade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{user_id}", response_model=LinkStatusResponse)
async def get_link_status(user_id: str):
    """
    Check if user has linked Tastytrade account.
    """
    creds = _user_credentials.get(user_id)
    
    if creds:
        return LinkStatusResponse(
            user_id=user_id,
            is_linked=True,
            account_number=creds.get("account_number"),
            linked_at=creds.get("linked_at"),
        )
    
    return LinkStatusResponse(
        user_id=user_id,
        is_linked=False,
    )


@router.delete("/unlink/{user_id}")
async def unlink_tastytrade(user_id: str):
    """
    Remove Tastytrade credentials for a user.
    """
    if user_id in _user_credentials:
        del _user_credentials[user_id]
        logger.info(f"Unlinked Tastytrade for user: {user_id}")
        return {"status": "unlinked", "message": "Tastytrade account unlinked"}
    
    raise HTTPException(status_code=404, detail="User not found")


def get_user_credentials(user_id: str) -> Optional[dict]:
    """
    Get decrypted credentials for a user.
    
    Used internally by the Tastytrade service.
    """
    creds = _user_credentials.get(user_id)
    if not creds:
        return None
    
    return {
        "client_id": creds["client_id"],
        "client_secret": decrypt_credential(creds["client_secret_enc"]),
        "refresh_token": decrypt_credential(creds["refresh_token_enc"]),
        "account_number": creds.get("account_number"),
    }
