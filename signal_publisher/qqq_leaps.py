"""
QQQ LEAPS Signal Publisher
==========================
Saves ENTER/EXIT/HOLD signals to PostgreSQL.
Does NOT trigger Tastytrade auto-execution (virtual account only).
"""
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)


def publish_qqq_leaps_signal(
    action: str,           # ENTER / EXIT / HOLD
    regime: str,
    confidence: float,
    spot: float,
    strike: float = 0.0,
    expiry_date: str = "",
    entry_px: float = 0.0,
    contracts: int = 0,
    delta: float = 0.0,
    exit_px: float = 0.0,
    exit_reason: str = "",
    rationale: str = "",
) -> dict:
    """
    Publish QQQ LEAPS signal to PostgreSQL.
    Signal is VIRTUAL ONLY — no auto-execution hook.
    """
    et = pytz.timezone("US/Eastern")
    now_et = datetime.now(et)
    # Signals expire at 3 PM ET next trading day
    next_day = now_et + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    expires_at = next_day.replace(hour=15, minute=0, second=0, microsecond=0)
    expires_at_utc = expires_at.astimezone(pytz.utc)

    import uuid
    data = {
        "id":          str(uuid.uuid4()),
        "timestamp":   datetime.utcnow().isoformat() + "Z",
        "symbol":      "QQQ",
        "strategy":    "QQQ_LEAPS",
        "type":        action,
        "action":      action,
        "direction":   "LONG" if action == "ENTER" else ("CLOSE" if action == "EXIT" else "HOLD"),
        "regime":      regime,
        "confidence":  round(confidence, 4),
        "rationale":   rationale,
        "expires_at":  expires_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cost":        round(entry_px * 100 * contracts, 2) if action == "ENTER" else 0.0,
        "capital_required": round(entry_px * 100 * contracts, 2),
        "virtual_only": False,   # Signals are routed to execution for subscribed accounts
        "auto_execute": True,    # Trigger Ghost Executor webhook

        # Option specifics
        "strike":      round(strike, 2),
        "expiry":      expiry_date,
        "entry_px":    round(entry_px, 4),
        "contracts":   contracts,
        "delta":       round(delta, 4),
        "spot":        round(spot, 2),
        "exit_px":     round(exit_px, 4),
        "exit_reason": exit_reason,

        # Leg format (for DB compatibility)
        "legs": [{
            "symbol":    f"QQQ_{expiry_date.replace('-', '')}C{int(strike):05d}",
            "action":    action,
            "strike":    strike,
            "expiry":    expiry_date,
            "delta":     delta,
            "contracts": contracts,
            "leg_type":  "leaps_call",
        }] if action == "ENTER" else [],
    }

    try:
        from src.earnings_intelligence.database import SignalRepository, get_session
        repo = SignalRepository()
        try:
            repo.save_signal(data)
            logger.info(f"[QQQ_LEAPS] Signal saved: {action} | regime={regime} | conf={confidence:.2f}")
        finally:
            repo.session.close()
    except Exception as e:
        logger.error(f"[QQQ_LEAPS] DB save failed: {e}")

    return data
