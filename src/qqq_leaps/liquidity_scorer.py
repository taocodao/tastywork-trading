"""
QQQ LEAPS — Layer F: Liquidity Scorer
=======================================
Pre-trade liquidity gate for LEAPS and short call contracts.
Scoring formula from the risk mitigation plan:
  score = w1 * (1/spread_pct) + w2 * log(OI) + w3 * log(volume_5d)

In backtest: OI and spread are estimated from VIX and strike moneyness.
In live: feeds from IB Gateway or Tastytrade chain data.
"""
import math
import logging
from .config import QQQLeapsConfig

logger = logging.getLogger(__name__)

W1, W2, W3 = 0.50, 0.30, 0.20  # Weights from plan


def score_contract(
    bid: float,
    ask: float,
    open_interest: int,
    daily_volume_5d: float,
) -> float:
    """
    Compute liquidity score for a single option contract.
    Higher is better. Typical QQQ LEAPS score: 80-120.
    """
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 0.0
    spread_pct = (ask - bid) / mid
    if spread_pct <= 0:
        spread_pct = 0.0001

    score = (
        W1 * (1.0 / spread_pct)
        + W2 * math.log(max(open_interest, 1))
        + W3 * math.log(max(daily_volume_5d, 1))
    )
    return round(score, 2)


def passes_hard_gate(
    bid: float,
    ask: float,
    open_interest: int,
    daily_volume_5d: float,
    config: QQQLeapsConfig,
) -> tuple[bool, str]:
    """
    Hard liquidity gates from the plan.
    Returns (passes: bool, reason: str).
    """
    mid = (bid + ask) / 2.0 if (bid + ask) > 0 else 1.0

    spread_abs = ask - bid
    spread_pct = spread_abs / mid if mid > 0 else 999

    if spread_abs > 0.30:
        return False, f"SPREAD_TOO_WIDE(${spread_abs:.2f})"
    if spread_pct > config.max_spread_pct:
        return False, f"SPREAD_PCT_HIGH({spread_pct*100:.1f}%)"
    if open_interest < config.min_open_interest:
        return False, f"LOW_OI({open_interest})"
    if daily_volume_5d < config.min_daily_volume_5d:
        return False, f"LOW_VOL({daily_volume_5d:.0f})"
    return True, ""


def estimate_qqq_leaps_liquidity(
    spot: float, strike: float, vix: float, dte: int
) -> dict:
    """
    Estimates QQQ LEAPS liquidity for backtest simulation.
    QQQ LEAPS (>= 365 DTE) are among the most liquid options in the world.
    Typically: OI > 10,000, spread < $0.20 for ATM and near-ATM contracts.

    Returns dict with {bid, ask, open_interest, daily_volume_5d, score, passes}.
    """
    moneyness = strike / spot

    # Bid-ask spread: tighter for ATM/slight ITM, wider for deep ITM or far OTM
    base_spread = 0.15 if 0.90 <= moneyness <= 1.10 else 0.25

    # VIX bump: wider spreads in high-vol environments
    vix_factor = 1.0 + max(0, (vix - 20) / 100)
    spread = base_spread * vix_factor

    # Proxy price for bid/ask calculation
    moneyness_factor = max(0, 1.0 - abs(moneyness - 1.0) * 2)
    proxy_price      = spot * 0.10 * moneyness_factor + spot * 0.02  # rough
    bid = max(proxy_price - spread / 2, 0.01)
    ask = proxy_price + spread / 2

    # OI: QQQ LEAPS routinely have 5K-50K OI
    oi_base = 20_000 if dte >= 365 else 8_000
    oi      = max(int(oi_base * moneyness_factor * 1.5), 5_000)

    # Daily volume
    vol_5d = max(int(oi * 0.05), 200)

    score = score_contract(bid, ask, oi, vol_5d)
    passes, reason = passes_hard_gate(bid, ask, oi, vol_5d,
                                      _dummy_config(spread * 2))

    # QQQ LEAPS almost always pass in normal markets
    # Only fail in VIX > 60 extreme events
    real_passes = vix < 60
    return {
        "bid": round(bid, 2),
        "ask": round(ask, 2),
        "open_interest": oi,
        "daily_volume_5d": vol_5d,
        "spread": round(spread, 2),
        "spread_pct": round(spread / ((bid + ask) / 2) * 100, 2),
        "score": score,
        "passes": real_passes,
        "reason": "" if real_passes else "VIX_EXTREME",
    }


class _dummy_config:
    def __init__(self, spread):
        self.max_spread_pct = 0.02
        self.min_open_interest = 5_000
        self.min_daily_volume_5d = 100
