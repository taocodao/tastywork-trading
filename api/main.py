"""
TradeMind API - FastAPI Backend
================================
Provides endpoints for:
- Account data (balance, positions) from Tastytrade
- Trade signals (CRUD)
- Trade execution
- User credential management
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging

from .routes import account, signals, trade, user, zebra, dvo
from .config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 TradeMind API starting up...")
    yield
    logger.info("👋 TradeMind API shutting down...")


app = FastAPI(
    title="TradeMind API",
    description="Backend API for TradeMind trading platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(account.router, prefix="/api/account", tags=["Account"])
app.include_router(signals.router, prefix="/api/signals", tags=["Signals"])
app.include_router(trade.router, prefix="/api/trade", tags=["Trade"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(zebra.router, prefix="/api/zebra", tags=["ZEBRA Strategy"])
app.include_router(dvo.router, prefix="/api/dvo", tags=["DVO Strategy"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "TradeMind API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "tastytrade_configured": bool(os.getenv("TASTYTRADE_CLIENT_SECRET")),
    }
