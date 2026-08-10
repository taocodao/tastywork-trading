"""
PhaseManager unit tests — Section 7 edge cases from the implementation plan.

Run: python3 -m pytest src/qqq_leaps/test_phase_manager.py -q
  or: python3 src/qqq_leaps/test_phase_manager.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("phase_manager", os.path.join(os.path.dirname(__file__), "phase_manager.py"))
_pm = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_pm)
PhaseManager, PhaseConfigError = _pm.PhaseManager, _pm.PhaseConfigError

BASE = {
    "enabled": True,
    "demotion_buffer_pct": 0.05,
    "min_dwell_days": 5,
    "emergency_demotion_dd_pct": 0.15,
    "phases": [
        {"name": "SEED", "nav_min": 0, "nav_max": 14999, "delta_bull": 0.55, "max_positions": 1},
        {"name": "GROWTH", "nav_min": 15000, "nav_max": 29999, "delta_bull": 0.75, "max_positions": 2},
        {"name": "TARGET", "nav_min": 30000, "nav_max": None, "delta_bull": 0.85, "max_positions": 3},
    ],
}

D0 = datetime(2026, 1, 5)


def make_pm(**overrides) -> PhaseManager:
    cfg = {"phase_system": {**BASE, **overrides}}
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(cfg, f)
        path = f.name
    return PhaseManager(path)


def day(n):
    return D0 + timedelta(days=n)


def test_initial_assignment():
    pm = make_pm()
    assert pm.evaluate(day(0), 8600).name == "SEED"
    assert pm.transition_log[0].reason == "INITIAL_ASSIGNMENT"
    print("ok initial_assignment")


def test_promotion_dwell_gated():
    pm = make_pm()
    pm.evaluate(day(0), 8600)
    # NAV above GROWTH floor but only 2 days elapsed -> no promotion
    assert pm.evaluate(day(2), 16000).name == "SEED"
    # 5 days elapsed -> promote
    assert pm.evaluate(day(5), 16000).name == "GROWTH"
    assert pm.transition_log[-1].reason == "PROMOTION"
    print("ok promotion_dwell_gated")


def test_skip_level_promotion():
    pm = make_pm()
    pm.evaluate(day(0), 8600)
    # Big realized gain jumps NAV straight past GROWTH into TARGET band
    assert pm.evaluate(day(6), 31000).name == "TARGET"
    print("ok skip_level_promotion")


def test_threshold_oscillation_hysteresis():
    """Edge case 3: NAV oscillating around the 15K boundary must not flip-flop."""
    pm = make_pm()
    pm.evaluate(day(0), 8600)
    pm.evaluate(day(5), 16000)  # promote to GROWTH
    assert pm.current_phase.name == "GROWTH"
    # NAV dips just below 15000 but above the buffered floor (15000 * 0.95 = 14250)
    for i, nav in enumerate([14950, 15050, 14900, 15100, 14800]):
        pm.evaluate(day(6 + i), nav)
        assert pm.current_phase.name == "GROWTH", f"flip on nav={nav}"
    print("ok threshold_oscillation_hysteresis")


def test_demotion_requires_buffer_and_dwell():
    pm = make_pm()
    pm.evaluate(day(0), 16000)  # GROWTH
    # Below buffered floor (14250) but only 2 days in phase -> no demotion
    assert pm.evaluate(day(2), 14000).name == "GROWTH"
    # After dwell, below buffered floor -> demote
    assert pm.evaluate(day(6), 14000).name == "SEED"
    assert pm.transition_log[-1].reason == "DEMOTION_HYSTERESIS_CONFIRMED"
    print("ok demotion_requires_buffer_and_dwell")


def test_emergency_demotion_bypasses_dwell():
    pm = make_pm()
    pm.evaluate(day(0), 31000)  # TARGET
    # 18% single-day drawdown lands NAV in SEED band, 1 day after entry
    assert pm.evaluate(day(1), 13000, prior_nav=31000).name == "SEED"
    assert pm.transition_log[-1].reason.startswith("EMERGENCY_DEMOTION")
    print("ok emergency_demotion_bypasses_dwell")


def test_emergency_dd_within_band_no_transition():
    pm = make_pm()
    pm.evaluate(day(0), 40000)  # TARGET
    # 16% drawdown but NAV (33600) still in TARGET band -> no transition
    assert pm.evaluate(day(1), 33600, prior_nav=40000).name == "TARGET"
    print("ok emergency_dd_within_band_no_transition")


def test_disabled_returns_nav_appropriate_phase_not_max():
    pm = make_pm(enabled=False)
    # Disabled system must fail safe to SEED for a small account, not TARGET
    assert pm.evaluate(day(0), 8600).name == "SEED"
    assert pm.evaluate(day(10), 50000).name == "TARGET"
    print("ok disabled_fails_safe")


def test_rapid_repromotion_after_emergency():
    pm = make_pm()
    pm.evaluate(day(0), 31000)
    pm.evaluate(day(1), 13000, prior_nav=31000)  # emergency -> SEED
    # Recovery to TARGET band; dwell applies to re-promotion (5 days)
    assert pm.evaluate(day(3), 32000).name == "SEED"
    assert pm.evaluate(day(7), 32000).name == "TARGET"
    print("ok rapid_repromotion_after_emergency")


def test_malformed_configs_rejected():
    # Non-whitelisted key
    try:
        make_pm(phases=[{"name": "SEED", "nav_min": 0, "nav_max": None, "pmcc_profit_take_early": 0.5}])
        raise AssertionError("should have rejected non-whitelisted key")
    except PhaseConfigError:
        pass
    # Overlapping bands
    try:
        make_pm(phases=[
            {"name": "A", "nav_min": 0, "nav_max": 20000},
            {"name": "B", "nav_min": 15000, "nav_max": None},
        ])
        raise AssertionError("should have rejected overlap")
    except PhaseConfigError:
        pass
    # Highest phase bounded
    try:
        make_pm(phases=[{"name": "A", "nav_min": 0, "nav_max": 100}])
        raise AssertionError("should have rejected bounded top phase")
    except PhaseConfigError:
        pass
    print("ok malformed_configs_rejected")


def test_apply_to_only_whitelisted():
    pm = make_pm()
    pm.evaluate(day(0), 8600)

    class FakeCfg:
        delta_bull = 0.85
        max_positions = 3
        pmcc_profit_take_early = 0.20  # management param — must never be touched

    cfg = pm.apply_to(FakeCfg())
    assert cfg.delta_bull == 0.55
    assert cfg.max_positions == 1
    assert cfg.pmcc_profit_take_early == 0.20
    print("ok apply_to_only_whitelisted")


if __name__ == "__main__":
    test_initial_assignment()
    test_promotion_dwell_gated()
    test_skip_level_promotion()
    test_threshold_oscillation_hysteresis()
    test_demotion_requires_buffer_and_dwell()
    test_emergency_demotion_bypasses_dwell()
    test_emergency_dd_within_band_no_transition()
    test_disabled_returns_nav_appropriate_phase_not_max()
    test_rapid_repromotion_after_emergency()
    test_malformed_configs_rejected()
    test_apply_to_only_whitelisted()
    print("\nALL PHASE MANAGER TESTS PASSED")
