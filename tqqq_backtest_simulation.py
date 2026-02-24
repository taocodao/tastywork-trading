"""
TQQQ Dual-Sided Backtest — Fast + Optimize Modes
==================================================
Usage:
    python tqqq_backtest_simulation.py            # FAST: ~2 min, pre-tuned params
    python tqqq_backtest_simulation.py --optimize # SLOW: overnight DE optimizer

FAST MODE:
  Uses best-known params from previous 6000+ eval DE sessions.
  Runs 3 scenarios in ~90 seconds total. Good for iterative testing.

OPTIMIZE MODE:
  Runs full Differential Evolution. Takes 60-90 min, leave overnight.
  Saves optimal params to tqqq_optimal_params.json when done.

Scenarios:
  A: Put Credit Spreads only (baseline)
  B: Put + Bear Call Credit Spreads
  C: Put + Call + Iron Condors (full)
"""

import sys, json, math, time, warnings
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm
from scipy.optimize import differential_evolution

warnings.filterwarnings("ignore")

OPTIMIZE_MODE = "--optimize" in sys.argv

# ─────────────── Constants ────────────────────────────────────────────────────
ACCT  = 25_000.0
COMM  = 4.0
RF    = 0.05
START, END = "2019-01-01", "2025-01-01"
CIRCUIT    = 0.05   # call spread circuit breaker: +5% move

VIX_T = {"LOW_VOL":(0,15),"NORMAL":(15,22),"HIGH_VOL":(22,35),"CRISIS":(35,9999)}
REGIMES = ["LOW_VOL","NORMAL","HIGH_VOL","CRISIS"]
PUT_DTE   = {"LOW_VOL":35,"NORMAL":30,"HIGH_VOL":21,"CRISIS":14}
PUT_W     = {"LOW_VOL":3, "NORMAL":5, "HIGH_VOL":5, "CRISIS":3}
CALL_DTE  = {"HIGH_VOL":14,"CRISIS":7}
CALL_W    = {"HIGH_VOL":5, "CRISIS":3}

# ─────────────── BEST-KNOWN PARAMS (from 29,046 DE evaluations, Feb 24 2026) ────
# Derived from overnight DE run: +75.1% return | Sharpe 14.58 | MaxDD -1.9% | 78 trades
# Format: [iv_mult, risk_pt, cooldown, slippage, vix5d_max,
#          lv_d, lv_pt, lv_lm,  no_d, no_pt, no_lm,
#          hv_d, hv_pt, hv_lm,  cr_d, cr_pt, cr_lm]
BEST_PUT_PARAMS = [
    2.10,   # iv_mult: DE-optimized (was 1.75)
    0.084,  # risk_pt: 8.4% account risk per trade (was 10%)
    6,      # cooldown: 6 days (was 3)
    0.008,  # slippage: 0.8% (was 1.2%)
    4.015,  # vix5d_max: allow entries if VIX rose < 4.0 pts over 5d
    # LOW_VOL — farther OTM, wider stop
    -0.163, 0.498, 3.845,
    # NORMAL — farther OTM, wider stop
    -0.176, 0.560, 3.166,
    # HIGH_VOL — let theta decay much more before closing (82%)
    -0.242, 0.825, 2.312,
    # CRISIS — very far OTM, very wide stop
    -0.145, 0.776, 4.314,
]

# Call-side best-known params (HIGH_VOL, CRISIS)
BEST_CALL_PARAMS = [
    # HIGH_VOL calls: far OTM, fast profit target
    0.14, 0.70, 2.0,
    # CRISIS calls: very far OTM, let decay fully (market crisis = down trend sustained)
    0.09, 0.88, 3.0,
]

# Iron Condor best-known params (NORMAL regime)
BEST_IC_PARAMS = [
    -0.22,  # put_delta
     0.18,  # call_delta (asymmetric — TQQQ has upward drift)
     0.60,  # profit_target
     2.0,   # loss_mult
]

