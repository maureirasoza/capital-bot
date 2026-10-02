#!/usr/bin/env python3
"""Trend oro: PIRAMIDAR a fondo sobre base + EMA200 (GOLD 1h 1000d reales, ANTIGUO 2024 vs RECIENTE).
 - modo 'nivel': la unidad extra entra en el nivel exacto dentro de la vela (orden stop en reposo)
 - modo 'cierre': entra al CIERRE de la vela 1h si el cierre ya supero el nivel (lo que puede hacer
   el bot con cron horario, sin ordenes en reposo)
Compara contra simplemente DUPLICAR el tamano (misma exposicion maxima), y mide riesgo."""
import backtest_real as br, bot_gold_trend as bt
O,H,L,C,T=br.fetch_capital('GOLD','HOUR',1000); n=len(C); WIN=400; SPREAD=0.3
TR=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=bt._rma(TR,14)
def ema(s,k):
    out=[s[0]]; a=2/(k+1)
    for x in s[1:]: out.append(x*a+out[-1]*(1-a))
    return out
E200=ema(C,200); cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=600)
def sim(a,b,ENT=15,EXIT=8,stop=5.0,emaf=True,pyr=None,mode='nivel',slip_add=0.0,hold=False,units0=1):
    tr=[]; pos=None; pend=None
    def close(t,px):
        nonlocal pos
        sgn=1 if pos['side']=='long' else -1
        net=sum(sgn*(px-e)-2*SPREAD for e in pos['entries'])-slip_add*(len(pos['entries'])-units0)
        tr.append({'net':net,'t':t,'u':len(pos['entries'])}); pos=None
    for t in range(max(a,WIN),b):
        hh=max(H[t-ENT:t]); ll=min(L[t-ENT:t]); exited=False
        if pos:
            s=pos['side']; sg=1 if s=='long' else -1
            if s=='long' and L[t]<=pos['stop']: close(t,pos['stop']); exited=True
            elif s=='short' and H[t]>=pos['stop']: close(t,pos['stop']); exited=True
            elif s=='long' and C[t]<min(L[t-EXIT:t]): close(t,C[t]); exited=True
            elif s=='short' and C[t]>max(H[t-EXIT:t]): close(t,C[t]); exited=True
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
                if pyr and pos['adds']<pyr[1]-1:
                    lvl=pos['last']+sg*pyr[0]*pos['atr']
                    if mode=='nivel':
                        if (s=='long' and H[t]>=lvl) or (s=='short' and L[t]<=lvl):
                            px=max(lvl,O[t]) if s=='long' else min(lvl,O[t]); pos['entries']+= [px]*units0; pos['last']=px; pos['adds']+=1
                    else:
                        if (s=='long' and C[t]>=lvl) or (s=='short' and C[t]<=lvl):
                            pos['entries']+= [C[t]]*units0; pos['last']=C[t]; pos['adds']+=1
        if pos is None and pend and not exited:
            s=pend['side']; ok=(C[t]>pend['lvl']) if s=='long' else (C[t]<pend['lvl']); pend=None
            if ok:
                d=stop*ATR[t]; pos={'side':s,'entries':[C[t]]*units0,'last':C[t],'adds':0,'dist':d,'atr':ATR[t],'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d}
            continue
        if pos is None and not exited and ATR[t]:
            s='long' if C[t]>hh else 'short' if C[t]<ll else None
            if not s: continue
            if emaf and ((s=='long' and C[t]<E200[t]) or (s=='short' and C[t]>E200[t])): continue
            if hold: pend={'side':s,'lvl':hh if s=='long' else ll}; continue
            d=stop*ATR[t]; pos={'side':s,'entries':[C[t]]*units0,'last':C[t],'adds':0,'dist':d,'atr':ATR[t],'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d}
    return tr
def st(tr):
    tot=sum(x['net'] for x in tr); w=sum(x['net'] for x in tr if x['net']>0); l=-sum(x['net'] for x in tr if x['net']<0); eq=pk=dd=0
    for x in tr: eq+=x['net']; pk=max(pk,eq); dd=min(dd,eq-pk)
    return len(tr),tot,(w/l if l else 9),dd,min(x['net'] for x in tr)
def row(name,**kw):
    a=st(sim(0,cut,**kw)); b=st(sim(cut,n,**kw)); c=st(sim(0,n,**kw))
    full=sim(0,n,**kw); addp=100*sum(1 for x in full if x['u']>kw.get('units0',1))/len(full)
    print(f"{name:<40} | {a[1]:>+6.0f} {a[2]:>5.2f} {a[3]:>+6.0f} | {b[1]:>+6.0f} {b[2]:>5.2f} {b[3]:>+6.0f} | {c[1]:>+6.0f} {c[2]:>5.2f} {c[3]:>+6.0f} {c[1]/abs(c[3]):>5.1f} {c[4]:>+6.0f} {addp:>4.0f}%")
print(f"{'variante (todas con filtro EMA200)':<40} | {'ANTIGUO neto PF DD':^19} | {'RECIENTE neto PF DD':^19} | {'TOTAL neto PF DD':^19} {'n/DD':>5} {'peor':>6} {'%pir':>5}")
row("1 unidad (base + EMA200)")
row("2 unidades fijas (doble tamano)",units0=2)
print("-- piramide, entrada en el NIVEL exacto (orden en reposo) --")
for k in (1.0,1.5,2.0,2.5,3.0,4.0): row(f"  +1 cada {k}xATR, max 2",pyr=(k,2))
for k in (1.5,2.0,3.0): row(f"  +1 cada {k}xATR, max 3",pyr=(k,3))
print("-- piramide, entrada al CIERRE de la vela 1h (lo que hace el bot con cron horario) --")
for k in (1.0,1.5,2.0,2.5,3.0,4.0): row(f"  +1 cada {k}xATR, max 2 (cierre)",pyr=(k,2),mode='cierre')
for k in (1.5,2.0,3.0): row(f"  +1 cada {k}xATR, max 3 (cierre)",pyr=(k,3),mode='cierre')
print("-- sensibilidad: desliz extra en cada unidad agregada (modo cierre, 2xATR max 2) --")
for sl in (0.5,1.0,2.0): row(f"  desliz {sl} pts por unidad extra",pyr=(2.0,2),mode='cierre',slip_add=sl)
print("-- sin filtro EMA (para ver si la piramide depende de el) y con espera de 1 vela --")
row("  sin EMA: 1 unidad",emaf=False); row("  sin EMA: +1 cada 2xATR max 2 (cierre)",emaf=False,pyr=(2.0,2),mode='cierre')
row("  EMA + esperar 1 vela: 1 unidad",hold=True); row("  EMA + esperar 1 vela + piramide 2x max 2",hold=True,pyr=(2.0,2),mode='cierre')
