"""
QQQ LEAPS — Layer D: PMCC Manager (v2)
========================================
Implements the full Poor Man's Covered Call (PMCC) lifecycle on top of an open
LEAPS position, following the v2 ruleset from:
  qqq-leaps/leaps rule set desc.md  (BCI 20%/10% + gamma rule + regime gates)

State machine transitions:
  LEAPS_ONLY → PMCC_ACTIVE   (entry conditions met)
  PMCC_ACTIVE → PMCC_ACTIVE  (profit-take + re-enter, or roll)
  PMCC_ACTIVE → PMCC_DEFENSIVE (regime drops to CHOPPY)
  PMCC_ACTIVE → LEAPS_ONLY   (loss limit, bear emergency)
  PMCC_DEFENSIVE → PMCC_ACTIVE (regime recovers)
  PMCC_DEFENSIVE → LEAPS_ONLY  (bear emergency)
  PMCC_ACTIVE / DEFENSIVE → CLOSED (Tier 2/3 DrawdownGuard exit)

Usage in scanner.py (3 PM scan):
    from .pmcc_manager import PMCCManager
    pmcc = PMCCManager(config)
    action = pmcc.evaluate(position, today_row, regime, spot, vix, iv_short)
    if action:
        # publish signal and execute via auto_approve.py
"""
import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger("PMCCManager")


# ── Action constants ──────────────────────────────────────────────────────────
class PMCCAction:
    NONE              = "NONE"
    ENTER             = "PMCC_ENTER"             # open short call
    PROFIT_TAKE_EARLY = "PMCC_PROFIT_TAKE_EARLY"  # closed 80%+ profit early
    PROFIT_TAKE_LATE  = "PMCC_PROFIT_TAKE_LATE"   # closed 90%+ profit late
    GAMMA_MANAGE      = "PMCC_GAMMA_MANAGE"        # ≤21 DTE — close and re-sell
    ROLL_UP_OUT       = "PMCC_ROLL_UP_OUT"         # rally risk — roll strike up + expiry out
    DEFENSIVE_ROLL    = "PMCC_DEFENSIVE_ROLL"      # regime → CHOPPY — roll to low delta
    TIER1_ROLL_DOWN   = "PMCC_TIER1_ROLL_DOWN"     # LEAPS delta < 0.65 — roll to 0.15 delta
    LOSS_LIMIT_CLOSE  = "PMCC_LOSS_LIMIT_CLOSE"    # 2× credit — forced buyback
    EMERGENCY_CLOSE   = "PMCC_CLOSE"               # BEAR regime — close immediately


@dataclass
class PMCCSignal:
    """Signal emitted by PMCCManager, published to DB and auto_approve."""
    action: str                  # PMCCAction constant
    leaps_position_id: str       # ties back to shadow_positions row
    user_id: str
    strategy: str = "QQQ_LEAPS"
    confidence: float = 0.0      # always 0.0 — management actions bypass gate
    auto_execute: bool = True

    # Short call details
    short_strike: float = 0.0
    short_expiry: str = ""
    short_delta: float = 0.0
    short_dte: int = 0
    limit_price: float = 0.0     # credit to collect (ENTER) or debit to pay (CLOSE)
    contracts: int = 0

    # For ROLL: new strike/expiry
    new_strike: float = 0.0
    new_expiry: str = ""
    new_delta: float = 0.0

    rationale: str = ""


# ── Helper: Black-Scholes delta approximation ────────────────────────────────
def _bs_call_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Approximate N(d1) using quick erf approximation."""
    if T <= 0 or sigma <= 0:
        return max(0.0, 1.0 if S > K else 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return 0.5 * (1 + math.erf(d1 / math.sqrt(2)))


def _bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call price."""
    if T <= 0:
        return max(S - K, 0.0)
    if sigma <= 0:
        return max(0.0, S - K * math.exp(-r * T))
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    Nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    Nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
    return S * Nd1 - K * math.exp(-r * T) * Nd2


