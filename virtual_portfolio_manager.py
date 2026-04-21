"""
Virtual Portfolio Manager
=========================
Tracks 3 strategy virtual accounts in a single JSON state file.
All principals are hardcoded — no DB auth required.

Accounts:
  - TurboCore       : $5,000 initial   (ETF rebalancing)
  - TurboCore Pro   : $25,000 initial  (ETF + options overlay)
  - QQQ LEAPS       : $25,000 initial  (LEAPS call positions)

State file: data/virtual_portfolio_state.json
Public file: data/virtual_portfolio_public.json  (5-day delayed, pushed to Vercel)
"""
import os
import json
import math
import logging
import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
from pathlib import Path
import pytz

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
INITIAL_PRINCIPALS = {
    "TQQQ_TURBOCORE": 5_000.0,
    "TURBOCORE_PRO":  25_000.0,
    "QQQ_LEAPS":      25_000.0,
}

# How many calendar days old the public JSON is (landing page delay)
PUBLIC_DELAY_DAYS = 5

DATA_DIR        = Path(__file__).parent / "data"
STATE_FILE      = DATA_DIR / "virtual_portfolio_state.json"
PUBLIC_FILE     = DATA_DIR / "virtual_portfolio_public.json"
NAV_HISTORY_DIR = DATA_DIR / "virtual_nav_history"


