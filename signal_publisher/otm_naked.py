"""
OTM Naked Options Signal Publisher
===================================
Saves ENTER/EXIT signals to PostgreSQL from the scanner.
"""
import logging
from datetime import datetime, timedelta
import pytz
import uuid

logger = logging.getLogger(__name__)


def publish_otm_naked_signals(signals: list) -> list:
    """
    Publish a batch of OTM Naked signals to PostgreSQL.
    Signals are VIRTUAL ONLY — no auto-execution hook yet.
    """
    if not signals:
        return []

    et = pytz.timezone("US/Eastern")
    now_et = datetime.now(et)
    
    # Signals expire at 3 PM ET next trading day
    next_day = now_et + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    expires_at = next_day.replace(hour=15, minute=0, second=0, microsecond=0)
    expires_at_utc = expires_at.astimezone(pytz.utc)

    db_signals = []
    
    for s in signals:
        action = s.get("action", "HOLD")
        symbol = s.get("symbol")
        option_type = s.get("option_type", "put")
        strike = s.get("strike", 0.0)
        contracts = s.get("contracts", 0)
        regime = s.get("regime", "UNKNOWN")
        confidence = s.get("confidence", 0.0)
        expiry_date = s.get("expiry_date", "")
        
        entry_px = s.get("entry_px", 0.0) if action == "ENTER" else 0.0
        exit_px = s.get("exit_px", 0.0) if action == "EXIT" else 0.0
        spot = s.get("spot", 0.0)
        vix = s.get("vix", 0.0)
        reason = s.get("reason", "")

        leg_type = f"naked_{option_type}"
        leg_symbol = f"{symbol}_{expiry_date.replace('-', '')}{option_type[0].upper()}{int(strike):05d}"
        
        data = {
            "id":          str(uuid.uuid4()),
            "timestamp":   datetime.utcnow().isoformat() + "Z",
            "symbol":      symbol,
            "strategy":    "OTM_NAKED",
            "type":        action,
            "action":      action,
            "direction":   "SHORT" if action == "ENTER" else ("CLOSE" if action == "EXIT" else "HOLD"),
            "regime":      regime,
            "confidence":  round(confidence, 4),
            "rationale":   f"VIX: {vix:.2f} | Spot: {spot:.2f}" + (f" | Reason: {reason}" if reason else ""),
            "expires_at":  expires_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cost":        -round(entry_px * 100 * contracts, 2) if action == "ENTER" else 0.0, # Credit received
            "capital_required": round(strike * 100 * contracts, 2), # Notional risk
            "virtual_only": True,   # Not auto-executing yet
            "auto_execute": False,  
            
            "strike":      round(strike, 2),
            "expiry":      expiry_date,
            "entry_px":    round(entry_px, 4),
            "contracts":   contracts,
            "delta":       0.0, # Approximated
            "spot":        round(spot, 2),
            "exit_px":     round(exit_px, 4),
            "exit_reason": reason,

            "legs": [{
                "symbol":    leg_symbol,
                "action":    action,
                "strike":    strike,
                "expiry":    expiry_date,
                "delta":     0.0,
                "contracts": contracts,
                "leg_type":  leg_type,
            }],
        }
        db_signals.append(data)

    try:
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        try:
            for data in db_signals:
                repo.save_signal(data)
                logger.info(f"[OTM_NAKED] Signal saved: {data['symbol']} {data['action']} | regime={data['regime']}")
                
                # We can add email / Whop notifications here later
        finally:
            repo.session.close()
    except Exception as e:
        logger.error(f"[OTM_NAKED] DB save failed: {e}")

    return db_signals
