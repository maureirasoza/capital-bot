#!/usr/bin/env python3
"""Trend oro: como gestionar el STOP de la unidad de PIRAMIDE (la base no se toca: trailing 5xATR + salida
por canal). Senal = bot_gold_trend.signal_at (ventana 600, EMA200), GOLD 1h 1000d reales. Variantes:
  comun   : la piramide comparte el stop de la base (supuesto del backtest original)
  propio5 : trailing propio 5xATR desde su entrada (lo que hace hoy capital.com)
  propioK : trailing propio K x ATR (K=1.5,2,3)
  be      : stop inicial en el precio de entrada de la BASE, luego trailing con esa misma distancia
  sin     : sin piramide (referencia)
Ambas unidades salen por canal Donchian. Costos: spread 0.3/lado por unidad. 2024 (no visto) | 600d | total."""
import sys
sys.argv=['x','--source','capital','--days','1000']
import backtest_real as br, bot_gold_trend as bt
O,H,L,C,T=br.fetch_capital("GOLD","HOUR",1000); n=len(C); W=bt.N_CANDLES; SP=0.3
sig=[None]*n
for t in range(W,n):
    lo=t-W+1; sig[t]=bt.signal_at(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1],W-1)
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=600)
def sim(mode,K=None,step=2.0):
    tr=[]; base=None; pyr=None
    def close_unit(u,px,t):
        g=(px-u["e"]) if u["s"]=="L" else (u["e"]-px); return {"net":g-2*SP,"t":t}
    for t in range(W,n):
        s=sig[t]
        # stops intrabar (base y piramide por separado), antes de mover trailing
        bstop=base["stop"] if base else None
        for nm in ("base","pyr"):
            u=base if nm=="base" else pyr
            if u is None: continue
            stop=bstop if (nm=="pyr" and mode=="comun" and bstop is not None) else u["stop"]
            hit=(u["s"]=="L" and L[t]<=stop) or (u["s"]=="S" and H[t]>=stop)
            if hit:
                tr.append(dict(close_unit(u,stop,T[t]),unit=nm))
                if nm=="base": base=None
                else: pyr=None
        if base is None and pyr is not None and mode=="comun":
            tr.append(dict(close_unit(pyr,bstop if bstop is not None else C[t],T[t]),unit="pyr")); pyr=None
        # salida por canal (al cierre) de todo
        if (base or pyr):
            u0=base or pyr
            if (u0["s"]=="L" and s["exit_long"]) or (u0["s"]=="S" and s["exit_short"]):
                for nm,u in (("base",base),("pyr",pyr)):
                    if u: tr.append(dict(close_unit(u,C[t],T[t]),unit=nm))
                base=pyr=None; continue
        # mover trailing
        for u in (base,pyr):
            if u is None: continue
            if u["s"]=="L": u["x"]=max(u["x"],H[t]); u["stop"]=max(u["stop"],u["x"]-u["d"])
            else: u["x"]=min(u["x"],L[t]); u["stop"]=min(u["stop"],u["x"]+u["d"])
        # piramide al cierre
        if base and pyr is None and mode!="sin" and not base.get("pyr_done"):
            lvl=base["e"]+(1 if base["s"]=="L" else -1)*step*base["atr"]
            if (base["s"]=="L" and C[t]>=lvl) or (base["s"]=="S" and C[t]<=lvl):
                e=C[t]; sg=1 if base["s"]=="L" else -1
                if mode in ("comun","propio5"): d=bt.ATR_STOP*base["atr"]
                elif mode=="be": d=abs(e-base["e"])
                else: d=K*base["atr"]
                pyr={"s":base["s"],"e":e,"d":d,"x":e,"stop":e-sg*d}; base["pyr_done"]=True
        # entrada nueva
        if base is None and pyr is None and s and s["atr"]:
            side="L" if s["long_break"] else ("S" if s["short_break"] else None)
            if side:
                d=bt.ATR_STOP*s["atr"]; e=C[t]; sg=1 if side=="L" else -1
                base={"s":side,"e":e,"d":d,"atr":s["atr"],"x":e,"stop":e-sg*d}
    return tr
def st(tr):
    tot=sum(x["net"] for x in tr); w=sum(x["net"] for x in tr if x["net"]>0); l=-sum(x["net"] for x in tr if x["net"]<=0)
    eq=pk=dd=0
    for x in sorted(tr,key=lambda z:z["t"]): eq+=x["net"]; pk=max(pk,eq); dd=min(dd,eq-pk)
    return tot,(w/l if l else 9),dd
print(f"{'variante':<36} | {'2024 (no visto)':^20} | {'600d':^22} | {'TOTAL 1000d':^22} | piramides: n, neto, peor")
for nm,mode,K in (("sin piramide","sin",None),("comun (backtest original)","comun",None),("propio 5xATR (EN VIVO HOY)","propio5",None),
                  ("propio 3xATR","propioK",3.0),("propio 2xATR","propioK",2.0),("propio 1.5xATR","propioK",1.5),("stop en entrada de la base","be",None)):
    tr=sim(mode,K); a=st([x for x in tr if x["t"]<T[cut]]); b=st([x for x in tr if x["t"]>=T[cut]]); c=st(tr)
    py=[x["net"] for x in tr if x["unit"]=="pyr"]
    print(f"{nm:<36} | {a[0]:>+6.0f} PF{a[1]:.2f} {a[2]:>+5.0f} | {b[0]:>+6.0f} PF{b[1]:.2f} {b[2]:>+6.0f} | {c[0]:>+6.0f} PF{c[1]:.2f} {c[2]:>+6.0f} | {len(py)}, {sum(py):+.0f}, {min(py) if py else 0:+.0f}")
