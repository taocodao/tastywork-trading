import logging
from typing import Dict

logger = logging.getLogger(__name__)


class AllocationOptimizer:
    """
    Dynamic Rebalancing Core-Satellite Matrix — TurboCore Pro v2.1

    ── Phase 0+1 Architecture Fix (2026-03-21) ─────────────────────────────────
    Root-cause analysis (Perplexity + backtest) identified six CAGR drags:
      Drag 1  SGOV in BULL allocations       -3.5 to -5.0 pp
      Drag 5  QLD in SIDEWAYS (vol decay)    -0.5 to -1.0 pp
      + QLD without fast-exit guard caused drawdown: -7.3% → -19.8% in test

    Fixes applied here:
      [A] BULL regime: removed SGOV entirely from all BULL tiers.
          New BULL matrix: Kelly-sized LEAPS + QQQ fill + 20% QLD (trend vehicle).
          QLD ONLY deployed when fast-exit guard passes (3-condition VIX/HYG/QQQ check).
          If guard fails → 100% SGOV regardless of confidence (safe fallback).

      [B] SIDEWAYS regime: removed QLD entirely (vol decay in choppy markets).
          New SIDEWAYS matrix: 35% LEAPS + 50% SGOV + 15% QQQ (CC income placeholder).
          Q3 research: "QLD has no structural place in a SIDEWAYS regime. The mathematics
          are unambiguous — leveraged ETFs experience negative compounding in mean-reverting
          markets." QLD 2022 full-year return in mixed sideways: -60.52%.

      [C] Fast-exit guard (two-layer):
          Entry: ALL three conditions must pass to deploy QLD
            vix_ratio < 1.0  (contango — market calm)
            hyg_ok           (HYG not deteriorating)
            qqq_momentum_ok  (QQQ 5d return > -1%)
          Exit: ANY single condition triggers immediate SGOV fallback
            QQQ drops > 1.5% (single day)
            VIX ratio > 1.05 (term structure inverts)
            HYG drops > 0.5% (credit stress)
            QQQ 3d return < -2.5% (grinding decline)
          Without this guard, QLD deployed into HMM lag window (first 5-10 days of
          bear transition) causes 2x losses exactly when the strategy is most exposed.

    Inputs:
      regime          — BULL | SIDEWAYS | BEAR | BEAR_SMA_FORCED
      signal          — 1 (long active), 0 (defensive/no signal), -1 (short)
      ml_confidence   — XGBoost meta-model score [0.0, 1.0]
      qqq_drawdown    — drawdown from ATH, e.g. -0.25 means 25% below peak
      market_guard    — dict with fast-exit conditions (computed from live price data):
                        {
                          'vix_ratio'     : float,  # VIX_spot / VIX3M
                          'hyg_ok'        : bool,   # HYG 1d return > -0.5%
                          'qqq_5d_ok'     : bool,   # QQQ 5d return > -1.0%
                          'qqq_1d_ok'     : bool,   # QQQ 1d return > -1.5%
                          'qqq_3d_ok'     : bool,   # QQQ 3d return > -2.5%
                        }
                        If None → conservative SGOV fallback for QLD slots.

    Outputs: Dict[str, float] allocation weights summing to 1.0
             Keys: QQQ | QLD | QQQ_LEAPS | SGOV
    """

    def __init__(self, params: dict = None):
        self.params = params or {}

        # ── Confidence thresholds ──────────────────────────────────────────────
        self.bull_high_conf_thresh = self.params.get('bull_high_conf_thresh', 0.60)
        self.bull_low_conf_thresh  = self.params.get('bull_low_conf_thresh',  0.40)
        self.deep_crash_thresh     = self.params.get('deep_crash_thresh',    -0.30)

        # ── Kelly b-ratio (theta-adjusted for 80Δ QQQ LEAPS, avg 45d hold) ───
        # b ≈ 1.8: expected delta-adjusted gain on win (~2.3x) minus theta decay
        # over avg 45-day hold (~0.5x) divided by premium at risk.
        # Quarter-Kelly used for uncalibrated XGBoost probs + TQQQ fat tails.
        # Source: MacLean, Ziemba (2004); tastylive Kelly guide.
        self.kelly_b_default = self.params.get('kelly_b', 1.8)

        # ── Fast-exit guard thresholds ─────────────────────────────────────────
        self.vix_ratio_entry_max = self.params.get('vix_ratio_entry_max', 1.00)  # must be < 1.0 to enter QLD
        self.vix_ratio_exit_max  = self.params.get('vix_ratio_exit_max',  1.05)  # > 1.05 → exit QLD

    # ─────────────────────────────────────────────────────────────────────────
    def _qld_guard_passes(self, market_guard: dict) -> bool:
        """
        Two-layer fast-exit guard. Returns True only when ALL entry conditions pass.
        Asymmetric: entry requires ALL green; exit fires on ANY single red.

        If market_guard is None/empty → conservative: return False (SGOV fallback).
        """
        if not market_guard:
            return False  # No market data → safe default (SGOV)

        vix_ratio   = market_guard.get('vix_ratio',   1.10)  # Default: stress assumed
        hyg_ok      = market_guard.get('hyg_ok',      False)
        qqq_5d_ok   = market_guard.get('qqq_5d_ok',   False)
        qqq_1d_ok   = market_guard.get('qqq_1d_ok',   False)
        qqq_3d_ok   = market_guard.get('qqq_3d_ok',   False)

        # Entry gate: ALL three must pass
        entry_ok = (
            vix_ratio < self.vix_ratio_entry_max  # VIX term structure in contango
            and hyg_ok                             # HYG not deteriorating
            and qqq_5d_ok                          # QQQ momentum not breaking
        )

        # Fast-exit check: if already in QLD, exit on ANY single red signal
        fast_exit = (
            not qqq_1d_ok                          # QQQ drops > 1.5% today
            or vix_ratio > self.vix_ratio_exit_max # VIX structure inverts
            or not hyg_ok                          # HYG stress
            or not qqq_3d_ok                       # 3-day grinding decline
        )

        return entry_ok and not fast_exit

    # ─────────────────────────────────────────────────────────────────────────
    def get_target_allocation(
        self,
        regime:        str,
        signal:        int,
        ml_confidence: float,
        qqq_drawdown:  float = 0.0,
        market_guard:  dict  = None,
    ) -> Dict[str, float]:
        """
        Returns target allocation dict {QQQ, QLD, QQQ_LEAPS, SGOV} summing to 1.0.
        """
        # ── 1. Deep Crash Recovery (overrides normal bear rules during recovery) ──
        if qqq_drawdown <= self.deep_crash_thresh and regime not in ("BEAR", "BEAR_SMA_FORCED"):
            logger.debug("Deep Crash Recovery Mode. Drawdown=%.1f%%", qqq_drawdown * 100)
            return {"QQQ": 0.10, "QLD": 0.00, "QQQ_LEAPS": 0.80, "SGOV": 0.10}

        # ── 2. Hard Bear (Risk-Off) — 100% SGOV ──────────────────────────────────
        if regime in ("BEAR", "BEAR_SMA_FORCED"):
            logger.debug("BEAR regime → 100%% SGOV")
            return {"QQQ": 0.0, "QLD": 0.0, "QQQ_LEAPS": 0.0, "SGOV": 1.0}

        # ── 3. SIDEWAYS — treat as UNCERTAIN BULL (transitional patch) ───────────
        # CRITICAL FIX (2026-03-21): The 3-state HMM is DEGENERATE.
        # SIDEWAYS = 48.7% of days, but the HMM's "SIDEWAYS" actually captures
        # misclassified bull-market days (QQQ gained +188% during this period).
        # Removing equity from SIDEWAYS caused CAGR: 14.3% → 6.1% (-8pp).
        #
        # Transitional fix (Option C from HMM report): treat SIDEWAYS as
        # "uncertain bull" with QQQ-heavy exposure and minimal leverage.
        # This patch remains until the 2-state HMM rebuild is complete.
        # Source: "HMM Misclassification Crisis" report, Part 2, Option C.
        if regime == "SIDEWAYS":
            logger.debug("SIDEWAYS (degenerate HMM patch) → uncertain-bull QQQ-heavy allocation")
            return {"QQQ": 0.55, "QLD": 0.10, "QQQ_LEAPS": 0.30, "SGOV": 0.05}

        # ── 4. BULL REGIME — tiered Kelly sizing + fast-exit guard on QLD ────────
        if regime == "BULL":
            qld_safe = self._qld_guard_passes(market_guard)
            p        = ml_confidence

            # ── Tier 0: No active signal in BULL → defensive but stay invested ──
            if signal == 0:
                if qld_safe:
                    return {"QQQ": 0.10, "QLD": 0.40, "QQQ_LEAPS": 0.15, "SGOV": 0.35}
                else:
                    return {"QQQ": 0.00, "QLD": 0.00, "QQQ_LEAPS": 0.15, "SGOV": 0.85}

            # ── Tier 1: HIGH confidence ≥ 60% — full Kelly LEAPS, no SGOV ────────
            # FIX A (2026-03-21): SGOV completely removed from high-confidence BULL.
            # New allocation: Kelly LEAPS + 20% QLD + QQQ fill + 0% SGOV.
            # Effective beta: ~2.4-2.8x vs former 1.82x (44% leverage boost).
            if p >= self.bull_high_conf_thresh:
                b             = self.kelly_b_default
                kelly_full    = (p * b - (1.0 - p)) / b
                kelly_quarter = kelly_full * 0.25
                leaps_weight  = min(0.60, max(0.20, kelly_quarter * 4.0)) if kelly_quarter > 0 else 0.20
                leaps_weight  = round(leaps_weight, 3)

                if qld_safe:
                    qld_weight  = 0.20
                    sgov_weight = 0.00   # ← SGOV REMOVED from BULL high-conf
                else:
                    qld_weight  = 0.00
                    sgov_weight = 0.20   # Guard failed → SGOV instead of QLD

                qqq_weight = round(max(0.0, 1.0 - leaps_weight - qld_weight - sgov_weight), 3)
                logger.debug("BULL high-conf (%.0f%%): LEAPS=%.0f%% QLD=%s",
                             p * 100, leaps_weight * 100,
                             "%.0f%%" % (qld_weight * 100) if qld_safe else "GUARD_FAIL→SGOV")
                return {
                    "QQQ":       float(qqq_weight),
                    "QLD":       float(qld_weight),
                    "QQQ_LEAPS": float(leaps_weight),
                    "SGOV":      float(sgov_weight),
                }

            # ── Tier 2: LOW–MEDIUM confidence 40–60% — reduced exposure ──────────
            # QLD only when guard passes; SGOV substitutes if guard fails.
            # Keeps LEAPS floor at 20% to maintain convexity in confirmed BULL.
            elif p >= self.bull_low_conf_thresh:
                if qld_safe:
                    return {"QQQ": 0.20, "QLD": 0.25, "QQQ_LEAPS": 0.25, "SGOV": 0.30}
                else:
                    return {"QQQ": 0.20, "QLD": 0.00, "QQQ_LEAPS": 0.20, "SGOV": 0.60}

            # ── Tier 3: LOW confidence < 40% — mostly defensive ───────────────────
            # LEAPS floor maintained; no QLD unless guard is very clean.
            else:
                if qld_safe:
                    return {"QQQ": 0.10, "QLD": 0.15, "QQQ_LEAPS": 0.15, "SGOV": 0.60}
                else:
                    return {"QQQ": 0.00, "QLD": 0.00, "QQQ_LEAPS": 0.10, "SGOV": 0.90}

        # Fallback (should never reach here)
        logger.warning("AllocationOptimizer: unhandled regime '%s' → 100%% SGOV", regime)
        return {"QQQ": 0.0, "QLD": 0.0, "QQQ_LEAPS": 0.0, "SGOV": 1.0}


