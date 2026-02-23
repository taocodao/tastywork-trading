"""
Unit tests for TQQQ AI Optimization modules.
Tests are focused on import correctness, logic paths, and interface contracts.
They do NOT require live IB connections or ML model files.
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# 1. Config: Regime parameter dictionary
# ─────────────────────────────────────────────────────────────────────────────

def test_tqqq_params_by_regime_all_regimes_present():
    from config import TQQQ_PARAMS_BY_REGIME
    for regime in ("LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"):
        assert regime in TQQQ_PARAMS_BY_REGIME, f"Missing regime: {regime}"

def test_tqqq_params_by_regime_keys_complete():
    from config import TQQQ_PARAMS_BY_REGIME
    required_keys = {"dte", "delta", "width", "profit_target", "loss_limit_mult",
                     "legout_short_threshold", "long_put_profit_target"}
    for regime, params in TQQQ_PARAMS_BY_REGIME.items():
        missing = required_keys - set(params.keys())
        assert not missing, f"Regime {regime} missing keys: {missing}"

def test_tqqq_params_delta_is_negative():
    from config import TQQQ_PARAMS_BY_REGIME
    for regime, params in TQQQ_PARAMS_BY_REGIME.items():
        assert params["delta"] < 0, f"Regime {regime}: delta should be negative (OTM puts)"

def test_tqqq_params_crisis_has_shortest_dte():
    from config import TQQQ_PARAMS_BY_REGIME
    assert TQQQ_PARAMS_BY_REGIME["CRISIS"]["dte"] <= TQQQ_PARAMS_BY_REGIME["NORMAL"]["dte"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Intraday Timing Engine
# ─────────────────────────────────────────────────────────────────────────────

def test_timing_engine_returns_wait_before_open():
    from src.tqqq.ml.timing_engine import IntradayTimingEngine
    engine = IntradayTimingEngine()
    
    # 9:45 AM — inside no-fly zone
    dt = datetime.now().replace(hour=9, minute=45, second=0)
    decision, _ = engine.evaluate_entry_timing(dt, {})
    assert decision == "WAIT"

def test_timing_engine_returns_skip_near_close():
    from src.tqqq.ml.timing_engine import IntradayTimingEngine
    engine = IntradayTimingEngine()
    
    # 15:50 — inside close blackout
    dt = datetime.now().replace(hour=15, minute=50, second=0)
    decision, _ = engine.evaluate_entry_timing(dt, {})
    assert decision == "SKIP_TODAY"

def test_timing_engine_executes_in_prime_window():
    from src.tqqq.ml.timing_engine import IntradayTimingEngine
    engine = IntradayTimingEngine()
    
    # 10:45 AM — ideal window
    dt = datetime.now().replace(hour=10, minute=45, second=0)
    decision, _ = engine.evaluate_entry_timing(dt, {})
    assert decision == "EXECUTE_NOW"

def test_timing_engine_executes_in_afternoon_window():
    from src.tqqq.ml.timing_engine import IntradayTimingEngine
    engine = IntradayTimingEngine()
    
    # 2:15 PM — secondary window
    dt = datetime.now().replace(hour=14, minute=15, second=0)
    decision, _ = engine.evaluate_entry_timing(dt, {})
    assert decision == "EXECUTE_NOW"


# ─────────────────────────────────────────────────────────────────────────────
# 3. IV Surface Monitor
# ─────────────────────────────────────────────────────────────────────────────

def test_iv_surface_returns_empty_dict_on_no_data():
    from src.tqqq.iv_surface_monitor import IVSurfaceMonitor
    monitor = IVSurfaceMonitor()
    result = monitor.analyze_surface([], 100.0)
    assert result == {}

def test_iv_surface_recommend_adjustments_respects_bounds():
    from src.tqqq.iv_surface_monitor import IVSurfaceMonitor
    monitor = IVSurfaceMonitor()
    
    # Steep positive slope should shorten DTE
    adj_dte, adj_delta = monitor.recommend_adjustments(
        {"term_slope": 0.05, "skew_steepness": 0.01},
        base_dte=30,
        base_delta=-0.30
    )
    assert adj_dte <= 30, "Steep positive slope should reduce DTE"
    assert adj_dte >= 14, "DTE should not drop below minimum"

def test_iv_surface_steep_skew_adjusts_delta():
    from src.tqqq.iv_surface_monitor import IVSurfaceMonitor
    monitor = IVSurfaceMonitor()
    
    # Steep put skew should move delta closer to ATM
    adj_dte, adj_delta = monitor.recommend_adjustments(
        {"term_slope": 0.0, "skew_steepness": 0.20},
        base_dte=30,
        base_delta=-0.30
    )
    assert adj_delta <= -0.30, "Steep skew should shift delta (more negative = closer to ATM)"
    assert adj_delta >= -0.40, "Delta should stay within legal range"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bayesian Param Optimizer
# ─────────────────────────────────────────────────────────────────────────────

def test_param_optimizer_fallback_returns_all_regimes():
    """When skopt is not available, should return default params for all regimes."""
    from src.tqqq.ml.param_optimizer import StrategyParamOptimizer
    optimizer = StrategyParamOptimizer(objective_backtest_fn=None)
    result = optimizer.optimize_all_regimes(n_calls=1)
    for regime in ("LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"):
        assert regime in result
        assert "dte" in result[regime]
        assert "delta" in result[regime]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Thompson Sampling Contextual Bandit (ContractRanker)
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_contract(**overrides):
    base = {
        "strike": 45.0, "bid": 0.50, "ask": 0.55, "volume": 2000,
        "open_interest": 5000, "bid_size": 80, "delta": -0.28,
        "gamma": 0.02, "theta": -0.05, "vega": 0.10, "iv": 0.65,
        "dte": 30, "credit": 0.50, "max_loss": 4.50, "liquidity_score": 0.8
    }
    base.update(overrides)
    return base

def _make_mock_context():
    return {
        "tqqq_price": 55.0, "regime": "NORMAL", "vix_direction": "NEUTRAL",
        "tqqq_hv20": 0.75
    }

def test_bandit_ranks_candidates_by_heuristic_early():
    """With < 20 observations, the bandit uses reward_to_risk * liquidity heuristic."""
    from src.tqqq.ml.contract_ranker import ContextualBanditContractSelector
    ranker = ContextualBanditContractSelector()
    
    candidates = [
        _make_mock_contract(credit=0.80, max_loss=4.00),  # Higher R/R
        _make_mock_contract(credit=0.20, max_loss=4.50),  # Lower R/R
    ]
    ctx = _make_mock_context()
    ranked = ranker.rank(candidates, ctx)
    
    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score

def test_bandit_rank_returns_ranked_contract_objects():
    from src.tqqq.ml.contract_ranker import ContextualBanditContractSelector, RankedContract
    ranker = ContextualBanditContractSelector()
    
    candidates = [_make_mock_contract()]
    ctx = _make_mock_context()
    ranked = ranker.rank(candidates, ctx)
    
    assert isinstance(ranked[0], RankedContract)
    assert ranked[0].rank == 1

def test_bandit_returns_empty_list_for_no_candidates():
    from src.tqqq.ml.contract_ranker import ContextualBanditContractSelector
    ranker = ContextualBanditContractSelector()
    result = ranker.rank([], _make_mock_context())
    assert result == []

def test_bandit_update_increments_observation_count():
    from src.tqqq.ml.contract_ranker import ContextualBanditContractSelector
    ranker = ContextualBanditContractSelector()
    initial_n = ranker.n_observations

    features = ranker._build_features(_make_mock_contract(), _make_mock_context())
    ranker.update(features, reward=0.35)

    assert ranker.n_observations == initial_n + 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. PPO Agent
# ─────────────────────────────────────────────────────────────────────────────

def test_ppo_agent_returns_do_nothing_without_model():
    """Without a trained model file, the agent should return action 0 (DO_NOTHING)."""
    from src.tqqq.ml.ppo_agent import TQQQPPOAgent
    agent = TQQQPPOAgent(model_path="nonexistent_model.zip")
    action, confidence = agent.get_action({"position_state": 0, "dte": 30, "vix_level": 15})
    assert action == TQQQPPOAgent.ACTION_DO_NOTHING
    assert confidence == 0.0

def test_ppo_agent_builds_observation_correctly():
    from src.tqqq.ml.ppo_agent import TQQQPPOAgent
    import numpy as np
    agent = TQQQPPOAgent(model_path="nonexistent_model.zip")
    
    obs = agent._build_observation({
        "position_state": 1,
        "spread_pnl_pct": 0.50,
        "short_put_pnl_pct": 0.25,
        "dte": 30,
        "vix_level": 20,
        "vix_trend": 1.0,
        "tqqq_trend": 0.0
    })
    assert obs.dtype == np.float32
    assert len(obs) == 7


# ─────────────────────────────────────────────────────────────────────────────
# 7. Walk-Forward Validation Pipeline (stub)
# ─────────────────────────────────────────────────────────────────────────────

def test_walk_forward_validator_returns_all_models():
    import pandas as pd
    from src.tqqq.ml.validation_pipeline import WalkForwardValidator
    
    dummy_df = pd.DataFrame({"a": range(600)})
    validator = WalkForwardValidator(dummy_df)
    results = validator.validate_all_models()
    
    expected_models = {"HMM_Regime", "XGBoost_VIX", "LSTM_VIX", "Bandit_Ranker", "PPO_Agent"}
    assert set(results.keys()) == expected_models

def test_walk_forward_validator_has_passed_key():
    import pandas as pd
    from src.tqqq.ml.validation_pipeline import WalkForwardValidator
    
    dummy_df = pd.DataFrame({"a": range(600)})
    validator = WalkForwardValidator(dummy_df)
    results = validator.validate_all_models()
    
    for model, result in results.items():
        assert "passed" in result, f"Model {model} result missing 'passed' key"
        assert "test_sharpe_avg" in result
