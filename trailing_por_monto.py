#!/usr/bin/env python3
"""SP500 (size 1.0 -> 1 pt = $1): apretar el stop solo cuando la ganancia maxima supera un MONTO
fijo en dolares. (A) apretar el trailing a m x ATR; (B) garantizar un % de la ganancia maxima."""
import backtest_real as br, bot_sp500 as sp
O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300); n=len(C); WIN=300; SPREAD=0.3
sig=[None]*n; atrs=[None]*n
for t in range(WIN,n):
    lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
def sim(X=None,m=None,frac=None,trail=4.0):
    tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD,'mfe':pos['mfe']}); pos=None
            else:
                sgn=1 if s=='long' else -1
                pos['extreme']=max(pos['extreme'],H[t]) if s=='long' else min(pos['extreme'],L[t])
                mfe=sgn*(pos['extreme']-pos['entry']); pos['mfe']=mfe
                d=pos['dist']
                if X and m and mfe>=X: d=m*pos['atr']
                cand=pos['extreme']-sgn*d
                if X and frac and mfe>=X: 
                    lock=pos['entry']+sgn*frac*mfe
                    cand=max(cand,lock) if s=='long' else min(cand,lock)
                pos['stop']=max(pos['stop'],cand) if s=='long' else min(pos['stop'],cand)
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'; c=C[t]; d=trail*a
        pos={'side':s,'entry':c,'dist':d,'atr':a,'extreme':c,'mfe':0,'stop':c-d if s=='long' else c+d}
    return tr
hdr=f"{'variante':<40} {'#tr':>4} {'NETO $':>7} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>18} {'ROB':>3}"
def row(n_,tr):
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); print(f"{n_:<40} {len(tr):>4} {tot:>+7.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {rob:>3}")
base=sim(); print(hdr); print('-'*len(hdr)); row("ACTUAL (trailing fijo 4xATR)",base)
mf=sorted(x['mfe'] for x in base)
print(f"   de {len(base)} trades: llegan a +$30: {sum(1 for v in mf if v>=30)} | +$50: {sum(1 for v in mf if v>=50)} | +$75: {sum(1 for v in mf if v>=75)} | +$100: {sum(1 for v in mf if v>=100)} | +$150: {sum(1 for v in mf if v>=150)}")
print("\n(A) al pasar +$X, apretar el trailing a m x ATR"); print(hdr); print('-'*len(hdr))
for X in (30,50,75,100,150):
    for m in (1.5,2.0,3.0): row(f"+${X} -> trailing {m}xATR",sim(X=X,m=m))
print("\n(B) al pasar +$X, garantizar un % de la ganancia maxima (el trailing 4x sigue activo)"); print(hdr); print('-'*len(hdr))
for X in (30,50,75,100,150):
    for f in (0.3,0.5,0.7): row(f"+${X} -> asegurar {int(f*100)}% del maximo",sim(X=X,frac=f))
