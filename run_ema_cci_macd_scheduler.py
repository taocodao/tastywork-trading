"""
EMA-CCI-MACD Live Scheduler
===========================
EC2 daemon for the ML-enhanced signal engine.
Runs continuously, fetches data, evaluates rules, applies ML filter,
and publishes to the RDS + frontend SSE pipeline.
"""
import time
import schedule
import logging
from datetime import datetime
import argparse

from src.ema_cci_macd.config import EngineConfig
from src.ema_cci_macd.data_fetcher import YFinanceFetcher
from src.ema_cci_macd.indicators import compute_indicators
from src.ema_cci_macd.signal_engine import evaluate_signal
from src.ema_cci_macd.features import build_feature_vector
from src.ema_cci_macd.regime import classify_regime
from src.ema_cci_macd.ml_filter import MLSignalFilter
from src.ema_cci_macd.model_store import load_model
from src.ema_cci_macd.candidate_logger import CandidateLogger
from src.ema_cci_macd.signal_logger import SignalLogger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("Scheduler")

def job(config: EngineConfig, ml_filter: MLSignalFilter, candidate_db: CandidateLogger, signal_db: SignalLogger):
    logger.info("Starting scan cycle...")
    fetcher = YFinanceFetcher()
    
    for instr in config.watchlist:
        logger.info(f"Scanning {instr.symbol} ({instr.timeframe})")
        df = fetcher.fetch_ohlcv(instr.symbol, instr.timeframe)
        if df.empty:
            continue
            
        df = compute_indicators(df, instr.ema_layers, instr.cci_period,
                                instr.macd_fast, instr.macd_slow, instr.macd_signal)
                                
        candidate = evaluate_signal(df, instr.symbol, instr.timeframe, 
                                    instr.ema_layers, instr.proximity_pct, instr.cci_lookback)
                                    
        if candidate is None:
            continue
            
        logger.info(f"Setup detected: {candidate.direction} {candidate.symbol} @ {candidate.entry_price}")
        
        # ML enrichment
        idx = len(df) - 1
        candidate.features = build_feature_vector(df, idx, instr)
        candidate.regime = classify_regime(df, idx, instr)
        
        if ml_filter and ml_filter.model:
            candidate.ml_score = ml_filter.score_candidate(candidate)
            candidate.publish_decision = ml_filter.should_publish(candidate)
            logger.info(f"  ML Score: {candidate.ml_score:.3f} | Publish: {candidate.publish_decision}")
        else:
            # Fallback to pure rules if ML is disabled or model missing
            candidate.publish_decision = True
            logger.info("  ML disabled. Publishing based on rules.")
            
        candidate_db.log_candidate(candidate)
        
        if candidate.publish_decision:
            signal_db.log_signal(candidate)
            # Call publisher
            from signal_publisher.ema_cci_macd import publish_ema_cci_macd_signal
            publish_ema_cci_macd_signal(candidate, config)
            logger.info(f"  --> PUBLISHED {candidate.symbol} {candidate.direction}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run scan once and exit")
    args = parser.parse_args()
    
    config = EngineConfig.from_yaml()
    candidate_db = CandidateLogger()
    signal_db = SignalLogger()
    
    model, metadata = load_model("v1")
    ml_filter = MLSignalFilter(model, metadata) if model else None
    
    if ml_filter:
        logger.info(f"Loaded ML model: v1 (Threshold: {metadata.publish_threshold})")
    else:
        logger.warning("No ML model found. Running in rules-only mode.")
        
    if args.once:
        job(config, ml_filter, candidate_db, signal_db)
        return
        
    interval = config.scheduler.interval_minutes
    schedule.every(interval).minutes.do(job, config, ml_filter, candidate_db, signal_db)
    
    logger.info(f"Scheduler running every {interval} minutes.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
