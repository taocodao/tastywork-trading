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

# Canonical TurboCore Pro v3.3 — two-stage confidence pipeline with
# hysteresis tiers (replaces the legacy data_pipeline/base_strategy/
# regime_detector/signal_scorer/allocation_optimizer chain).
import yaml
from pathlib import Path
from src.turbocore_pro.live.signal_runner import SignalRunner
from signal_publisher.turbocore import publish_turbocore_rebalance_signal

# Configure logging
home_dir = os.path.expanduser("~")
log_dir = os.path.join(home_dir, "tastywork-trading", "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'run_turbocore_pro_scheduler.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TurboCoreProScheduler")

import json
import pathlib
SCAN_STATE_FILE = pathlib.Path('/home/ubuntu/tastywork-trading/data/last_scan_state_pro.json')

class TurboCoreProScheduler:
    def _load_last_scan_date(self):
        if SCAN_STATE_FILE.exists():
            try:
                state = json.loads(SCAN_STATE_FILE.read_text())
                d = state.get('last_scan_date')
                return date.fromisoformat(d) if d else None
            except Exception as e:
                logger.error(f"Error loading scan state: {e}")
        return None

    def _save_last_scan_date(self, d: date):
        try:
            SCAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SCAN_STATE_FILE.write_text(json.dumps({'last_scan_date': d.isoformat()}))
        except Exception as e:
            logger.error(f"Error saving scan state: {e}")

    def __init__(self):
        # Load canonical v3.3 config and signal runner
        cfg_path = Path(__file__).parent / "src" / "turbocore_pro" / "live" / "config" / "paper_web3aistore.yaml"
        with open(cfg_path) as f:
            self.config = yaml.safe_load(f)
        self.signal_runner = SignalRunner(self.config, Path(__file__).parent)
        self.signal_runner.load_models()
        self.tz = pytz.timezone('US/Eastern')
        self.last_scan_date = self._load_last_scan_date()
        
    def run_daily_scan(self):
        logger.info("--- Starting TurboCore Pro ML Daily Scan ---")
        
        # 1. Fetch live bars + VIX and build features via the canonical pipeline
        from src.turbocore_pro.live.data_fetcher import fetch_all_vix_indices
        try:
            # Hourly bars via yfinance (signal-only path; the IBKR paper trader
            # fetches its own bars through ib_insync for execution).
            import yfinance as yf
            lookback_days = int(self.config["strategy"].get("lookback_bars", 1500) / 6.5) + 10
            ibkr_bars = {}
            for sym in ("QQQ", "TQQQ", "QLD", "SGOV", "HYG"):
                df = yf.download(sym, period=f"{min(lookback_days, 729)}d", interval="1h",
                                 auto_adjust=True, progress=False)
                if df is not None and not df.empty:
                    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
                    ibkr_bars[sym] = df
            vix_data = fetch_all_vix_indices(self.config["strategy"].get("vix_indices", ["VIX"]))
        except Exception as e:
            logger.error(f"Live data fetch failed: {e}", exc_info=True)
            return

        master = self.signal_runner.build_features(ibkr_bars, vix_data)
        if master.empty:
            logger.error("Feature build returned empty dataframe. Aborting.")
            return

        # 2. Canonical v3.3 signal: HMM regime -> two-stage XGBoost confidence
        #    -> hysteresis-tier allocation (QQQ/QLD/TQQQ/SGOV)
        result = self.signal_runner.compute_signal(master)

        regime = str(result.get("regime", "BEAR"))
        base_signal = int(result.get("signal", 0))
        confidence = float(result.get("confidence", 0.0))
        target_allocation = result.get("target_allocation", {"SGOV": 1.0})

        logger.info(f"Canonical v3.3 allocation: {target_allocation} "
                    f"(regime={regime}, signal={base_signal}, conf={confidence:.3f})")

        rationale = (f"TurboCore Pro v3.3 | Regime: {regime} | Conf: {confidence:.0%} | "
                     f"QQQ close: {result.get('qqq_close', 0):.2f}")

        # 3. Publish rebalance signal (no IV-Switching overlay — retired)
        publish_turbocore_rebalance_signal(
            regime=regime,
            confidence=confidence,
            alloc_dict=target_allocation,
            rationale=rationale,
            ema_signal=base_signal,
            sma200_gate=True,
            strategy="TQQQ_TURBOCORE_PRO",
            iv_switching_pending=False,
        )
        
        # 6. Notify trademind.bot Web Application via SSE Push
        try:
            resp = requests.post(
                "https://www.trademind.bot/api/signals/notify",
                json={"strategy": "TQQQ_TURBOCORE_PRO"},
                timeout=10
            )
            if resp.status_code == 200:
                logger.info("✅ Pushed SSE notification to trademind.bot frontend")
            else:
                logger.warning(f"⚠️ SSE Push returned status {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ Failed to notify trademind.bot SSE endpoint: {e}")
        
        logger.info("--- TurboCore Pro Scan Complete ---")

        # ── IV-Switching Composite Strategy — Unified Signal (equity + options) ──
        # Publishes ONE combined signal:
        #   - equity legs: target_pct (generic, no absolute quantities)
        #   - options_intent: mode/type/underlying/delta/dte + market data for per-user sizing
        #   - legs_override: retained for backward compat with manual-approve UI card
        try:
            import sys as _sys, os as _os
            from datetime import date as _date
            _ivs_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                     'iv-switching-composite')
            if _ivs_dir not in _sys.path:
                _sys.path.insert(0, _ivs_dir)
            from daily_order_generator import (
                generate_daily_signal,
                reconcile_and_generate_order,
                format_as_turbocore_signal,
            )

            _signal = generate_daily_signal(_date.today())
            _mode = _signal['mode']

            # ── Build generic options_intent (Phase 1 output) ────────────────
            _mode_map = {
                'A':  {'type': 'CSP',   'underlying': 'TQQQ', 'delta': 0.12, 'dte': 7},
                'B':  {'type': 'ZEBRA', 'underlying': 'QQQM', 'delta': 0.70, 'dte': 75},
                'C':  {'type': 'CCS',   'underlying': 'QQQ',  'delta': 0.30, 'dte': 45},
                'D2': {'type': 'SQQQ',  'underlying': 'SQQQ', 'delta': None, 'dte': None},
                'D3': {'type': 'ZEBRA', 'underlying': 'QQQM', 'delta': 0.70, 'dte': 75},
            }
            _intent_base = _mode_map.get(_mode, {'type': None, 'underlying': None, 'delta': None, 'dte': None})
            _options_intent = {
                'mode':      _mode,
                **_intent_base,
                'qqq_px':    _signal.get('qqq_px'),
                'qqqm_px':   _signal.get('qqqm_px'),
                'tqqq_px':   _signal.get('tqqq_px'),
                'sqqq_px':   _signal.get('sqqq_px'),
                'iv_short':  _signal.get('iv_short'),
                'iv_tqqq':   _signal.get('iv_tqqq_10d'),
                'rf':        _signal.get('rf'),
                'vix':       _signal.get('vix'),
                'vix_vix3m': _signal.get('vix_vix3m'),
            }

            # ── Legacy: reference account for manual-approve UI card ─────────
            # (Still needed so the approve-options route can show a preview card)
            _ref_account = {
                'nlv': 25000, 'cash': 25000, 'buying_power': 25000,
                'position_counts': {'zebra_units': 0, 'csp_count': 0,
                                    'ccs_count': 0, 'sqqq_shares': 0},
            }
            _order = reconcile_and_generate_order(_signal, _ref_account)

            if _order.get('signal_type') not in ('NO_ACTION', 'HOLD', 'ERROR') \
               and _order.get('order_legs'):
                _tc_signal = format_as_turbocore_signal(_signal, _order, order_db_id='')

                # Equity legs (generic — no absolute quantities)
                _equity_legs = [
                    {'symbol': sym, 'action': 'BUY', 'target_pct': float(pct), 'leg_type': 'equity'}
                    for sym, pct in target_allocation.items()
                ]
                # Legacy options legs retained for manual-approve UI card only
                _options_legs = [
                    {**leg, 'leg_type': 'options'}
                    for leg in _tc_signal.get('legs', [])
                ]
                _combined_legs = _equity_legs + _options_legs

                publish_turbocore_rebalance_signal(
                    regime=_tc_signal['regime'],
                    confidence=_tc_signal['confidence'],
                    alloc_dict={},
                    rationale=_tc_signal['rationale'],
                    ema_signal=_tc_signal['ema_signal'],
                    sma200_gate=_tc_signal.get('sma200_gate', True),
                    strategy='TQQQ_TURBOCORE_PRO',
                    legs_override=_combined_legs,
                    action_override=_order.get('signal_type'),
                    iv_switching_order_id='',
                    cost_override=_tc_signal.get('cost', 0),
                    options_intent=_options_intent,   # ← Phase 1: generic intent for Ghost Executor
                )
                logger.info(
                    f"✅ IV-Switching unified signal: Mode={_mode} → {_order.get('signal_type')} | "
                    f"{len(_equity_legs)} equity legs + options_intent[type={_options_intent['type']}]"
                )

                # ── Trigger demo executor 15 min after signal ────────────────
                # Runs as a background process so it doesn't block the scheduler
                try:
                    import subprocess
                    subprocess.Popen(
                        ['python3', 'run_demo_executor.py'],
                        cwd=_os.path.dirname(_os.path.abspath(__file__)),
                    )
                    logger.info("🤖 Demo executor launched in background")
                except Exception as _demo_e:
                    logger.warning(f"Demo executor launch failed (non-fatal): {_demo_e}")

            else:
                logger.info(f"IV-Switching HOLD (Mode={_mode}): {_order.get('skip_reason', '')}")
        except Exception as _e:
            logger.error(f"❌ IV-Switching signal publish failed (non-fatal): {_e}",
                         exc_info=True)



    def run_loop(self):
        """Main execution loop for continuous running."""
        logger.info("Starting TurboCore Pro Background Daemon loop...")
        
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
    parser = argparse.ArgumentParser(description="TurboCore Pro ML Scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    args = parser.parse_args()
    
    scheduler = TurboCoreProScheduler()
    if args.once:
        scheduler.run_daily_scan()
    else:
        scheduler.run_loop()
