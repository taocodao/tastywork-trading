"""
TQQQ Unified 3-Layer Strategy Scheduler
=========================================
Orchestrates all three non-conflicting return layers:

  Layer 1: Theta income (put credit spreads + bear call credit spreads)
           Driven by VIX regime + ML direction prediction.
           Uses 70% capital pool (THETA pool).

  Layer 2: RSI swing overlay (put diagonal spreads)
           Driven by RSI-2 dip detection + CrashGuard score >= 55.
           Runs INDEPENDENTLY of Layer 1 — separate 30% capital pool (SWING pool).

  Layer 3: Dynamic sizing
           CrashGuard score (55-100) → 1.0x to 2.0x contract multiplier.
           Applied to Layer 2 swing diagonals at entry.

Daily Timeline (Eastern):
  08:00  -- Morning refresh: data + ML model evaluation
  09:45  -- Entry scan: theta signals + swing signals (first pass)
  10:30  -- Entry scan: second pass if first had no signal
  12:00  -- Midday position check: exit assessments for all positions
  14:30  -- Afternoon entry scan + position check
  15:45  -- Pre-close: 5% rally circuit breaker + emergency swing close
  16:15  -- EOD P&L report
"""

import asyncio
import logging
import signal
import sys
import uuid
from datetime import date, datetime, timedelta
from typing import Optional, List

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
from src.tqqq.crash_guard          import CrashGuard
from src.tqqq.swing_exit_engine    import SwingExitEngine, ExitDecisionType
from src.tqqq.ml.regime_detector   import VIXRegimeDetector
from src.tqqq.ml.vix_predictor     import VIXEnsemblePredictor
from src.tqqq import TQQQStrategyState

from signal_publisher.tqqq import (
    publish_tqqq_entry_signal,
    publish_tqqq_legout_signal,
    publish_tqqq_long_put_signal,
    publish_tqqq_call_entry_signal,
    publish_tqqq_call_close_signal,
    publish_tqqq_diagonal_entry_signal,
    publish_tqqq_diagonal_exit_signal,
    publish_tqqq_backspread_entry_signal,
)

