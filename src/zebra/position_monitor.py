
import logging
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)

# Graceful fallback for DB/models that may not be available on all environments
try:
    from sqlalchemy.orm import Session
    from models.user import User
    from models.zebra_position import ZebraPosition
    from models.db import get_db
    from tastytrade_utils import create_user_session, get_user_account
    DB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DB/models not available ({e}). Per-user position monitoring disabled.")
    DB_AVAILABLE = False

from .client import ZebraClient
from .exit_engine import ZebraExitEngine


class ZebraPositionMonitor:
    """
    Monitors open ZEBRA positions for all users and triggers exits via the exit engine.
    Falls back gracefully if DB/models are not available (e.g., on EC2 without full stack).
    """

    def __init__(self):
        self.exit_engine = ZebraExitEngine()

    def check_all_users(self):
        """Iterate all users and check their open ZEBRA positions."""
        if not DB_AVAILABLE:
            logger.warning("Position monitoring skipped — DB/models not available on this host.")
            return

        db_gen = get_db()
        db = next(db_gen)

        try:
            users = db.query(User).filter(User.is_active == True).all()
            logger.info(f"Checking positions for {len(users)} users...")

            for user in users:
                try:
                    self._check_user_positions(user, db)
                except Exception as e:
                    logger.error(f"Error checking positions for user {user.id}: {e}")
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

    def _check_user_positions(self, user, db):
        """Check and manage open ZEBRA positions for a single user."""
        positions = db.query(ZebraPosition).filter(
            ZebraPosition.user_id == user.id,
            ZebraPosition.status == 'open'
        ).all()

        if not positions:
            return

        logger.info(f"User {user.id}: {len(positions)} open ZEBRA position(s)")

        try:
            session = create_user_session(user)
            account = get_user_account(session, user)
        except Exception as e:
            logger.error(f"Could not create session for user {user.id}: {e}")
            return

        client = ZebraClient(session=session, account=account)

        for pos in positions:
            try:
                self._evaluate_position(pos, client, db)
            except Exception as e:
                logger.error(f"Error evaluating position {pos.id}: {e}")

    def _evaluate_position(self, pos, client: ZebraClient, db):
        """Evaluate a single position and take action if needed."""
        symbol = pos.symbol
        df = client.get_historical_data(symbol)
        if df is None or df.empty:
            logger.warning(f"No data for {symbol}, skipping.")
            return

        eval_data = {
            'symbol': symbol,
            'entry_price': pos.entry_price,
            'current_price': df.iloc[-1]['Close'],
            'high_watermark': pos.high_watermark or df.iloc[-1]['Close'],
            'entry_debit': pos.entry_debit,
            'days_held': (datetime.utcnow() - pos.entry_date).days,
            'current_row': df.iloc[-1],
            'prev_row': df.iloc[-2] if len(df) > 1 else None,
            'atr_at_entry': pos.atr_at_entry or 0,
        }

        action, reason = self.exit_engine.evaluate(eval_data)

        if action != 'HOLD':
            logger.info(f"EXIT signal for {symbol} pos {pos.id}: {action} — {reason}")
            # TODO: Execute exit order via client
            # client.close_zebra_position(pos)
            pos.status = 'pending_exit'
            pos.exit_reason = reason
            db.commit()
