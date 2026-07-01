from src.otm_naked.optimization.fast_simulator import OTMParams, FastOTMSimulator
import pandas as pd, numpy as np

# Verify new OTMParams fields compile correctly
p = OTMParams()
print('OTMParams v2 fields:', list(p.__dataclass_fields__.keys()))
assert hasattr(p, 'vix_slope_threshold'), 'missing vix_slope_threshold'
assert hasattr(p, 'iv_hv_min'), 'missing iv_hv_min'
assert hasattr(p, 'iv_pct_threshold'), 'missing iv_pct_threshold'
assert not hasattr(p, 'rsi_oversold'), 'rsi_oversold should be removed'
assert not hasattr(p, 'vix_crisis_threshold'), 'vix_crisis_threshold should be removed'
print('OTMParams assertions passed.')

# Smoke test: build a tiny synthetic feature set and run simulate()
dates = pd.date_range('2020-01-01', periods=600, freq='B')
def _make_feat(n):
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.5), index=dates[:n])
    df = pd.DataFrame(index=dates[:n])
    df['close'] = close
    df['hv_20'] = 0.20
    df['vix'] = 18.0
    df['pct_from_52w_high'] = -0.10
    df['rf'] = 0.045
    df['vix_term_slope'] = 0.05   # Positive contango — entries should trigger
    df['iv_hv_ratio'] = 1.15       # IV > HV — premium edge present
    df['iv_rank'] = 0.45           # IV Percentile 45% — above threshold
    return df

features = {'AAPL': _make_feat(600), 'MSFT': _make_feat(600)}
sim = FastOTMSimulator(features, warmup_days=252)
metrics = sim.simulate(p)
print(f'Simulation result: trades={metrics["n_trades"]}, sortino={metrics["sortino"]:.3f}, max_dd={metrics["max_drawdown"]:.1%}')
assert metrics['n_trades'] >= 0, 'n_trades should be non-negative'
print('FastOTMSimulator smoke test PASSED.')

# Smoke test: optuna_study imports and _log_barrier_drawdown
from src.otm_naked.optimization.optuna_study import _log_barrier_drawdown, _default_params_dict
barrier_safe = _log_barrier_drawdown(-0.10)
barrier_edge = _log_barrier_drawdown(-0.24)
barrier_viol = _log_barrier_drawdown(-0.30)
print(f'Log-barrier: safe(-10%)={barrier_safe:.3f}, edge(-24%)={barrier_edge:.3f}, violation(-30%)={barrier_viol:.1f}')
assert barrier_safe < barrier_edge < barrier_viol, 'barrier should increase as drawdown worsens'
print('Log-barrier assertions passed.')

defaults = _default_params_dict()
assert 'vix_slope_threshold' in defaults, 'defaults missing vix_slope_threshold'
assert 'iv_hv_min' in defaults, 'defaults missing iv_hv_min'
print('All smoke tests PASSED.')
