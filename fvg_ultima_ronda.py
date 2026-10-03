#!/usr/bin/env python3
"""FVG, ultima ronda con ejecucion FIEL 1m: (A) senal en velas de 1 HORA (agregadas desde 15m) y
(B) salida por TRAILING (k x hueco o k x ATR) en vez de TP fijo, en 15m y 1h. ANTIGUO 2024 | RECIENTE 600d."""
import bisect
from datetime import datetime, timedelta
import backtest_real as br, fvg_sim1m as s1
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,SL_MULT=fv.SL_MULT,FILL_WIN=fv.FILL_WIN,MIN_GAP=fv.MIN_GAP,EMA_TREND=fv.EMA_TREND,MAX_GAP=fv.MAX_GAP)
def setp(**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
d15,d1=s1.load(1000); cut=datetime(2025,2,9)
def agg(d,mins):
    """agrega velas de 15m a 'mins' minutos (alineadas a la hora UTC)"""
    keys=("Ob","Hb","Lb","Cb","Oa","Ha","La","Ca"); out={k:[] for k in keys}; out["T"]=[]; cur=None
    for i,t in enumerate(d["T"]):
        b=t.replace(minute=(t.minute//mins)*mins)
        if b!=cur:
            cur=b; out["T"].append(b)
            for k in keys: out[k].append(d[k][i])
        else:
            for s in ("b","a"):
                out["H"+s][-1]=max(out["H"+s][-1],d["H"+s][i]); out["L"+s][-1]=min(out["L"+s][-1],d["L"+s][i]); out["C"+s][-1]=d["C"+s][i]
    return out
d60=agg(d15,60)
def sim(dS, bar_min, trail=None, sigfn=None):
    """copia de fvg_sim1m.sim con bar_min y salida opcional por trailing (trail=(modo,k): 'gap' o 'atr')."""
    O,H,L,C=s1.prep(dS); TS=dS["T"]; T1=d1["T"]; n=len(C); WIN=s1.WIN
    Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
    sigfn=sigfn or fv.find_pending_fvg_ohlc; M=timedelta(minutes=bar_min); m1=timedelta(minutes=1)
    j=bisect.bisect_left(T1,TS[WIN]+M); n1=len(T1); tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=TS[t]+M
        if pos is None and order is None:
            lo=t-WIN+1; s=sigfn(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if s and s.get("side"):
                dist=None
                if trail:
                    if trail[0]=="gap": dist=trail[1]*s["gap_eff"]
                    else:
                        a=fv.atr_series(H[lo:t+1],L[lo:t+1],C[lo:t+1],fv.ATR_LEN)[-1]; dist=trail[1]*a
                order={"side":s["side"],"level":s["level"],"sl":s["sl"],"tp":s["tp"],"dist":dist,"start":D+m1,"exp":D+m1+timedelta(minutes=bar_min*s["remaining_bars"]),"first":True}
        Dn=(TS[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"]:
                if order["first"]:
                    order["first"]=False
                    if (order["side"]=="BUY" and order["level"]>=Oa[j]) or (order["side"]=="SELL" and order["level"]<=Ob[j]): order=None
                if order and tm>=order["exp"]: order=None
                if order:
                    long=order["side"]=="BUY"
                    if (long and La[j]<=order["level"]) or ((not long) and Hb[j]>=order["level"]):
                        e=min(order["level"],Oa[j]) if long else max(order["level"],Ob[j]); d=order["dist"]
                        pos={"long":long,"entry":e,"sl":(e-d if long else e+d) if d else order["sl"],"tp":None if d else order["tp"],"dist":d,"ext":e,"t_in":tm}; order=None
            if pos:
                ex=None; long=pos["long"]
                if long:
                    if Lb[j]<=pos["sl"]: ex=min(pos["sl"],Ob[j]) if (Ob[j]<pos["sl"] and tm>pos["t_in"]) else pos["sl"]
                    elif pos["tp"] and Hb[j]>=pos["tp"] and tm>pos["t_in"]: ex=pos["tp"]
                else:
                    if Ha[j]>=pos["sl"]: ex=max(pos["sl"],Oa[j]) if (Oa[j]>pos["sl"] and tm>pos["t_in"]) else pos["sl"]
                    elif pos["tp"] and La[j]<=pos["tp"] and tm>pos["t_in"]: ex=pos["tp"]
                if ex is not None:
                    tr.append({"net":(ex-pos["entry"]) if long else (pos["entry"]-ex),"t_in":pos["t_in"],"t_out":tm}); pos=None
                elif pos["dist"]:
                    if long: pos["ext"]=max(pos["ext"],Hb[j]); pos["sl"]=max(pos["sl"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["sl"]=min(pos["sl"],pos["ext"]+pos["dist"])
            j+=1
    return tr
def row(name,dS,bar_min,trail=None,**kw):
    setp(**kw); full=sim(dS,bar_min,trail)
    a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut])
    print(f"{name:<44} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+5.0f}")
print(f"{'variante':<44} | {'ANTIGUO 2024: tr neto PF acc':^28} | {'RECIENTE 600d: tr neto PF acc DD':^32}")
row("15m ACTUAL (referencia)",d15,15)
print("-- (A) senal en velas de 1 HORA --")
for sl,tp in ((2.0,0.75),(1.5,1.0),(1.5,1.5),(1.0,2.0),(2.0,1.5)): row(f"  1h  SL{sl}/TP{tp}",d60,60,SL_MULT=sl,TP_R=tp)
row("  1h  SL1.5/TP1.0 huecos >=0.8xATR",d60,60,SL_MULT=1.5,TP_R=1.0,MIN_GAP=0.8)
print("-- (B) salida por TRAILING en vez de TP (stop inicial = trailing) --")
for k in (1.5,2.0,3.0): row(f"  15m trailing {k} x hueco",d15,15,trail=("gap",k))
for k in (2.0,3.0,5.0): row(f"  15m trailing {k} x ATR",d15,15,trail=("atr",k))
for k in (2.0,3.0): row(f"  1h  trailing {k} x hueco",d60,60,trail=("gap",k))
for k in (3.0,5.0): row(f"  1h  trailing {k} x ATR",d60,60,trail=("atr",k))
setp()
