#!/usr/bin/env python3
"""US30 bandas (bot_us30): validacion FIEL 1m bid/ask del trailing y de variantes BB/RSI vecinas (10-oct-2026).
Limite al cierre valida 15 min (como el bot), trailing nativo k x ATR. Mitades + 6 tramos. Base: us100_fiel.py."""
import os, sys, json, bisect
from datetime import datetime, timedelta
import backtest_real as br, fvg_sim1m as s1, bot_us30 as us
bg=br._import_bollinger(); WIN=300
def load(epic,res,days):
    d=json.load(open(os.path.join(br.DATA_DIR,f"capital_{epic}_{res}_{days}d_bidask.json"))); d["T"]=[datetime.fromisoformat(t) for t in d["T"]]; return d
d15=load("US30","MINUTE_15",600); d1=load("US30","MINUTE",600)
O,H,L,C=s1.prep(d15); T=d15["T"]; T1=d1["T"]; n=len(C); Ob,Hb,Lb,Oa,Ha,La=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"]
spr=sum(a-b for a,b in zip(d15["Ca"],d15["Cb"]))/n; print(f"US30 15m {n} velas {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | 1m {len(T1)} velas | spread medio {spr:.3f}")
mid=T[n//2]
def signals(mod,**kw):
    for k,v in kw.items(): setattr(mod,k,v)
    sig=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=mod.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
        if s["side"] and s["atr"]: sig[t]=(s["side"],s["close"],s["atr"])
    return sig
def sim(sig,trail):
    M=timedelta(minutes=15); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[WIN]+M); n1=len(T1); tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=T[t]+M
        if pos is None and order is None and sig[t]:
            side,close,atr=sig[t]; order={"side":side,"level":close,"dist":trail*atr,"start":D+m1,"exp":D+M+m1,"first":True}
        Dn=(T[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"]:
                fill=None; long=order["side"]=="BUY"
                if order["first"]:
                    order["first"]=False
                    if (long and Oa[j]<=order["level"]) or ((not long) and Ob[j]>=order["level"]): fill=Oa[j] if long else Ob[j]
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
    if len(tr)<30: return
    a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); c=s1.stats(tr)
    weeks=(T[-1]-T[WIN]).days/7; ok=" <<<" if a["tot"]>0 and b["tot"]>0 and a["pf"]>=1.15 and b["pf"]>=1.15 else ""
    print(f"{name:<36} | {a['n']:>4} {a['tot']:>+6.1f} {a['pf']:>5.2f} {a['dd']:>+6.1f} | {b['n']:>4} {b['tot']:>+6.1f} {b['pf']:>5.2f} {b['dd']:>+6.1f} | {c['tot']:>+6.1f} {c['pf']:>5.2f} {c['acc']:>3.0f}% {len(tr)/weeks:>4.1f}/sem{ok}")

def seg6(tr):
    t0=tr[0]["t_in"]; span=(tr[-1]["t_in"]-t0)/6; o=[0.0]*6
    for x in tr: o[min(5,int((x["t_in"]-t0)/span))]+=x["net"]
    return o
print(f"{'config':<30} | {'mitad1 neto PF':>16} | {'mitad2 neto PF':>16} | {'TOTAL pts':>9} {'PF':>5} {'DD':>7} | 6 tramos (pts)")
for bl,bm in ((20,2.0),(26,1.75),(20,2.25)):
    for rlo,rhi in ((35,65),(30,70),(40,60)):
        sig=signals(us,BB_LEN=bl,BB_MULT=bm,RSI_LOW=rlo,RSI_HIGH=rhi)
        for k in (3.0,3.5,4.0,4.5,5.0,6.0):
            tr=sim(sig,k)
            if len(tr)<30: continue
            a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); c=s1.stats(tr); sg=seg6(tr)
            act=" <- ACTUAL" if (bl,bm,rlo,rhi,k)==(20,2.0,35,65,5.0) else ""
            print(f"BB{bl}/{bm} RSI{rlo}/{rhi} trail{k:<4} | {a['tot']:>+8.0f} {a['pf']:>5.2f} | {b['tot']:>+8.0f} {b['pf']:>5.2f} | {c['tot']:>+9.0f} {c['pf']:>5.2f} {c['dd']:>+7.0f} | "
                  +" ".join(f"{v:+.0f}" for v in sg)+f"  ({sum(1 for v in sg if v>0)}/6+){act}", flush=True)
