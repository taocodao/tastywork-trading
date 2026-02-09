
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
vxv = fred_csv('VXVCLS')

start = max(vix['date'].min(), vxv['date'].min())
end = pd.Timestamp(datetime.now().strftime('%Y-%m-%d'))

vix = vix[(vix['date']>=start) & (vix['date']<=end)]
vxv = vxv[(vxv['date']>=start) & (vxv['date']<=end)]

df = pd.merge(vix, vxv, on='date', how='inner').dropna()

df['diff'] = df['VIXCLS'] - df['VXVCLS']
flat_band = 0.5

df['Regime'] = np.where(df['diff'] > flat_band, 'Backwardation', np.where(df['diff'] < -flat_band, 'Contango', 'Flat'))

freq = df['Regime'].value_counts(normalize=True).to_frame('PctDays')
freq['PctDays'] = (freq['PctDays']*100).round(2)

# Run lengths
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

# Also compute distribution of diff
stats = df['diff'].describe(percentiles=[0.05,0.25,0.5,0.75,0.95]).to_frame('VIX_minus_VXV')

freq.to_csv('vix_vxv_term_structure_frequency.csv')
duration.to_csv('vix_vxv_term_structure_duration.csv')
df.to_csv('vix_vxv_daily.csv', index=False)
stats.to_csv('vix_vxv_diff_stats.csv')

freq, duration, stats, (df['date'].min(), df['date'].max(), len(df))
