
# Write the pseudocode file
pseudocode = '''# QQQ PMCC Backtest — Pseudocode v2
# Integrates: TurboBounce QQQ LEAPS Architecture + YouTube/BCI/Tastytrade PMCC Insights
# =====================================================================================

# ─────────────────────────────────────────────────────
# DATA INPUTS (per trading day)
# ─────────────────────────────────────────────────────
INPUTS:
  date              # trading date
  qqq_open          # QQQ open price
  qqq_close         # QQQ close price
  qqq_52w_low       # rolling 52-week low
  qqq_sma50/100/200 # simple moving averages
  vix_close         # CBOE VIX
  vix3m_close       # VIX 3-month (for term structure)
  hmm_p_bull        # Hidden Markov Model bull probability (0-1)
  leaps_price       # LEAPS mid price (from Black-Scholes model)
  leaps_delta       # LEAPS delta
  leaps_dte         # LEAPS days-to-expiration
  short_call_price  # short call mid price
  short_call_delta  # short call delta
  short_call_dte    # short call DTE
  ml_confidence     # LightGBM specialist model confidence (0-1)

# ─────────────────────────────────────────────────────
# POSITION STATE (per open trade)
# ─────────────────────────────────────────────────────
STATE:
  leaps_status      # NONE | OPEN
  leaps_entry_price # price paid for LEAPS
  leaps_entry_date  # date of LEAPS entry
  leaps_contracts   # number of contracts (max 5)
  leaps_entry_qqq   # QQQ price at LEAPS entry

  pmcc_status       # NONE | ACTIVE | DEFENSIVE
  short_call_credit # premium collected (C0) when short sold
  short_call_entry_date
  short_call_strike
  short_call_expiry
  pmcc_credit_cumulative  # total credits collected to date

  virtual_nav       # virtual account balance
  cost_basis        # leaps_entry_price - pmcc_credit_cumulative

# ─────────────────────────────────────────────────────
# STEP 1: CLASSIFY REGIME (Layer A)
# ─────────────────────────────────────────────────────
FUNCTION classify_regime(hmm_p_bull, vix, qqq, sma100, sma200):
  IF hmm_p_bull > 0.70 AND vix < 25:
    RETURN "BULL_STRONG"
  ELSE IF hmm_p_bull >= 0.55 AND vix < 35:
    RETURN "BULL_MODERATE"
  ELSE IF hmm_p_bull >= 0.35 AND hmm_p_bull < 0.55:
    RETURN "CHOPPY"
  ELSE IF hmm_p_bull < 0.35 OR qqq < sma100:
    RETURN "BEAR"
  IF qqq < sma200 * 0.97:   # more than 3% below SMA200
    RETURN "BEAR_SMA_FORCED"
  RETURN "BEAR"

# ─────────────────────────────────────────────────────
# STEP 2: LEAPS ENTRY (Layer B + C)
# ─────────────────────────────────────────────────────
FUNCTION check_leaps_entry(regime, ml_confidence, leaps_delta, qqq_gap_pct):
  IF regime NOT IN ["BULL_STRONG", "BULL_MODERATE", "CHOPPY"]:
    RETURN False

  threshold = 0.45 if regime == "BULL_STRONG" else 0.42
  IF ml_confidence < threshold:
    RETURN False

  # Validate dip-entry: gap down open
  IF qqq_gap_pct > -0.005:   # less than 0.5% gap down → not a panic entry
    RETURN False

  RETURN True

FUNCTION select_leaps_strike(regime):
  IF regime == "BULL_STRONG":   RETURN delta_target=0.85, dte_target=365
  IF regime == "BULL_MODERATE": RETURN delta_target=0.80, dte_target=365
  IF regime == "CHOPPY":        RETURN delta_target=0.80, dte_target=540

FUNCTION bci_initialization_check(leaps_price, short_call_strike, leaps_strike, qqq_upside=0.10):
  # BCI Formula: if QQQ rallies 10%, can we still close the whole diagonal at profit?
  leaps_intrinsic_at_rally  = (qqq_close * (1 + qqq_upside)) - leaps_strike
  short_call_loss_at_rally  = short_call_strike - (qqq_close * (1 + qqq_upside))  # negative if ITM
  estimated_combined_pnl = leaps_intrinsic_at_rally - leaps_price + short_call_credit + short_call_loss_at_rally
  IF estimated_combined_pnl < 0:
    RETURN False  # reject setup
  RETURN True

FUNCTION size_position(virtual_nav, leaps_price):
  allocation = virtual_nav * 0.33
  contracts  = FLOOR(allocation / (leaps_price * 100))
  RETURN MIN(contracts, 5)   # hard cap: 5

# ─────────────────────────────────────────────────────
# STEP 3: PMCC SHORT CALL ENTRY (Layer D)
# ─────────────────────────────────────────────────────
FUNCTION check_pmcc_entry(regime, leaps_status, leaps_age_days, leaps_dte, 
                           qqq_vs_leaps_entry, vix, pmcc_status):
  IF leaps_status != "OPEN":          RETURN False
  IF pmcc_status != "NONE":           RETURN False
  IF regime NOT IN ["BULL_STRONG", "BULL_MODERATE"]: RETURN False
  IF leaps_age_days < 5:              RETURN False
  IF leaps_dte <= 60:                 RETURN False
  IF qqq_vs_leaps_entry < 0.02:       RETURN False  # QQQ must be +2% off entry low
  IF vix < 16 OR vix > 35:           RETURN False   # avoid extreme IV environments
  RETURN True

FUNCTION select_short_call(regime, vix):
  dte_target = 30 if vix > 20 else 35   # slightly longer tenor in calm markets
  IF regime == "BULL_STRONG":
    delta_target = 0.28  # up to 0.30 hard max
  ELSE:
    delta_target = 0.23  # conservative in BULL_MODERATE
  min_premium = 0.50   # $50/contract minimum to enter
  RETURN dte_target, delta_target, min_premium

# ─────────────────────────────────────────────────────
# STEP 4: PMCC MANAGEMENT (per day, while ACTIVE)
# ─────────────────────────────────────────────────────
FUNCTION manage_pmcc(current_price, C0, days_since_sell, short_dte, 
                      short_delta, qqq_close, short_strike, regime, leaps_delta):

  days_elapsed = days_since_sell

  # ── Profit taking: BCI 20%/10% rule ──
  IF days_elapsed < 10 AND current_price <= C0 * 0.20:
    RETURN "PROFIT_TAKE_EARLY"    # ~80% profit captured early

  IF days_elapsed >= 10 AND current_price <= C0 * 0.10:
    RETURN "PROFIT_TAKE_LATE"     # ~90% profit captured

  # ── Gamma / expiration rule (Tastytrade 21-DTE manage rule) ──
  IF short_dte <= 21:
    IF short_delta > 0.10:        # still has some risk, manage it
      RETURN "GAMMA_MANAGE"       # close and re-sell fresh 30-35 DTE
    ELSE:
      RETURN "EXPIRE_WORTHLESS"   # let it go if nearly zero value

  # ── Rally / assignment risk ──
  IF qqq_close >= short_strike * 0.97 OR short_delta >= 0.40:
    RETURN "ROLL_UP_OUT"

  # ── Loss limit ──
  IF current_price >= C0 * 2.0:
    RETURN "LOSS_LIMIT_CLOSE"

  # ── Regime deterioration ──
  IF regime == "CHOPPY":
    RETURN "DEFENSIVE_ROLL"       # roll to 0.15 delta, same expiry

  IF regime IN ["BEAR", "BEAR_SMA_FORCED"]:
    RETURN "EMERGENCY_CLOSE"

  # ── LEAPS delta deterioration (Layer E Tier 1 integration) ──
  IF leaps_delta < 0.65:
    RETURN "TIER1_ROLL_DOWN"      # roll to 0.15 delta

  RETURN "HOLD"

# ─────────────────────────────────────────────────────
# STEP 5: DRAWDOWN GUARD (Layer E)
# ─────────────────────────────────────────────────────
FUNCTION drawdown_guard(leaps_delta, leaps_dte, qqq_close, qqq_52w_low, pmcc_status):

  # Morning scan (9:45 AM) — emergency tier only
  IF qqq_close <= qqq_52w_low * 1.02:
    RETURN "TIER3_EMERGENCY_EXIT"   # close LEAPS + short call simultaneously

  # Afternoon scan (3:00 PM)
  IF leaps_delta < 0.30 AND leaps_dte < 60:
    RETURN "TIER2_EXIT"

  IF leaps_delta < 0.65:
    IF pmcc_status == "ACTIVE":
      RETURN "TIER1_ROLL_SHORT_DOWN"
    RETURN "TIER1_MONITOR"

  RETURN "NO_ACTION"

# ─────────────────────────────────────────────────────
# STEP 6: ROLL EXECUTION LOGIC
# ─────────────────────────────────────────────────────
FUNCTION execute_roll(roll_type, current_short_price, qqq_close, expiry):
  IF roll_type == "ROLL_UP_OUT":
    new_expiry  = expiry + 21  # push out 21 days
    new_strike  = qqq_close * 1.03  # ~3% OTM
    new_delta   = target_delta_by_regime()  # 0.22-0.28
    net_credit  = new_short_premium - current_short_price
    IF net_credit < -0.10:
      RETURN "CLOSE_ONLY"   # cannot achieve net credit/small debit; skip roll

  IF roll_type == "DEFENSIVE_ROLL":
    new_delta  = 0.15   # low income, low risk
    new_expiry = same_expiry
    net_credit = new_short_premium - current_short_price

  IF roll_type == "TIER1_ROLL_DOWN":
    new_delta  = 0.15
    new_expiry = same_expiry

  RETURN new_expiry, new_strike, new_delta, net_credit

# ─────────────────────────────────────────────────────
# STEP 7: PMCC RESET (after profit take or loss close)
# ─────────────────────────────────────────────────────
FUNCTION reset_pmcc_after_close(close_reason, regime, leaps_status, leaps_age, leaps_dte, vix):
  IF close_reason IN ["PROFIT_TAKE_EARLY", "PROFIT_TAKE_LATE", "GAMMA_MANAGE"]:
    # Immediately check if we can re-open
    IF check_pmcc_entry(regime, leaps_status, leaps_age, leaps_dte, ..., vix, "NONE"):
      RETURN "RE_ENTER_PMCC"
    ELSE:
      RETURN "WAIT_LEAPS_ONLY"

  IF close_reason == "LOSS_LIMIT_CLOSE":
    RETURN "WAIT_LEAPS_ONLY"   # cooldown; wait for regime confirmation

  IF close_reason IN ["EMERGENCY_CLOSE", "TIER2_EXIT", "TIER3_EMERGENCY_EXIT"]:
    RETURN "FULL_RESET"

# ─────────────────────────────────────────────────────
# MAIN BACKTEST LOOP
# ─────────────────────────────────────────────────────
INITIALIZE:
  virtual_nav = 25000
  state = empty position state

FOR each trading_day in date_range:
  LOAD daily data (prices, VIX, HMM output, ML confidence, option chain)

  regime = classify_regime(hmm_p_bull, vix, qqq, sma100, sma200)

  # ── Morning exit scan (9:45 AM equivalent) ──
  dg = drawdown_guard(leaps_delta, leaps_dte, qqq_open, qqq_52w_low, pmcc_status)
  IF dg == "TIER3_EMERGENCY_EXIT":
    CLOSE leaps and short call at open price with 4% slippage
    UPDATE virtual_nav
    RESET state
    CONTINUE to next day

  # ── Afternoon full scan (3:00 PM equivalent) ──
  dg = drawdown_guard(leaps_delta, leaps_dte, qqq_close, qqq_52w_low, pmcc_status)
  IF dg in ["TIER2_EXIT", "TIER1_ROLL_SHORT_DOWN", "TIER1_MONITOR"]:
    HANDLE accordingly

  # ── LEAPS entry check ──
  IF leaps_status == "NONE":
    IF check_leaps_entry(regime, ml_confidence, leaps_delta, gap_pct):
      IF bci_initialization_check(...):
        contracts = size_position(virtual_nav, leaps_price)
        OPEN leaps position
        UPDATE state

  # ── PMCC entry check ──
  IF leaps_status == "OPEN" AND pmcc_status == "NONE":
    IF check_pmcc_entry(regime, "OPEN", leaps_age, leaps_dte, qqq_vs_entry, vix, "NONE"):
      dte, delta, min_prem = select_short_call(regime, vix)
      premium = get_option_price(dte, delta)
      IF premium >= min_prem:
        OPEN short call at mid - 0.05 (limit order simulation)
        UPDATE pmcc_status = "ACTIVE"
        RECORD short_call_credit = premium

  # ── PMCC management ──
  IF pmcc_status in ["ACTIVE", "DEFENSIVE"]:
    action = manage_pmcc(short_call_price, short_call_credit, days_since_sell,
                          short_dte, short_delta, qqq_close, short_strike, regime, leaps_delta)

    IF action in ["PROFIT_TAKE_EARLY", "PROFIT_TAKE_LATE"]:
      BUY BACK short call at short_call_price
      pmcc_credit_cumulative += (short_call_credit - short_call_price)
      result = reset_pmcc_after_close(action, ...)
      IF result == "RE_ENTER_PMCC": OPEN new short call

    ELSE IF action == "GAMMA_MANAGE":
      BUY BACK short call
      IF conditions allow: OPEN new 30-35 DTE short call immediately

    ELSE IF action == "ROLL_UP_OUT":
      execute_roll("ROLL_UP_OUT", ...)
      IF roll feasible: REPLACE short call at new strike/expiry

    ELSE IF action == "LOSS_LIMIT_CLOSE":
      BUY BACK at 2x credit (loss)
      pmcc_credit_cumulative -= short_call_credit  # net loss
      pmcc_status = "NONE"

    ELSE IF action in ["EMERGENCY_CLOSE", "DEFENSIVE_ROLL", "TIER1_ROLL_DOWN"]:
      HANDLE accordingly

  # ── Record daily NAV ──
  MARK_TO_MARKET:
    daily_nav = virtual_cash + leaps_mark_value - short_call_mark_value
  APPEND to results: [date, regime, daily_nav, leaps_delta, short_call_delta, pmcc_credit_cumulative]

OUTPUT:
  trades_log       # all entries/exits/rolls with prices
  daily_nav_series # daily portfolio value
  CAGR, Sharpe, MaxDrawdown, WinRate, Avg_Monthly_PMCC_Income
'''

with open('/root/qqq_pmcc_pseudocode_v2.txt', 'w') as f:
    f.write(pseudocode)
print("Pseudocode written.")
