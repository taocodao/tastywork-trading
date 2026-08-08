import logging
from typing import Dict

logger = logging.getLogger(__name__)

TICKERS = ("QQQ", "QLD", "TQQQ", "SGOV")


class AllocationOptimizer:
    """
    Dynamic Rebalancing Core-Satellite Matrix — TurboCore Pro v3.

    ── v3 changes vs v2.1 ──────────────────────────────────────────────────────
    Phase 1 (LEAPS removal). The QQQ_LEAPS sleeve and its Kelly sizing are gone.
    The instrument universe is QQQ (1x) / QLD (2x) / TQQQ (3x) / SGOV (cash).
    QLD is the moderate-conviction leverage tier and TQQQ the high-conviction
    tier — an engineering hypothesis, not a literature-validated split.

    Phase 2.1 (BULL cash floor). The BULL defensive cash weight is now the
    single tunable `bull_sgov_floor` rather than a hardcoded 35%. Every BULL
    tier expresses its SGOV weight as a multiple of that floor, so the Phase 4
    grid search moves the whole BULL row of the matrix coherently.

    Phase 2.2 (graduated SMA200). The binary `below SMA200 -> 100% SGOV` gate is
    replaced by three bands keyed on how far below the 200-day SMA price sits,
    with the original hard floor preserved for deep breaks and for bars where
    the HMM and MS-GARCH both independently vote BEAR.

    Phase 2.3 (confidence tiers). `ml_confidence` is a score in [0,1] whose
    scale is set by the caller: pass the raw meta-model probability with
    raw-style thresholds, or a trailing percentile rank with percentile-style
    thresholds. This class only compares against `bull_high_conf_thresh` /
    `bull_low_conf_thresh`, so both modes work without a branch here.

    Preserved from v2.1: the asymmetric fast-exit guard on leveraged sleeves
    (ALL conditions must be green to add leverage, ANY one red removes it) and
    the deep-crash recovery override.

    ── v3.1 follow-up knobs ────────────────────────────────────────────────────
    All three default to v3 behaviour, so an unconfigured instance is
    bit-identical to v3.

    `vix_ratio_entry_max` / `vix_ratio_exit_max` — the guard reads whatever
    `vix_ratio` means in the feature set, and the two candidate definitions
    (VIX/30d-average vs the true VIX/VIX3M) sit ~1 std apart. Carrying v3's
    absolute thresholds onto the true ratio silently loosens the guard from
    31% fast-exit firing to 5.8%, so the thresholds must move with the series.

    `both_bear_override_scope` — 'all' is plan §2.2 as written and suppresses
    the graduated SMA200 tier on 82% of BEAR_SMA_FORCED bars. 'beyond_shallow'
    exempts the 0..-3% band so the tier can express the V-shaped-rally case the
    band was built for, while deep breaks keep the unconditional cash floor.

    `conf_sgov_floors` — per-confidence-tier SGOV floors. v3's single floor was
    already tier-scaled by fixed multiples (0.5x/1.0x/1.5x), so the tiers could
    only move together; this lets the floor be an arbitrary decreasing function
    of confidence.

    Inputs:
      regime            — BULL | SIDEWAYS | BEAR | BEAR_SMA_FORCED
      signal            — 1 (long active), 0 (defensive/no signal), -1 (short)
      ml_confidence     — conviction score in [0, 1] (raw prob or percentile rank)
      qqq_drawdown      — drawdown from ATH, e.g. -0.25 means 25% below peak
      market_guard      — fast-exit guard inputs; see _leverage_guard_passes
      pct_below_sma200  — signed % distance of QQQ from its 200d SMA
                          (-0.05 = 5% below). Only consulted for BEAR_SMA_FORCED.
      ensemble_both_bear— True when HMM and MS-GARCH both vote BEAR. Forces the
                          hard 100% SGOV floor regardless of SMA200 band.

    Output: Dict[str, float] over QQQ | QLD | TQQQ | SGOV, summing to 1.0.
    """

    def __init__(self, params: dict = None):
        self.params = params or {}

        # ── Confidence tier thresholds ─────────────────────────────────────────
        # Defaults are percentile-rank scale (Phase 2.3). Callers feeding the raw
        # meta-model probability should override with ~0.60 / ~0.40.
        self.bull_high_conf_thresh = self.params.get('bull_high_conf_thresh', 0.70)
        self.bull_low_conf_thresh = self.params.get('bull_low_conf_thresh', 0.40)
        self.deep_crash_thresh = self.params.get('deep_crash_thresh', -0.30)

        # ── Phase 2.1: tunable BULL cash floor (was hardcoded 0.35 in v2) ──────
        self.bull_sgov_floor = self.params.get('bull_sgov_floor', 0.20)

        # ── v3.1 issue 3: optional per-confidence-tier SGOV floors ─────────────
        # None/{} keeps v3's flat behaviour, where each tier's floor is a fixed
        # multiple of bull_sgov_floor. Supplying explicit floors overrides those
        # products tier by tier; see _tier_floors.
        self.conf_sgov_floors = dict(self.params.get('conf_sgov_floors') or {})
        unknown = set(self.conf_sgov_floors) - {'high', 'med', 'low'}
        if unknown:
            raise ValueError(f"unknown conf_sgov_floors keys {sorted(unknown)}")

        # ── Fast-exit guard thresholds ─────────────────────────────────────────
        # Scale-coupled to whatever `vix_ratio` means in the feature set. The v3
        # defaults were fitted to VIX/30d-average-VIX; the true VIX/VIX3M sits a
        # full standard deviation lower and needs the quantile-matched values
        # from v31_guard_calibration.py instead.
        self.vix_ratio_entry_max = self.params.get('vix_ratio_entry_max', 1.00)
        self.vix_ratio_exit_max = self.params.get('vix_ratio_exit_max', 1.05)

        # ── Phase 2.2: graduated SMA200 band edges (signed, negative = below) ──
        self.sma_band_shallow = self.params.get('sma_band_shallow', -0.03)
        self.sma_band_deep = self.params.get('sma_band_deep', -0.08)

        # Ablation switch: False restores the v2 binary 100%-SGOV hard gate.
        self.graduated_sma200 = self.params.get('graduated_sma200', True)

        # ── v3.1 issue 2: scope of the ensemble-both-BEAR hard override ────────
        # 'all' is plan v3 §2.2 as written. 'beyond_shallow' exempts the 0..-3%
        # band so the graduated tier can actually engage; measurement showed the
        # 'all' scope suppressed it on 82% of BEAR_SMA_FORCED bars.
        self.both_bear_override_scope = self.params.get('both_bear_override_scope', 'all')
        if self.both_bear_override_scope not in ('all', 'beyond_shallow'):
            raise ValueError(f"unknown both_bear_override_scope "
                             f"{self.both_bear_override_scope!r}")
        # Middle-ground fallback: when set, a both-BEAR bar in the exempted
        # shallow band gets this QQQ weight (no leverage) instead of the band's
        # normal 20/10 QQQ/QLD split.
        self.shallow_both_bear_qqq = self.params.get('shallow_both_bear_qqq')

        # ── Phase 4.1: QLD/TQQQ tiering variant ────────────────────────────────
        # 'both' is the v3 default. 'tqqq_only' / 'qld_only' collapse the two
        # leveraged sleeves into one at CONSTANT target beta (see _apply_leverage_
        # mode), so the sweep tests the wrapper choice rather than exposure size.
        self.leverage_mode = self.params.get('leverage_mode', 'both')
        if self.leverage_mode not in ('both', 'tqqq_only', 'qld_only'):
            raise ValueError(f"unknown leverage_mode {self.leverage_mode!r}")

        # ── CAGR Phase 1: BULL allocation style ─────────────────────────────────
        # 'tiered' is the v3 default (bit-identical). 'core_satellite' replaces
        # only the HIGH-confidence tier's TQQQ/QLD split with a fixed,
        # video-validated core-satellite mix (60% QQQ-equivalent core / 30% QLD /
        # 10% TQQQ satellite, per the 26yr backtest referenced in the CAGR
        # research prompt) instead of the v3 30/30 TQQQ/QLD split. The med/low
        # tiers and guard-red fallback are untouched — this isolates the
        # high-confidence-tier hypothesis for clean walk-forward attribution.
        self.allocation_style = self.params.get('allocation_style', 'tiered')
        if self.allocation_style not in ('tiered', 'core_satellite'):
            raise ValueError(f"unknown allocation_style {self.allocation_style!r}")
        self.bull_high_tqqq_weight = self.params.get('bull_high_tqqq_weight', 0.30)
        self.bull_high_qld_weight = self.params.get('bull_high_qld_weight', 0.30)
        self.core_sat_tqqq_weight = self.params.get('core_sat_tqqq_weight', 0.10)
        self.core_sat_qld_weight = self.params.get('core_sat_qld_weight', 0.30)

        # -- CAGR Phase 4: volatility-targeted continuous leverage sizing ------
        # Independent ablation flag (composes with allocation_style, does not
        # replace it). False (default) = v3 behaviour, bit-identical.
        self.vol_target_enabled = self.params.get('vol_target_enabled', False)
        self.vol_target_level = self.params.get('vol_target_level', 0.15)
        self.vol_target_min_mult = self.params.get('vol_target_min_mult', 0.5)
        self.vol_target_max_mult = self.params.get('vol_target_max_mult', 1.6)

        # -- SMA200 relaxation experiment knob --------------------------------
        # Fraction of the structural-BEAR bar held in SGOV. v3 default 1.0 =
        # 100% SGOV (bit-identical). Lowering it keeps a partial long position
        # during structural BEAR (HMM+MSGARCH agreement) bars, trading drawdown
        # for CAGR. The residual goes to QQQ (no leverage in a confirmed bear).
        self.bear_sgov_pct = self.params.get('bear_sgov_pct', 1.0)

        # ── CAGR Phase 2: continuous deep-crash-recovery ramp ────────────────
        # False (default) = v3 behaviour: a single binary jump straight to the
        # full contrarian mix the instant qqq_drawdown crosses deep_crash_thresh.
        # True = linearly ramp from a conservative entry mix at deep_crash_thresh
        # up to the full contrarian mix at deep_crash_ramp_full, smoothing the
        # single-bar trigger the CAGR research flagged as noise-sensitive.
        self.continuous_deep_crash = self.params.get('continuous_deep_crash', False)
        self.deep_crash_ramp_full = self.params.get('deep_crash_ramp_full', -0.40)

    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _mix(qqq=0.0, qld=0.0, tqqq=0.0, sgov=0.0) -> Dict[str, float]:
        """Build an allocation dict, clamped to [0,1] and renormalized to 1.0."""
        raw = {"QQQ": max(0.0, qqq), "QLD": max(0.0, qld),
               "TQQQ": max(0.0, tqqq), "SGOV": max(0.0, sgov)}
        total = sum(raw.values())
        if total <= 0:
            return {"QQQ": 0.0, "QLD": 0.0, "TQQQ": 0.0, "SGOV": 1.0}
        return {k: round(v / total, 4) for k, v in raw.items()}

    def _apply_leverage_mode(self, qld: float, tqqq: float, sgov: float) -> tuple:
        """
        Collapse the two leveraged sleeves into one at constant TOTAL portfolio
        beta, so the variants differ only in which wrapper delivers the exposure.

        With QQQ absorbing the residual, total beta is
            B = 1*(1 - qld - tqqq - sgov) + 2*qld + 3*tqqq
              = 1 - sgov + qld + 2*tqqq
        Solving that for a single leveraged sleeve at the same B and same sgov:
            TQQQ only:  tqqq' = (B - 1 + sgov) / 2
            QLD  only:  qld'  =  B - 1 + sgov

        Matching total beta (not just the leveraged sleeves' beta) is the point:
        a naive swap holding only 2*qld + 3*tqqq fixed silently changes the QQQ
        residual and moves total beta by up to ~0.25x between variants, which
        would confound the wrapper comparison with an exposure difference.
        """
        if self.leverage_mode == 'both':
            return qld, tqqq
        beta = 1.0 - sgov + qld + 2.0 * tqqq
        budget = max(0.0, 1.0 - sgov)
        if self.leverage_mode == 'tqqq_only':
            return 0.0, min(budget, max(0.0, (beta - 1.0 + sgov) / 2.0))
        return min(budget, max(0.0, beta - 1.0 + sgov)), 0.0

    def _tier_floors(self) -> Dict[str, float]:
        """
        SGOV floor per BULL confidence tier.

        v3 applied one flat floor scaled by a fixed per-tier multiple
        (0.5x high / 1.0x med / 1.5x low), so the tiers were already implicitly
        floor-differentiated but could only move together. v3.1 lets each tier
        be set outright; leaving a tier unset reproduces the v3 product exactly,
        so `conf_sgov_floors={}` is bit-identical to v3.
        """
        f = self.bull_sgov_floor
        floors = {'high': 0.5 * f, 'med': 1.0 * f, 'low': 1.5 * f}
        floors.update({k: float(v) for k, v in self.conf_sgov_floors.items()
                       if v is not None})
        return floors

    def _leverage_guard_passes(self, market_guard: dict) -> bool:
        """
        Two-layer fast-exit guard governing the QLD/TQQQ sleeves. Entry requires
        ALL conditions green; exit fires on ANY single red. Missing guard data is
        treated as red (conservative SGOV fallback).
        """
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

    # -----------------------------------------------------------------------
    def _vol_scaled_multiplier(self, realized_vol: float) -> float:
        """
        CAGR Phase 4: capped vol-targeting multiplier on the leveraged
        sleeves (QLD/TQQQ) within a BULL tier.

        raw = target_vol / realized_vol. Below-target realized vol scales
        leverage UP (raw > 1), above-target scales it DOWN (raw < 1),
        clamped to [vol_target_min_mult, vol_target_max_mult] so this can
        never exceed v3's existing ~1.6x max leverage envelope or delever
        below half of a tier's normal leveraged weight.

        Caller is responsible for passing an already-lagged/causal realized
        vol (e.g. qqq_vol_20d computed only from bars up to and including
        the current bar's own trailing window -- no future information).
        """
        rv = max(float(realized_vol), 0.01)
        raw = self.vol_target_level / rv
        return min(self.vol_target_max_mult, max(self.vol_target_min_mult, raw))

    # ─────────────────────────────────────────────────────────────────────────
    def _deep_crash_allocation(self, qqq_drawdown: float) -> Dict[str, float]:
        """
        CAGR Phase 2: continuous drawdown-scaled deep-crash recovery ramp.

        v3 jumped straight from whatever the pre-crash allocation was to a
        fixed 15/30/40/15 QQQ/QLD/TQQQ/SGOV mix the instant qqq_drawdown
        crossed deep_crash_thresh (default -30%). That single-bar binary
        trigger is noise-sensitive: one bar's drawdown estimate straddling the
        threshold swings the whole portfolio. This ramps linearly from a
        conservative entry mix at deep_crash_thresh to the full v3 contrarian
        mix at deep_crash_ramp_full (default -40%), so a marginal breach adds
        only a small tilt and the full contrarian allocation is reserved for
        confirmed, deeper drawdowns.

        Only called when self.continuous_deep_crash is True; the binary v3
        path in get_target_allocation is otherwise unchanged.
        """
        full_range = self.deep_crash_ramp_full - self.deep_crash_thresh
        if full_range == 0:
            frac = 1.0
        else:
            frac = (qqq_drawdown - self.deep_crash_thresh) / full_range
            frac = min(1.0, max(0.0, frac))
        entry_mix = dict(qqq=0.30, qld=0.15, tqqq=0.10, sgov=0.45)
        full_mix = dict(qqq=0.15, qld=0.30, tqqq=0.40, sgov=0.15)
        blended = {k: entry_mix[k] + frac * (full_mix[k] - entry_mix[k]) for k in entry_mix}
        return self._mix(**blended)

    # ──────────────────────────────────────────────────────────────────────────
    def _sma200_allocation(self, pct_below_sma200: float,
                           ensemble_both_bear: bool) -> Dict[str, float]:
        """
        Phase 2.2 graduated SMA200 exposure.

        v2 collapsed every bar below the 200d SMA to 100% SGOV, which covered
        24.5% of all bars and surrendered every V-shaped recovery. The bands
        below keep full crash protection for deep breaks and for confirmed
        two-detector bears, while leaving a reduced long position on during
        shallow, unconfirmed breaks.

        v3.1: the both-BEAR override can be scoped to the deeper bands only.
        Under the v3 'all' scope it fired on 82% of BEAR_SMA_FORCED bars and
        left the graduated tier reaching just 4.4% of the sample, which defeated
        the purpose of building it.
        """
        if not self.graduated_sma200:
            return self._mix(sgov=1.0)

        in_shallow = pct_below_sma200 > self.sma_band_shallow      # 0% to -3%
        exempt = in_shallow and self.both_bear_override_scope == 'beyond_shallow'
        if ensemble_both_bear and not exempt:
            return self._mix(sgov=1.0)

        if in_shallow:
            if ensemble_both_bear and self.shallow_both_bear_qqq is not None:
                q = float(self.shallow_both_bear_qqq)
                return self._mix(qqq=q, sgov=1.0 - q)
            return self._mix(qqq=0.20, qld=0.10, sgov=0.70)
        if pct_below_sma200 > self.sma_band_deep:         # -3% to -8% below
            return self._mix(qqq=0.12, sgov=0.88)
        return self._mix(sgov=1.0)                        # beyond -8%

    # ─────────────────────────────────────────────────────────────────────────
    def get_target_allocation(
        self,
        regime:             str,
        signal:             int,
        ml_confidence:      float,
        qqq_drawdown:       float = 0.0,
        market_guard:       dict = None,
        pct_below_sma200:   float = 0.0,
        ensemble_both_bear: bool = False,
        realized_vol:       float = None,
    ) -> Dict[str, float]:
        """Returns target weights over {QQQ, QLD, TQQQ, SGOV} summing to 1.0."""

        # ── 1. Deep crash recovery (overrides normal bear rules) ─────────────
        if qqq_drawdown <= self.deep_crash_thresh and regime not in ("BEAR", "BEAR_SMA_FORCED"):
            logger.debug("Deep Crash Recovery Mode. Drawdown=%.1f%%", qqq_drawdown * 100)
            if self.continuous_deep_crash:
                return self._deep_crash_allocation(qqq_drawdown)
            return self._mix(qqq=0.15, qld=0.30, tqqq=0.40, sgov=0.15)

        # ── 2. SMA200 gate — graduated in v3 (Phase 2.2) ─────────────────────
        if regime == "BEAR_SMA_FORCED":
            return self._sma200_allocation(pct_below_sma200, ensemble_both_bear)

        # ── 3. Structural BEAR (HMM + MS-GARCH agreement) — tunable SGOV ─────
        if regime == "BEAR":
            sgov = max(0.0, min(1.0, self.bear_sgov_pct))
            return self._mix(qqq=1.0 - sgov, sgov=sgov)

        # ── 4. SIDEWAYS — retained for compatibility; the 2-state ensemble ───
        #      never emits it, so this is a defensive branch only.
        if regime == "SIDEWAYS":
            return self._mix(qqq=0.55, qld=0.20, tqqq=0.10, sgov=0.15)

        # ── 5. BULL — confidence-tiered leverage over a tunable cash floor ───
        if regime == "BULL":
            lev_ok = self._leverage_guard_passes(market_guard)
            floors = self._tier_floors()
            p = ml_confidence

            # gf_ratio scales the tier's floor up for the guard-red fallback.
            # The ratios are v3's (gf_sgov / sgov) products held fixed, so the
            # guard-red path keeps its v3 shape when only the floors move.
            if signal == 0:
                tqqq, qld, sgov, gf_ratio = 0.00, 0.12, floors['med'], 3.0
            elif p >= self.bull_high_conf_thresh:
                if self.allocation_style == 'core_satellite':
                    tqqq, qld = self.core_sat_tqqq_weight, self.core_sat_qld_weight
                else:
                    tqqq, qld = self.bull_high_tqqq_weight, self.bull_high_qld_weight
                sgov, gf_ratio = floors['high'], 4.0
            elif p >= self.bull_low_conf_thresh:
                tqqq, qld, sgov, gf_ratio = 0.12, 0.28, floors['med'], 2.5
            else:
                tqqq, qld, sgov, gf_ratio = 0.00, 0.15, floors['low'], 2.0
            gf_sgov = gf_ratio * sgov

            if not lev_ok:
                # Guard red: no leveraged sleeves at all; the tier's risk appetite
                # survives only as the QQQ/SGOV split.
                gf_sgov = min(0.95, gf_sgov)
                return self._mix(qqq=1.0 - gf_sgov, sgov=gf_sgov)

            # -- CAGR Phase 4: vol-targeted continuous leverage sizing -------
            # Scales the tier's leveraged sleeves (QLD/TQQQ) by a realized-vol
            # multiplier BEFORE the leverage_mode wrapper-choice logic below,
            # so it composes cleanly with both allocation_style (Phase 1) and
            # leverage_mode (v3.1). Freed/added weight is absorbed by QQQ via
            # the residual computed below -- SGOV floor is untouched.
            if self.vol_target_enabled and realized_vol is not None:
                mult = self._vol_scaled_multiplier(realized_vol)
                tqqq *= mult
                qld *= mult
                cap = max(0.0, 1.0 - sgov)
                if tqqq + qld > cap:
                    scale = cap / (tqqq + qld) if (tqqq + qld) > 0 else 0.0
                    tqqq *= scale
                    qld *= scale

            qld, tqqq = self._apply_leverage_mode(qld, tqqq, sgov)
            qqq = 1.0 - tqqq - qld - sgov
            return self._mix(qqq=qqq, qld=qld, tqqq=tqqq, sgov=sgov)

        logger.warning("AllocationOptimizer: unhandled regime '%s' → 100%% SGOV", regime)
        return self._mix(sgov=1.0)

    # ─────────────────────────────────────────────────────────────────────────
    def apply_caution(self, allocation: Dict[str, float]) -> Dict[str, float]:
        """
        Phase 1.2 BOCD caution layer, de-LEAPS-ified.

        v2 halved the QQQ_LEAPS sleeve and pushed the freed weight to QQQ. With
        options gone the same intent — step the leverage down one notch on an
        ambiguous changepoint — is expressed by halving the highest-leverage
        sleeve held (TQQQ, else QLD) and moving the freed capital to QQQ.
        """
        out = dict(allocation)
        for sleeve in ("TQQQ", "QLD"):
            if out.get(sleeve, 0.0) > 0.0:
                freed = out[sleeve] * 0.50
                out[sleeve] -= freed
                out["QQQ"] = out.get("QQQ", 0.0) + freed
                break
        return out


