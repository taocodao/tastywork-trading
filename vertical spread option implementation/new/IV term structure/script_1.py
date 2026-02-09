
import pandas as pd
import numpy as np
import pandas_datareader.data as web
from datetime import datetime

start = datetime(2006,1,1)
end = datetime.now()

# FRED series: VIXCLS (CBOE VIX), VIX3M (CBOE 3-Month Volatility Index)
# These are daily series.

vix = web.DataReader('VIXCLS', 'fred', start, end)
vix3m = web.DataReader('VIX3M', 'fred', start, end)

df = pd.concat([vix, vix3m], axis=1).dropna()
df.columns = ['VIX', 'VIX3M']

diff = df['VIX'] - df['VIX3M']
flat_band = 0.5

df['Regime'] = np.where(diff > flat_band, 'Backwardation', np.where(diff < -flat_band, 'Contango', 'Flat'))

freq = df['Regime'].value_counts(normalize=True).to_frame('PctDays')
freq['PctDays'] = (freq['PctDays']*100).round(2)

# run lengths
runs = []
current = df['Regime'].iloc[0]
length = 1
for r in df['Regime'].iloc[1:]:
    if r == current:
        length += 1
    else:
        runs.append((current, length))
        current = r
        length = 1
runs.append((current, length))

runs_df = pd.DataFrame(runs, columns=['Regime', 'RunDays'])
duration = runs_df.groupby('Regime')['RunDays'].agg(['count','mean','median','max']).round(2)

# save
freq.to_csv('vix_vix3m_regime_frequency_2006_present.csv')
duration.to_csv('vix_vix3m_regime_durations_2006_present.csv')
df[['VIX','VIX3M','Regime']].to_csv('vix_vix3m_regimes_daily.csv')

print(freq)
print(duration)
