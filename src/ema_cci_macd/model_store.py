"""
Model Registry
==============
Saves and loads ML models + metadata.
"""
import os
import json
import joblib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Any

@dataclass
class ModelMetadata:
    model_version: str
    trained_at: str
    symbols: List[str]
    timeframe: str
    feature_columns: List[str]
    validation_metrics: dict
    publish_threshold: float

MODEL_DIR = Path(__file__).parent.parent.parent / "models" / "ema_cci_macd"

def save_model(model: Any, metadata: ModelMetadata, model_name: str = "v1") -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save model
    model_path = MODEL_DIR / f"{model_name}.joblib"
    joblib.dump(model, model_path)
    
    # Save metadata
    meta_path = MODEL_DIR / f"{model_name}_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(asdict(metadata), f, indent=4)
        
def load_model(model_name: str = "v1") -> Tuple[Any, ModelMetadata]:
    model_path = MODEL_DIR / f"{model_name}.joblib"
    meta_path = MODEL_DIR / f"{model_name}_metadata.json"
    
    if not model_path.exists() or not meta_path.exists():
        return None, None
        
    model = joblib.load(model_path)
    
    with open(meta_path, "r") as f:
        meta_dict = json.load(f)
        metadata = ModelMetadata(**meta_dict)
        
    return model, metadata
