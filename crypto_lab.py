#!/usr/bin/env python3
"""LABORATORIO CRIPTO (BTC/ETH) con costos REALES de capital.com: bid/ask historico, financiamiento
nocturno (largo -0.0616%/dia; corto 0 conservador: no se cuenta el credito), desliz 0.02%.
Senal al CIERRE de la vela (precio medio); entrada en la APERTURA de la siguiente (ask/bid);
stops chequeados contra bid (largo) / ask (corto) ANTES de mover el trailing (sin look-ahead);
gap a traves del stop -> se ejecuta en la apertura. Resultados en % por operacion (1 unidad).
Uso: import crypto_lab as cl; cl.load(epic,res); cl.run(...)"""
import os, json, statistics
from datetime import datetime, timedelta
import backtest_real as br
FIN_LONG=0.000616; FIN_SHORT=0.0; SLIP=0.0002
def load(epic,res,days):
    d=json.load(open(os.path.join(br.DATA_DIR,f"capital_{epic}_{res}_{days}d_bidask.json")))
    d["T"]=[datetime.fromisoformat(t) for t in d["T"]]
    m=lambda a,b:[(x+y)/2 for x,y in zip(d[a],d[b])]
    d["O"],d["H"],d["L"],d["C"]=m("Ob","Oa"),m("Hb","Ha"),m("Lb","La"),m("Cb","Ca")
    n=len(d["C"]); tr=[d["H"][0]-d["L"][0]]+[max(d["H"][i]-d["L"][i],abs(d["H"][i]-d["C"][i-1]),abs(d["L"][i]-d["C"][i-1])) for i in range(1,n)]
    a=[None]*n; p=sum(tr[:14])/14; a[13]=p
    for i in range(14,n): p=(p*13+tr[i])/14; a[i]=p
    d["ATR"]=a; d["n"]=n; return d
def ema(s,k):
    out=[s[0]]; a=2/(k+1)
    for x in s[1:]: out.append(x*a+out[-1]*(1-a))
    return out
def run(d, sig, trail=None, exitsig=None, sides=("L","S"), warm=60, fin_short=None):
    """sig[t] in {'L','S',None} decidido al cierre de t. exitsig[t] in {'XL','XS',None} (salida al cierre).
    trail = k (x ATR al entrar) o None. Devuelve lista de trades con r (%), t_in, t_out, side."""
    fs=FIN_SHORT if fin_short is None else fin_short
    O,C,T,A=d["O"],d["C"],d["T"],d["ATR"]; Ob,Oa,Hb,Ha,Lb,La=d["Ob"],d["Oa"],d["Hb"],d["Ha"],d["Lb"],d["La"]; n=d["n"]
    tr=[]; pos=None; pend=None; pend_exit=False
    for t in range(warm,n):
        # 1) ejecutar en la APERTURA de t lo decidido al cierre de t-1
        if pend_exit and pos:
            ex=Ob[t] if pos["s"]=="L" else Oa[t]; close_pos(tr,pos,ex,T[t],fs); pos=None
        pend_exit=False
        if pend and pos is None:
            s=pend; e=(Oa[t]*(1+SLIP)) if s=="L" else (Ob[t]*(1-SLIP)); a=A[t-1]
            pos={"s":s,"e":e,"t":T[t],"ext":e,"stop":(e-trail*a if s=="L" else e+trail*a) if trail else None,"dist":trail*a if trail else None}
        pend=None
        # 2) durante la vela t: stop (contra bid/ask), luego mover trailing con el extremo de t
        if pos and pos["stop"] is not None:
            if pos["s"]=="L" and Lb[t]<=pos["stop"]:
                ex=min(pos["stop"],Ob[t]); close_pos(tr,pos,ex,T[t],fs); pos=None
            elif pos["s"]=="S" and Ha[t]>=pos["stop"]:
                ex=max(pos["stop"],Oa[t]); close_pos(tr,pos,ex,T[t],fs); pos=None
            else:
                if pos["s"]=="L": pos["ext"]=max(pos["ext"],Hb[t]); pos["stop"]=max(pos["stop"],pos["ext"]-pos["dist"])
                else: pos["ext"]=min(pos["ext"],La[t]); pos["stop"]=min(pos["stop"],pos["ext"]+pos["dist"])
        # 3) al cierre de t: salidas por senal y nuevas entradas (ejecutan en la apertura de t+1)
        if t+1>=n: break
        if pos:
            if exitsig and exitsig[t]==("X"+pos["s"]): pend_exit=True
            elif sig[t] and sig[t]!=pos["s"] and sig[t] in sides: pend_exit=True; pend=sig[t]   # reversa
            continue
        if sig[t] in sides: pend=sig[t]
    if pos: close_pos(tr,pos,C[n-1],T[n-1],fs)
    return tr
def close_pos(tr,pos,ex,tout,fs):
    days=max(0.0,(tout-pos["t"]).total_seconds()/86400)
    r=(ex/pos["e"]-1) if pos["s"]=="L" else (1-ex/pos["e"])
    r-=SLIP+(FIN_LONG if pos["s"]=="L" else fs)*days
    tr.append({"r":r,"t_in":pos["t"],"t_out":tout,"s":pos["s"],"days":days})
def stats(tr):
    if not tr: return dict(n=0,tot=0,pf=0,acc=0,dd=0,years={},L=0,S=0,days=0)
    w=sum(x["r"] for x in tr if x["r"]>0); l=-sum(x["r"] for x in tr if x["r"]<=0)
    eq=pk=dd=0
    for x in tr: eq+=x["r"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    yrs={}
    for x in tr: yrs[x["t_in"].year]=yrs.get(x["t_in"].year,0)+x["r"]
    return dict(n=len(tr),tot=100*sum(x["r"] for x in tr),pf=w/l if l else 9,acc=100*sum(1 for x in tr if x["r"]>0)/len(tr),
                dd=100*dd,years={k:100*v for k,v in yrs.items()},L=100*sum(x["r"] for x in tr if x["s"]=="L"),
                S=100*sum(x["r"] for x in tr if x["s"]=="S"),days=statistics.mean(x["days"] for x in tr))
def buyhold(d,warm=60):
    """referencia: comprar y mantener con el financiamiento de largo (por anio, en %)."""
    T,C=d["T"],d["C"]; yrs={}; start={}
    for t in range(warm,d["n"]):
        y=T[t].year
        if y not in start: start[y]=C[t]
        yrs[y]=C[t]
    return {y:100*(yrs[y]/start[y]-1-FIN_LONG*365) for y in yrs}
