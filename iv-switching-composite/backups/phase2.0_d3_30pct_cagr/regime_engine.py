def classify_mode(row, peak_vix=None, d2_active=False, d2_entry_date=None, current_date=None):
    """
    Returns one of: 'A', 'B', 'C', 'D2', 'D3'
    D1 is not a mode — it is a concurrent allocation returned as a flag via should_open_d1
    """
    vix          = row['vix']
    vix_vix3m    = row['vix_vix3m_ratio']
    above_sma200 = row['above_sma200']
    above_sma100 = row['above_sma100']
    below_sma200_3d = row.get('below_sma200_3d', False)
    ivp          = row['ivp_252']

    # ── Master Defense Gate (Noise Filter) ──
    vix_panic = (vix_vix3m > 1.05 and vix > 18.0)
    defense_gate = vix_panic or below_sma200_3d

    # ── D3: Crash recovery check (takes priority if D2 was recently active) ──
    if d2_active and peak_vix is not None:
        vix_off_peak    = vix < peak_vix * 0.80        # VIX down 20%+ from peak
        contango_back   = not defense_gate             # Term structure normalizing
        qqq_recovering  = row['qqq_ret_10d'] > 0       # QQQ green over 10 days
        if vix_off_peak and contango_back and qqq_recovering:
            return 'D3'

    # ── D2: Active bear (all 3 conditions required simultaneously) ──
    # NOTE: Phase 1 uses vvix > 30 as HMM proxy. Phase 2 uses HMM score.
    d2_ts_signal    = vix_panic                       # Hard structural backwardation
    d2_sma_signal   = not above_sma200                # QQQ below SMA200
    d2_vvix_signal  = row.get('vvix', 25.0) > 30.0    # VVIX elevated
    if d2_ts_signal and d2_sma_signal and d2_vvix_signal:
        return 'D2'

    # ── Mode C: Cash/defense (structural backwardation or QQQ deeply below SMA200) ──
    if defense_gate:
        return 'C'

    # ── Mode A: CSP — sell premium ──
    if above_sma200 and not defense_gate and ivp >= 30:
        if vix > 35:
            return 'C'            # VIX too extreme
        return 'A'

    # ── Mode B: LEAPS — buy directional exposure ──
    if above_sma100 and not defense_gate and ivp < 30:
        return 'B'

    # ── Default: Neutral/Cash ──
    return 'C'


def should_open_d1(vix, vvix_10d_chg, regime_label, regime_duration_days):
    """
    Returns (bool, allocation_pct) for Mode D1 VIX call purchase.
    D1 runs concurrently with A and B.
    """
    if vix <= 15:
        base_pct = 0.0
    elif vix <= 30:
        base_pct = 0.015     # 1.5% NAV
    elif vix <= 50:
        base_pct = 0.005     # 0.5% NAV (vol already expensive)
    else:
        base_pct = 0.0       # Too late — transition to D2

    if base_pct > 0:
        # ML enhancement 1: Complacency bump after 90+ days of BULL_STRONG (Mode A approximation here)
        if regime_label == 'A' and regime_duration_days > 90:
            base_pct = min(base_pct * 1.25, 0.025)

        # ML enhancement 2: VVIX early warning
        if vvix_10d_chg > 0.25 and vix < 25:
            base_pct = min(base_pct * 1.50, 0.025)

    return base_pct > 0, base_pct
