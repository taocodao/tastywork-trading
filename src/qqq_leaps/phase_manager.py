"""
NAV-Based Phase Manager — QQQ LEAPS + PMCC
==========================================
Deterministic capital-scaling phases driven solely by account NAV.

Design (per implementation plan, with corrections made during code review):

1. NAV is the sole phase trigger, evaluated at DAILY CLOSE. The backtest/live
   loop calls evaluate() once per day with the latest closing NAV; the returned
   phase's parameters govern NEW entries only.

2. Hysteresis + dwell time prevent flip-flopping around a threshold.

3. Grandfathering: only whitelisted ENTRY/SIZING-time config fields are
   phase-varying (delta/DTE/position limits/PMCC entry deltas). Management-time
   params (PMCC profit-take, roll, loss multiple) are identical across phases,
   so open positions continue under their entry-time rules for free.

4. Emergency demotion bypasses dwell time when close-over-close drawdown
   exceeds the configured threshold.

5. Skip-level promotion is allowed (SEED -> TARGET directly) — the dwell check
   applies to the current phase, not to visiting intermediates.

6. When the system is disabled, the NAV-appropriate phase is returned (NOT the
   max/TARGET phase) — failing safe, never silently max-sizing a small account.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import yaml
import logging

log = logging.getLogger("PhaseManager")

# Config fields a phase may override. Entry/sizing-time only — this is what
# makes grandfathering (plan principle #3) hold by construction.
PHASE_PARAM_WHITELIST = frozenset({
    "delta_bull", "delta_neutral", "delta_bear",
    "dte_bull", "dte_neutral", "dte_bear",
    "max_positions", "max_contracts", "max_position_pct",
    "pmcc_enabled",
    "pmcc_delta_bull_strong", "pmcc_delta_bull_moderate", "pmcc_delta_defensive",
    "cash_reserve",
})

# Phase metadata keys that are NOT config params.
_PHASE_META_KEYS = frozenset({"name", "nav_min", "nav_max"})


@dataclass
class Phase:
    name: str
    nav_min: float
    nav_max: Optional[float]
    params: dict  # whitelisted Config overrides

    def contains(self, nav: float) -> bool:
        return self.nav_min <= nav and (self.nav_max is None or nav <= self.nav_max)


@dataclass
class PhaseTransitionEvent:
    ts: object
    from_phase: str
    to_phase: str
    nav_at_transition: float
    reason: str


class PhaseConfigError(ValueError):
    """Raised at startup for a malformed phase config — never mid-run."""


class PhaseManager:
    def __init__(self, config_path: str):
        with open(config_path) as f:
            raw = yaml.safe_load(f)["phase_system"]

        self.enabled = bool(raw.get("enabled", True))
        self.demotion_buffer_pct = float(raw.get("demotion_buffer_pct", 0.05))
        self.min_dwell_days = int(raw.get("min_dwell_days", 5))
        self.emergency_demotion_dd_pct = float(raw.get("emergency_demotion_dd_pct", 0.15))

        self.phases: List[Phase] = []
        for p in raw["phases"]:
            params = {k: v for k, v in p.items() if k not in _PHASE_META_KEYS}
            unknown = set(params) - PHASE_PARAM_WHITELIST
            if unknown:
                raise PhaseConfigError(
                    f"Phase '{p.get('name')}' sets non-whitelisted keys {sorted(unknown)}. "
                    f"Only entry/sizing fields are phase-varying: {sorted(PHASE_PARAM_WHITELIST)}"
                )
            self.phases.append(Phase(p["name"], float(p["nav_min"]), p.get("nav_max"), params))

        self._validate_bands()

        self.current_phase: Optional[Phase] = None
        self.phase_entered_ts = None
        self.phase_entered_nav: Optional[float] = None
        self.transition_log: List[PhaseTransitionEvent] = []

    def _validate_bands(self):
        """Bands must be sorted, contiguous, non-overlapping, covering [0, inf)."""
        if not self.phases:
            raise PhaseConfigError("phase_system.phases is empty")
        prev_max = -1.0
        for i, p in enumerate(self.phases):
            if p.nav_max is not None and p.nav_max < p.nav_min:
                raise PhaseConfigError(f"Phase {p.name}: nav_max < nav_min")
            if i > 0 and p.nav_min <= prev_max:
                raise PhaseConfigError(f"Phase {p.name}: overlaps or is out of order (nav_min={p.nav_min}, prev nav_max={prev_max})")
            prev_max = p.nav_max if p.nav_max is not None else float("inf")
        if self.phases[0].nav_min > 0:
            raise PhaseConfigError("Lowest phase must start at nav_min=0")
        if self.phases[-1].nav_max is not None:
            raise PhaseConfigError("Highest phase must have nav_max=null (no upper bound)")

    def _phase_for_nav(self, nav: float) -> Phase:
        for p in self.phases:
            if p.contains(nav):
                return p
        return self.phases[0]

    def _rank(self, phase: Phase) -> int:
        return [p.name for p in self.phases].index(phase.name)

    def evaluate(self, ts, nav: float, prior_nav: Optional[float] = None) -> Phase:
        """Call once per day with the latest closing NAV. Returns active phase."""
        target_phase = self._phase_for_nav(nav)

        if not self.enabled:
            # Fail safe: still return the NAV-appropriate phase, never max sizing.
            return target_phase

        if self.current_phase is None:
            self._set_phase(ts, target_phase, nav, reason="INITIAL_ASSIGNMENT")
            return self.current_phase

        # Emergency demotion: large close-over-close drawdown bypasses dwell lock.
        # Only fires when the drawdown actually crosses a phase boundary.
        if prior_nav and prior_nav > 0:
            dd = (prior_nav - nav) / prior_nav
            if dd >= self.emergency_demotion_dd_pct:
                if target_phase.name != self.current_phase.name:
                    self._set_phase(ts, target_phase, nav, reason=f"EMERGENCY_DEMOTION_DD_{dd:.1%}")
                    return self.current_phase
                else:
                    log.warning(
                        f"[PHASE] {dd:.1%} close-over-close drawdown but NAV still in "
                        f"{self.current_phase.name} band — no transition"
                    )

        if target_phase.name == self.current_phase.name:
            return self.current_phase

        dwell_elapsed = (ts - self.phase_entered_ts).days if self.phase_entered_ts is not None else 10**9

        if self._rank(target_phase) > self._rank(self.current_phase):
            # Promotion (skip-level allowed): dwell-gated only.
            if dwell_elapsed >= self.min_dwell_days:
                self._set_phase(ts, target_phase, nav, reason="PROMOTION")
            return self.current_phase

        # Demotion: NAV must clear the current phase's floor by the buffer.
        buffered_floor = self.current_phase.nav_min * (1 - self.demotion_buffer_pct)
        if nav < buffered_floor and dwell_elapsed >= self.min_dwell_days:
            self._set_phase(ts, target_phase, nav, reason="DEMOTION_HYSTERESIS_CONFIRMED")
        return self.current_phase

    def _set_phase(self, ts, new_phase: Phase, nav: float, reason: str):
        from_name = self.current_phase.name if self.current_phase else "NONE"
        event = PhaseTransitionEvent(ts, from_name, new_phase.name, nav, reason)
        self.transition_log.append(event)
        log.info(f"[PHASE TRANSITION] {from_name} -> {new_phase.name} @ NAV=${nav:,.2f} ({reason})")
        self.current_phase = new_phase
        self.phase_entered_ts = ts
        self.phase_entered_nav = nav

    # ── Config application ────────────────────────────────────────────────────

    def apply_to(self, cfg):
        """Return a copy of cfg with the active phase's whitelisted overrides."""
        import copy
        new_cfg = copy.copy(cfg)
        phase = self.current_phase
        if phase is None:
            return new_cfg
        for k, v in phase.params.items():
            if k in PHASE_PARAM_WHITELIST and hasattr(new_cfg, k):
                setattr(new_cfg, k, v)
        return new_cfg
