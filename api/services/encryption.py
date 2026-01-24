"""
Credential Encryption Service
=============================
AES-256-GCM encryption for storing Tastytrade OAuth tokens.
"""

import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import logging

logger = logging.getLogger(__name__)

# Get encryption key from environment
_ENCRYPTION_KEY = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")


def _get_key() -> bytes:
    """Get the 32-byte encryption key."""
    if not _ENCRYPTION_KEY:
        # Use a fallback for development (not secure for production!)
        logger.warning("CREDENTIAL_ENCRYPTION_KEY not set, using fallback")
        return hashlib.sha256(b"dev-fallback-key").digest()
    
    # If key is hex-encoded, decode it
    if len(_ENCRYPTION_KEY) == 64:
        return bytes.fromhex(_ENCRYPTION_KEY)
    
    # Otherwise hash it to get 32 bytes
    return hashlib.sha256(_ENCRYPTION_KEY.encode()).digest()


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential using AES-256-GCM.
    
    Returns base64-encoded ciphertext with nonce prepended.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    
    # Generate random 12-byte nonce
    nonce = os.urandom(12)
    
    # Encrypt
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    
    # Prepend nonce to ciphertext and base64 encode
    encrypted = base64.b64encode(nonce + ciphertext).decode()
    return encrypted


def decrypt_credential(encrypted: str) -> str:
    """
    Decrypt a credential encrypted with encrypt_credential.
    
    Returns plaintext string.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    
    # Base64 decode
    data = base64.b64decode(encrypted)
    
    # Extract nonce (first 12 bytes) and ciphertext
    nonce = data[:12]
    ciphertext = data[12:]
    
    # Decrypt
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def generate_encryption_key() -> str:
    """
    Generate a new 32-byte encryption key.
    
    Returns hex-encoded key suitable for CREDENTIAL_ENCRYPTION_KEY.
    """
    return os.urandom(32).hex()
