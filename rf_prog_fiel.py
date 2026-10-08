#!/usr/bin/env python3
"""US30 ruptura fallida: apretar tras ganancia, con EJECUCION FIEL 1m bid/ask (senal 1h real, entrada a mercado
en el minuto :01, trailing nativo minuto a minuto). El bot revisa al cierre de cada vela 1h: si la ganancia maxima
>= M x ATR, cambia la distancia a k x ATR (capital.com re-ancla desde el extremo). Dos mitades de 600d."""
import sys; sys.argv=['x']
src=open('rf_nativo.py').read(); exec(src[:src.index("def sim_nativo")])
def sim_p(N,Mc,p,M=None,k=None,WIN=200):
    M60=timedelta(minutes=60); m1=timedelta(minutes=1); j=bisect.bisect_left(T1,T[WIN]+M60); n1=len(T1); tr=[]; pos=None; order=None
    for t in range(WIN,n):
        D=T[t]+M60; a=ATR[t]
        # decision del bot al cierre de la vela 1h t: apretar si corresponde
        if pos and M and not pos["tight"] and pos["sg"]*(pos["ext"]-pos["entry"])>=M*pos["atr"]:
            pos["dist"]=k*pos["atr"]; pos["tight"]=True
            pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"]) if pos["sg"]==1 else min(pos["stop"],pos["ext"]+pos["dist"])
        if pos is None and order is None and a:
            lo=t-WIN+1; s=signal_at(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1],WIN-1,N,Mc)
            if s: order={"side":s[0],"atr":a,"start":D+m1}
        Dn=(T[t+1]+M60) if t+1<n else D+M60
        while j<n1 and T1[j]<D: j+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"] and pos is None:
                long=order["side"]=="BUY"; e=Oa[j] if long else Ob[j]; d=p*order["atr"]
                pos={"sg":1 if long else -1,"entry":e,"stop":e-d if long else e+d,"dist":d,"atr":order["atr"],"ext":e,"t_in":tm,"tight":False}; order=None
            if pos:
                sg=pos["sg"]; ex=None
                if sg==1 and Lb[j]<=pos["stop"]: ex=min(pos["stop"],Ob[j]) if Ob[j]<pos["stop"] else pos["stop"]
                elif sg==-1 and Ha[j]>=pos["stop"]: ex=max(pos["stop"],Oa[j]) if Oa[j]>pos["stop"] else pos["stop"]
                if ex is not None: tr.append({"net":sg*(ex-pos["entry"]),"t_in":pos["t_in"],"t_out":tm}); pos=None
                else:
                    if sg==1: pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
            j+=1
    return tr
base=sim_p(48,2,3.0); a0=s1.stats([x for x in base if x["t_in"]<mid]); b0=s1.stats([x for x in base if x["t_in"]>=mid]); c0=s1.stats(base)
print(f"FIEL 1m US30 RF: ACTUAL trail 3x: {c0['n']} tr total {c0['tot']:+.0f} PF {c0['pf']:.2f} DD {c0['dd']:+.0f} | mitades {a0['tot']:+.0f} / {b0['tot']:+.0f}")
print(f"{'regla':<22} | {'mitad1':>8} {'mitad2':>8} | {'total':>8} {'PF':>5} {'DD':>6} {'acc':>4} | mejora")
for M,k in ((3,1.0),(3,1.5),(3,2.0),(4,1.0),(4,1.5),(4,2.0),(5,1.5),(6,1.5),(2,1.0),(2,1.5)):
    tr=sim_p(48,2,3.0,M,k); a=s1.stats([x for x in tr if x["t_in"]<mid]); b=s1.stats([x for x in tr if x["t_in"]>=mid]); c=s1.stats(tr)
    ok="*" if a["tot"]>a0["tot"] and b["tot"]>b0["tot"] else " "
    print(f"tras +{M}xATR -> {k}x      | {a['tot']:>+8.0f} {b['tot']:>+8.0f} | {c['tot']:>+8.0f} {c['pf']:>5.2f} {c['dd']:>+6.0f} {c['acc']:>3.0f}% | {100*(c['tot']-c0['tot'])/abs(c0['tot']):>+4.0f}% {ok}")
