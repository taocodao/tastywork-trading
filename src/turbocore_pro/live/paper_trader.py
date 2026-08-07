"""
Paper Trader — main execution loop for TurboCore Pro paper trading.

Fetches live data, computes target allocation, compares to current positions,
applies drift threshold + execution timing, and submits (or logs) orders.

Usage:
    python live/paper_trader.py                    # single run
    python live/paper_trader.py --loop             # continuous loop
    python live/paper_trader.py --config <path>    # custom config
"""
import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
import pandas as pd

PKG_DIR = Path(__file__).resolve().parent          # src/turbocore_pro/live
REPO_ROOT = Path(__file__).resolve().parents[3]      # repo root
sys.path.insert(0, str(REPO_ROOT))                   # enables `src.turbocore_pro` package imports
sys.path.insert(0, str(PKG_DIR))                     # sibling live modules (ibkr_client, data_fetcher, ...)

from ibkr_client import IBKRClient
from data_fetcher import fetch_all_vix_indices, align_vix_to_hourly
from signal_runner import SignalRunner
import positions_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
)
log = logging.getLogger("turbocore.live")


class PaperTrader:
    def __init__(self, config_path: str = None):
        config_path = config_path or str(Path(__file__).parent / "config" / "paper_web3aistore.yaml")
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.repo_root = Path(__file__).resolve().parents[3]
        self.dry_run = self.config["execution"].get("dry_run", True)
        self.strat = self.config["strategy"]

        # Initialize components
        self.ibkr = IBKRClient(
            host=self.config["ibkr"]["host"],
            port=self.config["ibkr"]["port"],
            client_id=self.config["ibkr"]["client_id"],
            timeout=self.config["ibkr"]["timeout"],
        )
        self.signal_runner = SignalRunner(self.config, self.repo_root)

        # State
        self.initial_nav = self.config["risk"]["initial_capital"]
        self.kill_switch_triggered = False

        # Logging
        log_dir = self.repo_root / self.config["execution"].get("log_dir", "logs")
        log_dir.mkdir(exist_ok=True)
        self.db_path = log_dir / self.config["execution"].get("log_db", "paper_trades.db")
        self._init_db()

        # Positions/P&L tracking DB (separate from the trade_log audit table above)
        self.positions_db_path = log_dir / self.config["execution"].get(
            "positions_db", "positions.db")
        self._positions_conn = positions_db.get_conn(str(self.positions_db_path))

    def _init_db(self):
        """Initialize SQLite audit log."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                bar_time TEXT,
                regime TEXT, signal INTEGER, confidence REAL,
                target_allocation TEXT, current_positions TEXT,
                orders TEXT, nav REAL, dry_run INTEGER,
                status TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _log_to_db(self, **kwargs):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO trade_log
            (timestamp, bar_time, regime, signal, confidence,
             target_allocation, current_positions, orders, nav, dry_run, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kwargs.get("timestamp", datetime.now(timezone.utc).isoformat()),
            kwargs.get("bar_time", ""),
            kwargs.get("regime", ""),
            kwargs.get("signal", 0),
            kwargs.get("confidence", 0.0),
            json.dumps(kwargs.get("target_allocation", {})),
            json.dumps(kwargs.get("current_positions", {})),
            json.dumps(kwargs.get("orders", [])),
            kwargs.get("nav", 0.0),
            int(kwargs.get("dry_run", True)),
            kwargs.get("status", ""),
        ))
        conn.commit()
        conn.close()

    def check_kill_switch(self, nav: float) -> bool:
        """Stop trading if NAV drops below kill_switch threshold."""
        threshold = self.config["risk"].get("kill_switch_nav_pct", 0.80)
        if nav < self.initial_nav * threshold:
            log.warning(f"KILL SWITCH: NAV ${nav:,.0f} < "
                        f"${self.initial_nav * threshold:,.0f} threshold. "
                        f"Stopping all trading.")
            self.kill_switch_triggered = True
            return True
        return False

    def should_skip_bar(self, bar_time: datetime) -> bool:
        """Check execution timing: skip 9:30 and 15:00 bars."""
        if not self.strat.get("skip_open_close", False):
            return False
        hour = bar_time.hour
        if hour in (9, 15):
            log.info(f"Skipping order generation on {bar_time.strftime('%H:%M')} bar "
                     f"(thin liquidity window)")
            return True
        return False

    def compute_orders(self, target: dict, current: dict, nav: float,
                       prices: dict) -> list:
        """
        Compare target allocation to current positions and generate delta orders.
        Applies the 5% drift threshold. Only trades symbols in the strategy universe.
        """
        drift_threshold = self.strat.get("drift_threshold", 0.05)
        # Only trade symbols that are in our strategy universe
        strategy_symbols = {s["ticker"] for s in self.strat["symbols"]}
        orders = []

        all_symbols = (set(list(target.keys()) + list(current.keys()))
                       & strategy_symbols)
        for sym in all_symbols:
            target_weight = target.get(sym, 0.0)
            target_value = target_weight * nav
            target_shares = target_value / prices.get(sym, 1) if prices.get(sym, 0) > 0 else 0

            current_shares = current.get(sym, 0)
            current_value = current_shares * prices.get(sym, 0)

            # Drift check: only trade if deviation exceeds threshold
            if nav > 0:
                drift = abs(target_value - current_value) / nav
                if drift < drift_threshold and target_weight > 0:
                    continue  # within band, skip

            delta = target_shares - current_shares
            if abs(delta) < 0.01:  # negligible share difference
                continue

            # Round to whole shares — IBKR API doesn't support fractional orders
            quantity = int(round(abs(delta)))
            if quantity == 0:
                continue

            action = "BUY" if delta > 0 else "SELL"

            # Cap single order notional
            max_notional = self.config["risk"].get("max_order_notional", 50000)
            order_value = quantity * prices.get(sym, 0)
            if order_value > max_notional:
                quantity = int(max_notional / prices.get(sym, 1))
                log.warning(f"Capped {sym} order to ${max_notional:,.0f} notional ({quantity} shares)")

            orders.append({
                "symbol": sym,
                "action": action,
                "quantity": round(quantity, 4),
                "price": prices.get(sym, 0),
                "notional": round(quantity * prices.get(sym, 0), 2),
            })

        return orders

    def run_once(self) -> dict:
        """Execute one trading cycle: fetch data, compute signal, generate orders."""
        log.info("=" * 60)
        log.info(f"Paper trading cycle started at {datetime.now(timezone.utc).isoformat()}")
        log.info(f"Dry run: {self.dry_run}")

        # 1. Connect to IBKR
        connected = self.ibkr.connect()
        if not connected and not self.dry_run:
            log.error("Cannot trade without IBKR connection")
            return {"status": "NO_CONNECTION"}

        # 2. Load models (first run only)
        if self.signal_runner._hmm is None:
            self.signal_runner.load_models()

        # 3. Fetch hourly bars from IBKR
        ibkr_bars = {}
        if connected:
            nav = self.ibkr.get_nav()
            positions = self.ibkr.get_positions()
            current_pos = {sym: p.shares for sym, p in positions.items()}
        else:
            nav = self.initial_nav
            current_pos = {}

        log.info(f"NAV: ${nav:,.2f}, Positions: {current_pos}")

        # Check kill switch
        if self.check_kill_switch(nav):
            return {"status": "KILL_SWITCH"}

        # Fetch bars
        if connected:
            for sym_cfg in self.strat["symbols"]:
                sym = sym_cfg["ticker"]
                bars = self.ibkr.fetch_hourly_bars_df(sym, self.strat["lookback_bars"])
                if not bars.empty:
                    ibkr_bars[sym] = bars
        else:
            log.warning("No IBKR connection — using empty bars (dry-run mode)")

        if not ibkr_bars:
            log.warning("No bars fetched — cannot compute signal")
            # Still log the attempt
            self._log_to_db(
                timestamp=datetime.now(timezone.utc).isoformat(),
                nav=nav, current_positions=current_pos,
                dry_run=self.dry_run, status="NO_DATA",
            )
            return {"status": "NO_DATA"}

        # 4. Fetch VIX indices (CBOE → Yahoo → IBKR fallback chain)
        vix_data_raw = fetch_all_vix_indices(ibkr_client=self.ibkr)
        vix_data = {}
        qqq_index = ibkr_bars.get("QQQ", pd.DataFrame()).index
        for sym, daily_df in vix_data_raw.items():
            if not daily_df.empty and not qqq_index.empty:
                vix_data[sym] = align_vix_to_hourly(daily_df, qqq_index)

        # 5. Build features and compute signal
        master = self.signal_runner.build_features(ibkr_bars, vix_data)
        signal = self.signal_runner.compute_signal(master)

        log.info(f"Signal: regime={signal['regime']}, signal={signal['signal']}, "
                 f"confidence={signal['confidence']:.3f}")
        log.info(f"Target allocation: {signal['target_allocation']}")

        # 6. Check execution timing
        bar_time = pd.to_datetime(signal.get("timestamp"))
        if self.should_skip_bar(bar_time):
            log.info("Skipping order generation (execution timing)")
            self._log_to_db(
                bar_time=str(bar_time), regime=signal["regime"],
                signal=signal["signal"], confidence=signal["confidence"],
                target_allocation=signal["target_allocation"],
                current_positions=current_pos, nav=nav,
                dry_run=self.dry_run, status="SKIP_TIMING",
            )
            return {**signal, "status": "SKIP_TIMING"}

        # 7. Compute orders
        prices = {}
        for sym in signal["target_allocation"]:
            if sym in ibkr_bars and not ibkr_bars[sym].empty:
                prices[sym] = float(ibkr_bars[sym]["close"].iloc[-1])

        orders = self.compute_orders(signal["target_allocation"], current_pos, nav, prices)
        log.info(f"Generated {len(orders)} orders: {orders}")

        # 8. Submit orders
        submitted_orders = []
        for order in orders:
            result = self.ibkr.submit_order(
                symbol=order["symbol"], action=order["action"],
                quantity=order["quantity"], dry_run=self.dry_run,
            )
            submitted_orders.append({**order, **result})

            # Record filled/submitted live orders into the positions/P&L ledger.
            # (Dry-run orders are not recorded — they never touch the account.)
            if not self.dry_run and result.get("status") == "SUBMITTED":
                try:
                    positions_db.record_trade(
                        self._positions_conn,
                        symbol=order["symbol"],
                        action=order["action"],
                        shares=order["quantity"],
                        price=order["price"],
                        regime=signal["regime"],
                        ml_confidence=signal["confidence"],
                        target_pct=signal["target_allocation"].get(order["symbol"]),
                        order_id=result.get("order_id"),
                    )
                except Exception as e:
                    log.error(f"Failed to record trade to positions DB: {e}")

        # Record allocation snapshot every cycle (executed or not) for tracking drift over time
        try:
            positions_db.record_allocation_snapshot(
                self._positions_conn,
                ts=datetime.now(timezone.utc).isoformat(),
                target_allocation=signal["target_allocation"],
                current_positions=current_pos,
                prices=prices,
                nav=nav,
                regime=signal["regime"],
                ml_confidence=signal["confidence"],
            )
        except Exception as e:
            log.error(f"Failed to record allocation snapshot: {e}")

        # 9. Log everything
        self._log_to_db(
            bar_time=str(bar_time), regime=signal["regime"],
            signal=signal["signal"], confidence=signal["confidence"],
            target_allocation=signal["target_allocation"],
            current_positions=current_pos,
            orders=submitted_orders, nav=nav,
            dry_run=self.dry_run,
            status="DRY_RUN" if self.dry_run else "EXECUTED",
        )

        # 10. Disconnect
        self.ibkr.disconnect()

        return {**signal, "orders": submitted_orders, "nav": nav,
                "status": "DRY_RUN" if self.dry_run else "EXECUTED"}


def main():
    parser = argparse.ArgumentParser(description="TurboCore Pro Paper Trader")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config YAML")
    parser.add_argument("--loop", action="store_true",
                        help="Run in continuous loop mode")
    parser.add_argument("--live", action="store_true",
                        help="Enable live paper order submission (not dry-run)")
    args = parser.parse_args()

    trader = PaperTrader(config_path=args.config)
    if args.live:
        trader.dry_run = False
        log.warning("LIVE PAPER TRADING ENABLED — orders will be submitted to IBKR paper account")

    if args.loop:
        log.info("Starting continuous loop mode. Press Ctrl+C to stop.")
        import time
        try:
            while True:
                trader.run_once()
                log.info("Sleeping 3600 seconds (1 hour) until next cycle...")
                time.sleep(3600)
        except KeyboardInterrupt:
            log.info("Stopped by user")
    else:
        result = trader.run_once()
        log.info(f"Cycle complete: {result.get('status', 'unknown')}")
        return result


if __name__ == "__main__":
    main()
