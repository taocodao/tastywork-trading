import logging

logger = logging.getLogger(__name__)

class TQQQPositionSizer:
    """
    Calculates how many contracts to trade based on:
      - User's investment principal (e.g., $25,000)
      - Risk level (LOW=5%, MEDIUM=7.5%, HIGH=10%)
      - Signal's max loss per contract
      - Max concurrent position cap
    """

    RISK_PCT = {"LOW": 0.05, "MEDIUM": 0.075, "HIGH": 0.10}
    MAX_POSITIONS = {"LOW": 3, "MEDIUM": 5, "HIGH": 7}

    @staticmethod
    def calculate(
        principal: float,
        risk_level: str,       # "LOW" | "MEDIUM" | "HIGH"
        credit: float,         # Per-contract credit received (e.g. 0.85)
        spread_width: float,   # Spread width in dollars (e.g. 5.00)
        active_positions: int = 0, # How many TQQQ positions already open
    ) -> dict:
        risk_level = risk_level.upper()
        risk_pct = TQQQPositionSizer.RISK_PCT.get(risk_level, 0.075)
        max_positions = TQQQPositionSizer.MAX_POSITIONS.get(risk_level, 5)

        max_risk_per_trade = principal * risk_pct
        max_loss_per_contract = (spread_width - credit) * 100  # e.g. ($5 - $0.85) × 100 = $415

        # Position cap boundary condition
        if active_positions >= max_positions:
            logger.info(f"Position blocked: {active_positions} active >= {max_positions} max for {risk_level} risk.")
            return {
                "quantity": 0, 
                "reason": "max_positions_reached",
                "maxRiskPerTrade": round(max_risk_per_trade, 2),
                "maxLossPerContract": round(max_loss_per_contract, 2)
            }

        if max_loss_per_contract <= 0:
             logger.warning("Invalid spread width or credit. Max loss <= 0.")
             return {"quantity": 0, "reason": "invalid_parameters"}

        # Floor division: how many contracts stay within risk budget
        quantity = max(1, int(max_risk_per_trade / max_loss_per_contract))

        # Cap at 10 contracts regardless to avoid liquidity/execution issues
        quantity = min(quantity, 10)

        return {
            "quantity": quantity,
            "maxRiskPerTrade": round(max_risk_per_trade, 2),
            "maxLossPerContract": round(max_loss_per_contract, 2),
            "totalCredit": round(credit * quantity * 100, 2),
            "totalMaxLoss": round(max_loss_per_contract * quantity, 2),
            "riskPct": risk_pct,
        }
