import sys, warnings, logging
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '.')

from src.otm_naked import backtest_engine as be

counters = {'iv': 0, 'vix': 0, 'regime': 0, 'premium': 0, 'capacity': 0, 'contracts': 0, 'pass': 0, 'calls': 0}

def debug_should(self, symbol, iv_rank, vix, regime, spot, T_years, sigma, rf, nav, risk_mgr, open_positions):
    counters['calls'] += 1
    cfg = self.config
    if not cfg.strangle_enabled:
        return False, 0.0, 0.0, 0
    if iv_rank < cfg.strangle_iv_rank_min:
        counters['iv'] += 1
        return False, 0.0, 0.0, 0
    if vix > cfg.strangle_vix_max:
        counters['vix'] += 1
        return False, 0.0, 0.0, 0
    if regime in ('HIGH', 'CRISIS'):
        counters['regime'] += 1
        return False, 0.0, 0.0, 0
    try:
        call_strike, call_premium, _ = self.strike_sel.select_call_strike(spot, T_years, sigma, regime, rf)
    except Exception:
        return False, 0.0, 0.0, 0
    if call_premium < cfg.strangle_min_call_premium:
        counters['premium'] += 1
        return False, 0.0, 0.0, 0
    open_count = len(open_positions)
    if open_count + 1 > cfg.max_concurrent_positions:
        counters['capacity'] += 1
        return False, 0.0, 0.0, 0
    call_contracts = risk_mgr.calculate_contracts(call_premium, call_strike, nav, symbol=symbol)
    if call_contracts < 1:
        counters['contracts'] += 1
        return False, 0.0, 0.0, 0
    counters['pass'] += 1
    return True, call_strike, call_premium, call_contracts

be.OTMNakedBacktestEngine._should_upgrade_to_strangle = debug_should

from backtest_otm_naked import download_data
from src.otm_naked.config import OTMNakedConfig, OTM_NAKED_UNIVERSE

symbols = OTM_NAKED_UNIVERSE
price_data, vix, vix3m, rf = download_data(symbols, '2021-01-01', '2021-12-31')
config = OTMNakedConfig(backtest_start='2021-01-01', backtest_end='2021-12-31')
engine = be.OTMNakedBacktestEngine(config)
results = engine.run(
    price_data=price_data,
    vix=vix,
    vix3m=vix3m if len(vix3m) > 0 else None,
    rf=rf if len(rf) > 0 else None,
    initial_capital=50000,
    use_ml=False,
)

print()
print('Strangle decision counters for 2021:')
for k, v in counters.items():
    print(f'  {k:12s}: {v}')
print(f"Total trades: {results['metrics'].get('n_trades', 0)}")
