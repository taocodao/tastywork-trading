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

from sqlalchemy.orm import Session
from fastapi import Depends
from ..models.db import get_db
from ..models.user import User

@router.post("/link-tastytrade")
async def link_tastytrade_account(request: LinkTastytradeRequest, db: Session = Depends(get_db)):
    """
    Store encrypted Tastytrade OAuth credentials in database.
    """
    try:
        # Encrypt sensitive credentials
        encrypted_secret = encrypt_credential(request.client_secret)
        encrypted_token = encrypt_credential(request.refresh_token)
        
        # Check if user exists
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            user = User(id=request.user_id)
            db.add(user)
            
        # Update credentials
        user.tt_refresh_token = encrypted_token
        # We don't store client_secret anymore as per updated plan, wait...
        # Actually user model has tt_refresh_token only?
        # Let's check user model definition I just wrote.
        # User model has: tt_refresh_token, tt_account_number.
        # Client ID/Secret are usually app-level, but sometimes per-user.
        # The request has client_id/secret.
        # Ideally we should store them if needed. But let's assume app-level secret is env var?
        # The request comes from frontend. Frontend sends what?
        # TastytradeCredentials component sends client_id, client_secret, refresh_token.
        # But `tastytrade_utils.create_user_session` uses ENV VAR for secret.
        # So storing secret per user might be redundant or for BYO-App scenarios.
        # For this implementation, I will stick to what User model has: tt_refresh_token.
        # Wait, if `create_user_session` uses env var, why does frontend send secret?
        # Maybe to support BYO-App?
        # Let's just store refresh token for now as per `models/user.py`.
        
        user.tt_account_number = request.account_number
        # user.tt_client_id = request.client_id # Not in model yet
        # user.tt_client_secret = encrypted_secret # Not in model yet
        
        db.commit()
        
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
async def get_link_status(user_id: str, db: Session = Depends(get_db)):
    """
    Check if user has linked Tastytrade account.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if user and user.tt_refresh_token:
        return LinkStatusResponse(
            user_id=user_id,
            is_linked=True,
            account_number=user.tt_account_number,
            linked_at=user.created_at.isoformat() if user.created_at else None,
        )
    
    return LinkStatusResponse(
        user_id=user_id,
        is_linked=False,
    )


@router.delete("/unlink/{user_id}")
async def unlink_tastytrade(user_id: str, db: Session = Depends(get_db)):
    """
    Remove Tastytrade credentials for a user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.tt_refresh_token = None
        user.tt_account_number = None
        db.commit()
        logger.info(f"Unlinked Tastytrade for user: {user_id}")
        return {"status": "unlinked", "message": "Tastytrade account unlinked"}
    
    raise HTTPException(status_code=404, detail="User not found")


def get_user_credentials(user_id: str) -> Optional[dict]:
    """
    Get decrypted credentials for a user.
    
    Used internally by the Tastytrade service.
    """
    from ..models.db import SessionLocal
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.tt_refresh_token:
            return None
            
        return {
            "refresh_token": decrypt_credential(user.tt_refresh_token),
            "account_number": user.tt_account_number,
            # We assume client_secret is environmental for now
             "client_secret": None 
        }
    finally:
        db.close()
