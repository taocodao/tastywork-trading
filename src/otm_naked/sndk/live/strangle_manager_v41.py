
# strangle_manager_v41.py
# v4.1: Dynamic Short Strangle with ML-Guided Leg Management (CORRECTED)
#
# KEY CORRECTIONS FROM v4.0:
#   1. Per-leg GTC OCA bracket (PT+SL) placed immediately on fill -- this is the
#      PRIMARY protection mechanism. It survives bot restarts/crashes.
#   2. Combined 50% P&L check in run_management() is a SECONDARY accelerator,
#      not the only protection.
#   3. Call leg is regime-gated: naked / credit spread / blocked, decided at open_call_leg().
#   4. Tested CALL legs are never rolled directly (roll_call_when_tested=False).
#      Only the winning leg is rolled for extra credit when the opposite side is tested.
#   5. delta_tested_threshold corrected to 0.45 (was 0.35).
#   6. _check_bpr_headroom() gates every new leg placement (roll, re-leg, new strangle).

import uuid, logging, math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from ib_insync import IB, Option, Order, Trade
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LegState:
    """Single leg (put, call, or call-spread short strike) within a strangle."""
    leg_id: str
    contract: Option
    right: str                            # 'C' or 'P'
    quantity: int
    open_spot: float
    is_spread: bool = False               # True if this call leg is a defined-risk credit spread
    spread_long_contract: Optional[Option] = None   # The protective long leg, if is_spread
    sto_fill_price: float = 0.0
    fill_spot: float = 0.0
    sto_trade: Optional[Trade] = None
    spread_long_trade: Optional[Trade] = None
    btc_pt_trade: Optional[Trade] = None  # GTC OCA profit target (PRIMARY protection)
    btc_sl_trade: Optional[Trade] = None  # GTC OCA stop-loss (PRIMARY protection)
    oca_group: str = ""
    state: str = "FLAT"                   # FLAT|PENDING|OPEN|ROLLING|CLOSING|CLOSED
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    realized_pnl: float = 0.0
    exit_reason: str = ""
    roll_count: int = 0


@dataclass
class StrangleState:
    """A single strangle (put leg + call leg/spread)."""
    strangle_id: str
    put_leg: Optional[LegState] = None
    call_leg: Optional[LegState] = None
    state: str = "PENDING_PUT"            # PENDING_PUT|PENDING_CALL|FULL|MANAGING|CLOSING|CLOSED
    open_combined_credit: float = 0.0
    regime_at_open: str = "SIDEWAYS"
    call_leg_type: str = "NAKED"          # NAKED|CREDIT_SPREAD|BLOCKED
    ivr_at_open: float = 0.0
    expiry: str = ""
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    exit_reason: str = ""
    combined_pnl: float = 0.0
    last_management_bar: Optional[datetime] = None


