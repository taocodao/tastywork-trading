"""
SNDK Dynamic Ladder Strategy - IV Regime Mapping
==============================================
Maps IVR ranges to specific DTE targets.
"""

def get_dte_for_ivr(ivr: float) -> int:
    """
    Map IV Rank to DTE based on strategy rules.
    - IVR >= 80: 60 DTE (extreme IV, premium is so fat we can go further out)
    - IVR 65-80: 52 DTE (high IV)
    - IVR 45-65: 45 DTE (moderate IV, though we usually skip < 65)
    - IVR < 45:  30 DTE (low IV, rarely entered)
    """
    if ivr >= 80:
        return 60
    elif ivr >= 65:
        return 52
    elif ivr >= 45:
        return 45
    else:
        return 30