# ── BCI Initialization Check ──────────────────────────────────────────────────
def bci_initialization_check(
    leaps_price: float,
    leaps_strike: float,
    short_call_credit: float,
    short_call_strike: float,
    qqq_close: float,
    qqq_rally_pct: float = 0.10,
    slippage_pct: float = 0.01,
) -> bool:
    """
    Blue Collar Investor 'forced-close' test.

    Simulates a +10% QQQ rally: LEAPS becomes mostly intrinsic (sell at intrinsic
    − slippage), short call is ITM (buy back at intrinsic + remaining extrinsic).
    Requires combined P&L ≥ 0 — ensures the diagonal is not fragile to upside.

    Returns True if setup is robust, False if it should be rejected.
    """
    qqq_at_rally = qqq_close * (1 + qqq_rally_pct)

    # LEAPS P&L at +10% rally (sell at intrinsic - slippage)
    leaps_intrinsic = max(qqq_at_rally - leaps_strike, 0)
    leaps_proceeds  = leaps_intrinsic * (1 - slippage_pct) * 100  # per contract
    leaps_cost      = leaps_price * 100                             # paid at entry

    # Short call P&L (credit collected minus buyback at intrinsic + extrinsic, +slippage)
    short_intrinsic = max(qqq_at_rally - short_call_strike, 0)
    short_buyback   = short_intrinsic * (1 + slippage_pct) * 100   # per contract
    short_credit    = short_call_credit * 100                        # collected at entry

    combined_pnl = (leaps_proceeds - leaps_cost) + (short_credit - short_buyback)
    ok = combined_pnl >= 0
    logger.debug(
        f"BCI check: LEAPS P&L={leaps_proceeds-leaps_cost:.0f} "
        f"Short P&L={short_credit-short_buyback:.0f} "
        f"Combined={combined_pnl:.0f} → {'PASS' if ok else 'FAIL'}"
    )
    return ok


