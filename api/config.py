"""API Configuration."""

import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # API Settings
    api_secret_key: str = os.getenv("API_SECRET_KEY", "dev-secret-key")
    cors_origins: List[str] = [
        "http://localhost:3000",
        "https://trademind.bot",
        "https://www.trademind.bot",
    ]
    
    # Tastytrade Settings
    tastytrade_client_id: str = os.getenv("TASTYTRADE_CLIENT_ID", "")
    tastytrade_client_secret: str = os.getenv("TASTYTRADE_CLIENT_SECRET", "")
    tastytrade_refresh_token: str = os.getenv("TASTYTRADE_REFRESH_TOKEN", "")
    
    # Encryption
    encryption_key: str = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
    
    # Database (optional, for signal storage)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./trademind.db")
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra env vars not defined here


settings = Settings()
