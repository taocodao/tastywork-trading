import yfinance as yf, numpy as np, math, warnings
warnings.filterwarnings('ignore')

data = yf.download('SPY', start='2016-01-01', end='2025-12-31', progress=False, auto_adjust=True)
close = data['Close'].squeeze()
log_ret = np.log(close / close.shift(1))
hv30 = log_ret.rolling(30).std() * math.sqrt(252) * 100
hv_min = hv30.rolling(252).min()
hv_max = hv30.rolling(252).max()
iv_rank = ((hv30 - hv_min) / (hv_max - hv_min)).clip(0,1).fillna(0.5)

print("SPY IV Rank proxy by year:")
for yr in ['2019','2020','2021','2022','2023','2024','2025']:
    yr_data = iv_rank[yr]
    if len(yr_data):
        print(f"  {yr}: mean={yr_data.mean():.3f}  pct<0.15={( yr_data < 0.15).mean():.1%}  pct<0.25={( yr_data < 0.25).mean():.1%}")
