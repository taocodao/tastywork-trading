import sys, warnings, logging
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, '.')

from src.turbocore_pro.data_pipeline import TurboCoreDataPipeline
from src.turbocore_pro.ml.regime_detector import TurboCoreRegimeDetector

pipeline = TurboCoreDataPipeline()
pipeline.fetch_data('10y')
df = pipeline.prepare_core_features(fetch_fred=False)

features = [c for c in df.columns if c in ["qqq_vol_20d","vix_close","qqq_10d_return","vix_term_slope"]]
print(f'Rows: {len(df)}, Features present: {features}')

det = TurboCoreRegimeDetector()
det.fit(df)
print('HMM Training complete.')