# ── Black-Scholes (mirrored from strike_optimizer for self-containment) ────────
def _bs_call_price(S, K, T, r, sigma) -> float:
    """Black-Scholes call price. T in years."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        from scipy.stats import norm
        return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    except Exception:
        return max(S - K, 0.0)


# ── ETF price fetcher ─────────────────────────────────────────────────────────
def _fetch_etf_prices(tickers: List[str]) -> Dict[str, float]:
    """Fetch current prices for ETF tickers via yfinance."""
    try:
        import yfinance as yf
        data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
        prices = {}
        for t in tickers:
            try:
                col = ("Close", t) if isinstance(data.columns, type(data.columns)) and len(data.columns.names) > 1 else "Close"
                prices[t] = float(data[col].dropna().iloc[-1])
            except Exception:
                prices[t] = 0.0
        return prices
    except Exception as e:
        logger.warning(f"ETF price fetch failed: {e}")
        return {}


# ── Core Portfolio State ───────────────────────────────────────────────────────
class VirtualPortfolio:
    """
    Tracks one virtual account. Serializes to/from the shared JSON state.
    """
    def __init__(self, strategy: str, initial: float):
        self.strategy  = strategy
        self.initial   = initial
        self.cash      = initial
        self.positions: List[dict] = []  # Each: {type, symbol, strike, expiry, contracts, entry_px, entry_date}
        self.etf_holdings: Dict[str, float] = {}  # {symbol: dollar_value}
        self.nav_history: List[dict] = []  # [{date, nav}]
        self.peak_nav  = initial
        self.max_drawdown = 0.0
        self.trade_count  = 0
        self.inception_date: str = date.today().isoformat()

    # ── Serialization ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "strategy":       self.strategy,
            "initial":        self.initial,
            "cash":           round(self.cash, 2),
            "positions":      self.positions,
            "etf_holdings":   self.etf_holdings,
            "nav_history":    self.nav_history[-500:],  # Keep last 500 days
            "peak_nav":       round(self.peak_nav, 2),
            "max_drawdown":   round(self.max_drawdown, 4),
            "trade_count":    self.trade_count,
            "inception_date": self.inception_date,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VirtualPortfolio":
        vp = cls(d["strategy"], d["initial"])
        vp.cash          = d.get("cash", d["initial"])
        vp.positions     = d.get("positions", [])
        vp.etf_holdings  = d.get("etf_holdings", {})
        vp.nav_history   = d.get("nav_history", [])
        vp.peak_nav      = d.get("peak_nav", d["initial"])
        vp.max_drawdown  = d.get("max_drawdown", 0.0)
        vp.trade_count   = d.get("trade_count", 0)
        vp.inception_date = d.get("inception_date", date.today().isoformat())
        return vp

    # ── LEAPS Operations ──────────────────────────────────────────────────────
    def leaps_enter(
        self,
        spot: float,
        strike: float,
        expiry_date: str,
        entry_px: float,
        contracts: int,
        regime: str,
        confidence: float,
    ) -> bool:
        """Open a new LEAPS position. Returns True if sufficient cash."""
        cost = contracts * 100 * entry_px
        if cost > self.cash:
            logger.warning(f"[{self.strategy}] Insufficient cash for LEAPS entry: need ${cost:.0f}, have ${self.cash:.0f}")
            return False
        self.cash -= cost
        self.positions.append({
            "type":       "LEAPS_CALL",
            "symbol":     "QQQ",
            "strike":     round(strike, 2),
            "expiry":     expiry_date,
            "contracts":  contracts,
            "entry_px":   round(entry_px, 4),
            "entry_spot": round(spot, 2),
            "entry_date": date.today().isoformat(),
            "regime":     regime,
            "confidence": round(confidence, 3),
        })
        self.trade_count += 1
        logger.info(f"[{self.strategy}] LEAPS ENTER | strike={strike:.1f} expiry={expiry_date} px=${entry_px:.2f} x{contracts} contracts | cost=${cost:.0f}")
        return True

    def leaps_exit(self, exit_px: float, reason: str = "signal") -> float:
        """Close ALL open LEAPS positions at exit_px. Returns total proceeds."""
        total_proceeds = 0.0
        remaining = []
        for pos in self.positions:
            if pos["type"] == "LEAPS_CALL":
                proceeds = pos["contracts"] * 100 * exit_px
                self.cash += proceeds
                total_proceeds += proceeds
                pnl = proceeds - pos["contracts"] * 100 * pos["entry_px"]
                logger.info(f"[{self.strategy}] LEAPS EXIT | px=${exit_px:.2f} proceeds=${proceeds:.0f} pnl=${pnl:.0f} reason={reason}")
            else:
                remaining.append(pos)
        self.positions = remaining
        return total_proceeds

    def leaps_mtm(self, spot: float, iv: float, rf: float = 0.045) -> float:
        """Mark-to-market LEAPS positions. Returns total position market value."""
        today = date.today()
        total_mv = 0.0
        for pos in self.positions:
            if pos["type"] != "LEAPS_CALL":
                continue
            try:
                expiry = date.fromisoformat(pos["expiry"])
                T = max((expiry - today).days / 365.0, 1 / 365.0)
                mv = _bs_call_price(spot, pos["strike"], T, rf, iv) * pos["contracts"] * 100
                pos["current_px"]    = round(mv / (pos["contracts"] * 100), 4)
                pos["current_mv"]    = round(mv, 2)
                pos["unrealized_pnl"] = round(mv - pos["contracts"] * 100 * pos["entry_px"], 2)
                total_mv += mv
            except Exception as e:
                logger.warning(f"MTM pricing error: {e}")
        return total_mv

    # ── TurboCore / ETF Rebalance Operations ──────────────────────────────────
    def etf_rebalance(self, alloc_dict: Dict[str, float], prices: Dict[str, float]):
        """
        Simulate a TurboCore rebalance at live market prices.
        alloc_dict: {symbol: fraction} e.g. {"TQQQ": 0.7, "SGOV": 0.3}
        prices: {symbol: price}
        """
        nav = self.etf_nav(prices)
        self.etf_holdings = {}
        for symbol, frac in alloc_dict.items():
            self.etf_holdings[symbol] = round(nav * frac, 2)
        self.cash = 0.0  # All deployed
        self.trade_count += 1
        logger.info(f"[{self.strategy}] ETF REBALANCE | nav=${nav:.0f} | {alloc_dict}")

    def etf_nav(self, prices: Dict[str, float] = None) -> float:
        """Current NAV for ETF portfolio (cash + holdings at current prices)."""
        if not self.etf_holdings:
            return self.cash
        # Holdings are stored as dollar values at last rebalance;
        # scale by price change ratio since rebalance
        if prices is None:
            return sum(self.etf_holdings.values()) + self.cash
        # Approximate MTM for ETF portfolios — price-weight since last rebalance
        # We store dollar value, not shares, for simplicity
        return sum(self.etf_holdings.values()) + self.cash

    # ── NAV Snapshot ──────────────────────────────────────────────────────────
    def record_nav(self, nav: float):
        """Record today's NAV to history."""
        today_str = date.today().isoformat()
        # Avoid duplicate entries for the same day
        if self.nav_history and self.nav_history[-1]["date"] == today_str:
            self.nav_history[-1]["nav"] = round(nav, 2)
        else:
            self.nav_history.append({"date": today_str, "nav": round(nav, 2)})

        # Update peak and max drawdown
        if nav > self.peak_nav:
            self.peak_nav = nav
        if self.peak_nav > 0:
            dd = (nav - self.peak_nav) / self.peak_nav
            self.max_drawdown = min(self.max_drawdown, dd)

    def get_stats(self, current_nav: float) -> dict:
        """Compute summary statistics."""
        total_return = (current_nav / self.initial - 1) * 100
        inception    = date.fromisoformat(self.inception_date)
        years        = max((date.today() - inception).days / 365.25, 1 / 365.25)
        cagr         = ((current_nav / self.initial) ** (1 / years) - 1) * 100
        return {
            "strategy":     self.strategy,
            "initial":      self.initial,
            "nav":          round(current_nav, 2),
            "total_return": round(total_return, 2),
            "cagr":         round(cagr, 2),
            "max_drawdown": round(self.max_drawdown * 100, 2),
            "trade_count":  self.trade_count,
            "inception_date": self.inception_date,
            "nav_history":  self.nav_history,
        }


