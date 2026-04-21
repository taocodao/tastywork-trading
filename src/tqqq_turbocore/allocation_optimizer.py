import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class AllocationOptimizer:
    """
    Dynamic Rebalancing Core-Satellite Matrix — v2.1.
    
    Architecture:
      - Uses p_loss as a hard veto gate (relaxed to >0.65 threshold).
      - ML confidence selects between High/Medium Bull tiers.
      - Includes RSI(2) mean-reversion, Drawdown-adaptive sizing, Vol-targeting.
      - NEW: Weak Bull tier for SIDEWAYS + EMA cross.
    """

    TARGET_VOL = 0.22

    def __init__(self, params: dict = None):
        self.params = params or {}
        
        # Bull High Config (Aggressive) — updated to 60% TQQQ, 22% QLD
        self.bh_qqq = self.params.get('bh_qqq', 0.17)
        self.bh_qld = self.params.get('bh_qld', 0.22)
        self.bh_tqqq = self.params.get('bh_tqqq', 0.60)
        self.bh_sgov = self.params.get('bh_sgov', 0.01)
        
        # Bull Medium Config (Moderate)
        self.bm_qqq = self.params.get('bm_qqq', 0.40)
        self.bm_qld = self.params.get('bm_qld', 0.00)
        self.bm_tqqq = self.params.get('bm_tqqq', 0.60)
        self.bm_sgov = self.params.get('bm_sgov', 0.00)

        # Bull Weak Config (for SIDEWAYS + EMA cross)
        self.bw_qqq = self.params.get('bw_qqq', 0.50)
        self.bw_qld = self.params.get('bw_qld', 0.00)
        self.bw_tqqq = self.params.get('bw_tqqq', 0.30)
        self.bw_sgov = self.params.get('bw_sgov', 0.20)
        
        # Sideways / Defensive Config (Wait/Side)
        self.def_qqq = self.params.get('def_qqq', 0.66)
        self.def_qld = self.params.get('def_qld', 0.00)
        self.def_tqqq = self.params.get('def_tqqq', 0.00)
        self.def_sgov = self.params.get('def_sgov', 0.34)
        
        # Thresholds
        self.bull_high_conf_thresh = self.params.get('bull_high_conf_thresh', 0.65)
        self.bull_med_conf_thresh = self.params.get('bull_med_conf_thresh', 0.45)
        self.p_loss_veto_thresh = self.params.get('p_loss_veto_thresh', 0.65) # Relaxed from 0.50
        
    def get_target_allocation(
        self,
        regime: str,
        signal: int,
        ml_confidence: float = 0.55,
        dual_confirm: bool = False,
        rsi_add: bool = False,
        rsi_trim: bool = False,
        portfolio_drawdown_pct: float = 0.0,
        current_vol: Optional[float] = None,
        p_loss: float = 0.0,
        vix_close: float = 20.0
    ) -> Dict[str, float]:
        
        base_alloc = {"QQQ": 0.0, "QLD": 0.0, "TQQQ": 0.0, "SGOV": 1.0}
        
        # 1. HARD BEAR -> Risk Off
        if regime in ["BEAR", "BEAR_SMA_FORCED"]:
            logger.info(f"Regime {regime}: 100% SGOV")
            return base_alloc
            
        # 2. ML VETO GATE (Relaxed to 0.65)
        if signal == 1 and p_loss > self.p_loss_veto_thresh:
            logger.info(f"p_loss veto triggered (p_loss={p_loss:.3f} > {self.p_loss_veto_thresh}). Deflecting to Defensive.")
            base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
            return self._apply_modifiers(base_alloc, rsi_add, rsi_trim, portfolio_drawdown_pct, current_vol)

        # 3. SIDEWAYS 
        if regime == "SIDEWAYS":
            # Only go defensive if VIX > 25, otherwise if there's a signal, treat as Weak Bull
            if signal == 1:
                if vix_close > 25:
                    logger.debug("SIDEWAYS + signal=1 but VIX > 25 -> Defensive")
                    base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
                else:
                    logger.debug("SIDEWAYS + signal=1 and VIX <= 25 -> Weak Bull")
                    base_alloc = {"QQQ": self.bw_qqq, "QLD": self.bw_qld, "TQQQ": self.bw_tqqq, "SGOV": self.bw_sgov}
            else:
                base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
                
        # 4. BULL REGIME
        elif regime == "BULL":
            if signal == 1:
                # dual_confirm overrides to High Bull
                if dual_confirm or ml_confidence > self.bull_high_conf_thresh:
                    base_alloc = {"QQQ": self.bh_qqq, "QLD": self.bh_qld, "TQQQ": self.bh_tqqq, "SGOV": self.bh_sgov}
                elif ml_confidence > self.bull_med_conf_thresh:
                    base_alloc = {"QQQ": self.bm_qqq, "QLD": self.bm_qld, "TQQQ": self.bm_tqqq, "SGOV": self.bm_sgov}
                else:
                    base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
            else:
                base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
                
        return self._apply_modifiers(base_alloc, rsi_add, rsi_trim, portfolio_drawdown_pct, current_vol)

    def _apply_modifiers(self, alloc, rsi_add, rsi_trim, dd_pct, current_vol):
        # RSI Modifier
        tqqq = alloc.get("TQQQ", 0.0)
        sgov = alloc.get("SGOV", 0.0)
        if rsi_add and tqqq > 0:
            amt = tqqq * 0.15
            alloc["TQQQ"] = min(tqqq + amt, 0.85)
            alloc["SGOV"] = max(0.0, sgov - amt)
        elif rsi_trim and tqqq > 0:
            amt = tqqq * 0.15
            alloc["TQQQ"] = max(0.0, tqqq - amt)
            alloc["SGOV"] = sgov + amt

        # Volatility Targeting Overlay
        if current_vol and current_vol > 0:
            vol_scalar = min(1.5, max(0.25, self.TARGET_VOL / current_vol))
            if abs(vol_scalar - 1.0) >= 0.05:
                tqqq_orig = alloc.get("TQQQ", 0.0)
                qld_orig = alloc.get("QLD", 0.0)
                alloc["TQQQ"] = tqqq_orig * vol_scalar
                alloc["QLD"] = qld_orig * vol_scalar
                delta = (alloc["TQQQ"] - tqqq_orig) + (alloc["QLD"] - qld_orig)
                alloc["SGOV"] = max(0.0, alloc.get("SGOV", 0.0) - delta)

        # Drawdown Adaptive Sizing
        if dd_pct > 0:
            if dd_pct >= 0.30:
                return {"QQQ": 0.0, "QLD": 0.0, "TQQQ": 0.0, "SGOV": 1.0}
            
            if dd_pct >= 0.20: mult = 0.50
            elif dd_pct >= 0.10: mult = 0.75
            else: mult = 1.0

            if mult < 1.0:
                tqqq_orig = alloc.get("TQQQ", 0.0)
                qld_orig = alloc.get("QLD", 0.0)
                qqq_orig = alloc.get("QQQ", 0.0)
                alloc["TQQQ"] = tqqq_orig * mult
                alloc["QLD"] = qld_orig * mult
                alloc["QQQ"] = qqq_orig * (1.0 - (1.0 - mult) * 0.3)
                freed = (tqqq_orig - alloc["TQQQ"]) + (qld_orig - alloc["QLD"]) + (qqq_orig - alloc["QQQ"])
                alloc["SGOV"] += freed

        return self._normalize(alloc)
        
    @staticmethod
    def _normalize(alloc: Dict[str, float]) -> Dict[str, float]:
        result = {k: max(0.0, v) for k, v in alloc.items()}
        total = sum(result.values())
        if total > 0 and abs(total - 1.0) > 0.001:
            result = {k: round(v / total, 4) for k, v in result.items()}
        return result
