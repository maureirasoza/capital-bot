#!/usr/bin/env python3
"""Trend oro (config EN VIVO: Donchian 15/8, EMA200, trailing 5xATR, piramide +2xATR con stop propio 5xATR).
Variantes de SALIDA, en (a) la operacion del 7-oct y (b) 1000d de GOLD 1h real (2024 no visto | 600d).
Dolares con size 0.5 (base) y 0.51 (piramide)."""
import sys
refresh="--refresh" in sys.argv
sys.argv=['x','--source','capital','--days','1000']+(['--refresh'] if refresh else [])
import backtest_real as br, bot_gold_trend as bt
from datetime import datetime
O,H,L,C,T=br.fetch_capital("GOLD","HOUR",1000); n=len(C); W=bt.N_CANDLES; SP=0.3
sig=[None]*n
for t in range(W,n):
    lo=t-W+1; sig[t]=bt.signal_at(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1],W-1)
def exit_ch(t,side,X):
    if X==bt.EXIT: return sig[t]["exit_long"] if side=="L" else sig[t]["exit_short"]
    return (C[t]<min(L[t-X:t])) if side=="L" else (C[t]>max(H[t-X:t]))
def sim(trail=5.0,prog=None,tp=None,X=8,pyr_tp=None):
    """prog=(M,k): cuando la ganancia maxima de la base >= M x ATR, el trailing de ambas pasa a k x ATR.
    tp=T: cierre de todo al tocar base_entrada +/- T x ATR. pyr_tp=P: la piramide toma ganancia a +P x ATR de su entrada."""
    tr=[]; base=None; pyr=None
    def cu(u,px,t,nm,size): g=(px-u["e"]) if u["s"]=="L" else (u["e"]-px); return {"net":g-2*SP,"usd":(g-2*SP)*size,"t":T[t],"t_in":u["t_in"],"unit":nm}
    for t in range(W,n):
        s=sig[t]
        for nm in ("base","pyr"):
            u=base if nm=="base" else pyr
            if u is None: continue
            sg=1 if u["s"]=="L" else -1; px=None
            if (sg==1 and L[t]<=u["stop"]) or (sg==-1 and H[t]>=u["stop"]): px=u["stop"]
            elif u.get("tp") is not None and ((sg==1 and H[t]>=u["tp"]) or (sg==-1 and L[t]<=u["tp"])): px=u["tp"]
            if px is not None:
                tr.append(cu(u,px,t,nm,0.5 if nm=="base" else 0.51))
                if nm=="base": base=None
                else: pyr=None
        if base or pyr:
            u0=base or pyr
            if exit_ch(t,u0["s"],X):
                for nm,u in (("base",base),("pyr",pyr)):
                    if u: tr.append(cu(u,C[t],t,nm,0.5 if nm=="base" else 0.51))
                base=pyr=None; continue
        for u in (base,pyr):
            if u is None: continue
            sg=1 if u["s"]=="L" else -1
            u["x"]=max(u["x"],H[t]) if sg==1 else min(u["x"],L[t])
            if prog and base and sg*(base["x"]-base["e"])>=prog[0]*base["atr"]: u["d"]=min(u["d"],prog[1]*base["atr"])
            u["stop"]=max(u["stop"],u["x"]-u["d"]) if sg==1 else min(u["stop"],u["x"]+u["d"])
        if base and pyr is None and not base.get("pd"):
            sg=1 if base["s"]=="L" else -1; lvl=base["e"]+sg*bt.PYR_STEP*base["atr"]
            if (sg==1 and C[t]>=lvl) or (sg==-1 and C[t]<=lvl):
                e=C[t]; d=trail*base["atr"]
                pyr={"s":base["s"],"e":e,"d":d,"x":e,"stop":e-sg*d,"t_in":T[t],"tp":(e+sg*pyr_tp*base["atr"]) if pyr_tp else base.get("tp")}; base["pd"]=True
        if base is None and pyr is None and s and s["atr"]:
            side="L" if s["long_break"] else ("S" if s["short_break"] else None)
            if side:
                sg=1 if side=="L" else -1; e=C[t]; d=trail*s["atr"]
                base={"s":side,"e":e,"d":d,"atr":s["atr"],"x":e,"stop":e-sg*d,"t_in":T[t],"tp":(e+sg*tp*s["atr"]) if tp else None}
    return tr
def st(tr):
    tot=sum(x["net"] for x in tr); w=sum(x["net"] for x in tr if x["net"]>0); l=-sum(x["net"] for x in tr if x["net"]<=0)
    eq=pk=dd=0
    for x in sorted(tr,key=lambda z:z["t"]): eq+=x["usd"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    return sum(x["usd"] for x in tr),(w/l if l else 9),dd
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=600)
print(f"datos GOLD 1h: {n} velas hasta {T[-1]:%Y-%m-%d %H:%M} UTC")
V=[("ACTUAL (trail 5x, canal 8)",{}),("trailing 3x",dict(trail=3.0)),("trailing 4x",dict(trail=4.0)),("trailing 6x",dict(trail=6.0)),
   ("tras +4xATR apretar a 2x",dict(prog=(4,2.0))),("tras +6xATR apretar a 2x",dict(prog=(6,2.0))),("tras +6xATR apretar a 3x",dict(prog=(6,3.0))),("tras +8xATR apretar a 3x",dict(prog=(8,3.0))),
   ("objetivo fijo +6xATR",dict(tp=6)),("objetivo fijo +8xATR",dict(tp=8)),("objetivo fijo +12xATR",dict(tp=12)),
   ("canal de salida 4",dict(X=4)),("canal de salida 6",dict(X=6)),
   ("piramide toma ganancia +3xATR",dict(pyr_tp=3)),("piramide toma ganancia +5xATR",dict(pyr_tp=5))]
print(f"\n{'salida':<34} | {'op 7-oct (USD)':>14} | {'2024 no visto: USD PF':>22} | {'600d: USD PF DD':>24} | {'TOTAL 1000d: USD PF':>20}")
for nm,kw in V:
    tr=sim(**kw)
    op=[x for x in tr if x["t_in"].replace(tzinfo=None)>=datetime(2026,10,7,0,0) and x["t_in"].replace(tzinfo=None)<datetime(2026,10,8,0,0)]
    a=st([x for x in tr if x["t"]<T[cut]]); b=st([x for x in tr if x["t"]>=T[cut]]); c=st(tr)
    print(f"{nm:<34} | {sum(x['usd'] for x in op):>+14.2f} | {a[0]:>+12.0f} PF{a[1]:.2f} | {b[0]:>+11.0f} PF{b[1]:.2f} {b[2]:>+6.0f} | {c[0]:>+11.0f} PF{c[1]:.2f}")
