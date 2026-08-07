"""
FROZEN COPY of the v2.1 LEAPS-based allocation matrix.

Kept only so the Phase 4 ablation waterfall can measure stages A and B (the
original v2 configuration, with and without the Phase 0 correctness fixes)
against the v3 stages in the same environment and on the same data. Nothing in
the live v3 pipeline imports this module — see allocation_optimizer.py for the
production matrix.
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class AllocationOptimizerV2Legacy:
    """v2.1 matrix over QQQ | QLD | QQQ_LEAPS | SGOV."""

    def __init__(self, params: dict = None):
        self.params = params or {}
        self.bull_high_conf_thresh = self.params.get('bull_high_conf_thresh', 0.60)
        self.bull_low_conf_thresh = self.params.get('bull_low_conf_thresh', 0.40)
        self.deep_crash_thresh = self.params.get('deep_crash_thresh', -0.30)
        self.kelly_b_default = self.params.get('kelly_b', 1.8)
        self.vix_ratio_entry_max = self.params.get('vix_ratio_entry_max', 1.00)
        self.vix_ratio_exit_max = self.params.get('vix_ratio_exit_max', 1.05)

    def _qld_guard_passes(self, market_guard: dict) -> bool:
        if not market_guard:
            return False
        vix_ratio = market_guard.get('vix_ratio', 1.10)
        hyg_ok = market_guard.get('hyg_ok', False)
        qqq_5d_ok = market_guard.get('qqq_5d_ok', False)
        qqq_1d_ok = market_guard.get('qqq_1d_ok', False)
        qqq_3d_ok = market_guard.get('qqq_3d_ok', False)
        entry_ok = (vix_ratio < self.vix_ratio_entry_max and hyg_ok and qqq_5d_ok)
        fast_exit = (not qqq_1d_ok or vix_ratio > self.vix_ratio_exit_max
                     or not hyg_ok or not qqq_3d_ok)
        return entry_ok and not fast_exit

    def get_target_allocation(self, regime: str, signal: int, ml_confidence: float,
                              qqq_drawdown: float = 0.0,
                              market_guard: dict = None) -> Dict[str, float]:
        if qqq_drawdown <= self.deep_crash_thresh and regime not in ("BEAR", "BEAR_SMA_FORCED"):
            return {"QQQ": 0.10, "QLD": 0.00, "QQQ_LEAPS": 0.80, "SGOV": 0.10}

        if regime in ("BEAR", "BEAR_SMA_FORCED"):
            return {"QQQ": 0.0, "QLD": 0.0, "QQQ_LEAPS": 0.0, "SGOV": 1.0}

        if regime == "SIDEWAYS":
            return {"QQQ": 0.55, "QLD": 0.10, "QQQ_LEAPS": 0.30, "SGOV": 0.05}

        if regime == "BULL":
            qld_safe = self._qld_guard_passes(market_guard)
            p = ml_confidence

            if signal == 0:
                if qld_safe:
                    return {"QQQ": 0.10, "QLD": 0.40, "QQQ_LEAPS": 0.15, "SGOV": 0.35}
                return {"QQQ": 0.00, "QLD": 0.00, "QQQ_LEAPS": 0.15, "SGOV": 0.85}

            if p >= self.bull_high_conf_thresh:
                b = self.kelly_b_default
                kelly_full = (p * b - (1.0 - p)) / b
                kelly_quarter = kelly_full * 0.25
                leaps_weight = min(0.60, max(0.20, kelly_quarter * 4.0)) if kelly_quarter > 0 else 0.20
                leaps_weight = round(leaps_weight, 3)
                if qld_safe:
                    qld_weight, sgov_weight = 0.20, 0.00
                else:
                    qld_weight, sgov_weight = 0.00, 0.20
                qqq_weight = round(max(0.0, 1.0 - leaps_weight - qld_weight - sgov_weight), 3)
                return {"QQQ": float(qqq_weight), "QLD": float(qld_weight),
                        "QQQ_LEAPS": float(leaps_weight), "SGOV": float(sgov_weight)}

            if p >= self.bull_low_conf_thresh:
                if qld_safe:
                    return {"QQQ": 0.20, "QLD": 0.25, "QQQ_LEAPS": 0.25, "SGOV": 0.30}
                return {"QQQ": 0.20, "QLD": 0.00, "QQQ_LEAPS": 0.20, "SGOV": 0.60}

            if qld_safe:
                return {"QQQ": 0.10, "QLD": 0.15, "QQQ_LEAPS": 0.15, "SGOV": 0.60}
            return {"QQQ": 0.00, "QLD": 0.00, "QQQ_LEAPS": 0.10, "SGOV": 0.90}

        logger.warning("AllocationOptimizerV2Legacy: unhandled regime '%s' → 100%% SGOV", regime)
        return {"QQQ": 0.0, "QLD": 0.0, "QQQ_LEAPS": 0.0, "SGOV": 1.0}
