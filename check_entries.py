import yfinance as yf
import pandas as pd
from src.qqq_leaps.leaps_feature_engineering import build_leaps_features
from src.qqq_leaps.regime_classifier import LeapsRegimeClassifier
from src.qqq_leaps.entry_classifier_v2 import LeapsEntryClassifierV2
from src.qqq_leaps.config import QQQLeapsConfig

qqq = yf.download('QQQ', start='2018-01-01', end='2026-04-01', auto_adjust=True, progress=False)
vix = yf.download('^VIX', start='2018-01-01', end='2026-04-01', progress=False)
vix3m = yf.download('^VIX3M', start='2018-01-01', end='2026-04-01', progress=False)
irx = yf.download('^IRX', start='2018-01-01', end='2026-04-01', progress=False)
if isinstance(qqq.columns, pd.MultiIndex): qqq.columns = qqq.columns.droplevel(1)
if isinstance(vix.columns, pd.MultiIndex): vix.columns = vix.columns.droplevel(1)
if isinstance(vix3m.columns, pd.MultiIndex): vix3m.columns = vix3m.columns.droplevel(1)
if isinstance(irx.columns, pd.MultiIndex): irx.columns = irx.columns.droplevel(1)

master = build_leaps_features(qqq['Close'].squeeze(), qqq['Open'].squeeze(), vix['Close'].squeeze().ffill(), vix3m['Close'].squeeze().ffill(), (irx['Close'] / 100).squeeze().ffill())
cfg = QQQLeapsConfig()
regime_clf = LeapsRegimeClassifier(cfg)
master = regime_clf.apply_to_master(master)
ml_clf = LeapsEntryClassifierV2(); ml_clf.load()

master["prev_close"] = master["qqq_close"].shift(1)

df = master.loc['2019-01-01':].copy().reset_index()
if 'Date' in df.columns: df = df.rename(columns={'Date': 'date'})

valid_entries = 0
for idx, row in df.iterrows():
    gap = row.get('gap_pct', 0)
    regime = row.get('leaps_regime', 'CHOPPY')
    if regime in ['BULL_STRONG', 'BULL_MODERATE', 'CHOPPY'] and gap <= -0.003:
        conf, _ = ml_clf.predict_with_threshold(row, regime)
        if conf >= 0.45:
            print(f"{row['date'].date()}: Gap {gap*100:.2f}%, Conf {conf:.3f}, Regime {regime}")
            valid_entries += 1
print(f'Total Valid Entries: {valid_entries}')