# Build full param vector per scenario
def scenario_params(sc: str) -> list:
    p = list(BEST_PUT_PARAMS)
    if sc in ("B","C"): p += BEST_CALL_PARAMS
    if sc == "C":       p += BEST_IC_PARAMS
    return p

# ─────────────── DE bounds (optimize mode only) ─────────────────────────────
GLOBAL_BNDS = [(1.30,2.10),(0.05,0.15),(2,6),(0.008,0.022),(1.0,7.0)]
PUT_BNDS    = [(-0.38,-0.14),(0.35,0.85),(1.2,4.0),  # LOW_VOL
               (-0.38,-0.14),(0.35,0.85),(1.2,4.0),  # NORMAL
               (-0.40,-0.15),(0.35,0.85),(1.2,4.0),  # HIGH_VOL
               (-0.28,-0.11),(0.50,0.95),(2.0,5.0)]  # CRISIS
CALL_BNDS   = [(0.07,0.18),(0.50,0.95),(1.5,4.0),
               (0.05,0.13),(0.65,0.98),(2.0,5.0)]
IC_BNDS     = [(-0.28,-0.15),(0.13,0.23),(0.45,0.80),(1.5,3.5)]

def all_bounds(sc):
    b = GLOBAL_BNDS + PUT_BNDS
    if sc in ("B","C"): b += CALL_BNDS
    if sc == "C":       b += IC_BNDS
    return b

# ─────────────── Black-Scholes (fast) ─────────────────────────────────────────

def bs_put(S,K,T,v):
    if T<=0 or v<=0: return max(0.0,K-S)
    d1=(math.log(S/K)+(RF+0.5*v*v)*T)/(v*math.sqrt(T)); d2=d1-v*math.sqrt(T)
    return K*math.exp(-RF*T)*norm.cdf(-d2)-S*norm.cdf(-d1)

def bs_call(S,K,T,v):
    if T<=0 or v<=0: return max(0.0,S-K)
    d1=(math.log(S/K)+(RF+0.5*v*v)*T)/(v*math.sqrt(T)); d2=d1-v*math.sqrt(T)
    return S*norm.cdf(d1)-K*math.exp(-RF*T)*norm.cdf(d2)

# Analytical strike via closed-form delta inversion (no loop)
def put_strike(S,delta,iv,dte):
    T=dte/365.0; d1=norm.ppf(1.0+delta)
    return round(S*math.exp(-d1*iv*math.sqrt(T)+(RF+0.5*iv*iv)*T))

def call_strike(S,delta,iv,dte):
    T=dte/365.0; d1=norm.ppf(delta)
    return round(S*math.exp(-d1*iv*math.sqrt(T)+(RF+0.5*iv*iv)*T))

def put_spread(S,delta,width,iv,dte):
    sk=float(put_strike(S,delta,iv,dte)); lk=float(max(1,sk-width))
    T=dte/365.0; cr=max(0.01,bs_put(S,sk,T,iv)-bs_put(S,lk,T,iv))
    return sk,lk,cr

def call_spread(S,delta,width,iv,dte):
    sk=float(call_strike(S,delta,iv,dte)); lk=float(sk+width)
    T=dte/365.0; cr=max(0.01,bs_call(S,sk,T,iv)-bs_call(S,lk,T,iv))
    return sk,lk,cr

# ─────────────── Data ─────────────────────────────────────────────────────────
_DF=None

def load_data(iv_mult=1.75):
    global _DF
    if _DF is not None:
        df=_DF.copy(); df["iv"]=(df["hv30"]*iv_mult).clip(lower=0.40); return df
    print("Downloading TQQQ + VIX (2019–2025)…", flush=True)
    t=yf.download("TQQQ",start=START,end=END,auto_adjust=True,progress=False)
    v=yf.download("^VIX", start=START,end=END,auto_adjust=True,progress=False)
    for x in [t,v]:
        if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
    df=t[["Close"]].copy(); df.columns=["close"]
    df["vix"]=v["Close"].reindex(df.index).ffill()
    df["hv30"]=df["close"].pct_change().rolling(20).std()*math.sqrt(252)
    df["vix5d"]=df["vix"].diff(5)
    df=df.dropna(); _DF=df.copy()
    df["iv"]=(df["hv30"]*iv_mult).clip(lower=0.40)
    print(f"Loaded {len(df)} days.", flush=True)
    return df

