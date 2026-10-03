#!/usr/bin/env python3
"""ATR-breakout 4h en una CESTA de criptos: bruto (sin costos) vs neto (bid/ask real + financiamiento).
Zona k3.0-3.5 x trail 2-4, 2 lados. Si el fenomeno es real, el BRUTO debe ser positivo en casi todas."""
import os
import crypto_lab as cl
def atrbk(d,k):
    C,A=d["C"],d["ATR"]; n=d["n"]; s=[None]*n
    for t in range(15,n):
        if A[t-1] and C[t]-C[t-1]>k*A[t-1]: s[t]="L"
        elif A[t-1] and C[t-1]-C[t]>k*A[t-1]: s[t]="S"
    return s
EP=["BTCUSD","ETHUSD","UNIUSD","DOTUSD","AVAXUSD","ADAUSD","BCHUSD","XLMUSD","LINKUSD","LTCUSD","DOGEUSD","XRPUSD","SOLUSD"]
def bruto(d):
    """copia de d con bid=ask=medio (sin spread) para medir el fenomeno sin costos"""
    g=dict(d)
    for s in ("O","H","L","C"): g[s+"b"]=d[s]; g[s+"a"]=d[s]
    return g
CELLS=[(k,t) for k in (3.0,3.5) for t in (2.0,3.0,4.0)]
print(f"{'cripto':<8} {'velas':>6} {'desde':<11} {'spr%med':>7} | "+" | ".join(f"k{k} t{t} bruto/neto" for k,t in CELLS))
agg={c:{"b":[], "n":[]} for c in CELLS}
for e in EP:
    path=os.path.join("data",f"capital_{e}_HOUR_4_2200d_bidask.json")
    if not os.path.exists(path): continue
    d=cl.load(e,"HOUR_4",2200); g=bruto(d)
    spr=sum((a-b)/((a+b)/2) for a,b in zip(d["Ca"],d["Cb"]))/d["n"]
    cells=[]
    for k,t in CELLS:
        sg=atrbk(d,k)
        sl,fl=cl.SLIP,cl.FIN_LONG; cl.SLIP=0; cl.FIN_LONG=0
        rb=cl.stats(cl.run(g,sg,t,None,("L","S"))); cl.SLIP,cl.FIN_LONG=sl,fl
        rn=cl.stats(cl.run(d,sg,t,None,("L","S")))
        agg[(k,t)]["b"].append(rb); agg[(k,t)]["n"].append((e,rn))
        cells.append(f"{rb['pf']:>4.2f}/{rn['pf']:<4.2f} ({rn['n']:>3})")
    print(f"{e:<8} {d['n']:>6} {d['T'][0]:%Y-%m-%d} {100*spr:>6.3f}% | "+" | ".join(f"{c:>19}" for c in cells))
print("\nresumen por celda: criptos con PF BRUTO > 1 | criptos con PF NETO > 1.15")
for c in CELLS:
    nb=sum(1 for r in agg[c]["b"] if r["pf"]>1); nn=[e for e,r in agg[c]["n"] if r["pf"]>1.15]
    print(f"  k{c[0]} trail{c[1]}: bruto>1 en {nb}/{len(agg[c]['b'])} | neto>1.15 en {len(nn)}: {' '.join(x[:-3] for x in nn)}")
