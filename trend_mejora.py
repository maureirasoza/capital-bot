#!/usr/bin/env python3
"""Busqueda de mejoras para el bot ORO TREND (Donchian 2 lados, 1h) sobre GOLD 1h 600d REALES.
Simulador rapido equivalente a backtest_real.simulate (se verifica contra el real al inicio).
Dimensiones: ENT x EXIT x stop, lado, filtro de tendencia EMA, filtro de vela-spike, regimen de
volatilidad, salida por canal on/off. Criterio: sextos positivos (6 tramos de ~100d) + tercios."""
import sys, statistics, itertools
sys.argv=['x','--source','capital','--days','600']
import backtest_real as br, bot_gold_trend as bt
(O,H,L,C,T),_=br._fetch_1h(); n=len(C); WIN=br.WIN; SPREAD=0.3
# ATR global (RMA 14)
tr_=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]
ATR=bt._rma(tr_,14)
def ema(s,k):
    out=[s[0]]; a=2/(k+1)
    for x in s[1:]: out.append(x*a+out[-1]*(1-a))
    return out
EMA={k:ema(C,k) for k in (100,200)}
med=[None]*n; buf=[]
for i in range(n):
    if ATR[i]: buf.append(ATR[i])
    if len(buf)>300: buf.pop(0)
    med[i]=statistics.median(buf) if len(buf)>=50 else None
