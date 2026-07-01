"""
OTM Naked Options — Backtest Engine
======================================
Walk-forward backtest using Black-Scholes synthetic option pricing.
No historical options data required — all Greeks computed analytically.

Architecture:
  For each trading day:
    1. Build feature matrix (feature_engineering.py)
    2. Run signal engine  (signal_engine.py)
    3. ML classifier gate (entry_classifier.py) — trained on rolling window
    4. Strike selection   (strike_selector.py)  — BS delta targeting
    5. Risk check         (risk_manager.py)
    6. Simulate fill at BS mid
    7. Monitor open positions daily (stop-loss, profit-take, time exit)
    8. Record P&L, win/loss labels for next ML retraining window

Performance metrics reported: CAGR, Sharpe, Max Drawdown, Win Rate,
Profit Factor, Average DTE at close, Average credit/loss per trade.
"""
import logging
import math
import warnings
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import OTMNakedConfig
from .feature_engineering import build_all_features
from .signal_engine import OTMSignalEngine, SignalType
from .entry_classifier import OTMNakedEntryClassifier
from .strike_selector import OTMStrikeSelector, bs_put_price, bs_call_price, bs_all_greeks
from .risk_manager import OTMNakedRiskManager
from .stop_manager import SpreadAwareStopManager, StopState, compute_stop_from_row
from .earnings_overlay import EarningsICOverlay

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------
@dataclass
class NakedPosition:
    symbol:       str
    option_type:  str           # "put" or "call"
    strike:       float
    entry_date:   pd.Timestamp
    expiry_date:  pd.Timestamp
    entry_premium: float        # Credit collected per share
    entry_spot:   float
    entry_sigma:  float
    contracts:    int
    regime:       str
    ml_confidence: float
    notional_risk: float        # strike * contracts * 100
    # Filled during lifecycle
    exit_date:     Optional[pd.Timestamp] = None
    exit_premium:  float = 0.0
    exit_reason:   str   = ""
    pnl:           float = 0.0
    trade_won:     bool  = False
    stop_state:    Optional[object] = field(default=None, repr=False)  # StopState
    strangle_id:   Optional[str]   = None   # Non-None -> this leg is part of a strangle pair
    is_strangle_call: bool = False          # True = call leg; False = put leg (or solo put)
    pathway:       str   = "A"             # "A" = HILO signal; "B" = VIX-conditional (Phase 2)


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------
class OTMNakedBacktestEngine:
    """
    Walk-forward backtest for the OTM Naked Options Selling strategy.

    Usage:
        engine = OTMNakedBacktestEngine(config)
        results = engine.run(price_data, vix, vix3m, rf)
        engine.print_summary(results)
    """

    def __init__(self, config: Optional[OTMNakedConfig] = None):
        self.config      = config or OTMNakedConfig()
        self.signal_eng  = OTMSignalEngine(self.config)
        self.strike_sel  = OTMStrikeSelector(self.config)
        self.stop_mgr    = SpreadAwareStopManager(
            base_stop_mult    = self.config.stop_loss_credit_mult,
            high_vol_mult     = self.config.stop_loss_hv_mult,
            low_vol_mult      = self.config.stop_loss_lv_mult,
            iv_rank_scale     = self.config.stop_iv_rank_scale,
            trail_trigger_pct = self.config.stop_trail_trigger_pct,
            trail_step_pct    = self.config.stop_trail_step_pct,
            spread_buffer_mult= self.config.stop_spread_buffer_mult,
            check_interval    = self.config.stop_check_interval,
            check_dte_urgent  = self.config.stop_check_dte_urgent,
            check_move_pct    = self.config.stop_check_move_pct,
        )
        self.classifier  = OTMNakedEntryClassifier()

    # ── Main entry point ──────────────────────────────────────────────────────
    def run(
        self,
        price_data: Dict[str, pd.DataFrame],  # {symbol: OHLCV DataFrame}
        vix:        pd.Series,
        vix3m:      Optional[pd.Series] = None,
        rf:         Optional[pd.Series] = None,
        initial_capital: float = 50_000.0,
        use_ml: bool = True,
    ) -> dict:
        """
        Run the full walk-forward backtest.

        Args:
            price_data:      {symbol: DataFrame with Close/High/Low/Volume}
            vix:             VIX close prices
            vix3m:           VIX3M close prices (optional)
            rf:              Risk-free rate series (optional)
            initial_capital: Starting capital
            use_ml:          Enable XGBoost classifier gate

        Returns:
            results dict with equity_curve, trades, metrics
        """
        cfg = self.config
        logger.info("=" * 60)
        logger.info("OTM Naked Options — Walk-Forward Backtest")
        logger.info(f"  Capital: ${initial_capital:,.0f} | Period: {cfg.backtest_start} to {cfg.backtest_end}")
        logger.info(f"  Universe: {len(price_data)} symbols | ML: {use_ml}")
        logger.info("=" * 60)

        # Build feature matrices for all symbols
        logger.info("Building feature matrices...")
        features = build_all_features(price_data, vix, vix3m, rf)
        if not features:
            raise ValueError("No valid feature matrices built. Check data.")

        # Align all features to common trading dates
        all_dates = sorted(set.union(
            *[set(df.index) for df in features.values()]
        ))
        start_ts = pd.Timestamp(cfg.backtest_start)
        end_ts   = pd.Timestamp(cfg.backtest_end)
        trading_days = [d for d in all_dates if start_ts <= d <= end_ts]

        if use_ml and len(trading_days) < cfg.train_window_days + 30:
            raise ValueError(f"Insufficient trading days for ML training: {len(trading_days)}")
        elif not use_ml and len(trading_days) < 30:
            raise ValueError(f"Insufficient trading days: {len(trading_days)}")

        logger.info(f"Simulation: {len(trading_days)} trading days across {len(features)} symbols")

        # ── Walk-forward state ────────────────────────────────────────────────
        cash           = initial_capital
        open_positions: List[NakedPosition] = []
        closed_trades:  List[NakedPosition] = []
        equity_curve    = []
        risk_mgr        = OTMNakedRiskManager(cfg, initial_capital)

        ml_trained_through: Optional[pd.Timestamp] = None
        labeled_data: List[dict] = []    # accumulates for ML training

        # Phase 3: drawdown kill-switch state
        peak_nav             = initial_capital
        drawdown_kill_active = False    # True = max_risk_per_trade_pct reverted to 2%

        # Phase 3b: Earnings IC overlay (separate capital pool)
        earnings_overlay = EarningsICOverlay(cfg) if cfg.earnings_ic_enabled else None

        # ── Daily simulation ──────────────────────────────────────────────────
        for i, today in enumerate(trading_days):
            today_vix   = float(vix.get(today, vix.iloc[-1]) if today in vix.index else vix.iloc[-1])
            today_rf    = float(rf.get(today, 0.045) if rf is not None and today in rf.index else 0.045)

            # ── 1. Monitor open positions ─────────────────────────────────────
            exits = []
            for pos in open_positions:
                result = self._check_exits(pos, today, features, today_vix, today_rf, i)
                if result:
                    exit_premium, exit_reason = result
                    # BUG FIX: Cash accounting for naked option sellers.
                    # At ENTRY: cash already received entry_premium * contracts * 100 (credit)
                    # At EXIT:  we pay exit_premium to close; net = entry - exit (already in pnl)
                    # Old code added entry_premium a 2nd time, doubling the credit every close.
                    pnl = (pos.entry_premium - exit_premium) * pos.contracts * 100
                    pnl -= cfg.commission_per_contract * pos.contracts * 2   # round-trip comm
                    pos.exit_date    = today
                    pos.exit_premium = exit_premium
                    pos.exit_reason  = exit_reason
                    pos.pnl          = pnl
                    pos.trade_won    = pnl > 0
                    # Only subtract the cost-to-close and exit commission (entry credit already in cash)
                    cash -= exit_premium * pos.contracts * 100                     # Pay to close
                    cash -= cfg.commission_per_contract * pos.contracts            # Exit commission
                    exits.append(pos)
                    closed_trades.append(pos)
                    labeled_data.append(self._position_to_label(pos, features))
                    logger.debug(f"  EXIT {pos.symbol} {pos.option_type.upper()} "
                                 f"strike={pos.strike:.1f} pnl=${pnl:+.0f} [{exit_reason}]")

            open_positions = [p for p in open_positions if p not in exits]
            risk_mgr.open_positions = [self._pos_to_dict(p) for p in open_positions]

            # ── 2. ML retraining window ───────────────────────────────────────
            if (use_ml and len(labeled_data) >= 50 and
                    (ml_trained_through is None or
                     (today - ml_trained_through).days >= cfg.step_days)):
                self._retrain_classifier(labeled_data, features)
                ml_trained_through = today

            # ── 3. Scan for new entries ────────────────────────────────────────
            nav = cash + sum(
                self._mtm_position(p, today, features, today_vix, today_rf)
                for p in open_positions
            )

            # Phase 3: Drawdown kill-switch — protect quarter-Kelly sizing
            # If NAV drops 10% from its peak, revert sizing to 2% for safety
            peak_nav = max(peak_nav, nav)
            drawdown_pct = (peak_nav - nav) / peak_nav if peak_nav > 0 else 0
            if drawdown_pct >= cfg.max_drawdown_kill_pct and not drawdown_kill_active:
                drawdown_kill_active = True
                logger.warning(f"  KILL-SWITCH: {today.date()} | DD={drawdown_pct*100:.1f}% "
                               f"| Reverting sizing to 2%")
            elif drawdown_pct < cfg.max_drawdown_kill_pct * 0.5 and drawdown_kill_active:
                # Re-enable when drawdown recovers to 5% (half of kill threshold)
                drawdown_kill_active = False
                logger.info(f"  KILL-SWITCH RESET: {today.date()} | DD={drawdown_pct*100:.1f}%")

            # Override config sizing if kill-switch is active
            effective_risk_pct = cfg.max_drawdown_kill_revert_pct if drawdown_kill_active else cfg.max_risk_per_trade_pct
            risk_mgr.config.max_risk_per_trade_pct = effective_risk_pct

            new_entries = self._scan_entries(
                today=today,
                features=features,
                vix=today_vix,
                rf=today_rf,
                cash=cash,
                nav=nav,
                risk_mgr=risk_mgr,
                open_positions=open_positions,
                use_ml=use_ml,
            )
            for pos in new_entries:
                cost = pos.entry_premium * pos.contracts * 100
                cash -= cfg.commission_per_contract * pos.contracts   # Entry commission
                # For naked sellers: premium is received at entry
                cash += cost
                open_positions.append(pos)
                logger.debug(f"  ENTER {pos.symbol} {pos.option_type.upper()} "
                             f"strike={pos.strike:.1f} x{pos.contracts} "
                             f"credit=${cost:.0f} conf={pos.ml_confidence:.2f}")

            # ── 4. MTM equity curve ───────────────────────────────────────────
            positions_mv = sum(
                self._mtm_position(p, today, features, today_vix, today_rf)
                for p in open_positions
            )
            # Naked positions: cash already has premium; MTM is unrealized loss risk
            # Net NAV = cash - current cost to close open positions
            nav = cash - positions_mv

            # ── 4.5 SGOV cash sweep yield (Phase 1B) ─────────────────────────
            if cfg.sgov_sweep_enabled:
                margin_reserve = nav * cfg.sgov_margin_buffer_pct
                sweepable_cash = max(0.0, cash - positions_mv - margin_reserve)
                daily_yield    = sweepable_cash * (cfg.sgov_annual_yield / 252.0)
                cash          += daily_yield
                nav           += daily_yield

            # ── 4.6 Earnings IC Overlay (Phase 3b) ───────────────────────────
            if earnings_overlay is not None:
                # Check exits FIRST (yesterday's ICs closing today)
                closed_ics = earnings_overlay.check_exits(today, features, today_vix)
                for ic in closed_ics:
                    # Pay debit to close IC legs; entry credit already in cash
                    cash -= ic.exit_debit * ic.contracts * 100

                # Then scan for new earnings IC entries
                new_ics = earnings_overlay.scan_entries(today, features, nav)
                for ic in new_ics:
                    # Receive net credit from selling the IC
                    cash += ic.net_credit * ic.contracts * 100

            equity_curve.append({"date": today, "nav": nav, "cash": cash,
                                  "open_positions": len(open_positions)})

            if i % 100 == 0 or i == len(trading_days) - 1:
                logger.info(f"  {today.date()} | NAV=${nav:,.0f} | "
                            f"open={len(open_positions)} | closed={len(closed_trades)}")

        # Force-close all positions at end date
        last_day = trading_days[-1]
        for pos in open_positions:
            today_vix_last = float(vix.iloc[-1])
            today_rf_last  = 0.045
            exit_premium   = self._current_premium(pos, last_day, features, today_vix_last, today_rf_last)
            pnl = (pos.entry_premium - exit_premium) * pos.contracts * 100
            pnl -= cfg.commission_per_contract * pos.contracts * 2
            pos.exit_date    = last_day
            pos.exit_premium = exit_premium
            pos.exit_reason  = "end_of_backtest"
            pos.pnl          = pnl
            pos.trade_won    = pnl > 0
            # Consistent with intra-backtest exit: subtract cost-to-close only
            cash -= exit_premium * pos.contracts * 100
            cash -= cfg.commission_per_contract * pos.contracts
            closed_trades.append(pos)

        equity_df = pd.DataFrame(equity_curve).set_index("date")
        trades_df = pd.DataFrame([self._pos_to_dict(p) for p in closed_trades])
        metrics   = self._compute_metrics(equity_df, trades_df, initial_capital)

        # Include earnings IC overlay results (separate from core metrics)
        ic_metrics  = earnings_overlay.get_metrics() if earnings_overlay else {}
        ic_trades   = earnings_overlay.to_dataframe() if earnings_overlay else pd.DataFrame()

        return {
            "equity_curve":   equity_df,
            "trades":         trades_df,
            "metrics":        metrics,
            "ic_metrics":     ic_metrics,
            "ic_trades":      ic_trades,
        }


    # ── Entry scanning ────────────────────────────────────────────────────────
    def _scan_entries(self, today, features, vix, rf, cash, nav,
                      risk_mgr, open_positions, use_ml) -> List[NakedPosition]:
        """Scan all symbols for entry signals today."""
        cfg = self.config
        candidates = []
        entries = []
        existing_symbols = {p.symbol for p in open_positions}

        for symbol, feat_df in features.items():
            if today not in feat_df.index:
                continue
            if symbol in existing_symbols:
                continue    # One position per symbol at a time

            row = feat_df.loc[today]
            # Signal engine
            signal = self.signal_eng.evaluate(symbol, row)
            if signal.signal_type in (SignalType.NONE,):
                continue

            # ML confidence gate
            ml_conf = self.classifier.predict_confidence(row) if use_ml else signal.raw_confidence
            if ml_conf < cfg.ml_confidence_min and use_ml:
                continue

            # Determine option type and parameters
            if signal.signal_type == SignalType.SELL_CALL:
                opt_type = "call"
            elif signal.signal_type == SignalType.SELL_PUT:
                opt_type = "put"
            else:
                opt_type = "put"    # BOTH → prefer put (more common)

            # Strike selection
            regime  = signal.vix_regime
            dte     = self.strike_sel.select_dte(regime)
            T_years = dte / 365.0
            hv_20   = float(row.get("hv_20", 0.20))
            sigma   = self.strike_sel.estimate_iv(hv_20, vix)
            spot    = float(row.get("close", row.get("Close", 0)))
            if spot <= 0:
                continue

            if opt_type == "put":
                strike, premium, greeks = self.strike_sel.select_put_strike(
                    spot, T_years, sigma, regime, rf)
            else:
                strike, premium, greeks = self.strike_sel.select_call_strike(
                    spot, T_years, sigma, regime, rf)

            if premium < cfg.min_premium:
                continue    # Not enough credit

            # Risk check — pass symbol for high-beta size multiplier
            contracts = risk_mgr.calculate_contracts(premium, strike, nav, symbol=symbol)
            if contracts < 1:
                continue

            # Pathway B: apply smaller size multiplier (more conservative)
            if signal.pathway == "B":
                contracts = max(1, int(contracts * cfg.pathway_b_size_mult))

            # Add to candidates list instead of committing immediately
            rsi_14_val   = float(row.get("rsi_14", 50.0))
            pct_52w_dist = abs(float(row.get("pct_from_52w_high", 0)))

            # Sort score by pathway:
            # Pathway A: pure 52W distance (unchanged from Phase 1 — do NOT pollute with RSI)
            # Pathway B: RSI confirmation bonus (+0.5) so the most oversold B candidates
            #            fill their slots first, but never compete with Pathway A ordering.
            if signal.pathway == "A":
                sort_score = pct_52w_dist
            else:
                sort_score = pct_52w_dist + (
                    0.50 if (opt_type == "put"  and rsi_14_val <= 30) else 0
                ) + (
                    0.50 if (opt_type == "call" and rsi_14_val >= 70) else 0
                )

            candidates.append({
                "symbol":    symbol,
                "opt_type":  opt_type,
                "strike":    strike,
                "premium":   premium,
                "sigma":     sigma,
                "contracts": contracts,
                "regime":    regime,
                "ml_conf":   ml_conf,
                "spot":      spot,
                "vix":       vix,
                "iv_rank":   float(row.get("iv_rank", 0.5)),
                "iv_hv_ratio": float(row.get("iv_hv_ratio", 1.1)),
                "earn_days": int(row.get("earnings_days_away", 999)),
                "dte":       dte,
                "pathway":    signal.pathway,
                "rsi_14":     rsi_14_val,
                "sort_score": sort_score,
            })

        # Sort: Pathway A first (HILO signals take priority), then by sort_score desc
        candidates.sort(key=lambda x: (x["pathway"] != "A", -x["sort_score"]))

        # Track Pathway B slots used today (separate pool from Pathway A)
        pathway_b_used = sum(
            1 for p in open_positions if getattr(p, "pathway", "A") == "B"
        )

        for cand in candidates:
            # Check risk limits sequentially on the sorted candidates
            rcheck = risk_mgr.check_entry(
                cand["symbol"], cand["strike"], cand["premium"], cand["contracts"], cand["vix"],
                cand["iv_rank"], cand["iv_hv_ratio"], cand["earn_days"], cand["opt_type"]
            )
            if not rcheck:
                continue

            # Pathway B: enforce separate slot limit
            if cand["pathway"] == "B":
                if pathway_b_used >= cfg.pathway_b_max_slots:
                    logger.debug(f"  {cand['symbol']}: Pathway B slot limit ({cfg.pathway_b_max_slots}) reached")
                    continue
                pathway_b_used += 1

            # Build position + initialize spread-aware stop state
            expiry = today + pd.Timedelta(days=cand["dte"])
            notional = cand["strike"] * cand["contracts"] * 100
            iv_rank_at_entry = float(cand.get("iv_rank", 0.30))
            pos = NakedPosition(
                symbol=cand["symbol"], option_type=cand["opt_type"],
                strike=cand["strike"], entry_date=today, expiry_date=expiry,
                entry_premium=cand["premium"], entry_spot=cand["spot"],
                entry_sigma=cand["sigma"], contracts=cand["contracts"],
                regime=cand["regime"], ml_confidence=cand["ml_conf"],
                notional_risk=notional,
                pathway=cand["pathway"],
                stop_state=self.stop_mgr.init_stop(
                    entry_premium=cand["premium"],
                    regime=cand["regime"],
                    iv_rank=iv_rank_at_entry,
                    day_idx=0,
                ),
            )
            entries.append(pos)
            risk_mgr.record_open(self._pos_to_dict(pos))

            # ── Strangle upgrade: try to add a call leg ───────────────────────
            T_years_s = cand["dte"] / 365.0
            should_strang, call_strike, call_premium, call_contr = \
                self._should_upgrade_to_strangle(
                    symbol=cand["symbol"],
                    iv_rank=cand["iv_rank"],
                    vix=cand["vix"],
                    regime=cand["regime"],
                    spot=cand["spot"],
                    T_years=T_years_s,
                    sigma=cand["sigma"],
                    rf=rf,
                    nav=nav,
                    risk_mgr=risk_mgr,
                    open_positions=open_positions + entries,
                )
            if should_strang:
                import uuid
                pair_id = str(uuid.uuid4())[:8]
                # Tag the put leg we just added
                pos.strangle_id = pair_id

                # Build the call leg
                call_notional = call_strike * call_contr * 100
                call_pos = NakedPosition(
                    symbol=cand["symbol"], option_type="call",
                    strike=call_strike, entry_date=today,
                    expiry_date=today + pd.Timedelta(days=cand["dte"]),
                    entry_premium=call_premium, entry_spot=cand["spot"],
                    entry_sigma=cand["sigma"], contracts=call_contr,
                    regime=cand["regime"], ml_confidence=cand["ml_conf"],
                    notional_risk=call_notional,
                    strangle_id=pair_id, is_strangle_call=True,
                    stop_state=self.stop_mgr.init_stop(
                        entry_premium=call_premium,
                        regime=cand["regime"],
                        iv_rank=cand["iv_rank"],
                        day_idx=0,
                    ),
                )
                entries.append(call_pos)
                risk_mgr.record_open(self._pos_to_dict(call_pos))
                logger.debug(f"  STRANGLE {cand['symbol']} | put K={pos.strike:.1f} call K={call_strike:.1f} "
                             f"total_cr=${(pos.entry_premium + call_premium)*call_contr*100:.0f}")

        return entries

    # ── Strangle upgrade decision ──────────────────────────────────────────────
    def _should_upgrade_to_strangle(
        self,
        symbol: str,
        iv_rank: float,
        vix: float,
        regime: str,
        spot: float,
        T_years: float,
        sigma: float,
        rf: float,
        nav: float,
        risk_mgr: OTMNakedRiskManager,
        open_positions: list,
    ) -> Tuple[bool, float, float, int]:
        """
        Decide if a PUT signal should be upgraded to a strangle.

        Returns:
            (should_upgrade, call_strike, call_premium, call_contracts)
        """
        cfg = self.config
        if not cfg.strangle_enabled:
            return False, 0.0, 0.0, 0

        # IV & VIX gates
        if iv_rank < cfg.strangle_iv_rank_min:
            return False, 0.0, 0.0, 0
        if vix > cfg.strangle_vix_max:
            return False, 0.0, 0.0, 0
        if regime in ("HIGH", "CRISIS"):
            return False, 0.0, 0.0, 0

        # Compute call strike and premium
        try:
            call_strike, call_premium, _ = self.strike_sel.select_call_strike(
                spot, T_years, sigma, regime, rf
            )
        except Exception:
            return False, 0.0, 0.0, 0

        if call_premium < cfg.strangle_min_call_premium:
            return False, 0.0, 0.0, 0

        # The put leg is already counted in open_positions when this is called.
        # We only need 1 additional slot for the call leg.
        open_count = len(open_positions)
        if open_count + 1 > cfg.max_concurrent_positions:
            return False, 0.0, 0.0, 0

        # Size the call leg (same logic as put, high-beta adjusted)
        call_contracts = risk_mgr.calculate_contracts(call_premium, call_strike, nav, symbol=symbol)
        if call_contracts < 1:
            return False, 0.0, 0.0, 0

        return True, call_strike, call_premium, call_contracts

    def _check_exits(self, pos: NakedPosition, today: pd.Timestamp,
                     features: dict, vix: float, rf: float,
                     day_idx: int = 0,
                     ) -> Optional[Tuple[float, str]]:
        """Check all exit rules using spread-aware + IV-adjusted stop. Returns (exit_premium, reason) or None."""
        current_mid = self._current_premium(pos, today, features, vix, rf)
        dte_remaining = (pos.expiry_date - today).days

        # 1. DTE-graduated profit targets (TastyTrade 200K-trade study)
        #    DTE > 21 → 50%, 14 < DTE ≤ 21 → 70%, 7 < DTE ≤ 14 → 80%, DTE ≤ 7 → 90%
        profit_pct = 1.0 - (current_mid / max(pos.entry_premium, 0.001))
        if dte_remaining > 21:
            target_pct = self.config.profit_take_pct           # 50%
        elif dte_remaining > 14:
            target_pct = self.config.profit_take_pct_21dte     # 70%
        elif dte_remaining > 7:
            target_pct = self.config.profit_take_pct_14dte     # 80%
        else:
            target_pct = self.config.profit_take_pct_7dte      # 90%
        if profit_pct >= target_pct:
            return current_mid, f"profit_take_{int(target_pct*100)}pct"

        # 2. Time exit (DTE ≤ 7) — always check
        if dte_remaining <= self.config.time_exit_dte:
            return current_mid, "time_exit"

        # 3. Expiry — always check
        if today >= pos.expiry_date:
            return current_mid, "expired"

        # 4. VIX crisis spike — always check
        if vix >= self.config.vix_crisis_threshold:
            return current_mid, "vix_crisis"

        # 5. Spread-aware IV-adjusted trailing stop (check-frequency gated)
        if pos.stop_state is None:
            pos.stop_state = self.stop_mgr.init_stop(pos.entry_premium, pos.regime)

        # Frequency gate: skip evaluation on calm days
        if not self.stop_mgr.should_check(pos.stop_state, day_idx, dte_remaining, current_mid):
            return None

        feat_df  = features.get(pos.symbol)
        feat_row = feat_df.loc[today] if (feat_df is not None and today in feat_df.index) else None

        if feat_row is not None:
            import math as _math
            try:
                close_today = float(feat_row.get("close", 1.0))
                close_prev  = float(feat_row.get("prev_close", close_today))
                daily_move  = abs(close_today - close_prev) / max(close_prev, 0.01)
                hv20        = float(feat_row.get("hv_20", 0.20))
                avg_move    = hv20 / _math.sqrt(252)
            except Exception:
                daily_move, avg_move = 0.01, 0.01

            triggered, exit_px, reason = self.stop_mgr.check(
                entry_premium=pos.entry_premium,
                current_mid=current_mid,
                stop_state=pos.stop_state,
                regime=pos.regime,
                current_day_idx=day_idx,
                underlying_daily_move=daily_move,
                underlying_avg_move=avg_move,
            )
        else:
            # Fallback: simple multiplier
            triggered = (current_mid / max(pos.entry_premium, 0.001)) >= self.config.stop_loss_credit_mult
            exit_px   = current_mid
            reason    = "stop_loss_2x"

        if triggered:
            return exit_px, reason

        return None

    def _current_premium(self, pos: NakedPosition, today: pd.Timestamp,
                         features: dict, vix: float, rf: float) -> float:
        """Compute current BS mid price for an open position."""
        dte_remaining = max((pos.expiry_date - today).days, 0)
        T = dte_remaining / 365.0
        if T <= 0:
            # At expiry: check if ITM
            feat_df = features.get(pos.symbol)
            if feat_df is not None and today in feat_df.index:
                spot = float(feat_df.loc[today].get("close", pos.entry_spot))
            else:
                spot = pos.entry_spot
            if pos.option_type == "put":
                return max(pos.strike - spot, 0.0)
            else:
                return max(spot - pos.strike, 0.0)

        # Estimate current IV from features
        feat_df = features.get(pos.symbol)
        if feat_df is not None and today in feat_df.index:
            row  = feat_df.loc[today]
            hv20 = float(row.get("hv_20", pos.entry_sigma))
            spot = float(row.get("close", pos.entry_spot))
            sigma = self.strike_sel.estimate_iv(hv20, vix)
        else:
            spot  = pos.entry_spot
            sigma = pos.entry_sigma

        if pos.option_type == "put":
            return bs_put_price(spot, pos.strike, T, rf, sigma)
        else:
            return bs_call_price(spot, pos.strike, T, rf, sigma)

    def _mtm_position(self, pos: NakedPosition, today: pd.Timestamp,
                      features: dict, vix: float, rf: float) -> float:
        """Current cost-to-close (liability side of naked position)."""
        return self._current_premium(pos, today, features, vix, rf) * pos.contracts * 100

    # ── ML retraining ─────────────────────────────────────────────────────────
    def _retrain_classifier(self, labeled_data: list, features: dict):
        """Retrain classifier on accumulated labeled trades."""
        if len(labeled_data) < 50:
            return
        df = pd.DataFrame(labeled_data)
        try:
            self.classifier.fit(df, win_col="trade_won")
            logger.info(f"  ML retrained on {len(df)} labeled trades")
        except Exception as e:
            logger.warning(f"  ML retrain failed: {e}")

    def _position_to_label(self, pos: NakedPosition, features: dict) -> dict:
        """Convert closed position to a labeled row for ML training."""
        feat_df = features.get(pos.symbol)
        row = {}
        if feat_df is not None and pos.entry_date in feat_df.index:
            row = feat_df.loc[pos.entry_date].to_dict()
        row["symbol"]         = pos.symbol
        row["option_type"]    = pos.option_type
        row["signal_type"]    = f"SELL_{pos.option_type.upper()}"
        row["trade_won"]      = int(pos.trade_won)
        row["entry_premium"]  = pos.entry_premium
        row["exit_reason"]    = pos.exit_reason
        row["pnl"]            = pos.pnl
        return row

    # ── Metrics ───────────────────────────────────────────────────────────────
    def _compute_metrics(self, equity_df: pd.DataFrame,
                         trades_df: pd.DataFrame,
                         initial_capital: float) -> dict:
        """Compute standard performance metrics."""
        nav = equity_df["nav"]
        if nav.empty:
            return {}

        final    = float(nav.iloc[-1])
        n_days   = len(nav)
        years    = n_days / 252.0
        cagr     = ((final / initial_capital) ** (1 / max(years, 0.1)) - 1) * 100
        total_r  = (final / initial_capital - 1) * 100

        # Drawdown
        roll_max  = nav.cummax()
        dd_series = (nav - roll_max) / roll_max
        max_dd    = float(dd_series.min()) * 100

        # Sharpe (daily returns)
        daily_ret = nav.pct_change().dropna()
        sharpe    = (float(daily_ret.mean()) / max(float(daily_ret.std()), 1e-9)
                     * math.sqrt(252)) if len(daily_ret) > 1 else 0.0

        # Trade stats
        n_trades = len(trades_df)
        if n_trades > 0 and "trade_won" in trades_df.columns:
            win_rate = float(trades_df["trade_won"].mean()) * 100
            wins  = trades_df[trades_df["trade_won"] == True]["pnl"]
            losses= trades_df[trades_df["trade_won"] == False]["pnl"]
            gross_profit = float(wins.sum())  if len(wins) > 0  else 0.0
            gross_loss   = abs(float(losses.sum())) if len(losses) > 0 else 1.0
            profit_factor = gross_profit / max(gross_loss, 1.0)
            avg_win   = float(wins.mean())   if len(wins) > 0   else 0.0
            avg_loss  = float(losses.mean()) if len(losses) > 0 else 0.0
        else:
            win_rate = profit_factor = avg_win = avg_loss = 0.0

        return {
            "initial_capital": initial_capital,
            "final_value":     round(final, 2),
            "total_return_pct": round(total_r, 2),
            "cagr_pct":        round(cagr, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio":    round(sharpe, 3),
            "n_trades":        n_trades,
            "win_rate_pct":    round(win_rate, 1),
            "profit_factor":   round(profit_factor, 3),
            "avg_win":         round(avg_win, 2),
            "avg_loss":        round(avg_loss, 2),
        }

    def print_summary(self, results: dict):
        m = results.get("metrics", {})
        t = results.get("trades", pd.DataFrame())
        print("\n" + "=" * 60)
        print("  OTM NAKED OPTIONS — BACKTEST RESULTS")
        print("=" * 60)
        print(f"  Initial Capital : ${m.get('initial_capital', 0):>12,.2f}")
        print(f"  Final Value     : ${m.get('final_value', 0):>12,.2f}")
        print(f"  Total Return    : {m.get('total_return_pct', 0):>12.1f}%")
        print(f"  CAGR            : {m.get('cagr_pct', 0):>12.1f}%")
        print(f"  Max Drawdown    : {m.get('max_drawdown_pct', 0):>12.1f}%")
        print(f"  Sharpe Ratio    : {m.get('sharpe_ratio', 0):>12.3f}")
        print(f"  Total Trades    : {m.get('n_trades', 0):>12,d}")
        print(f"  Win Rate        : {m.get('win_rate_pct', 0):>12.1f}%")
        print(f"  Profit Factor   : {m.get('profit_factor', 0):>12.3f}")
        print(f"  Avg Win         : ${m.get('avg_win', 0):>12,.2f}")
        print(f"  Avg Loss        : ${m.get('avg_loss', 0):>12,.2f}")
        print("=" * 60)
        if not t.empty and "exit_reason" in t.columns:
            print("\n  Exit Reasons:")
            for reason, cnt in t["exit_reason"].value_counts().items():
                print(f"    {reason:<25} {cnt:>4d}  ({cnt/len(t)*100:.1f}%)")
        if not t.empty and "option_type" in t.columns:
            print("\n  By Option Type:")
            for ot, grp in t.groupby("option_type"):
                wr = grp["trade_won"].mean() * 100 if "trade_won" in grp else 0
                print(f"    {ot:<10} trades={len(grp):>3d}  win={wr:.1f}%  "
                      f"pnl=${grp['pnl'].sum():+,.0f}")
        if not t.empty and "strangle_id" in t.columns:
            strang = t[t["strangle_id"].notna()]
            solo   = t[t["strangle_id"].isna()]
            n_strang_pairs = strang["strangle_id"].nunique()
            print(f"\n  Strategy Mix:")
            print(f"    Naked puts/calls (solo) : {len(solo):>3d} legs  pnl=${solo['pnl'].sum():+,.0f}")
            print(f"    Strangle legs           : {len(strang):>3d} legs  ({n_strang_pairs} pairs)  pnl=${strang['pnl'].sum():+,.0f}")

    @staticmethod
    def _pos_to_dict(pos: NakedPosition) -> dict:
        return {
            "symbol":        pos.symbol,
            "option_type":   pos.option_type,
            "strike":        pos.strike,
            "entry_date":    pos.entry_date,
            "expiry_date":   pos.expiry_date,
            "entry_premium": pos.entry_premium,
            "entry_spot":    pos.entry_spot,
            "contracts":     pos.contracts,
            "regime":        pos.regime,
            "ml_confidence": pos.ml_confidence,
            "notional_risk": pos.notional_risk,
            "exit_date":     pos.exit_date,
            "exit_premium":  pos.exit_premium,
            "exit_reason":   pos.exit_reason,
            "pnl":           pos.pnl,
            "trade_won":     pos.trade_won,
            "strangle_id":   pos.strangle_id,
            "pathway":       pos.pathway,   # "A" = HILO; "B" = VIX-conditional
        }
