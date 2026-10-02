#!/usr/bin/env python3
"""Trend oro: (a) efecto MARGINAL de ENT / EXIT / stop sobre toda la malla (no una celda elegida);
(b) fuera de muestra: bajar GOLD 1h 1000d y evaluar SOLO el tramo antiguo que la busqueda no vio."""
import sys, statistics, itertools
import backtest_real as br, bot_gold_trend as bt
O,H,L,C,T=br.fetch_capital('GOLD','HOUR',1000); n=len(C); WIN=br.WIN; SPREAD=0.3
print(f"{n} velas | {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}")
tr_=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=bt._rma(tr_,14)
def sim(a,b,ENT=15,EXIT=8,stop=5.0,slip=0.0):
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
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD-slip,'t':t}); pos=None; exited=True
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
        if pos is None and not exited and ATR[t]:
            s='long' if C[t]>hh else 'short' if C[t]<ll else None
            if s:
                d=stop*ATR[t]; pos={'side':s,'entry':C[t],'dist':d,'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d}
    return tr
def res(tr,a,b,k=3):
    if len(tr)<15: return None
    tot=sum(x['net'] for x in tr); w=sum(x['net'] for x in tr if x['net']>0); l=-sum(x['net'] for x in tr if x['net']<0)
    eq=pk=dd=0
    for x in tr: eq+=x['net']; pk=max(pk,eq); dd=min(dd,eq-pk)
    a=max(a,WIN); seg=[0.0]*k; span=(b-a)/k
    for x in tr: seg[min(k-1,int((x['t']-a)/span))]+=x['net']
    return dict(n=len(tr),tot=tot,pf=w/l if l else 9,dd=dd,seg=seg,pos=sum(1 for v in seg if v>0))
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=600)
A=(0,cut); B=(cut,n)
print(f"ANTIGUO (fuera de muestra): {T[max(WIN,0)]:%Y-%m-%d} -> {T[cut]:%Y-%m-%d} | RECIENTE (donde se busco): {T[cut]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}")
ENTS=(10,15,20,30,40,55,80,120); EXITS=(5,8,10,15,20,30); STOPS=(3.0,5.0,7.0,10.0)
grid={}
for ENT,EXIT,stop in itertools.product(ENTS,EXITS,STOPS):
    if EXIT>=ENT: continue
    grid[(ENT,EXIT,stop)]=(res(sim(*A,ENT,EXIT,stop),*A),res(sim(*B,ENT,EXIT,stop),*B,k=6))
def marg(name,idx,vals):
    print(f"\n-- efecto marginal de {name} (mediana sobre todas las demas combinaciones) --")
    print(f"{name:>6} | {'ANTIGUO: neto':>13} {'PF':>5} {'%comb>0':>8} | {'RECIENTE: neto':>14} {'PF':>5} {'tramos+/6':>9}")
    for v in vals:
        ra=[g[0] for k,g in grid.items() if k[idx]==v and g[0]]; rb=[g[1] for k,g in grid.items() if k[idx]==v and g[1]]
        if not ra or not rb: continue
        print(f"{v:>6} | {statistics.median(r['tot'] for r in ra):>+13.0f} {statistics.median(r['pf'] for r in ra):>5.2f} {100*sum(1 for r in ra if r['tot']>0)/len(ra):>7.0f}% | {statistics.median(r['tot'] for r in rb):>+14.0f} {statistics.median(r['pf'] for r in rb):>5.2f} {statistics.mean(r['pos'] for r in rb):>9.1f}")
marg("ENT",0,ENTS); marg("EXIT",1,EXITS); marg("stop",2,STOPS)
print("\n-- finalistas: ANTIGUO (nunca visto) | RECIENTE 600d --")
print(f"{'config':<22} | {'tr':>4} {'neto':>6} {'PF':>5} {'DD':>5} {'3 tercios':>17} | {'tr':>4} {'neto':>6} {'PF':>5} {'DD':>5} {'pos/6':>5}")
for k in ((15,8,5.0),(30,15,5.0),(30,15,3.0),(40,10,5.0),(55,8,5.0),(55,10,5.0),(80,5,5.0),(80,8,5.0),(80,10,5.0),(80,5,7.0),(120,8,5.0)):
    a,b=grid[k]
    if not a or not b: continue
    tag=" <- ACTUAL" if k==(15,8,5.0) else ""
    print(f"ENT{k[0]}/EXIT{k[1]} stop{k[2]:<4} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['dd']:>+5.0f} {a['seg'][0]:>+5.0f}/{a['seg'][1]:>+5.0f}/{a['seg'][2]:>+5.0f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['dd']:>+5.0f} {b['pos']:>5}{tag}")
print("\n-- desliz (todo el periodo): actual vs candidatas --")
for k in ((15,8,5.0),(55,8,5.0),(80,5,5.0),(80,8,5.0)):
    out=[]
    for sl in (0,0.5,1.0,2.0):
        r=res(sim(0,n,*k,slip=sl),0,n); out.append(f"{sl}: {r['tot']:>+6.0f} PF{r['pf']:.2f}")
    print(f"ENT{k[0]}/EXIT{k[1]} stop{k[2]} | "+' | '.join(out))
