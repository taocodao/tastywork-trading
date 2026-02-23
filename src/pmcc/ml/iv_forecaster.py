import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
import os

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

if TORCH_AVAILABLE:
    class IVForecasterModel(nn.Module):
        """
        Bidirectional LSTM model to predict 30-day forward IV direction.
        Input is a sequence (e.g., 30 days of historical data).
        Output is a probability distribution over 3 classes: [DOWN, FLAT, UP].
        """
        def __init__(self, input_dim: int, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2):
            super().__init__()
            self.hidden_dim = hidden_dim
            self.num_layers = num_layers
            
            # Bidirectional LSTM to capture patterns in both forward and backward time contexts
            self.lstm = nn.LSTM(
                input_dim, 
                hidden_dim, 
                num_layers, 
                batch_first=True, 
                dropout=dropout if num_layers > 1 else 0,
                bidirectional=True
            )
            
            # Fully connected layer maps hidden states to 3 output classes
            # * 2 because of bidirectional LSTM
            self.fc = nn.Sequential(
                nn.Linear(hidden_dim * 2, hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, 3) # 3 classes: 0=DOWN, 1=FLAT, 2=UP
            )
            
        def forward(self, x):
            # x shape: (batch_size, sequence_length, features)
            
            # Initialize hidden and cell states
            h0 = torch.zeros(self.num_layers * 2, x.size(0), self.hidden_dim).to(x.device)
            c0 = torch.zeros(self.num_layers * 2, x.size(0), self.hidden_dim).to(x.device)
            
            # Forward propagate LSTM
            out, _ = self.lstm(x, (h0, c0))
            
            # Decode the hidden state of the last time step
            out = self.fc(out[:, -1, :])
            return out


