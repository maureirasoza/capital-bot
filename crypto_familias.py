#!/usr/bin/env python3
"""Familias de estrategia en BTC y ETH (diario y 4h), costos reales. Muestra por anio y compras/ventas."""
import sys, itertools
import crypto_lab as cl
RES=sys.argv[1] if len(sys.argv)>1 else "DAY"; DAYS=2200
data={e:cl.load(e,RES,DAYS) for e in ("BTCUSD","ETHUSD")}
for e,d in data.items():
    bh=cl.buyhold(d); spr=[ (a-b)/((a+b)/2) for a,b in zip(d["Ca"],d["Cb"])]
    yrs=sorted(bh); print(f"{e} {RES}: {d['n']} velas {d['T'][0]:%Y-%m-%d} -> {d['T'][-1]:%Y-%m-%d} | spread medio {100*sum(spr)/len(spr):.3f}% | comprar-y-mantener %/anio: "+" ".join(f"{y}:{bh[y]:+.0f}" for y in yrs))
YEARS=sorted(cl.buyhold(data["BTCUSD"]))
def donchian(d,N,X):
    H,L,C=d["H"],d["L"],d["C"]; n=d["n"]; s=[None]*n; x=[None]*n
    for t in range(N,n):
        if C[t]>max(H[t-N:t]): s[t]="L"
        elif C[t]<min(L[t-N:t]): s[t]="S"
        if t>=X:
            if C[t]<min(L[t-X:t]): x[t]="XL"
            elif C[t]>max(H[t-X:t]): x[t]="XS"
    return s,x
def emax(d,f,sl):
    C=d["C"]; ef,es=cl.ema(C,f),cl.ema(C,sl); n=d["n"]; s=[None]*n
    for t in range(1,n):
        if ef[t]>es[t] and ef[t-1]<=es[t-1]: s[t]="L"
        elif ef[t]<es[t] and ef[t-1]>=es[t-1]: s[t]="S"
    return s
def tsmom(d,Lb):
    C=d["C"]; n=d["n"]; s=[None]*n
    for t in range(Lb,n): s[t]="L" if C[t]>C[t-Lb] else "S"
    return s
def atrbk(d,k):
    C,A=d["C"],d["ATR"]; n=d["n"]; s=[None]*n
    for t in range(15,n):
        if A[t-1] and C[t]-C[t-1]>k*A[t-1]: s[t]="L"
        elif A[t-1] and C[t-1]-C[t]>k*A[t-1]: s[t]="S"
    return s
def bbrsi(d,bl,bm,lo,hi):
    C=d["C"]; n=d["n"]; s=[None]*n
    g=[0]+[max(C[i]-C[i-1],0) for i in range(1,n)]; l=[0]+[max(C[i-1]-C[i],0) for i in range(1,n)]
    def rma(x,k):
        o=[None]*len(x); p=sum(x[1:k+1])/k; o[k]=p
        for i in range(k+1,len(x)): p=(p*(k-1)+x[i])/k; o[i]=p
        return o
    ag,al=rma(g,14),rma(l,14); rsi=[None if ag[i] is None else (100 if al[i]==0 else 100-100/(1+ag[i]/al[i])) for i in range(n)]
    prev=None
    for t in range(bl,n):
        w=C[t-bl+1:t+1]; m=sum(w)/bl; sd=(sum((x-m)**2 for x in w)/bl)**0.5
        cl_=C[t]<m-bm*sd and rsi[t] is not None and rsi[t]<lo; cs=C[t]>m+bm*sd and rsi[t] is not None and rsi[t]>hi
        cur="L" if cl_ else ("S" if cs else None)
        s[t]=cur if cur and cur!=prev else None; prev=cur
    return s
rows=[]
def test(name,sig,trail=None,exitsig=None,sides=("L","S")):
    out={}
    for e,d in data.items(): out[e]=cl.stats(cl.run(d,sig[e],trail,exitsig[e] if exitsig else None,sides))
    rows.append((name,out))
