import logging
import os
import sys

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.pmcc.ml.data_provider import PolygonDataProvider
from src.pmcc.ml.confidence_gate import ConfidenceGatedDecisionMaker
from src.pmcc.ml.iv_forecaster import LSTMIVForecaster
from src.pmcc.ml.short_call_bandit import PMCCShortCallBandit
from src.pmcc.ml.pmcc_rl_agent import PMCCRLOptimizer

from src.pmcc.pmcc_selector import PMCCSelector
from src.pmcc.pmcc_short_call_selector import PMCCShortCallSelector
from src.pmcc.pmcc_stop_manager import PMCCStopManager

from src.zebra.ml_signal_filter import PMCCMLFilter
from src.zebra.regime_detector import RegimeDetector
from src.pmcc.ml.hmm_regime import HMMRegimeDetector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def bootstrap_pmcc_ml_engine():
    """
    Initializes all Phase 2 Machine Learning models and wires them into the PMCC trading engine.
    This script serves as the paper-trading entry point.
    """
    logger.info("Initializing PMCC Machine Learning Framework...")

    # 1. Gatekeeper / Confidence Engine
    gater = ConfidenceGatedDecisionMaker(confidence_threshold=0.70)
    
    # 2. HMM Regime Detector (Replaces hard ATR thresholds)
    hmm_detector = HMMRegimeDetector()
    regime_manager = RegimeDetector(hmm_model=hmm_detector if hmm_detector.is_trained else None)

    # 3. XGBoost Trade Veto Filter
    xgb_filter = PMCCMLFilter(confidence_threshold=0.65)
    
    # 4. LSTM IV Forecaster (For LEAPS Timing)
    lstm_forecaster = LSTMIVForecaster()
    
    # 5. LinUCB Bandit (For Short Call Strike Selection)
    bandit = PMCCShortCallBandit()
    
    # 6. PPO RL Agent (For Roll/Exit Timing)
    rl_agent = PMCCRLOptimizer(symbol="SPY") # Configurable per symbol

    logger.info("Models loaded. Wiring into Strategy Selectors...")

    # Wire into PMCC Selector (LEAPS + Initial Short)
    # The selector will now respect the LSTM's IV crush predictions
    leaps_selector = PMCCSelector()
    leaps_selector.iv_forecaster = lstm_forecaster if lstm_forecaster.is_trained else None
    
    # Wire into Short Call Selector
    # The selector will now respect the Bandit's expected premium mapping
    short_selector = PMCCShortCallSelector(bandit=bandit if bandit.is_trained else None)
    
    # Wire into Stop Manager
    # The stop manager will now query the PPO Agent before executing an exit/roll
    stop_manager = PMCCStopManager(rl_agent=rl_agent if rl_agent.model else None)

    logger.info("PMCC ML Engine Successfully Bootstrapped.")
    logger.info("Strategy is now ready for autonomous Paper Trading via Auto-Approve hooks.")

    return {
        "gater": gater,
        "regime": regime_manager,
        "filter": xgb_filter,
        "selector": leaps_selector,
        "short_selector": short_selector,
        "stop_manager": stop_manager
    }

if __name__ == "__main__":
    engine = bootstrap_pmcc_ml_engine()
