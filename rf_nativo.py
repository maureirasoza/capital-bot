#!/usr/bin/env python3
"""Ruptura fallida US30, version EJECUTABLE: trailing nativo p x ATR desde la entrada (sin stop
estructural aparte) y senal como FUNCION PURA sobre la ventana (maquina de estados de la ruptura
pendiente sin depender de la posicion). Ejecucion fiel 1m."""
import sys; sys.argv=['x']
src=open('ruptura_fallida_fiel.py').read(); exec(src[:src.index("\ndef sim(")])
def signal_at(O,H,L,C,i,N,M):
    """Devuelve ('SELL'|'BUY', nivel) si en la vela i se CONFIRMA una ruptura fallida; None si no.
    Maquina de estados sobre la ventana: una ruptura queda pendiente hasta M velas; otra ruptura no la
    reemplaza mientras este pendiente (igual que la simulacion)."""
    pend=None
    for t in range(N+1,i+1):
        hh=max(H[t-N:t]); ll=min(L[t-N:t])
        if pend:
            if t>pend[1]+M: pend=None
            elif pend[0]=='up' and C[t]<pend[2]:
                if t==i: return ('SELL',pend[2])
                pend=None; continue
            elif pend[0]=='down' and C[t]>pend[2]:
                if t==i: return ('BUY',pend[2])
                pend=None; continue
            else: continue
        if C[t]>hh: pend=('up',t,hh)
        elif C[t]<ll: pend=('down',t,ll)
    return None
def sim_nativo(N,M,p,WIN=200):
    M60=timedelta(minutes=60); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[WIN]+M60); n1=len(T1); tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=T[t]+M60; a=ATR[t]
        if pos is None and order is None and a:
            lo=t-WIN+1; s=signal_at(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1],WIN-1,N,M)
            if s: order={"side":s[0],"dist":p*a,"start":D+m1}
        Dn=(T[t+1]+M60) if t+1<n else D+M60
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"] and pos is None:
                long=order["side"]=="BUY"; e=Oa[j] if long else Ob[j]; d=order["dist"]
                pos={"long":long,"entry":e,"stop":e-d if long else e+d,"dist":d,"ext":e,"t_in":tm}; order=None
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
weeks=(T[-1]-T[0]).days/7
print(f"{'config (trailing nativo, senal pura)':<34} | {'MITAD 1: tr neto PF DD':^26} | {'MITAD 2: tr neto PF DD':^26} | {'TOTAL PF acc frec':^20}")
for N in (48,96):
    for M in (2,3):
        for p in (2.0,2.5,3.0,4.0):
            tr=sim_nativo(N,M,p); a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); c=s1.stats(tr)
            ok=" <<<" if a["tot"]>0 and b["tot"]>0 and a["pf"]>1.15 and b["pf"]>1.15 else ""
            print(f"N{N} M{M} trail{p:<4}                   | {a['n']:>4} {a['tot']:>+7.0f} {a['pf']:>5.2f} {a['dd']:>+6.0f} | {b['n']:>4} {b['tot']:>+7.0f} {b['pf']:>5.2f} {b['dd']:>+6.0f} | {c['pf']:>5.2f} {c['acc']:>3.0f}% {len(tr)/weeks:>4.1f}/sem{ok}")
