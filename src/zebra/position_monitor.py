
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session
from models.user import User
from models.zebra_position import ZebraPosition
from models.db import get_db

from .client import ZebraClient
from .exit_engine import ZebraExitEngine
from tastytrade_utils import create_user_session, get_user_account

logger = logging.getLogger(__name__)

class ZebraPositionMonitor:
    def __init__(self):
        self.exit_engine = ZebraExitEngine()
        
    def check_all_users(self):
        """Iterate all users and check their open ZEBRA positions."""
        db_gen = get_db()
        db = next(db_gen)
        
        try:
            users = db.query(User).filter(User.is_active == True, User.zebra_enabled == True).all()
            logger.info(f"🔍 Monitoring ZEBRA positions for {len(users)} users...")
            
            for user in users:
                self._check_user_positions(user, db)
                
        except Exception as e:
            logger.error(f"Error in ZebraPositionMonitor: {e}")
        finally:
            db.close()
            
    def _check_user_positions(self, user: User, db: Session):
        """Check positions for a specific user."""
        positions = db.query(ZebraPosition).filter(
            ZebraPosition.user_id == user.id, 
            ZebraPosition.status == "OPEN"
        ).all()
        
        if not positions:
            return

        # Initialize client for this user
        try:
            if not user.tt_refresh_token:
                logger.debug(f"User {user.id} has no token, skipping positions.")
                return
                
            # Decrypt token (assuming util exists, otherwise use what we have)
            from api.services.encryption import decrypt_credential
            refresh_token = decrypt_credential(user.tt_refresh_token)
            
            session = create_user_session(refresh_token)
            account = get_user_account(session, user.tt_account_number)
            
            client = ZebraClient()
            client.session = session
            client.account = account
            
        except Exception as e:
            logger.error(f"Failed to init session for user {user.id}: {e}")
            return
            
        for pos in positions:
            self._process_position(pos, client, db)
            
    def _process_position(self, pos: ZebraPosition, client: ZebraClient, db: Session):
        """Evaluate exit criteria for a single position."""
        logger.info(f"Checking position {pos.symbol} for user {pos.user_id}")
        
        # 1. Get Live Price via Client
        # The position might be complex (2 Long calls, 1 Short call)
        # We need a way to get the *complex* price or underlying price.
        # ZebraClient.get_price? 
        # For now, let's use underlying price as proxy for some checks, 
        # but ideal is option structure price.
        
        # Determine regime (can be passed in or fetched)
        # Using placeholder 'NORMAL' for now or fetch from monitor
        from .regime_detector import RegimeDetector
        # This is expensive if instantiated every time. 
        # Better to pass it in. For now, assume 'NORMAL'.
        regime = "NORMAL" 
        
        # Get live data
        # We need current pnl, days held, etc.
        # We can ask TASTYTRADE for the position PnL directly!
        # Tastytrade 'get_positions' returns PnL.
        
        try:
            # Match database position to real TT position
            # This is tricky without exact correlation key (order id -> position)
            # But we can match by Symbol.
            tt_positions = client.get_zebra_positions() # This needs to be implemented/verified works
            
            # Find matching position
            match = next((p for p in tt_positions if p['symbol'] == pos.symbol), None)
            
            if not match:
                logger.warning(f"Position {pos.symbol} not found in Tastytrade! Marking CLOSED?")
                # Maybe closed manually?
                # For safety, verify history or check again later.
                return
                
            current_pnl = float(match.get('pnl', 0))
            pos.unrealized_pnl = current_pnl
            pos.current_price = float(match.get('mark_price', 0))
            
            # Update High Watermark
            if pos.high_watermark is None or current_pnl > pos.high_watermark:
                pos.high_watermark = current_pnl
            
            # Check Exit Engine
            # We need to construct a 'trade' object that ExitEngine expects
            trade_context = {
                "entry_date": pos.entry_date,
                "unrealized_pnl_pct": (current_pnl / pos.capital_deployed) if pos.capital_deployed else 0,
                "days_held": (datetime.now() - pos.entry_date).days,
                "regime": regime
            }
            
            should_exit, reason = self.exit_engine.check_exit(trade_context, current_pnl)
            
            if should_exit:
                logger.info(f"🚨 EXIT TRIGGERED for {pos.symbol}: {reason}")
                
                # Execute Exit
                # Need leg details to build close order.
                # Assuming standard ZEBRA structure... 
                # We need to store exact legs in DB to close correctly!
                # For now, assuming standard structure.
                
                # result = client.execute_zebra_exit(pos.symbol, ..., reason)
                # If success:
                # pos.status = "CLOSED"
                # pos.exit_date = datetime.now()
                # pos.exit_reason = reason
                # pos.realized_pnl = current_pnl
                
            db.commit()
            
        except Exception as e:
            logger.error(f"Error processing position {pos.symbol}: {e}")

