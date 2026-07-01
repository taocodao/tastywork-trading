import logging, pandas as pd, numpy as np, yfinance as yf
logging.basicConfig(level=logging.WARNING)

from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.backtest_engine import SNDKBacktestEngine
from src.otm_naked.sndk.feature_engineering import build_sndk_features

ticker = 'SNDK'
raw = yf.download([ticker, '^VIX', 'SPY'], start='2025-01-01', end='2026-06-30', auto_adjust=True, progress=False)
df_full = build_sndk_features(
    close=raw['Close'][ticker].dropna(), open_price=raw['Open'][ticker].dropna(),
    high=raw['High'][ticker].dropna(), low=raw['Low'][ticker].dropna(),
    volume=raw['Volume'][ticker].dropna(), vix=raw['Close']['^VIX'].dropna(),
    spy_close=raw['Close']['SPY'].dropna()
)
df = df_full.loc['2025-03-01':'2026-06-29']
print(f"Feature rows: {len(df)}")

config = SNDKLadderConfig(universe=[ticker])
config.entry_trigger_pct = 2.0
config.ivr_min = 20.0
config.position_size_pct = 0.10
config.macro_filter_spy_pct = 15.0
config.max_rungs_per_side = 4
config.profit_take_pct = 0.50
config.delta_breach_threshold = 0.40
config.initial_capital = 500_000.0
config.dte_target = 30
config.stop_loss_credit_mult = 3.0

engine = SNDKBacktestEngine(config)
pnls = engine.simulate_strategy(df, use_ml=False)
wins = [p for p in pnls if p > 0]
losses = [p for p in pnls if p <= 0]
print(f"Total trades: {len(pnls)}")
print(f"Wins:  {len(wins)} ({len(wins)/max(len(pnls),1)*100:.1f}%)  avg=${np.mean(wins) if wins else 0:.0f}")
print(f"Losses:{len(losses)} ({len(losses)/max(len(pnls),1)*100:.1f}%)  avg=${np.mean(losses) if losses else 0:.0f}")
print(f"Total PnL: ${sum(pnls):,.0f}")
print(f"CAGR approx: {((500000+sum(pnls))/500000)**(252/len(df))-1:.1%}")
