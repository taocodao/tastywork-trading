#!/usr/bin/env python3
"""
TurboCore ML Scheduler
==================================================
Runs the daily data fetch, ML Regime detection, XGBoost scoring, 
and Kelly-sized allocation for the 530+SMA200 strategy.
Emits the final allocation vector to the signal_publisher to be picked up
by auto_approve.py.
"""

import os
import time
import logging
import requests
from datetime import datetime, date, timedelta
import pytz
from dotenv import load_dotenv

def is_market_open() -> bool:
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)
    if now.weekday() >= 5: return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close

def time_until_market_open() -> float:
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now > market_open:
        market_open += timedelta(days=1)
    while market_open.weekday() >= 5:
        market_open += timedelta(days=1)
    return (market_open - now).total_seconds()

# Load environment variables
load_dotenv()

from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
from src.tqqq_turbocore.base_strategy import BaseStrategy
from src.tqqq_turbocore.ml.regime_detector import TurboCoreRegimeDetector
from src.tqqq_turbocore.ml.signal_scorer import TurboCoreSignalScorer
from src.tqqq_turbocore.allocation_optimizer import AllocationOptimizer
from signal_publisher.turbocore import publish_turbocore_rebalance_signal

# Configure logging
home_dir = os.path.expanduser("~")
log_dir = os.path.join(home_dir, "tastywork-trading", "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'run_turbocore_scheduler.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TurboCoreScheduler")

import json
import math
import pathlib
SCAN_STATE_FILE = pathlib.Path('/home/ubuntu/tastywork-trading/data/last_scan_state.json')

