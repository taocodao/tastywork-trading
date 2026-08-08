"""
TurboCore Pro — Strategy-Isolated P&L Report

Reads the positions.db ledger (built by paper_trader.py via positions_db.py),
fetches live prices from IBKR for mark-to-market, and prints/logs a full
P&L breakdown: starting capital, realized/unrealized P&L per symbol,
current allocation vs target, and NAV.

Usage:
    python3 turbocore_pro_pnl_report.py                # print report
    python3 turbocore_pro_pnl_report.py --log          # print + append CSV history
    python3 turbocore_pro_pnl_report.py --config <path>

Env:
    TURBOCORE_PNL_START_CAPITAL  — override starting capital (default: 250000)
"""
import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(PKG_DIR))

from ibkr_client import IBKRClient
import positions_db

DEFAULT_START_CAPITAL = 250_000.0


def load_config(config_path: str = None) -> dict:
    config_path = config_path or str(Path(__file__).parent / "config" / "paper_web3aistore.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def fetch_live_prices(ibkr: IBKRClient, symbols: list) -> dict:
    """Fetch last price for each symbol via a 1-bar hourly request."""
    prices = {}
    for sym in symbols:
        try:
            bars = ibkr.fetch_hourly_bars_df(sym, 5)
            if not bars.empty:
                prices[sym] = float(bars["close"].iloc[-1])
        except Exception as e:
            print(f"WARNING: could not fetch price for {sym}: {e}", file=sys.stderr)
    return prices


def build_report(config: dict, positions_conn: sqlite3.Connection,
                  prices: dict, nav_ibkr: float = None,
                  start_capital: float = DEFAULT_START_CAPITAL) -> dict:
    """Compute the full P&L breakdown. Returns a dict for both printing and CSV logging."""
    positions = positions_db.get_all_positions(positions_conn)

    strategy_symbols = [s["ticker"] for s in config["strategy"]["symbols"]]

    total_realized = 0.0
    total_unrealized = 0.0
    total_market_value = 0.0
    per_symbol = {}

    for sym in strategy_symbols:
        pos = positions.get(sym, {"shares": 0.0, "cost_basis": 0.0,
                                   "avg_price": 0.0, "realized_pnl": 0.0})
        price = prices.get(sym, 0.0)
        market_value = pos["shares"] * price
        unrealized = market_value - pos["cost_basis"] if pos["shares"] > 0 else 0.0

        per_symbol[sym] = {
            "shares": pos["shares"],
            "avg_price": pos["avg_price"],
            "current_price": price,
            "cost_basis": pos["cost_basis"],
            "market_value": market_value,
            "realized_pnl": pos["realized_pnl"],
            "unrealized_pnl": unrealized,
        }
        total_realized += pos["realized_pnl"]
        total_unrealized += unrealized
        total_market_value += market_value

    # Cash balance = start_capital - net cash spent on buys + net cash from sells
    # i.e. start_capital - sum(cost_basis of open positions) + realized_pnl already
    # accounted for via avg cost accounting. Simplify: cash = start - total_cost_basis_open + realized
    total_cost_basis_open = sum(p["cost_basis"] for p in per_symbol.values())
    cash_balance = start_capital - total_cost_basis_open + total_realized

    strategy_nav = cash_balance + total_market_value
    total_pnl = strategy_nav - start_capital
    total_pnl_pct = (total_pnl / start_capital * 100) if start_capital else 0.0

    # Latest allocation target/regime snapshot
    latest = positions_conn.execute(
        "SELECT ts, regime, ml_confidence FROM allocation_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    latest_ts, latest_regime, latest_conf = latest if latest else (None, None, None)

    targets = {}
    if latest_ts:
        rows = positions_conn.execute(
            "SELECT symbol, target_pct FROM allocation_history WHERE ts = ?",
            (latest_ts,),
        ).fetchall()
        targets = {r[0]: r[1] for r in rows}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_capital": start_capital,
        "strategy_nav": strategy_nav,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "cash_balance": cash_balance,
        "per_symbol": per_symbol,
        "total_realized": total_realized,
        "total_unrealized": total_unrealized,
        "targets": targets,
        "regime": latest_regime,
        "ml_confidence": latest_conf,
        "ibkr_shared_nav": nav_ibkr,
    }


def format_report(report: dict) -> str:
    lines = []
    lines.append("TurboCore Pro Strategy — Isolated P&L Report")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("=" * 60)
    lines.append(f"Starting Capital:      ${report['start_capital']:>15,.2f}")
    lines.append(f"Strategy NAV:          ${report['strategy_nav']:>15,.2f}")
    sign = "+" if report["total_pnl"] >= 0 else ""
    lines.append(f"Total P&L:             ${report['total_pnl']:>15,.2f}  "
                 f"({sign}{report['total_pnl_pct']:.2f}%)")
    lines.append(f"Cash Balance:          ${report['cash_balance']:>15,.2f}")
    lines.append("")
    lines.append("--- REALIZED P&L (by symbol) ---")
    for sym, p in report["per_symbol"].items():
        lines.append(f"{sym} realized:          ${p['realized_pnl']:>15,.2f}")
    lines.append("")
    lines.append("--- UNREALIZED P&L (open positions) ---")
    for sym, p in report["per_symbol"].items():
        lines.append(f"{sym}: {p['shares']:.0f} shares, avg ${p['avg_price']:.2f}, "
                     f"market value ${p['market_value']:,.2f}, "
                     f"unrealized ${p['unrealized_pnl']:,.2f}")
    lines.append("")
    lines.append("--- CURRENT ALLOCATION ---")
    for sym, p in report["per_symbol"].items():
        target_pct = report["targets"].get(sym, 0.0) * 100
        actual_pct = (p["market_value"] / report["strategy_nav"] * 100
                      if report["strategy_nav"] else 0.0)
        lines.append(f"{sym}: target {target_pct:.0f}%, actual {actual_pct:.1f}%")
    lines.append(f"Regime: {report['regime']}, ML confidence: {report['ml_confidence']:.3f}"
                 if report["ml_confidence"] is not None else f"Regime: {report['regime']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def append_csv_history(report: dict, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "date", "generated_at", "start_capital", "strategy_nav",
                "total_pnl", "total_pnl_pct", "cash_balance",
                "total_realized", "total_unrealized", "regime", "ml_confidence",
            ])
        writer.writerow([
            datetime.now(timezone.utc).date().isoformat(),
            report["generated_at"], report["start_capital"], report["strategy_nav"],
            report["total_pnl"], report["total_pnl_pct"], report["cash_balance"],
            report["total_realized"], report["total_unrealized"],
            report["regime"], report["ml_confidence"],
        ])


