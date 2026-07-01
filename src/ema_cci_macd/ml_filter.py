"""
ML Inference Filter
===================
Live scoring of candidates against the trained ML model.
"""
import pandas as pd
from typing import Optional
from .types import SignalCandidate
from .model_store import ModelMetadata

class MLSignalFilter:
    def __init__(self, model, metadata: ModelMetadata):
        self.model = model
        self.metadata = metadata
        
    def score_candidate(self, candidate: SignalCandidate) -> Optional[float]:
        """
        Score a candidate setup. Returns probability of hitting target before stop.
        """
        if not self.model or not candidate.features:
            return None
            
        # Build inference dataframe matching feature columns
        row = candidate.to_dict()
        row.update(candidate.features)
        
        # One-hot encode regime if present
        if candidate.regime:
            row[f"regime_{candidate.regime}"] = 1
            
        df = pd.DataFrame([row])
        
        # Ensure all feature columns are present and in correct order
        for col in self.metadata.feature_columns:
            if col not in df.columns:
                df[col] = 0.0 # fill missing one-hot columns with 0
                
        X = df[self.metadata.feature_columns].astype(float)
        
        # Predict probability of class 1 (success)
        prob = self.model.predict_proba(X)[0, 1]
        return float(prob)
        
    def should_publish(self, candidate: SignalCandidate) -> bool:
        """
        Compare ML score to metadata threshold.
        """
        if candidate.ml_score is None:
            return False
            
        return candidate.ml_score >= self.metadata.publish_threshold
