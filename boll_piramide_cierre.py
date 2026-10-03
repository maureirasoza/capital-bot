#!/usr/bin/env python3
"""Bollinger oro: piramide en modo EJECUTABLE (se decide con el CIERRE 15m y se agrega a mercado en
el minuto :01 siguiente), vs modo 'nivel intrabar'. Ejecucion fiel 1m. 2024 | 600d | 6 tramos."""
import sys, bisect
sys.argv=['x']
src=open('boll_mejora1m.py').read().split('print(f"{\'variante\'')[0]
exec(src)
IDX={t:i for i,t in enumerate(T)}
def sim_c(sig, trail=5.0, pyr=None):
    """igual que sim(), piramide solo al cierre 15m: si C15 >= nivel, agrega al ask/bid de apertura del minuto :01"""
    M=timedelta(minutes=15); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[WIN]+M); n1=len(T1)
    tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=T[t]+M
        if pos is None and order is None and sig[t]:
            side,close,atr=sig[t]; order={"side":side,"level":close,"dist":trail*atr,"atr":atr,"start":D+m1,"exp":D+M+m1,"first":True}
        Dn=(T[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"]:
                fill=None
                if order["first"]:
                    order["first"]=False
                    if (order["side"]=="BUY" and Oa[j]<=order["level"]) or (order["side"]=="SELL" and Ob[j]>=order["level"]): fill=Oa[j] if order["side"]=="BUY" else Ob[j]
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
                if ex is not None:
                    tr.append({"net":sum(sg*(ex-e) for e in pos["entries"]),"t_in":pos["t_in"],"t_out":tm,"u":len(pos["entries"])}); pos=None
                else:
                    if long: pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
                    if pyr and len(pos["entries"])<pyr[1] and tm.minute%15==1 and tm>pos["t_in"]+m1:
                        prev=tm.replace(minute=(tm.minute//15)*15)-M; i15=IDX.get(prev)
                        if i15 is not None:
                            lvl=pos["last"]+sg*pyr[0]*pos["atr"]; c15=C[i15]
                            if (long and c15>=lvl) or ((not long) and c15<=lvl):
                                px=Oa[j] if long else Ob[j]; pos["entries"].append(px); pos["last"]=px
            j+=1
    return tr
def row2(name,full,ref=None):
    a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut]); c=s1.stats(full); s6=seg6(full)
    pir=100*sum(1 for x in full if x["u"]>1)/len(full)
    print(f"{name:<36} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['dd']:>+5.0f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['dd']:>+5.0f} | {c['tot']:>+6.0f} {c['pf']:>5.2f} {c['tot']/abs(c['dd']):>4.1f} | "+' '.join(f"{v:>+5.0f}" for v in s6)+f" | {sum(1 for v in s6 if v>0)}/6 | {pir:>3.0f}% | peor {min(x['net'] for x in full):+.0f}")
sig=signals()
print(f"{'variante':<36} | {'2024: tr neto PF DD':^25} | {'600d: tr neto PF DD':^25} | {'TOTAL n/DD':^17} | {'6 tramos':^35} | pos | %pir")
row2("ACTUAL 1 unidad",sim(sig))
row2("doble tamano fijo",[dict(x,net=2*x["net"]) for x in sim(sig)])
for k,m in ((2.0,2),(3.0,2),(4.0,2),(2.0,3),(3.0,3)):
    row2(f"piramide CIERRE +1 cada {k}xATR max {m}",sim_c(sig,pyr=(k,m)))