def sim(ENT=15,EXIT=8,stop=5.0,sides=('long','short'),ema_f=None,spike=None,vol=None,canal=True,ext=None):
    tr=[]; pos=None
    for t in range(WIN,n):
        hh=max(H[t-ENT:t]); ll=min(L[t-ENT:t])
        exited=False
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            elif canal and s=='long' and C[t]<min(L[t-EXIT:t]): ex=C[t]
            elif canal and s=='short' and C[t]>max(H[t-EXIT:t]): ex=C[t]
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD,'t':t,'side':s}); pos=None; exited=True
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
        if pos is None and not exited:
            a=ATR[t]; s=None
            if C[t]>hh: s='long'
            elif C[t]<ll: s='short'
            if not s or s not in sides or not a: continue
            if ema_f and ((s=='long' and C[t]<EMA[ema_f][t]) or (s=='short' and C[t]>EMA[ema_f][t])): continue
            if spike and (H[t]-L[t])>spike*ATR[t-1]: continue          # no perseguir velas-noticia
            if ext and abs(C[t]-(hh if s=='long' else ll))>ext*a: continue  # ruptura ya muy extendida
            if vol=='alta' and (med[t] is None or a<med[t]): continue
            if vol=='baja' and (med[t] is None or a>=med[t]): continue
            d=stop*a
            pos={'side':s,'entry':C[t],'dist':d,'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d}
    return tr
def seg(tr,k):
    out=[0.0]*k; span=(n-WIN)/k
    for x in tr: out[min(k-1,int((x['t']-WIN)/span))]+=x['net']
    return out
def res(tr):
    if len(tr)<30: return None
    tot=sum(x['net'] for x in tr); w=[x['net'] for x in tr if x['net']>0]; l=[-x['net'] for x in tr if x['net']<0]
    pf=sum(w)/sum(l) if l else 9; eq=0; pk=0; dd=0
    for x in tr:
        eq+=x['net']; pk=max(pk,eq); dd=min(dd,eq-pk)
    s6=seg(tr,6); s3=seg(tr,3)
    return dict(n=len(tr),tot=tot,pf=pf,acc=100*len(w)/len(tr),dd=dd,s3=s3,s6=s6,pos6=sum(1 for v in s6 if v>0),rob=sum(1 for v in s3 if v>0))
weeks=(T[-1]-T[WIN]).days/7
def line(name,r):
    print(f"{name:<46} {r['n']/weeks:>4.1f} {r['tot']:>+6.0f} {r['pf']:>5.2f} {r['acc']:>3.0f}% {r['dd']:>+5.0f} {r['s3'][0]:>+5.0f}/{r['s3'][1]:>+5.0f}/{r['s3'][2]:>+5.0f} R{r['rob']} | "+' '.join(f"{v:>+5.0f}" for v in r['s6'])+f" | {r['pos6']}/6")
hdr=f"{'config':<46} {'tr/s':>4} {'NETO':>6} {'PF':>5} {'acc':>4} {'DD':>5} {'3 tercios':>17}    | {'6 tramos (~100d c/u)':<35} | pos"
# verificacion contra el simulador REAL
real=br.simulate(O,H,L,C,T,5.0); rr=br.stats(real,'net'); b=res(sim())
print(f"VERIFICACION: real {len(real)} tr {rr[0]:+.1f} PF{rr[2]:.2f} | rapido {b['n']} tr {b['tot']:+.1f} PF{b['pf']:.2f}")
print(f"\nperiodo {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}\n"+hdr); print('-'*len(hdr)); line("ACTUAL 15/8 stop5 2lados canal",b)
print("\n== 1) una palanca a la vez sobre la config actual =="); print(hdr)
for nm,kw in (("solo largos",dict(sides=('long',))),("solo cortos",dict(sides=('short',))),("sin salida por canal",dict(canal=False)),
              ("filtro EMA100",dict(ema_f=100)),("filtro EMA200",dict(ema_f=200)),("sin velas-spike >2xATR",dict(spike=2.0)),("sin velas-spike >3xATR",dict(spike=3.0)),
              ("ruptura extendida <1xATR",dict(ext=1.0)),("ruptura extendida <0.5xATR",dict(ext=0.5)),("solo volatilidad ALTA",dict(vol='alta')),("solo volatilidad BAJA",dict(vol='baja')),
              ("stop 3x",dict(stop=3.0)),("stop 7x",dict(stop=7.0)),("stop 10x",dict(stop=10.0))):
    r=res(sim(**kw)); 
    if r: line(nm,r)
print("\n== 2) malla ENT x EXIT x stop (2 lados, con canal): solo las que tienen >=5/6 tramos positivos =="); print(hdr)
rows=[]
for ENT,EXIT,stop in itertools.product((10,15,20,30,40,55,80),(5,8,10,15,20,30),(3.0,5.0,7.0,10.0)):
    if EXIT>=ENT: continue
    r=res(sim(ENT=ENT,EXIT=EXIT,stop=stop))
    if r: rows.append((r['pos6'],r['pf'],f"ENT{ENT}/EXIT{EXIT} stop{stop}",r))
print(f"   {len(rows)} combinaciones | con 6/6: {sum(1 for x in rows if x[0]==6)} | con 5/6: {sum(1 for x in rows if x[0]==5)} | con >=4/6: {sum(1 for x in rows if x[0]>=4)}")
for p6,pf,nm,r in sorted(rows,key=lambda x:(-x[0],-x[1]))[:14]: line(nm,r)
print("\n== 3) mismas mallas con filtro EMA200 y con solo-largos: conteo de robustez ==")
for lab,kw in (("+ filtro EMA200",dict(ema_f=200)),("+ filtro EMA100",dict(ema_f=100)),("solo largos",dict(sides=('long',))),("+ sin spike>2x",dict(spike=2.0))):
    rs=[]
    for ENT,EXIT,stop in itertools.product((10,15,20,30,40,55,80),(5,8,10,15,20,30),(3.0,5.0,7.0,10.0)):
        if EXIT>=ENT: continue
        r=res(sim(ENT=ENT,EXIT=EXIT,stop=stop,**kw))
        if r: rs.append((r['pos6'],r['pf'],f"ENT{ENT}/EXIT{EXIT} stop{stop} {lab}",r))
    print(f"{lab:<18}: {len(rs)} comb | 6/6: {sum(1 for x in rs if x[0]==6)} | 5/6: {sum(1 for x in rs if x[0]==5)} | PF mediano {statistics.median(x[1] for x in rs):.2f}")
    for p6,pf,nm,r in sorted(rs,key=lambda x:(-x[0],-x[1]))[:4]: line(nm,r)
