#!/usr/bin/env python3
"""Salida alternativa para SP500 v2: cerrar al tocar la banda MEDIA (salida clasica de reversion)
con SL fijo k x ATR, y variantes hibridas (media + trailing). Objetivo: menos dependencia de pocas
operaciones grandes. Se valida en 15m/300d y en 1h/600d."""
import backtest_real as br, bot_sp500 as sp
def run(res,days,SPREAD=0.3,WIN=300):
    O,H,L,C,T=br.fetch_capital('US500',res,days); n=len(C); weeks=(T[-1]-T[WIN]).days/7
    sig=[None]*n; atrs=[None]*n; mid=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']; mid[t]=(s['upper']+s['lower'])/2
    def sim(exit_mode,k,trail=None):
        tr=[]; pos=None
        for t in range(WIN,n):
            if pos:
                s=pos['side']; ex=None
                if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
                elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
                elif exit_mode=='media' and ((s=='long' and C[t]>=mid[t]) or (s=='short' and C[t]<=mid[t])): ex=C[t]
                if ex is not None:
                    g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD}); pos=None
                elif trail:
                    if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-trail*pos['atr'])
                    else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+trail*pos['atr'])
                continue
            sd=sig[t]; a=atrs[t]
            if not sd or not a: continue
            s='long' if sd=='BUY' else 'short'; c=C[t]
            pos={'side':s,'entry':c,'atr':a,'extreme':c,'stop':c-k*a if s=='long' else c+k*a}
        return tr
    hdr=f"{'salida':<34} {'tr/s':>5} {'NETO':>7} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>18} {'peor':>5} {'top5%':>5}"; print(hdr); print('-'*len(hdr))
    cfgs=[("trailing 4x (actual)",'trail',4.0,4.0)]
    for k in (1.5,2.0,3.0,4.0): cfgs.append((f"media + SL fijo {k}xATR",'media',k,None))
    for k in (3.0,4.0): cfgs.append((f"media + trailing {k}xATR",'media',k,k))
    for name,mode,k,trail in cfgs:
        tr=sim(mode,k,trail)
        if len(tr)<20: print(f"{name:<34} {len(tr)} trades"); continue
        tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); nets=sorted([x['net'] for x in tr],reverse=True); t5=sum(nets[:5])
        print(f"{name:<34} {len(tr)/weeks:>5.1f} {tot:>+7.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {min(terc):>+5.0f} {100*t5/tot if tot>0 else 0:>4.0f}%")
print("=== US500 15m 300d ==="); run('MINUTE_15',300)
print("\n=== US500 1h 600d ==="); run('HOUR',600)
