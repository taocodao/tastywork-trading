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
    tiers: dict = None,   # {"conservative": {...}, "moderate": {...}, "aggressive": {...}}
) -> dict:
    """
    Publish QQQ LEAPS signal to PostgreSQL.
    Signal is VIRTUAL ONLY — no auto-execution hook.
    """
    # Callers pass None for price fields on HOLD/NO-ACTION days; coerce so the
    # payload math below never sees None.
    strike    = float(strike or 0.0)
    entry_px  = float(entry_px or 0.0)
    contracts = int(contracts or 0)
    delta     = float(delta or 0.0)
    exit_px   = float(exit_px or 0.0)
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

        # Per-risk-tier entry/sizing variants — the app selects the tier
        # matching each account's configured risk level.
        "tiers": tiers or {},

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

            # ── Fan out to per-account virtual execution ──────────────────
            # The app's notify route runs fanoutSignal() only when signal_id
            # is present — this generates per-account orders, pre-executes
            # them into each virtual account, and emails sized instructions.
            try:
                import os as _os, requests as _requests
                _secret = _os.environ.get("INTERNAL_API_SECRET", "")
                _res = _requests.post(
                    "https://www.trademind.bot/api/signals/notify",
                    json={"strategy": "QQQ_LEAPS", "signal_id": data.get("id")},
                    headers={"Authorization": f"Bearer {_secret}"} if _secret else {},
                    timeout=15,
                )
                logger.info(f"[QQQ_LEAPS] Fan-out notify status={_res.status_code} signal_id={data.get('id')}")
            except Exception as fanout_err:
                logger.warning(f"[QQQ_LEAPS] Fan-out notify failed (non-fatal): {fanout_err}")

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


def publish_qqq_leaps_pmcc_signal(pmcc_signal) -> dict:
    """
    Publish a PMCC overlay signal (short-call management on an open LEAPS).

    Saves to PostgreSQL and triggers the app fan-out so subscribed virtual
    accounts see the signal. No Whop post and no legacy email blast: PMCC is
    per-account position management, and the app fan-out is the canonical
    delivery path.

    Args:
        pmcc_signal: src.qqq_leaps.pmcc_manager.PMCCSignal dataclass
    """
    et = pytz.timezone("US/Eastern")
    now_et = datetime.now(et)
    # PMCC orders are day orders: expire at 4 PM ET today, or next trading
    # day if the market has already closed.
    expires_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_et >= expires_et:
        expires_et += timedelta(days=1)
        while expires_et.weekday() >= 5:
            expires_et += timedelta(days=1)
    expires_at_utc = expires_et.astimezone(pytz.utc)

    import uuid
    action = str(pmcc_signal.action)              # PMCC_ENTER / PMCC_ROLL_* / ...
    is_open = action == "PMCC_ENTER"

    def _occ(strike: float, expiry: str) -> str:
        return f"QQQ_{expiry.replace('-', '')}C{int(round(strike)):05d}"

    legs = []
    # Closing leg for rolls / management closes (existing short call)
    if not is_open and pmcc_signal.short_strike and pmcc_signal.short_expiry:
        legs.append({
            "symbol":    _occ(pmcc_signal.short_strike, pmcc_signal.short_expiry),
            "action":    "BUY_TO_CLOSE",
            "strike":    pmcc_signal.short_strike,
            "expiry":    pmcc_signal.short_expiry,
            "delta":     pmcc_signal.short_delta,
            "contracts": pmcc_signal.contracts,
            "leg_type":  "pmcc_short_call",
        })
    # Opening leg: ENTER uses short_*, rolls use new_*
    open_strike = pmcc_signal.short_strike if is_open else getattr(pmcc_signal, "new_strike", 0.0)
    open_expiry = pmcc_signal.short_expiry if is_open else getattr(pmcc_signal, "new_expiry", "")
    open_delta  = pmcc_signal.short_delta  if is_open else getattr(pmcc_signal, "new_delta", 0.0)
    if open_strike and open_expiry:
        legs.append({
            "symbol":    _occ(open_strike, open_expiry),
            "action":    "SELL_TO_OPEN",
            "strike":    open_strike,
            "expiry":    open_expiry,
            "delta":     open_delta,
            "contracts": pmcc_signal.contracts,
            "leg_type":  "pmcc_short_call",
        })

    data = {
        "id":          str(uuid.uuid4()),
        "timestamp":   datetime.utcnow().isoformat() + "Z",
        "symbol":      "QQQ",
        "strategy":    "QQQ_LEAPS",
        "type":        action,
        "action":      action,
        "direction":   "SHORT" if is_open else "CLOSE",
        "regime":      "",
        "confidence":  round(float(pmcc_signal.confidence), 4),
        "rationale":   pmcc_signal.rationale,
        "expires_at":  expires_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cost":        0.0,
        "capital_required": 0.0,
        "virtual_only": False,
        "auto_execute": True,

        # Short call specifics
        "short_strike": round(float(pmcc_signal.short_strike), 2),
        "short_expiry": pmcc_signal.short_expiry,
        "short_delta":  round(float(pmcc_signal.short_delta), 4),
        "short_dte":    int(pmcc_signal.short_dte),
        "limit_price":  round(float(pmcc_signal.limit_price), 4),
        "contracts":    int(pmcc_signal.contracts),

        # Roll target (when applicable)
        "new_strike":   round(float(getattr(pmcc_signal, "new_strike", 0.0)), 2),
        "new_expiry":   getattr(pmcc_signal, "new_expiry", ""),
        "new_delta":    round(float(getattr(pmcc_signal, "new_delta", 0.0)), 4),

        # Backend bookkeeping
        "leaps_position_id": pmcc_signal.leaps_position_id,
        "user_id":           pmcc_signal.user_id,

        "legs": legs,
    }

    try:
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        try:
            repo.save_signal(data)
            logger.info(f"[QQQ_LEAPS] PMCC signal saved: {action} | {pmcc_signal.rationale[:80]}")

            # ── Fan out to per-account virtual execution ──────────────────
            try:
                import os as _os, requests as _requests
                _secret = _os.environ.get("INTERNAL_API_SECRET", "")
                _res = _requests.post(
                    "https://www.trademind.bot/api/signals/notify",
                    json={"strategy": "QQQ_LEAPS", "signal_id": data.get("id")},
                    headers={"Authorization": f"Bearer {_secret}"} if _secret else {},
                    timeout=15,
                )
                logger.info(f"[QQQ_LEAPS] PMCC fan-out notify status={_res.status_code} signal_id={data.get('id')}")
            except Exception as fanout_err:
                logger.warning(f"[QQQ_LEAPS] PMCC fan-out notify failed (non-fatal): {fanout_err}")
        finally:
            repo.session.close()
    except Exception as e:
        logger.error(f"[QQQ_LEAPS] PMCC DB save failed: {e}")

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
