#!/usr/bin/env python3
"""Mejoras del BOLLINGER oro con ejecucion FIEL 1m (senal real bot_gold.signal_last en 300 velas 15m).
Senales cacheadas por juego de parametros de entrada; palancas de salida/filtro/ejecucion encima.
ANTIGUO 2024 (no visto) | RECIENTE 600d | 6 tramos."""
import bisect, statistics
from datetime import datetime, timedelta
import backtest_real as br, fvg_sim1m as s1
bg=br._import_bollinger(); WIN=300
d15,d1=s1.load(1000); O,H,L,C=s1.prep(d15); T=d15["T"]; T1=d1["T"]; n=len(C)
Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
cut=datetime(2025,2,9)
BASE=dict(BB_LEN=bg.BB_LEN,BB_MULT=bg.BB_MULT,RSI_LOW=bg.RSI_LOW,RSI_HIGH=bg.RSI_HIGH,ADX_MIN=bg.ADX_MIN,EMA_TREND=bg.EMA_TREND)
def setp(**kw):
    for k,v in BASE.items(): setattr(bg,k,v)
    for k,v in kw.items(): setattr(bg,k,v)
CACHE={}
def signals(**kw):
    key=tuple(sorted(kw.items()))
    if key in CACHE: return CACHE[key]
    setp(**kw); sig=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=bg.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
        if s["side"] and s["atr"]: sig[t]=(s["side"],s["close"],s["atr"])
    CACHE[key]=sig; return sig
# ATR mediana movil para regimen de volatilidad
atrs=[None]*n; buf=[]; med=[None]*n
def sim(sig, trail=5.0, market=False, hours=None, sides=("BUY","SELL"), vol=None, pyr=None, tstop=None, offset=0.0):
    M=timedelta(minutes=15); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[WIN]+M); n1=len(T1)
    tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=T[t]+M
        if pos is None and order is None and sig[t]:
            side,close,atr=sig[t]; ok=side in sides
            if ok and hours and not hours(T[t].hour): ok=False
            if ok and vol and med[t] and ((vol=="alta" and atr<med[t]) or (vol=="baja" and atr>=med[t])): ok=False
            if ok:
                lvl=close-offset*atr if side=="BUY" else close+offset*atr
                order={"side":side,"level":lvl,"dist":trail*atr,"atr":atr,"start":D+m1,"exp":D+M+m1,"first":True}
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
                    pos={"long":long,"entries":[fill],"dist":d,"atr":order["atr"],"ext":fill,"stop":fill-d if long else fill+d,"t_in":tm,"last":fill}; order=None; j+=1; continue
            if pos:
                long=pos["long"]; sg=1 if long else -1; ex=None
                if long and Lb[j]<=pos["stop"]: ex=min(pos["stop"],Ob[j]) if Ob[j]<pos["stop"] else pos["stop"]
                elif (not long) and Ha[j]>=pos["stop"]: ex=max(pos["stop"],Oa[j]) if Oa[j]>pos["stop"] else pos["stop"]
                elif tstop and tm-pos["t_in"]>=timedelta(minutes=15*tstop) and sg*((Hb[j] if long else La[j])-pos["entries"][0])<=0: ex=Ob[j] if long else Oa[j]
                if ex is not None:
                    tr.append({"net":sum(sg*(ex-e) for e in pos["entries"]),"t_in":pos["t_in"],"t_out":tm,"u":len(pos["entries"])}); pos=None
                else:
                    if long: pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
                    if pyr and len(pos["entries"])<pyr[1]:
                        lvl=pos["last"]+sg*pyr[0]*pos["atr"]
                        if (long and Hb[j]>=lvl) or ((not long) and La[j]<=lvl):
                            px=max(lvl,Oa[j]) if long else min(lvl,Ob[j]); pos["entries"].append(px); pos["last"]=px
            j+=1
    return tr