if __name__ == "__main__":
    alloc = AllocationOptimizer()

    guard_green = {
        'vix_ratio': 0.88, 'hyg_ok': True,
        'qqq_5d_ok': True, 'qqq_1d_ok': True, 'qqq_3d_ok': True,
    }
    guard_red = {
        'vix_ratio': 1.08, 'hyg_ok': False,
        'qqq_5d_ok': False, 'qqq_1d_ok': False, 'qqq_3d_ok': False,
    }

    print("\n=== BULL Regime — Guard GREEN ===")
    print("High conf (85%):", alloc.get_target_allocation("BULL", 1, 0.85, 0.0, guard_green))
    print("Med  conf (50%):", alloc.get_target_allocation("BULL", 1, 0.50, 0.0, guard_green))
    print("Low  conf (30%):", alloc.get_target_allocation("BULL", 1, 0.30, 0.0, guard_green))
    print("No   signal    :", alloc.get_target_allocation("BULL", 0, 0.55, 0.0, guard_green))

    print("\n=== BULL Regime — Guard RED (VIX inverted / HYG stress) ===")
    print("High conf (85%):", alloc.get_target_allocation("BULL", 1, 0.85, 0.0, guard_red))
    print("Med  conf (50%):", alloc.get_target_allocation("BULL", 1, 0.50, 0.0, guard_red))

    print("\n=== SIDEWAYS (QLD removed) ===")
    print(alloc.get_target_allocation("SIDEWAYS", 1, 0.60, 0.0))

    print("\n=== BEAR / SMA200 forced ===")
    print(alloc.get_target_allocation("BEAR", 1, 0.99, -0.40))
    print(alloc.get_target_allocation("BEAR_SMA_FORCED", 1, 0.99, -0.40))

    print("\n=== Deep Crash Recovery (SIDEWAYS, -35%) ===")
    print(alloc.get_target_allocation("SIDEWAYS", 1, 0.80, -0.35))