F={}
for e,d in data.items(): F[e]={}
# familias
for N,X in ((20,10),(55,20),(100,50)):
    sg={e:donchian(d,N,X) for e,d in data.items()}
    for tr_ in (None,3.0,5.0):
        for sides,lab in ((("L","S"),"2L"),(("L",),"L")):
            test(f"DONCH {N}/{X} trail{tr_} {lab}",{e:sg[e][0] for e in data},tr_,{e:sg[e][1] for e in data},sides)
for f,sl in ((10,30),(20,50),(50,200)):
    sg={e:emax(d,f,sl) for e,d in data.items()}
    for tr_ in (None,4.0):
        for sides,lab in ((("L","S"),"2L"),(("L",),"L")): test(f"EMAX {f}/{sl} trail{tr_} {lab}",sg,tr_,None,sides)
for Lb in (20,60,120):
    sg={e:tsmom(d,Lb) for e,d in data.items()}
    for sides,lab in ((("L","S"),"2L"),(("L",),"L")): test(f"TSMOM {Lb} {lab}",sg,None,None,sides)
for k in (1.5,2.0,3.0):
    sg={e:atrbk(d,k) for e,d in data.items()}
    for tr_ in (2.0,3.0,5.0): test(f"ATRBK k{k} trail{tr_} 2L",sg,tr_,None)
for bl,bm,lo,hi in ((20,2.0,30,70),(20,2.0,35,65)):
    sg={e:bbrsi(d,bl,bm,lo,hi) for e,d in data.items()}
    for tr_ in (2.0,3.0,5.0): test(f"BBRSI {bl}/{bm} {lo}/{hi} trail{tr_} 2L",sg,tr_,None)
# reporte: candidatos = positivos en BTC y ETH, y positivos en >= (anios-2) anios en ambos, y 2022 >= 0 en ambos
def yrs_pos(s): return sum(1 for y in YEARS if s["years"].get(y,0)>0)
print(f"\n{'estrategia':<34} | {'BTC: tot% PF DD% L% S% anios+':^40} | {'ETH: tot% PF DD% L% S% anios+':^40} | 2022 B/E")
good=[]
for name,o in rows:
    b,e_=o["BTCUSD"],o["ETHUSD"]
    flag=b["tot"]>0 and e_["tot"]>0 and b["years"].get(2022,0)>=0 and e_["years"].get(2022,0)>=0 and yrs_pos(b)>=len(YEARS)-2 and yrs_pos(e_)>=len(YEARS)-2
    if flag: good.append(name)
    print(f"{name:<34} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>4.2f} {b['dd']:>+5.0f} {b['L']:>+5.0f} {b['S']:>+5.0f} {yrs_pos(b)}/{len(YEARS)} | {e_['n']:>4} {e_['tot']:>+6.0f} {e_['pf']:>4.2f} {e_['dd']:>+5.0f} {e_['L']:>+5.0f} {e_['S']:>+5.0f} {yrs_pos(e_)}/{len(YEARS)} | {b['years'].get(2022,0):+.0f}/{e_['years'].get(2022,0):+.0f}{'  <<<' if flag else ''}")
print(f"\ncandidatos (BTC y ETH positivos, 2022>=0 en ambos, casi todos los anios +): {len(good)} de {len(rows)}")
for g in good:
    o=dict(rows)[g]; print(f"  {g}: BTC por anio "+" ".join(f"{y}:{o['BTCUSD']['years'].get(y,0):+.0f}" for y in YEARS)+" | ETH "+" ".join(f"{y}:{o['ETHUSD']['years'].get(y,0):+.0f}" for y in YEARS))
print("\n== TOP 12 por min(PF BTC, PF ETH) con >=20 trades en cada uno: detalle por anio ==")
cand=[(min(o["BTCUSD"]["pf"],o["ETHUSD"]["pf"]),name,o) for name,o in rows if o["BTCUSD"]["n"]>=20 and o["ETHUSD"]["n"]>=20]
for pf,name,o in sorted(cand,reverse=True)[:12]:
    for e in ("BTCUSD","ETHUSD"):
        s=o[e]; print(f"  {name:<32} {e[:3]} PF{s['pf']:.2f} DD{s['dd']:+.0f} | "+" ".join(f"{y}:{s['years'].get(y,0):+5.0f}" for y in YEARS)+f" | dias/op {s['days']:.0f}")
