#!/usr/bin/env python3
"""RUPTURA FALLIDA en US30 con ejecucion FIEL 1m bid/ask. Senal en velas de 1h (agregadas de 15m
bid/ask, precio medio); entrada a MERCADO en el minuto :01 tras el cierre de confirmacion (ask/bid);
stop inicial = extremo de la ruptura +/- 0.5 x k x ATR (min k x ATR desde la entrada); trailing p x ATR
minuto a minuto. Dos mitades. Compara con el modelo 1h medio+spread."""
import os, sys, json, bisect
from datetime import datetime, timedelta
import backtest_real as br, fvg_sim1m as s1
def load(epic,res,days):
    d=json.load(open(os.path.join(br.DATA_DIR,f"capital_{epic}_{res}_{days}d_bidask.json"))); d["T"]=[datetime.fromisoformat(t) for t in d["T"]]; return d
d15=load("US30","MINUTE_15",600); d1=load("US30","MINUTE",600)
src=open('fvg_ultima_ronda.py').read(); exec(src[src.index("def agg("):src.index("def sim(")])
d60=agg(d15,60); O,H,L,C=s1.prep(d60); T=d60["T"]; n=len(C); T1=d1["T"]
Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
def rma(s,k):
    out=[None]*len(s); p=sum(s[:k])/k; out[k-1]=p
    for i in range(k,len(s)): p=(p*(k-1)+s[i])/k; out[i]=p
    return out
tr_=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=rma(tr_,14); mid=T[n//2]
def sim(N,M,k,p):
    M60=timedelta(minutes=60); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[N+2]+M60); n1=len(T1)
    tr=[]; pos=None; pend=None; order=None
    for t in range(N+2,n):
        D=T[t]+M60; hh=max(H[t-N:t]); ll=min(L[t-N:t]); a=ATR[t]
        if pos is None and order is None and a:
            if pend:
                if t>pend['t0']+M: pend=None
                elif pend['dir']=='up' and C[t]<pend['lvl']: order={"side":"SELL","ext":pend['ext'],"atr":a,"k":k,"start":D+m1}; pend=None
                elif pend['dir']=='down' and C[t]>pend['lvl']: order={"side":"BUY","ext":pend['ext'],"atr":a,"k":k,"start":D+m1}; pend=None
                else:
                    pend['ext']=max(pend['ext'],H[t]) if pend['dir']=='up' else min(pend['ext'],L[t])
            if order is None and pend is None:
                if C[t]>hh: pend={'dir':'up','lvl':hh,'t0':t,'ext':H[t]}
                elif C[t]<ll: pend={'dir':'down','lvl':ll,'t0':t,'ext':L[t]}
        Dn=(T[t+1]+M60) if t+1<n else D+M60
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"] and pos is None:
                long=order["side"]=="BUY"; e=Oa[j] if long else Ob[j]; risk=order["k"]*order["atr"]
                stop=(min(order["ext"]-0.5*risk,e-risk)) if long else (max(order["ext"]+0.5*risk,e+risk))
                pos={"long":long,"entry":e,"stop":stop,"dist":p*order["atr"],"ext":e,"t_in":tm}; order=None
            if pos:
                long=pos["long"]; ex=None
                if long and Lb[j]<=pos["stop"]: ex=min(pos["stop"],Ob[j]) if Ob[j]<pos["stop"] else pos["stop"]
                elif (not long) and Ha[j]>=pos["stop"]: ex=max(pos["stop"],Oa[j]) if Oa[j]>pos["stop"] else pos["stop"]
                if ex is not None: tr.append({"net":(ex-pos["entry"]) if long else (pos["entry"]-ex),"t_in":pos["t_in"],"t_out":tm}); pos=None
                else:
                    if long: pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
            j+=1
    return tr
print(f"US30 1h {n} velas {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | 1m {len(T1)} velas")
print(f"{'config':<22} | {'MITAD 1: tr neto PF DD':^26} | {'MITAD 2: tr neto PF DD':^26} | {'TOTAL PF acc frec':^20}")
weeks=(T[-1]-T[0]).days/7
for N in (24,48,96):
    for M in (2,4):
        for k in (1.0,2.0):
            for p in (2.0,3.0,5.0):
                tr=sim(N,M,k,p); a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); c=s1.stats(tr)
                if a["n"]<15 or b["n"]<15: continue
                ok=" <<<" if a["tot"]>0 and b["tot"]>0 and a["pf"]>1.15 and b["pf"]>1.15 else ""
                print(f"N{N} M{M} k{k} trail{p:<4} | {a['n']:>4} {a['tot']:>+7.0f} {a['pf']:>5.2f} {a['dd']:>+6.0f} | {b['n']:>4} {b['tot']:>+7.0f} {b['pf']:>5.2f} {b['dd']:>+6.0f} | {c['pf']:>5.2f} {c['acc']:>3.0f}% {len(tr)/weeks:>4.1f}/sem{ok}")