from config import (
    TQQQ_ENABLED, TQQQ_AUTO_TRADE,
    TQQQ_SCAN_INTERVAL_MIN, TQQQ_POSITION_CHECK_MIN,
    TQQQ_COOLDOWN_DAYS, TQQQ_VIX_5D_MAX,
    TQQQ_CALL_PARAMS_BY_REGIME,
    TQQQ_CALL_RALLY_CIRCUIT_BREAKER_PCT,
    TQQQ_SWING_RSI_THRESHOLD, TQQQ_SWING_MIN_CRASH_GUARD,
    TQQQ_SWING_MAX_CONCURRENT, TQQQ_SWING_MAX_HOLD_DAYS,
    TQQQ_SWING_COOLDOWN_MIN,
    TQQQ_THETA_POOL_PCT, TQQQ_SWING_POOL_PCT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tqqq_scheduler")


class TQQQScheduler:
    """
    Orchestrates all scheduled tasks for the unified TQQQ 3-Layer strategy.

    Capital pools are strictly isolated:
      - THETA pool (70%): put credit spreads + bear call credit spreads
      - SWING pool (30%): RSI dip diagonal spreads with CrashGuard gating

    Layers never compete for the same capital budget.
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

        # Layer 2 / Layer 3 components
        self.crash_guard      = CrashGuard()
        self.swing_exit       = SwingExitEngine()

        try:
            from src.tqqq.ml.timing_engine import IntradayTimingEngine
            self.timing_engine = IntradayTimingEngine()
        except ImportError:
            self.timing_engine = None

        # ── State ─────────────────────────────────────────────────────────
        self._active_positions: List[TQQQPosition] = []
        self._ml_retrain_needed: bool = False
        self._scheduler: Optional[AsyncIOScheduler] = None

        # Theta cooldown state
        self._last_entry_date: Optional[date] = None
        self._last_entry_strikes: Optional[tuple] = None

        # Swing cooldown state (prevent rapid consecutive swing entries)
        self._last_swing_entry_time: dict = {"Deep": None, "Mod": None, "Light": None}

        # Load all DE parameters
        self.de_params_all = {}
        import os
        try:
            param_file = os.path.join(os.path.dirname(__file__), "src", "tqqq", "ml", "optimized_swing_params.json")
            if os.path.exists(param_file):
                import json
                with open(param_file, "r") as f:
                    self.de_params_all = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load optimized_swing_params.json: {e}")

    # ─────────────────────── Startup ─────────────────────────────────────

    def start(self) -> None:
        """Start the async scheduler. Blocks until shutdown."""
        if not TQQQ_ENABLED:
            logger.info("TQQQ strategy disabled in config. Exiting.")
            return

        logger.info("=" * 60)
        logger.info("   TQQQ Unified 3-Layer Strategy Scheduler Starting")
        logger.info(f"   Account: ${self.account_value:,.0f} | AutoTrade: {TQQQ_AUTO_TRADE}")
        logger.info(f"   Capital pools: Theta {TQQQ_THETA_POOL_PCT:.0%} / Swing {TQQQ_SWING_POOL_PCT:.0%}")
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
        """
        09:45 / 10:30 / 14:30 — Evaluate entry opportunities.

        Runs two independent layers:
          • LAYER 1: Theta credit spreads (put or call) driven by VIX regime
          • LAYER 2: Swing diagonal (RSI dip + CrashGuard) with Layer 3 sizing
        """
        logger.info("── Entry Scan ──────────────────────────────────────")

        df       = self.data_pipeline.get_ml_feature_dataframe(lookback_days=60)
        snapshot = self.data_pipeline.get_live_snapshot()

        if df.empty:
            return

        regime_result   = self.regime_detector.predict(df)
        vix_prediction  = self.vix_predictor.predict(df)

        # ── VIX 5-day gate ────────────────────────────────────────────────
        if "vix5d" in df.columns:
            vix5d_change = float(df["vix5d"].iloc[-1]) if not df["vix5d"].isna().iloc[-1] else 0.0
            if vix5d_change > TQQQ_VIX_5D_MAX:
                logger.info(
                    f"VIX 5-day filter: VIX rose {vix5d_change:.1f} pts (max {TQQQ_VIX_5D_MAX}). "
                    f"Skipping theta entry to avoid elevated vol."
                )
                # Swing can still run — CrashGuard provides independent gating
                await self._scan_swing_entry(df, snapshot, regime_result, vix_prediction)
                return

        # ── LAYER 1: Theta entry ──────────────────────────────────────────
        await self._scan_theta_entry(df, snapshot, regime_result, vix_prediction)

        # ── LAYER 2: Swing entry ─ runs independently ─────────────────────
        await self._scan_swing_entry(df, snapshot, regime_result, vix_prediction)

    # ─────────────────────── Layer 1: Theta Entry ────────────────────────

    async def _scan_theta_entry(self, df, snapshot, regime_result, vix_prediction) -> None:
        """Layer 1: Evaluate put credit spread or bear call credit spread entry."""

        # Cooldown gate for theta positions
        if self._last_entry_date is not None:
            days_since = (date.today() - self._last_entry_date).days
            if days_since < TQQQ_COOLDOWN_DAYS:
                logger.info(f"Theta cooldown: {days_since}/{TQQQ_COOLDOWN_DAYS} days. Skipping.")
                return

        # Timing engine gate (optional ML timing filter)
        if self.timing_engine:
            decision, _ = self.timing_engine.evaluate_entry_timing(datetime.now(), snapshot)
            if decision in ("WAIT", "SKIP_TODAY"):
                logger.info(f"TimingEngine: {decision}. Suppressing theta entry.")
                return

        # Get strategy evaluation
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
            await self._enter_put_spread(df, snapshot, regime_result, vix_prediction, details)
        elif action == "ENTER_CALL_SPREAD":
            await self._enter_call_spread(df, snapshot, regime_result, vix_prediction, details)
        else:
            logger.info(
                f"No theta entry. Action={action} | Regime={regime_result.regime} "
                f"| VIX={vix_prediction.direction} (conf: {vix_prediction.confidence:.0%})"
            )

    async def _enter_put_spread(self, df, snapshot, regime_result, vix_prediction, details) -> None:
        """Enter a TQQQ put credit spread (Layer 1 THETA pool)."""
        regime_params = details.get("regime_params", {}) if details else {}
        chain = self.data_pipeline.get_options_chain()

        best = self.spread_builder.select_optimal_spread(
            current_price=snapshot["tqqq_price"],
            chain_data=chain,
            target_dte=regime_params.get("dte"),
            target_delta=regime_params.get("delta"),
            spread_width=regime_params.get("width"),
            vix_prediction=vix_prediction,
        )

        if best is None:
            logger.warning("No liquid TQQQ put spread found — signal suppressed.")
            return

        # Intraday deduplication (prevent exact duplicate signals same day)
        current_strikes = (best.short_leg.strike, best.long_leg.strike)
        if self._last_entry_date == date.today() and self._last_entry_strikes == current_strikes:
            logger.info("Skipping exact duplicate put signal (same strikes) already generated today.")
            return

        # Theta pool budget check
        spread_max_loss = best.max_loss * 100  # per contract → per share notation
        buying_power = self.account_value * TQQQ_THETA_POOL_PCT
        risk_check = self.risk_manager.can_enter_theta_position(spread_max_loss, buying_power)
        if not risk_check:
            logger.warning(f"Theta pool budget check FAILED: {risk_check.reason}. Skipping put entry.")
            return

        expiry_str = str(best.short_leg.expiration)
        expiry_disp = best.short_leg.expiration.strftime("%b %d") if hasattr(best.short_leg.expiration, "strftime") else expiry_str

        signal_msg = publish_tqqq_entry_signal(
            short_strike=best.short_leg.strike,
            long_strike=best.long_leg.strike,
            expiration=expiry_str,
            credit=best.credit,
            regime=regime_result.regime,
            vix_direction=vix_prediction.direction,
            confidence=vix_prediction.confidence,
        )

        logger.info(
            f"THETA PUT ENTRY: {signal_msg.short_strike}P / {signal_msg.long_strike}P "
            f"| Credit: ${signal_msg.credit:.2f} | Regime: {regime_result.regime}"
        )

        signal_dict = signal_msg.to_dict()
        signal_dict.update({
            "spread_width":    round(abs(best.short_leg.strike - best.long_leg.strike), 2),
            "type":            "PUT_CREDIT",
            "pool":            "THETA",
            "expiry_display":  expiry_disp,
            "strikes_display": f"Sell ${best.short_leg.strike:g}P / Buy ${best.long_leg.strike:g}P",
        })
        self._persist_signal(signal_dict)
        self._last_entry_date = date.today()
        self._last_entry_strikes = current_strikes

        if TQQQ_AUTO_TRADE:
            # Register position so risk_manager knows we opened it
            max_loss_dollars = best.max_loss * 100
            self.risk_manager.on_position_opened(max_loss_dollars, pool="THETA")
            pos = TQQQPosition(
                id=signal_msg.id,
                symbol="TQQQ",
                state=TQQQStrategyState.FULL_SPREAD,
                spread_type="PUT",
                pool="THETA",
                short_strike=best.short_leg.strike,
                long_strike=best.long_leg.strike,
                expiration_date=expiry_str,
                original_credit=best.credit,
                max_loss=best.max_loss,
            )
            self._active_positions.append(pos)

    async def _enter_call_spread(self, df, snapshot, regime_result, vix_prediction, details) -> None:
        """Enter a TQQQ bear call credit spread (Layer 1 THETA pool, HIGH_VOL/CRISIS only)."""
        regime_str = regime_result.regime if hasattr(regime_result, "regime") else str(regime_result.regime)

        # Call spreads only in HIGH_VOL / CRISIS
        call_params = TQQQ_CALL_PARAMS_BY_REGIME.get(regime_str)
        if call_params is None:
            logger.info(f"Call spread skipped: regime {regime_str} not in call spread params.")
            return

        # Fetch call options chain
        chain = self.data_pipeline.get_options_chain(right="C")

        best = self.spread_builder.select_optimal_call_spread(
            current_price=snapshot["tqqq_price"],
            chain_data=chain,
            target_dte=call_params.get("dte"),
            target_delta=call_params.get("delta"),
            spread_width=call_params.get("width"),
        )

        if best is None:
            logger.warning(f"No liquid TQQQ call spread found for {regime_str} regime — signal suppressed.")
            return

        # Theta pool budget check
        spread_max_loss = best.max_loss * 100
        buying_power = self.account_value * TQQQ_THETA_POOL_PCT
        risk_check = self.risk_manager.can_enter_theta_position(spread_max_loss, buying_power)
        if not risk_check:
            logger.warning(f"Theta pool budget check FAILED for call spread: {risk_check.reason}. Skipping.")
            return

        tqqq_price = snapshot["tqqq_price"]
        expiry_str = str(best.short_leg.expiration)
        expiry_disp = best.short_leg.expiration.strftime("%b %d") if hasattr(best.short_leg.expiration, "strftime") else expiry_str

        signal_msg = publish_tqqq_call_entry_signal(
            short_call_strike=best.short_leg.strike,
            long_call_strike=best.long_leg.strike,
            expiration=expiry_str,
            credit=best.credit,
            regime=regime_str,
            vix_direction=vix_prediction.direction,
            confidence=vix_prediction.confidence,
            tqqq_entry_price=tqqq_price,
        )

        logger.info(
            f"THETA CALL ENTRY: {signal_msg.short_call_strike}C / {signal_msg.long_call_strike}C "
            f"| Credit: ${signal_msg.credit:.2f} | Regime: {regime_str}"
        )

        signal_dict = signal_msg.to_dict()
        signal_dict.update({
            "spread_width":    round(abs(best.short_leg.strike - best.long_leg.strike), 2),
            "type":            "BEAR_CALL",
            "pool":            "THETA",
            "expiry_display":  expiry_disp,
            "strikes_display": f"Sell ${best.short_leg.strike:g}C / Buy ${best.long_leg.strike:g}C",
        })
        self._persist_signal(signal_dict)
        self._last_entry_date = date.today()
        self._last_entry_strikes = (best.short_leg.strike, best.long_leg.strike)

        if TQQQ_AUTO_TRADE:
            max_loss_dollars = best.max_loss * 100
            self.risk_manager.on_position_opened(max_loss_dollars, pool="THETA")
            pos = TQQQPosition(
                id=signal_msg.id,
                symbol="TQQQ",
                state=TQQQStrategyState.FULL_CALL_SPREAD,
                spread_type="CALL",
                pool="THETA",
                short_call_strike=best.short_leg.strike,
                long_call_strike=best.long_leg.strike,
                expiration_date=expiry_str,
                tqqq_entry_price=tqqq_price,
                original_credit=best.credit,
                max_loss=best.max_loss,
            )
            self._active_positions.append(pos)

    # ─────────────────────── Layer 2: Swing Entry ────────────────────────

    async def _scan_swing_entry(self, df, snapshot, regime_result, vix_prediction) -> None:
        """
        Layer 2: Multi-threshold RSI-2 dip detection → put diagonal / backspread, gated by CrashGuard & Hurst.
        Layer 3: CrashGuard score drives 1.0x – 2.0x quantity multiplier.
        """
        from config import TQQQ_SWING_THRESHOLDS, TQQQ_HURST_GATE, TQQQ_RISK_LEVEL, TQQQ_SWING_MAX_CONCURRENT, TQQQ_SWING_COOLDOWN_MIN

        # --- Swing pool capacity check ---
        active_swing = [p for p in self._active_positions if p.pool == "SWING"]
        if len(active_swing) >= TQQQ_SWING_MAX_CONCURRENT:
            logger.info(f"Swing pool full ({len(active_swing)}/{TQQQ_SWING_MAX_CONCURRENT}). Skipping swing scan.")
            return

        # --- Hurst Exponent gate ---
        hurst_60 = None
        if "hurst_60" in df.columns and not df["hurst_60"].isna().iloc[-1]:
            hurst_60 = float(df["hurst_60"].iloc[-1])
        elif "hurst_60" in snapshot:
            hurst_60 = float(snapshot["hurst_60"])

        if hurst_60 is not None and hurst_60 >= TQQQ_HURST_GATE:
            logger.info(f"Swing scan: Hurst {hurst_60:.2f} >= {TQQQ_HURST_GATE} (trend too strong).")
            return

        # --- Base RSI & Data prep ---
        rsi_2 = None
        if "rsi_2" in df.columns and not df["rsi_2"].isna().iloc[-1]:
            rsi_2 = float(df["rsi_2"].iloc[-1])
        elif "rsi_2" in snapshot:
            rsi_2 = float(snapshot["rsi_2"])

        if rsi_2 is None:
            logger.warning("Swing scan: RSI-2 not available. Skipping swing entry.")
            return

        import pandas as pd
        intraday_row = pd.Series({
            "close":     snapshot.get("tqqq_price", 0),
            "rsi_2":     rsi_2,
            "vol_ratio": snapshot.get("vol_ratio", 1.0),
        })

        ml_prob = vix_prediction.confidence if vix_prediction.direction in ("VIX_FALLING", "FALLING") else 0.5
        crash_result = self.crash_guard.evaluate_entry(df, intraday_row, ml_prob)

        if not crash_result.passed:
            logger.info(f"Swing scan: CrashGuard BLOCKED. Score={crash_result.score}")
            return

        swing_budget = self.account_value * TQQQ_SWING_POOL_PCT
        chain = self.data_pipeline.get_options_chain()

        # Multi-threshold evaluation
        for tranche_name, config_dict in TQQQ_SWING_THRESHOLDS.items():
            rsi_thresh = config_dict["rsi"]
            if rsi_2 >= rsi_thresh:
                continue

            last_entry = self._last_swing_entry_time.get(tranche_name)
            if last_entry is not None:
                mins_since = (datetime.now() - last_entry).total_seconds() / 60
                if mins_since < TQQQ_SWING_COOLDOWN_MIN:
                    continue
                    
            logger.info(f"Swing scan: CrashGuard PASSED. Tranche={tranche_name} | RSI-2={rsi_2:.1f} < {rsi_thresh}")

            for risk_level, params_for_risk in self.de_params_all.items():
                tranche_params = params_for_risk.get(tranche_name, {})
                if not tranche_params: continue

                if risk_level == TQQQ_RISK_LEVEL:
                    risk_check = self.risk_manager.can_enter_swing_position(new_max_loss=0, current_buying_power=swing_budget)
                    if not risk_check: continue

                max_risk_est = 0.0
                credit_est = 0.0
                signal_msg = None
                exp1, exp2 = "", ""

                if tranche_name == "Deep":
                    spread = self.spread_builder.select_optimal_backspread(
                        current_price=snapshot["tqqq_price"],
                        chain_data=chain,
                        anchor_dte=tranche_params.get("anchor_dte", 55),
                        hedge_dte=tranche_params.get("hedge_dte", 12),
                        anchor_k_pct=tranche_params.get("anchor_k_pct", 0.04),
                        hedge_k_pct=tranche_params.get("hedge_k_pct", 0.08)
                    )
                    if not spread: continue
                    max_risk_est = spread.max_risk_estimate
                    credit_est = -spread.net_cost
                    
                    # Prevent division by zero if max_risk_est == 0
                    base_contracts = self.risk_manager.calculate_contracts(1.0 if max_risk_est == 0 else max_risk_est, credit_est) 
                    quantity = max(1, round(base_contracts * crash_result.multiplier))
                    
                    signal_msg = publish_tqqq_backspread_entry_signal(
                        short_strike=spread.short_leg.strike, long_strike=spread.long_leg.strike,
                        expiration=str(spread.short_leg.expiration), net_cost=spread.net_cost,
                        rsi_2=rsi_2, ml_prob=ml_prob, regime_score=crash_result.score, quantity=quantity, risk_level=risk_level
                    )
                    
                    short_s = spread.short_leg.strike
                    hedge_s = spread.long_leg.strike
                    exp1 = str(spread.short_leg.expiration)
                    exp2 = exp1
                    spread_type = "BACKSPREAD"

                else:
                    spread = self.spread_builder.select_optimal_diagonal(
                        current_price=snapshot["tqqq_price"],
                        chain_data=chain,
                        anchor_dte=tranche_params.get("anchor_dte", 30),
                        hedge_dte=tranche_params.get("hedge_dte", 10),
                        anchor_k_pct=tranche_params.get("anchor_k_pct", 0.04),
                        hedge_k_pct=tranche_params.get("hedge_k_pct", 0.08)
                    )
                    if not spread: continue
                    max_risk_est = spread.max_risk_estimate
                    credit_est = spread.net_credit
                    
                    base_contracts = self.risk_manager.calculate_contracts(max_risk_est, credit_est)
                    quantity = max(1, round(base_contracts * crash_result.multiplier))
                    
                    signal_msg = publish_tqqq_diagonal_entry_signal(
                        anchor_strike=spread.anchor_leg.strike, anchor_expiration=str(spread.anchor_leg.expiration),
                        hedge_strike=spread.hedge_leg.strike, hedge_expiration=str(spread.hedge_leg.expiration),
                        net_credit=spread.net_credit,
                        rsi_2=rsi_2, ml_prob=ml_prob, regime_score=crash_result.score, quantity=quantity, risk_level=risk_level
                    )

                    short_s = spread.anchor_leg.strike
                    hedge_s = spread.hedge_leg.strike
                    exp1 = str(spread.anchor_leg.expiration)
                    exp2 = str(spread.hedge_leg.expiration)
                    spread_type = "DIAGONAL"
                    
                # Store signal
                signal_dict = signal_msg.to_dict()
                signal_dict.update({
                    "type":             f"{spread_type}_SWING",
                    "pool":             "SWING",
                    "crash_guard_score": crash_result.score,
                    "layer3_multiplier": crash_result.multiplier,
                    "strikes_display":  f"Anchor ${short_s:g} / Hedge ${hedge_s:g}",
                })
                self._persist_signal(signal_dict)
                
                # Active trade happens only for the configured risk level
                if risk_level == TQQQ_RISK_LEVEL and TQQQ_AUTO_TRADE:
                    max_loss_dollars = max_risk_est * 100 * quantity
                    self.risk_manager.on_position_opened(max_loss_dollars, pool="SWING")
                    
                    pos = TQQQPosition(
                        id=signal_msg.id,
                        symbol="TQQQ",
                        state=TQQQStrategyState.DIAGONAL_OPEN, # Treat backspread logic similarly to diagonal for position management
                        spread_type=spread_type,
                        pool="SWING",
                        anchor_strike=short_s,
                        anchor_expiration=exp1,
                        hedge_strike=hedge_s,
                        hedge_expiration=exp2,
                        entry_price=snapshot["tqqq_price"],
                        crash_guard_score=crash_result.score,
                        quantity=quantity,
                        original_credit=credit_est,
                        max_loss=max_risk_est,
                        tranche=tranche_name,
                    )
                    self._active_positions.append(pos)
                    self._last_swing_entry_time[tranche_name] = datetime.now()

    # ─────────────────────── Position Check ──────────────────────────────

    async def _position_check(self) -> None:
        """
        12:00 / 14:30 — Evaluate all existing positions for exit or management.

        THETA positions: use VIX strategy evaluate() (profit target / stop loss / leg-out)
        SWING positions: use SwingExitEngine cascade (RSI bounce / emergency / theta kicker)
        """
        logger.info("── Position Check ──────────────────────────────────")
        if not self._active_positions:
            logger.info("No active positions to check.")
            return

        df            = self.data_pipeline.get_ml_feature_dataframe(lookback_days=30)
        snapshot      = self.data_pipeline.get_live_snapshot()
        regime_result = self.regime_detector.predict(df)
        vix_prediction = self.vix_predictor.predict(df)

        current_price = snapshot.get("tqqq_price", 0.0)
        rsi_2 = float(df["rsi_2"].iloc[-1]) if "rsi_2" in df.columns and not df["rsi_2"].isna().iloc[-1] else 50.0
        sma_5 = float(df["sma_5"].iloc[-1]) if "sma_5" in df.columns and not df["sma_5"].isna().iloc[-1] else current_price
        ml_prob = vix_prediction.confidence if vix_prediction.direction in ("VIX_FALLING", "FALLING") else 0.5

        for pos in list(self._active_positions):
            if pos.pool == "THETA":
                await self._check_theta_position(pos, df, snapshot, regime_result, vix_prediction)
            elif pos.pool == "SWING" and pos.state == TQQQStrategyState.DIAGONAL_OPEN:
                await self._check_swing_position(pos, current_price, rsi_2, sma_5, ml_prob)

    async def _check_theta_position(self, pos: TQQQPosition, df, snapshot, regime_result, vix_prediction) -> None:
        """Evaluate a theta (put or call credit spread) position."""
        current_spread_value = 0.0
        short_put_value      = 0.0
        long_put_value       = 0.0

        if self.data_pipeline.ib_provider:
            try:
                right = "C" if pos.spread_type == "CALL" else "P"
                short_strike = pos.short_call_strike if pos.spread_type == "CALL" else pos.short_strike
                long_strike  = pos.long_call_strike  if pos.spread_type == "CALL" else pos.long_strike

                short_val = self.data_pipeline.ib_provider.get_live_price(short_strike, pos.expiration_date, right) or 0.0
                long_val  = self.data_pipeline.ib_provider.get_live_price(long_strike,  pos.expiration_date, right) or 0.0

                if pos.state in (TQQQStrategyState.FULL_SPREAD, TQQQStrategyState.FULL_CALL_SPREAD):
                    current_spread_value = short_val - long_val
                elif pos.state in (TQQQStrategyState.LONG_PUT_ONLY, TQQQStrategyState.LONG_CALL_ONLY):
                    current_spread_value = long_val

                short_put_value = short_val
                long_put_value  = long_val
            except Exception as e:
                logger.error(f"Live pricing error for {pos.id}: {e}")
        else:
            logger.warning("No IB provider — using 0.0 for live pricing.")

        action, details = self.strategy.evaluate(
            position=pos,
            regime=regime_result.regime,
            vix_direction=vix_prediction.direction,
            vix_confidence=vix_prediction.confidence,
            current_spread_value=current_spread_value,
            short_put_value=short_put_value,
            long_put_value=long_put_value,
            dte=30,  # TODO: compute actual DTE from pos.expiration_date
        )

        if pos.spread_type == "CALL" and action in ("CLOSE_SPREAD",):
            # Close bear call spread
            pnl = (pos.original_credit - current_spread_value) * 100 * pos.quantity
            sig = publish_tqqq_call_close_signal(
                position_id=pos.id,
                reason=details.get("reason", "PROFIT_TARGET") if details else "PROFIT_TARGET",
                pnl=pnl,
            )
            logger.info(f"CALL SPREAD CLOSE: pos {pos.id[:8]} | P&L: ${pnl:.0f} | {sig.reason}")
            self._finalize_position(pos)

        elif action == "LEG_OUT" and pos.spread_type == "PUT":
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
            logger.info(f"LEG-OUT SIGNAL: pos {pos.id[:8]}")
            pos.state = TQQQStrategyState.LONG_PUT_ONLY
            pos.long_put_legout_value = details.get("long_value_at_legout") if details else long_put_value

        elif action in ("CLOSE_SPREAD", "SELL_LONG_PUT", "ABANDON_LONG_PUT"):
            act_str = "SELL" if action == "SELL_LONG_PUT" else "ABANDON"
            sig = publish_tqqq_long_put_signal(
                position_id=pos.id,
                long_strike=pos.long_strike,
                expiration=pos.expiration_date,
                current_value=long_put_value,
                action=act_str,
                reason=details.get("reason", action) if details else action,
            )
            logger.info(f"{action} SIGNAL: pos {pos.id[:8]}")
            self._finalize_position(pos)

    async def _check_swing_position(self, pos: TQQQPosition, current_price: float,
                                     rsi_2: float, sma_5: float, ml_prob: float) -> None:
        """Evaluate a swing (diagonal or backspread) position using SwingExitEngine."""
        days_held = (date.today() - self._position_entry_date(pos)).days

        # Load DE params based on stored tranche
        from config import TQQQ_RISK_LEVEL
        exit_rsi = 65.0
        time_stop_days = TQQQ_SWING_MAX_HOLD_DAYS
        de_params = self.de_params_all.get(TQQQ_RISK_LEVEL, {}).get(pos.tranche, {})
        if de_params:
            exit_rsi = de_params.get("exit_rsi", exit_rsi)
            time_stop_days = de_params.get("time_stop", time_stop_days)
            
        # Get live spread mark for Priority 0: BP-based stop loss
        current_spread_mark = 0.0
        if self.data_pipeline.ib_provider and pos.anchor_expiration:
            try:
                right = "C" if pos.spread_type == "BACKSPREAD" else "P"
                short_val = self.data_pipeline.ib_provider.get_live_price(pos.anchor_strike, pos.anchor_expiration, right) or 0.0
                long_val = self.data_pipeline.ib_provider.get_live_price(pos.hedge_strike, pos.hedge_expiration, right) or 0.0
                
                if pos.spread_type == "BACKSPREAD":
                    # For backspreads we sold 1, bought 2. We pay short - 2*long to close
                    current_spread_mark = short_val - 2 * long_val
                else: 
                    # For diagonals we sold 1, bought 1. We pay short - long to close
                    current_spread_mark = short_val - long_val
            except Exception as e:
                logger.error(f"Live pricing error for swing pos {pos.id}: {e}")

        # Force close if held beyond DE-optimized time stop
        if days_held >= time_stop_days:
            sig = publish_tqqq_diagonal_exit_signal(
                position_id=pos.id,
                action="CLOSE_ALL",
                reason=f"MAX_HOLD: {days_held} days >= {time_stop_days}",
                pnl=0.0,
                days_held=days_held,
                roll_count=pos.roll_count,
                risk_level=TQQQ_RISK_LEVEL,
            )
            logger.info(f"SWING TIME STOP EXIT: pos {pos.id[:8]} day {days_held}")
            self._finalize_position(pos)
            return

        exit_decision = self.swing_exit.evaluate(
            position=pos,
            current_price=current_price,
            rsi_2=rsi_2,
            sma_5=sma_5,
            regime_score=pos.crash_guard_score,
            ml_prob=ml_prob,
            days_held=days_held,
            current_spread_mark=current_spread_mark,
            bp_consumed=pos.max_loss * 100 * pos.quantity,
            exit_rsi=exit_rsi,
            time_stop_days=time_stop_days,
        )

        if exit_decision.decision == ExitDecisionType.CLOSE_ALL:
            pnl = (current_price - pos.entry_price) / pos.entry_price * 100 if pos.entry_price > 0 else 0.0
            sig = publish_tqqq_diagonal_exit_signal(
                position_id=pos.id,
                action="CLOSE_ALL",
                reason=exit_decision.reason,
                pnl=pnl,
                days_held=days_held,
                roll_count=pos.roll_count,
                risk_level=TQQQ_RISK_LEVEL,
            )
            logger.info(
                f"SWING CLOSE: pos {pos.id[:8]} | {exit_decision.reason} "
                f"| Days: {days_held} | P&L≈{pnl:+.1f}%"
            )
            self._finalize_position(pos)

        elif exit_decision.decision == ExitDecisionType.ROLL_HEDGE:
            pos.roll_count += 1
            sig = publish_tqqq_diagonal_exit_signal(
                position_id=pos.id,
                action="ROLL_HEDGE",
                reason=exit_decision.reason,
                pnl=0.0,
                days_held=days_held,
                roll_count=pos.roll_count,
                risk_level=TQQQ_RISK_LEVEL,
            )
            logger.info(f"SWING ROLL HEDGE (theta kicker): pos {pos.id[:8]} | Roll #{pos.roll_count}")

        # ExitDecisionType.HOLD → do nothing
        else:
            logger.debug(f"Swing pos {pos.id[:8]} HOLD | days={days_held} | rsi2={rsi_2:.1f}")

    # ─────────────────────── Pre-Close Check ─────────────────────────────

    async def _pre_close_check(self) -> None:
        """
        15:45 — Final safety checks:
          1. 5% rally circuit breaker on ALL open call spreads.
          2. Emergency close on ALL swing positions if daily drop > 10%.
        """
        logger.info("── Pre-Close Check ─────────────────────────────────")
        snapshot = self.data_pipeline.get_live_snapshot()
        current_price = snapshot.get("tqqq_price", 0.0)

        for pos in list(self._active_positions):

            # ── Call spread rally circuit breaker ──────────────────────
            if pos.spread_type == "CALL" and pos.state == TQQQStrategyState.FULL_CALL_SPREAD:
                if pos.tqqq_entry_price > 0:
                    rally_pct = (current_price - pos.tqqq_entry_price) / pos.tqqq_entry_price
                    if rally_pct >= TQQQ_CALL_RALLY_CIRCUIT_BREAKER_PCT:
                        pnl = (pos.original_credit - 0.0) * 100 * pos.quantity  # mark-to-market placeholder
                        sig = publish_tqqq_call_close_signal(
                            position_id=pos.id,
                            reason=f"RALLY_CIRCUIT_BREAKER: +{rally_pct:.1%} from entry",
                            pnl=pnl,
                        )
                        logger.warning(
                            f"CALL CIRCUIT BREAKER TRIGGERED: pos {pos.id[:8]} "
                            f"| TQQQ rallied +{rally_pct:.1%} from ${pos.tqqq_entry_price:.2f}"
                        )
                        self._finalize_position(pos)
                        continue

            # ── Swing emergency exit on severe TQQQ drop ───────────────
            if pos.pool == "SWING" and pos.state == TQQQStrategyState.DIAGONAL_OPEN:
                if pos.entry_price > 0:
                    drop_pct = (current_price - pos.entry_price) / pos.entry_price
                    if drop_pct <= -0.10:
                        days_held = (date.today() - self._position_entry_date(pos)).days
                        sig = publish_tqqq_diagonal_exit_signal(
                            position_id=pos.id,
                            action="CLOSE_ALL",
                            reason=f"EMERGENCY_DROP: {drop_pct:.1%} from entry",
                            pnl=drop_pct * 100,
                            days_held=days_held,
                            roll_count=pos.roll_count,
                        )
                        logger.warning(
                            f"SWING EMERGENCY EXIT: pos {pos.id[:8]} "
                            f"| TQQQ dropped {drop_pct:.1%} from ${pos.entry_price:.2f}"
                        )
                        self._finalize_position(pos)

            # Log status of positions not needing action
            elif pos.spread_type == "PUT":
                logger.info(f"Pre-close: PUT pos {pos.id[:8]} state={pos.state.name} — no action.")

    # ─────────────────────── EOD Report ──────────────────────────────────

    async def _eod_report(self) -> None:
        """16:15 — End-of-day summary covering all three layers."""
        status = self.risk_manager.get_status()

        theta_positions = [p for p in self._active_positions if p.pool == "THETA"]
        swing_positions = [p for p in self._active_positions if p.pool == "SWING"]

        logger.info(
            f"── EOD Report ─────────────────────────────────────\n"
            f"   Theta positions    : {len(theta_positions)}\n"
            f"   Swing positions    : {len(swing_positions)}\n"
            f"   Total at risk      : ${status['total_at_risk']:.2f}\n"
            f"   Account value      : ${status['account_value']:,.2f}\n"
            f"   Drawdown           : {status['drawdown_pct']:.1%}\n"
            f"   Circuit broken     : {status['circuit_broken']}\n"
            f"───────────────────────────────────────────────────"
        )

    # ─────────────────────── Helpers ─────────────────────────────────────

    def _finalize_position(self, pos: TQQQPosition) -> None:
        """Mark a position as closed and remove from active pool."""
        self.risk_manager.on_position_closed(pos.max_loss * 100 * pos.quantity, pool=pos.pool)
        pos.state = TQQQStrategyState.IDLE
        if pos in self._active_positions:
            self._active_positions.remove(pos)

    def _position_entry_date(self, pos: TQQQPosition) -> date:
        """
        Best-effort attempt to get the entry date of a position.
        Falls back to today if no date is recorded.
        """
        # For diagonal positions, entry_price was set at entry time.
        # We don't store a datetime in TQQQPosition yet, so we use today as fallback.
        # TODO: add entry_date: date field to TQQQPosition for accurate hold-day tracking.
        return date.today()

    def _persist_status(self, regime_result, vix_result, snapshot) -> None:
        """Write current VIX regime and TQQQ price to tqqq_status.json."""
        import json, os
        regime_str = regime_result.regime if isinstance(regime_result.regime, str) else regime_result.regime.value
        status = {
            'regime':            regime_str,
            'can_trade':         regime_str != 'CRISIS',
            'vix':               snapshot.get('vix', 0),
            'vix_direction':     vix_result.direction,
            'tqqq_price':        snapshot.get('tqqq_price', 0),
            'position_multiplier': 1.0,
            'early_warning':     regime_str == 'HIGH_VOL',
            'message':           (
                f'{regime_str} regime | VIX {vix_result.direction} '
                f'(conf: {vix_result.confidence:.0%})'
            ),
            'timestamp':         datetime.now().isoformat(),
        }
        path = os.path.expanduser('~/tastywork-trading/tqqq_status.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            import json
            json.dump(status, f, indent=2)
        logger.info(f"Persisted TQQQ status: regime={status['regime']}")

    def _persist_signal(self, signal_dict: dict) -> None:
        """Append a new signal to tqqq_signals.json."""
        import json, os

        # Frontend-compatible field aliases
        signal_dict.setdefault('strikes',     signal_dict.get('strikes_display', ''))
        signal_dict.setdefault('expiry',      signal_dict.get('expiry_display', ''))
        signal_dict.setdefault('createdAt',   signal_dict.get('created_at', ''))
        signal_dict.setdefault('vixDirection', signal_dict.get('vix_direction', 'STABLE'))
        signal_dict.setdefault('vixLevel',    signal_dict.get('metadata', {}).get('vix', 0))

        # confidence: 0.0–1.0 → 0–100
        raw_conf = signal_dict.get('confidence', 0)
        if isinstance(raw_conf, float) and raw_conf <= 1.0:
            signal_dict['confidence'] = round(raw_conf * 100)

        # maxLoss = spread_width - credit
        sw = signal_dict.get('spread_width', 5.0)
        cr = signal_dict.get('credit', signal_dict.get('net_credit', 0))
        signal_dict.setdefault('maxLoss', round(sw - cr, 2))

        path = os.path.expanduser('~/tastywork-trading/tqqq_signals.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        signals = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    signals = json.load(f)
            except Exception:
                pass
        signals.append(signal_dict)
        with open(path, 'w') as f:
            json.dump(signals, f, indent=2)
        logger.info(f"Persisted TQQQ signal: {signal_dict.get('id', 'unknown')[:8]}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    account_size = float(os.getenv("ACCOUNT_SIZE", "25000"))
    scheduler    = TQQQScheduler(account_value=account_size)
    scheduler.start()
