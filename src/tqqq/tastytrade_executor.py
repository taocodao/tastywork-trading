"""
TastytradeExecutor
==================
Places vertical spread orders via the Tastytrade Python SDK (v10.3.0).
Uses OAuthSession with user's refresh_token + app's client_secret.
"""

import os
import logging
from decimal import Decimal
from datetime import date
from typing import Optional, Union

from tastytrade import OAuthSession, Account
from tastytrade.instruments import Option, get_option_chain
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType

logger = logging.getLogger(__name__)

class TastytradeExecutor:
    """Places vertical spread orders on Tastytrade using user's OAuth session."""

    @staticmethod
    def create_session(refresh_token: str) -> OAuthSession:
        """
        Create a Tastytrade OAuth session from a user's refresh token.
        Requires TASTYTRADE_CLIENT_SECRET env var.
        """
        client_secret = os.environ.get('TASTYTRADE_CLIENT_SECRET', '')
        if not client_secret:
            raise ValueError('TASTYTRADE_CLIENT_SECRET not set')
            
        session = OAuthSession(client_secret, refresh_token)
        logger.info('Tastytrade OAuth session created successfully')
        return session

    @staticmethod
    def get_account(session: OAuthSession, account_number: str) -> Account:
        """Get a specific account by number."""
        accounts = Account.get(session)
        for a in accounts:
            if a.account_number == account_number:
                return a
        raise ValueError(f'Account {account_number} not found in this Tastytrade session')

    @staticmethod
    def build_occ_symbol(
        root: str,                       # "TQQQ"
        expiration: Union[str, date],    # "2026-03-07" or date object
        option_type: str,                # "P" or "C"
        strike: float,                   # 72.0
    ) -> str:
        """
        Builds OCC symbol: TQQQ  260307P00072000
        Root = 6 chars space-padded, exp = yymmdd, strike = 8 digits (price × 1000)
        """
        root_padded = root.ljust(6)
        if isinstance(expiration, str):
            # Parse YYYY-MM-DD or YYYYMMDD
            if '-' in expiration:
                parts = expiration.split('-')
                exp_str = parts[0][2:] + parts[1] + parts[2]
            else:
                exp_str = expiration[2:] # 20260307 -> 260307
        else:
            exp_str = expiration.strftime('%y%m%d')
            
        strike_int = int(strike * 1000)
        strike_str = f'{strike_int:08d}'
        
        return f'{root_padded}{exp_str}{option_type}{strike_str}'

    @staticmethod
    def place_vertical_spread(
        session: OAuthSession,
        account: Account,
        symbol: str,              # e.g., "TQQQ"
        short_strike: float,      # e.g., 72.0
        long_strike: float,       # e.g., 67.0
        expiration: str,          # e.g., "2026-03-07"
        spread_type: str,         # "PUT" or "CALL"
        credit: float,            # net credit per contract (e.g., 0.85)
        quantity: int,            # number of contracts
        dry_run: bool = False,    # True for verifying validity without real trade
    ) -> dict:
        """
        Places a vertical credit spread order:
          PUT CREDIT:  SELL higher put, BUY lower put
          CALL CREDIT: SELL lower call, BUY higher call

        Returns order confirmation dict.
        """
        opt_type = spread_type[0].upper()  # "P" or "C"

        # 1. Build Exact OCC symbols
        short_occ = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, short_strike)
        long_occ  = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, long_strike)

        logger.info(f'Looking up options: {short_occ} / {long_occ}')

        # 2. Fetch Option objects from Tastytrade
        short_option = Option.get(session, short_occ)
        long_option  = Option.get(session, long_occ)

        # 3. Build decimal legs
        qty_dec = Decimal(str(quantity))
        short_leg = short_option.build_leg(qty_dec, OrderAction.SELL_TO_OPEN)
        long_leg  = long_option.build_leg(qty_dec, OrderAction.BUY_TO_OPEN)

        # 4. Build limit order — positive Decimal = net credit
        # (Negative Decimal would represent a net debit)
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[short_leg, long_leg],
            price=Decimal(str(round(credit, 2))),  
        )

        mode = " (DRY RUN)" if dry_run else ""
        logger.info(f'Placing order: {spread_type} split '
                    f'{short_strike}/{long_strike} x{quantity} @ ${credit:.2f} credit{mode}')

        # 5. Connect to market
        response = account.place_order(session, order, dry_run=dry_run)

        # 6. Parse response ID
        order_id = None
        if hasattr(response, 'order') and hasattr(response.order, 'id'):
            order_id = str(response.order.id)
        elif hasattr(response, 'id'):
            order_id = str(response.id)

        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'SELL_TO_OPEN', 'strike': short_strike, 'type': spread_type, 'occ': short_occ},
                {'action': 'BUY_TO_OPEN',  'strike': long_strike,  'type': spread_type, 'occ': long_occ},
            ],
            'credit': credit,
            'quantity': quantity,
            'dryRun': dry_run,
        }