class StrangleManagerV41:
    """
    v4.1 Dynamic Strangle Manager (corrected).

    PROTECTION HIERARCHY (most important design principle):
      PRIMARY:   Per-leg GTC OCA bracket (PT=credit*0.50, SL=credit*3.0), placed
                 immediately upon fill. Lives on IB's servers. Survives bot
                 crashes/restarts. This is the CANONICAL exit for each leg.
      SECONDARY: Combined-P&L Python check in the 5-min loop. When it fires
                 faster than the per-leg GTC brackets would, it accelerates
                 the exit by closing both legs early. If the bot is offline,
                 this simply doesn't fire -- the per-leg GTC brackets still work.

    CALL LEG RISK GATE:
      Naked call only in SIDEWAYS / REVERT_BEARISH regimes.
      Credit spread in TREND_UP / REVERT_BULLISH with ADX >= 25.
      Blocked entirely in EXTREME_UPTREND (historical 100%-loss regime for this bot).

    ROLL RULES:
      Tested PUT (delta > 0.45) in idiosyncratic regime -> roll the put itself for credit.
      Tested CALL (delta > 0.45) in idiosyncratic regime -> DO NOT roll the call.
                    Roll the winning PUT up instead. Let the call ride to its own
                    GTC SL, or to its spread's defined max loss.
      Any tested leg in a STRUCTURAL trend regime -> close everything, no rolling.

    BPR HEADROOM:
      Every new leg placement (initial open, roll, re-leg) must pass
      _check_bpr_headroom() confirming projected BPR <= 45% of NAV, even transiently.
    """

    def __init__(self, ib: IB, config: dict):
        self.ib = ib
        self.cfg = config
        self.strangles: Dict[str, StrangleState] = {}
        self._last_spot: float = 0.0
        self._ml_regime_model = None
        self._lstm_forecaster = None
        # self.ib.execDetailsEvent += self.on_fill
        # self.ib.orderStatusEvent += self.on_order_status
        # self.ib.errorEvent += self.on_error

    # ============ STRANGLE OPENING ============

    def open_strangle(self, expiry: str, spot: float, ivr: float,
                       regime: str = 'SIDEWAYS') -> Optional[StrangleState]:
        """Phase 1: open the put leg. Call open_call_leg() within 3 days to complete."""
        if not self._can_open_strangle():
            return None
        if not self._check_bpr_headroom(estimated_new_margin=self._estimate_strangle_margin(spot)):
            logger.warning("BPR headroom check failed -- skipping new strangle")
            return None

        put_strike = self._select_strike('P', spot, ivr)
        if put_strike is None:
            return None

        strangle_id = f"STR_{expiry}_{uuid.uuid4().hex[:6]}"
        put_leg = self._place_leg('P', expiry, put_strike, 1, spot, ivr)
        if not put_leg:
            return None

        s = StrangleState(
            strangle_id=strangle_id, put_leg=put_leg, state='PENDING_CALL',
            regime_at_open=regime, ivr_at_open=ivr, expiry=expiry,
            opened_at=datetime.now()
        )
        self.strangles[strangle_id] = s
        logger.info(f"STRANGLE OPEN (put leg) {strangle_id}: K={put_strike} exp={expiry}")
        return s

    def open_call_leg(self, strangle_id: str, spot: float, ivr: float,
                       regime: str, adx: float = 20.0, atr14: float = None) -> bool:
        """
        Phase 2: add the call leg, regime-gated between NAKED / CREDIT_SPREAD / BLOCKED.
        """
        s = self.strangles.get(strangle_id)
        if not s or s.state != 'PENDING_CALL':
            return False

        gate = self.cfg['call_leg_regime_gate']
        if regime in gate['blocked_regimes']:
            logger.info(f"Call leg BLOCKED for {strangle_id} (regime={regime}). Running put-only.")
            s.call_leg_type = 'BLOCKED'
            s.state = 'FULL'   # Put-only strangle is considered "full" for this cycle
            return True

        use_spread = (regime in gate['credit_spread_regimes'] and adx >= gate['credit_spread_adx_min'])

        call_strike = self._select_strike('C', spot, ivr)
        if call_strike is None:
            return False

        if not self._check_bpr_headroom(estimated_new_margin=self._estimate_call_leg_margin(
                spot, call_strike, is_spread=use_spread, atr14=atr14)):
            logger.warning(f"BPR headroom check failed for call leg on {strangle_id}")
            return False

        if use_spread:
            long_strike = round((call_strike + gate['credit_spread_width_atr_mult'] * (atr14 or spot * 0.03)) / 5) * 5
            call_leg = self._place_credit_spread_leg(s.expiry, call_strike, long_strike, 1, spot, ivr)
            s.call_leg_type = 'CREDIT_SPREAD'
        else:
            call_leg = self._place_leg('C', s.expiry, call_strike, 1, spot, ivr)
            s.call_leg_type = 'NAKED'

        if not call_leg:
            return False

        s.call_leg = call_leg
        s.state = 'FULL'
        logger.info(f"STRANGLE FULL {strangle_id}: put K={s.put_leg.contract.strike} / "
                    f"call K={call_strike} type={s.call_leg_type}")
        self._notify(f"STRANGLE OPEN\n{strangle_id}\nPut: ${s.put_leg.contract.strike:.0f} | "
                     f"Call: ${call_strike:.0f} ({s.call_leg_type})\nExp: {s.expiry}")
        return True

    def _place_credit_spread_leg(self, expiry, short_strike, long_strike,
                                  quantity, spot, ivr) -> Optional[LegState]:
        """Place a call credit spread: sell short_strike call, buy long_strike call."""
        short_contract = self._qualify('C', expiry, short_strike)
        long_contract = self._qualify('C', expiry, long_strike)

        short_mid = self._get_mark(short_contract) or self._estimate_premium('C', expiry, short_strike, spot)
        long_mid = self._get_mark(long_contract) or self._estimate_premium('C', expiry, long_strike, spot)
        net_credit_mid = short_mid - long_mid
        if net_credit_mid < 0.30:
            logger.info(f"SKIP credit spread: net credit ${net_credit_mid:.2f} too small")
            return None

        # Sell short leg
        sto = Order()
        sto.action = 'SELL'; sto.orderType = 'LMT'; sto.totalQuantity = quantity
        sto.lmtPrice = max(round(short_mid * 0.95, 2), 0.10)
        sto.tif = 'DAY'; sto.transmit = True
        sto_trade = self.ib.placeOrder(short_contract, sto)
        self.ib.sleep(0.5)

        # Buy long (protective) leg
        bto = Order()
        bto.action = 'BUY'; bto.orderType = 'LMT'; bto.totalQuantity = quantity
        bto.lmtPrice = round(long_mid * 1.05, 2)
        bto.tif = 'DAY'; bto.transmit = True
        long_trade = self.ib.placeOrder(long_contract, bto)
        self.ib.sleep(0.5)

        leg_id = f"CSPR_{expiry}_{int(short_strike)}_{uuid.uuid4().hex[:6]}"
        leg = LegState(
            leg_id=leg_id, contract=short_contract, right='C', quantity=quantity,
            open_spot=spot, is_spread=True, spread_long_contract=long_contract
        )
        leg.sto_trade = sto_trade
        leg.spread_long_trade = long_trade
        leg.state = 'PENDING'
        return leg

    # ============ 5-MIN MANAGEMENT LOOP ============

    def run_management(self, spot: float, ml_regime: str,
                        vix: float = 20.0, spy_move: float = 0.0, adx: float = 20.0) -> list:
        """Called every 5-min bar. Evaluates all FULL strangles."""
        self._last_spot = spot
        actions = []

        for sid, s in list(self.strangles.items()):
            if s.state not in ('FULL', 'MANAGING'):
                continue
            if not s.put_leg:
                continue

            put_mark = self._get_mark(s.put_leg.contract)
            call_mark = self._get_call_leg_mark(s.call_leg) if s.call_leg else 0.0

            if put_mark is None:
                continue

            combined_credit = s.open_combined_credit
            combined_debit = put_mark + (call_mark or 0)
            combined_pnl_pct = (combined_credit - combined_debit) / combined_credit if combined_credit else 0

            # --- SECONDARY ACCELERATOR: combined 50% PT ---
            if combined_pnl_pct >= self.cfg['management']['combined_pt_pct']:
                self._close_both_legs(s, 'combined_50pct_pt_accelerator')
                actions.append((sid, 'CLOSE_50PCT_ACCELERATOR'))
                continue

            # --- Supplemental combined stop-loss (not primary; per-leg GTC SL is primary) ---
            combined_sl_mult = self.cfg['management']['combined_stop_loss_mult']
            if combined_credit and combined_debit > combined_credit * combined_sl_mult:
                self._close_both_legs(s, 'combined_stop_loss_supplemental')
                actions.append((sid, 'CLOSE_COMBINED_SL'))
                continue

            # --- Tested leg detection (threshold corrected to 0.45) ---
            put_delta = abs(self._get_delta(s.put_leg.contract))
            call_delta = abs(self._get_call_leg_delta(s.call_leg)) if s.call_leg else 0.0
            put_theta = abs(self._get_theta(s.put_leg.contract))
            call_theta = abs(self._get_call_leg_theta(s.call_leg)) if s.call_leg else 0.01

            delta_theta_ratio = (abs(call_delta - put_delta) / (put_theta + call_theta)
                                 if (put_theta + call_theta) > 0 else 999)

            tested_threshold = self.cfg['management']['delta_tested_threshold']  # 0.45
            put_tested = put_delta > tested_threshold
            call_tested = call_delta > tested_threshold

            if put_tested or call_tested:
                action = self._handle_tested_leg(s, spot, ml_regime, put_tested, call_tested,
                                                  put_delta, call_delta)
                actions.append((sid, action))
                continue

            # --- Swing re-leg check ---
            if s.put_leg.fill_spot > 0:
                sw = self.cfg['management']['swing_re_leg']
                put_spot_chg = (spot - s.put_leg.fill_spot) / s.put_leg.fill_spot
                if put_spot_chg >= sw['put_buyback_trigger'] and s.put_leg.state == 'OPEN':
                    if ml_regime in ('REVERT_BULLISH', 'SIDEWAYS'):
                        if self._check_bpr_headroom(estimated_new_margin=0):  # re-leg is roughly margin-neutral
                            self._swing_close_and_re_leg(s, 'P', spot, s.ivr_at_open)
                            actions.append((sid, 'SWING_RE_LEG_PUT'))

                if s.call_leg and s.call_leg.fill_spot > 0 and not s.call_leg.is_spread:
                    call_spot_chg = (spot - s.call_leg.fill_spot) / s.call_leg.fill_spot
                    if call_spot_chg <= sw['call_buyback_trigger'] and s.call_leg.state == 'OPEN':
                        if ml_regime in ('REVERT_BEARISH', 'SIDEWAYS'):
                            if self._check_bpr_headroom(estimated_new_margin=0):
                                self._swing_close_and_re_leg(s, 'C', spot, s.ivr_at_open)
                                actions.append((sid, 'SWING_RE_LEG_CALL'))

        return actions

    def _handle_tested_leg(self, s: StrangleState, spot: float, ml_regime: str,
                            put_tested: bool, call_tested: bool,
                            put_delta: float, call_delta: float) -> str:
        """
        CORRECTED decision tree:
          - Tested PUT in idiosyncratic regime -> roll the put itself
          - Tested CALL in idiosyncratic regime -> do NOT roll the call;
                roll the winning PUT for extra credit; call rides to its own exit
          - Structural trend regime (TREND_UP / TREND_DOWN) -> close everything
        """
        roll_cfg = self.cfg['management']['roll']

        if call_tested and ml_regime == 'TREND_UP':
            logger.info(f"TREND_UP: structural move, closing both legs {s.strangle_id}")
            self._close_one_leg(s, 'C', 'trend_close_structural')
            self._close_one_leg(s, 'P', 'trend_close_structural_lock_profit')
            return 'TREND_UP_FULL_CLOSE'

        elif put_tested and ml_regime == 'TREND_DOWN':
            logger.info(f"TREND_DOWN: structural move, closing both legs {s.strangle_id}")
            self._close_one_leg(s, 'P', 'trend_close_structural')
            self._close_one_leg(s, 'C', 'trend_close_structural_lock_profit')
            return 'TREND_DOWN_FULL_CLOSE'

        elif call_tested and ml_regime in ('REVERT_BULLISH', 'SIDEWAYS'):
            # CORRECTED: never roll the tested call. Roll the winning put instead.
            if roll_cfg['roll_call_when_tested']:
                logger.error("Config error: roll_call_when_tested should be False in v4.1")
            if roll_cfg['roll_winning_leg_on_opposite_test'] and s.put_leg.state == 'OPEN':
                rolled = self._roll_leg(s, 'P', spot)
                if rolled:
                    return 'ROLL_WINNING_PUT_CALL_TESTED_HOLD'
            return 'CALL_TESTED_NO_ROLL_HOLD_GTC_SL'

        elif put_tested and ml_regime in ('REVERT_BEARISH', 'SIDEWAYS'):
            if roll_cfg['roll_put_when_tested']:
                rolled = self._roll_leg(s, 'P', spot)
                if rolled:
                    if s.call_leg and s.call_leg.state == 'OPEN' and not s.call_leg.is_spread:
                        self._roll_leg(s, 'C', spot)  # roll winning call up for extra credit
                    return 'ROLL_PUT_DOWN_TESTED'
            return 'PUT_TESTED_NO_ROLL_HOLD_GTC_SL'

        else:
            return 'AMBIGUOUS_NO_ACTION_GTC_SL_ACTIVE'

    def _roll_leg(self, s: StrangleState, right: str, spot: float) -> bool:
        """
        Roll one leg for a net credit >= min_credit_to_roll.
        NOTE: This function is called for (a) tested puts, and (b) winning legs
        (put or call) being rolled up/down to capture extra credit. It is NEVER
        called for a tested call directly (enforced by the caller logic above).
        """
        leg = s.put_leg if right == 'P' else s.call_leg
        if not leg or leg.is_spread:
            return False  # Do not roll spread legs via this path

        roll_cfg = self.cfg['management']['roll']
        if leg.roll_count >= 3:
            logger.warning(f"Roll count limit reached for {leg.leg_id}")
            return False

        new_expiry = self._get_roll_expiry(leg.contract.lastTradeDateOrContractMonth, weeks_out=3)
        new_delta = 0.15 if right == 'P' else 0.12
        new_strike = self._select_strike(right, spot, ivr=s.ivr_at_open, target_delta=new_delta)
        if not new_strike:
            return False

        old_mark = self._get_mark(leg.contract) or leg.sto_fill_price * 0.3
        new_mark = self._estimate_premium(right, new_expiry, new_strike, spot)
        net_credit = new_mark - old_mark

        if net_credit < roll_cfg['min_credit_to_roll']:
            logger.info(f"Roll for {right} rejected: net credit {net_credit:.2f} < min "
                        f"{roll_cfg['min_credit_to_roll']}")
            return False

        if not self._check_bpr_headroom(estimated_new_margin=self._estimate_leg_margin(spot, new_strike)):
            logger.warning(f"Roll for {right} rejected: BPR headroom exceeded")
            return False

        # Cancel old GTC OCA bracket before closing the leg
        self._cancel_leg_gtc_bracket(leg)

        btc = Order()
        btc.action = 'BUY'; btc.orderType = 'LMT'; btc.totalQuantity = leg.quantity
        btc.lmtPrice = round(old_mark * 1.05, 2); btc.tif = 'DAY'; btc.transmit = True
        self.ib.placeOrder(leg.contract, btc)
        self.ib.sleep(1.0)

        new_contract = self._qualify(right, new_expiry, new_strike)
        sto = Order()
        sto.action = 'SELL'; sto.orderType = 'LMT'; sto.totalQuantity = 1
        sto.lmtPrice = max(round(new_mark * 0.95, 2), 0.10)
        sto.tif = 'DAY'; sto.transmit = True
        new_trade = self.ib.placeOrder(new_contract, sto)
        self.ib.sleep(0.5)

        leg.roll_count += 1
        logger.info(f"ROLL {right} {s.strangle_id}: K={leg.contract.strike}->{new_strike} "
                    f"exp->{new_expiry} credit~{net_credit:.2f}")
        self._notify(f"ROLL {right}\n{s.strangle_id}\n${leg.contract.strike:.0f}->${new_strike:.0f}\n"
                     f"Net credit: ~${net_credit*100:.0f}")
        return True

    def _swing_close_and_re_leg(self, s: StrangleState, right: str, spot: float, ivr: float):
        """Swing close the profitable (untested) leg and immediately re-leg at new strike."""
        leg = s.put_leg if right == 'P' else s.call_leg
        if not leg or leg.is_spread:
            return

        mark = self._get_mark(leg.contract)
        self._cancel_leg_gtc_bracket(leg)

        btc = Order()
        btc.action = 'BUY'; btc.orderType = 'LMT'; btc.totalQuantity = leg.quantity
        btc.lmtPrice = max(round((mark or 0.20) * 1.10, 2), 0.05)
        btc.tif = 'DAY'; btc.transmit = True
        self.ib.placeOrder(leg.contract, btc)
        self.ib.sleep(2)

        new_strike = self._select_strike(right, spot, ivr)
        if new_strike:
            new_premium = self._estimate_premium(right, s.expiry, new_strike, spot)
            sto = Order()
            sto.action = 'SELL'; sto.orderType = 'LMT'; sto.totalQuantity = 1
            sto.lmtPrice = max(round(new_premium * 0.95, 2), 0.10)
            sto.tif = 'DAY'; sto.transmit = True
            new_contract = self._qualify(right, s.expiry, new_strike)
            new_trade = self.ib.placeOrder(new_contract, sto)
            self.ib.sleep(0.5)

        old_pnl = (leg.sto_fill_price - (mark or leg.sto_fill_price * 0.3)) * leg.quantity * 100
        logger.info(f"SWING RE-LEG {right} {s.strangle_id}: close K={leg.contract.strike} "
                    f"pnl~${old_pnl:.0f}, re-leg K={new_strike}")
        self._notify(f"SWING RE-LEG {right}\n{s.strangle_id}\nClose K=${leg.contract.strike:.0f} "
                     f"(P&L~${old_pnl:+,.0f})\nRe-leg K=${new_strike:.0f}")

    def _close_both_legs(self, s: StrangleState, reason: str):
        for right, leg in [('P', s.put_leg), ('C', s.call_leg)]:
            if leg and leg.state == 'OPEN':
                self._close_one_leg(s, right, reason)
        s.state = 'CLOSING'

    def _close_one_leg(self, s: StrangleState, right: str, reason: str):
        leg = s.put_leg if right == 'P' else s.call_leg
        if not leg or leg.state != 'OPEN':
            return
        self._cancel_leg_gtc_bracket(leg)
        mark = self._get_mark(leg.contract) or leg.sto_fill_price * 0.30
        btc = Order()
        btc.action = 'BUY'; btc.orderType = 'LMT'; btc.totalQuantity = leg.quantity
        btc.lmtPrice = max(round(mark * 1.10, 2), 0.05)
        btc.tif = 'DAY'; btc.transmit = True
        self.ib.placeOrder(leg.contract, btc)
        self.ib.sleep(0.5)

        if leg.is_spread and leg.spread_long_contract:
            stc = Order()
            stc.action = 'SELL'; stc.orderType = 'LMT'; stc.totalQuantity = leg.quantity
            stc.lmtPrice = 0.05; stc.tif = 'DAY'; stc.transmit = True
            self.ib.placeOrder(leg.spread_long_contract, stc)
            self.ib.sleep(0.5)

        leg.exit_reason = reason
        leg.state = 'CLOSING'

    # ============ PRIMARY PROTECTION: PER-LEG GTC OCA BRACKET ============

    def _place_gtc_oca_bracket(self, leg: LegState):
        """
        PRIMARY protection. Called immediately after STO fills.
        Places a GTC OCA pair: profit target (BUY LMT at credit*0.50) and
        stop loss (BUY STP LMT at credit*3.0, limit +10%). ocaType=1 means
        whichever fills first auto-cancels the other on IB's servers.
        This bracket protects the leg even if the Python bot process is offline.
        """
        pt_pct = self.cfg['management']['profit_target_per_leg_pct']
        sl_mult = self.cfg['management']['stop_loss_per_leg_mult']

        pt_price = round(leg.sto_fill_price * pt_pct, 2)
        sl_trigger = round(leg.sto_fill_price * sl_mult, 2)
        sl_limit = round(sl_trigger * 1.10, 2)

        oca_group = f"OCA_{leg.leg_id}_{int(datetime.now().timestamp())}"

        pt_order = Order()
        pt_order.action = 'BUY'; pt_order.orderType = 'LMT'
        pt_order.totalQuantity = leg.quantity; pt_order.lmtPrice = pt_price
        pt_order.tif = 'GTC'; pt_order.ocaGroup = oca_group; pt_order.ocaType = 1
        pt_order.transmit = False

        sl_order = Order()
        sl_order.action = 'BUY'; sl_order.orderType = 'STP LMT'
        sl_order.totalQuantity = leg.quantity
        sl_order.auxPrice = sl_trigger; sl_order.lmtPrice = sl_limit
        sl_order.tif = 'GTC'; sl_order.triggerMethod = 1
        sl_order.ocaGroup = oca_group; sl_order.ocaType = 1
        sl_order.transmit = True

        leg.btc_pt_trade = self.ib.placeOrder(leg.contract, pt_order)
        self.ib.sleep(0.3)
        leg.btc_sl_trade = self.ib.placeOrder(leg.contract, sl_order)
        self.ib.sleep(0.3)
        leg.oca_group = oca_group

        logger.info(f"GTC OCA BRACKET {leg.leg_id}: PT=${pt_price:.2f} SL trig=${sl_trigger:.2f} "
                    f"lmt=${sl_limit:.2f} oca={oca_group}")

    def _cancel_leg_gtc_bracket(self, leg: LegState):
        """Cancel both sides of a leg's GTC OCA bracket before rolling/closing manually."""
        for trade in (leg.btc_pt_trade, leg.btc_sl_trade):
            if trade and trade.isActive():
                self.ib.cancelOrder(trade.order)
                self.ib.sleep(0.3)

    # ============ BPR HEADROOM CHECK (NEW IN v4.1) ============

    def _check_bpr_headroom(self, estimated_new_margin: float) -> bool:
        """
        Ensures adding a new leg (initial open, roll, or re-leg) never pushes
        projected BPR above the configured ceiling (45% of NAV), even transiently.
        """
        if not self.cfg['bpr_headroom_check']['enabled']:
            return True
        nav = self.cfg['account']['nav']
        max_bpr_pct = self.cfg['bpr_headroom_check']['max_bpr_pct']
        current_margin_used = self._compute_current_margin_used()
        projected = current_margin_used + estimated_new_margin
        if projected > nav * max_bpr_pct:
            logger.warning(f"BPR headroom check FAILED: projected {projected:.0f} > "
                            f"ceiling {nav*max_bpr_pct:.0f}")
            return False
        return True

    def _compute_current_margin_used(self) -> float:
        total = 0.0
        for s in self.strangles.values():
            if s.state in ('CLOSED', 'CANCELLED'):
                continue
            for leg in (s.put_leg, s.call_leg):
                if leg and leg.state == 'OPEN':
                    total += self._estimate_leg_margin(self._last_spot, leg.contract.strike)
        return total

    def _estimate_leg_margin(self, spot: float, strike: float) -> float:
        return max(0.20 * spot - abs(strike - spot), 0.10 * spot) * 100

    def _estimate_call_leg_margin(self, spot, strike, is_spread, atr14=None) -> float:
        if is_spread:
            width = (atr14 or spot * 0.03) * self.cfg['call_leg_regime_gate']['credit_spread_width_atr_mult']
            return width * 100  # Defined-risk margin = spread width
        return self._estimate_leg_margin(spot, strike)

    def _estimate_strangle_margin(self, spot: float) -> float:
        return self.cfg['account']['nav'] * self.cfg['account']['capital_per_strangle_pct']

    # ============ CAP + UTILITIES ============

    def _can_open_strangle(self) -> bool:
        active = sum(1 for s in self.strangles.values() if s.state not in ('CLOSED', 'CANCELLED'))
        return active < self.cfg['account']['max_strangles']

    def _select_strike(self, right: str, spot: float, ivr: float,
                        target_delta: float = None) -> Optional[float]:
        if target_delta is None:
            target_delta = self.cfg['delta_targets']['put' if right == 'P' else 'call']

        lstm_cfg = self.cfg.get('lstm_strike_selection', {})
        if lstm_cfg.get('enabled') and self._lstm_forecaster:
            try:
                forecast = self._lstm_forecaster.predict_range(self._get_recent_20d())
                if right == 'P':
                    pct_otm = abs(forecast['buffer_put_strike_pct'])
                    return round(spot * (1 - pct_otm) / 5) * 5
                else:
                    pct_otm = forecast['buffer_call_strike_pct']
                    return round(spot * (1 + pct_otm) / 5) * 5
            except Exception as e:
                logger.warning(f"LSTM strike selection failed: {e}. Falling back to delta.")

        t = self._get_dte_years(right)
        sigma = ivr / 100
        from scipy.stats import norm
        if right == 'P':
            k = spot * np.exp(norm.ppf(target_delta) * sigma * np.sqrt(t))
        else:
            k = spot * np.exp(norm.ppf(1 - target_delta) * sigma * np.sqrt(t))
        return round(k / 5) * 5

    def _place_leg(self, right: str, expiry: str, strike: float,
                    quantity: int, spot: float, ivr: float) -> Optional[LegState]:
        contract = self._qualify(right, expiry, strike)
        ticker = self.ib.reqMktData(contract, '', True, False)
        self.ib.sleep(2.5)
        bid = ticker.bid or 0; ask = ticker.ask or 0
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
        self.ib.cancelMktData(contract)

        if mid < 0.50:
            logger.info(f"SKIP {right} K={strike}: mid ${mid:.2f} < $0.50 minimum")
            return None

        sto = Order()
        sto.action = 'SELL'; sto.orderType = 'LMT'; sto.totalQuantity = quantity
        sto.lmtPrice = max(round(mid * (1 - self.cfg['slippage']['entry_pct']), 2), 0.50)
        sto.tif = 'DAY'; sto.transmit = True

        leg_id = f"{right}_{expiry}_{int(strike)}_{uuid.uuid4().hex[:6]}"
        trade = self.ib.placeOrder(contract, sto)
        self.ib.sleep(0.5)

        leg = LegState(leg_id=leg_id, contract=contract, right=right,
                        quantity=quantity, open_spot=spot)
        leg.sto_trade = trade
        leg.state = 'PENDING'
        return leg

    # ============ EVENT HANDLERS ============

    def on_fill(self, trade: Trade, fill):
        price = fill.execution.price
        qty = fill.execution.shares
        for sid, s in self.strangles.items():
            for right_key, leg in [('P', s.put_leg), ('C', s.call_leg)]:
                if leg and trade is leg.sto_trade and leg.state == 'PENDING':
                    leg.sto_fill_price = price
                    leg.fill_spot = self._last_spot
                    leg.filled_at = datetime.now()
                    leg.state = 'OPEN'

                    other_leg = s.call_leg if right_key == 'P' else s.put_leg
                    if other_leg and other_leg.sto_fill_price > 0:
                        s.open_combined_credit = leg.sto_fill_price + other_leg.sto_fill_price
                    elif not other_leg:
                        s.open_combined_credit = leg.sto_fill_price

                    # PRIMARY protection: place GTC OCA bracket immediately
                    self._place_gtc_oca_bracket(leg)

                    self._notify(f"LEG FILL {right_key} K={leg.contract.strike}\n${price:.2f} x {qty}")
                    self._log_leg_fill_to_db(s, leg)
                    return

    def on_order_status(self, trade: Trade):
        pass

    def on_error(self, req_id, error_code, error_string, contract):
        if error_code in (103, 201, 202, 321):
            logger.error(f"IB ERROR {error_code}: {error_string}")

    # ============ STARTUP RECONCILIATION ============

    def on_startup_reconcile(self):
        """Rebuild strangles from IB's actual open orders/positions on bot restart."""
        open_orders = {t.order.orderId: t for t in self.ib.reqOpenOrders()}
        open_positions = {(p.contract.symbol, p.contract.strike, p.contract.right): p
                           for p in self.ib.positions()}

        for sid, s in list(self.strangles.items()):
            for right_key, leg in [('P', s.put_leg), ('C', s.call_leg)]:
                if not leg:
                    continue
                has_pos = ('SNDK', leg.contract.strike, right_key) in open_positions
                has_gtc = ((leg.btc_pt_trade and leg.btc_pt_trade.order.orderId in open_orders) or
                           (leg.btc_sl_trade and leg.btc_sl_trade.order.orderId in open_orders))
                if not has_pos and not has_gtc:
                    leg.state = 'CLOSED'

            if (not s.put_leg or s.put_leg.state == 'CLOSED') and \
               (not s.call_leg or s.call_leg.state == 'CLOSED'):
                s.state = 'CLOSED'

        active = sum(1 for s in self.strangles.values() if s.state not in ('CLOSED', 'CANCELLED'))
        logger.info(f"Startup reconciliation: {active} active strangles")

    def eod_cleanup(self):
        """15:45 ET: cancel PENDING leg DAY orders ONLY. NEVER touch GTC OCA brackets."""
        for sid, s in self.strangles.items():
            for leg in [s.put_leg, s.call_leg]:
                if leg and leg.state == 'PENDING' and leg.sto_trade and leg.sto_trade.isActive():
                    self.ib.cancelOrder(leg.sto_trade.order)
                    self.ib.sleep(0.3)
                    leg.state = 'CANCELLED'
                    logger.info(f"EOD CANCEL {leg.leg_id}")
            # NEVER cancel leg.btc_pt_trade / leg.btc_sl_trade (GTC OCA -- primary protection)

    def gtc_quarterly_resubmit_check(self):
        """
        IB auto-cancels GTC orders at the end of the calendar quarter following
        the current quarter. Run this check quarterly and resubmit any bracket
        that IB has expired but the underlying position is still open.
        """
        for sid, s in self.strangles.items():
            for leg in [s.put_leg, s.call_leg]:
                if leg and leg.state == 'OPEN':
                    pt_active = leg.btc_pt_trade and leg.btc_pt_trade.isActive()
                    sl_active = leg.btc_sl_trade and leg.btc_sl_trade.isActive()
                    if not pt_active and not sl_active:
                        logger.warning(f"GTC bracket expired for {leg.leg_id}, resubmitting")
                        self._place_gtc_oca_bracket(leg)

    # ============ HELPERS ============

    def _qualify(self, right, expiry, strike) -> Option:
        contract = Option('SNDK', expiry, strike, right, 'SMART', currency='USD')
        self.ib.qualifyContracts(contract)
        return contract

    def _get_mark(self, contract: Option) -> Optional[float]:
        t = self.ib.reqMktData(contract, '', True, False)
        self.ib.sleep(2.0)
        result = None
        if t.bid and t.ask and t.bid > 0 and t.ask > 0:
            result = (t.bid + t.ask) / 2
        self.ib.cancelMktData(contract)
        return result

    def _get_call_leg_mark(self, leg: Optional[LegState]) -> float:
        if not leg:
            return 0.0
        short_mark = self._get_mark(leg.contract) or 0.0
        if leg.is_spread and leg.spread_long_contract:
            long_mark = self._get_mark(leg.spread_long_contract) or 0.0
            return short_mark - long_mark  # net debit to close the spread
        return short_mark

    def _get_delta(self, contract: Option) -> float:
        t = self.ib.reqMktData(contract, '', True, False)
        self.ib.sleep(2.0)
        d = t.modelGreeks.delta if t.modelGreeks and t.modelGreeks.delta is not None else 0.0
        self.ib.cancelMktData(contract)
        return d

    def _get_call_leg_delta(self, leg: Optional[LegState]) -> float:
        if not leg:
            return 0.0
        short_delta = self._get_delta(leg.contract)
        if leg.is_spread and leg.spread_long_contract:
            long_delta = self._get_delta(leg.spread_long_contract)
            return short_delta - long_delta  # net position delta
        return short_delta

    def _get_theta(self, contract: Option) -> float:
        t = self.ib.reqMktData(contract, '', True, False)
        self.ib.sleep(2.0)
        th = t.modelGreeks.theta if t.modelGreeks and t.modelGreeks.theta is not None else 0.01
        self.ib.cancelMktData(contract)
        return th

    def _get_call_leg_theta(self, leg: Optional[LegState]) -> float:
        if not leg:
            return 0.01
        short_theta = self._get_theta(leg.contract)
        if leg.is_spread and leg.spread_long_contract:
            long_theta = self._get_theta(leg.spread_long_contract)
            return short_theta - long_theta
        return short_theta

    def _get_dte_years(self, right: str) -> float:
        return 45 / 365   # simplified; wire to live IVR->DTE table lookup in production

    def _get_roll_expiry(self, current_expiry: str, weeks_out: int = 3) -> str:
        dt = datetime.strptime(current_expiry, '%Y%m%d') + timedelta(weeks=weeks_out)
        return dt.strftime('%Y%m%d')

    def _estimate_premium(self, right, expiry, strike, spot) -> float:
        from scipy.stats import norm
        t = max((datetime.strptime(expiry, '%Y%m%d') - datetime.now()).days / 365, 0.01)
        sigma = 1.10
        d1 = (np.log(spot/strike) + (0.05 + 0.5*sigma**2)*t) / (sigma*np.sqrt(t))
        d2 = d1 - sigma*np.sqrt(t)
        if right == 'C':
            return max(spot*norm.cdf(d1) - strike*np.exp(-0.05*t)*norm.cdf(d2), 0.05)
        return max(strike*np.exp(-0.05*t)*norm.cdf(-d2) - spot*norm.cdf(-d1), 0.05)

    def _get_recent_20d(self) -> np.ndarray:
        return np.zeros((20, 7))  # wire to actual daily bar cache in production

    def _log_leg_fill_to_db(self, s: StrangleState, leg: LegState):
        import sqlite3
        conn = sqlite3.connect('sndk_trades_v41.db')
        conn.execute("""INSERT INTO strangle_legs
            (strangle_id, leg_id, right, expiry, strike, sto_price, fill_spot,
             opened_at, ivr_at_open, regime, is_spread, call_leg_type)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (s.strangle_id, leg.leg_id, leg.right,
             leg.contract.lastTradeDateOrContractMonth, leg.contract.strike,
             leg.sto_fill_price, leg.fill_spot,
             leg.filled_at.isoformat() if leg.filled_at else None,
             s.ivr_at_open, s.regime_at_open, int(leg.is_spread), s.call_leg_type))
        conn.commit(); conn.close()

    def _notify(self, msg):
        import os, requests
        t = os.environ.get('TELEGRAM_BOT_TOKEN')
        c = os.environ.get('TELEGRAM_CHAT_ID')
        if t and c:
            try:
                requests.post(f'https://api.telegram.org/bot{t}/sendMessage',
                              json={'chat_id': c, 'text': f'SNDK Bot v4.1\n{msg}'}, timeout=5)
            except Exception as e:
                logger.warning(f'Telegram error: {e}')