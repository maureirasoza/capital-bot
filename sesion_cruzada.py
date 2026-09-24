#!/usr/bin/env python3
"""Confirmacion cruzada del filtro de sesion (no entrar 12-20 UTC = horario contado de Wall St)
en OTROS instrumentos con el mismo motor de reversion: si el mecanismo es real, deberia mejorar
tambien el peor tercio de US30 (motor bot_us30) y US100 (motor sp500 como proxy)."""
import statistics
import backtest_real as br, bot_sp500 as sp, bot_us30 as us
def run(epic,res,days,mod,trail,SPREAD,WIN=300):
    O,H,L,C,T=br.fetch_capital(epic,res,days); n=len(C); weeks=(T[-1]-T[WIN]).days/7
    sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=mod.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    def sim(allow):
        tr=[]; pos=None
        for t in range(WIN,n):
            if pos:
                s=pos['side']; ex=None
                if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
                elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
                if ex is not None:
                    g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD}); pos=None
                else:
                    if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                    else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
                continue
            sd=sig[t]; a=atrs[t]
            if not sd or not a: continue
            h=T[t].hour+T[t].minute/60
            if not allow(h): continue
            s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
            pos={'side':s,'entry':c,'dist':d,'extreme':c,'stop':c-d if s=='long' else c+d}
        return tr
    hdr=f"{'filtro':<26} {'tr/s':>5} {'NETO':>7} {'PF':>5} {'maxDD':>6} {'3 tercios':>20} {'peor':>6}"; print(hdr); print('-'*len(hdr))
    for k,f in {'ninguna':lambda h:True,'fuera 12-20 UTC':lambda h:not(12<=h<20),'fuera 13:30-20 UTC':lambda h:not(13.5<=h<20),'SOLO 12-20 UTC':lambda h:12<=h<20}.items():
        tr=sim(f)
        if len(tr)<20: print(f"{k:<26} {len(tr)} trades"); continue
        tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
        print(f"{k:<26} {len(tr)/weeks:>5.1f} {tot:>+7.0f} {pf:>5.2f} {mdd:>+6.0f} {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} {min(terc):>+6.0f}")
print("=== US30 15m 300d (motor bot_us30, trail 5, spread 1.0) ==="); run('US30','MINUTE_15',300,us,us.TRAIL_ATR,1.0)
print("\n=== US30 1h 600d (motor bot_us30, trail 5) ==="); run('US30','HOUR',600,us,us.TRAIL_ATR,1.0)
import os
if os.path.exists('data/capital_US100_MINUTE_15_300d.json'):
    print("\n=== US100 15m 300d (motor sp500 como proxy, trail 4, spread 0.5) ==="); run('US100','MINUTE_15',300,sp,4.0,0.5)
print("\n=== US500 15m 300d (control) ==="); run('US500','MINUTE_15',300,sp,sp.TRAIL_ATR,0.3)
