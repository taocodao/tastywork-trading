
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# Attempt to quantify term structure regime frequency using available implied volatility proxies.
# Note: Free sources rarely provide full daily ATM IV term structure. We'll approximate using VIX (30d) vs VIX3M (3m) as an equity-index vol term structure proxy.

start = "2006-01-01"
end = datetime.now().strftime("%Y-%m-%d")

symbols = ["^VIX", "^VIX3M"]
data = yf.download(symbols, start=start, end=end, progress=False)["Adj Close"].dropna()

# Define regimes
# Backwardation: VIX > VIX3M (front > back)
# Contango: VIX < VIX3M
# Flat: within 0.5 vol points

diff = data["^VIX"] - data["^VIX3M"]
flat_band = 0.5

regime = np.where(diff > flat_band, "Backwardation", np.where(diff < -flat_band, "Contango", "Flat"))

regime_series = pd.Series(regime, index=data.index, name="Regime")

summary = regime_series.value_counts(normalize=True).rename("PctDays").to_frame()
summary["PctDays"] = (summary["PctDays"]*100).round(2)

# Duration statistics: consecutive runs
runs = []
current = regime_series.iloc[0]
length = 1
for r in regime_series.iloc[1:]:
    if r == current:
        length += 1
    else:
        runs.append((current, length))
        current = r
        length = 1
runs.append((current, length))

runs_df = pd.DataFrame(runs, columns=["Regime", "RunDays"])
duration_stats = runs_df.groupby("Regime")["RunDays"].agg(["count","mean","median","max"]).round(2)

# Save artifacts
summary.to_csv("vix_term_structure_regime_frequency.csv")
duration_stats.to_csv("vix_term_structure_regime_durations.csv")

print(summary)
print(duration_stats)