# ── PMCCManager ───────────────────────────────────────────────────────────────
class PMCCManager:
    """
    Evaluates PMCC state for a single LEAPS position and returns a PMCCSignal
    describing the required action for the day.

    Called once per open position per 3 PM scan.
    """

    def __init__(self, config=None):
        if config is None:
            from .config import QQQLeapsConfig
            config = QQQLeapsConfig()
        self.cfg = config

    # ── Public entry point ────────────────────────────────────────────────────
    def evaluate(
        self,
        position: Dict[str, Any],   # shadow_positions row (or virtual portfolio position)
        today_row,                  # pd.Series — today's feature row from master
        regime: str,
        spot: float,
        vix: float,
        iv_short: float,            # IV for short call pricing (VIX × 1.12 typically)
        rf: float = 0.045,
    ) -> Optional[PMCCSignal]:
        """
        Main evaluation function. Returns a PMCCSignal if action required, else None.

        position dict must contain:
          - user_id
          - leaps_position_id (or 'id')
          - pmcc_state: LEAPS_ONLY | PMCC_ACTIVE | PMCC_DEFENSIVE
          - entry_price / leaps_entry_price
          - entry_date
          - strike (LEAPS strike)
          - expiry (LEAPS expiry ISO string)
          - contracts
          - pmcc_credit_c0 (credit when current short was sold, 0 if no short)
          - pmcc_short_strike
          - pmcc_short_expiry
          - pmcc_short_entry_date
          - pmcc_credit_cumulative
        """
        user_id   = position.get("user_id", "unknown")
        pos_id    = str(position.get("leaps_position_id", position.get("id", "?")))
        pmcc_state = position.get("pmcc_state", "LEAPS_ONLY")

        # LEAPS age
        entry_date_str = position.get("entry_date", date.today().isoformat())
        try:
            entry_dt  = date.fromisoformat(str(entry_date_str)[:10])
            leaps_age = (date.today() - entry_dt).days
        except Exception:
            leaps_age = 0

        # LEAPS DTE
        leaps_expiry_str = position.get("expiry", "")
        try:
            leaps_dte = (date.fromisoformat(leaps_expiry_str) - date.today()).days
        except Exception:
            leaps_dte = 365

        # LEAPS mark-to-market delta
        leaps_strike = float(position.get("strike", spot))
        T_leaps = max(leaps_dte / 365.0, 1 / 365.0)
        leaps_delta = _bs_call_delta(spot, leaps_strike, T_leaps, rf, iv_short / 1.12)

        # LEAPS entry price for QQQ recovery check
        leaps_entry_qqq = float(position.get("leaps_entry_qqq", spot))
        qqq_recovery = (spot - leaps_entry_qqq) / leaps_entry_qqq if leaps_entry_qqq > 0 else 0

        logger.debug(
            f"[PMCC {user_id}] state={pmcc_state} age={leaps_age}d "
            f"DTE={leaps_dte} LEAPS_delta={leaps_delta:.2f} "
            f"regime={regime} qqq_recovery={qqq_recovery:.1%}"
        )

        # ── Route by current state ─────────────────────────────────────────────
        if pmcc_state == "LEAPS_ONLY":
            return self._check_entry(
                user_id, pos_id, regime, leaps_age, leaps_dte, leaps_delta,
                leaps_strike, qqq_recovery, spot, vix, iv_short, rf,
            )

        elif pmcc_state in ("PMCC_ACTIVE", "PMCC_DEFENSIVE"):
            return self._manage_active(
                user_id, pos_id, position, pmcc_state,
                regime, leaps_delta, leaps_dte, spot, vix, iv_short, rf,
            )

        return None  # CLOSED or unknown state — nothing to do

    # ── Entry check ──────────────────────────────────────────────────────────
    def _check_entry(
        self,
        user_id: str, pos_id: str,
        regime: str, leaps_age: int, leaps_dte: int, leaps_delta: float,
        leaps_strike: float, qqq_recovery: float,
        spot: float, vix: float, iv_short: float, rf: float,
    ) -> Optional[PMCCSignal]:
        cfg = self.cfg

        # 5-condition gate (from v2 ruleset)
        if regime not in ("BULL_STRONG", "BULL_MODERATE"):
            logger.debug(f"[PMCC {user_id}] Entry skip: regime={regime}")
            return None
        if leaps_age < cfg.pmcc_min_leaps_age_days:
            logger.debug(f"[PMCC {user_id}] Entry skip: LEAPS age {leaps_age}d < {cfg.pmcc_min_leaps_age_days}d")
            return None
        if leaps_dte <= cfg.pmcc_min_leaps_dte:
            logger.debug(f"[PMCC {user_id}] Entry skip: LEAPS DTE {leaps_dte} ≤ {cfg.pmcc_min_leaps_dte}")
            return None
        if qqq_recovery < cfg.pmcc_qqq_recovery_pct:
            logger.debug(f"[PMCC {user_id}] Entry skip: QQQ recovery {qqq_recovery:.1%} < {cfg.pmcc_qqq_recovery_pct:.1%}")
            return None
        if not (cfg.pmcc_min_vix <= vix <= cfg.pmcc_max_vix):
            logger.debug(f"[PMCC {user_id}] Entry skip: VIX {vix:.1f} outside [{cfg.pmcc_min_vix},{cfg.pmcc_max_vix}]")
            return None

        # Select delta and DTE
        target_delta = (
            cfg.pmcc_delta_bull_strong if regime == "BULL_STRONG"
            else cfg.pmcc_delta_bull_moderate
        )
        dte_target = cfg.pmcc_dte  # 30-35 DTE

        # Find short call strike that targets our delta
        short_strike = self._find_strike_for_delta(spot, dte_target, rf, iv_short, target_delta)
        short_expiry = (date.today() + timedelta(days=dte_target)).isoformat()
        T_short = dte_target / 365.0
        short_price = _bs_call_price(spot, short_strike, T_short, rf, iv_short)

        # BCI initialization check
        if not bci_initialization_check(
            leaps_price=0,  # Not available here — use conservative pass
            leaps_strike=leaps_strike,
            short_call_credit=short_price,
            short_call_strike=short_strike,
            qqq_close=spot,
        ):
            logger.info(f"[PMCC {user_id}] Entry rejected by BCI initialization check")
            return None

        if short_price < cfg.pmcc_min_premium:
            logger.debug(f"[PMCC {user_id}] Entry skip: premium ${short_price:.2f} < ${cfg.pmcc_min_premium:.2f}")
            return None

        limit_price = round(short_price * 0.99, 2)  # Sell at mid − small haircut

        logger.info(
            f"[PMCC {user_id}] ENTER short call: strike={short_strike:.1f} "
            f"expiry={short_expiry} delta={target_delta:.2f} credit=${limit_price:.2f}"
        )
        return PMCCSignal(
            action=PMCCAction.ENTER,
            leaps_position_id=pos_id,
            user_id=user_id,
            short_strike=short_strike,
            short_expiry=short_expiry,
            short_delta=target_delta,
            short_dte=dte_target,
            limit_price=limit_price,
            rationale=(
                f"PMCC entry: regime={regime} VIX={vix:.1f} "
                f"strike={short_strike:.1f} delta={target_delta:.2f} credit=${limit_price:.2f}"
            ),
        )

    # ── Active / Defensive management ────────────────────────────────────────
    def _manage_active(
        self,
        user_id: str, pos_id: str,
        position: Dict[str, Any],
        pmcc_state: str,
        regime: str,
        leaps_delta: float,
        leaps_dte: int,
        spot: float,
        vix: float,
        iv_short: float,
        rf: float,
    ) -> Optional[PMCCSignal]:
        cfg = self.cfg

        # Short call data
        C0            = float(position.get("pmcc_credit_c0", 0))
        short_strike  = float(position.get("pmcc_short_strike", spot * 1.05))
        short_expiry  = position.get("pmcc_short_expiry", "")
        entry_date_str= position.get("pmcc_short_entry_date", date.today().isoformat())

        try:
            short_expiry_dt = date.fromisoformat(short_expiry)
            short_dte = (short_expiry_dt - date.today()).days
        except Exception:
            short_dte = 30

        try:
            short_entry_dt  = date.fromisoformat(str(entry_date_str)[:10])
            days_since_sell = (date.today() - short_entry_dt).days
        except Exception:
            days_since_sell = 0

        T_short   = max(short_dte / 365.0, 1 / 365.0)
        current_price = _bs_call_price(spot, short_strike, T_short, rf, iv_short)
        short_delta   = _bs_call_delta(spot, short_strike, T_short, rf, iv_short)

        logger.debug(
            f"[PMCC {user_id}] manage: state={pmcc_state} C0={C0:.2f} "
            f"now={current_price:.2f} dte={short_dte} delta={short_delta:.2f} "
            f"days_since={days_since_sell}"
        )

        # ── Priority 0: Emergency exit on BEAR regime ─────────────────────────
        if regime in ("BEAR", "BEAR_SMA_FORCED"):
            logger.warning(f"[PMCC {user_id}] EMERGENCY_CLOSE — regime={regime}")
            return PMCCSignal(
                action=PMCCAction.EMERGENCY_CLOSE,
                leaps_position_id=pos_id,
                user_id=user_id,
                short_strike=short_strike,
                short_expiry=short_expiry,
                limit_price=round(current_price * 1.01, 2),  # pay debit to close
                rationale=f"Emergency close: regime={regime}",
            )

        # ── Priority 0b: LEAPS DrawdownGuard Tier 1 ──────────────────────────
        if leaps_delta < cfg.dd_delta_rolldown_trigger:
            logger.info(f"[PMCC {user_id}] TIER1_ROLL_DOWN — LEAPS delta={leaps_delta:.2f}")
            roll_dte = short_dte  # same expiry
            new_strike = self._find_strike_for_delta(
                spot, roll_dte, rf, iv_short, cfg.pmcc_delta_defensive
            )
            new_expiry = short_expiry
            return PMCCSignal(
                action=PMCCAction.TIER1_ROLL_DOWN,
                leaps_position_id=pos_id,
                user_id=user_id,
                short_strike=short_strike,
                short_expiry=short_expiry,
                new_strike=new_strike,
                new_expiry=new_expiry,
                new_delta=cfg.pmcc_delta_defensive,
                limit_price=round(current_price * 1.01, 2),
                rationale=f"Tier1 roll: LEAPS delta={leaps_delta:.2f} < {cfg.dd_delta_rolldown_trigger}",
            )

        # ── Priority 1: Gamma / 21-DTE management rule ───────────────────────
        if short_dte <= cfg.pmcc_gamma_manage_dte:
            if short_delta > 0.10:  # still has risk
                logger.info(f"[PMCC {user_id}] GAMMA_MANAGE — DTE={short_dte} delta={short_delta:.2f}")
                return PMCCSignal(
                    action=PMCCAction.GAMMA_MANAGE,
                    leaps_position_id=pos_id,
                    user_id=user_id,
                    short_strike=short_strike,
                    short_expiry=short_expiry,
                    limit_price=round(current_price * 1.01, 2),
                    rationale=f"Gamma manage: DTE={short_dte} ≤ {cfg.pmcc_gamma_manage_dte}",
                )
            # Else near-zero delta — let expire worthless (no action needed)
            return None

        # ── Priority 2: Profit-take rules (BCI 20% / 10%) ────────────────────
        if C0 > 0:
            if days_since_sell < cfg.pmcc_early_cycle_days and current_price <= C0 * cfg.pmcc_profit_take_early_pct:
                logger.info(f"[PMCC {user_id}] PROFIT_TAKE_EARLY — {current_price/C0:.0%} of credit")
                return PMCCSignal(
                    action=PMCCAction.PROFIT_TAKE_EARLY,
                    leaps_position_id=pos_id,
                    user_id=user_id,
                    short_strike=short_strike,
                    short_expiry=short_expiry,
                    limit_price=round(current_price * 1.01, 2),
                    rationale=f"Early profit: price={current_price:.2f} ≤ {cfg.pmcc_profit_take_early_pct:.0%}×C0={C0:.2f}",
                )
            if days_since_sell >= cfg.pmcc_early_cycle_days and current_price <= C0 * cfg.pmcc_profit_take_late_pct:
                logger.info(f"[PMCC {user_id}] PROFIT_TAKE_LATE — {current_price/C0:.0%} of credit")
                return PMCCSignal(
                    action=PMCCAction.PROFIT_TAKE_LATE,
                    leaps_position_id=pos_id,
                    user_id=user_id,
                    short_strike=short_strike,
                    short_expiry=short_expiry,
                    limit_price=round(current_price * 1.01, 2),
                    rationale=f"Late profit: price={current_price:.2f} ≤ {cfg.pmcc_profit_take_late_pct:.0%}×C0={C0:.2f}",
                )

        # ── Priority 3: Rally / assignment risk ──────────────────────────────
        if spot >= short_strike * (1 - cfg.pmcc_force_close_gap_pct) or short_delta >= cfg.pmcc_roll_delta_trigger:
            new_expiry_dt = date.fromisoformat(short_expiry) + timedelta(days=cfg.pmcc_roll_new_expiry_days)
            new_dte = (new_expiry_dt - date.today()).days
            target_d = cfg.pmcc_delta_bull_strong if regime == "BULL_STRONG" else cfg.pmcc_delta_bull_moderate
            new_strike = self._find_strike_for_delta(spot, new_dte, rf, iv_short, target_d)
            new_expiry = new_expiry_dt.isoformat()
            logger.info(
                f"[PMCC {user_id}] ROLL_UP_OUT — QQQ={spot:.1f} near strike={short_strike:.1f} "
                f"delta={short_delta:.2f}"
            )
            return PMCCSignal(
                action=PMCCAction.ROLL_UP_OUT,
                leaps_position_id=pos_id,
                user_id=user_id,
                short_strike=short_strike,
                short_expiry=short_expiry,
                new_strike=new_strike,
                new_expiry=new_expiry,
                new_delta=target_d,
                limit_price=round(current_price * 1.01, 2),
                rationale=(
                    f"Roll up/out: QQQ={spot:.1f} vs strike={short_strike:.1f} "
                    f"short_delta={short_delta:.2f} → new_strike={new_strike:.1f} expiry={new_expiry}"
                ),
            )

        # ── Priority 4: Loss limit ────────────────────────────────────────────
        if C0 > 0 and current_price >= C0 * cfg.pmcc_loss_limit_multiple:
            logger.warning(f"[PMCC {user_id}] LOSS_LIMIT_CLOSE — price={current_price:.2f} >= {cfg.pmcc_loss_limit_multiple}×{C0:.2f}")
            return PMCCSignal(
                action=PMCCAction.LOSS_LIMIT_CLOSE,
                leaps_position_id=pos_id,
                user_id=user_id,
                short_strike=short_strike,
                short_expiry=short_expiry,
                limit_price=round(current_price * 1.01, 2),
                rationale=f"Loss limit: {current_price:.2f} ≥ {cfg.pmcc_loss_limit_multiple}×C0={C0:.2f}",
            )

        # ── Priority 5: Regime deterioration to CHOPPY ───────────────────────
        if regime == "CHOPPY" and pmcc_state == "PMCC_ACTIVE":
            # Roll to defensive delta (same expiry, lower strike)
            new_strike = self._find_strike_for_delta(
                spot, short_dte, rf, iv_short, cfg.pmcc_delta_defensive
            )
            logger.info(f"[PMCC {user_id}] DEFENSIVE_ROLL — regime=CHOPPY → delta={cfg.pmcc_delta_defensive}")
            return PMCCSignal(
                action=PMCCAction.DEFENSIVE_ROLL,
                leaps_position_id=pos_id,
                user_id=user_id,
                short_strike=short_strike,
                short_expiry=short_expiry,
                new_strike=new_strike,
                new_expiry=short_expiry,  # same expiry
                new_delta=cfg.pmcc_delta_defensive,
                limit_price=round(current_price * 1.01, 2),
                rationale=f"Defensive roll: regime=CHOPPY → 0.15 delta strike={new_strike:.1f}",
            )

        # ── HOLD ──────────────────────────────────────────────────────────────
        logger.debug(f"[PMCC {user_id}] HOLD — no action required")
        return None

    # ── Strike finder ─────────────────────────────────────────────────────────
    def _find_strike_for_delta(
        self,
        spot: float,
        dte: int,
        rf: float,
        iv: float,
        target_delta: float,
        step: float = 0.50,
    ) -> float:
        """
        Binary-search a strike price achieving approximately target_delta.
        Returns nearest $0.50 strike.
        """
        T = max(dte / 365.0, 1 / 365.0)
        low, high = spot * 0.80, spot * 1.40
        for _ in range(40):
            mid = (low + high) / 2
            d = _bs_call_delta(spot, mid, T, rf, iv)
            if abs(d - target_delta) < 0.001:
                break
            if d > target_delta:
                low = mid
            else:
                high = mid
        # Round to nearest $0.50
        return round(mid / step) * step

    # ── DB schema helpers ─────────────────────────────────────────────────────
    @staticmethod
    def get_db_migration_sql() -> str:
        """Returns SQL to run on PostgreSQL to add PMCC tracking columns/tables."""
        return """
-- Add PMCC state tracking to shadow_positions
ALTER TABLE shadow_positions
    ADD COLUMN IF NOT EXISTS pmcc_state VARCHAR(20) DEFAULT 'LEAPS_ONLY',
    ADD COLUMN IF NOT EXISTS pmcc_credit_cumulative FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pmcc_credit_c0 FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pmcc_short_strike FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pmcc_short_expiry DATE,
    ADD COLUMN IF NOT EXISTS pmcc_short_entry_date DATE,
    ADD COLUMN IF NOT EXISTS leaps_entry_qqq FLOAT DEFAULT 0.0;

-- Short-call cycle ledger: one row per PMCC cycle (open → close)
CREATE TABLE IF NOT EXISTS pmcc_cycles (
    id                   SERIAL PRIMARY KEY,
    user_id              VARCHAR(50) NOT NULL,
    strategy             VARCHAR(30) DEFAULT 'QQQ_LEAPS',
    leaps_position_id    INTEGER,
    short_strike         FLOAT,
    short_expiry         DATE,
    short_dte_at_entry   INTEGER,
    short_delta_at_entry FLOAT,
    credit_collected     FLOAT,   -- C0: premium when sold
    credit_buyback       FLOAT,   -- what we paid to close (NULL if not yet closed)
    net_credit           FLOAT,   -- credit_collected - credit_buyback (NULL if open)
    entry_date           DATE,
    exit_date            DATE,
    exit_reason          VARCHAR(50),
    tastytrade_order_id  VARCHAR(60),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pmcc_cycles_user
    ON pmcc_cycles (user_id, strategy, entry_date DESC);
"""
