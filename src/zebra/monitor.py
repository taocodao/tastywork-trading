"""
ZEBRA Strategy Monitor
======================
Main service loop for ZEBRA strategy.
Runs 24/7, performing entry scans and position management.
"""

import sys
import os
import time
import signal
import logging
from datetime import datetime, timedelta
import pytz

# Adjust path to root to import config/tastytrade_client
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from config import (
    ZEBRA_SCAN_INTERVAL_MIN, ZEBRA_POSITION_CHECK_MIN,
    ZEBRA_ENTRY_WINDOW_START, ZEBRA_ENTRY_WINDOW_END,
    ZEBRA_ENABLED, ZEBRA_MIN_DIRECTIONAL_CONFIDENCE
)
from src.zebra.client import ZebraClient
from src.zebra.universe import ZebraUniverse
from src.zebra.construction_engine import ZebraConstructionEngine
from src.zebra.lifecycle_engine import ZebraLifecycleEngine, ZebraPositionState, ZebraAction
from src.zebra.security_scorer import ZebraSecurityScorer
from src.zebra.entry_timing import ZebraEntryTiming
from src.zebra.exit_engine import ZebraExitEngine
from src.zebra.regime_detector import RegimeDetector
from src.zebra.ml_signal_filter import ZebraMLFilter, FeatureExtractor
from src.zebra.position_monitor import ZebraPositionMonitor
from signal_publisher.zebra import ZebraEntrySignal, ZebraExitSignal, publish_zebra_entry_signal, publish_zebra_exit_signal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] ZEBRA: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/zebra_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

