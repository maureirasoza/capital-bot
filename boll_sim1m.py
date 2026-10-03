#!/usr/bin/env python3
"""Bollinger oro con ejecucion FIEL (1m bid/ask): senal = bot_gold.signal_last sobre 300 velas 15m (medio);
entrada LIMITE al cierre valida hasta el proximo cierre 15m (o a mercado si el precio ya es mejor);
trailing nativo = extremo del bid/ask minuto a minuto - TRAIL_ATR x ATR(entrada). Compara con el modelo 15m."""
import bisect
from datetime import datetime, timedelta, timezone
import backtest_real as br, fvg_sim1m as s1
bg=br._import_bollinger(); WIN=300
d15,d1=s1.load(1000); O,H,L,C=s1.prep(d15); T=d15["T"]; T1=d1["T"]
Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
def sim1m(trail, a=None, b=None, market=False):
    n=len(C); t0=max(WIN,bisect.bisect_left(T,a) if a else WIN); t1=bisect.bisect_left(T,b) if b else n
    M=timedelta(minutes=15); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[t0]+M); n1=len(T1)
    tr=[]; pos=None; order=None
    for t in range(t0,t1):
        D=T[t]+M
        if pos is None and order is None:
            lo=t-WIN+1; s=bg.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if s["side"] and s["atr"]: order={"side":s["side"],"level":s["close"],"dist":trail*s["atr"],"start":D+m1,"exp":D+M+m1,"first":True}
        Dn=(T[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"]:
                fill=None
                if order["first"]:
                    order["first"]=False
                    if market or (order["side"]=="BUY" and Oa[j]<=order["level"]) or (order["side"]=="SELL" and Ob[j]>=order["level"]): fill=Oa[j] if order["side"]=="BUY" else Ob[j]
                if fill is None and tm>=order["exp"]: order=None
                elif fill is None:
                    if order["side"]=="BUY" and La[j]<=order["level"]: fill=order["level"]
                    elif order["side"]=="SELL" and Hb[j]>=order["level"]: fill=order["level"]
                if fill is not None:
                    d=order["dist"]; long=order["side"]=="BUY"
                    pos={"long":long,"entry":fill,"dist":d,"ext":fill,"stop":fill-d if long else fill+d,"t_in":tm}; order=None; j+=1; continue
            if pos:
                if pos["long"]:
                    if Lb[j]<=pos["stop"]: ex=min(pos["stop"],Ob[j]) if Ob[j]<pos["stop"] else pos["stop"]; tr.append({"net":ex-pos["entry"],"t_in":pos["t_in"],"t_out":tm}); pos=None
                    else: pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                else:
                    if Ha[j]>=pos["stop"]: ex=max(pos["stop"],Oa[j]) if Oa[j]>pos["stop"] else pos["stop"]; tr.append({"net":pos["entry"]-ex,"t_in":pos["t_in"],"t_out":tm}); pos=None
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
            j+=1
    return tr
cut=datetime(2025,2,9); i600=bisect.bisect_left(T,cut); Tz=[t.replace(tzinfo=timezone.utc) for t in T]
print(f"{'modelo':<38} | {'ANTIGUO 2024: tr neto PF acc DD':^32} | {'RECIENTE 600d: tr neto PF acc DD':^32}")
def pr(nm,a,b):
    a=s1.stats(a); b=s1.stats(b); print(f"{nm:<38} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% {a['dd']:>+5.0f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+5.0f}")
br.SPREAD=0.3
for m in (5.0,4.0,6.0):
    full15=br.simulate_bollinger(O,H,L,C,Tz,bg,m); 
    a15=[x for x in full15 if x["t_in"].replace(tzinfo=None)<cut]; b15=[x for x in full15 if x["t_in"].replace(tzinfo=None)>=cut]
    pr(f"15m medio+0.6 fijo, trail {m}x",a15,b15)
    f1=sim1m(m); pr(f"1m bid/ask FIEL (limite al cierre), {m}x",[x for x in f1 if x["t_in"]<cut],[x for x in f1 if x["t_in"]>=cut])
f1=sim1m(5.0,market=True); pr("1m FIEL, entrada a MERCADO, 5x",[x for x in f1 if x["t_in"]<cut],[x for x in f1 if x["t_in"]>=cut])
