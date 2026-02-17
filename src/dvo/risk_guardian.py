
"""
DVO Risk Guardian
=================
Defines 3-tier risk profiles (Low, Medium, High) and enforces hard exposure limits.
"""

from dataclasses import dataclass

@dataclass
class DVORiskProfile:
    name: str
    max_portfolio_leverage: float  # Margin / Net Liq
    max_short_put_notional: float  # % of Net Liq
    max_single_name_exposure: float # % of Net Liq
    max_leaps_premium_risk: float   # % of Net Liq
    leaps_recycling_pct: float      # % of Put premium to spend on LEAPS
    max_concurrent_positions: int
    min_margin_of_safety: float     # Required discount to EPS line
    vix_kill_switch: float

# 3-Tier Risk Profiles (Consistent with ZEBRA/Theta)
DVO_RISK_PROFILES = {
    "LOW": DVORiskProfile(
        name="LOW",
        max_portfolio_leverage=0.20,
        max_short_put_notional=0.20,
        max_single_name_exposure=0.05,
        max_leaps_premium_risk=0.03,
        leaps_recycling_pct=0.0,    # Disabled
        max_concurrent_positions=3,
        min_margin_of_safety=0.25,  # Requires deep value
        vix_kill_switch=35.0
    ),
    "MEDIUM": DVORiskProfile(
        name="MEDIUM",
        max_portfolio_leverage=0.35,
        max_short_put_notional=0.35,
        max_single_name_exposure=0.07,
        max_leaps_premium_risk=0.07,
        leaps_recycling_pct=0.60,   # Recycle 60% of premium
        max_concurrent_positions=5,
        min_margin_of_safety=0.20,
        vix_kill_switch=40.0
    ),
    "HIGH": DVORiskProfile(
        name="HIGH",
        max_portfolio_leverage=0.50,
        max_short_put_notional=0.50,
        max_single_name_exposure=0.10,
        max_leaps_premium_risk=0.10,
        leaps_recycling_pct=1.00,   # Aggressive recycling
        max_concurrent_positions=8,
        min_margin_of_safety=0.15,
        vix_kill_switch=45.0
    )
}

class RiskGuardian:
    def __init__(self, risk_level: str = "MEDIUM"):
        self.profile = DVO_RISK_PROFILES.get(risk_level.upper(), DVO_RISK_PROFILES["MEDIUM"])

    def check_entry(self, 
                    current_leverage: float, 
                    current_positions: int,
                    margin_of_safety: float,
                    current_vix: float = 20.0) -> (bool, str):
        """
        Validates if a new trade can be entered based on risk profile.
        Returns (allowed: bool, reason: str)
        """
        
        # 1. Kill Switch
        if current_vix > self.profile.vix_kill_switch:
            return False, f"VIX {current_vix} exceeds limit {self.profile.vix_kill_switch}"
            
        # 2. Leverage Check
        if current_leverage >= self.profile.max_portfolio_leverage:
            return False, f"Leverage {current_leverage:.2f} >= Limit {self.profile.max_portfolio_leverage}"
            
        # 3. Position Count
        if current_positions >= self.profile.max_concurrent_positions:
            return False, f"Max positions {self.profile.max_concurrent_positions} reached"
            
        # 4. Margin of Safety
        if margin_of_safety < self.profile.min_margin_of_safety:
            return False, f"MoS {margin_of_safety:.2f} < Min {self.profile.min_margin_of_safety}"
            
        return True, "Approved"

    def get_recycling_amount(self, put_credit: float) -> float:
        """Calculate max capital to allocate to LEAPS based on put credit."""
        return put_credit * self.profile.leaps_recycling_pct
