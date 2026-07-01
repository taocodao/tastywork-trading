"""
Train the SNDK DSS (Directional Signal Score) XGBoost Model locally.
Fetches historical data using yfinance.
"""
import sys
import logging
import pandas as pd
try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Please install it using: pip install yfinance")
    sys.exit(1)

from src.otm_naked.sndk.feature_engineering import build_sndk_features
from src.otm_naked.sndk.dss_model import DSSModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_data():
    logger.info("Fetching historical daily data for SNDK, SPY, VIX...")
    
    # We use roughly 16-18 months of data to cover recent regimes, or more if available
    # SNDK has been trading longer, but let's grab last 2 years for robust training
    sndk = yf.download("SNDK", period="2y", interval="1d")
    spy = yf.download("SPY", period="2y", interval="1d")
    vix = yf.download("^VIX", period="2y", interval="1d")
    vix3m = yf.download("^VIX3M", period="2y", interval="1d")
    rf = yf.download("^TNX", period="2y", interval="1d") # 10-year treasury yield proxy
    
    # Formatting columns for yfinance MultiIndex returned in newer versions
    def flatten_columns(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df

    sndk = flatten_columns(sndk)
    spy = flatten_columns(spy)
    vix = flatten_columns(vix)
    vix3m = flatten_columns(vix3m)
    rf = flatten_columns(rf)

    # Ensure lowercase columns
    sndk.columns = [c.lower() for c in sndk.columns]
    spy.columns = [c.lower() for c in spy.columns]
    vix.columns = [c.lower() for c in vix.columns]
    vix3m.columns = [c.lower() for c in vix3m.columns]
    rf.columns = [c.lower() for c in rf.columns]
    
    return sndk, spy, vix, vix3m, rf

def main():
    logger.info("Starting local DSS Model Training Pipeline")
    
    try:
        sndk, spy, vix, vix3m, rf = fetch_data()
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return

    # Check for empty
    if sndk.empty:
        logger.error("No SNDK data found.")
        return
        
    logger.info(f"Loaded {len(sndk)} rows of SNDK daily data.")
    
    # We need to map yfinance columns to our feature engine signature:
    # close, open_price, high, low, volume, vix, spy_close, vix3m, rf, earnings_days_away
    
    # Approximate earnings days away (mocked for training purposes since exact historical dates are hard to fetch automatically without an API)
    # SNDK reports ~every 90 days. We'll use a sawtooth pattern from 90 down to 0.
    days_len = len(sndk)
    earnings_days_away = pd.Series([90 - (i % 90) for i in range(days_len)], index=sndk.index)
    
    logger.info("Generating 18+ features through feature_engineering pipeline...")
    
    # The feature builder handles the merging, but we pass aligned Series
    df_features = build_sndk_features(
        close=sndk['close'],
        open_price=sndk['open'],
        high=sndk['high'],
        low=sndk['low'],
        volume=sndk['volume'],
        vix=vix['close'],
        spy_close=spy['close'],
        vix3m=vix3m['close'],
        rf=rf['close'] / 100.0, # convert % to decimal
        earnings_days_away=earnings_days_away
    )
    
    # Need to preserve the close price for target generation in DSSModel
    df_features["close"] = sndk['close'].reindex(df_features.index)
    
    logger.info(f"Feature generation complete. {len(df_features)} rows ready for training.")
    
    model = DSSModel(model_dir="models")
    try:
        model.train_model(df_features)
    except Exception as e:
        logger.error(f"Training failed: {e}")
        
    if model.is_loaded:
        logger.info("Verifying model predictions...")
        # Test a prediction
        test_row = df_features.iloc[-1]
        score = model.predict_dss(test_row)
        logger.info(f"Latest day DSS prediction score: {score:.3f}")

if __name__ == "__main__":
    main()