class TurboCoreScheduler:
    def _load_state(self) -> dict:
        if SCAN_STATE_FILE.exists():
            try:
                return json.loads(SCAN_STATE_FILE.read_text())
            except Exception as e:
                logger.error(f"Error loading scan state: {e}")
        return {}

    def _save_state(self, state: dict):
        try:
            SCAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SCAN_STATE_FILE.write_text(json.dumps(state, default=str))
        except Exception as e:
            logger.error(f"Error saving scan state: {e}")

    # Backward-compat helpers
    def _load_last_scan_date(self):
        d = self._load_state().get('last_scan_date')
        return date.fromisoformat(d) if d else None

    def _save_last_scan_date(self, d: date):
        state = self._load_state()
        state['last_scan_date'] = d.isoformat()
        self._save_state(state)

    def __init__(self):
        self.data_pipe = TurboCoreDataPipeline()
        self.regime_detector = TurboCoreRegimeDetector()
        self.scorer = TurboCoreSignalScorer()
        self.allocator = AllocationOptimizer()
        self.tz = pytz.timezone('US/Eastern')
        self.last_scan_date = self._load_last_scan_date()
        
    def run_daily_scan(self):
        logger.info("--- Starting TurboCore ML Daily Scan v2 ---")

        # ── 0. Load persistent state (ATH, last trained date) ────────────────
        state = self._load_state()

        # ── 1. Quarterly HMM auto-retrain check ──────────────────────────────
        if self.regime_detector.needs_retrain():
            logger.info("HMM quarterly retrain triggered — fetching 5y data")
            self.data_pipe.fetch_data("5y")
        else:
            self.data_pipe.fetch_data("2y")

        master_df = self.data_pipe.prepare_core_features()
        if master_df.empty:
            logger.error("Data pipeline returned empty dataframe. Aborting.")
            return

        # ── 2. Retrain HMM if needed (after fresh 5y data fetch) ─────────────
        if self.regime_detector.needs_retrain():
            logger.info("Retraining HMM v2 with 6-feature set...")
            self.regime_detector.fit(master_df)

        # ── 3. Base Rules → HMM → XGBoost ────────────────────────────────────
        base = BaseStrategy(master_df)
        df = base.evaluate()
        df = self.regime_detector.predict_regimes(df)
        df = self.scorer.predict_confidence(df)

        # ── 4. Extract today's signal row ────────────────────────────────────
        today_row = df.iloc[-1]

        regime       = str(today_row.get('final_regime', 'SIDEWAYS'))
        base_signal  = int(today_row.get('base_signal', 0))
        confidence   = float(today_row.get('ml_confidence', 0.55))
        if confidence == 0.0:
            confidence = 0.55
            
        # v2.1: Disabling XGBoost p_loss as N<100 data starvation falsely vetoes early bull market rallies
        p_loss       = 0.0 
        
        is_sma_forced = bool(today_row.get('qqq_below_sma200_sell', False))

        # v2: dual-EMA confirmation modifiers
        dual_confirm = bool(today_row.get('dual_ema_confirmed', False))
        rsi_add      = bool(today_row.get('rsi_add_signal', False))
        rsi_trim     = bool(today_row.get('rsi_trim_signal', False))

        # SMA200 hard override
        if is_sma_forced:
            regime = "BEAR_SMA_FORCED"

        # ── 5. Compute blended current_vol for vol-targeting ─────────────────
        try:
            qqq_rv = float(today_row.get('qqq_vol_20d', 0.0)) * math.sqrt(252)
            vix_daily = float(today_row.get('vix_close', 20.0)) / 100.0
            current_vol = round(0.6 * qqq_rv + 0.4 * vix_daily, 4)
        except Exception:
            current_vol = None

        # ── 6. Compute portfolio drawdown from ATH ────────────────────────────
        # ATH is persisted across runs in state file; approximated from TQQQ price
        # for a simple proxy (a full virtual account tracker is the robust solution)
        try:
            tqqq_px = float(today_row.get('tqqq_close', 0))
            stored_ath = float(state.get('portfolio_ath', tqqq_px))
            if tqqq_px > stored_ath:
                stored_ath = tqqq_px
                state['portfolio_ath'] = stored_ath
            drawdown_pct = max(0.0, (stored_ath - tqqq_px) / stored_ath)
        except Exception:
            drawdown_pct = 0.0

        logger.info(
            f"Signal: regime={regime} signal={base_signal} conf={confidence:.1%} "
            f"p_loss={p_loss:.1%} dual={dual_confirm} rsi_add={rsi_add} rsi_trim={rsi_trim} "
            f"drawdown={drawdown_pct:.1%} current_vol={current_vol}"
        )

        # ── 7. Determine Allocation Matrix (v2 with all modifiers) ────────────
        target_allocation = self.allocator.get_target_allocation(
            regime=regime,
            signal=base_signal,
            ml_confidence=confidence,
            dual_confirm=dual_confirm,
            rsi_add=rsi_add,
            rsi_trim=rsi_trim,
            portfolio_drawdown_pct=drawdown_pct,
            current_vol=current_vol,
            p_loss=p_loss,
        )
        logger.info(f"Target allocation: {target_allocation}")

        rationale = (
            f"Regime: {regime} | Conf: {confidence:.0%} | p_loss: {p_loss:.0%} | "
            f"dual_confirm: {dual_confirm} | RSI2_add: {rsi_add} | RSI2_trim: {rsi_trim} | "
            f"drawdown: {drawdown_pct:.1%} | vol: {current_vol}"
        )

        # ── 8. Publish ────────────────────────────────────────────────────────
        publish_turbocore_rebalance_signal(
            regime=regime,
            confidence=confidence,
            alloc_dict=target_allocation,
            rationale=rationale,
            ema_signal=base_signal,
            sma200_gate=not is_sma_forced,
            strategy="TQQQ_TURBOCORE"
        )

        # ── 9. Persist updated state ─────────────────────────────────────────
        state['last_scan_date'] = date.today().isoformat()
        self._save_state(state)

        # ── 10. SSE push to web app ───────────────────────────────────────────
        try:
            resp = requests.post(
                "https://www.trademind.bot/api/signals/notify",
                json={"strategy": "TQQQ_TURBOCORE"},
                timeout=10
            )
            if resp.status_code == 200:
                logger.info("SSE notification pushed to trademind.bot")
            else:
                logger.warning(f"SSE push returned status {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to notify trademind.bot SSE: {e}")

        logger.info("--- TurboCore v2 Scan Complete ---")

    def run_loop(self):
        """Main execution loop for continuous running."""
        logger.info("Starting TurboCore Background Daemon loop...")
        
        while True:
            try:
                now = datetime.now(self.tz)
                is_open = is_market_open()
                
                time_to_scan = False
                
                # Trigger scan continuously after 15:00 ET (1 hour before close) and catch-up if missed
                if now.weekday() < 5 and now.hour >= 15:
                    if self.last_scan_date != now.date():
                        time_to_scan = True
                
                if time_to_scan:
                    self.run_daily_scan()
                    self.last_scan_date = now.date()
                    self._save_last_scan_date(self.last_scan_date)
                    
                if is_open:
                    # Check every 1 minute to ensure we trigger cleanly at 3:00 PM
                    time.sleep(60)
                else:
                    sleep_time = time_until_market_open()
                    logger.info(f"Market closed. Sleeping for {sleep_time/3600:.1f} hours.")
                    for _ in range(int(sleep_time / 300)):
                        time.sleep(300)
            except Exception as e:
                logger.error(f"Fatal error in scheduler loop: {e}", exc_info=True)
                time.sleep(60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TurboCore ML Scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    args = parser.parse_args()
    
    scheduler = TurboCoreScheduler()
    if args.once:
        scheduler.run_daily_scan()
    else:
        scheduler.run_loop()