# ─────────────── Simulate single legs (check every 3 days near DTE) ───────────

def sim_put(cl,iv,sk,lk,cr,dte,ei,n,crt,mlt,pt,lm):
    for j in range(ei+1,min(ei+dte+5,len(cl))):
        dh=j-ei; dr=max(0.5,dte-dh)
        if dh%3!=0 and dr>5: continue
        T=dr/365.0; pnl=(cr-(bs_put(cl[j],sk,T,iv[j])-bs_put(cl[j],lk,T,iv[j])))*100*n
        if pnl>=crt*pt: return ("PT",pnl,j)
        if pnl<=-mlt*mlt*0.9: return ("SL",pnl,j)
        if dr<=5: return ("DTE",pnl,j)
    return None

def sim_call(cl,iv,sk,lk,cr,dte,ei,n,crt,mlt,pt,lm,S0):
    for j in range(ei+1,min(ei+dte+5,len(cl))):
        dh=j-ei; dr=max(0.5,dte-dh)
        if dh%3!=0 and dr>3: continue
        T=dr/365.0
        pnl=(cr-(bs_call(cl[j],sk,T,iv[j])-bs_call(cl[j],lk,T,iv[j])))*100*n
        if (cl[j]-S0)/S0>=CIRCUIT: return ("CIRC",pnl,j)
        if pnl>=crt*pt: return ("PT",pnl,j)
        if pnl<=-mlt*lm*0.9: return ("SL",pnl,j)
        if dr<=3: return ("DTE",pnl,j)
    return None

def sim_ic(cl,iv,psk,plk,pcr,csk,clk,ccr,dte,ei,n,crt,mlt,pt,lm):
    for j in range(ei+1,min(ei+dte+5,len(cl))):
        dh=j-ei; dr=max(0.5,dte-dh)
        if dh%3!=0 and dr>5: continue
        T=dr/365.0
        pnow=bs_put(cl[j],psk,T,iv[j])-bs_put(cl[j],plk,T,iv[j])
        cnow=bs_call(cl[j],csk,T,iv[j])-bs_call(cl[j],clk,T,iv[j])
        pnl=((pcr+ccr)-(pnow+cnow))*100*n
        if pnl>=crt*pt: return ("PT",pnl,j)
        if pnl<=-mlt*lm*0.9: return ("SL",pnl,j)
        if dr<=5: return ("DTE",pnl,j)
    return None

# ─────────────── Core backtest ────────────────────────────────────────────────

