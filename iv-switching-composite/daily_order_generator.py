"""
Daily Order Generator
=====================
Runs every trading day at 4:15 PM ET.

One global IV-Switching signal is generated from today's market data, then
for each subscribed user:
  1. Fetch their live TastyTrade account balance + positions
  2. Count what strategy positions they already have
  3. Determine what order the strategy calls for
  4. Build exact OCC option symbols + order legs
  5. Persist to user_daily_orders table

Entry point: run_daily_order_generation(trade_date=today)
"""

import sys
import os
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

log = logging.getLogger("IVS.DailyOrders")

# ── Add iv-switching-composite to path ────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

# ── Internal imports (strategy engine) ───────────────────────────────────────
import data.features as features
from regime_engine import classify_mode, should_open_d1
from position_sizer import (
    size_csp_trade, size_zebra_trade, size_ccs_trade, size_d2_sqqq
)
from pricing import bs_call_price, bs_put_price, find_strike_for_delta, SLIPPAGE_PER_SIDE


def _get_monthly_friday(ref_date: date, offset_days: int = 35) -> date:
    import pandas_market_calendars as mcal
    nyse = mcal.get_calendar('NYSE')
    
    target = pd.Timestamp(ref_date) + pd.Timedelta(days=offset_days)
    weekday = target.weekday()
    if weekday < 4:
        target += pd.Timedelta(days=4 - weekday)
    elif weekday > 4:
        target += pd.Timedelta(days=7 - weekday + 4)
        
    date_obj = target.date()
    # Step backward if the target Friday is a market holiday.
    while len(nyse.valid_days(start_date=date_obj, end_date=date_obj)) == 0:
        date_obj -= timedelta(days=1)
        
    return date_obj


