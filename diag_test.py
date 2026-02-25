"""Quick diagnostic to trace why backtest generates 0 trades."""
import logging, sys
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from diagonal_strategy.backtest.data_loader import DiagonalDataLoader
from diagonal_strategy.core.ta_signal_engine import TASignalEngine
from diagonal_strategy.ml.oscillation_predictor import OscillationPredictor
import diagonal_strategy.config as config

loader = DiagonalDataLoader()
df = loader.load_historical_data('2019-01-01')
print(f"Columns: {list(df.columns)}")
print(f"Shape: {df.shape}")
print(f"iv_rank sample [250:255]: {df['iv_rank'].iloc[250:255].values}")
print(f"vix_roc_5 sample [250:255]: {df['vix_roc_5'].iloc[250:255].values}")

# Test TA on a known dip slice
ta = TASignalEngine(ml_model=None)
osc = OscillationPredictor()  # no model, will use fallback

# Find dates where VIX > 20 (likely dip conditions)
dip_dates = df[df['vix_level'] > 20].index
print(f"\nDates with VIX > 20: {len(dip_dates)}")

# Test 5 sample dates
for i, dt in enumerate(dip_dates[::50][:5]):
    idx = df.index.get_loc(dt)
    if idx < 50:
        continue
    bars = df.iloc[idx-49:idx+1]
    row = df.iloc[idx]
    vix = row['vix_level']
    
    regime = 'LOW_VOL' if vix < 16 else ('NORMAL' if vix < 24 else ('HIGH_VOL' if vix < 32 else 'CRISIS'))
    
    mkt = {
        'tqqq_bars': bars,
        'current_date': dt.date(),
        'regime': regime,
        'vix_level': float(vix),
        'vix_roc_5': float(row.get('vix_roc_5', 0)),
        'iv_rank': float(row.get('iv_rank', 50)),
        'iv_percentile': float(row.get('iv_percentile', 50)),
        'term_slope': 0.0,
    }
    
    features = ta.compute_features(mkt)
    if not features:
        print(f"  {dt.date()}: No features!")
        continue
    
    dip = ta.dip_score(features)
    ml = osc.predict(features)
    
    print(f"  {dt.date()}: VIX={vix:.1f} regime={regime} RSI14={features.get('rsi_14',0):.1f} "
          f"BB={features.get('bb_position',0):.2f} IV_rank={features.get('iv_rank',0):.1f} "
          f"DipScore={dip:.3f} ML_dir={ml['direction']} ML_conf={ml['confidence']:.2f} "
          f"PASS_DIP={dip > config.TA_DIP_SCORE_THRESHOLD} PASS_IV={features.get('iv_rank',0) > config.TA_IV_RANK_MIN}")
