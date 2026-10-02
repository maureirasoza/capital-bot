#!/usr/bin/env python3
"""Regla 'asegurar f% de la ganancia maxima cuando supera k x ATR' (el trailing sigue activo),
en unidades de ATR para poder cruzarla entre instrumentos: US500, US30, Bollinger oro, US100."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br
def prep(O,H,L,C,T,mod,WIN=300):
    n=len(C); sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=mod.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    return O,H,L,C,T,sig,atrs
def sim(D,trail,SPREAD,k=None,f=None,WIN=300):
    O,H,L,C,T,sig,atrs=D; n=len(C); tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD}); pos=None
            else:
                sgn=1 if s=='long' else -1
                pos['extreme']=max(pos['extreme'],H[t]) if s=='long' else min(pos['extreme'],L[t])
                mfe=sgn*(pos['extreme']-pos['entry']); cand=pos['extreme']-sgn*pos['dist']
                if k and mfe>=k*pos['atr']:
                    lock=pos['entry']+sgn*f*mfe; cand=max(cand,lock) if s=='long' else min(cand,lock)
                pos['stop']=max(pos['stop'],cand) if s=='long' else min(pos['stop'],cand)
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'; c=C[t]; d=trail*a
        pos={'side':s,'entry':c,'dist':d,'atr':a,'extreme':c,'stop':c-d if s=='long' else c+d}
    return tr
def tabla(nombre,D,trail,SPREAD):
    b=br.stats(sim(D,trail,SPREAD),'net'); print(f"\n=== {nombre} | ACTUAL: {b[0]:+.0f} PF{b[2]:.2f} DD{b[3]:+.0f} tercios {b[4][0]:+.0f}/{b[4][1]:+.0f}/{b[4][2]:+.0f} R{b[5]} ===")
    print(f"{'umbral':>8} | " + ' | '.join(f"{'asegurar '+str(int(f*100))+'%':>24}" for f in (0.4,0.5,0.6)))
    mejores=0; tot_=0
    for k in (4,5,6,8):
        cells=[]
        for f in (0.4,0.5,0.6):
            r=br.stats(sim(D,trail,SPREAD,k,f),'net'); tot_+=1; mejores+= r[0]>b[0]
            cells.append(f"{r[0]:>+6.0f} ({r[0]-b[0]:>+5.0f}) PF{r[2]:.2f} R{r[5]}")
        print(f"{'+'+str(k)+'xATR':>8} | " + ' | '.join(f"{c:>24}" for c in cells))
    print(f"   -> mejoran al actual: {mejores}/{tot_}")
import bot_sp500 as sp, bot_us30 as us
O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300); tabla("US500 15m (trail 4x)",prep(O,H,L,C,T,sp),4.0,0.3)
O,H,L,C,T=br.fetch_capital('US30','MINUTE_15',300); tabla("US30 15m (trail 5x)",prep(O,H,L,C,T,us),5.0,1.0)
bg=br._import_bollinger(); (O,H,L,C,T),_=br._fetch_15m("GOLD","GC=F"); tabla("Bollinger oro 15m (trail 5x)",prep(O,H,L,C,T,bg),5.0,0.3)
O,H,L,C,T=br.fetch_capital('US100','MINUTE_15',300); tabla("US100 15m (motor sp500, trail 4x)",prep(O,H,L,C,T,sp),4.0,0.9)
