"""
Settings API Routes
====================
Endpoints for managing trading strategy settings including risk levels.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
import os
import json
import logging
from pathlib import Path

router = APIRouter()
logger = logging.getLogger(__name__)

# Settings persistence file
SETTINGS_FILE = Path("data/theta_settings.json")


class RiskLevelUpdate(BaseModel):
    """Risk level update request."""
    level: Literal["LOW", "MEDIUM", "HIGH"]


class RiskProfileResponse(BaseModel):
    """Risk profile details for frontend display."""
    level: str
    name: str
    description: str
    max_positions: int
    max_capital_deployed_pct: float
    cash_reserve_pct: float
    max_portfolio_heat: float
    contracts_per_trade: int
    breach_confirmation_days: int
    vix_block_trading: float
    vix_close_all: float
    expected_max_loss_pct: float
    expected_annual_roi_pct: float
    recovery_time_months: str


def _load_settings() -> dict:
    """Load settings from disk."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE) as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load settings: {e}")
    return {"risk_level": "MEDIUM"}


def _save_settings(settings: dict) -> None:
    """Save settings to disk."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")


@router.get("/risk-level")
async def get_risk_level():
    """
    Get current risk level and all profile options.
    
    Returns the active risk level and details for all three profiles
    so the frontend can display comparison information.
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        from src.theta_spreads.risk_profiles import (
            RiskLevel, RISK_PROFILES, LOW_RISK_PROFILE, 
            MEDIUM_RISK_PROFILE, HIGH_RISK_PROFILE
        )
        
        settings = _load_settings()
        current_level = settings.get("risk_level", "MEDIUM").upper()
        
        def profile_to_dict(profile) -> dict:
            return {
                "level": profile.level.value.upper(),
                "name": profile.name,
                "description": profile.description,
                "max_positions": profile.max_positions,
                "max_capital_deployed_pct": profile.max_capital_deployed_pct,
                "cash_reserve_pct": profile.cash_reserve_pct,
                "max_portfolio_heat": profile.max_portfolio_heat,
                "contracts_per_trade": profile.contracts_per_trade,
                "breach_confirmation_days": profile.breach_confirmation_days,
                "vix_block_trading": profile.vix_block_trading,
                "vix_close_all": profile.vix_close_all,
                "expected_max_loss_pct": profile.expected_max_loss_pct,
                "expected_annual_roi_pct": profile.expected_annual_roi_pct,
                "recovery_time_months": profile.recovery_time_months,
            }
        
        return {
            "current_level": current_level,
            "profiles": {
                "LOW": profile_to_dict(LOW_RISK_PROFILE),
                "MEDIUM": profile_to_dict(MEDIUM_RISK_PROFILE),
                "HIGH": profile_to_dict(HIGH_RISK_PROFILE),
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting risk level: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/risk-level")
async def set_risk_level(request: RiskLevelUpdate):
    """
    Set the Theta strategy risk level.
    
    Updates the risk level setting. Takes effect on next scheduler run.
    Valid values: LOW, MEDIUM, HIGH
    """
    try:
        level = request.level.upper()
        
        if level not in ["LOW", "MEDIUM", "HIGH"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid risk level '{level}'. Must be LOW, MEDIUM, or HIGH."
            )
        
        # Save to settings file
        settings = _load_settings()
        settings["risk_level"] = level
        _save_settings(settings)
        
        # Also update environment variable for current session
        os.environ["THETA_RISK_LEVEL"] = level
        
        logger.info(f"✅ Risk level changed to: {level}")
        
        return {
            "status": "success",
            "message": f"Risk level set to {level}",
            "current_level": level
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting risk level: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk-profiles")
async def list_risk_profiles():
    """
    Get all available risk profiles with full details.
    
    Used by the frontend to display profile comparison cards.
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        from src.theta_spreads.risk_profiles import (
            LOW_RISK_PROFILE, MEDIUM_RISK_PROFILE, HIGH_RISK_PROFILE
        )
        
        def profile_summary(profile, icon: str) -> dict:
            return {
                "level": profile.level.value.upper(),
                "name": profile.name,
                "icon": icon,
                "description": profile.description,
                "highlights": {
                    "max_positions": profile.max_positions,
                    "capital_deployed": f"{int(profile.max_capital_deployed_pct * 100)}%",
                    "cash_reserve": f"{int(profile.cash_reserve_pct * 100)}%",
                    "vix_close_all": f">{int(profile.vix_close_all)}",
                    "expected_roi": f"{int(profile.expected_annual_roi_pct * 100)}%",
                    "max_loss": f"-{int(profile.expected_max_loss_pct * 100)}%",
                    "recovery": profile.recovery_time_months
                }
            }
        
        return {
            "profiles": [
                profile_summary(LOW_RISK_PROFILE, "🛡️"),
                profile_summary(MEDIUM_RISK_PROFILE, "⚖️"),
                profile_summary(HIGH_RISK_PROFILE, "🚀"),
            ]
        }
        
    except Exception as e:
        logger.error(f"Error listing risk profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
