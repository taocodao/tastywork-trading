from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict
import pytz

from email_notifications.resend_sender import notify_signal_subscribers

@dataclass
class TurboCoreEntrySignal:
    timestamp: str
    symbol: str
    action: str  # e.g., 'REBALANCE'
    strategy: str = "TQQQ_TURBOCORE"
    
    # ML Outputs
    ml_regime: str = "SIDEWAYS"
    ml_confidence: float = 0.5
    
    # Base Triggers
    ema_signal: int = 0
    sma200_gate: bool = True
    
    # Portfolio Allocation Matrix (%) - dynamically passed from allocator
    allocations: dict = field(default_factory=dict)
    
    # Optional metadata
    rationale: str = ""

    # Set to True on the first (ML-regime) publish when an IV-Switching overlay
    # is still computing and will be published moments later.
    iv_switching_pending: bool = False
    
    def to_dict(self) -> dict:
        import uuid

        # TurboCore signals expire at 3:00 PM ET the next trading day
        # (the scheduler runs at 3PM, so the next scan replaces this signal)
        et = pytz.timezone('US/Eastern')
        now_et = datetime.now(et)
        next_day = now_et + timedelta(days=1)
        # Skip to Monday if next day is a weekend
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        expires_at_et = next_day.replace(hour=15, minute=0, second=0, microsecond=0)
        expires_at_utc = expires_at_et.astimezone(pytz.utc)

        return {
            "id": str(uuid.uuid4()),
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "action": self.action,
            "strategy": self.strategy,
            "type": "REBALANCE",  # Standardized for DB schema
            "direction": "LONG",  # We are always long something
            "confidence": self.ml_confidence,
            "rationale": self.rationale,
            "expires_at": expires_at_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),

            # Pack custom TurboCore fields into JSON structure
            # (Matches DB schema 'legs' or dynamic 'cost' fields on Vercel)
            "legs": [
                {"symbol": str(sym), "target_pct": float(pct)}
                for sym, pct in self.allocations.items()
            ],
            "cost": 0.0,
            "capital_required": 1000.0, # Dummy for UI compatibility initially
            "regime": self.ml_regime,
            "ema_signal": self.ema_signal,
            "sma200_gate": self.sma200_gate,
            "iv_switching_pending": self.iv_switching_pending,
        }

def publish_turbocore_rebalance_signal(
    regime: str,
    confidence: float,
    alloc_dict: Dict[str, float],
    rationale: str,
    ema_signal: int,
    sma200_gate: bool,
    strategy: str = "TQQQ_TURBOCORE",
    # ── IV-Switching options signal fields (optional) ─────────────────────
    legs_override: list = None,          # Raw order legs for options signals
    action_override: str = None,         # e.g., OPEN_CSP, OPEN_ZEBRA, OPEN_CCS
    user_id_override: str = None,        # Per-user routing for options signals
    iv_switching_order_id: str = None,   # FK to user_daily_orders.id
    cost_override: float = None,         # Limit price for options orders (overrides hardcoded 0.0)
    iv_switching_pending: bool = False,  # True when IV-Switching overlay is still computing
):
    import logging
    logger = logging.getLogger(__name__)

    sig = TurboCoreEntrySignal(
        timestamp=datetime.utcnow().isoformat() + "Z",
        symbol="TQQQ_PORT",
        action=action_override or "REBALANCE",
        strategy=strategy,
        ml_regime=regime,
        ml_confidence=confidence,
        allocations=alloc_dict,
        rationale=rationale,
        ema_signal=ema_signal,
        sma200_gate=sma200_gate,
        iv_switching_pending=iv_switching_pending,
    )

    data = sig.to_dict()

    # If options legs are provided, replace the allocations-based legs with the
    # actual option order legs (OCC symbols, qty, action) so the frontend
    # IVSwitchingSignalCard can render them correctly.
    if legs_override:
        data["legs"] = legs_override
        logger.info(f"Publishing TurboCore Signal: {action_override or regime} | Conf: {confidence:.2f} | Legs: {[l.get('symbol','?') for l in legs_override]}")
    else:
        logger.info(f"Publishing TurboCore Signal: {regime} | Conf: {confidence:.2f} | Legs: {list(alloc_dict.keys())}")

    # FIX: Override the hardcoded cost=0.0 with the actual limit price for options orders
    if cost_override is not None:
        data["cost"] = cost_override

    # Attach options routing fields to the DB row
    if iv_switching_order_id:
        data["iv_switching_order_id"] = iv_switching_order_id
    if user_id_override:
        data["user_id"] = user_id_override

    # Save to PostgreSQL
    try:
        from src.earnings_intelligence.database import SignalRepository, get_session
        repo = SignalRepository()
        try:
            repo.save_signal(data)
            logger.info("DB Save success: TurboCore Rebalance")

            # ── NEW: Notify email subscribers ─────────────────────────────
            try:
                # Skip email for the intermediate "pending" publish that fires while the
                # IV-Switching overlay is still computing. Only the final unified signal
                # (iv_switching_pending=False) should notify subscribers.
                if data.get("iv_switching_pending"):
                    logger.info("[Email] Skipping email — iv_switching_pending=True (intermediate publish)")
                else:
                    session = get_session()
                    # Determine tier filter based on strategy name
                    strategy = data.get("strategy", "")
                    tier_filter = (
                        "('TURBOCORE_PRO', 'BOTH_BUNDLE', 'turbocore_pro', 'both_bundle')"
                        if "PRO" in (strategy or "")
                        else "('TURBOCORE', 'BOTH_BUNDLE', 'turbocore', 'both_bundle')"
                    )
                    
                    rows = session.execute(
                        f"""SELECT email, first_name FROM user_settings
                            WHERE subscription_tier IN {tier_filter}
                              AND email IS NOT NULL
                              AND email_signal_alerts = TRUE"""
                    ).fetchall()
                    session.close()
                    subscribers = [{"email": r[0], "first_name": r[1]} for r in rows]
                    notify_signal_subscribers(data, subscribers)
            except Exception as email_err:
                logger.warning(f"[Email] Signal notification failed (non-fatal): {email_err}")
                
            # ── NEW: Fire Ghost Auto-Execution Webhook ────────────────────
            try:
                if data.get("iv_switching_pending"):
                    logger.info("[Ghost] Skipping auto-execute — iv_switching_pending=True (intermediate publish)")
                else:
                    import requests, os
                    logger.info(f"🤖 Firing Ghost Executor for Signal {data.get('id')}")
                    # Fallback to local host if dev
                    base_url = "https://trademind.bot" if os.environ.get("FLASK_ENV") != "development" else "http://localhost:3000"
                    secret_key = os.environ.get("INTERNAL_API_SECRET", "dev_secret_key")
                    res = requests.post(
                        f"{base_url}/api/internal/signals/{data.get('id', 'new')}/auto-execute",
                        json={"signal": data},
                        headers={"Authorization": f"Bearer {secret_key}"},
                        timeout=5
                    )
                    if res.status_code == 200:
                        logger.info(f"✅ Ghost Executor verified: {res.json().get('processed', 0)} users executed.")
                    else:
                        logger.warning(f"❌ Ghost Executor warning: status {res.status_code}")
            except Exception as ghost_err:
                logger.warning(f"[Ghost] Auto-execute trigger failed (non-fatal): {ghost_err}")
            # ── END NEW ───────────────────────────────────────────────────

        finally:
            repo.session.close()
    except Exception as e:
        logger.error(f"DB Save failed for TurboCore: {e}")

    return data