class ZebraMonitor:
    def __init__(self):
        self.client = ZebraClient()
        self.universe = ZebraUniverse(self.client)
        self.constructor = ZebraConstructionEngine(self.client)
        self.lifecycle = ZebraLifecycleEngine()
        self.scorer = ZebraSecurityScorer()
        self.entry_timing = ZebraEntryTiming()
        self.exit_engine = ZebraExitEngine()
        
        # Enhanced Components (Phase 6)
        self.regime_detector = RegimeDetector()
        self.ml_filter = ZebraMLFilter()
        
        # Per-User Monitor (Phase 9)
        self.position_monitor = ZebraPositionMonitor()
        # Load optimized model if available
        try:
            import json
            if os.path.exists("zebra_regime_params_prod.json"):
                with open("zebra_regime_params_prod.json", "r") as f:
                    params = json.load(f)
                    self.regime_detector.set_optimized_params(params)
                    logger.info("Loaded Optimized Regime Parameters.")
        except Exception as e:
            logger.error(f"Failed to load optimized params: {e}")

        # Load optimized model if available
        # Prefer production model
        model_path = "zebra_ml_model_prod.joblib"
        if not os.path.exists(model_path):
             model_path = "zebra_ml_model_optimized.joblib" # Fallback to sim model
             
        self.ml_filter.load_model(model_path)
        
        self.running = True
        
        # State
        self.last_scan_time = datetime.min
        self.last_check_time = datetime.min
        self.last_retrain_time = datetime.now() # Don't retrain immediately on restart

    def check_retrain_schedule(self):
        """
        Check if we need to retrain the ML model (Weekly on Sunday).
        """
        now = datetime.now()
        # Retrain if Sunday and haven't retrained today
        if now.weekday() == 6 and (now - self.last_retrain_time).days >= 1:
             logger.info("Weekly ML Retraining Triggered...")
             try:
                 # Run training script as subprocess to avoid blocking main loop too long?
                 # Or import and run? Import is better for state sharing but might block.
                 # Subprocess is safer for memory.
                 import subprocess
                 subprocess.Popen([sys.executable, "src/zebra/train_production.py"])
                 self.last_retrain_time = now
             except Exception as e:
                 logger.error(f"Retraining trigger failed: {e}")

    def connect(self):
        if not self.client.connect():
            logger.error("Failed to connect to Tastytrade")
            sys.exit(1)
        logger.info("Connected to Tastytrade")

    def run(self):
        self.connect()
        logger.info("ZEBRA Monitor started")
        
        while self.running:
            try:
                now = datetime.now(pytz.timezone('US/Eastern'))
                
                # Market Hours Check
                if self._is_market_open(now):
                    # 1. Entry Scan
                    if self._should_run_entry_scan(now):
                        self.run_entry_scan()
                        self.last_scan_time = now.replace(tzinfo=None)
                        
                    # 2. Position Check
                    if self._should_run_position_check(now):
                        self.run_position_check()
                        self.last_check_time = now.replace(tzinfo=None)
                        
                    # 3. Retraining Check
                    self.check_retrain_schedule()
                        
                else:
                    logger.debug("Market closed. Sleeping...")
                
                # Sleep 60s
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(60)

    def _is_market_open(self, now):
        # Simple check: Mon-Fri, 9:30-16:00
        if now.weekday() >= 5: return False
        market_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_start <= now <= market_end

    def _should_run_entry_scan(self, now):
        # Window check
        entry_start = now.replace(hour=ZEBRA_ENTRY_WINDOW_START.hour, minute=ZEBRA_ENTRY_WINDOW_START.minute)
        entry_end = now.replace(hour=ZEBRA_ENTRY_WINDOW_END.hour, minute=ZEBRA_ENTRY_WINDOW_END.minute)
        
        if not (entry_start <= now <= entry_end):
            return False
            
        # Interval check
        elapsed = (now.replace(tzinfo=None) - self.last_scan_time).total_seconds() / 60
        return elapsed >= ZEBRA_SCAN_INTERVAL_MIN

    def _should_run_position_check(self, now):
        elapsed = (now.replace(tzinfo=None) - self.last_check_time).total_seconds() / 60
        return elapsed >= ZEBRA_POSITION_CHECK_MIN

    def run_entry_scan(self):
        logger.info("Starting Enhanced Entry Scan...")
        symbols = self.universe.get_eligible_symbols()
        
        # 0. Detect Market Regime
        # Ensure data availability
        try:
            now = datetime.now()
            self.regime_detector.fetch_spy_data(now - timedelta(days=60), now)
            regime_label, regime_params = self.regime_detector.get_regime(now)
            logger.info(f"Market Regime: {regime_label}")
            
            if regime_label == 'CRISIS':
                logger.warning("CRISIS Regime detected. Skipping entry scan.")
                return
        except Exception as e:
            logger.error(f"Regime detection failed: {e}")
            regime_label = "NORMAL" # Fallback
            regime_params = {}

        # Fetch open positions for limit check
        open_pos_symbols = []
        try:
            positions = self.client.get_zebra_positions()
            open_pos_symbols = [p['symbol'] for p in positions]
        except Exception:
            pass # Use empty list if fetch fails

        for symbol in symbols:
            # Per-Symbol Limit Check (Phase 8)
            if open_pos_symbols.count(symbol) >= 2:
                logger.debug(f"Skipping {symbol}: Already have {open_pos_symbols.count(symbol)} positions.")
                continue

            try:
                # 1. Fetch data for scoring
                df = self.client.get_historical_data(symbol)
                if df is None or df.empty:
                    continue
                
                # 2. Multi-Factor Scoring
                score_res = self.scorer.score_symbol(symbol, df)
                logger.debug(f"Scored {symbol}: {score_res['composite_score']:.1f}")
                
                if score_res['composite_score'] < ZEBRA_MIN_DIRECTIONAL_CONFIDENCE:
                    continue
                
                # 3. ML Signal Filter (Guardrail)
                # Feature Extraction
                # Create candidate dict for extractor
                cand_dict = {
                    'symbol': symbol,
                    'price': df.iloc[-1]['Close'],
                    'Drop_Pct': (df['High'].iloc[-20:].max() - df.iloc[-1]['Close']) / df['High'].iloc[-20:].max() * 100,
                    'RSI': score_res.get('rsi', 50), # Assuming scorer returns RSI
                    'SMA50': df['Close'].rolling(50).mean().iloc[-1],
                    'Close': df.iloc[-1]['Close'],
                    'atr': 0 # placeholder if not calculated
                }
                
                features = FeatureExtractor.extract(cand_dict, df, datetime.now())
                should_trade, ml_conf = self.ml_filter.should_trade(features)
                
                if not should_trade:
                    logger.info(f"ML Filter rejected {symbol} (Conf: {ml_conf:.2f})")
                    continue

                # 4. Entry Timing & Regime Adjustment
                # Pass recent rows to timing engine
                now_row = df.iloc[-1]
                prev_rows = df.iloc[:-1]
                timing_res = self.entry_timing.should_enter(symbol, now_row, prev_rows)
                
                if not timing_res['enter']:
                    logger.info(f"Skipping {symbol} due to timing: {timing_res['reason']}")
                    continue
                
                logger.info(f"Entry Signal for {symbol}: Score {score_res['composite_score']:.1f} (ML: {ml_conf:.2f})")

                # 4. Construct Trade
                price = now_row['Close']
                # Direction currently hardcoded Bullish, but could be derived from score_res
                direction = "LONG" 
                
                structures = self.constructor.construct(symbol, price, direction=direction)
                
                    # Dynamic Position Sizing
                    try:
                        equity = self.client.get_account_equity()
                        if equity <= 0: equity = 10000.0 # Safety fallback
                        
                        # Allocation Logic (Same as Simulation)
                        # High Conviction: Score >= 80, ML >= 0.70 -> 15%
                        # Standard: Score >= 65, ML >= 0.60 -> 12%
                        # Marginal: -> 8%
                        alloc_pct = 0.08
                        if score_res['composite_score'] >= 80 and ml_conf >= 0.70:
                            alloc_pct = 0.15
                        elif score_res['composite_score'] >= 65 and ml_conf >= 0.60:
                            alloc_pct = 0.12
                            
                        target_capital = equity * alloc_pct
                        cost_per_unit = best.net_debit * 100
                        
                        num_contracts = int(target_capital / cost_per_unit)
                        num_contracts = max(1, num_contracts) # Ensure at least 1 if valid
                        
                        # Cap at max contracts? Maybe 10?
                        num_contracts = min(num_contracts, 10)
                    except Exception as sz_err:
                        logger.error(f"Sizing error: {sz_err}")
                        num_contracts = 1

                    self._publish_entry(best, score_res['composite_score'], price, signal_params, contracts=num_contracts)
                    
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")

    def run_position_check(self):
        logger.info("Checking Open Positions with Advanced Exit Engine...")
        
        # 0. Run Per-User Position Monitor (Phase 9)
        self.position_monitor.check_all_users()
        
        # 1. Fetch positions from Tastytrade
        # Note: This requires logic to reconstruct ZEBRA complexes from flat legs
        # For now, we simulate the loop over what would be grouped positions
        positions = self.client.get_zebra_positions() # Assuming this handles grouping
        
        # Get Regime Params for Dynamic Exit
        try:
            now = datetime.now()
            # Ensure data (cached or fetch)
            # self.regime_detector.fetch_spy_data... (Done in entry scan? Optimize to share cache)
            # Just call get_regime, it handles if data missing? No, need fetch.
            # Assuming entry scan runs frequently or we fetch lightly here.
            self.regime_detector.fetch_spy_data(now - timedelta(days=60), now) 
            _, regime_params = self.regime_detector.get_regime(now)
        except:
             regime_params = {}
        
        
        for pos in positions:
            try:
                # 2. Update state for evaluation
                # This needs current stock price and recent price action
                symbol = pos['symbol']
                df = self.client.get_historical_data(symbol)
                if df is None or df.empty: continue
                
                # 3. Evaluate using Advanced Exit Engine
                # We convert Tastytrade position data to the format ExitEngine expects
                eval_data = {
                    'symbol': symbol,
                    'entry_price': pos['entry_price'],
                    'current_price': df.iloc[-1]['Close'],
                    'high_watermark': pos.get('high_watermark', df.iloc[-1]['Close']), # Should be tracked in DB/State
                    'entry_debit': pos['entry_debit'],
                    'days_held': (datetime.utcnow() - pos['entry_date']).days,
                    'current_row': df.iloc[-1],
                    'prev_row': df.iloc[-2] if len(df) > 1 else None,
                    'atr_at_entry': pos.get('atr_at_entry', 0)
                }
                
                exit_signal = self.exit_engine.evaluate(eval_data, override_params=regime_params)
                
                if exit_signal['exit']:
                    logger.info(f"EXIT SIGNAL for {symbol}: {exit_signal['reason']} ({exit_signal['priority']})")
                    self._publish_exit(pos, exit_signal['reason'])
                else:
                    # Also check original lifecycle for re-centering (not in exit_engine)
                    # This would involve creating a ZebraPositionState
                    pass

            except Exception as e:
                logger.error(f"Error checking position {pos.get('symbol')}: {e}")

    def _publish_entry(self, structure, confidence, price, params=None, contracts=1):
        # Determine current UTC time
        current_time_utc = datetime.utcnow()
        timestamp = int(current_time_utc.timestamp())
        
        # Prepare signal data
        signal_id = f"zebra_{structure.symbol}_{timestamp}"
        
        # Rationale including regime info if available
        regime_info = f" | Regime: {params.get('regime', 'NORMAL')}" if params and 'regime' in params else ""
        rationale = f"ZEBRA {structure.direction} Opportunity (Score: {structure.construction_score:.1f}){regime_info}"
        
        signal = ZebraEntrySignal(
            id=signal_id,
            symbol=structure.symbol,
            direction=structure.direction,
            
            # Structure
            long_strike=float(structure.long_leg.strike),
            long_delta=structure.long_leg.delta or 0.0,
            short_strike=float(structure.short_leg.strike),
            short_delta=structure.short_leg.delta or 0.0,
            expiry=structure.expiry.isoformat(),
            dte=structure.dte,
            
            # Pricing
            net_debit=structure.net_debit,
            max_loss=structure.net_debit, # Defined risk
            breakeven=structure.breakeven,
            
            # Greeks
            net_delta=structure.net_delta,
            net_theta=structure.net_theta,
            net_vega=structure.net_vega,
            net_extrinsic=structure.net_extrinsic,
            
            # Scoring
            construction_score=structure.construction_score,
            directional_confidence=confidence,
            capital_efficiency=structure.capital_efficiency,
            anti_crowding_score=100.0, # Placeholder
            composite_score=85.0, # Placeholder
            
            # Leg Quotes
            long_leg_bid=structure.long_leg.bid,
            long_leg_ask=structure.long_leg.ask,
            short_leg_bid=structure.short_leg.bid,
            short_leg_ask=structure.short_leg.ask,
            
            # Risk Context
            capital_required=structure.net_debit * 100, # Per contract
            expected_move_pct=0.0, # Placeholder
            thesis_horizon_days=30,
            
            # Metadata
            contracts=contracts,
            rationale=rationale,
            strategy="zebra",
            created_at=current_time_utc
        )
        
        if publish_zebra_entry_signal(signal):
            logger.info(f"Published ZEBRA signal for {structure.symbol} (Score: {structure.construction_score:.1f})")

    def _publish_exit(self, position, reason):
        """
        Publish exit signal for an open position.
        """
        signal_id = f"exit_{position.get('symbol')}_{int(time.time())}"
        
        exit_signal = ZebraExitSignal(
            id=signal_id,
            symbol=position.get('symbol'),
            reason=reason,
            pnl_dollar=0.0, # Calculated in client
            pnl_pct=0.0,
            created_at=datetime.utcnow()
        )
        
        if publish_zebra_exit_signal(exit_signal):
            logger.info(f"Published ZEBRA EXIT signal for {position.get('symbol')} | Reason: {reason}")

if __name__ == "__main__":
    monitor = ZebraMonitor()
    
    def handle_sig(signum, frame):
        monitor.running = False
        logger.info("Stopping...")
        
    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)
    
    monitor.run()
