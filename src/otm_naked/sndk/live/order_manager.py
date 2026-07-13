import uuid
import logging
import sqlite3
import os
import requests
import yaml
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from ib_insync import IB, Option, Order, Trade, Fill

logger = logging.getLogger(__name__)

def load_config(path: str = None) -> dict:
    if not path:
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../config.yaml'))
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def init_database():
    """Initialize the SQLite database schema."""
    conn = sqlite3.connect('sndk_trades.db')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leg_id TEXT NOT NULL,
            right TEXT NOT NULL,
            expiry TEXT,
            strike REAL,
            quantity INTEGER,
            sto_price REAL,
            btc_price REAL,
            exit_reason TEXT,
            pnl REAL,
            opened_at TEXT,
            closed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            sndk_price REAL,
            iv REAL,
            ivr REAL,
            vix REAL,
            vix3m REAL,
            regime TEXT,
            dss_score REAL,
            call_action TEXT,
            action_taken TEXT
        )
    """)
    conn.commit()
    conn.close()


@dataclass
class LegState:
    """Tracks all orders associated with a single option leg."""
    leg_id: str
    contract: Option
    right: str                          # 'C' or 'P'
    quantity: int
    target_credit: float                # Credit received at STO fill
    
    sto_trade: Optional[Trade] = None   # STO entry order
    btc_pt_trade: Optional[Trade] = None  # BTC profit target
    btc_sl_trade: Optional[Trade] = None  # BTC stop loss
    
    state: str = 'FLAT'                 # FLAT | ENTRY_PENDING | OPEN | CLOSING | CLOSED | CANCELLED
    sto_fill_price: float = 0.0
    oca_group: str = ''
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    realized_pnl: float = 0.0
    
    # Store config params for bracket creation
    pt_pct: float = 0.50
    sl_mult: float = 3.00


class SNDKOrderManager:
    """Master order controller for the SNDK DDS Bot."""
    
    def __init__(self, ib: IB):
        self.ib = ib
        self.legs: Dict[str, LegState] = {}
        self.yaml_config = load_config()
        
        # Register event handlers
        self.ib.orderStatusEvent += self._on_order_status
        self.ib.fillEvent += self._on_fill
        self.ib.errorEvent += self._on_error
        
        init_database()

    def open_put_leg(
        self,
        expiry: str,
        strike: float,
        quantity: int,
        mid_price: float,
        profit_target_pct: float = 0.50,
        stop_loss_mult: float = 3.00
    ) -> LegState:
        """Open a naked put STO with a pre-attached dormant BTC bracket."""
        leg_id = f"PUT_{expiry}_{strike}_{uuid.uuid4().hex[:6]}"
        contract = self._qualify_option('P', expiry, strike)
        
        sto_order, btc_pt_order, btc_sl_order, oca_group = self._build_bracket(
            action='SELL',
            order_type='LMT',
            quantity=quantity,
            entry_price=mid_price,
            credit=mid_price,
            profit_target_pct=profit_target_pct,
            stop_loss_mult=stop_loss_mult
        )
        
        leg = LegState(
            leg_id=leg_id,
            contract=contract,
            right='P',
            quantity=quantity,
            target_credit=mid_price,
            oca_group=oca_group,
            pt_pct=profit_target_pct,
            sl_mult=stop_loss_mult
        )
        
        # Transmit orders atomically
        sto_trade = self.ib.placeOrder(contract, sto_order)
        self.ib.sleep(0.3)
        btc_pt_trade = self.ib.placeOrder(contract, btc_pt_order)
        self.ib.sleep(0.3)
        btc_sl_trade = self.ib.placeOrder(contract, btc_sl_order)
        self.ib.sleep(0.5)
        
        leg.sto_trade = sto_trade
        leg.btc_pt_trade = btc_pt_trade
        leg.btc_sl_trade = btc_sl_trade
        leg.state = 'ENTRY_PENDING'
        
        self.legs[leg_id] = leg
        
        logger.info(f"[PUT LEG] {leg_id} | STO ${mid_price:.2f} | "
                    f"PT={mid_price * profit_target_pct:.2f} | "
                    f"SL={mid_price * stop_loss_mult:.2f} | OCA={oca_group}")
        return leg

    def open_call_leg_stoplimit(
        self,
        expiry: str,
        strike: float,
        quantity: int,
        current_bid: float,
        ivr: float,
        profit_target_pct: float = 0.50,
        stop_loss_mult: float = 2.50
    ) -> LegState:
        """Open a naked call STO using a conditional stop-limit order."""
        leg_id = f"CALL_{expiry}_{strike}_{uuid.uuid4().hex[:6]}"
        contract = self._qualify_option('C', expiry, strike)
        
        prices = self._compute_stoplimit_prices(current_bid, ivr)
        
        sto_order = Order(usePriceMgmtAlgo=False)
        sto_order.action = 'SELL'
        sto_order.orderType = 'STP LMT'
        sto_order.totalQuantity = quantity
        sto_order.auxPrice = prices['stop_price']
        sto_order.lmtPrice = prices['limit_price']
        sto_order.tif = 'DAY'
        sto_order.triggerMethod = 1
        sto_order.outsideRth = False
        sto_order.transmit = True
        
        leg = LegState(
            leg_id=leg_id,
            contract=contract,
            right='C',
            quantity=quantity,
            target_credit=prices['stop_price'],
            oca_group='',
            pt_pct=profit_target_pct,
            sl_mult=stop_loss_mult
        )
        
        sto_trade = self.ib.placeOrder(contract, sto_order)
        self.ib.sleep(0.5)
        
        leg.sto_trade = sto_trade
        leg.state = 'ENTRY_PENDING'
        
        self.legs[leg_id] = leg
        
        logger.info(f"[CALL LEG] {leg_id} | Stop-Limit STO | "
                    f"bid={current_bid:.2f} stop={prices['stop_price']:.2f} "
                    f"limit={prices['limit_price']:.2f} | Waiting...")
        return leg

    def cancel_pending_sto(self, leg_id: str, reason: str = 'regime_change') -> bool:
        """Cancel an unfilled STO entry order."""
        leg = self.legs.get(leg_id)
        if not leg or leg.state != 'ENTRY_PENDING':
            return False
        
        if leg.sto_trade and leg.sto_trade.isActive():
            self.ib.cancelOrder(leg.sto_trade.order)
            self.ib.sleep(0.3)
            
        leg.state = 'CANCELLED'
        logger.info(f"[CANCEL STO] {leg_id} | Reason: {reason}")
        return True

    def cancel_all_pending_stos(self, reason: str = 'eod_cleanup'):
        """Cancel all unfilled STO orders."""
        cancelled = []
        for leg_id, leg in list(self.legs.items()):
            if leg.state == 'ENTRY_PENDING':
                self.cancel_pending_sto(leg_id, reason)
                cancelled.append(leg_id)
        logger.info(f"[EOD CLEANUP] Cancelled {len(cancelled)} pending STOs: {cancelled}")
        return cancelled

    def check_gtc_orders(self):
        """Check if GTC orders were cancelled by IB (e.g., quarter-end)."""
        for leg in self.legs.values():
            if leg.state == 'OPEN':
                needs_resubmit = False
                if leg.btc_pt_trade and not leg.btc_pt_trade.isActive():
                    needs_resubmit = True
                if leg.btc_sl_trade and not leg.btc_sl_trade.isActive():
                    needs_resubmit = True
                    
                if needs_resubmit:
                    logger.warning(f"[WATCHDOG] Resubmitting cancelled GTC bracket for {leg.leg_id}")
                    self._place_btc_bracket_after_fill(leg, leg.sto_fill_price)

    # --- Event Handlers ---

    def _on_fill(self, trade: Trade, fill: Fill):
        order_id = trade.order.orderId
        leg = self._find_leg_by_order(order_id)
        if not leg:
            return
            
        fill_price = fill.execution.price
        qty = int(fill.execution.shares)
        
        # STO filled
        if trade == leg.sto_trade:
            if qty < leg.quantity:
                logger.info(f"[PARTIAL FILL] STO {leg.leg_id}: {qty}/{leg.quantity} filled. Waiting for remainder.")
                pass
                
            filled_qty = int(trade.orderStatus.filled)
            
            if filled_qty > 0 and trade.orderStatus.remaining == 0:
                avg_price = trade.orderStatus.avgFillPrice
                leg.sto_fill_price = avg_price
                leg.quantity = filled_qty
                leg.filled_at = datetime.now()
                leg.state = 'OPEN'
                
                logger.info(f"[STO FILL] {leg.leg_id} | {leg.right} {avg_price:.2f} × {filled_qty}")
                
                if leg.right == 'C':
                    self._place_btc_bracket_after_fill(leg, avg_price)
                else:
                    leg.target_credit = avg_price
                    logger.info(f"[BRACKET ACTIVE] {leg.leg_id} | PT and SL now active via IB bracket")
                
                self._notify(f"✅ STO FILLED: {leg.right} {leg.leg_id}\nCredit: ${avg_price:.2f} × {filled_qty} = ${avg_price * filled_qty * 100:.0f}")

        # BTC Profit Target filled
        elif trade == leg.btc_pt_trade:
            leg.state = 'CLOSED'
            leg.closed_at = datetime.now()
            pnl = (leg.sto_fill_price - fill_price) * qty * 100
            leg.realized_pnl += pnl
            
            if leg.btc_sl_trade and leg.btc_sl_trade.isActive():
                self.ib.cancelOrder(leg.btc_sl_trade.order)
                
            logger.info(f"[PT FILL] {leg.leg_id} | P&L: +${pnl:.2f}")
            self._log_trade_to_db(leg, 'profit_target', fill_price, pnl)
            self._notify(f"🎯 PROFIT TARGET: {leg.leg_id}\nP&L: +${pnl:.2f}")
            
        # BTC Stop Loss filled
        elif trade == leg.btc_sl_trade:
            leg.state = 'CLOSED'
            leg.closed_at = datetime.now()
            pnl = (leg.sto_fill_price - fill_price) * qty * 100
            leg.realized_pnl += pnl
            
            if leg.btc_pt_trade and leg.btc_pt_trade.isActive():
                self.ib.cancelOrder(leg.btc_pt_trade.order)
                
            logger.info(f"[SL FILL] {leg.leg_id} | P&L: ${pnl:.2f}")
            self._log_trade_to_db(leg, 'stop_loss', fill_price, pnl)
            self._notify(f"🛑 STOP LOSS: {leg.leg_id}\nP&L: ${pnl:.2f}")

    def _on_order_status(self, trade: Trade):
        leg = self._find_leg_by_order(trade.order.orderId)
        if not leg:
            return
            
        status = trade.orderStatus.status
        if status == 'Cancelled':
            if trade == leg.btc_pt_trade:
                logger.debug(f"[OCA CANCEL] PT cancelled for {leg.leg_id}")
            elif trade == leg.btc_sl_trade:
                logger.debug(f"[OCA CANCEL] SL cancelled for {leg.leg_id}")

    def _on_error(self, reqId, errorCode, errorString, contract):
        if errorCode in [103, 201, 202]:
            logger.debug(f"[IB ERROR] {errorCode}: {errorString} | reqId={reqId}")
            if errorCode == 201:
                leg = self._find_leg_by_order(reqId)
                if leg and leg.state == 'OPEN' and (leg.btc_pt_trade and reqId == leg.btc_pt_trade.order.orderId or leg.btc_sl_trade and reqId == leg.btc_sl_trade.order.orderId):
                    logger.error(f"ERROR: BTC bracket child rejected for {leg.leg_id}. Retrying standalone OCA.")
                    self._place_btc_bracket_after_fill(leg, leg.sto_fill_price)
                    self._notify(f"⚠️ Bracket child rejected for {leg.leg_id}. Auto-recovering.")

    # --- Private Helpers ---

    def _build_bracket(self, action, order_type, quantity, entry_price, credit, profit_target_pct, stop_loss_mult):
        parent_id = self.ib.client.getReqId()
        oca_group = f"OCA_{uuid.uuid4().hex[:10]}"
        
        parent = Order(usePriceMgmtAlgo=False)
        parent.orderId = parent_id
        parent.action = action
        parent.orderType = order_type
        parent.totalQuantity = quantity
        parent.lmtPrice = round(entry_price, 2)
        parent.tif = 'DAY'
        parent.transmit = False
        
        pt_price = max(round(credit * profit_target_pct, 2), 0.05)
        btc_pt = Order(usePriceMgmtAlgo=False)
        btc_pt.orderId = parent_id + 1
        btc_pt.action = 'BUY'
        btc_pt.orderType = 'LMT'
        btc_pt.totalQuantity = quantity
        btc_pt.lmtPrice = pt_price
        btc_pt.parentId = parent_id
        btc_pt.tif = 'GTC'
        btc_pt.ocaGroup = oca_group
        btc_pt.ocaType = 1
        btc_pt.transmit = False
        
        sl_trigger = round(credit * stop_loss_mult, 2)
        sl_limit = round(sl_trigger * 1.10, 2)
        
        btc_sl = Order(usePriceMgmtAlgo=False)
        btc_sl.orderId = parent_id + 2
        btc_sl.action = 'BUY'
        btc_sl.orderType = 'STP LMT'
        btc_sl.totalQuantity = quantity
        btc_sl.auxPrice = sl_trigger
        btc_sl.lmtPrice = sl_limit
        btc_sl.parentId = parent_id
        btc_sl.tif = 'GTC'
        btc_sl.ocaGroup = oca_group
        btc_sl.ocaType = 1
        btc_sl.triggerMethod = 1
        btc_sl.transmit = True
        
        return parent, btc_pt, btc_sl, oca_group

    def _place_btc_bracket_after_fill(self, leg: LegState, fill_price: float):
        oca_group = f"OCA_{uuid.uuid4().hex[:10]}"
        leg.oca_group = oca_group
        
        pt_price = max(round(fill_price * leg.pt_pct, 2), 0.05)
        sl_trigger = round(fill_price * leg.sl_mult, 2)
        sl_limit = round(sl_trigger * 1.10, 2)
        
        btc_pt = Order(usePriceMgmtAlgo=False)
        btc_pt.action = 'BUY'
        btc_pt.orderType = 'LMT'
        btc_pt.totalQuantity = leg.quantity
        btc_pt.lmtPrice = pt_price
        btc_pt.tif = 'GTC'
        btc_pt.ocaGroup = oca_group
        btc_pt.ocaType = 1
        btc_pt.transmit = False
        
        btc_sl = Order(usePriceMgmtAlgo=False)
        btc_sl.action = 'BUY'
        btc_sl.orderType = 'STP LMT'
        btc_sl.totalQuantity = leg.quantity
        btc_sl.auxPrice = sl_trigger
        btc_sl.lmtPrice = sl_limit
        btc_sl.tif = 'GTC'
        btc_sl.ocaGroup = oca_group
        btc_sl.ocaType = 1
        btc_sl.triggerMethod = 1
        btc_sl.transmit = True
        
        leg.btc_pt_trade = self.ib.placeOrder(leg.contract, btc_pt)
        self.ib.sleep(0.3)
        leg.btc_sl_trade = self.ib.placeOrder(leg.contract, btc_sl)
        self.ib.sleep(0.3)
        
        logger.info(f"[BTC BRACKET] {leg.leg_id} | PT=${pt_price:.2f} SL-trigger=${sl_trigger:.2f} OCA={oca_group}")

    def _qualify_option(self, right: str, expiry: str, strike: float) -> Option:
        ticker = self.yaml_config.get('ticker', 'SPY')
        contract = Option(ticker, expiry, strike, right, 'SMART', currency='USD')
        self.ib.qualifyContracts(contract)
        return contract

    def _compute_stoplimit_prices(self, current_bid: float, ivr: float) -> dict:
        cfg = self.yaml_config['call_entry_stop_gaps']
        if ivr >= cfg['high_ivr']['ivr_min']:
            discount = cfg['high_ivr']['stop_pct']
            limit_offset = cfg['high_ivr']['limit_offset_pct']
        elif ivr >= cfg['mid_ivr']['ivr_min']:
            discount = cfg['mid_ivr']['stop_pct']
            limit_offset = cfg['mid_ivr']['limit_offset_pct']
        else:
            discount = cfg['low_ivr']['stop_pct']
            limit_offset = cfg['low_ivr']['limit_offset_pct']
        
        stop_price = max(round(current_bid * (1 - discount), 2), 0.10)
        limit_price = max(round(stop_price * (1 - limit_offset), 2), 0.05)
        
        return {'stop_price': stop_price, 'limit_price': limit_price}

    def _find_leg_by_order(self, order_id: int) -> Optional[LegState]:
        for leg in self.legs.values():
            if leg.sto_trade and leg.sto_trade.order.orderId == order_id:
                return leg
            if leg.btc_pt_trade and leg.btc_pt_trade.order.orderId == order_id:
                return leg
            if leg.btc_sl_trade and leg.btc_sl_trade.order.orderId == order_id:
                return leg
        return None

    def _log_trade_to_db(self, leg: LegState, exit_reason: str, exit_price: float, pnl: float):
        try:
            conn = sqlite3.connect('sndk_trades.db')
            conn.execute("""
                INSERT INTO trades (leg_id, right, expiry, strike, quantity,
                                   sto_price, btc_price, exit_reason, pnl,
                                   opened_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                leg.leg_id, leg.right, leg.contract.lastTradeDateOrContractMonth,
                leg.contract.strike, leg.quantity,
                leg.sto_fill_price, exit_price, exit_reason, pnl,
                leg.filled_at.isoformat() if leg.filled_at else None,
                leg.closed_at.isoformat() if leg.closed_at else None
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB Error: {e}")

    def _notify(self, message: str):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if token and chat_id:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={'chat_id': chat_id, 'text': message},
                    timeout=5
                )
            except Exception as e:
                logger.error(f"Telegram notification failed: {e}")