if __name__ == "__main__":
    alloc = AllocationOptimizer()
    guard_green = {'vix_ratio': 0.88, 'hyg_ok': True,
                   'qqq_5d_ok': True, 'qqq_1d_ok': True, 'qqq_3d_ok': True}
    guard_red = {'vix_ratio': 1.08, 'hyg_ok': False,
                 'qqq_5d_ok': False, 'qqq_1d_ok': False, 'qqq_3d_ok': False}

    print("\n=== BULL — guard GREEN (confidence = percentile rank) ===")
    for name, p in [("high (0.90)", 0.90), ("mid (0.55)", 0.55), ("low (0.20)", 0.20)]:
        print(f"{name:<12}", alloc.get_target_allocation("BULL", 1, p, 0.0, guard_green))
    print("no signal   ", alloc.get_target_allocation("BULL", 0, 0.90, 0.0, guard_green))

    print("\n=== BULL — guard RED ===")
    for name, p in [("high (0.90)", 0.90), ("low (0.20)", 0.20)]:
        print(f"{name:<12}", alloc.get_target_allocation("BULL", 1, p, 0.0, guard_red))

    print("\n=== Graduated SMA200 bands ===")
    for pct in (-0.01, -0.05, -0.12):
        print(f"{pct:+.0%} below, split ensemble :",
              alloc.get_target_allocation("BEAR_SMA_FORCED", -1, 0.5, -0.05, guard_red, pct, False))
    print("-1% below, BOTH detectors BEAR :",
          alloc.get_target_allocation("BEAR_SMA_FORCED", -1, 0.5, -0.05, guard_red, -0.01, True))
    narrowed = AllocationOptimizer({'both_bear_override_scope': 'beyond_shallow'})
    print("-1% below, BOTH bear, narrowed :",
          narrowed.get_target_allocation("BEAR_SMA_FORCED", -1, 0.5, -0.05, guard_red, -0.01, True))

    print("\n=== Confidence-conditional SGOV floors ===")
    tiered = AllocationOptimizer({'conf_sgov_floors': {'high': 0.15, 'med': 0.25, 'low': 0.40}})
    for name, p in [("high (0.90)", 0.90), ("mid (0.55)", 0.55), ("low (0.20)", 0.20)]:
        print(f"{name:<12}", tiered.get_target_allocation("BULL", 1, p, 0.0, guard_green))

    print("\n=== BEAR / deep crash / caution ===")
    print("structural BEAR :", alloc.get_target_allocation("BEAR", 1, 0.99, -0.40))
    print("deep crash      :", alloc.get_target_allocation("SIDEWAYS", 1, 0.80, -0.35))
    print("caution applied :", alloc.apply_caution(
        alloc.get_target_allocation("BULL", 1, 0.90, 0.0, guard_green)))
