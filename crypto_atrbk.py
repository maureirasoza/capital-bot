#!/usr/bin/env python3
"""ATR-BREAKOUT (estallido de volatilidad) en BTC/ETH: |cierre - cierre previo| > k x ATR(previo) ->
seguir la direccion a la apertura siguiente, salida trailing t x ATR. Malla k x t x lados en 4h (6 anios)
y 1h (3 anios), costos reales (bid/ask, financiamiento largo, desliz)."""
import sys
import crypto_lab as cl
def atrbk(d,k):
    C,A=d["C"],d["ATR"]; n=d["n"]; s=[None]*n
    for t in range(15,n):
        if A[t-1] and C[t]-C[t-1]>k*A[t-1]: s[t]="L"
        elif A[t-1] and C[t-1]-C[t]>k*A[t-1]: s[t]="S"
    return s
for res,days in (("HOUR_4",2200),("HOUR",1100)):
    data={e:cl.load(e,res,days) for e in ("BTCUSD","ETHUSD")}
    yrs=sorted({t.year for t in data["BTCUSD"]["T"][60:]}); weeks=(data["BTCUSD"]["T"][-1]-data["BTCUSD"]["T"][60]).days/7
    print(f"\n######## {res}: {data['BTCUSD']['T'][60]:%Y-%m-%d} -> {data['BTCUSD']['T'][-1]:%Y-%m-%d} ({weeks:.0f} sem)")
    print("malla: celda = PF_BTC/PF_ETH ; * = ambos PF>1.2 y ambos con >= (anios-2) anios positivos")
    ks=(1.5,2.0,2.5,3.0,3.5,4.0); ts=(1.5,2.0,3.0,4.0,5.0)
    SG={k:{e:atrbk(d,k) for e,d in data.items()} for k in ks}
    for sides,lab in ((("L","S"),"2 LADOS"),(("L",),"SOLO LARGO"),(("S",),"SOLO CORTO")):
        print(f"-- {lab} --   "+"".join(f"{'trail'+str(t):>16}" for t in ts))
        for k in ks:
            cells=[]
            for t in ts:
                rb=cl.stats(cl.run(data["BTCUSD"],SG[k]["BTCUSD"],t,None,sides)); re=cl.stats(cl.run(data["ETHUSD"],SG[k]["ETHUSD"],t,None,sides))
                yb=sum(1 for y in yrs if rb["years"].get(y,0)>0); ye=sum(1 for y in yrs if re["years"].get(y,0)>0)
                star="*" if rb["pf"]>1.2 and re["pf"]>1.2 and yb>=len(yrs)-2 and ye>=len(yrs)-2 else " "
                cells.append(f"{rb['pf']:>5.2f}/{re['pf']:<5.2f}{star}")
            print(f"   k{k:<4}      "+"".join(f"{c:>16}" for c in cells))
    print("detalle de la zona k2.5-3.5 trail2-4, 2 lados:")
    for k in (2.5,3.0,3.5):
        for t in (2.0,3.0,4.0):
            for e,d in data.items():
                tr=cl.run(d,SG[k][e],t,None,("L","S")); s=cl.stats(tr)
                print(f"   k{k} trail{t} {e[:3]}: {s['n']:>4} tr ({s['n']/weeks:.1f}/sem) tot {s['tot']:>+5.0f}% PF {s['pf']:.2f} acc {s['acc']:.0f}% DD {s['dd']:+.0f}% L {s['L']:+.0f} S {s['S']:+.0f} dias/op {s['days']:.1f} | "+" ".join(f"{y}:{s['years'].get(y,0):+.0f}" for y in yrs))
