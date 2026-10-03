#!/usr/bin/env python3
"""Solape entre la RUPTURA FALLIDA (US30 1h, N48 M2 k2 trail3, fiel 1m) y el bot US30 actual
(BB20/2.0 RSI35/65 trail5, 15m): correlacion semanal, % de tiempo ambos en posicion, mismo lado."""
import sys, statistics
sys.argv=['x']
src=open('ruptura_fallida_fiel.py').read(); exec(src[:src.index('print(f"US30 1h')])
import bot_us30 as us
from datetime import timezone
O15,H15,L15,C15=s1.prep(d15); T15=d15["T"]
# trades del bot US30 con el modelo 15m (medio + spread 1.0) y marcas de tiempo
br.SPREAD=1.0; Tz=[t.replace(tzinfo=timezone.utc) for t in T15]
b=br.simulate_bollinger(O15,H15,L15,C15,Tz,us,us.TRAIL_ATR)
rf=sim(48,2,2.0,3.0)
def weekly(tr,key_in,key_out):
    d={}
    for x in tr: k=x[key_out].strftime('%G-%V'); d[k]=d.get(k,0)+x['net']
    return d
wb={}; 
for x in b: k=x['t_out'].strftime('%G-%V'); wb[k]=wb.get(k,0)+x['net']
wr=weekly(rf,'t_in','t_out'); ks=sorted(set(wb)|set(wr)); a=[wb.get(k,0) for k in ks]; c=[wr.get(k,0) for k in ks]
ma,mc=statistics.mean(a),statistics.mean(c); cov=sum((x-ma)*(y-mc) for x,y in zip(a,c)); corr=cov/((sum((x-ma)**2 for x in a)*sum((y-mc)**2 for y in c))**0.5)
# solape temporal: minutos con ambos en posicion y mismo lado
ints_b=[(x['t_in'].replace(tzinfo=None),x['t_out'].replace(tzinfo=None),x['side']) for x in b]
same=opp=0; tot_rf_min=0
for x in rf:
    s='long' if x['net']==x['net'] and x.get('long',None) is None else None
for x in rf:
    pass
# reconstruir lado de rf: lo guardamos recalculando signo via entrada/salida no disponible -> usar overlap solo temporal
ov=0
for x in rf:
    for (ti,to,sd) in ints_b:
        if x['t_in']<to and x['t_out']>ti: ov+=1; break
print(f"bot US30 (15m): {len(b)} trades, {sum(x['net'] for x in b):+.0f} pts | ruptura fallida: {len(rf)} trades, {sum(x['net'] for x in rf):+.0f} pts")
print(f"correlacion de P&L semanal: {corr:+.2f} | semanas ambos negativos: {sum(1 for x,y in zip(a,c) if x<0 and y<0)}/{len(ks)} | trades de ruptura fallida que coinciden en el tiempo con una posicion del bot US30: {ov}/{len(rf)} ({100*ov/len(rf):.0f}%)")