def main():
    parser = argparse.ArgumentParser(description="TurboCore Pro P&L Report")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--log", action="store_true", help="Append to CSV history")
    args = parser.parse_args()

    config = load_config(args.config)
    repo_root = Path(__file__).resolve().parents[3]
    log_dir = repo_root / config["execution"].get("log_dir", "logs")
    positions_db_path = log_dir / config["execution"].get("positions_db", "positions.db")

    start_capital = float(os.environ.get("TURBOCORE_PNL_START_CAPITAL", DEFAULT_START_CAPITAL))

    conn = positions_db.get_conn(str(positions_db_path))

    strategy_symbols = [s["ticker"] for s in config["strategy"]["symbols"]]

    ibkr = IBKRClient(
        host=config["ibkr"]["host"],
        port=config["ibkr"]["port"],
        client_id=301,  # dedicated clientId for the P&L reporter, avoids collision
        timeout=config["ibkr"]["timeout"],
    )
    connected = ibkr.connect()
    nav_ibkr = None
    prices = {}
    if connected:
        nav_ibkr = ibkr.get_nav()
        prices = fetch_live_prices(ibkr, strategy_symbols)
        ibkr.disconnect()
    else:
        print("WARNING: could not connect to IBKR — using last known prices from allocation_history",
              file=sys.stderr)
        for sym in strategy_symbols:
            row = conn.execute(
                "SELECT actual_value, actual_shares FROM allocation_history "
                "WHERE symbol = ? AND actual_shares > 0 ORDER BY id DESC LIMIT 1",
                (sym,),
            ).fetchone()
            if row and row[1]:
                prices[sym] = row[0] / row[1]

    report = build_report(config, conn, prices, nav_ibkr=nav_ibkr, start_capital=start_capital)
    output = format_report(report)
    print(output)

    if args.log:
        csv_path = log_dir / "turbocore_pro_pnl_history.csv"
        append_csv_history(report, csv_path)
        print(f"\nAppended to {csv_path}")

    conn.close()


if __name__ == "__main__":
    main()