class LSTMIVForecaster:
    """
    Wrapper class to manage data normalization, sequence generation,
    training, and inference for the PyTorch LSTM model.
    """
    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'iv_forecaster.pt')
    
    def __init__(self, sequence_length: int = 30):
        self.sequence_length = sequence_length
        self.model: Optional['IVForecasterModel'] = None
        self.is_trained = False
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if TORCH_AVAILABLE else None
        
        # Mapping from numeric class to label string
        self.class_mapping = {0: "DOWN", 1: "FLAT", 2: "UP"}
        
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not installed. LSTM IV Forecaster disabled.")
            return
            
        self._load_model()
        
    def _load_model(self):
        """Loads trained model weights from disk."""
        if os.path.exists(self.MODEL_FILE):
            try:
                # Lazy initialization of the model; input_dim is hardcoded here based on expected features
                # Real implementation might save hyperparameters alongside weights
                self.model = IVForecasterModel(input_dim=6).to(self.device)
                self.model.load_state_dict(torch.load(self.MODEL_FILE, map_location=self.device))
                self.model.eval()
                self.is_trained = True
                logger.info(f"Loaded LSTM IV Forecaster Model from {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed to load LSTM model: {e}")
                
    def _save_model(self):
        """Saves trained model weights to disk."""
        if self.model:
            try:
                torch.save(self.model.state_dict(), self.MODEL_FILE)
                logger.info(f"Saved LSTM IV Forecaster Model to {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed to save LSTM model: {e}")

    def _extract_sequences(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert historical dataframe into supervised learning sequences.
        Requires IV data in the dataframe.
        """
        # Ex: ['IV_30', 'IV_Rank', 'VIX_Close', 'HV_20', 'ATR_Pct', 'Days_To_Earnings']
        required_cols = ['IV_30', 'IV_Rank', 'VIX_Close', 'HV_20', 'ATR_Pct', 'Days_To_Earnings']
        
        # For this skeleton, we assume the df already has these. If not, generate dummy/approx.
        for num_col in required_cols:
            if num_col not in df.columns:
                df[num_col] = 0.5 # Dummy normalized filling
                
        # Forward target generation (e.g. 30 days ahead)
        if 'Target_IV' not in df.columns:
            df['Target_IV'] = df['IV_30'].shift(-30)
            
        df = df.dropna()
        
        # Calculate % change in IV
        df['IV_Change'] = (df['Target_IV'] - df['IV_30']) / df['IV_30']
        
        # Classify: < -5% = DOWN (0), -5% to 5% = FLAT (1), > 5% = UP (2)
        conditions = [
            (df['IV_Change'] < -0.05),
            (df['IV_Change'] >= -0.05) & (df['IV_Change'] <= 0.05),
            (df['IV_Change'] > 0.05)
        ]
        choices = [0, 1, 2]
        df['Target_Class'] = np.select(conditions, choices, default=1)
        
        # Normalize features (in production, use StandardScaler and save fit)
        features = df[required_cols].values
        features = (features - np.mean(features, axis=0)) / (np.std(features, axis=0) + 1e-8)
        
        targets = df['Target_Class'].values
        
        # Build rolling sequences (sequence_length days of data -> 1 target)
        X, y = [], []
        for i in range(len(features) - self.sequence_length):
            X.append(features[i:i+self.sequence_length])
            y.append(targets[i+self.sequence_length])
            
        return np.array(X), np.array(y)

    def train(self, historical_data: pd.DataFrame, epochs: int = 50, batch_size: int = 64) -> None:
        """
        Train the Bidirectional LSTM on historical data.
        """
        if not TORCH_AVAILABLE:
            logger.error("Cannot train LSTM: PyTorch not installed.")
            return
            
        logger.info("Extracting sequences for LSTM training...")
        X, y = self._extract_sequences(historical_data)
        
        if len(X) < 100:
            logger.error("Insufficient data to train LSTM. Need more history.")
            return
            
        # Convert to PyTorch tensors
        X_tensor = torch.FloatTensor(X).to(self.device)
        y_tensor = torch.LongTensor(y).to(self.device)
        
        dataset = TensorDataset(X_tensor, y_tensor)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
        
        # Initialize model
        input_dim = X.shape[2]
        self.model = IVForecasterModel(input_dim=input_dim).to(self.device)
        
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        
        logger.info(f"Training LSTM IV Forecaster for {epochs} epochs on {self.device}...")
        self.model.train()
        
        for epoch in range(epochs):
            total_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
                
            if (epoch + 1) % 10 == 0:
                logger.debug(f"Epoch [{epoch+1}/{epochs}], Loss: {total_loss/len(loader):.4f}")
                
        self.is_trained = True
        self._save_model()
        logger.info("LSTM Training complete.")

    def predict(self, current_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict 30-day forward IV direction using the most recent sequence.
        
        Returns:
            Dict containing direction ('UP', 'DOWN', 'FLAT') and confidence (0.0 - 1.0).
        """
        fallback = {"direction": "UNKNOWN", "confidence": 0.0}
        
        if not self.is_trained or self.model is None or not TORCH_AVAILABLE:
            return fallback
            
        if len(current_data) < self.sequence_length:
            logger.warning(f"Not enough recent data to predict IV. Need {self.sequence_length} days.")
            return fallback
            
        # Extract features (using same dummy padding as train for unpopulated cols)
        required_cols = ['IV_30', 'IV_Rank', 'VIX_Close', 'HV_20', 'ATR_Pct', 'Days_To_Earnings']
        df = current_data.copy()
        for num_col in required_cols:
            if num_col not in df.columns:
                df[num_col] = 0.5
                
        # Get the last exactly 'sequence_length' days
        df = df.tail(self.sequence_length)
        features = df[required_cols].values
        
        # Normalize (Assuming standard scaling approx for this mockup)
        features = (features - np.mean(features, axis=0)) / (np.std(features, axis=0) + 1e-8)
        
        # Reshape to (1, sequence_length, features)
        X_tensor = torch.FloatTensor(features).unsqueeze(0).to(self.device)
        
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(X_tensor)
            probabilities = torch.softmax(outputs, dim=1).cpu().numpy()[0]
            
        predicted_class_idx = np.argmax(probabilities)
        confidence = probabilities[predicted_class_idx]
        direction = self.class_mapping.get(predicted_class_idx, "UNKNOWN")
        
        return {
            "direction": direction,
            "confidence": float(confidence),
            "probs": {
                "DOWN": float(probabilities[0]),
                "FLAT": float(probabilities[1]),
                "UP": float(probabilities[2])
            }
        }
