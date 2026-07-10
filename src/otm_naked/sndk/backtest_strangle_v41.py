import yfinance as yf, pandas as pd, numpy as np, math, yaml, os
from scipy.stats import norm
from datetime import datetime, timedelta

def fetch_data(symbol='WDC') -> dict:
    ticker = yf.Ticker(symbol)
    bars_5min  = ticker.history(period='60d', interval='5m', auto_adjust=True)
    bars_daily = ticker.history(period='1y', interval='1d',  auto_adjust=True)
    for df in [bars_5min, bars_daily]:
        df.index = df.index.tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
    
    return _calc_adx(bars_5min, bars_daily)

def load_local_data(csv_path: str) -> dict:
    df = pd.read_csv(csv_path, index_col='date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    
    # Resample to daily
    bars_daily = df.resample('D').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()
    
    return _calc_adx(df, bars_daily)

def _calc_adx(bars_5min, bars_daily):
    # Pre-calculate ADX-14 on daily bars
    df = bars_daily
    up = df['high'] - df['high'].shift(1)
    down = df['low'].shift(1) - df['low']
    pos_dm = np.where((up > down) & (up > 0), up, 0.0)
    neg_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift(1)).abs(), (df['low'] - df['close'].shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    pos_di = 100 * (pd.Series(pos_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr)
    neg_di = 100 * (pd.Series(neg_dm, index=df.index).ewm(span=14, adjust=False).mean() / atr)
    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di + 1e-8)
    bars_daily['adx'] = dx.ewm(span=14, adjust=False).mean()
    
    return {'5min': bars_5min, 'daily': bars_daily}

class BacktestEngineV41:
    def __init__(self, cfg):
        self.cfg = cfg
        self.nav = cfg['account']['nav']
        self.equity_curve = [self.nav]
        self.strangles = []  # active strangles
        self.trade_log = []
        self.last_entry_date = None
        self.max_bpr_pct = cfg['account']['max_bpr_pct']
        self.comm_per_contract = cfg['commission']['per_contract']

    def run(self, data: dict) -> dict:
        bars_5m  = data['5min'].copy()
        bars_day = data['daily'].copy()
        bars_5m['_date'] = bars_5m.index.date
        
        current_nav = self.nav
        
        for day in sorted(bars_5m['_date'].unique()):
            day_bars = bars_5m[bars_5m['_date'] == day]
            daily_ctx = self._daily_ctx(day, bars_day)
            if not daily_ctx:
                continue
                
            for i in range(len(day_bars)):
                bar = day_bars.iloc[i]
                spot = bar['close']
                
                # 1. Management Loop (every 5-min bar)
                self._manage_strangles(bar, spot, daily_ctx)
                
                # Update NAV based on realized PnL
                realized = sum([t['realized_pnl'] for t in self.trade_log if t.get('_new', False)])
                for t in self.trade_log: t['_new'] = False
                current_nav += realized
                
                # 2. Entry Loop (Only after 10:00 AM, before 3:30 PM)
                bar_time = pd.Timestamp(bar.name).time()
                from datetime import time as dtime
                if bar_time >= dtime(15, 30) or bar_time < dtime(10, 0):
                    continue
                
                # Check if we can open
                if daily_ctx['ivr'] >= self.cfg['entry_gates']['ivr_min']:
                    days_since = (day - self.last_entry_date).days if self.last_entry_date else 999
                    if days_since >= 3 and len(self.strangles) < self.cfg['account']['max_strangles']:
                        if self._check_bpr_headroom(self._estimate_margin(spot), current_nav):
                            self._open_strangle(day, bar, spot, daily_ctx, current_nav)

            mtm_nav = current_nav
            for s in self.strangles:
                t_rem = max((s['expiry'] - day).days / 365.0, 0.001)
                
                # Mark put
                if s['put']:
                    p_price = self._price_leg(spot, s['put']['strike'], t_rem, 'P', daily_ctx)
                    mtm_nav += s['put']['credit'] - (p_price * 100 * s['put']['qty']) - (s['put']['qty'] * self.comm_per_contract)
                    
                # Mark call
                if s['call']:
                    c_price = self._price_leg(spot, s['call']['strike'], t_rem, 'C', daily_ctx)
                    if s['call'].get('is_spread'):
                        c_price -= self._price_leg(spot, s['call']['long_strike'], t_rem, 'C', daily_ctx)
                        c_price = max(c_price, 0.05)
                    comm = (2 if s['call'].get('is_spread') else 1) * s['call']['qty'] * self.comm_per_contract
                    mtm_nav += s['call']['credit'] - (c_price * 100 * s['call']['qty']) - comm
                    
            self.equity_curve.append(mtm_nav)
            
        return self._stats(current_nav)

    def _manage_strangles(self, bar, spot, ctx):
        still_open = []
        for s in self.strangles:
            # Price both legs
            t_rem = max((s['expiry'] - bar.name.date()).days / 365.0, 0.001)
            
            p_price = self._price_leg(spot, s['put']['strike'], t_rem, 'P', ctx) if s['put'] else 0
            
            c_price = 0
            if s['call']:
                c_price = self._price_leg(spot, s['call']['strike'], t_rem, 'C', ctx)
                if s['call']['is_spread']:
                    c_price -= self._price_leg(spot, s['call']['long_strike'], t_rem, 'C', ctx)
                    c_price = max(c_price, 0.05)
            
            put_val = p_price * 100 * s['put']['qty'] if s['put'] else 0
            call_val = c_price * 100 * s['call']['qty'] if s['call'] else 0
            
            # Primary Exits: Per-leg GTC (PT 50%, SL 3x)
            pt_pct = self.cfg['management']['profit_target_per_leg_pct']
            sl_mult = self.cfg['management']['stop_loss_per_leg_mult']
            
            p_closed = False
            if s['put']:
                fp = s['put']['fill_price']
                if p_price <= fp * pt_pct:
                    fill_p = min(fp * pt_pct, p_price)
                    self._close_leg(s, 'P', spot, fill_p, 'PT', ctx)
                    p_closed = True
                elif p_price >= fp * sl_mult:
                    fill_p = max(fp * sl_mult, p_price)
                    self._close_leg(s, 'P', spot, fill_p, 'SL', ctx)
                    p_closed = True

            c_closed = False
            if s['call'] and not p_closed:
                fp = s['call']['fill_price']
                if c_price <= fp * pt_pct:
                    fill_p = min(fp * pt_pct, c_price)
                    self._close_leg(s, 'C', spot, fill_p, 'PT', ctx)
                    c_closed = True
                elif c_price >= fp * sl_mult:
                    fill_p = max(fp * sl_mult, c_price)
                    self._close_leg(s, 'C', spot, fill_p, 'SL', ctx)
                    c_closed = True

            # Combined PT Accelerator
            combined_debit = put_val + call_val
            combined_credit = (s['put']['credit'] if s['put'] else 0) + (s['call']['credit'] if s['call'] else 0)
            if combined_credit > 0 and (combined_credit - combined_debit) / combined_credit >= self.cfg['management']['combined_pt_pct']:
                if s['put']: self._close_leg(s, 'P', spot, p_price, 'COMBINED_PT', ctx)
                if s['call']: self._close_leg(s, 'C', spot, c_price, 'COMBINED_PT', ctx)
                continue

            # Swing Re-leg
            sw = self.cfg['management']['swing_re_leg']
            if s['put']:
                put_chg = (spot - s['put']['fill_spot']) / s['put']['fill_spot']
                if put_chg >= sw['put_buyback_trigger'] and ctx['regime'] in ('REVERT_BULLISH', 'SIDEWAYS'):
                    self._close_leg(s, 'P', spot, p_price, 'SWING_BUYBACK', ctx)
                    self._re_leg(s, 'P', spot, bar, ctx)
            
            if s['call'] and not s['call']['is_spread']:
                call_chg = (spot - s['call']['fill_spot']) / s['call']['fill_spot']
                if call_chg <= sw['call_buyback_trigger'] and ctx['regime'] in ('REVERT_BEARISH', 'SIDEWAYS'):
                    self._close_leg(s, 'C', spot, c_price, 'SWING_BUYBACK', ctx)
                    self._re_leg(s, 'C', spot, bar, ctx)

            # Tested Leg Roll (Delta > 0.45)
            p_delta = abs(self._get_delta(spot, s['put']['strike'], t_rem, 'P', ctx)) if s['put'] else 0
            c_delta = abs(self._get_delta(spot, s['call']['strike'], t_rem, 'C', ctx)) if s['call'] else 0
            if s['call'] and s['call']['is_spread']:
                c_delta -= abs(self._get_delta(spot, s['call']['long_strike'], t_rem, 'C', ctx))

            tested = self.cfg['management']['delta_tested_threshold']
            if p_delta > tested or c_delta > tested:
                if ctx['regime'] == 'TREND_UP' and c_delta > tested:
                    if s['put']: self._close_leg(s, 'P', spot, p_price, 'TREND_CLOSE', ctx)
                    if s['call']: self._close_leg(s, 'C', spot, c_price, 'TREND_CLOSE', ctx)
                elif ctx['regime'] == 'TREND_DOWN' and p_delta > tested:
                    if s['put']: self._close_leg(s, 'P', spot, p_price, 'TREND_CLOSE', ctx)
                    if s['call']: self._close_leg(s, 'C', spot, c_price, 'TREND_CLOSE', ctx)
                else:
                    if p_delta > tested and self.cfg['management']['roll']['roll_put_when_tested']:
                        self._roll_leg(s, 'P', spot, p_price, t_rem, ctx)
                    elif c_delta > tested and self.cfg['management']['roll']['roll_winning_leg_on_opposite_test']:
                        if s['put']: self._roll_leg(s, 'P', spot, p_price, t_rem, ctx)

            # DTE Close
            if t_rem * 365 <= self.cfg['management']['dte_close_threshold']:
                if s['put']: self._close_leg(s, 'P', spot, p_price, 'DTE_CLOSE', ctx)
                if s['call']: self._close_leg(s, 'C', spot, c_price, 'DTE_CLOSE', ctx)

            if s['put'] or s['call']:
                still_open.append(s)
                
        self.strangles = still_open

    def _open_strangle(self, date, bar, spot, ctx, nav):
        ivr = ctx['ivr']
        dte = self._get_dte(ivr)
        t_rem = dte / 365.0
        
        # Open Put
        p_strike = self._delta_to_K(spot, ctx, t_rem, 0.15, 'P')
        p_price = self._price_leg(spot, p_strike, t_rem, 'P', ctx)
        if p_price < 0.50: return
        
        p_qty = max(1, int(nav * 0.15 / max(0.20*spot, 0.10*spot) / 100))
        p_fp = p_price * (1 - self.cfg['slippage']['entry_pct'])
        p_credit = p_fp * 100 * p_qty - p_qty*self.comm_per_contract*2
        
        s = {
            'id': f"STR_{date}_{len(self.trade_log)}",
            'expiry': date + timedelta(days=dte),
            'put': {
                'strike': p_strike, 'qty': p_qty, 'fill_price': p_fp, 
                'credit': p_credit, 'fill_spot': spot, 'roll_count': 0
            },
            'call': None
        }
        
        # Open Call (Regime Gated)
        regime = ctx['regime']
        gate = self.cfg['call_leg_regime_gate']
        
        if regime not in gate['blocked_regimes']:
            c_strike = self._delta_to_K(spot, ctx, t_rem, 0.12, 'C')
            is_spread = (regime in gate['credit_spread_regimes'])
            
            c_price = self._price_leg(spot, c_strike, t_rem, 'C', ctx)
            long_strike = 0
            if is_spread:
                atr14 = spot * 0.03
                long_strike = round((c_strike + gate['credit_spread_width_atr_mult'] * atr14) / 5) * 5
                c_price -= self._price_leg(spot, long_strike, t_rem, 'C', ctx)
            
            if c_price >= 0.30:
                c_fp = c_price * (1 - self.cfg['slippage']['entry_pct'])
                comm = (2 if is_spread else 1) * p_qty * self.comm_per_contract * 2
                c_credit = c_fp * 100 * p_qty - comm
                
                s['call'] = {
                    'strike': c_strike, 'qty': p_qty, 'fill_price': c_fp,
                    'credit': c_credit, 'fill_spot': spot, 'roll_count': 0,
                    'is_spread': is_spread, 'long_strike': long_strike
                }
        
        self.strangles.append(s)
        self.last_entry_date = date

    def _close_leg(self, s, right, spot, price, reason, ctx):
        leg = s['put'] if right == 'P' else s['call']
        slip = self.cfg['slippage']['exit_sl_pct'] if reason == 'SL' else self.cfg['slippage']['exit_pt_pct']
        cost = price * (1 + slip)
        comm = (2 if leg.get('is_spread') else 1) * leg['qty'] * self.comm_per_contract
        realized = leg['credit'] - (cost * 100 * leg['qty']) - comm
        
        self.trade_log.append({
            'strangle_id': s['id'], 'right': right, 'reason': reason,
            'realized_pnl': realized, 'regime': ctx['regime'], '_new': True
        })
        
        if right == 'P': s['put'] = None
        else: s['call'] = None

    def _re_leg(self, s, right, spot, bar, ctx):
        # Open new leg
        t_rem = max((s['expiry'] - bar.name.date()).days / 365.0, 0.001)
        tgt = 0.15 if right == 'P' else 0.12
        new_k = self._delta_to_K(spot, ctx, t_rem, tgt, right)
        price = self._price_leg(spot, new_k, t_rem, right, ctx)
        
        if price >= 0.50:
            qty = s['call']['qty'] if right == 'C' and s['call'] else (s['put']['qty'] if s['put'] else 1)
            fp = price * (1 - self.cfg['slippage']['entry_pct'])
            credit = fp * 100 * qty - qty*self.comm_per_contract*2
            new_leg = {
                'strike': new_k, 'qty': qty, 'fill_price': fp, 
                'credit': credit, 'fill_spot': spot, 'roll_count': 0,
                'is_spread': False
            }
            if right == 'P': s['put'] = new_leg
            else: s['call'] = new_leg

    def _roll_leg(self, s, right, spot, price, t_rem, ctx):
        leg = s['put'] if right == 'P' else s['call']
        if not leg or leg.get('is_spread') or leg['roll_count'] >= 3: return
        
        new_exp = s['expiry'] + timedelta(weeks=3)
        new_t = t_rem + 3/52.0
        tgt = 0.15 if right == 'P' else 0.12
        new_k = self._delta_to_K(spot, ctx, new_t, tgt, right)
        
        new_price = self._price_leg(spot, new_k, new_t, right, ctx)
        old_cost = price * (1 + 0.12) # roll round trip slippage
        net_credit = new_price - old_cost
        
        if net_credit >= 0.50:
            realized = leg['credit'] - (old_cost * 100 * leg['qty']) - leg['qty']*self.comm_per_contract*2
            self.trade_log.append({
                'strangle_id': s['id'], 'right': right, 'reason': 'ROLL',
                'realized_pnl': realized, 'regime': ctx['regime'], '_new': True
            })
            
            fp = new_price * (1 - 0.12)
            credit = fp * 100 * leg['qty']
            new_leg = {
                'strike': new_k, 'qty': leg['qty'], 'fill_price': fp, 
                'credit': credit, 'fill_spot': spot, 'roll_count': leg['roll_count']+1,
                'is_spread': False
            }
            if right == 'P': 
                s['put'] = new_leg
                s['expiry'] = new_exp
            else: 
                s['call'] = new_leg

    def _check_bpr_headroom(self, est_margin, nav):
        active = sum([self._estimate_margin(150) for _ in self.strangles]) # approx
        return (active + est_margin) <= nav * self.max_bpr_pct

    def _estimate_margin(self, spot):
        return self.nav * self.cfg['account']['capital_per_strangle_pct']

    def _daily_ctx(self, date, bars_day):
        try:
            prev_date = pd.Timestamp(date) - pd.Timedelta(days=1)
            w = bars_day.loc[:prev_date].tail(60)
            if len(w) < 20: return None
            close = w['close']
            rets  = close.pct_change().dropna()
            hv20  = rets.tail(20).std() * np.sqrt(252)
            atm_iv = min(hv20 * 1.55, 2.5)
            hv_s  = rets.rolling(20).std() * np.sqrt(252)
            ivr   = int(100*(hv20-hv_s.min())/(hv_s.max()-hv_s.min()+1e-8))
            ivr   = max(0, min(100, ivr))
            
            # Perplexity fix: Conditional slope lookback
            hv5 = rets.tail(5).std() * np.sqrt(252)
            lookback = 10 if hv5 > (hv20 * 1.5) else 20
            
            roc5  = (close.iloc[-1]-close.iloc[-5])/close.iloc[-5] if len(close)>=5 else 0
            slope = np.polyfit(range(min(lookback,len(close))), close.tail(lookback).values, 1)[0]/close.mean()
            adx   = w['adx'].iloc[-1]
            
            # ADX-14 filter (Perplexity recommendation)
            if adx < 25:
                regime = 'SIDEWAYS' # Chop, override momentum signals
            elif roc5 > 0.15 or slope > 0.015: regime = 'EXTREME_UPTREND'
            elif roc5 > 0.06 or slope > 0.005: regime = 'TREND_UP'
            elif roc5 < -0.15 or slope < -0.015: regime = 'EXTREME_DOWNTREND'
            elif roc5 < -0.06 or slope < -0.005: regime = 'TREND_DOWN'
            elif roc5 > 0.03: regime = 'REVERT_BULLISH'
            elif roc5 < -0.03: regime = 'REVERT_BEARISH'
            else: regime = 'SIDEWAYS'
            
            return {'atm_iv': atm_iv, 'ivr': ivr, 'regime': regime}
        except: return None

    def _price_leg(self, spot, K, T, right, ctx):
        sigma = ctx['atm_iv'] + (0.10 if right == 'P' else -0.03)
        return self._bs(spot, K, T, 0.05, sigma, right)
        
    def _get_delta(self, spot, K, T, right, ctx):
        sigma = ctx['atm_iv'] + (0.10 if right == 'P' else -0.03)
        if T <= 0: return 1.0 if (right=='C' and spot>K) or (right=='P' and spot<K) else 0.0
        d1 = (math.log(spot/K) + (0.05 + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
        return norm.cdf(d1) if right == 'C' else norm.cdf(d1) - 1

    def _get_dte(self, ivr):
        for k, v in self.cfg['dte_by_ivr'].items():
            if v['dte'] and v['ivr_min'] <= ivr <= v['ivr_max']: return v['dte']
        return 45

    def _delta_to_K(self, S, ctx, T, target_delta, right):
        sigma = ctx['atm_iv'] + (0.10 if right == 'P' else -0.03)
        lo, hi = S*0.01, S*8.0
        for _ in range(50):
            mid = (lo+hi)/2
            d1 = (math.log(S/mid) + (0.05 + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
            d = norm.cdf(d1) if right=='C' else norm.cdf(d1)-1
            if right=='C': lo, hi = (mid, hi) if d > target_delta else (lo, mid)
            else: lo, hi = (lo, mid) if d < -target_delta else (mid, hi)
        return round((lo+hi)/2/5)*5

    @staticmethod
    def _bs(S, K, T, r, sigma, right):
        if T <= 0: return max(K-S,0) if right=='P' else max(S-K,0)
        d1 = (math.log(S/K)+(r+.5*sigma**2)*T)/(sigma*math.sqrt(T))
        d2 = d1-sigma*math.sqrt(T)
        if right=='P': return K*math.exp(-r*T)*norm.cdf(-d2)-S*norm.cdf(-d1)
        return S*norm.cdf(d1)-K*math.exp(-r*T)*norm.cdf(d2)

    def _stats(self, final_nav):
        if not self.trade_log: return {'error': 'No trades'}
        df = pd.DataFrame(self.trade_log)
        pnl = df['realized_pnl']
        w = pnl[pnl>0]
        l = pnl[pnl<=0]
        n = len(self.equity_curve)-1
        cagr = (final_nav/self.nav)**(252/max(n,1)) - 1
        dr   = pd.Series(self.equity_curve).pct_change().dropna()
        sharpe = dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
        eq = pd.Series(self.equity_curve)
        max_dd = ((eq - eq.cummax())/eq.cummax()).min() if not eq.empty else 0
        return {
            'total_leg_exits': len(df), 'win_rate': len(w)/len(df) if len(df) else 0,
            'avg_win': w.mean() if len(w) else 0, 'avg_loss': l.mean() if len(l) else 0,
            'total_pnl': pnl.sum(), 'cagr': cagr, 'sharpe': sharpe, 'max_drawdown': max_dd,
            'final_nav': final_nav, 'by_reason': df['reason'].value_counts().to_dict()
        }

if __name__ == '__main__':
    import sys
    symbol_or_csv = sys.argv[1] if len(sys.argv) > 1 else 'WDC'
    with open(os.path.join(os.path.dirname(__file__), 'config_v41.yaml')) as f:
        cfg = yaml.safe_load(f)
        
    if symbol_or_csv.endswith('.csv'):
        print(f"Loading local data from {symbol_or_csv}...")
        data = load_local_data(symbol_or_csv)
        symbol = os.path.basename(symbol_or_csv).split('_')[0]
    else:
        symbol = symbol_or_csv
        print(f"Fetching {symbol} 6-month 5m data...")
        data = fetch_data(symbol)
        
    print(f"Loaded {len(data['5min'])} 5m bars.")
    
    engine = BacktestEngineV41(cfg)
    r = engine.run(data)
    
    print("\n" + "="*60)
    print(f"{symbol} DDS Bot v4.1 — 6-Month Backtest Results")
    print("="*60)
    if 'error' in r:
        print(f"ERROR: {r['error']}")
    else:
        print(f"Total Leg Exits:   {r['total_leg_exits']}")
        print(f"Leg Win Rate:      {r['win_rate']:.1%}")
        print(f"Avg Win:           ${r['avg_win']:+,.0f}")
        print(f"Avg Loss:          ${r['avg_loss']:+,.0f}")
        print(f"Total P&L:         ${r['total_pnl']:+,.0f}")
        print(f"CAGR (annualized): {r['cagr']:.1%}")
        print(f"Sharpe Ratio:      {r['sharpe']:.2f}")
        print(f"Max Drawdown:      {r['max_drawdown']:.1%}")
        print(f"Exit Breakdown:    {r['by_reason']}")
        print(f"Final NAV:         ${r['final_nav']:,.0f}  (Start: ${cfg['account']['nav']})")
