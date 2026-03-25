from regime_engine import should_open_d1

def size_csp_trade(nav, vix, strike, premium_per_share=0):
    """
    Returns number of CSP contracts for Mode A.
    Kelly-scaled by VIX regime.
    """
    if vix < 18.0:
        kelly_frac = 0.50
    elif vix <= 25.0:
        kelly_frac = 0.30
    elif vix <= 35.0:
        kelly_frac = 0.15
    else:
        return 0

    if strike <= 0:
        return 0

    max_collateral = nav * kelly_frac
    contracts      = int(max_collateral / (strike * 100))
    return max(contracts, 0)


def size_zebra_trade(nav, net_debit_per_unit, n_open=0):
    """
    Returns number of ZEBRA units for Mode B.
    Each unit = 2 long calls + 1 short call.
    Max 2 slots, 15% NAV per slot.
    """
    max_slots = 2
    if n_open >= max_slots:
        return 0

    pct_per_slot = 0.15          # 15% NAV per ZEBRA slot
    max_outlay   = nav * pct_per_slot
    if net_debit_per_unit <= 0:
        return 0
    # Cost per unit = net_debit * 100 shares + 3 legs of slippage/commission
    return max(int(max_outlay / (net_debit_per_unit * 100)), 0)


def size_ccs_trade(nav, margin_per_contract):
    """
    Allocates up to 15% NAV for Mode C Bear Call Spreads margin.
    """
    if margin_per_contract <= 0:
        return 0
    return int((nav * 0.15) / margin_per_contract)


def size_d2_sqqq(nav, vix):
    """Returns dollar amount for Mode D2 SQQQ position."""
    if vix < 30:
        return nav * 0.07
    else:
        return nav * 0.05


def size_d1_vix_calls(nav, vix, vvix_10d_chg, regime_duration_days):
    """Returns dollar amount for Mode D1 VIX call purchase."""
    should_open, alloc_pct = should_open_d1(vix, vvix_10d_chg, 'A', regime_duration_days)
    if not should_open:
        return 0.0
    return nav * alloc_pct
