#!/usr/bin/env python3
"""Familias de momentum en ORO con ejecucion FIEL 1m: cruce de EMAs (15m y 1h) y MACD (15m y 1h),
entrada limite al cierre (o mercado), salida trailing k x ATR. 2024 (no visto) | 600d | 6 tramos."""
import sys, bisect
from datetime import datetime, timedelta
sys.argv=['x']
import backtest_real as br, fvg_sim1m as s1
d15,d1=s1.load(1000); cut=datetime(2025,2,9)
src=open('fvg_ultima_ronda.py').read(); exec(src[src.index("def agg("):src.index("def sim(")])
d60=agg(d15,60); T1=d1["T"]; Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
def ema(s,k):
    out=[s[0]]; a=2/(k+1)
    for x in s[1:]: out.append(x*a+out[-1]*(1-a))
    return out
def rma(s,k):
    out=[None]*len(s); p=sum(s[:k])/k; out[k-1]=p
    for i in range(k,len(s)): p=(p*(k-1)+s[i])/k; out[i]=p
    return out
def prep_sig(dS):
    O,H,L,C=s1.prep(dS); n=len(C)
    tr=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=rma(tr,14)
    return O,H,L,C,ATR
def sig_emax(C,f,s):
    ef,es=ema(C,f),ema(C,s); return [None]+[("BUY" if ef[t]>es[t] and ef[t-1]<=es[t-1] else "SELL" if ef[t]<es[t] and ef[t-1]>=es[t-1] else None) for t in range(1,len(C))]
def sig_macd(C,f,s,k):
    ef,es=ema(C,f),ema(C,s); m=[a-b for a,b in zip(ef,es)]; sg=ema(m,k); return [None]+[("BUY" if m[t]>sg[t] and m[t-1]<=sg[t-1] else "SELL" if m[t]<sg[t] and m[t-1]>=sg[t-1] else None) for t in range(1,len(C))]
def sim(dS,bar_min,sig,ATR,C,trail,market=False,ema_f=None,sides=("BUY","SELL")):
    TS=dS["T"]; n=len(C); M=timedelta(minutes=bar_min); m1=timedelta(minutes=1); WIN=300
    E=ema(C,ema_f) if ema_f else None
    j=bisect.bisect_left(T1,TS[WIN]+M); n1=len(T1); tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=TS[t]+M
        if pos is None and order is None and sig[t] and ATR[t] and sig[t] in sides:
            if E and ((sig[t]=="BUY" and C[t]<E[t]) or (sig[t]=="SELL" and C[t]>E[t])): pass
            else: order={"side":sig[t],"level":C[t],"dist":trail*ATR[t],"start":D+m1,"exp":D+M+m1,"first":True}
        Dn=(TS[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"]:
                fill=None; long=order["side"]=="BUY"
                if order["first"]:
                    order["first"]=False
                    if market or (long and Oa[j]<=order["level"]) or ((not long) and Ob[j]>=order["level"]): fill=Oa[j] if long else Ob[j]
                if fill is None and tm>=order["exp"]: order=None
                elif fill is None:
                    if long and La[j]<=order["level"]: fill=order["level"]
                    elif (not long) and Hb[j]>=order["level"]: fill=order["level"]
                if fill is not None:
                    d=order["dist"]; pos={"long":long,"entry":fill,"dist":d,"ext":fill,"stop":fill-d if long else fill+d,"t_in":tm}; order=None; j+=1; continue
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
def row(name,tr):
    if len(tr)<30: print(f"{name:<40} pocos trades"); return
    a=s1.stats([x for x in tr if x["t_in"]<cut]); b=s1.stats([x for x in tr if x["t_in"]>=cut]); c=s1.stats(tr)
    t0=tr[0]["t_in"]; t1=tr[-1]["t_in"]; span=(t1-t0)/6; s6=[0.0]*6
    for x in tr: s6[min(5,int((x["t_in"]-t0)/span))]+=x["net"]
    ok=" <<<" if a["tot"]>0 and b["tot"]>0 and a["pf"]>=1.15 and b["pf"]>=1.15 else ""
    print(f"{name:<40} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['dd']:>+5.0f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['dd']:>+5.0f} | {c['pf']:>5.2f} | "+' '.join(f"{v:>+5.0f}" for v in s6)+f" | {sum(1 for v in s6 if v>0)}/6{ok}")
print(f"{'familia':<40} | {'2024: tr neto PF DD':^25} | {'600d: tr neto PF DD':^25} | {'PF':^5} | {'6 tramos':^35} | pos")
for lab,dS,bm in (("15m",d15,15),("1h",d60,60)):
    O,H,L,C,ATR=prep_sig(dS)
    print(f"-- EMAX en {lab} --")
    for f,s in ((9,21),(12,26),(20,50)):
        sg=sig_emax(C,f,s)
        for k in (2.0,3.0,5.0): row(f"  EMAX {f}/{s} trail {k}x",sim(dS,bm,sg,ATR,C,k))
    print(f"-- MACD en {lab} --")
    for f,s,kk in ((12,26,9),(8,17,9)):
        sg=sig_macd(C,f,s,kk)
        for k in (2.0,3.0,5.0): row(f"  MACD {f}/{s}/{kk} trail {k}x",sim(dS,bm,sg,ATR,C,k))
# variantes sobre las mejores: filtro EMA200 y mercado
O,H,L,C,ATR=prep_sig(d15); sg=sig_emax(C,12,26)
print("-- variantes EMAX 12/26 15m --")
for k in (3.0,5.0):
    row(f"  EMAX 12/26 trail {k}x + filtro EMA200",sim(d15,15,sg,ATR,C,k,ema_f=200))
    row(f"  EMAX 12/26 trail {k}x a MERCADO",sim(d15,15,sg,ATR,C,k,market=True))
    row(f"  EMAX 12/26 trail {k}x solo largos",sim(d15,15,sg,ATR,C,k,sides=("BUY",)))
