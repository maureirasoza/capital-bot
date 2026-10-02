#!/usr/bin/env python3
"""Trend oro: filtros sobre la config actual (y sobre canal largo) evaluados en el tramo ANTIGUO
(2024, fuera de muestra), el RECIENTE (600d) y el TOTAL de 1000d de GOLD 1h real."""
import statistics
import backtest_real as br, bot_gold_trend as bt
O,H,L,C,T=br.fetch_capital('GOLD','HOUR',1000); n=len(C); WIN=br.WIN; SPREAD=0.3
tr_=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=bt._rma(tr_,14)
def ema(s,k):
    out=[s[0]]; a=2/(k+1)
    for x in s[1:]: out.append(x*a+out[-1]*(1-a))
    return out
EMA={k:ema(C,k) for k in (100,200)}
def sim(a,b,ENT=15,EXIT=8,stop=5.0,sides=('long','short'),ema_f=None,spike=None,ext=None):
    tr=[]; pos=None
    for t in range(max(a,WIN),b):
        hh=max(H[t-ENT:t]); ll=min(L[t-ENT:t]); exited=False
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            elif s=='long' and C[t]<min(L[t-EXIT:t]): ex=C[t]
            elif s=='short' and C[t]>max(H[t-EXIT:t]): ex=C[t]
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD,'t':t,'side':s}); pos=None; exited=True
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
        if pos is None and not exited and ATR[t]:
            s='long' if C[t]>hh else 'short' if C[t]<ll else None
            if not s or s not in sides: continue
            if ema_f and ((s=='long' and C[t]<EMA[ema_f][t]) or (s=='short' and C[t]>EMA[ema_f][t])): continue
            if spike and (H[t]-L[t])>spike*ATR[t-1]: continue
            if ext and abs(C[t]-(hh if s=='long' else ll))>ext*ATR[t]: continue
            d=stop*ATR[t]; pos={'side':s,'entry':C[t],'dist':d,'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d}
    return tr
def st(tr):
    tot=sum(x['net'] for x in tr); w=sum(x['net'] for x in tr if x['net']>0); l=-sum(x['net'] for x in tr if x['net']<0)
    eq=pk=dd=0
    for x in tr: eq+=x['net']; pk=max(pk,eq); dd=min(dd,eq-pk)
    return len(tr),tot,(w/l if l else 9),dd
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=600)
print(f"{'variante':<40} | {'ANTIGUO 2024 (no visto)':^26} | {'RECIENTE 600d':^26} | {'TOTAL 1000d':^26}")
print(f"{'':<40} | {'tr':>4} {'neto':>6} {'PF':>5} {'DD':>6} | {'tr':>4} {'neto':>6} {'PF':>5} {'DD':>6} | {'tr':>4} {'neto':>6} {'PF':>5} {'DD':>6}")
V=[("ACTUAL 15/8 stop5",{}),("  + filtro EMA200",dict(ema_f=200)),("  + filtro EMA100",dict(ema_f=100)),("  + sin vela-spike >3xATR",dict(spike=3.0)),("  + sin vela-spike >2xATR",dict(spike=2.0)),
   ("  + ruptura no extendida (<0.5xATR)",dict(ext=0.5)),("  + ruptura no extendida (<1xATR)",dict(ext=1.0)),("  solo largos",dict(sides=('long',))),("  solo largos + EMA200",dict(sides=('long',),ema_f=200)),
   ("canal 55/8 stop5",dict(ENT=55)),("  + filtro EMA200",dict(ENT=55,ema_f=200)),("canal 80/8 stop5",dict(ENT=80)),("  + filtro EMA200",dict(ENT=80,ema_f=200)),("canal 120/8 stop5",dict(ENT=120)),("canal 30/15 stop5",dict(ENT=30,EXIT=15))]
for nm,kw in V:
    a=st(sim(0,cut,**kw)); b=st(sim(cut,n,**kw)); c=st(sim(0,n,**kw))
    print(f"{nm:<40} | {a[0]:>4} {a[1]:>+6.0f} {a[2]:>5.2f} {a[3]:>+6.0f} | {b[0]:>4} {b[1]:>+6.0f} {b[2]:>5.2f} {b[3]:>+6.0f} | {c[0]:>4} {c[1]:>+6.0f} {c[2]:>5.2f} {c[3]:>+6.0f}")
# por año calendario, config actual
print("\nconfig ACTUAL por trimestre (pts netos):")
tr=sim(0,n); q={}
for x in tr:
    k=f"{T[x['t']].year}-T{(T[x['t']].month-1)//3+1}"; q[k]=q.get(k,0)+x['net']
print('  '+' | '.join(f"{k} {v:+.0f}" for k,v in sorted(q.items())))
print(f"  trimestres positivos: {sum(1 for v in q.values() if v>0)}/{len(q)}")