def _get_standard_monthly_expiry(ref_date: date, min_dte: int = 30) -> date:
    """
    Returns the nearest STANDARD MONTHLY expiry (3rd Friday of month) that is
    at least min_dte calendar days away from ref_date.

    Standard monthly expirations are guaranteed to be listed by TT/CBOE well
    in advance, unlike weekly expirations which TT only lists 4-6 weeks ahead.
    Using a weekly expiry can trigger 'Instrument not found in TT catalog'.
    """
    from calendar import monthcalendar
    import pandas_market_calendars as mcal
    nyse = mcal.get_calendar('NYSE')
    
    y, m = ref_date.year, ref_date.month
    for _ in range(6):  # check up to 6 months ahead
        cal = monthcalendar(y, m)
        # All Fridays (weekday index 4) in month, skipping zeros (padding)
        fridays = [week[4] for week in cal if week[4] != 0]
        third_friday = date(y, m, fridays[2])  # 3rd Friday (0-indexed)
        
        # IMPORTANT: Do NOT adjust backward for market holidays.
        # The OCC always registers standard monthly contracts on the 3rd Friday —
        # even when markets are closed that day (e.g., June 19 Juneteenth, Good Friday).
        # The *last trading day* shifts to Thursday, but the OCC contract symbol and
        # TastyTrade's option chain always use the official Friday expiration date.
        # Stepping back to Thursday produces symbols like 260618 that TT does not have.
        valid_date = third_friday

        dte = (valid_date - ref_date).days
        if dte >= min_dte:
            return valid_date
        # Advance to next month
        m += 1
        if m > 12:
            m = 1
            y += 1
    raise ValueError(f"Could not find standard monthly expiry >= {min_dte} DTE from {ref_date}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Generate Global Daily Signal
# ─────────────────────────────────────────────────────────────────────────────

def generate_daily_signal(trade_date: date) -> dict:
    """
    Runs regime_engine on today's market data and returns a snapshot dict
    that is shared across all user order calculations.
    """
    import pandas as pd
    date_str = trade_date.strftime("%Y-%m-%d")
    # Fetch a 400-day lookback so indicators (SMA200, IVP, etc.) are valid
    start = (trade_date - timedelta(days=400)).strftime("%Y-%m-%d")

    log.info(f"Building feature set for {date_str}...")
    df = features.build_feature_set(start, date_str)
    if df.empty:
        raise RuntimeError(f"No market data returned for {date_str}")

    row = df.iloc[-1]

    # ── Extract core market data (historical close as baseline) ──────────────
    qqq_px       = float(row['qqq_close'])
    qqqm_px      = float(row['qqqm_close'])
    tqqq_px      = float(row['tqqq_close'])
    sqqq_px      = float(row['sqqq_close'])
    vix          = float(row['vix'])
    rf           = float(row['rf'])
    iv_short     = float(row['qqq_short_iv'])
    iv_leaps     = float(row['qqq_iv_leaps'])   # LEAPS-tenor IV (~110% of spot VIX)
    iv_tqqq_10d  = float(row['tqqq_iv_10d'])
    vvix_10d_chg = float(row.get('vvix_10d_chg', 0))
    vix_vix3m    = float(row['vix_vix3m_ratio'])

    # ── Override with live spot prices for accurate strike computation ─────────
    # Priority: 1) IB Gateway (batch, single connection)  2) yfinance 5-min intraday
    #           3) yfinance Ticker.fast_info (most reliable REST fallback)
    # Falls back to historical close ONLY if all three fail — logs a loud warning.
    SPOT_SYMBOLS = ["QQQ", "QQQM", "TQQQ", "SQQQ"]
    live_prices: dict = {}

    # Attempt 1: IB Gateway (batch — one connection for all symbols)
    try:
        from ib_options_pricing import get_live_spot_prices
        live_prices = get_live_spot_prices(SPOT_SYMBOLS)
        if live_prices:
            log.info(f"IB batch spot prices: {live_prices}")
    except Exception as ib_err:
        log.warning(f"IB live spot fetch failed: {ib_err}")

    # Attempt 2: yfinance 5-min intraday (works during market hours, no IB needed)
    missing = [s for s in SPOT_SYMBOLS if s not in live_prices]
    if missing:
        try:
            import yfinance as yf
            import pandas as pd
            raw = yf.download(missing, period="1d", interval="5m",
                              auto_adjust=True, progress=False, threads=False)
            if not raw.empty:
                # raw["Close"] is a Series for 1 symbol, DataFrame for multiple
                close_data = raw["Close"] if "Close" in raw.columns else raw
                for sym in missing:
                    try:
                        if isinstance(close_data, pd.DataFrame) and sym in close_data.columns:
                            series = close_data[sym].dropna()
                        elif isinstance(close_data, pd.Series):
                            series = close_data.dropna()  # single-symbol case
                        else:
                            continue
                        if not series.empty:
                            last = float(series.iloc[-1])
                            if last > 0:
                                live_prices[sym] = last
                                log.info(f"yfinance intraday {sym}: ${last:.2f}")
                    except Exception:
                        pass
        except Exception as yf_err:
            log.warning(f"yfinance intraday fallback failed: {yf_err}")

    # Attempt 3: yfinance Ticker.fast_info — most reliable on high-volatility days
    # (single lightweight REST call per symbol; doesn't require intraday history)
    missing = [s for s in SPOT_SYMBOLS if s not in live_prices]
    if missing:
        try:
            import yfinance as yf
            for sym in missing:
                try:
                    ticker = yf.Ticker(sym)
                    px = getattr(ticker.fast_info, 'last_price', None)
                    if px and float(px) > 0:
                        live_prices[sym] = float(px)
                        log.info(f"yfinance fast_info {sym}: ${float(px):.2f}")
                except Exception as _ticker_err:
                    log.debug(f"yfinance fast_info {sym} failed: {_ticker_err}")
        except Exception as yf3_err:
            log.warning(f"yfinance fast_info fallback failed: {yf3_err}")

    # Cross-check: ALWAYS verify QQQ with yfinance fast_info regardless of IB success.
    # During fast market crashes, IB delayed data can lag by 30+ minutes.
    # In a crash, the lower price is always safer (prevents OTM strikes that don't exist).
    try:
        import yfinance as yf
        _yf_ticker = yf.Ticker("QQQ")
        _yf_px = getattr(_yf_ticker.fast_info, 'last_price', None)
        if _yf_px and float(_yf_px) > 0:
            _yf_px = float(_yf_px)
            _ib_px = live_prices.get("QQQ", qqq_px)
            _diff = abs(_yf_px - _ib_px) / _ib_px
            if _diff > 0.03:
                # Prices differ by >3% — use the LOWER one to stay conservative
                _chosen = min(_yf_px, _ib_px)
                log.warning(
                    f"QQQ price discrepancy: IB=${_ib_px:.2f} yfinance=${_yf_px:.2f} "
                    f"(diff={_diff:.1%}) — using lower ${_chosen:.2f} to avoid stale strikes"
                )
                live_prices["QQQ"] = _chosen
            else:
                log.info(f"QQQ cross-check OK: IB=${_ib_px:.2f} yfinance=${_yf_px:.2f}")
    except Exception as _xcheck_err:
        log.debug(f"QQQ cross-check failed (non-fatal): {_xcheck_err}")

    # Apply live prices (log delta vs historical close)
    for sym, live_px in live_prices.items():
        if sym == "QQQ" and live_px > 0:
            diff = abs(live_px - qqq_px) / qqq_px
            if diff > 0.05:
                log.warning(f"STALE STRIKE WARNING: QQQ live ${live_px:.2f} vs close ${qqq_px:.2f} (diff {diff:.1%})")
            log.info(f"QQQ live ${live_px:.2f} vs close ${qqq_px:.2f} — using live for strikes")
            qqq_px = live_px
        elif sym == "QQQM" and live_px > 0:
            qqqm_px = live_px
        elif sym == "TQQQ" and live_px > 0:
            tqqq_px = live_px
        elif sym == "SQQQ" and live_px > 0:
            sqqq_px = live_px

    if not live_prices:
        log.warning("No live spot prices available — using historical closes (strikes may be stale)")

    # Classify regime (no user-specific peak_vix at this level)
    mode = classify_mode(row, peak_vix=None, d2_active=False, current_date=date_str)

    signal = {
        "trade_date":   trade_date,
        "mode":         mode,
        "qqq_px":       qqq_px,
        "qqqm_px":      qqqm_px,
        "tqqq_px":      tqqq_px,
        "sqqq_px":      sqqq_px,
        "vix":          vix,
        "rf":           rf,
        "iv_short":     iv_short,
        "iv_leaps":     iv_leaps,
        "iv_tqqq_10d":  iv_tqqq_10d,
        "vvix_10d_chg": vvix_10d_chg,
        "vix_vix3m":    vix_vix3m,
        "row":          row,          # full row for advanced calcs
    }
    log.info(f"Daily signal: Mode={mode}, VIX={vix:.1f}, QQQ=${qqq_px:.2f}, QQQM=${qqqm_px:.2f}")
    return signal



# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Fetch & Classify User's Live TastyTrade Account
# ─────────────────────────────────────────────────────────────────────────────

def fetch_user_account_state(user) -> dict:
    """
    Creates a TastyTrade session for the user and returns their live
    account balance + classified position summary.

    Args:
        user: models.user.User ORM object (must have tt_refresh_token)

    Returns:
        dict with cash, nlv, buying_power, position_counts, raw_positions
    """
    from tastytrade_utils import create_user_session, get_user_account

    if not user.tt_refresh_token:
        raise ValueError(f"User {user.id} has no tt_refresh_token")

    session = create_user_session(user.tt_refresh_token)
    account = get_user_account(session, getattr(user, 'tt_account_number', None))
    balances  = account.get_balances(session)
    positions = account.get_positions(session)

    # Classify positions
    pos_counts = _classify_tt_positions(positions)

    return {
        "session":        session,
        "account":        account,
        "cash":           float(getattr(balances, 'cash_balance', 0) or 0),
        "nlv":            float(getattr(balances, 'net_liquidating_value', 0) or 0),
        "buying_power":   float(getattr(balances, 'derivative_buying_power', 0) or 0),
        "position_counts": pos_counts,
        "raw_positions":  positions,
    }


def _classify_tt_positions(positions) -> dict:
    """
    Inspect live TastyTrade positions and classify into strategy buckets.

    - ZEBRA = QQQM calls (2 long + 1 short per unit)
    - CSP   = TQQQ short puts
    - CCS   = QQQ short call spread
    - SQQQ  = SQQQ long shares
    """
    qqqm_long_qty  = 0
    qqqm_short_qty = 0
    tqqq_short_put = 0
    qqq_ccs_count  = 0
    sqqq_shares    = 0

    for pos in positions:
        symbol   = getattr(pos, 'underlying_symbol', '') or ''
        qty      = int(getattr(pos, 'quantity', 0) or 0)
        itype    = getattr(pos, 'instrument_type', '') or ''
        opt_type = getattr(pos, 'option_type', '') or ''

        if symbol == 'SQQQ' and itype in ('Equity', ''):
            sqqq_shares += qty
        elif symbol == 'TQQQ' and opt_type.upper() in ('P', 'PUT') and qty < 0:
            tqqq_short_put += abs(qty)
        elif symbol == 'QQQ' and opt_type.upper() in ('C', 'CALL'):
            if qty < 0:
                qqq_ccs_count += 1
        elif symbol == 'QQQM' and opt_type.upper() in ('C', 'CALL'):
            if qty > 0:
                qqqm_long_qty += qty
            else:
                qqqm_short_qty += abs(qty)

    # Each ZEBRA unit = 2 long calls + 1 short call
    zebra_by_long  = qqqm_long_qty // 2
    zebra_by_short = qqqm_short_qty
    zebra_units    = min(zebra_by_long, zebra_by_short)

    return {
        "zebra_units":  zebra_units,
        "csp_count":    tqqq_short_put,
        "ccs_count":    qqq_ccs_count // 2,   # pairs
        "sqqq_shares":  sqqq_shares,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Build Order for Each Mode
# ─────────────────────────────────────────────────────────────────────────────

def _build_zebra_order(signal: dict, contracts: int) -> dict:
    """Builds a Mode B ZEBRA order dict with exact OCC symbols.

    ZEBRA ratio spread: 2× long 70-delta / 1× short 50-delta at 75 DTE (same expiry).
    Validated by Perplexity (2026-03-22): lower net debit than PMCC diagonal, higher
    upside convexity, and theta-neutral from Day 0 — optimal for 30–60 day hold periods.
    """
    qqqm_px  = signal['qqqm_px']
    iv_short = signal['iv_short']
    rf       = signal['rf']
    T_z      = 75 / 365.0

    # QQQM uses $1 strike increments — round continuous B-S output to nearest integer
    long_strike  = round(find_strike_for_delta(qqqm_px, T_z, rf, iv_short, 0.70, 'call'))
    short_strike = round(find_strike_for_delta(qqqm_px, T_z, rf, iv_short, 0.50, 'call'))

    expiry  = _get_monthly_friday(signal['trade_date'], 75)
    exp_str = expiry.strftime('%y%m%d')

    # ── Try IB Gateway for real bid/ask; fall back to Black-Scholes ──────────
    net_debit = None
    try:
        from ib_options_pricing import get_option_spread_quote
        ib_q = get_option_spread_quote("QQQM", short_strike, long_strike, exp_str, "C")
        if ib_q and ib_q.long_mid > 0:
            net_debit = round((2 * ib_q.long_mid) - ib_q.short_mid, 2)
            log.info(f"IB ZEBRA: long_mid={ib_q.long_mid}, short_mid={ib_q.short_mid}, net_debit={net_debit}")
    except Exception as _e:
        log.debug(f"IB ZEBRA pricing unavailable: {_e}")
    if net_debit is None or net_debit <= 0:
        lc_px = bs_call_price(qqqm_px, long_strike,  T_z, rf, iv_short)
        sc_px = bs_call_price(qqqm_px, short_strike, T_z, rf, iv_short)
        net_debit = round((2 * lc_px) - sc_px, 2)
        log.info(f"B-S ZEBRA: long={long_strike} lc={lc_px:.2f}, short={short_strike} sc={sc_px:.2f}, net_debit={net_debit}")

    long_occ  = f"QQQM  {exp_str}C{int(long_strike * 1000):08d}"
    short_occ = f"QQQM  {exp_str}C{int(short_strike * 1000):08d}"

    cap = round(net_debit * contracts * 100, 2)

    return {
        "signal_type":     "OPEN_ZEBRA",
        "symbol":          "QQQM",
        "option_type":     "ZEBRA",
        "contracts":       contracts,
        "long_strike":     long_strike,
        "short_strike":    short_strike,
        "expiry_date":     expiry,
        "limit_price":     net_debit,
        "capital_required": cap,
        "order_legs": [
            {"action": "BUY_TO_OPEN",  "symbol": long_occ,  "qty": contracts * 2,
             "instrument_type": "Equity Option"},
            {"action": "SELL_TO_OPEN", "symbol": short_occ, "qty": contracts,
             "instrument_type": "Equity Option"},
        ],
    }


def _build_csp_order(signal: dict, contracts: int) -> dict:
    """Builds a Mode A TQQQ CSP order dict with exact OCC symbol."""
    tqqq_px    = signal['tqqq_px']
    rf         = signal['rf']
    iv_tqqq    = signal['iv_tqqq_10d']
    T_csp      = 7 / 365.0

    # TQQQ uses $0.50 increments — round to nearest 0.5 to get a valid strike
    _raw_strike = find_strike_for_delta(tqqq_px, T_csp, rf, iv_tqqq, 0.12, 'put')
    strike = round(_raw_strike * 2) / 2

    # Expiry: next Friday (7 DTE)
    d = signal['trade_date']
    days_to_fri = (4 - d.weekday()) % 7
    if days_to_fri == 0:
        days_to_fri = 7
    expiry  = d + timedelta(days=days_to_fri)
    exp_str = expiry.strftime('%y%m%d')

    # ── Try IB Gateway for real bid/ask; fall back to Black-Scholes ──────────
    premium = None
    try:
        from ib_options_pricing import get_single_option_quote
        ib_q = get_single_option_quote("TQQQ", int(strike), exp_str, "P")
        if ib_q and ib_q[0] > 0:
            premium = round((ib_q[0] + ib_q[1]) / 2, 2)  # mid price
            log.info(f"IB CSP: bid={ib_q[0]}, ask={ib_q[1]}, mid={premium}")
    except Exception as _e:
        log.debug(f"IB CSP pricing unavailable: {_e}")
    if premium is None or premium <= 0:
        premium = round(bs_put_price(tqqq_px, strike, T_csp, rf, iv_tqqq), 2)
        log.info(f"B-S CSP: strike={strike}, premium={premium}")

    occ = f"TQQQ  {exp_str}P{int(strike * 1000):08d}"

    return {
        "signal_type":     "OPEN_CSP",
        "symbol":          "TQQQ",
        "option_type":     "CSP",
        "contracts":       contracts,
        "long_strike":     None,
        "short_strike":    strike,
        "expiry_date":     expiry,
        "limit_price":     premium,
        "capital_required": round(strike * contracts * 100, 2),  # margin held
        "order_legs": [
            {"action": "SELL_TO_OPEN", "symbol": occ, "qty": contracts,
             "instrument_type": "Equity Option"},
        ],
    }


def _build_ccs_order(signal: dict, contracts: int) -> dict:
    """Builds a Mode C QQQ Bear Call Spread order."""
    qqq_px   = signal['qqq_px']
    iv_short = signal['iv_short']
    rf       = signal['rf']
    T_ccs    = 45 / 365.0

    # QQQ options trade in $1 strike increments at all price levels (CBOE carve-out for QQQ/IWM/SPY).
    # Use round() to nearest whole dollar — do NOT round to $5 which are not the correct intervals.
    short_strike = round(find_strike_for_delta(qqq_px, T_ccs, rf, iv_short, 0.30, 'call'))
    long_strike  = round(find_strike_for_delta(qqq_px, T_ccs, rf, iv_short, 0.20, 'call'))

    # Use the STANDARD MONTHLY (3rd Friday) expiry — guaranteed to be listed
    # in TT/CBOE catalog. Weekly expirations (~45 DTE) may not be listed yet
    # and trigger 'Instrument not found in TT catalog' on submission.
    expiry  = _get_standard_monthly_expiry(signal['trade_date'], min_dte=40)
    exp_str = expiry.strftime('%y%m%d')

    # ── Try IB for real bid/ask; fall back to Black-Scholes ──────────────────
    net_credit = None
    try:
        from ib_options_pricing import get_option_spread_quote
        ib_quote = get_option_spread_quote("QQQ", short_strike, long_strike, exp_str, "C")
        if ib_quote and ib_quote.net_credit > 0:
            net_credit = ib_quote.net_credit
            log.info(f"IB CCS quote: short={short_strike} mid={ib_quote.short_mid}, long={long_strike} mid={ib_quote.long_mid}, net_credit={net_credit}")
    except Exception as _e:
        log.debug(f"IB CCS pricing unavailable: {_e}")
    if net_credit is None:
        sc_px = bs_call_price(qqq_px, short_strike, T_ccs, rf, iv_short)
        lc_px = bs_call_price(qqq_px, long_strike,  T_ccs, rf, iv_short)
        net_credit = round(sc_px - lc_px, 2)
        log.info(f"B-S CCS: short={short_strike} sc={sc_px:.2f}, long={long_strike} lc={lc_px:.2f}, net_credit={net_credit}")

    margin = round((long_strike - short_strike) * 100, 2)

    short_occ = f"QQQ   {exp_str}C{int(short_strike * 1000):08d}"
    long_occ  = f"QQQ   {exp_str}C{int(long_strike  * 1000):08d}"

    return {
        "signal_type":      "OPEN_CCS",
        "symbol":           "QQQ",
        "option_type":      "CCS",
        "contracts":        contracts,
        "long_strike":      long_strike,
        "short_strike":     short_strike,
        "expiry_date":      expiry,
        "limit_price":      net_credit,
        "capital_required": round(margin * contracts, 2),
        "order_legs": [
            {"action": "SELL_TO_OPEN", "symbol": short_occ, "qty": contracts,
             "instrument_type": "Equity Option"},
            {"action": "BUY_TO_OPEN",  "symbol": long_occ,  "qty": contracts,
             "instrument_type": "Equity Option"},
        ],
    }


def _build_sqqq_order(signal: dict, dollar_amount: float) -> dict:
    """Builds a Mode D2 SQQQ equity buy order."""
    sqqq_px = signal['sqqq_px']
    shares  = max(int(dollar_amount / sqqq_px), 0)
    if shares == 0:
        return _hold_order("Insufficient cash for SQQQ")

    return {
        "signal_type":      "OPEN_SQQQ",
        "symbol":           "SQQQ",
        "option_type":      "EQUITY",
        "contracts":        shares,
        "long_strike":      None,
        "short_strike":     None,
        "expiry_date":      None,
        "limit_price":      round(sqqq_px, 2),
        "capital_required": round(shares * sqqq_px, 2),
        "order_legs": [
            {"action": "BUY", "symbol": "SQQQ", "qty": shares,
             "instrument_type": "Equity"},
        ],
    }


def _hold_order(reason: str = "Strategy is HOLD") -> dict:
    """Returns a NO_ACTION order placeholder."""
    return {
        "signal_type":      "NO_ACTION",
        "symbol":           None,
        "option_type":      None,
        "contracts":        0,
        "long_strike":      None,
        "short_strike":     None,
        "expiry_date":      None,
        "limit_price":      None,
        "capital_required": 0.0,
        "order_legs":       [],
        "skip_reason":      reason,
    }


# (P3 OVERLAY_SHORT_CALL removed: Perplexity confirmed selling on negative momentum
#  caps upside during V-shape recoveries. The ZEBRA's built-in 50-delta short already
#  handles theta collection. Do not add a separate overlay.)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Exit Scanner & Order Generation
# ─────────────────────────────────────────────────────────────────────────────

def check_exits(account_state: dict, signal: dict) -> list:
    """
    Scans the user's live TastyTrade positions and generates BUY_TO_CLOSE / SELL_TO_CLOSE
    legs if any exit conditions (profit target, stop-loss, time-stop, max-loss) are met.
    """
    from datetime import date
    try:
        from ib_options_pricing import get_option_spread_quote, get_single_option_quote
    except ImportError:
        get_option_spread_quote = None
        get_single_option_quote = None
        log.warning("IB pricing unavailable — check_exits will not work without live data.")

    close_legs = []
    raw_positions = account_state.get('raw_positions', [])
    today = signal.get('trade_date', date.today())
    mode = signal.get('mode', 'NO_ACTION')

    # Group TT positions by underlying and expiry
    csps = []   # TQQQ short puts
    # FIX #1: Use separate short/long lists per expiry to support MULTIPLE spreads
    # at the same expiry (different strikes). Previous single-slot dict was overwriting
    # earlier spreads, leaving orphaned legs unmanaged through to assignment.
    ccs_shorts = {}  # { expiry_str: [ {'pos', 'occ', 'strike', 'qty'}, ... ] }
    ccs_longs  = {}  # { expiry_str: [ {'pos', 'occ', 'strike', 'qty'}, ... ] }
    zebras = {}    # QQQM zebras: { expiry: { 'short': pos, 'long': pos } }

    for pos in raw_positions:
        symbol = getattr(pos, 'underlying_symbol', '') or ''
        qty = int(getattr(pos, 'quantity', 0) or 0)
        itype = getattr(pos, 'instrument_type', '') or ''
        opt_type = getattr(pos, 'option_type', '') or ''
        occ = getattr(pos, 'symbol', '') or ''
        
        if itype != 'Equity Option' or qty == 0:
            continue
            
        # Parse OCC: QQQ   260515C00612000 => expiry is 260515
        if len(occ) >= 15:
            expiry_str = occ[6:12]
            strike = int(occ[13:]) / 1000.0
            
            if symbol == 'TQQQ' and opt_type in ('P', 'PUT') and qty < 0:
                csps.append({'pos': pos, 'expiry_str': expiry_str, 'strike': strike})
                
            elif symbol == 'QQQ' and opt_type in ('C', 'CALL'):
                entry = {'pos': pos, 'occ': occ, 'strike': strike, 'qty': qty}
                if qty < 0:
                    ccs_shorts.setdefault(expiry_str, []).append(entry)
                else:
                    ccs_longs.setdefault(expiry_str, []).append(entry)
                    
            elif symbol == 'QQQM' and opt_type in ('C', 'CALL'):
                if expiry_str not in zebras:
                    zebras[expiry_str] = {}
                if qty < 0:
                    zebras[expiry_str]['short'] = {'pos': pos, 'occ': occ, 'strike': strike, 'qty': qty}
                else:
                    zebras[expiry_str]['long'] = {'pos': pos, 'occ': occ, 'strike': strike, 'qty': qty}

    if not get_option_spread_quote or not get_single_option_quote:
        log.warning("IB not loaded, skipping exits.")
        return close_legs 

    # Evaluate MODE A: TQQQ CSP Exits
    force_close_csps = mode in ['C', 'D2']
    for csp in csps:
        strike = csp['strike']
        expiry_str = csp['expiry_str']
        pos = csp['pos']
        try:
            entry_premium = abs(float(getattr(pos, 'average_open_price', 0) or 0))
        except ValueError:
            entry_premium = 0.0
        qty = abs(int(getattr(pos, 'quantity', 0) or 0))
        occ = getattr(pos, 'symbol', '')
        
        exp_y, exp_m, exp_d = 2000 + int(expiry_str[:2]), int(expiry_str[2:4]), int(expiry_str[4:6])
        exp_date = date(exp_y, exp_m, exp_d)
        
        q = get_single_option_quote('TQQQ', strike, expiry_str, 'P')
        if q and entry_premium > 0:
            current_val = q[1]  # ask
            profit_pct = 1.0 - (current_val / entry_premium)
            
            if profit_pct >= 0.50 or current_val > entry_premium * 3.0 or today >= exp_date or force_close_csps:
                log.info(f"Closing CSP {occ}: profit={profit_pct*100:.1f}%, force={force_close_csps}")
                close_legs.append({"action": "BUY_TO_CLOSE", "symbol": occ, "qty": qty, "instrument_type": "Equity Option"})

    # Evaluate MODE C: QQQ CCS Exits
    # FIX #1: Iterate all expiries from both short and long lists; pair each short with
    # its nearest long above (by strike), consuming each long only once.
    # FIX #2: Force-close any spread with DTE <= 3 to prevent OCC auto-assignment.
    # FIX #4: Use min(short_qty, long_qty) for close quantities to handle mismatches.
    all_ccs_expiries = set(ccs_shorts.keys()) | set(ccs_longs.keys())
    for exp_str in all_ccs_expiries:
        exp_y, exp_m, exp_d = 2000 + int(exp_str[:2]), int(exp_str[2:4]), int(exp_str[4:6])
        exp_date = date(exp_y, exp_m, exp_d)
        dte = (exp_date - today).days
        # FIX #2: Force close 3 days before expiry to avoid OCC auto-exercise/assignment
        force_close_expiry = dte <= 3

        shorts = sorted(ccs_shorts.get(exp_str, []), key=lambda x: x['strike'])
        longs  = list(sorted(ccs_longs.get(exp_str, []),  key=lambda x: x['strike']))

        for sl in shorts:
            short_strike = sl['strike']
            # Find the nearest long leg whose strike is above this short strike
            paired_long = None
            for ll in longs:
                if ll['strike'] > short_strike:
                    paired_long = ll
                    break
            if not paired_long:
                log.warning(f"CCS orphaned short leg {sl['occ']} — no paired long found for exp {exp_str}")
                if force_close_expiry:
                    # Close the orphaned short alone to prevent assignment
                    orphan_qty = abs(int(getattr(sl['pos'], 'quantity', 0) or 0))
                    log.warning(f"Force-closing orphaned short {sl['occ']} (qty={orphan_qty}) — DTE={dte}")
                    close_legs.append({"action": "BUY_TO_CLOSE", "symbol": sl['occ'], "qty": orphan_qty, "instrument_type": "Equity Option"})
                continue
            longs.remove(paired_long)  # consume this long leg

            long_strike = paired_long['strike']
            # FIX #4: Use each leg's own quantity; close the paired (minimum) amount
            short_qty = abs(int(getattr(sl['pos'], 'quantity', 0) or 0))
            long_qty  = abs(int(getattr(paired_long['pos'], 'quantity', 0) or 0))
            close_qty = min(short_qty, long_qty)
            if short_qty != long_qty:
                log.warning(f"CCS quantity mismatch for exp {exp_str}: short={short_qty} long={long_qty} — closing min={close_qty}")

            try:
                sc_entry = abs(float(getattr(sl['pos'], 'average_open_price', 0) or 0))
                lc_entry = float(getattr(paired_long['pos'], 'average_open_price', 0) or 0)
            except ValueError:
                sc_entry, lc_entry = 0.0, 0.0
            entry_premium = sc_entry - lc_entry

            q = get_option_spread_quote('QQQ', short_strike, long_strike, exp_str, 'C')
            should_close = force_close_expiry  # always close near expiry
            close_reason = f"DTE={dte} expiry protection" if force_close_expiry else ""

            if q and entry_premium > 0:
                liability = max(q.short_ask - q.long_bid, 0)
                profit_pct = 1.0 - (liability / entry_premium)
                if profit_pct >= 0.50:
                    should_close = True
                    close_reason = f"profit={profit_pct*100:.1f}%"
                elif liability >= entry_premium * 3.0:
                    should_close = True
                    close_reason = f"loss limit (liability={liability:.2f})"
            elif not q and force_close_expiry:
                # Can't get a quote but we must close near expiry anyway
                should_close = True

            if should_close:
                log.info(f"Closing CCS {exp_str} {short_strike}/{long_strike}: {close_reason} (qty={close_qty})")
                close_legs.append({"action": "BUY_TO_CLOSE", "symbol": sl['occ'], "qty": close_qty, "instrument_type": "Equity Option"})
                close_legs.append({"action": "SELL_TO_CLOSE", "symbol": paired_long['occ'], "qty": close_qty, "instrument_type": "Equity Option"})

        # Warn about any remaining unmatched long legs
        for ll in longs:
            log.warning(f"CCS orphaned long leg {ll['occ']} — no paired short found for exp {exp_str}")

    # Evaluate MODE B: QQQM ZEBRA Exits
    for exp_str, legs in zebras.items():
        if 'short' in legs and 'long' in legs:
            sl = legs['short']
            ll = legs['long']
            short_strike = sl['strike']
            long_strike = ll['strike']
            short_qty = abs(sl['qty'])
            long_qty = ll['qty']
            if long_qty != short_qty * 2:
                continue 
                
            try:
                sc_entry = abs(float(getattr(sl['pos'], 'average_open_price', 0) or 0))
                lc_entry = float(getattr(ll['pos'], 'average_open_price', 0) or 0)
            except ValueError:
                sc_entry, lc_entry = 0.0, 0.0
            entry_debit = (lc_entry * 2) - sc_entry
            
            exp_y, exp_m, exp_d = 2000 + int(exp_str[:2]), int(exp_str[2:4]), int(exp_str[4:6])
            exp_date = date(exp_y, exp_m, exp_d)
            dte = (exp_date - today).days
            
            q = get_option_spread_quote('QQQM', short_strike, long_strike, exp_str, 'C')
            if q and entry_debit > 0:
                val = max((q.long_bid * 2) - q.short_ask, 0)
                profit_pct = (val - entry_debit) / entry_debit
                time_stop = dte <= 21
                # FIX #2: Also force-close ZEBRA 3 days before expiry to avoid assignment
                force_close_expiry = dte <= 3

                if profit_pct >= 0.50 or time_stop or val <= 0.01 or force_close_expiry:
                    close_reason = (
                        f"profit={profit_pct*100:.1f}%" if profit_pct >= 0.50
                        else (f"DTE={dte} expiry protection" if force_close_expiry
                              else ("time_stop" if time_stop else "val~0"))
                    )
                    log.info(f"Closing ZEBRA {exp_str}: {close_reason}")
                    close_legs.append({"action": "BUY_TO_CLOSE", "symbol": sl['occ'], "qty": short_qty, "instrument_type": "Equity Option"})
                    close_legs.append({"action": "SELL_TO_CLOSE", "symbol": ll['occ'], "qty": long_qty, "instrument_type": "Equity Option"})

    # Evaluate MODE D2: SQQQ Equity Exit
    # Exit conditions (from backtest): 30% profit, vix term structure in contango,
    # regime switched to D3/A/B, or 21-day time-stop
    sqqq_px = signal.get('sqqq_px', 0)
    for pos in raw_positions:
        pos_symbol = getattr(pos, 'underlying_symbol', '') or ''
        pos_itype  = getattr(pos, 'instrument_type', '') or ''
        pos_qty    = int(getattr(pos, 'quantity', 0) or 0)
        if pos_symbol == 'SQQQ' and pos_itype in ('Equity', 'Equity Option', '') and pos_qty > 0:
            entry_price = float(getattr(pos, 'average_open_price', 0) or 0)
            if entry_price > 0 and sqqq_px > 0:
                pnl_pct   = (sqqq_px / entry_price) - 1.0
                vix_vix3m = signal.get('vix_vix3m', 1.0)
                # Close if: profit target hit, term structure normalized, regime shifted, or time-stop
                if pnl_pct >= 0.30 or vix_vix3m < 1.0 or mode in ('D3', 'A', 'B'):
                    reason = ("30% profit" if pnl_pct >= 0.30 else
                              "contango" if vix_vix3m < 1.0 else f"mode={mode}")
                    log.info(f"Closing SQQQ ({pos_qty} shares): {reason}, pnl={pnl_pct*100:.1f}%")
                    close_legs.append({"action": "SELL", "symbol": "SQQQ", "qty": pos_qty, "instrument_type": "Equity"})

    return close_legs

def _reconcile_open_orders(signal: dict, account_state: dict) -> dict:
    """
    Given today's global signal and the user's live account state, determine
    what new entry order (if any) the strategy requires.
    """
    mode  = signal['mode']
    nav   = account_state['nlv']
    cash  = account_state['cash']
    pc    = account_state['position_counts']

    if nav <= 0:
        return _hold_order("Account NAV is zero or negative")

    # ── Mode A: Sell weekly TQQQ CSP ─────────────────────────────────────────
    if mode == 'A':
        if pc['csp_count'] > 0:
            return _hold_order("Already have open CSP — no new entry needed")
        _csp_strike = round(find_strike_for_delta(signal['tqqq_px'], 7/365.0,
                                                  signal['rf'], signal['iv_tqqq_10d'],
                                                  0.12, 'put') * 2) / 2
        contracts = size_csp_trade(nav, signal['vix'], _csp_strike)
        if contracts == 0:
            return _hold_order("NAV too small or VIX too high for CSP")
        # Cash constraint: collateral = strike * 100 per contract
        collateral = _csp_strike * 100
        if cash < collateral * contracts:
            contracts = max(int(cash / collateral), 0)
        if contracts == 0:
            return _hold_order("Insufficient cash for CSP collateral")
        return _build_csp_order(signal, contracts)

    # ── Mode B: Open QQQM ZEBRA (75 DTE, 2× 70-delta / 1× 50-delta) ─────────
    elif mode == 'B':
        if pc['zebra_units'] >= 2:
            return _hold_order("Already at max ZEBRA slots (2)")
        contracts = size_zebra_trade(nav, 0, n_open=pc['zebra_units'])
        # Re-compute with actual debit
        qqqm_px  = signal['qqqm_px']
        T_z      = 75 / 365.0
        ls = find_strike_for_delta(qqqm_px, T_z, signal['rf'], signal['iv_short'], 0.70, 'call')
        ss = find_strike_for_delta(qqqm_px, T_z, signal['rf'], signal['iv_short'], 0.50, 'call')
        lc = bs_call_price(qqqm_px, ls, T_z, signal['rf'], signal['iv_short'])
        sc = bs_call_price(qqqm_px, ss, T_z, signal['rf'], signal['iv_short'])
        net_debit = (2 * lc) - sc
        contracts = size_zebra_trade(nav, net_debit, n_open=pc['zebra_units'])
        if contracts == 0:
            return _hold_order("NAV too small or already max slots")
        cost = net_debit * contracts * 100
        if cash < cost * 1.05:  # 5% buffer
            return _hold_order(f"Insufficient cash (need ${cost:.0f}, have ${cash:.0f})")
        return _build_zebra_order(signal, contracts)

    # ── Mode C: Bear Call Spread (LEAPS held, not rolled) ─────────────────────
    elif mode == 'C':
        # P4 (kept): Existing ZEBRA positions are held through Mode C for recovery —
        # the regime engine is the stop-loss; no forced close, no new roll.
        # CCS income continues regardless — it runs in parallel with open LEAPS
        # since it uses free buying power and is unrelated to the ZEBRA position.
        if pc['ccs_count'] > 0:
            return _hold_order("Already have open CCS — no new entry")
        qqq_px   = signal['qqq_px']
        T_ccs    = 45 / 365.0
        ss = round(find_strike_for_delta(qqq_px, T_ccs, signal['rf'], signal['iv_short'], 0.30, 'call'))
        ls = round(find_strike_for_delta(qqq_px, T_ccs, signal['rf'], signal['iv_short'], 0.20, 'call'))
        margin_per = round((ls - ss) * 100, 2)
        contracts = size_ccs_trade(nav, margin_per)
        if contracts == 0:
            return _hold_order("NAV too small for CCS margin")
        # Cash constraint: margin held per contract
        if margin_per > 0 and cash < margin_per * contracts:
            contracts = max(int(cash / margin_per), 0)
        if contracts == 0:
            return _hold_order("Insufficient cash for CCS margin")
        return _build_ccs_order(signal, contracts)

    # ── Mode D2: Buy SQQQ ─────────────────────────────────────────────────────
    elif mode == 'D2':
        if pc['sqqq_shares'] > 0:
            return _hold_order("Already have SQQQ position")
        dollar_amt = size_d2_sqqq(nav, signal['vix'])
        if cash < dollar_amt:
            dollar_amt = cash * 0.95
        return _build_sqqq_order(signal, dollar_amt)

    # ── Mode D3: Crash recovery re-entry ─────────────────────────────────────
    elif mode == 'D3':
        if pc['zebra_units'] >= 2:
            return _hold_order("Already at max ZEBRA slots for D3 recovery")
        # Same 75 DTE ZEBRA params as Mode B
        qqqm_px  = signal['qqqm_px']
        T_z      = 75 / 365.0
        ls = find_strike_for_delta(qqqm_px, T_z, signal['rf'], signal['iv_short'], 0.70, 'call')
        ss = find_strike_for_delta(qqqm_px, T_z, signal['rf'], signal['iv_short'], 0.50, 'call')
        lc = bs_call_price(qqqm_px, ls, T_z, signal['rf'], signal['iv_short'])
        sc = bs_call_price(qqqm_px, ss, T_z, signal['rf'], signal['iv_short'])
        net_debit = (2 * lc) - sc
        contracts = size_zebra_trade(nav, net_debit, n_open=pc['zebra_units'])
        if contracts == 0:
            return _hold_order("NAV too small for D3 re-entry")
        order = _build_zebra_order(signal, contracts)
        order["signal_type"] = "OPEN_ZEBRA_D3"
        return order

    return _hold_order(f"Unrecognized mode: {mode}")

def reconcile_and_generate_order(signal: dict, account_state: dict) -> dict:
    """
    Given today's global signal and the user's live account state, determine
    what order (if any) the strategy requires, including EXITS.
    """
    # 1. Evaluate Exits via IB pricing
    close_legs = check_exits(account_state, signal)
    
    # 2. Evaluate Entries
    order = _reconcile_open_orders(signal, account_state)
    
    # 3. Combine
    if close_legs:
        if order['signal_type'] in ['NO_ACTION', 'HOLD']:
            order['signal_type'] = 'CLOSE_POSITIONS'
            order['order_legs']  = close_legs
            order['skip_reason'] = None
            order['limit_price'] = 0.0 # Will submit at market or mid in frontend
        else:
            # Append close legs to the open legs
            order['order_legs'] = close_legs + order.get('order_legs', [])
            
    return order


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Persist to DB
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_order(db_session, user_id: str, trade_date: date,
                  signal: dict, account_state: dict, order: dict):
    """
    Insert or update a UserDailyOrder row for this user+date.
    """
    from models.user_daily_order import UserDailyOrder
    from sqlalchemy import and_

    existing = db_session.query(UserDailyOrder).filter(
        and_(UserDailyOrder.user_id == user_id,
             UserDailyOrder.trade_date == trade_date)
    ).first()

    pc = account_state['position_counts']
    nav = account_state['nlv']
    cap = order.get('capital_required', 0)

    row_data = dict(
        user_id           = user_id,
        trade_date        = trade_date,
        strategy_mode     = signal['mode'],
        signal_type       = order['signal_type'],
        account_cash      = account_state['cash'],
        account_nlv       = nav,
        account_bp        = account_state['buying_power'],
        open_zebra_count  = pc['zebra_units'],
        open_csp_count    = pc['csp_count'],
        open_ccs_count    = pc['ccs_count'],
        open_sqqq_shares  = pc['sqqq_shares'],
        symbol            = order.get('symbol'),
        option_type       = order.get('option_type'),
        contracts         = order.get('contracts', 0),
        capital_required  = cap,
        nav_pct           = round(cap / nav, 4) if nav > 0 else 0,
        order_legs        = order.get('order_legs', []),
        limit_price       = order.get('limit_price'),
        long_strike       = order.get('long_strike'),
        short_strike      = order.get('short_strike'),
        expiry_date       = order.get('expiry_date'),
        status            = 'PENDING',
        skip_reason       = order.get('skip_reason'),
        generation_error  = None,
    )

    if existing:
        for k, v in row_data.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
        row = existing
    else:
        import uuid
        row_data['id'] = str(uuid.uuid4())
        row = UserDailyOrder(**row_data)
        db_session.add(row)

    db_session.commit()
    log.info(f"  └─ {user_id[:8]}… | {signal['mode']} | {order['signal_type']} | "
             f"${cap:.0f} ({row_data['nav_pct']*100:.1f}% NAV)")
    return row


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5b — Serialize as TurboCore-Compatible Signal
# ─────────────────────────────────────────────────────────────────────────────

def format_as_turbocore_signal(signal: dict, order: dict, order_db_id: str) -> dict:
    """
    Converts an IV-Switching order into a TQQQ_TURBOCORE_PRO-format signal
    payload so it renders in the existing TurboCoreSignalCard without any
    frontend changes.

    Regime mapping:
      Mode A (CSP)   → 'SIDEWAYS'  (calm, theta-income environment)
      Mode B (ZEBRA) → 'BULL'      (trend-following long exposure)
      Mode C (CCS)   → 'BEAR'      (defensive, directional short)
      Mode D2 (SQQQ) → 'BEAR'      (crash hedge)
      Mode D3        → 'BULL'      (crash recovery re-entry)
    """
    mode = signal['mode']
    signal_type = order.get('signal_type', 'NO_ACTION')
    regime_map = {
        'A': 'SIDEWAYS',
        'B': 'BULL',
        'C': 'BEAR',
        'D2': 'BEAR',
        'D3': 'BULL',
    }
    # CLOSE_POSITIONS orders use 'NEUTRAL' regime regardless of current mode
    regime = 'NEUTRAL' if signal_type == 'CLOSE_POSITIONS' else regime_map.get(mode, 'SIDEWAYS')

    # Confidence: inverse of VIX percentile (lower VIX → higher confidence in the signal)
    vix = signal.get('vix', 20.0)
    confidence = round(min(0.95, max(0.50, 1.0 - (vix / 60.0))), 3)

    # Build legs in TurboCore format — the card displays them in the order grid
    legs = []
    for leg in (order.get('order_legs') or []):
        legs.append({
            'symbol':     leg['symbol'],            # Do NOT .strip() — OCC padding is required
            'action':     leg['action'],           # BUY_TO_OPEN, SELL_TO_OPEN, etc.
            'qty':        leg['qty'],
            'target_pct': 0.0,                     # not applicable for options legs
        })

    option_type   = order.get('option_type', '')
    contracts     = order.get('contracts', 0)
    expiry        = order.get('expiry_date')
    expiry_str    = expiry.isoformat() if hasattr(expiry, 'isoformat') else str(expiry or '')
    limit_price   = order.get('limit_price', 0)

    return {
        # TurboCore Pro signal shape — matches TurboCoreSignal interface in frontend
        'strategy':          'TQQQ_TURBOCORE_PRO',
        'action':            signal_type,
        'regime':            regime,

        'confidence':        confidence,
        'capital_required':  order.get('capital_required', 0),
        'cost':              limit_price,
        'legs':              legs,
        'rationale': (
            f'IV-Switching Mode {mode} · {signal_type} · '
            f'VIX {vix:.1f} · {contracts} contract(s) · '
            f'Exp {expiry_str} · Limit ${limit_price:.2f}'
        ),
        'ema_signal':        1 if mode in ('B', 'D3') else 0,
        'sma200_gate':       mode not in ('D2', 'D3'),
        # Back-reference: used by auto_approve.py to route to IV-Switching
        # placement engine instead of TurboCore equity rebalancer
        'iv_switching_order_id': order_db_id,
    }


def _publish_user_signal(turbocore_payload: dict, user_id: str) -> None:
    """
    Persists the IV-Switching options signal to the PostgreSQL signals table
    (so the TradeMind frontend signal card can display it), writes to the
    shared JSON file, and fires an SSE push notification.
    """
    import json, os, uuid, requests

    payload = {
        **turbocore_payload,
        'id':         str(uuid.uuid4()),
        'user_id':    user_id,
        'status':     'pending',
        'createdAt':  datetime.utcnow().isoformat() + 'Z',
    }

    # ── PRIMARY: Write to PostgreSQL signals table ──────────────────────────
    # This is what the TradeMind frontend actually reads from.
    # Uses the same signal_publisher used by the TurboCore Pro equity signals.
    try:
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import sys
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from signal_publisher.turbocore import publish_turbocore_rebalance_signal

        legs_formatted = payload.get('legs', [])
        alloc_legs = [
            {
                'symbol':     leg.get('symbol', ''),  # Do NOT .strip() — OCC padding required
                'action':     leg.get('action', ''),
                'qty':        leg.get('qty', 0),
                'target_pct': 0.0,
            }
            for leg in legs_formatted
        ]

        publish_turbocore_rebalance_signal(
            regime=payload.get('regime', 'SIDEWAYS'),
            confidence=payload.get('confidence', 0.7),
            alloc_dict={},          # No equity allocation for options signals
            rationale=payload.get('rationale', ''),
            ema_signal=payload.get('ema_signal', 0),
            sma200_gate=payload.get('sma200_gate', True),
            strategy='TQQQ_TURBOCORE_PRO',
            legs_override=alloc_legs,
            action_override=payload.get('action'),
            user_id_override=user_id,
            iv_switching_order_id=payload.get('iv_switching_order_id', ''),
            cost_override=payload.get('cost', 0),  # Pass limit price to DB
        )
        log.info(f"  ✅ Persisted IV-Switching signal to DB for user {user_id[:8]}")
    except Exception as e:
        log.warning(f"  ⚠️ DB signal persist failed (non-fatal): {e}")

    # ── FALLBACK: Write to shared signals JSON file ─────────────────────────
    try:
        path = os.path.expanduser('~/tastywork-trading/tqqq_signals.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        signals = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    signals = json.load(f)
            except Exception:
                pass
        signals.append(payload)
        with open(path, 'w') as f:
            json.dump(signals, f, indent=2)
    except Exception as e:
        log.warning(f"  ⚠️ JSON file write failed (non-fatal): {e}")

    # ── SSE push to frontend ────────────────────────────────────────────────
    try:
        resp = requests.post(
            'https://www.trademind.bot/api/signals/notify',
            json={'strategy': 'TQQQ_TURBOCORE_PRO', 'user_id': user_id},
            timeout=8
        )
        if resp.status_code == 200:
            log.info(f"  ✅ SSE notified for user {user_id[:8]}")
        else:
            log.warning(f"  ⚠️ SSE push returned {resp.status_code}")
    except Exception as e:
        log.warning(f"  ⚠️ SSE push failed (non-fatal): {e}")




# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT

# ─────────────────────────────────────────────────────────────────────────────

def run_daily_order_generation(trade_date: Optional[date] = None) -> dict:
    """
    Full pipeline: generate signal → for each user → build order → persist.

    Returns summary dict {users_processed, errors, trade_date}.
    """
    if trade_date is None:
        trade_date = date.today()

    log.info(f"=== Daily Order Generation starting for {trade_date} ===")

    # ─ 1. Global signal ───────────────────────────────────────────────────────
    signal = generate_daily_signal(trade_date)

    # ─ 2. Load subscribed Pro users via TradeMind Next.js API ─────────────────
    # TT refresh tokens are stored in Upstash Redis (Next.js side), not in the
    # Python PostgreSQL DB. Calling the internal /api/admin/pro-users endpoint
    # which reads user_settings + Redis and returns users with TT credentials.
    import requests as _req

    _api_base = os.environ.get("TRADEMIND_API_URL", "https://www.trademind.bot")
    _secret   = os.environ.get("EC2_API_SECRET", "")

    users = []
    try:
        resp_users = _req.get(
            f"{_api_base}/api/admin/pro-users",
            headers={"x-ec2-secret": _secret},
            timeout=15
        )
        if resp_users.status_code == 200:
            data = resp_users.json()
            users = data.get("users", [])
            log.info(f"Found {len(users)} TurboCore Pro users via /api/admin/pro-users")
        else:
            log.error(f"pro-users API returned {resp_users.status_code}: {resp_users.text[:200]}")
    except Exception as _e:
        log.error(f"Failed to fetch pro users from Next.js API: {_e}")

    # SimpleNamespace lets us access user fields with dot notation (user.id, etc.)
    import types
    users = [types.SimpleNamespace(**u) for u in users]



    processed, errors = 0, 0

    for user in users:
        try:
            # ─ 3. Fetch live account state ────────────────────────────────────
            account_state = fetch_user_account_state(user)
            # ─ 4. Generate order ──────────────────────────────────────────────
            order = reconcile_and_generate_order(signal, account_state)
            # ─ 5. Persist ─────────────────────────────────────────────────────
            order_row = _upsert_order(db, user.id, trade_date, signal, account_state, order)
            processed += 1

            # ─ 6. Publish as TurboCore Pro signal (unless HOLD/NO_ACTION) ─────
            if order.get('signal_type') not in ('NO_ACTION', 'HOLD', 'ERROR') \
               and order.get('order_legs'):
                tc_signal = format_as_turbocore_signal(
                    signal, order,
                    order_db_id=order_row.id if order_row else ''
                )
                _publish_user_signal(tc_signal, user.id)

        except Exception as e:
            errors += 1
            log.error(f"Failed to generate order for user {user.id}: {e}", exc_info=True)
            # Write error record so user dashboard shows something
            try:
                from models.user_daily_order import UserDailyOrder
                import uuid
                err_row = UserDailyOrder(
                    id=str(uuid.uuid4()), user_id=user.id, trade_date=trade_date,
                    strategy_mode=signal.get('mode', '?'), signal_type='ERROR',
                    status='ERROR', generation_error=str(e)[:500]
                )
            except Exception:
                pass

    log.info(f"=== Done: {processed} processed, {errors} errors ===")
    return {"trade_date": trade_date.isoformat(), "users_processed": processed, "errors": errors}



if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Trade date (YYYY-MM-DD), default=today")
    args = parser.parse_args()
    td = date.fromisoformat(args.date) if args.date else date.today()
    result = run_daily_order_generation(td)
    print(result)
