import logging
import yfinance as yf
from datetime import datetime
import uuid

import diagonal_strategy.config as config
from diagonal_strategy.core.ta_signal_engine import TASignalEngine
from diagonal_strategy.ml.oscillation_predictor import OscillationPredictor
from diagonal_strategy.core.state_machine import ActiveDiagonalManager, DiagonalPosition, DiagonalState
from signal_publisher.diagonal import publish_diagonal_entry_signal, DiagonalEntrySignal

logger = logging.getLogger(__name__)

class DiagonalLiveScanner:
    def __init__(self):
        self.ta_engine = TASignalEngine(ml_model=None)
        self.osc_predictor = OscillationPredictor()
        
        # We need a trained model for predictions. During Phase 3, we built the xgboost model.
        try:
            self.osc_predictor.load_models()
        except Exception as e:
            logger.warning(f"DiagonalLiveScanner: ML model not loaded, relying on TA. ({e})")

        self.manager = ActiveDiagonalManager(config, self.ta_engine, self.osc_predictor)

    def scan(self) -> int:
        logger.info("📐 Running Active Diagonal Strategy Scan...")
        
        try:
            # 1. Fetch TQQQ data
            tqqq = yf.Ticker("TQQQ").history(period="6mo")
            if tqqq.empty:
                logger.warning("No TQQQ data fetched.")
                return 0
                
            # Rename columns to lowercase for TASignalEngine
            tqqq = tqqq.rename(columns=str.lower)
            
            # 2. Fetch VIX data
            vix = yf.Ticker("^VIX").history(period="1mo")
            if vix.empty:
                logger.warning("No VIX data fetched.")
                return 0
                
            cur_vix = vix['Close'].iloc[-1]
            if len(vix) >= 6:
                vix_roc_5 = (cur_vix - vix['Close'].iloc[-6]) / vix['Close'].iloc[-6]
            else:
                vix_roc_5 = 0.0
                
            # Regime map
            if cur_vix < 18.0: 
                regime = 'LOW_VOL'
            elif cur_vix < 25.0: 
                regime = 'NORMAL'
            else: 
                regime = 'HIGH_VOL'
            
            # Combine
            mkt_data = {
                'tqqq_bars': tqqq,
                'vix_level': cur_vix,
                'vix_roc_5': vix_roc_5,
                'regime': regime,
                'current_date': datetime.now().date(),
            }
            
            # 3. Dummy position for entry evaluation
            dummy_pos = DiagonalPosition(position_id="dummy", state=DiagonalState.IDLE)
            
            # 4. Evaluate using the state machine rules
            action = self.manager.evaluate(dummy_pos, mkt_data)
            
            if action == 'OPEN_DIAGONAL':
                # Re-compute features just to get the scores for logging/publishing
                ta_features = self.ta_engine.compute_features(mkt_data)
                dip_score = self.ta_engine.dip_score(ta_features)
                ml_pred = self.osc_predictor.predict(ta_features)
                
                logger.info(f"  ✅ Diagonal Signal FOUND: Regime={regime}, Dip={dip_score:.2f}, ML={ml_pred['direction']} ({ml_pred['confidence']:.2f})")
                
                # Create Signal
                sig = DiagonalEntrySignal(
                    id=str(uuid.uuid4()),
                    symbol="TQQQ",
                    strategy="diagonal",
                    dip_score=dip_score,
                    ml_direction=ml_pred['direction'],
                    ml_confidence=ml_pred['confidence'],
                    regime=regime,
                    current_price=tqqq['close'].iloc[-1],
                    status="pending",
                    created_at=datetime.utcnow().isoformat()
                )
                
                # Publish
                success = publish_diagonal_entry_signal(sig)
                if success:
                    logger.info("  🚀 Successfully published Diagonal Entry Signal to Hub.")
                    return 1
            else:
                logger.info(f"  No Diagonal Entry Signal at this time. (Regime={regime}, Action={action})")
            
            return 0
            
        except Exception as e:
            logger.error(f"Error in Diagonal scan: {e}")
            import traceback
            traceback.print_exc()
            return 0

def run_diagonal_scanner() -> int:
    scanner = DiagonalLiveScanner()
    return scanner.scan()