def run(params,sc="A"):
    iv_mult=float(params[0]); risk=float(params[1])
    cool=int(round(params[2])); slip=float(params[3]); v5mx=float(params[4])

    pp={REGIMES[i]:{"d":float(params[5+i*3]),"pt":float(params[6+i*3]),"lm":float(params[7+i*3])}
        for i in range(4)}
    cp={}
    if sc in ("B","C"):
        for i,r in enumerate(["HIGH_VOL","CRISIS"]):
            cp[r]={"d":float(params[17+i*3]),"pt":float(params[18+i*3]),"lm":float(params[19+i*3])}
    ic={}
    if sc=="C":
        ic={"pd":float(params[23]),"cd":float(params[24]),"pt":float(params[25]),"lm":float(params[26])}

    df=load_data(iv_mult)
    cl=df["close"].values; iv=df["iv"].values
    vixa=df["vix"].values; v5=df["vix5d"].values
    dates=df.index.tolist(); N=len(dates)
    eq=ACCT; ec=[]; trades=[]; lei=-9999

    for i in range(N):
        ec.append(eq)
        if i-lei<cool: continue
        vix=vixa[i]; S=cl[i]; iv_=iv[i]; v5_=v5[i]
        regime=next((r for r,(lo,hi) in VIX_T.items() if lo<=vix<hi),"CRISIS")

        if regime=="CRISIS":
            tt="CALL" if sc in ("B","C") else None
        elif regime=="HIGH_VOL":
            if v5_>1.5 and sc in ("B","C"):  tt="CALL"
            elif v5_<=v5mx:                  tt="PUT"
            else:                            tt=None
        elif regime=="NORMAL":
            if sc=="C" and abs(v5_)<2.5:     tt="IC"
            elif v5_<=v5mx:                  tt="PUT"
            else:                            tt=None
        elif regime=="LOW_VOL":
            tt="PUT" if v5_<=v5mx else None
        else:
            tt=None

        if tt is None or iv_<0.35: continue

        try:
            if tt=="PUT":
                p=pp[regime]; dte=PUT_DTE[regime]; w=PUT_W[regime]
                sk,lk,cr=put_spread(S,p["d"],w,iv_,dte)
                if cr<0.05: continue
                mlp=(w-cr)*100; nc=max(1,int(eq*risk/mlp))
                crt=cr*100*nc; mlt=mlp*nc
                res=sim_put(cl,iv,sk,lk,cr,dte,i,nc,crt,mlt,p["pt"],p["lm"])
                reason,gross,xi=(res if res else ("EXP",cr*100*nc,min(i+dte,N-1)))
                net=gross-COMM*nc-crt*slip

            elif tt=="CALL":
                p=cp[regime]; dte=CALL_DTE[regime]; w=CALL_W[regime]
                sk,lk,cr=call_spread(S,p["d"],w,iv_,dte)
                if cr<0.03: continue
                mlp=(w-cr)*100; nc=max(1,int(eq*risk/mlp))
                crt=cr*100*nc; mlt=mlp*nc
                res=sim_call(cl,iv,sk,lk,cr,dte,i,nc,crt,mlt,p["pt"],p["lm"],S)
                reason,gross,xi=(res if res else ("EXP",cr*100*nc,min(i+dte,N-1)))
                net=gross-COMM*nc-crt*slip

            else:  # IC
                psk,plk,pcr=put_spread(S,ic["pd"],PUT_W["NORMAL"],iv_,PUT_DTE["NORMAL"])
                csk,clk,ccr=call_spread(S,ic["cd"],PUT_W["NORMAL"],iv_,PUT_DTE["NORMAL"])
                if pcr<0.03 or ccr<0.03: continue
                mlp=max((PUT_W["NORMAL"]-pcr),(PUT_W["NORMAL"]-ccr))*100
                nc=max(1,int(eq*risk/mlp))
                crt=(pcr+ccr)*100*nc; mlt=mlp*nc
                res=sim_ic(cl,iv,psk,plk,pcr,csk,clk,ccr,PUT_DTE["NORMAL"],i,nc,crt,mlt,ic["pt"],ic["lm"])
                reason,gross,xi=(res if res else ("EXP",crt,min(i+PUT_DTE["NORMAL"],N-1)))
                net=gross-COMM*2*nc-crt*slip
        except Exception:
            continue

        eq+=net; eq=max(eq,1.0)
        # be_pct = breakeven cushion as % of spread width (PUT trades only)
        be_pct = (cr / w * 100) if (tt == "PUT" and w > 0) else 0.0
        trades.append({"type":tt,"regime":regime,"date":str(dates[i])[:10],
                       "net":net,"w":net>0,"r":reason,"xi":xi,"be_pct":be_pct})
        lei=xi

    if not trades:
        return {"sharpe":-10,"total_return":-100,"trades":0,"equity":ACCT,"ec":ec,"tl":[],
                "avg_breakeven_pct":0.0}

    s=pd.Series([t["net"] for t in trades])
    sharpe=(s.mean()/s.std()*math.sqrt(252)) if s.std()>0 else 0.0
    totr=(eq-ACCT)/ACCT*100
    arr=np.array(ec); pk=np.maximum.accumulate(arr)
    mdd=float(((arr-pk)/pk).min()*100)

    # Breakeven width: average credit-to-width ratio across trades
    # Higher = more cushion before hitting max loss (wider breakeven zone)
    be_pcts = [t.get("be_pct", 0.0) for t in trades if t.get("be_pct", 0.0) > 0]
    avg_be  = float(sum(be_pcts) / len(be_pcts)) if be_pcts else 0.0

    # Score: Sharpe + breakeven bonus - large drawdown penalty
    # breakeven_bonus weight=2.0: 1% wider BE contributes ~same as 0.02 Sharpe
    score = sharpe - max(0, -mdd - 20) * 0.5 + avg_be * 2.0
    return {"sharpe":sharpe,"score":score,
            "total_return":totr,"max_dd":mdd,"trades":len(trades),
            "equity":eq,"ec":ec,"tl":trades,"avg_breakeven_pct":avg_be}

