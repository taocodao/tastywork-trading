import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class BaseStrategy:
    """
    Implements the core deterministic logic for TQQQ TurboCore:
    1. 5/30 EMA Crossovers (Golden Cross = Long, Death Cross = Exit/Hedge)
    2. SMA200 Hysteresis Gate (+5% Buy / -3% Sell)
    """
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        
    def evaluate(self) -> pd.DataFrame:
        if self.df.empty:
            logger.warning("Empty dataframe provided to BaseStrategy")
            return self.df
            
        logger.info("Evaluating Base Strategy rules...")
        
        # Determine macro regime purely based on SMA200 Hysteresis
        # Initialize as 0 (Transitional)
        self.df['sma200_regime'] = 0 
        
        # We need to forward-fill state based on crossing the boundaries
        # +1 = Risk-On, 0 = Transitional, -1 = Risk-Off
        current_state = 0 
        regimes = []
        
        for idx, row in self.df.iterrows():
            if row['qqq_above_sma200_buy']:
                current_state = 1
            elif row['qqq_below_sma200_sell']:
                current_state = -1
            else:
                # If neither breached, we carry the prior state forward
                # Originally the plan states transitional zone is holding. Let's strictly map transitional
                pass 
                
            regimes.append(current_state)
            
        self.df['sma200_regime'] = regimes
        
        # Basic Signal Generation
        # 1 = Long, -1 = Exit/Short
        
        signals = []
        for idx, row in self.df.iterrows():
            if row['sma200_regime'] == 1 and row['tqqq_bull_cross']:
                signals.append(1) # Aggressive Bull
            elif row['sma200_regime'] == 1 and not row['tqqq_bull_cross']:
                signals.append(0) # Defensive Bull (Death cross inside Risk-On)
            elif row['sma200_regime'] == -1:
                signals.append(-1) # Hard Bear / Exit
            else:
                signals.append(0) # Transitional
                
        self.df['base_signal'] = signals
        return self.df
