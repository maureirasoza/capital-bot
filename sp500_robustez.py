#!/usr/bin/env python3
"""Busqueda de MEJORAS DE ROBUSTEZ para SP500 v2 sobre 300d reales de US500 15m.
Punto debil conocido: primer tercio +25 (edge concentrado en mar-sep) y cortos flojos (+4.2 vs +13.7).
Dimensiones nuevas: sesion horaria, regimen de volatilidad, lado, trailing, salida por tiempo.
Criterio: maximizar el PEOR tercio (robustez), con >=3 tr/sem y PF>=1.5. Coste = spread (entrada limite)."""
import sys, os, statistics
import backtest_real as br, bot_sp500 as sp
O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300)
n=len(C); WIN=300; SPREAD=0.3; weeks=(T[-1]-T[WIN]).days/7
# senal real cacheada
sig=[None]*n; atrs=[None]*n
for t in range(WIN,n):
    lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
# mediana movil de ATR (regimen de volatilidad), ventana 300
atr_med=[None]*n
buf=[]
for t in range(n):
    if atrs[t]: buf.append(atrs[t])
    if len(buf)>300: buf.pop(0)
    atr_med[t]=statistics.median(buf) if len(buf)>=50 else None
hour=[t_.hour+t_.minute/60 for t_ in T]

SES={'todas':lambda h:True,'WallSt 13:30-20':lambda h:13.5<=h<20,'fuera WallSt':lambda h:not(13.5<=h<20),
     'Europa+WallSt 07-20':lambda h:7<=h<20,'noche 20-07':lambda h:h>=20 or h<7}
VOL={'cualquiera':lambda a,m:True,'ATR>=med':lambda a,m:a>=m,'ATR<med':lambda a,m:a<m,'ATR 0.7-1.5xmed':lambda a,m:0.7*m<=a<=1.5*m}
SIDES={'2lados':('long','short'),'largo':('long',)}

def sim(ses,vol,sides,trail,tstop):
    tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            elif tstop and t-pos['t0']>=tstop: ex=C[t]
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'gross':g,'net':g-2*SPREAD}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'
        if s not in sides: continue
        if not SES[ses](hour[t]): continue
        if atr_med[t] is None or not VOL[vol](a,atr_med[t]): continue
        d=trail*a; c=C[t]
        pos={'side':s,'entry':c,'dist':d,'extreme':c,'t0':t,'stop':c-d if s=='long' else c+d}
    return tr

rows=[]
for ses in SES:
  for vol in VOL:
    for sn,sides in SIDES.items():
      for trail in (3.0,4.0,5.0):
        for tstop in (None,24,48):
          tr=sim(ses,vol,sides,trail,tstop)
          if len(tr)<40: continue
          tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
          rows.append((min(terc),tot,pf,wr,mdd,terc,len(tr)/weeks,len(tr),f"{ses:<19} {vol:<15} {sn:<6} trail{trail} {('t'+str(tstop)+'v') if tstop else 'sin-tstop'}"))
base=[r for r in rows if r[8].startswith('todas') and 'cualquiera' in r[8] and '2lados' in r[8] and 'trail4.0' in r[8] and 'sin-tstop' in r[8]][0]
print(f"BASELINE (config actual): {base[8]}\n  {base[7]} tr ({base[6]:.1f}/sem) | {base[1]:+.0f} pts | PF {base[2]:.2f} | tercios {base[5][0]:+.0f}/{base[5][1]:+.0f}/{base[5][2]:+.0f} | PEOR TERCIO {base[0]:+.0f}\n")
print(f"{len(rows)} variantes. == TOP por PEOR TERCIO (robustez), con >=3 tr/sem y PF>=1.5 ==")
hdr=f"{'config':<58} {'tr/sem':>6} {'NETO':>6} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>18} {'peor':>6}"
print(hdr); print('-'*len(hdr))
cand=sorted([r for r in rows if r[6]>=3 and r[2]>=1.5], key=lambda r:-r[0])
for peor,tot,pf,wr,mdd,terc,tpw,ntr,name in cand[:15]:
    print(f"{name:<58} {tpw:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {peor:>+6.0f}")
print("\n== TOP por NETO (>=3 tr/sem, ROB3) ==")
for peor,tot,pf,wr,mdd,terc,tpw,ntr,name in sorted([r for r in rows if r[6]>=3 and r[0]>0], key=lambda r:-r[1])[:8]:
    print(f"{name:<58} {tpw:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {peor:>+6.0f}")