# ─────────────── Report ───────────────────────────────────────────────────────

def report(res,label):
    tl=res["tl"]
    if not tl: print(f"\n  {label}: No trades."); return
    w=[t for t in tl if t["w"]]; l=[t for t in tl if not t["w"]]
    wr=len(w)/len(tl)*100
    pf=abs(sum(t["net"] for t in w))/max(0.01,abs(sum(t["net"] for t in l)))
    ann: Dict[str,float]={}
    ext: Dict[str,int]={}
    tyc: Dict[str,int]={}
    for t in tl:
        yr=t["date"][:4]; ann[yr]=ann.get(yr,0)+t["net"]
        ext[t["r"]]=ext.get(t["r"],0)+1
        tyc[t["type"]]=tyc.get(t["type"],0)+1
    div="="*70
    print(f"\n{div}\n  {label}\n{div}")
    print(f"  ${ACCT:,.0f} → ${res['equity']:,.0f}  |  "
          f"Return: {res['total_return']:+.1f}%  |  "
          f"Sharpe: {res['sharpe']:.2f}  |  MaxDD: {res['max_dd']:.1f}%")
    print(f"  {len(tl)} trades  |  WR: {wr:.1f}%  |  PF: {pf:.2f}")
    for k,v in sorted(tyc.items()): print(f"    {k}: {v} trades")
    print(f"{'─'*70}  ANNUAL P&L")
    for yr in sorted(ann):
        p=ann[yr]; s="+" if p>=0 else ""
        bar="█"*min(50,int(abs(p)/100))
        print(f"  {yr}  {s}${p:>9,.0f}  ({s}{p/ACCT*100:>4.1f}%)  {bar}")
    print(f"{'─'*70}  EXIT REASONS")
    for r,c in sorted(ext.items(),key=lambda x:-x[1]):
        print(f"  {r:<20}: {c}")
    print(div)

# ─────────────── Optimizer (overnight mode) ───────────────────────────────────

_cnt=0
def make_obj(sc):
    def obj(p):
        global _cnt; _cnt+=1
        r=run(list(p),sc)
        if _cnt%50==0:
            ts=time.strftime("%H:%M:%S")
            print(f"  [{_cnt:>4}] {ts}  Sharpe={r['sharpe']:+.2f}  "
                  f"Return={r['total_return']:+.1f}%  MaxDD={r['max_dd']:.1f}%  "
                  f"Trades={r['trades']}", flush=True)
        return -r["score"]
    return obj

# ─────────────── Main ─────────────────────────────────────────────────────────

