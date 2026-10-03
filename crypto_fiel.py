#!/usr/bin/env python3
"""Validacion FIEL del ATR-breakout cripto: senal en velas 4h (precio medio, como el bot) y EJECUCION en
velas de 5 min bid/ask: entrada a mercado en la apertura de los 5 min tras el cierre 4h (ask largo / bid
corto) + desliz 0.02%; trailing nativo movido cada 5 min contra bid (largo) / ask (corto), stop chequeado
ANTES de moverlo; piramide decidida al cierre 4h y ejecutada a mercado; financiamiento por dia por unidad.
Compara con el modelo 4h (crypto_lab) sobre el MISMO periodo."""
import sys, os, json, bisect
from datetime import datetime, timedelta
import crypto_lab as cl, backtest_real as br
def load5(epic):
    d=json.load(open(os.path.join(br.DATA_DIR,f"capital_{epic}_MINUTE_5_1000d_bidask.json"))); d["T"]=[datetime.fromisoformat(t) for t in d["T"]]; return d
def atrbk(d,k,ema_len=None):
    C,A=d["C"],d["ATR"]; n=d["n"]; s=[None]*n; E=cl.ema(C,ema_len) if ema_len else None
    for t in range(15,n):
        if A[t-1] and C[t]-C[t-1]>k*A[t-1] and (E is None or C[t]>E[t]): s[t]="L"
        elif A[t-1] and C[t-1]-C[t]>k*A[t-1] and (E is None or C[t]<E[t]): s[t]="S"
    return s
def sim(d4,d5,sig,trail,pyr=None,t_from=None):
    T4,C4,A4=d4["T"],d4["C"],d4["ATR"]; T5=d5["T"]; Ob,Oa,Hb,Ha,Lb,La=d5["Ob"],d5["Oa"],d5["Hb"],d5["Ha"],d5["Lb"],d5["La"]
    n4=d4["n"]; n5=len(T5); H4=timedelta(hours=4); tr=[]; pos=None
    def close(px,tm):
        r=0
        for e,te in pos["u"]:
            days=max(0,(tm-te).total_seconds()/86400)
            r+=((px/e-1) if pos["s"]=="L" else (1-px/e))-cl.SLIP-(cl.FIN_LONG if pos["s"]=="L" else cl.FIN_SHORT)*days
        tr.append({"r":r,"t_in":pos["t"],"t_out":tm,"s":pos["s"],"units":len(pos["u"]),"days":(tm-pos["t"]).total_seconds()/86400})
    t0=bisect.bisect_left(T4,t_from) if t_from else 60; t0=max(t0,60)
    j=bisect.bisect_left(T5,T4[t0]+H4)
    for t in range(t0,n4):
        D=T4[t]+H4; Dn=T4[t+1]+H4 if t+1<n4 else D+H4
        # decision al cierre 4h t: entrada nueva o piramide (se ejecutan en el primer 5m >= D)
        act=None
        if pos is None and sig[t]: act=("in",sig[t],A4[t])
        elif pos and pyr and len(pos["u"])<pyr[1]:
            lvl=pos["last"]+(1 if pos["s"]=="L" else -1)*pyr[0]*pos["atr"]
            if (pos["s"]=="L" and C4[t]>=lvl) or (pos["s"]=="S" and C4[t]<=lvl): act=("add",)
        while j<n5 and T5[j]<D: j+=1
        first=True
        while j<n5 and T5[j]<Dn:
            tm=T5[j]
            if first and act:
                if act[0]=="in" and pos is None and act[2]:
                    s=act[1]; e=Oa[j]*(1+cl.SLIP) if s=="L" else Ob[j]*(1-cl.SLIP); dist=trail*act[2]
                    pos={"s":s,"u":[(e,tm)],"t":tm,"ext":e,"stop":e-dist if s=="L" else e+dist,"dist":dist,"atr":act[2],"last":e}
                elif act[0]=="add" and pos:
                    e=Oa[j]*(1+cl.SLIP) if pos["s"]=="L" else Ob[j]*(1-cl.SLIP); pos["u"].append((e,tm)); pos["last"]=e
            first=False
            if pos:
                if pos["s"]=="L" and Lb[j]<=pos["stop"]: close(min(pos["stop"],Ob[j]),tm); pos=None
                elif pos["s"]=="S" and Ha[j]>=pos["stop"]: close(max(pos["stop"],Oa[j]),tm); pos=None
                else:
                    if pos["s"]=="L": pos["ext"]=max(pos["ext"],Hb[j]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                    else: pos["ext"]=min(pos["ext"],La[j]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
            j+=1
    return tr
if __name__=="__main__":
    exec(open('crypto_atrbk2.py').read().split("YRS=")[0].split("data={e")[0])   # imports
    src=open('crypto_atrbk2.py').read(); exec(src[src.index("def run_pyr"):src.index("YRS=")])
    print(f"{'config':<34} {'activo':<4} | {'MODELO 4h: n tot% PF acc':^28} | {'FIEL 5m: n tot% PF acc DD':^34} | por anio (fiel)")
    for e in ("BTCUSD","ETHUSD"):
        d4=cl.load(e,"HOUR_4",2200); d5=load5(e); t_from=d5["T"][0]+timedelta(days=2)
        sub=[i for i,t in enumerate(d4["T"]) if t>=t_from]; print(f"   {e}: 5m {len(d5['T'])} velas {d5['T'][0]:%Y-%m-%d} -> {d5['T'][-1]:%Y-%m-%d}")
        for name,k,tl,el,py in (("base k3 t2",3.0,2.0,None,None),("k3 t2 EMA200",3.0,2.0,200,None),("k3 t2 EMA200 pir2x2 (CENTRO)",3.0,2.0,200,(2.0,2)),
                                ("k3 t3 EMA200 pir2x2",3.0,3.0,200,(2.0,2)),("k3.5 t2 EMA200 pir2x2",3.5,2.0,200,(2.0,2)),("k3 t2 EMA250 pir3x2",3.0,2.0,250,(3.0,2))):
            sg=atrbk(d4,k,el)
            mod=run_pyr(d4,sg,tl,py[0],py[1]) if py else cl.run(d4,sg,tl,None,("L","S"))
            mod=[x for x in mod if x["t_in"]>=t_from]; m=cl.stats(mod)
            f=sim(d4,d5,sg,tl,py,t_from); s=cl.stats(f)
            print(f"{name:<34} {e[:3]:<4} | {m['n']:>4} {m['tot']:>+6.0f} {m['pf']:>5.2f} {m['acc']:>3.0f}% | {s['n']:>4} {s['tot']:>+6.0f} {s['pf']:>5.2f} {s['acc']:>3.0f}% {s['dd']:>+5.0f} | "+" ".join(f"{y}:{s['years'].get(y,0):+.0f}" for y in sorted(s['years'])))
