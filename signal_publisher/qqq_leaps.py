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

            # ── Notify email subscribers ────────────────────────────────────
            try:
                from email_notifications.resend_sender import notify_signal_subscribers
                session = get_session()
                rows = session.execute(
                    """SELECT email, first_name FROM user_settings
                       WHERE subscription_tier IN ('TURBOCORE_PRO', 'BOTH_BUNDLE', 'turbocore_pro', 'both_bundle')
                         AND email IS NOT NULL
                         AND email_signal_alerts = TRUE"""
                ).fetchall()
                session.close()
                subscribers = [{"email": r[0], "first_name": r[1]} for r in rows]
                # Override strategy_label in the signal data so email header reads correctly
                email_data = dict(data)
                email_data["strategy"] = "TQQQ_TURBOCORE_PRO"   # triggers "TurboCore Pro" label
                notify_signal_subscribers(email_data, subscribers)
                logger.info(f"[QQQ_LEAPS] Email sent to {len(subscribers)} subscriber(s)")
            except Exception as email_err:
                logger.warning(f"[QQQ_LEAPS] Email notification failed (non-fatal): {email_err}")

            # ── Post to Whop Pro Strategy channel (non-fatal) ─────────────
            try:
                _post_leaps_to_whop(data)
            except Exception as whop_err:
                logger.warning(f"[Whop] LEAPS channel post failed (non-fatal): {whop_err}")

        finally:
            repo.session.close()
    except Exception as e:
        logger.error(f"[QQQ_LEAPS] DB save failed: {e}")

    return data


def _post_leaps_to_whop(signal_data: dict) -> None:
    """Post LEAPS signal to the Whop Pro Strategy Chat channel."""
    import os, requests

    api_key    = os.getenv("WHOP_API_KEY", "")
    channel_id = os.getenv("WHOP_PRO_CHANNEL_ID", "")
    if not api_key or not channel_id:
        logger.warning("[Whop] WHOP_PRO_CHANNEL_ID not set — skipping LEAPS post")
        return

    regime     = signal_data.get("regime", "UNKNOWN")
    confidence = int(float(signal_data.get("confidence", 0)) * 100)
    action     = signal_data.get("action", "HOLD")
    legs       = signal_data.get("legs", [])

    # Find the LEAPS call leg
    leaps_leg = next((l for l in legs if l.get("leg_type") == "leaps_call"), None)
    if leaps_leg:
        strike    = leaps_leg.get("strike", 0)
        expiry    = leaps_leg.get("expiry", "—")
        contracts = leaps_leg.get("contracts", 0)
        delta     = leaps_leg.get("delta", 0)
        leg_str   = f"QQQ ${strike:.0f} Call | Exp {expiry} | Δ {delta:.2f} | {contracts} contracts"
    else:
        leg_str = action.replace("_", " ").title()

    action_emoji = "🟢" if action == "ENTER" else ("🔴" if action == "EXIT" else "⚪️")

    content = (
        f"{action_emoji} **QQQ LEAPS Signal — {action}**\n"
        f"Regime: **{regime}** | Confidence: **{confidence}%**\n"
        f"{leg_str}\n"
        f"_Full brief and execution details in the TradeMind app._\n\n"
        f"*Educational analysis only. Not personalized investment advice.*"
    )

    try:
        res = requests.post(
            f"https://api.whop.com/v5/channels/{channel_id}/messages",
            json={"content": content},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=8,
        )
        if res.ok:
            logger.info(f"[Whop] ✅ LEAPS signal posted to Pro channel ({res.status_code})")
        else:
            logger.warning(f"[Whop] Pro channel post failed: {res.status_code} — {res.text[:200]}")
    except Exception as e:
        logger.warning(f"[Whop] LEAPS request error: {e}")
