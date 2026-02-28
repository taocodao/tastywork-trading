"""
Backtest Runner
===============
CLI entry point to run the Active Diagonal backtest, train ML, or optimize.
"""

import argparse
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

def setup_logger():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_engine(principal=None):
    from diagonal_strategy.config import TQQQ_DIAGONAL_PARAMS as raw_config
    import diagonal_strategy.config as config
    
    if principal is not None:
        config.ACCOUNT_VALUE = principal
    from diagonal_strategy.core.ta_signal_engine import TASignalEngine
    from diagonal_strategy.ml.oscillation_predictor import OscillationPredictor
    from diagonal_strategy.core.risk_manager import DiagonalRiskManager
    from diagonal_strategy.backtest.data_loader import DiagonalDataLoader
    from diagonal_strategy.backtest.engine import BacktestEngine
    
    loader = DiagonalDataLoader()
    df = loader.load_historical_data("2019-01-01")
    
    if df is None or df.empty:
        logger.error("Failed to load historical data. Exiting.")
        return None
        
    osc_predictor = OscillationPredictor("diagonal_strategy/ml/models/xgb_oscillator.json")
    ta_engine = TASignalEngine(ml_model=osc_predictor)
    
    rx_manager = DiagonalRiskManager(config.ACCOUNT_VALUE)
    
    engine = BacktestEngine(df, config, ta_engine, rx_manager, osc_predictor)
    return engine

def main():
    setup_logger()
    parser = argparse.ArgumentParser(description="Active Diagonal Strategy CLI")
    parser.add_argument("--run", action="store_true", help="Run backtest with default params")
    parser.add_argument("--optimize", action="store_true", help="Run parameter optimization")
    parser.add_argument("--optimize-regime", type=str, help="Specific regime to optimize (LOW_VOL, NORMAL, HIGH_VOL)")
    parser.add_argument("--train-ml", action="store_true", help="Train Oscillation Predictor")
    parser.add_argument("--principal", type=float, default=25000.0, help="Account principal to simulate scaling")
    parser.add_argument("--maxiter", type=int, default=10, help="DE max generations (default 10, ~2min/regime)")
    parser.add_argument("--popsize", type=int, default=10, help="DE population size per generation (default 10)")
    
    args = parser.parse_args()
    
    if args.train_ml:
        logger.info("Training ML Model...")
        from diagonal_strategy.backtest.data_loader import DiagonalDataLoader
        from diagonal_strategy.ml.feature_engineering import FeatureEngineer
        from diagonal_strategy.ml.model_trainer import ModelTrainer
        
        loader = DiagonalDataLoader()
        df = loader.load_historical_data("2015-01-01", use_cache=True)
        if df is None: return
        
        engineer = FeatureEngineer()
        X, y = engineer.create_features_and_labels(df)
        
        trainer = ModelTrainer()
        trainer.train(X, y)
        return

    engine = get_engine(args.principal)
    if not engine: return
    
    if args.optimize:
        from diagonal_strategy.ml.param_optimizer import ParamOptimizer
        opt = ParamOptimizer(engine)
        regimes = [args.optimize_regime] if args.optimize_regime else ['LOW_VOL', 'NORMAL', 'HIGH_VOL']
        
        os.makedirs("data", exist_ok=True)
        for regime in regimes:
            logger.info(f"Optimizing {regime}  (maxiter={args.maxiter}, popsize={args.popsize})...")
            best = opt.optimize(
                regime, "2019-01-01", "2024-01-01",
                maxiter=args.maxiter,
                popsize=args.popsize
            )
            logger.info(f"Best params for {regime}: {json.dumps(best, indent=2)}")
            
            with open(f"data/optimized_params_{regime}.json", "w") as f:
                json.dump(best, f, indent=2)
        return
        
    if args.run or not (args.train_ml or args.optimize):
        metrics = engine.run_scenario()
        logger.info(f"Final Metrics:\n{json.dumps(metrics, indent=2)}")
        
        os.makedirs("data", exist_ok=True)
        with open("data/last_backtest_trades.json", "w") as f:
            json.dump(engine.trades_history, f, indent=2, default=str)
        logger.info("Saved trades history to data/last_backtest_trades.json")

if __name__ == "__main__":
    main()
