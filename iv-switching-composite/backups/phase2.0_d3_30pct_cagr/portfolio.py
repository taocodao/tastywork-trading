from pricing import bs_call_price, bs_put_price

class ZebraPosition:
    """
    ZEBRA = 2x 70-delta long calls + 1x 50-delta short call, same expiry.
    Net delta ~90.  No theta decay (extrinsic of shorts pays for longs).
    Max loss = net debit paid.
    """
    def __init__(self, open_date, expiry, long_strike, short_strike,
                 net_debit, contracts, iv, rf, position_id):
        self.open_date    = open_date
        self.expiry       = expiry
        self.long_strike  = long_strike   # 70-delta strike (2 longs per unit)
        self.short_strike = short_strike  # 50-delta strike (1 short per unit)
        self.entry_price  = net_debit     # net debit per 1-unit (2L-1S)
        self.contracts    = contracts     # number of ZEBRA units
        self.iv           = iv
        self.rf           = rf
        self.position_id  = position_id

    def dte(self, current_date):
        return (self.expiry - current_date).days

    def current_value(self, spot, current_date, current_iv, current_rf):
        """Net value of one ZEBRA unit: 2*long_call - 1*short_call"""
        T = max(self.dte(current_date) / 365.0, 1/365.0)
        lc = bs_call_price(spot, self.long_strike,  T, current_rf, current_iv)
        sc = bs_call_price(spot, self.short_strike, T, current_rf, current_iv)
        return 2 * lc - sc


class Portfolio:
    def __init__(self, initial_capital):
        self.initial_capital = initial_capital
        self.cash = initial_capital

        self.open_csps    = []   # CSP dicts: {strike, expiry, entry_price, contracts, entry_date}
        self.open_zebras  = []   # list of ZebraPosition
        self.open_ccs     = []   # Bear Call Spread dicts (Mode C income)
        self.d1_positions = []   # VIX call dicts

        self.d2_active   = False
        self.d2_position = None  # SQQQ dict

        self.nav_history = []
        self.trade_log   = []

        self.peak_vix = None

    def update_peak_vix(self, current_vix):
        if self.peak_vix is None or current_vix > self.peak_vix:
            self.peak_vix = current_vix

    def reset_peak_vix(self):
        self.peak_vix = None

    def calculate_nav(self, date, qqq_px, tqqq_px, sqqq_px, vix_px,
                      tqqq_iv, qqq_leaps_iv, qqq_short_iv, d1_iv, rf):
        nav = self.cash

        # ZEBRA mark-to-market (capped at zero where loss > debit)
        for z in self.open_zebras:
            val = z.current_value(qqq_px, date, qqq_short_iv, rf)
            nav += max(val, 0.0) * z.contracts * 100

        # CSP unrealized liability
        for csp in self.open_csps:
            T = max((csp['expiry'] - date).days / 365.0, 1/365.0)
            put_val = bs_put_price(tqqq_px, csp['strike'], T, rf, tqqq_iv)
            nav -= put_val * csp['contracts'] * 100

        # Bear Call Spread (Mode C) unrealized liability
        for ccs in self.open_ccs:
            T = max((ccs['expiry'] - date).days / 365.0, 1/365.0)
            sc_val = bs_call_price(qqq_px, ccs['short_strike'], T, rf, qqq_short_iv)
            lc_val = bs_call_price(qqq_px, ccs['long_strike'],  T, rf, qqq_short_iv)
            nav -= max(sc_val - lc_val, 0) * ccs['contracts'] * 100

        # D1 VIX calls
        for vc in self.d1_positions:
            T = max((vc['expiry'] - date).days / 365.0, 1/365.0)
            nav += bs_call_price(vix_px, vc['strike'], T, rf, d1_iv) * vc['contracts'] * 100

        # D2 SQQQ
        if self.d2_position:
            nav += self.d2_position['shares'] * sqqq_px

        return nav

    def log_trade(self, trade_info):
        self.trade_log.append(trade_info)
