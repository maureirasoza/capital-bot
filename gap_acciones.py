#!/usr/bin/env python3
"""Continuacion de SALTOS (gap) diarios en acciones CFD de capital.com (idea del video: una noticia
produce un salto y el movimiento sigue). Velas DIARIAS bid/ask, 23 acciones con spread <=0.3%.
Senal: apertura con gap |O/C_prev - 1| >= G% y >= 1.5 x ATR%. Entrada a la apertura (ask/bid) con
desliz 0.1%, o al cierre del dia del gap. Salida: a los N dias al cierre, o trailing k x ATR, o stop.
Costos: spread real de cada accion + 0.02%/noche. Dos mitades (2022-24 | 2024-26). Resultados en %."""
import time, statistics
from datetime import datetime
import capital_client as cc
STOCKS=["MU","TSLA","AMD","AAPL","GS","AMZN","MCD","NVDA","GOOGL","META","MSFT","COST","AVGO","LLY","INTC","ORCL","PLTR","BABA","WMT","NFLX","UNH","JPM","QCOM"]
h=cc.login(); DATA={}
for e in STOCKS:
    P=cc.get(h,f"/api/v1/prices/{e}?resolution=DAY&max=1000").json().get("prices",[]); P.sort(key=lambda p:p["snapshotTimeUTC"])
    m=lambda x:(x["bid"]+x["ask"])/2
    DATA[e]={"T":[datetime.fromisoformat(p["snapshotTimeUTC"].replace("Z","")) for p in P],
             "O":[m(p["openPrice"]) for p in P],"H":[m(p["highPrice"]) for p in P],"L":[m(p["lowPrice"]) for p in P],"C":[m(p["closePrice"]) for p in P],
             "spr":[(p["closePrice"]["ask"]-p["closePrice"]["bid"])/m(p["closePrice"]) for p in P]}
    time.sleep(0.1)
print(f"{len(DATA)} acciones, {sum(len(d['C']) for d in DATA.values())} velas diarias | {min(d['T'][0] for d in DATA.values()):%Y-%m-%d} -> {max(d['T'][-1] for d in DATA.values()):%Y-%m-%d}")
MID=datetime(2024,10,15); SLIP=0.001; NIGHT=0.0002
def atrp(d):
    H,L,C=d["H"],d["L"],d["C"]; tr=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,len(C))]
    out=[None]*len(C); p=sum(tr[:14])/14; out[13]=p/C[13]
    for i in range(14,len(C)): p=(p*13+tr[i])/14; out[i]=p/C[i]
    return out
def sim(G,mode,entry,exit_,p,sides):
    tr=[]
    for e,d in DATA.items():
        O,H,L,C,T=d["O"],d["H"],d["L"],d["C"],d["T"]; A=atrp(d); n=len(C); t=15
        while t<n-1:
            g=O[t]/C[t-1]-1; a=A[t-1]
            if a and G<=abs(g)<=0.25 and abs(g)>=1.0*a:
                side=(1 if g>0 else -1)*(1 if mode=="sigue" else -1)
                if (side==1 and "long" not in sides) or (side==-1 and "short" not in sides): t+=1; continue
                e0=O[t] if entry=="apertura" else C[t]; cost=d["spr"][t]+SLIP; t0=t if entry=="apertura" else t+1
                ex=None; days=0
                if exit_=="dias":
                    k=min(t0+p-1,n-1); ex=C[k]; days=k-t0+1
                else:
                    ext=e0; stop=e0*(1-side*p*a); k=t0
                    while k<n:
                        if side==1 and L[k]<=stop: ex=stop; break
                        if side==-1 and H[k]>=stop: ex=stop; break
                        ext=max(ext,H[k]) if side==1 else min(ext,L[k]); stop=max(stop,ext*(1-p*a)) if side==1 else min(stop,ext*(1+p*a)); k+=1
                    if ex is None: ex=C[n-1]; k=n-1
                    days=k-t0+1
                r=side*(ex/e0-1)-cost-NIGHT*days
                tr.append({"r":r,"t":T[t],"side":side,"days":days}); t=t0+days
            else: t+=1
    return tr
def st(tr):
    if len(tr)<20: return None
    w=[x["r"] for x in tr if x["r"]>0]; l=[-x["r"] for x in tr if x["r"]<=0]
    return len(tr),100*sum(x["r"] for x in tr),100*statistics.mean(x["r"] for x in tr),(sum(w)/sum(l) if l else 9),100*len(w)/len(tr)
print(f"{'variante':<44} | {'2022-24: n sum% med% PF acc':^30} | {'2024-26: n sum% med% PF acc':^30}")
def row(name,**kw):
    tr=sim(**kw); a=st([x for x in tr if x["t"]<MID]); b=st([x for x in tr if x["t"]>=MID])
    if not a or not b: print(f"{name:<44} pocos trades"); return
    ok=" <<<" if a[1]>0 and b[1]>0 and a[3]>1.15 and b[3]>1.15 else ""
    print(f"{name:<44} | {a[0]:>4} {a[1]:>+6.0f} {a[2]:>+5.2f} {a[3]:>4.2f} {a[4]:>3.0f}% | {b[0]:>4} {b[1]:>+6.0f} {b[2]:>+5.2f} {b[3]:>4.2f} {b[4]:>3.0f}%{ok}")
for G in (0.03,0.05):
    print(f"-- gap >= {int(G*100)}% --")
    for mode in ("sigue","contra"):
        for entry in ("apertura","cierre"):
            for exit_,p in (("dias",1),("dias",3),("dias",5),("dias",10),("trail",2.0),("trail",3.0)):
                row(f"{mode} {entry} {exit_}{p} 2 lados",G=G,mode=mode,entry=entry,exit_=exit_,p=p,sides=("long","short"))
print("-- por lado, gap>=5%, sigue, cierre --")
for sides in (("long",),("short",)):
    for exit_,p in (("dias",3),("dias",10),("trail",3.0)): row(f"sigue cierre {exit_}{p} solo {sides[0]}",G=0.05,mode="sigue",entry="cierre",exit_=exit_,p=p,sides=sides)
print("\n-- CONTRA el gap, apertura: meseta del trailing y lados --")
for G in (0.03,0.05):
    for p in (2.0,2.5,3.0,4.0,5.0): row(f"gap>={int(G*100)}% contra apertura trail{p}",G=G,mode="contra",entry="apertura",exit_="trail",p=p,sides=("long","short"))
for sides in (("long",),("short",)):
    for p in (3.0,4.0): row(f"gap>=3% contra apertura trail{p} solo {sides[0]}",G=0.03,mode="contra",entry="apertura",exit_="trail",p=p,sides=sides)
tr=sim(G=0.03,mode="contra",entry="apertura",exit_="trail",p=3.0,sides=("long","short"))
print(f"\ngap>=3% contra trail3: {len(tr)} trades | dias medios en posicion {statistics.mean(x['days'] for x in tr):.1f} | mediana {statistics.median(x['days'] for x in tr):.0f} | max {max(x['days'] for x in tr)} | mejor {100*max(x['r'] for x in tr):+.1f}% peor {100*min(x['r'] for x in tr):+.1f}% | top5 = {100*sum(sorted([x['r'] for x in tr],reverse=True)[:5]):+.0f}% de {100*sum(x['r'] for x in tr):+.0f}%")
by={}
for x in tr: by[x['t'].year]=by.get(x['t'].year,0)+x['r']
print("por anio:",{k:f"{100*v:+.0f}%" for k,v in sorted(by.items())})