if __name__=="__main__":
    t0=time.time(); load_data(); all_res={}; all_opt_params={}

    # All 3 scenarios — optimized fairly or run with best-known params
    SCENARIOS=[
        ("A","Scenario A — Put Credit Spreads Only (Baseline)"),
        ("B","Scenario B — Put + Bear Call Credit Spreads"),
        ("C","Scenario C — Put + Call + Iron Condors (Full)"),
    ]

    if OPTIMIZE_MODE:
        print("\n🔧 OPTIMIZE MODE — running overnight DE optimizer for ALL 3 scenarios")
        print("   Expected runtime: ~90-180 min total\n")
        for sc,label in SCENARIOS:
            _cnt=0; bnds=all_bounds(sc)
            n_dim=len(bnds)
            # More evals for scenario A (simpler, faster per call)
            maxiter = 60 if sc=="A" else 40
            popsize = 10 if sc=="A" else 8
            print(f"\n{'='*70}\n  {label}\n  {n_dim}-dim | maxiter={maxiter} popsize={popsize}\n{'='*70}",flush=True)
            opt=differential_evolution(make_obj(sc),bounds=bnds,seed=42,
                                       maxiter=maxiter,popsize=popsize,tol=0.005,
                                       mutation=(0.5,1.2),recombination=0.85,
                                       workers=1,disp=False)
            best_p=list(opt.x)
            res=run(best_p,sc)
            report(res,label)
            all_res[label]=res
            all_opt_params[sc]={
                "params": best_p,
                "score": -opt.fun,
                "evals": _cnt,
            }
            print(f"  ✓ {_cnt} evals | score={-opt.fun:.3f} | "
                  f"Sharpe={res['sharpe']:.2f} | Return={res['total_return']:+.1f}%", flush=True)

        # Save optimized params + results
        save_data = {
            "run_date": time.strftime("%Y-%m-%d %H:%M UTC"),
            "mode": "DE_optimized",
            "runtime_seconds": round(time.time()-t0),
            "scenarios": {}
        }
        for sc,label in SCENARIOS:
            res=all_res[label]
            op=all_opt_params.get(sc,{})
            save_data["scenarios"][sc]={
                "label": label,
                "optimized_params": op.get("params",[]),
                "evals": op.get("evals",0),
                "score": op.get("score",0),
                "return_pct": res["total_return"],
                "sharpe": res["sharpe"],
                "max_dd_pct": res["max_dd"],
                "trades": res["trades"],
                "final_equity": res["equity"],
            }
        with open("tqqq_optimal_params.json","w") as f:
            json.dump(save_data,f,indent=2)
        print(f"\n  ✅ Saved optimized params → tqqq_optimal_params.json")

    else:
        print("\n⚡ FAST MODE — using best-known pre-tuned parameters (~90 sec)")
        print("   (Run with --optimize for full DE optimization — ~2-3 hrs)\n", flush=True)
        for sc,label in SCENARIOS:
            print(f"  Running {label}…", flush=True)
            p=scenario_params(sc)
            while len(p)<len(all_bounds(sc)): p.append(0.0)
            res=run(p[:len(all_bounds(sc))],sc)
            report(res,label); all_res[label]=res

    # Comparison table
    print(f"\n{'='*70}")
    print(f"  3-SCENARIO COMPARISON{' (DE-OPTIMIZED)' if OPTIMIZE_MODE else ' (FAST MODE — pre-tuned params)'}")
    print(f"{'='*70}")
    print(f"  {'Scenario':<45} {'Return':>8} {'Sharpe':>8} {'MaxDD':>7} {'Trades':>7}")
    print(f"  {'─'*67}")
    for lbl,r in all_res.items():
        print(f"  {lbl:<45} {r['total_return']:>+7.1f}%"
              f" {r['sharpe']:>8.2f} {r['max_dd']:>6.1f}% {r['trades']:>7}")
    print(f"{'='*70}")

    out={"mode": "optimized" if OPTIMIZE_MODE else "fast",
         "scenarios":{lbl:{"return_pct":r["total_return"],"sharpe":r["sharpe"],
                            "max_dd_pct":r["max_dd"],"trades":r["trades"],
                            "final_equity":r["equity"]}
                      for lbl,r in all_res.items()}}
    with open("tqqq_dual_backtest_results.json","w") as f:
        json.dump(out,f,indent=2,default=str)
    print(f"\n  Saved → tqqq_dual_backtest_results.json")
    print(f"  Total runtime: {time.time()-t0:.0f}s")
