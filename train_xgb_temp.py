import sys, warnings, logging
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, '.')

from src.turbocore_pro.data_pipeline import TurboCoreDataPipeline
from src.turbocore_pro.ml.signal_scorer import TurboCoreSignalScorer

pipeline = TurboCoreDataPipeline()
pipeline.fetch_data('7y')
df = pipeline.prepare_core_features(fetch_fred=False)

scorer = TurboCoreSignalScorer()
scorer.fit(df)
print('XGBoost Training complete.')
