#!/usr/bin/env python3
"""RUPTURA FALLIDA (idea del video: 'el Nasdaq llego a un techo, no lo cruzo, vienen correcciones'):
en 1h, el cierre supera el maximo de N velas y dentro de M velas vuelve a cerrar por debajo -> CORTO
(simetrico para LARGO). Stop = extremo de la ruptura + k x ATR; salida trailing o TP en R.
Datos 1h 600d reales (modelo medio + spread; trailing -> sesgo pequeno). Dos mitades."""
import sys, statistics
import backtest_real as br
EP={"US500":0.3,"US30":1.0,"US100":0.9,"RTY":0.25,"NL25":0.05}
def rma(s,k):
    out=[None]*len(s); p=sum(s[:k])/k; out[k-1]=p
    for i in range(k,len(s)): p=(p*(k-1)+s[i])/k; out[i]=p
    return out
def run(epic,SPREAD):
    O,H,L,C,T=br.fetch_capital(epic,'HOUR',600); n=len(C)
    tr_=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=rma(tr_,14); mid=n//2
    def sim(N,M,k,exit_,p):
        trades=[]; pos=None; pend=None
        for t in range(N+2,n):
            if pos:
                s=pos['side']; ex=None
                if s=='short' and H[t]>=pos['stop']: ex=pos['stop']
                elif s=='long' and L[t]<=pos['stop']: ex=pos['stop']
                elif exit_=='tp':
                    if s=='short' and L[t]<=pos['tp']: ex=pos['tp']
                    elif s=='long' and H[t]>=pos['tp']: ex=pos['tp']
                if ex is not None:
                    g=(pos['entry']-ex) if s=='short' else (ex-pos['entry']); trades.append({'net':g-2*SPREAD,'t':t}); pos=None
                elif exit_=='trail':
                    if s=='short': pos['ext']=min(pos['ext'],L[t]); pos['stop']=min(pos['stop'],pos['ext']+p*pos['atr'])
                    else: pos['ext']=max(pos['ext'],H[t]); pos['stop']=max(pos['stop'],pos['ext']-p*pos['atr'])
                continue
            hh=max(H[t-N:t]); ll=min(L[t-N:t]); a=ATR[t]
            if not a: continue
            if pend:
                if t>pend['t0']+M: pend=None
                elif pend['dir']=='up' and C[t]<pend['lvl']:
                    risk=k*a; stop=pend['ext']+risk*0.5+0.0; e=C[t]
                    pos={'side':'short','entry':e,'stop':max(stop,e+risk),'atr':a,'ext':e,'tp':e-p*max(stop,e+risk-e) if exit_=='tp' else None}
                    if exit_=='tp': pos['tp']=e-p*(pos['stop']-e)
                    pend=None; continue
                elif pend['dir']=='down' and C[t]>pend['lvl']:
                    risk=k*a; stop=pend['ext']-risk*0.5; e=C[t]
                    pos={'side':'long','entry':e,'stop':min(stop,e-risk),'atr':a,'ext':e,'tp':None}
                    if exit_=='tp': pos['tp']=e+p*(e-pos['stop'])
                    pend=None; continue
                else:
                    if pend['dir']=='up': pend['ext']=max(pend['ext'],H[t])
                    else: pend['ext']=min(pend['ext'],L[t])
                    continue
            if C[t]>hh: pend={'dir':'up','lvl':hh,'t0':t,'ext':H[t]}
            elif C[t]<ll: pend={'dir':'down','lvl':ll,'t0':t,'ext':L[t]}
        return trades
    def st(tr):
        if len(tr)<15: return None
        tot=sum(x['net'] for x in tr); w=sum(x['net'] for x in tr if x['net']>0); l=-sum(x['net'] for x in tr if x['net']<=0)
        return len(tr),tot,(w/l if l else 9)
    rows=[]
    for N in (24,48,96,168):
        for M in (2,4,8):
            for k in (1.0,2.0):
                for exit_,p in (('trail',2.0),('trail',3.0),('trail',5.0),('tp',1.5),('tp',2.5)):
                    tr=sim(N,M,k,exit_,p); a=st([x for x in tr if x['t']<mid]); b=st([x for x in tr if x['t']>=mid])
                    if a and b: rows.append((a,b,f"N{N} M{M} k{k} {exit_}{p}"))
    ok=[r for r in rows if r[0][1]>0 and r[1][1]>0 and r[0][2]>1.15 and r[1][2]>1.15]
    weeks=(T[-1]-T[0]).days/7
    print(f"\n=== {epic} 1h: {len(rows)} variantes | positivas en AMBAS mitades con PF>1.15: {len(ok)} ({100*len(ok)/len(rows):.0f}%) ===")
    for a,b,name in sorted(ok,key=lambda r:-(r[0][2]+r[1][2]))[:5]:
        print(f"  {name:<22} mitad1 {a[0]:>3}tr {a[1]:>+7.0f} PF{a[2]:.2f} | mitad2 {b[0]:>3}tr {b[1]:>+7.0f} PF{b[2]:.2f} | {(a[0]+b[0])/weeks:.1f}/sem")
for e,s in EP.items():
    try: run(e,s)
    except SystemExit as ex: print(e,"sin datos",ex)
