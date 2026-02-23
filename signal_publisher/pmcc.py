import logging
from typing import Optional
from datetime import datetime
import pytz

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from signal_publisher.websocket_client import broadcast_to_channel
from src.pmcc.pmcc_signal_generator import PMCCEntrySignal, PMCCShortCallSignal

logger = logging.getLogger(__name__)

def publish_pmcc_entry_signal(signal: PMCCEntrySignal, **kwargs) -> bool:
    """
    Publish PMCC entry signal to WebSocket channels AND save to database.
    
    Args:
        signal: PMCCEntrySignal dataclass
        
    Returns:
        True if broadcast to at least one channel succeeded
    """
    try:
        data = signal.to_dict()
        data['strategy'] = 'pmcc'
        data['signal_type'] = 'entry'
        
        # Calculate expiration: Market close today (16:00 ET)
        try:
            ny_tz = pytz.timezone('US/Eastern')
            now_ny = datetime.now(ny_tz)
            # Market close is 4 PM ET
            market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # Convert to UTC naive datetime for DB
            market_close_utc = market_close.astimezone(pytz.UTC).replace(tzinfo=None)
            data['expires_at'] = market_close_utc
        except Exception as e:
            logger.warning(f"Could not calculate exact market close UTC, using +4 hours: {e}")
            data['expires_at'] = datetime.utcnow() + timedelta(hours=4)
            
        success_pmcc = broadcast_to_channel('pmcc_all', data)
        success_entry = broadcast_to_channel('pmcc_entry', data)
        
        # Save to DB (Assuming standard SignalRepository handles generic signals for UI)
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            repo.save_signal(data)
            logger.info(f"✅ PMCC entry signal saved to database: {signal.symbol}")
            
            # Execute Auto-Approve check in background (non-blocking style)
            from auto_approve import auto_approve_signal
            try:
                auto_approve_signal(data, user_refresh_token=kwargs.get('user_refresh_token'))
            except Exception as auto_approve_error:
                logger.error(f"❌ Auto-approve failed for PMCC {signal.symbol}: {auto_approve_error}")
                
        except Exception as db_error:
            logger.warning(f"⚠️ Failed to save to DB (signal will still broadcast): {db_error}")
            
        return success_pmcc or success_entry
        
    except Exception as e:
        logger.error(f"Failed to publish PMCC entry signal: {e}")
        return False


def publish_pmcc_cycle_signal(signal: PMCCShortCallSignal, **kwargs) -> bool:
    """
    Publish PMCC short call cycle signal to WebSocket channels.
    """
    try:
        data = signal.to_dict()
        data['strategy'] = 'pmcc'
        data['signal_type'] = 'cycle'
        
        # Calculate expiration: Market close today (16:00 ET)
        try:
            ny_tz = pytz.timezone('US/Eastern')
            now_ny = datetime.now(ny_tz)
            # Market close is 4 PM ET
            market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # Convert to UTC naive datetime for DB
            market_close_utc = market_close.astimezone(pytz.UTC).replace(tzinfo=None)
            data['expires_at'] = market_close_utc
        except Exception as e:
            logger.warning(f"Could not calculate exact market close UTC, using +4 hours: {e}")
            data['expires_at'] = datetime.utcnow() + timedelta(hours=4)
            
        success_pmcc = broadcast_to_channel('pmcc_all', data)
        success_cycle = broadcast_to_channel('pmcc_cycle', data)
        
        return success_pmcc or success_cycle
        
    except Exception as e:
        logger.error(f"Failed to publish PMCC cycle signal: {e}")
        return False
