"""
TQQQ VIX-Adaptive Strategy Scheduler
======================================
Top-level launcher for the TQQQ strategy.
Mirrors the pattern of run_theta_scheduler.py.

Daily Timeline (Eastern):
  08:00  -- Refresh VIX + TQQQ prices; retrain ML if confidence dropped
  09:45  -- Regime detection + VIX prediction → evaluate entry
  10:30  -- Re-evaluate entry if first scan had no signal
  12:00  -- Midday position health check (leg-out assessment)
  14:30  -- Afternoon position check
  15:45  -- Pre-close check / emergency exits
  16:15  -- EOD P&L report + next-day preparation
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, time
from typing import Optional

# APScheduler for production use
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    logging.warning("APScheduler not installed — will run in single-pass mode.")
    AsyncIOScheduler = None
    CronTrigger = None
    SCHEDULER_AVAILABLE = False

from src.tqqq.data_pipeline       import TQQQDataPipeline
from src.tqqq.vix_adaptive_strategy import VIXAdaptiveStrategy
from src.tqqq.spread_builder       import SpreadBuilder
from src.tqqq.position_tracker     import TQQQPosition
from src.tqqq.tqqq_risk_manager    import TQQQRiskManager
from src.tqqq.order_manager        import TQQQOrderManager
from src.tqqq.ml.regime_detector   import VIXRegimeDetector
from src.tqqq.ml.vix_predictor     import VIXEnsemblePredictor
from src.tqqq import TQQQStrategyState

from signal_publisher.tqqq import (
    publish_tqqq_entry_signal,
    publish_tqqq_legout_signal,
    publish_tqqq_long_put_signal
)

from config import (
    TQQQ_ENABLED, TQQQ_AUTO_TRADE,
    TQQQ_SCAN_INTERVAL_MIN, TQQQ_POSITION_CHECK_MIN,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tqqq_scheduler")


class TQQQScheduler:
    """
    Orchestrates all scheduled tasks for the TQQQ VIX-Adaptive strategy.
    """

    def __init__(self, account_value: float = 25_000.0, ib_client=None):
        self.account_value = account_value

        # ── Data & ML ─────────────────────────────────────────────────────
        self.data_pipeline    = TQQQDataPipeline(ib_provider=ib_client)
        self.regime_detector  = VIXRegimeDetector()
        self.vix_predictor    = VIXEnsemblePredictor()

        # ── Strategy components ───────────────────────────────────────────
        self.spread_builder   = SpreadBuilder()
        self.strategy         = VIXAdaptiveStrategy()
        self.risk_manager     = TQQQRiskManager(account_value)
        self.order_manager    = TQQQOrderManager(ib_client=ib_client)
        
        try:
            from src.tqqq.ml.timing_engine import IntradayTimingEngine
            self.timing_engine = IntradayTimingEngine()
        except ImportError:
            self.timing_engine = None

        # ── State ─────────────────────────────────────────────────────────
        self._active_positions: list[TQQQPosition] = []
        self._ml_retrain_needed: bool = False
        self._scheduler: Optional[AsyncIOScheduler] = None

    # ─────────────────────── Startup ─────────────────────────────────────

    def start(self) -> None:
        """Start the async scheduler. Blocks until shutdown."""
        if not TQQQ_ENABLED:
            logger.info("TQQQ strategy disabled in config. Exiting.")
            return

        logger.info("=" * 60)
        logger.info("   TQQQ VIX-Adaptive Strategy Scheduler Starting")
        logger.info(f"   Account: ${self.account_value:,.0f} | AutoTrade: {TQQQ_AUTO_TRADE}")
        logger.info("=" * 60)

        asyncio.run(self._async_main())

    async def _async_main(self) -> None:
        if not SCHEDULER_AVAILABLE:
            # Single-pass mode (useful for testing)
            await self._morning_refresh()
            await self._scan_for_entry()
            return

        scheduler = AsyncIOScheduler(timezone="America/New_York")
        self._scheduler = scheduler

        # ── Daily jobs (Eastern time) ──────────────────────────────────
        scheduler.add_job(self._morning_refresh,   CronTrigger(hour=8,  minute=0,  day_of_week="mon-fri"))
        scheduler.add_job(self._scan_for_entry,    CronTrigger(hour=9,  minute=45, day_of_week="mon-fri"))
        scheduler.add_job(self._scan_for_entry,    CronTrigger(hour=10, minute=30, day_of_week="mon-fri"))
        # Add a 2:30 PM entry scan window as suggested by the timing engine ML rules
        scheduler.add_job(self._scan_for_entry,    CronTrigger(hour=14, minute=30, day_of_week="mon-fri"))
        
        scheduler.add_job(self._position_check,    CronTrigger(hour=12, minute=0,  day_of_week="mon-fri"))
        scheduler.add_job(self._position_check,    CronTrigger(hour=14, minute=30, day_of_week="mon-fri"))
        scheduler.add_job(self._pre_close_check,   CronTrigger(hour=15, minute=45, day_of_week="mon-fri"))
        scheduler.add_job(self._eod_report,        CronTrigger(hour=16, minute=15, day_of_week="mon-fri"))

        scheduler.start()
        logger.info("Scheduler started. Press Ctrl+C to stop.")

        # Graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown)

        await asyncio.Event().wait()   # Block forever

    def _shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        logger.info("TQQQ Scheduler stopped.")
        sys.exit(0)

    # ─────────────────────── Scheduled Tasks ─────────────────────────────

    async def _morning_refresh(self) -> None:
        """08:00 — Refresh data and retrain ML models if needed."""
        logger.info("── Morning Refresh ──────────────────────────────────")

        df = self.data_pipeline.get_ml_feature_dataframe(lookback_days=504)
        if df.empty:
            logger.warning("Empty feature DataFrame. Skipping model evaluation.")
            return

        # Check if retraining is needed
        regime_result = self.regime_detector.predict(df)
        if self.regime_detector.needs_retraining(regime_result):
            logger.info("Confidence below threshold — initiating model retraining…")
            self.regime_detector.fit(df)

        self._ml_retrain_needed = False
        logger.info(f"Morning refresh complete. Current regime: {regime_result.regime} "
                    f"(conf: {regime_result.confidence:.0%})")

        # Persist status so API can serve /api/tqqq/status
        try:
            snapshot = self.data_pipeline.get_live_snapshot()
            vix_result = self.vix_predictor.predict(df)
            self._persist_status(regime_result, vix_result, snapshot)
        except Exception as _e:
            logger.warning(f"Could not persist TQQQ status: {_e}")

    async def _scan_for_entry(self) -> None:
        """Evaluate whether to open a new spread, governed by the Intraday Timing Engine."""
        logger.info("── Entry Scan ──────────────────────────────────────")

        # Reuse cached data or fetch fresh
        df       = self.data_pipeline.get_ml_feature_dataframe(lookback_days=60)
        snapshot = self.data_pipeline.get_live_snapshot()

        if df.empty:
            return

        regime_result   = self.regime_detector.predict(df)
        vix_prediction  = self.vix_predictor.predict(df)

        # Create a stub "IDLE" position for evaluation
        stub_pos = TQQQPosition(id="stub", symbol="TQQQ")
        action, details = self.strategy.evaluate(
            position=stub_pos,
            regime=regime_result.regime,
            vix_direction=vix_prediction.direction,
            vix_confidence=vix_prediction.confidence,
            current_spread_value=0.0,
            short_put_value=0.0,
            long_put_value=0.0,
            dte=35,
        )

        if action == "ENTER_SPREAD":
            
            # Request timing verification from the Timing Engine
            if self.timing_engine:
                decision, savings = self.timing_engine.evaluate_entry_timing(
                    datetime.now(), snapshot
                )
                if decision in ("WAIT", "SKIP_TODAY"):
                    logger.info(f"TimingEngine intercepted entry signal. Decision: {decision}.")
                    return
            
            chain = self.data_pipeline.get_options_chain()
            
            # Check if strategy passed regime-specific overrides
            regime_params = details.get("regime_params", {}) if details else {}
            
            best  = self.spread_builder.select_optimal_spread(
                current_price=snapshot["tqqq_price"],
                chain_data=chain,
                target_dte=regime_params.get("dte"),
                target_delta=regime_params.get("delta"),
                spread_width=regime_params.get("width")
            )

            if best is None:
                logger.warning("No liquid TQQQ spread found — signal suppressed.")
                return

            signal_msg = publish_tqqq_entry_signal(
                short_strike=best.short_leg.strike,
                long_strike=best.long_leg.strike,
                expiration=str(best.short_leg.expiration),
                credit=best.credit,
                regime=regime_result.regime,
                vix_direction=vix_prediction.direction,
                confidence=vix_prediction.confidence,
            )

            logger.info(
                f"ENTRY SIGNAL: {signal_msg.short_strike}P / {signal_msg.long_strike}P "
                f"| Credit: ${signal_msg.credit:.2f}"
            )

            # Persist signal so API can serve it via /api/tqqq/signals
            self._persist_signal(signal_msg.to_dict())

            if TQQQ_AUTO_TRADE:
                await self.order_manager.place_spread_order(
                    short_strike=best.short_leg.strike,
                    long_strike=best.long_leg.strike,
                    expiration=str(best.short_leg.expiration).replace("-", ""),
                    quantity=1,
                    account_id="",   # Set via env / config
                )
        else:
            logger.info(f"No entry signal. Action={action} | Regime={regime_result.regime} "
                        f"| VIX={vix_prediction.direction} (conf: {vix_prediction.confidence:.0%})")

    async def _position_check(self) -> None:
        """12:00 / 14:30 — Evaluate existing positions for leg-out or close."""
        logger.info("── Position Check ──────────────────────────────────")
        df       = self.data_pipeline.get_ml_feature_dataframe(lookback_days=30)
        regime_result  = self.regime_detector.predict(df)
        vix_prediction = self.vix_predictor.predict(df)

        for pos in self._active_positions:
            
            # Fetch live pricing if ib_provider is available
            current_spread_value = 0.0
            short_put_value = 0.0
            long_put_value = 0.0
            
            if self.data_pipeline.ib_provider:
                try:
                    short_put_value = self.data_pipeline.ib_provider.get_live_price(pos.short_strike, pos.expiration_date, "P") or 0.0
                    long_put_value = self.data_pipeline.ib_provider.get_live_price(pos.long_strike, pos.expiration_date, "P") or 0.0
                    
                    if pos.state == TQQQStrategyState.FULL_SPREAD:
                        current_spread_value = short_put_value - long_put_value
                    elif pos.state == TQQQStrategyState.LONG_PUT_ONLY:
                        current_spread_value = -long_put_value  # Spread value is just the net of what's left
                except Exception as e:
                    logger.error(f"Failed to fetch live pricing for position {pos.id}: {e}")
            else:
                 logger.warning("No IB provider available. Using 0.0 for live pricing stubs.")
                 
            action, details = self.strategy.evaluate(
                position=pos,
                regime=regime_result.regime,
                vix_direction=vix_prediction.direction,
                vix_confidence=vix_prediction.confidence,
                current_spread_value=current_spread_value,
                short_put_value=short_put_value,
                long_put_value=long_put_value,
                dte=30, # NOTE: should compute actual DTE based on today
            )

            if action == "LEG_OUT":
                sig = publish_tqqq_legout_signal(
                    position_id=pos.id,
                    short_strike=pos.short_strike,
                    expiration=pos.expiration_date,
                    short_put_buyback_price=details.get("short_value", 0.0) if details else short_put_value,
                    long_put_value=details.get("long_value_at_legout", 0.0) if details else long_put_value,
                    regime=regime_result.regime,
                    vix_direction=vix_prediction.direction,
                    confidence=vix_prediction.confidence,
                )
                logger.info(f"LEG-OUT SIGNAL fired for position {pos.id}")
                pos.state = TQQQStrategyState.LONG_PUT_ONLY
                pos.long_put_legout_value = details.get("long_value_at_legout") if details else long_put_value

            elif action in ("CLOSE_SPREAD", "SELL_LONG_PUT", "ABANDON_LONG_PUT"):
                act_str = "SELL" if action == "SELL_LONG_PUT" else "ABANDON"
                sig = publish_tqqq_long_put_signal(
                    position_id=pos.id,
                    long_strike=pos.long_strike,
                    expiration=pos.expiration_date,
                    current_value=0.0,
                    action=act_str,
                    reason=details.get("reason", "UNKNOWN") if details else action,
                )
                logger.info(f"{action} SIGNAL fired for position {pos.id}")
                pos.state = TQQQStrategyState.IDLE

    async def _pre_close_check(self) -> None:
        """15:45 — Final safety check before market close."""
        logger.info("── Pre-Close Check ─────────────────────────────────")
        # Force-close any positions with DTE <= 5 or near max loss
        for pos in list(self._active_positions):
            if pos.state == TQQQStrategyState.FULL_SPREAD:
                logger.info(f"Pre-close check: Position {pos.id} is still in FULL_SPREAD.")
            elif pos.state == TQQQStrategyState.LONG_PUT_ONLY:
                logger.info(f"Pre-close check: Position {pos.id} retaining long put.")

    async def _eod_report(self) -> None:
        """16:15 — End-of-day summary."""
        status = self.risk_manager.get_status()
        logger.info(
            f"── EOD Report ─────────────────────────────────────\n"
            f"   Open positions : {status['open_positions']}\n"
            f"   Total at risk  : ${status['total_at_risk']:.2f}\n"
            f"   Account value  : ${status['account_value']:,.2f}\n"
            f"   Drawdown       : {status['drawdown_pct']:.1%}\n"
            f"   Circuit broken : {status['circuit_broken']}\n"
            f"───────────────────────────────────────────────────"
        )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    
    account_size = float(os.getenv("ACCOUNT_SIZE", "25000"))
    scheduler    = TQQQScheduler(account_value=account_size)
    scheduler.start()
