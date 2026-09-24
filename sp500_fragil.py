#!/usr/bin/env python3
"""Fragilidad del SP500 v2: concentracion del edge en pocas operaciones/horas, P&L mensual
(walk-forward), horario de la venue, y combos del filtro de sesion con trailing/volatilidad."""
import statistics
from collections import Counter
import backtest_real as br, bot_sp500 as sp
O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300); n=len(C); WIN=300; SPREAD=0.3
weeks=(T[-1]-T[WIN]).days/7
sig=[None]*n; atrs=[None]*n
for t in range(WIN,n):
    lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
buf=[]; atr_med=[None]*n
for t in range(n):
    if atrs[t]: buf.append(atrs[t])
    if len(buf)>300: buf.pop(0)
    atr_med[t]=statistics.median(buf) if len(buf)>=50 else None
print("-- velas por hora UTC (horario real de US500 en capital.com) --")
cnt=Counter(t_.hour for t_ in T); print(' '.join(f"{h}h:{cnt.get(h,0)}" for h in range(24)))

def sim(allow,trail=4.0,vol=None):
    tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD,'h':pos['h'],'m':T[pos['t0']].strftime('%Y-%m'),'side':s}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        h=T[t].hour+T[t].minute/60
        if not allow(h): continue
        if vol and (atr_med[t] is None or not vol(a,atr_med[t])): continue
        s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
        pos={'side':s,'entry':c,'dist':d,'extreme':c,'t0':t,'h':h,'stop':c-d if s=='long' else c+d}
    return tr

def row(name,tr):
    if len(tr)<20: print(f"{name:<44} {len(tr)} trades (pocos)"); return
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
    nets=sorted([x['net'] for x in tr],reverse=True); top5=sum(nets[:5]); sin_top5=tot-top5
    ms={}; [ms.__setitem__(x['m'],ms.get(x['m'],0)+x['net']) for x in tr]
    mpos=sum(1 for v in ms.values() if v>0)
    print(f"{name:<44} {len(tr)/weeks:>5.1f} {tot:>+6.0f} {pf:>5.2f} {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {min(terc):>+5.0f} {top5:>+6.0f} {sin_top5:>+7.0f} {mpos:>2}/{len(ms)}")
    return ms

hdr=f"{'config':<44} {'tr/s':>5} {'NETO':>6} {'PF':>5} {'maxDD':>6} {'3 tercios':>18} {'peor':>5} {'top5':>6} {'sinTop5':>7} {'meses+':>6}"
print("\n-- fragilidad: cuanto del neto son las 5 mejores operaciones; meses positivos --"); print(hdr); print('-'*len(hdr))
ALL=lambda h:True; F1220=lambda h:not(12<=h<20); FWS=lambda h:not(13.5<=h<20)
ms_base=row("actual (todas las horas, trail4)",sim(ALL))
row("actual SIN entradas 20-23h (reapertura)",sim(lambda h:not(20<=h<23)))
row("actual SIN entradas 22h",sim(lambda h:not(22<=h<23)))
ms_f=row("fuera 12-20, trail4",sim(F1220))
row("fuera 12-20 y SIN 20-23h",sim(lambda h:not(12<=h<23)))
row("fuera 13:30-20, trail4",sim(FWS))
print("\n-- combos del filtro de sesion --"); print(hdr); print('-'*len(hdr))
for tr_ in (3.0,4.0,5.0,6.0):
    row(f"fuera 12-20, trail{tr_}",sim(F1220,tr_))
for tr_ in (3.0,4.0,5.0):
    row(f"fuera 12-20 + ATR>=med, trail{tr_}",sim(F1220,tr_,lambda a,m:a>=m))
row("fuera 12-20 + ATR 0.7-1.5xmed, trail4",sim(F1220,4.0,lambda a,m:0.7*m<=a<=1.5*m))
print("\n-- P&L por mes: actual vs fuera 12-20 --")
for m in sorted(set(ms_base)|set(ms_f)): print(f"  {m}  actual {ms_base.get(m,0):>+6.0f}   fuera12-20 {ms_f.get(m,0):>+6.0f}")