# ── Portfolio Manager (singleton-style, file-backed) ──────────────────────────
class PortfolioManager:
    """Manages all 3 virtual accounts from a single JSON state file."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        NAV_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        self.portfolios: Dict[str, VirtualPortfolio] = {}
        self._load()

    def _load(self):
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                for strategy, d in state.items():
                    self.portfolios[strategy] = VirtualPortfolio.from_dict(d)
                logger.info(f"Loaded virtual portfolio state for {list(self.portfolios.keys())}")
            except Exception as e:
                logger.warning(f"Could not load portfolio state: {e} — initializing fresh.")
        # Initialize any missing strategies
        for strategy, initial in INITIAL_PRINCIPALS.items():
            if strategy not in self.portfolios:
                logger.info(f"Initializing fresh virtual account: {strategy} @ ${initial:,.0f}")
                self.portfolios[strategy] = VirtualPortfolio(strategy, initial)

    def save(self):
        """Persist all portfolio state to disk."""
        state = {k: v.to_dict() for k, v in self.portfolios.items()}
        STATE_FILE.write_text(json.dumps(state, indent=2))

    def get(self, strategy: str) -> VirtualPortfolio:
        if strategy not in self.portfolios:
            self.portfolios[strategy] = VirtualPortfolio(strategy, INITIAL_PRINCIPALS.get(strategy, 25_000))
        return self.portfolios[strategy]

    # ── Daily MTM update for LEAPS account ────────────────────────────────────
    def leaps_daily_mtm(self, spot: float, iv: float, rf: float = 0.045):
        """Called daily at 3 PM to update LEAPS account MTM."""
        vp = self.get("QQQ_LEAPS")
        positions_mv = vp.leaps_mtm(spot, iv, rf)
        nav = vp.cash + positions_mv
        vp.record_nav(nav)
        logger.info(f"[QQQ_LEAPS] MTM | spot=${spot:.2f} iv={iv:.2f} cash=${vp.cash:.0f} positions_mv=${positions_mv:.0f} nav=${nav:.0f}")
        self.save()
        return nav

    # ── Daily ETF MTM for TurboCore accounts ──────────────────────────────────
    def etf_daily_mtm(self, strategy: str, prices: Dict[str, float] = None):
        """Called daily for TurboCore / TurboCore Pro MTM."""
        vp = self.get(strategy)
        nav = vp.etf_nav(prices)
        vp.record_nav(nav)
        logger.info(f"[{strategy}] ETF MTM | nav=${nav:.0f}")
        self.save()
        return nav

    # ── Push public JSON to Vercel ─────────────────────────────────────────────
    def publish_public_snapshot(self):
        """
        Write the 5-day-delayed public snapshot and push to Vercel.
        """
        cutoff = date.today() - timedelta(days=PUBLIC_DELAY_DAYS)
        cutoff_str = cutoff.isoformat()

        public_accounts = []
        for strategy, vp in self.portfolios.items():
            # Filter nav history to ≤ cutoff (5-day delay)
            delayed_history = [h for h in vp.nav_history if h["date"] <= cutoff_str]
            if not delayed_history:
                delayed_nav = vp.initial
            else:
                delayed_nav = delayed_history[-1]["nav"]

            inception = date.fromisoformat(vp.inception_date)
            years = max((cutoff - inception).days / 365.25, 1 / 365.25)
            cagr = ((delayed_nav / vp.initial) ** (1 / years) - 1) * 100 if vp.initial > 0 else 0

            # Max drawdown from delayed history
            peak = vp.initial
            max_dd = 0.0
            for h in delayed_history:
                n = h["nav"]
                if n > peak:
                    peak = n
                if peak > 0:
                    dd = (n - peak) / peak
                    max_dd = min(max_dd, dd)

            DISPLAY_NAMES = {
                "TQQQ_TURBOCORE": "TurboCore",
                "TURBOCORE_PRO":  "TurboCore Pro",
                "QQQ_LEAPS":      "QQQ LEAPS",
            }

            public_accounts.append({
                "strategy":     strategy,
                "name":         DISPLAY_NAMES.get(strategy, strategy),
                "initial":      vp.initial,
                "nav":          round(delayed_nav, 2),
                "total_return": round((delayed_nav / vp.initial - 1) * 100, 2),
                "cagr":         round(cagr, 2),
                "max_drawdown": round(max_dd * 100, 2),
                "trade_count":  vp.trade_count,
                "inception_date": vp.inception_date,
                "last_data_date": delayed_history[-1]["date"] if delayed_history else None,
                "nav_history":  delayed_history[-180:],  # Last 6 months for sparkline
            })

        snapshot = {
            "accounts":     public_accounts,
            "delay_days":   PUBLIC_DELAY_DAYS,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "data_through": cutoff_str,
        }

        PUBLIC_FILE.write_text(json.dumps(snapshot, indent=2))
        logger.info(f"Public snapshot written to {PUBLIC_FILE} (delayed through {cutoff_str})")

        # Push to Vercel
        vercel_url  = os.environ.get("VERCEL_INTERNAL_URL", "https://trademind.bot")
        secret_key  = os.environ.get("INTERNAL_API_SECRET", "dev_secret_key")
        try:
            resp = requests.post(
                f"{vercel_url}/api/internal/virtual-portfolio/update",
                json=snapshot,
                headers={"Authorization": f"Bearer {secret_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Virtual portfolio snapshot pushed to Vercel")
            else:
                logger.warning(f"Vercel push returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Could not push snapshot to Vercel (non-fatal): {e}")

        return snapshot


# ── Module-level singleton ─────────────────────────────────────────────────────
_manager: Optional[PortfolioManager] = None

def get_portfolio_manager() -> PortfolioManager:
    global _manager
    if _manager is None:
        _manager = PortfolioManager()
    return _manager
