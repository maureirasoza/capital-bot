#!/usr/bin/env python3
"""Trailing PROGRESIVO: arranca en el trailing del bot (4x o 5x ATR) y, cuando la ganancia
maxima alcanzada supera k x ATR, la distancia del trailing se aprieta a m x ATR.
Se prueba en SP500, US30 y Bollinger oro (mismo motor) sobre datos reales congelados."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br
def prep(O,H,L,C,T,mod,WIN=300):
    n=len(C); sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=mod.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    return O,H,L,C,T,sig,atrs
def sim(D,trail,SPREAD,k=None,m=None,WIN=300):
    O,H,L,C,T,sig,atrs=D; n=len(C); tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD}); pos=None
            else:
                if s=='long':
                    pos['extreme']=max(pos['extreme'],H[t])
                    d=m*pos['atr'] if (k and pos['extreme']-pos['entry']>=k*pos['atr']) else pos['dist']
                    pos['stop']=max(pos['stop'],pos['extreme']-d)
                else:
                    pos['extreme']=min(pos['extreme'],L[t])
                    d=m*pos['atr'] if (k and pos['entry']-pos['extreme']>=k*pos['atr']) else pos['dist']
                    pos['stop']=min(pos['stop'],pos['extreme']+d)
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'; c=C[t]; d=trail*a
        pos={'side':s,'entry':c,'dist':d,'atr':a,'extreme':c,'stop':c-d if s=='long' else c+d}
    return tr
def tabla(nombre,D,trail,SPREAD):
    print(f"\n=== {nombre} (trailing base {trail}x) ===")
    hdr=f"{'variante':<34} {'#tr':>4} {'NETO':>7} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>20} {'ROB':>3}"; print(hdr); print('-'*len(hdr))
    def row(n_,tr):
        tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); print(f"{n_:<34} {len(tr):>4} {tot:>+7.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} {rob:>3}")
    row("ACTUAL (trailing fijo)",sim(D,trail,SPREAD))
    for k in (3,5,8):
        for m in (1.5,2.0,3.0):
            if m>=trail: continue
            row(f"tras +{k}xATR apretar a {m}xATR",sim(D,trail,SPREAD,k,m))
import bot_sp500 as sp, bot_us30 as us
O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300); tabla("SP500 15m 300d",prep(O,H,L,C,T,sp),sp.TRAIL_ATR,0.3)
O,H,L,C,T=br.fetch_capital('US30','MINUTE_15',300); tabla("US30 15m 300d",prep(O,H,L,C,T,us),us.TRAIL_ATR,1.0)
bg=br._import_bollinger(); (O,H,L,C,T),_=br._fetch_15m("GOLD","GC=F"); tabla("Bollinger oro 15m 300d",prep(O,H,L,C,T,bg),bg.TRAIL_ATR,0.3)
