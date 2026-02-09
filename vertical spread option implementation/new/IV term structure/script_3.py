
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from io import StringIO

def fred_csv(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    df.columns = ['date', series_id]
    df['date'] = pd.to_datetime(df['date'])
    df[series_id] = pd.to_numeric(df[series_id], errors='coerce')
    return df.dropna()

vix = fred_csv('VIXCLS')
# FRED series for VIX 3M is VIX3MCLS (close). Validate by attempting download.
vix3m = fred_csv('VIX3MCLS')

start = max(vix['date'].min(), vix3m['date'].min())
end = pd.Timestamp(datetime.now().strftime('%Y-%m-%d'))

vix = vix[(vix['date']>=start) & (vix['date']<=end)]
vix3m = vix3m[(vix3m['date']>=start) & (vix3m['date']<=end)]

df = pd.merge(vix, vix3m, on='date', how='inner').dropna()

df['diff'] = df['VIXCLS'] - df['VIX3MCLS']
flat_band = 0.5

df['Regime'] = np.where(df['diff'] > flat_band, 'Backwardation', np.where(df['diff'] < -flat_band, 'Contango', 'Flat'))

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

freq.to_csv('vix_vix3m_term_structure_frequency.csv')
duration.to_csv('vix_vix3m_term_structure_duration.csv')
df.to_csv('vix_vix3m_daily.csv', index=False)

freq, duration, (df['date'].min(), df['date'].max(), len(df))
