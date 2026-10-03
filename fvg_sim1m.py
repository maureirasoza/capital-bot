#!/usr/bin/env python3
"""Simulador FVG FIEL: senales en velas 15m cerradas (precio medio, funcion REAL del bot) y
EJECUCION minuto a minuto con bid/ask reales. Elimina el sesgo del backtest de 15m, que cobraba
un TP 'en la misma vela de la entrada' usando un maximo/minimo ocurrido ANTES del llenado.
  compra limite: se llena cuando el ASK de 1m <= nivel; TP/SL contra el BID.
  venta limite : se llena cuando el BID de 1m >= nivel; TP/SL contra el ASK.
La orden se coloca 1 min despues del cierre de la vela 15m (como el cron) y vive remaining x 15 min."""
import os, json, bisect
from datetime import datetime, timedelta
import backtest_real as br
WIN=br.WIN_FVG

def load(days=1000):
    out=[]
    for res in ("MINUTE_15","MINUTE"):
        d=json.load(open(os.path.join(br.DATA_DIR,f"capital_GOLD_{res}_{days}d_bidask.json")))
        d["T"]=[datetime.fromisoformat(t) for t in d["T"]]; out.append(d)
    return out

def prep(d15):
    m=lambda a,b:[(x+y)/2 for x,y in zip(d15[a],d15[b])]
    return m("Ob","Oa"),m("Hb","Ha"),m("Lb","La"),m("Cb","Ca")

def sim(d15, d1, fv, a=None, b=None, sigfn=None, extra=None, be=None, mids=None):
    """a,b: datetimes limite (inicio/fin). extra(setup, t_idx)->bool. Devuelve lista de trades."""
    O,H,L,C=mids or prep(d15); T15=d15["T"]; T1=d1["T"]; n=len(C)
    Ob,Hb,Lb,Oa,Ha,La,Ca,Cb=d1["Ob"],d1["Hb"],d1["Lb"],d1["Oa"],d1["Ha"],d1["La"],d1["Ca"],d1["Cb"]
    sigfn=sigfn or fv.find_pending_fvg_ohlc
    t0=max(WIN, bisect.bisect_left(T15,a) if a else WIN); t1=bisect.bisect_left(T15,b) if b else n
    trades=[]; pos=None; order=None; M=timedelta(minutes=15); m1=timedelta(minutes=1)
    j=bisect.bisect_left(T1,T15[t0]+M); n1=len(T1); nofine=0
    for t in range(t0,t1):
        D=T15[t]+M                                   # cierre de la vela 15m t = momento de decision
        if pos is None and order is None:
            lo=t-WIN+1; sig=sigfn(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if sig and sig.get("side") and not (extra and not extra(sig,t)):
                order={"side":sig["side"],"level":sig["level"],"sl":sig["sl"],"tp":sig["tp"],"start":D+m1,
                       "exp":D+m1+timedelta(minutes=15*sig["remaining_bars"]),"t_sig":D,"meta":sig,"first":True}
        Dn=(T15[t+1]+M) if t+1<n else D+M
        while j<n1 and T1[j]<D: j+=1
        if (pos or order) and (j>=n1 or T1[j]>=Dn): nofine+=1
        while j<n1 and T1[j]<Dn:
            tm=T1[j]
            if order and tm>=order["start"]:
                if order["first"]:                 # guarda del bot al colocar: nivel del lado correcto
                    order["first"]=False
                    if (order["side"]=="BUY" and order["level"]>=Oa[j]) or (order["side"]=="SELL" and order["level"]<=Ob[j]): order=None
                if order and tm>=order["exp"]: order=None
                if order:
                    if order["side"]=="BUY" and La[j]<=order["level"]:
                        pos={"side":"BUY","entry":min(order["level"],Oa[j]),"sl":order["sl"],"tp":order["tp"],"t_in":tm,"meta":order["meta"],"t_sig":order["t_sig"],"be":False}; order=None
                    elif order["side"]=="SELL" and Hb[j]>=order["level"]:
                        pos={"side":"SELL","entry":max(order["level"],Ob[j]),"sl":order["sl"],"tp":order["tp"],"t_in":tm,"meta":order["meta"],"t_sig":order["t_sig"],"be":False}; order=None
            if pos:
                ex=None
                if pos["side"]=="BUY":
                    if Lb[j]<=pos["sl"]: ex=min(pos["sl"],Ob[j]) if tm>pos["t_in"] else pos["sl"]
                    elif Hb[j]>=pos["tp"] and tm>pos["t_in"]: ex=pos["tp"]       # sin TP en el mismo minuto del llenado
                else:
                    if Ha[j]>=pos["sl"]: ex=max(pos["sl"],Oa[j]) if tm>pos["t_in"] else pos["sl"]
                    elif La[j]<=pos["tp"] and tm>pos["t_in"]: ex=pos["tp"]
                if ex is not None:
                    g=(ex-pos["entry"]) if pos["side"]=="BUY" else (pos["entry"]-ex)
                    trades.append({"side":pos["side"],"entry":pos["entry"],"exit":ex,"t_in":pos["t_in"],"t_out":tm,"net":g,"gross":g,
                                   "sl":pos["sl"],"tp":pos["tp"],"meta":pos["meta"],"t_sig":pos["t_sig"]}); pos=None
            j+=1
    sim.nofine=nofine
    return trades

def stats(tr,k=3):
    if not tr: return dict(n=0,tot=0,pf=0,acc=0,dd=0,seg=[0]*k,rob=0,w=0,l=0)
    tot=sum(x["net"] for x in tr); w=[x["net"] for x in tr if x["net"]>0]; l=[-x["net"] for x in tr if x["net"]<=0]
    eq=pk=dd=0
    for x in tr: eq+=x["net"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    t0=tr[0]["t_in"]; t1=tr[-1]["t_in"]; span=(t1-t0)/k if t1>t0 else timedelta(days=1); seg=[0.0]*k
    for x in tr: seg[min(k-1,int((x["t_in"]-t0)/span))]+=x["net"]
    return dict(n=len(tr),tot=tot,pf=sum(w)/sum(l) if l else 9,acc=100*len(w)/len(tr),dd=dd,seg=seg,rob=sum(1 for v in seg if v>0),
                w=sum(w)/len(w) if w else 0,l=sum(l)/len(l) if l else 0)
