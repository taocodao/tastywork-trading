"""
TastytradeExecutor
==================
Places vertical spread orders via the Tastytrade Python SDK (v12+).
Uses Session with user's refresh_token + app's client_secret.
Handles async SDK methods via asyncio.run() for use in sync HTTP server.
"""

import os
import asyncio
import logging
from decimal import Decimal
from datetime import date
from typing import Optional, Union

from tastytrade import Session, Account
from tastytrade.instruments import Option, get_option_chain
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType

logger = logging.getLogger(__name__)


def _run(coro):
    """Run a coroutine synchronously — handles both async (v12+) and sync (v11) returns."""
    import inspect
    if inspect.iscoroutine(coro):
        return asyncio.run(coro)
    return coro


class TastytradeExecutor:
    """Places vertical spread orders on Tastytrade using user's OAuth session."""

    @staticmethod
    def create_session(refresh_token: str) -> Session:
        """
        Create a Tastytrade session from a user's refresh token.
        Requires TASTYTRADE_CLIENT_SECRET env var.
        Works with SDK v12: Session(client_secret, refresh_token).
        """
        client_secret = os.environ.get('TASTYTRADE_CLIENT_SECRET', '')
        if not client_secret:
            raise ValueError('TASTYTRADE_CLIENT_SECRET not set')

        session = Session(client_secret, refresh_token)
        logger.info('Tastytrade session created successfully')
        return session

    @staticmethod
    def get_account(session: Session, account_number: str) -> Account:
        """Get a specific account by number."""
        accounts = _run(Account.get(session))
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
                exp_str = expiration[2:]  # 20260307 -> 260307
        else:
            exp_str = expiration.strftime('%y%m%d')

        strike_int = int(strike * 1000)
        strike_str = f'{strike_int:08d}'

        return f'{root_padded}{exp_str}{option_type}{strike_str}'

    @staticmethod
    def place_vertical_spread(
        session: Session,
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

        # 2. Fetch Option objects from Tastytrade (may be async in v12)
        short_option = _run(Option.get(session, short_occ))
        long_option  = _run(Option.get(session, long_occ))

        # 3. Build decimal legs
        qty_dec = Decimal(str(quantity))
        short_leg = short_option.build_leg(qty_dec, OrderAction.SELL_TO_OPEN)
        long_leg  = long_option.build_leg(qty_dec, OrderAction.BUY_TO_OPEN)

        # 4. Build limit order — positive Decimal = net credit
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[short_leg, long_leg],
            price=Decimal(str(round(credit, 2))),
        )

        mode = " (DRY RUN)" if dry_run else ""
        logger.info(f'Placing order: {spread_type} split '
                    f'{short_strike}/{long_strike} x{quantity} @ ${credit:.2f} credit{mode}')

        # 5. Place order (may be async in v12)
        response = _run(account.place_order(session, order, dry_run=dry_run))

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

    @staticmethod
    def place_diagonal_spread(
        session: Session,
        account: Account,
        symbol: str,              # e.g., "TQQQ"
        anchor_strike: float,     # e.g., 72.0 (Short)
        anchor_expiration: str,   # e.g., "2026-03-07"
        hedge_strike: float,      # e.g., 67.0 (Long)
        hedge_expiration: str,    # e.g., "2026-02-14"
        spread_type: str,         # "PUT"
        credit: float,            # net credit per contract (e.g., 0.85)
        quantity: int,            # number of contracts
        dry_run: bool = False,    # True for verifying validity without real trade
    ) -> dict:
        """
        Places a diagonal credit spread order:
          SELL anchor leg (usually longer expiration)
          BUY hedge leg (usually shorter expiration)
        Returns order confirmation dict.
        """
        opt_type = spread_type[0].upper()  # "P"

        anchor_occ = TastytradeExecutor.build_occ_symbol(symbol, anchor_expiration, opt_type, anchor_strike)
        hedge_occ  = TastytradeExecutor.build_occ_symbol(symbol, hedge_expiration, opt_type, hedge_strike)

        logger.info(f'Looking up options: {anchor_occ} / {hedge_occ}')

        anchor_option = _run(Option.get(session, anchor_occ))
        hedge_option  = _run(Option.get(session, hedge_occ))

        qty_dec = Decimal(str(quantity))
        anchor_leg = anchor_option.build_leg(qty_dec, OrderAction.SELL_TO_OPEN)
        hedge_leg  = hedge_option.build_leg(qty_dec, OrderAction.BUY_TO_OPEN)

        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[anchor_leg, hedge_leg],
            price=Decimal(str(round(credit, 2))),
        )

        mode = " (DRY RUN)" if dry_run else ""
        logger.info(f'Placing diagonal: {spread_type} '
                    f'Short {anchor_strike} ({anchor_expiration}) / Long {hedge_strike} ({hedge_expiration}) '
                    f'x{quantity} @ ${credit:.2f} credit{mode}')

        response = _run(account.place_order(session, order, dry_run=dry_run))

        order_id = str(response.order.id) if hasattr(response, 'order') and hasattr(response.order, 'id') else (str(response.id) if hasattr(response, 'id') else None)

        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'SELL_TO_OPEN', 'strike': anchor_strike, 'expiration': anchor_expiration, 'type': spread_type, 'occ': anchor_occ},
                {'action': 'BUY_TO_OPEN',  'strike': hedge_strike,  'expiration': hedge_expiration, 'type': spread_type, 'occ': hedge_occ},
            ],
            'credit': credit,
            'quantity': quantity,
            'dryRun': dry_run,
        }

    @staticmethod
    def close_diagonal_spread(
        session: Session,
        account: Account,
        symbol: str,
        anchor_strike: float,
        anchor_expiration: str,
        hedge_strike: float,
        hedge_expiration: str,
        spread_type: str,
        debit: float,
        quantity: int,
        dry_run: bool = False,
    ) -> dict:
        """
        Closes a diagonal spread:
          BUY TO CLOSE anchor leg
          SELL TO CLOSE hedge leg
        """
        opt_type = spread_type[0].upper()

        anchor_occ = TastytradeExecutor.build_occ_symbol(symbol, anchor_expiration, opt_type, anchor_strike)
        hedge_occ  = TastytradeExecutor.build_occ_symbol(symbol, hedge_expiration, opt_type, hedge_strike)

        anchor_option = _run(Option.get(session, anchor_occ))
        hedge_option  = _run(Option.get(session, hedge_occ))

        qty_dec = Decimal(str(quantity))
        anchor_leg = anchor_option.build_leg(qty_dec, OrderAction.BUY_TO_CLOSE)
        hedge_leg  = hedge_option.build_leg(qty_dec, OrderAction.SELL_TO_CLOSE)

        # Debit: represented as negative limit price in Tastytrade SDK
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[anchor_leg, hedge_leg],
            price=Decimal(str(round(-debit, 2))),
        )

        mode = " (DRY RUN)" if dry_run else ""
        logger.info(f'Closing diagonal: {spread_type} '
                    f'Buy {anchor_strike} / Sell {hedge_strike} x{quantity} @ ${debit:.2f} debit{mode}')

        response = _run(account.place_order(session, order, dry_run=dry_run))

        order_id = str(response.order.id) if hasattr(response, 'order') and hasattr(response.order, 'id') else (str(response.id) if hasattr(response, 'id') else None)
        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'BUY_TO_CLOSE', 'strike': anchor_strike, 'type': spread_type, 'occ': anchor_occ},
                {'action': 'SELL_TO_CLOSE', 'strike': hedge_strike, 'type': spread_type, 'occ': hedge_occ},
            ],
            'debit': debit,
            'dryRun': dry_run,
        }

    @staticmethod
    def roll_hedge(
        session: Session,
        account: Account,
        symbol: str,
        current_hedge_strike: float,
        current_hedge_expiration: str,
        new_hedge_strike: float,
        new_hedge_expiration: str,
        spread_type: str,
        net_credit: float, # Negative if debit
        quantity: int,
        dry_run: bool = False,
    ) -> dict:
        """
        Rolls a hedge by selling to close the active hedge and buying to open a new hedge.
        """
        opt_type = spread_type[0].upper()

        old_hedge_occ = TastytradeExecutor.build_occ_symbol(symbol, current_hedge_expiration, opt_type, current_hedge_strike)
        new_hedge_occ = TastytradeExecutor.build_occ_symbol(symbol, new_hedge_expiration, opt_type, new_hedge_strike)

        old_option = _run(Option.get(session, old_hedge_occ))
        new_option = _run(Option.get(session, new_hedge_occ))

        qty_dec = Decimal(str(quantity))
        old_leg = old_option.build_leg(qty_dec, OrderAction.SELL_TO_CLOSE)
        new_leg = new_option.build_leg(qty_dec, OrderAction.BUY_TO_OPEN)

        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[old_leg, new_leg],
            price=Decimal(str(round(net_credit, 2))),
        )

        mode = " (DRY RUN)" if dry_run else ""
        action_word = "credit" if net_credit >= 0 else "debit"
        price_val = abs(net_credit)
        logger.info(f'Rolling hedge: close {current_hedge_strike} ({current_hedge_expiration}) '
                    f'open {new_hedge_strike} ({new_hedge_expiration}) '
                    f'x{quantity} @ ${price_val:.2f} {action_word}{mode}')

        response = _run(account.place_order(session, order, dry_run=dry_run))

        order_id = str(response.order.id) if hasattr(response, 'order') and hasattr(response.order, 'id') else (str(response.id) if hasattr(response, 'id') else None)
        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'SELL_TO_CLOSE', 'strike': current_hedge_strike, 'expiration': current_hedge_expiration, 'occ': old_hedge_occ},
                {'action': 'BUY_TO_OPEN', 'strike': new_hedge_strike, 'expiration': new_hedge_expiration, 'occ': new_hedge_occ},
            ],
            'net_credit': net_credit,
            'dryRun': dry_run,
        }

    @staticmethod
    def place_backspread(
        session: Session,
        account: Account,
        symbol: str,
        short_strike: float,
        long_strike: float,
        expiration: str,
        spread_type: str,
        net_cost: float,
        quantity: int,
        dry_run: bool = False,
    ) -> dict:
        """
        Places a 1x2 Ratio Backspread:
          SELL 1 short leg
          BUY 2 long legs
        Returns order confirmation dict.
        """
        opt_type = spread_type[0].upper()

        short_occ = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, short_strike)
        long_occ  = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, long_strike)

        logger.info(f'Looking up options: {short_occ} / {long_occ}')

        short_option = _run(Option.get(session, short_occ))
        long_option  = _run(Option.get(session, long_occ))

        qty_dec = Decimal(str(quantity))
        qty2_dec = Decimal(str(quantity * 2))
        
        short_leg = short_option.build_leg(qty_dec, OrderAction.SELL_TO_OPEN)
        long_leg  = long_option.build_leg(qty2_dec, OrderAction.BUY_TO_OPEN)

        # In Tastytrade SDK, debit is represented as a negative limit price
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[short_leg, long_leg],
            price=Decimal(str(round(-net_cost, 2))),
        )

        mode = " (DRY RUN)" if dry_run else ""
        cost_str = f"${net_cost:.2f} debit" if net_cost >= 0 else f"${-net_cost:.2f} credit"
        logger.info(f'Placing backspread: {spread_type} '
                    f'-1 {short_strike} / +2 {long_strike} ({expiration}) '
                    f'x{quantity} @ {cost_str}{mode}')

        response = _run(account.place_order(session, order, dry_run=dry_run))

        order_id = str(response.order.id) if hasattr(response, 'order') and hasattr(response.order, 'id') else (str(response.id) if hasattr(response, 'id') else None)

        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'SELL_TO_OPEN', 'strike': short_strike, 'expiration': expiration, 'type': spread_type, 'occ': short_occ, 'ratio': 1},
                {'action': 'BUY_TO_OPEN',  'strike': long_strike,  'expiration': expiration, 'type': spread_type, 'occ': long_occ, 'ratio': 2},
            ],
            'net_cost': net_cost,
            'quantity': quantity,
            'dryRun': dry_run,
        }

    @staticmethod
    def close_backspread(
        session: Session,
        account: Account,
        symbol: str,
        short_strike: float,
        long_strike: float,
        expiration: str,
        spread_type: str,
        net_credit: float,
        quantity: int,
        dry_run: bool = False,
    ) -> dict:
        """
        Closes a 1x2 Ratio Backspread:
          BUY TO CLOSE 1 short leg
          SELL TO CLOSE 2 long legs
        """
        opt_type = spread_type[0].upper()

        short_occ = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, short_strike)
        long_occ  = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, long_strike)

        short_option = _run(Option.get(session, short_occ))
        long_option  = _run(Option.get(session, long_occ))

        qty_dec = Decimal(str(quantity))
        qty2_dec = Decimal(str(quantity * 2))
        
        short_leg = short_option.build_leg(qty_dec, OrderAction.BUY_TO_CLOSE)
        long_leg  = long_option.build_leg(qty2_dec, OrderAction.SELL_TO_CLOSE)

        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[short_leg, long_leg],
            price=Decimal(str(round(net_credit, 2))),
        )

        mode = " (DRY RUN)" if dry_run else ""
        cost_str = f"${net_credit:.2f} credit" if net_credit >= 0 else f"${-net_credit:.2f} debit"
        logger.info(f'Closing backspread: {spread_type} '
                    f'+1 {short_strike} / -2 {long_strike} ({expiration}) '
                    f'x{quantity} @ {cost_str}{mode}')

        response = _run(account.place_order(session, order, dry_run=dry_run))

        order_id = str(response.order.id) if hasattr(response, 'order') and hasattr(response.order, 'id') else (str(response.id) if hasattr(response, 'id') else None)

        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'BUY_TO_CLOSE', 'strike': short_strike, 'expiration': expiration, 'type': spread_type, 'occ': short_occ, 'ratio': 1},
                {'action': 'SELL_TO_CLOSE', 'strike': long_strike, 'expiration': expiration, 'type': spread_type, 'occ': long_occ, 'ratio': 2},
            ],
            'net_credit': net_credit,
            'dryRun': dry_run,
        }
