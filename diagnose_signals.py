"""Check what's actually blocking signals in 2023-2025."""
import sys, warnings, math
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import yfinance as yf, numpy as np, pandas as pd
from src.otm_naked.config import OTMNakedConfig
from src.otm_naked.feature_engineering import build_all_features
from src.otm_naked.signal_engine import OTMSignalEngine, SignalType, classify_vix_regime

cfg = OTMNakedConfig()
print(f"Thresholds: min_iv_rank={cfg.min_iv_rank}, min_iv_hv_ratio={cfg.min_iv_hv_ratio}")
print(f"  put_decline_from_high={cfg.put_decline_from_high}, put_near_52w_low={cfg.put_near_52w_low_pct}")

symbols = ["NVDA", "AAPL", "MSFT", "META", "AMZN", "NFLX"]
all_tickers = symbols + ["^VIX", "^VIX3M"]
raw = yf.download(all_tickers, start="2021-01-01", end="2026-01-01", progress=False, auto_adjust=True, group_by="ticker")

def get_df(ticker):
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            df = raw.xs(ticker, axis=1, level=1).copy()
        else:
            df = raw.copy()
        df.columns = [c.capitalize() if isinstance(c, str) else c for c in df.columns]
        needed = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
        return df[needed].dropna(subset=["Close"])
    except:
        return pd.DataFrame()

price_data = {s: get_df(s) for s in symbols if len(get_df(s)) > 50}
vix = raw.xs("^VIX", axis=1, level=1)["Close"].squeeze() if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
vix3m = raw.xs("^VIX3M", axis=1, level=1)["Close"].squeeze() if isinstance(raw.columns, pd.MultiIndex) else vix * 1.05

features = build_all_features(price_data, vix, vix3m)

# Sample daily stats for each year
for yr_str in ["2022", "2023", "2024", "2025"]:
    rows = []
    for sym, feat_df in features.items():
        yr_df = feat_df[feat_df.index.year == int(yr_str)]
        for dt, row in yr_df.iterrows():
            regime = classify_vix_regime(float(row.get("vix", 20)))
            l1_put = abs(float(row.get("pct_from_52w_high", 0))) >= cfg.put_decline_from_high or \
                     float(row.get("pct_from_52w_low", 1)) <= cfg.put_near_52w_low_pct
            l3_iv  = float(row.get("iv_rank", 0)) >= cfg.min_iv_rank
            l3_ihv = float(row.get("iv_hv_ratio", 0)) >= cfg.min_iv_hv_ratio
            l3_reg = regime != "CRISIS"
            rows.append({"sym": sym, "l1_put": l1_put, "l3_iv": l3_iv, "l3_ihv": l3_ihv,
                         "l3_reg": l3_reg, "all3": l1_put and l3_iv and l3_ihv and l3_reg,
                         "iv_rank": float(row.get("iv_rank", 0)),
                         "iv_hv": float(row.get("iv_hv_ratio", 0)),
                         "pct_hi": float(row.get("pct_from_52w_high", 0))})
    if not rows:
        continue
    d = pd.DataFrame(rows)
    print(f"\n{yr_str}:")
    print(f"  L1_put={d['l1_put'].mean():.1%}  L3_iv={d['l3_iv'].mean():.1%}  "
          f"L3_ihv={d['l3_ihv'].mean():.1%}  ALL_PASS={d['all3'].mean():.1%}")
    print(f"  iv_rank: mean={d['iv_rank'].mean():.3f}  iv_hv: mean={d['iv_hv'].mean():.3f}")
    print(f"  pct_from_52w_high: mean={d['pct_hi'].mean():.3f}")