def seg6(tr):
    t0=tr[0]["t_in"]; t1=tr[-1]["t_in"]; span=(t1-t0)/6; out=[0.0]*6
    for x in tr: out[min(5,int((x["t_in"]-t0)/span))]+=x["net"]
    return out
REF={}
def row(name,sig,ref=None,**kw):
    full=sim(sig,**kw); a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut]); c=s1.stats(full); s6=seg6(full)
    mark=""
    if ref and ref in REF:
        ra,rb=REF[ref]; mark=" <<< mejor en ambos" if (a["tot"]>ra["tot"] and b["tot"]>rb["tot"] and a["pf"]>=ra["pf"] and b["pf"]>=rb["pf"]) else ""
    print(f"{name:<40} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['dd']:>+5.0f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['dd']:>+5.0f} | {c['tot']:>+6.0f} {c['pf']:>5.2f} | "+' '.join(f"{v:>+5.0f}" for v in s6)+f" | {sum(1 for v in s6 if v>0)}/6{mark}")
    return a,b
print(f"{'variante':<40} | {'2024: tr neto PF DD':^25} | {'600d: tr neto PF DD':^25} | {'TOTAL':^12} | {'6 tramos':^35} | pos")
# ATR mediana para regimen
tmp=signals()
for t in range(n):
    s=tmp[t]
    if s: buf.append(s[2])
    if len(buf)>300: buf.pop(0)
    med[t]=statistics.median(buf) if len(buf)>=30 else None
print("-- base y ejecucion --")
REF["base"]=row("ACTUAL (limite al cierre, trail 5x)",tmp)
row("  entrada a MERCADO",tmp,"base",market=True)
for off in (0.1,0.25): row(f"  limite a cierre -{off}xATR",tmp,"base",offset=off)
print("-- salida --")
for k in (3.0,4.0,6.0,7.0): row(f"  trailing {k}xATR",tmp,"base",trail=k)
for N in (8,16,32): row(f"  salida por tiempo {N} velas sin ganancia",tmp,"base",tstop=N)
print("-- lado / regimen / horario --")
row("  solo largos",tmp,"base",sides=("BUY",)); row("  solo cortos",tmp,"base",sides=("SELL",))
row("  solo volatilidad ALTA",tmp,"base",vol="alta"); row("  solo volatilidad BAJA",tmp,"base",vol="baja")
for nm,f in (("sin Asia 06-22",lambda h:6<=h<22),("Londres+NY 07-20",lambda h:7<=h<20),("solo NY 12-20",lambda h:12<=h<20),("sin NY (fuera 12-20)",lambda h:not(12<=h<20))): row(f"  horario {nm}",tmp,"base",hours=f)
print("-- piramide --")
for k,m in ((1.0,2),(2.0,2),(3.0,2),(2.0,3)): row(f"  +1 unidad cada {k}xATR, max {m}",tmp,"base",pyr=(k,m))
print("-- filtro direccional --")
for nm,kw in (("sin filtro ADX/EMA",dict(ADX_MIN=999)),("ADX>=15",dict(ADX_MIN=15)),("ADX>=25",dict(ADX_MIN=25)),("ADX>=30",dict(ADX_MIN=30)),("EMA100",dict(EMA_TREND=100)),("EMA300",dict(EMA_TREND=300))):
    row(f"  {nm}",signals(**kw),"base")
print("-- entrada (BB / RSI) --")
for nm,kw in (("BB20/2.0",dict(BB_LEN=20,BB_MULT=2.0)),("BB26/2.0",dict(BB_MULT=2.0)),("BB26/1.5",dict(BB_MULT=1.5)),("BB30/1.75",dict(BB_LEN=30)),("RSI 35/65",dict(RSI_LOW=35,RSI_HIGH=65)),("RSI 30/70",dict(RSI_LOW=30,RSI_HIGH=70)),("RSI 42/58",dict(RSI_LOW=42,RSI_HIGH=58))):
    row(f"  {nm}",signals(**kw),"base")
setp()
