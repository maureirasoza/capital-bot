#!/usr/bin/env python3
"""Misma metrica de fragilidad para los 5 bots (datos reales congelados): % del neto en las 5
mejores operaciones, neto sin ellas, meses positivos y neto sin la mejor hora de entrada."""
import sys, statistics
import backtest_real as br
sys.argv=['x','--source','capital']   # que _fetch_* use datos reales
def frag(name,tr,T=None):
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
    nets=sorted([x['net'] for x in tr],reverse=True); top5=sum(nets[:5])
    print(f"{name:<22} {len(tr):>4} {tot:>+7.0f} {pf:>5.2f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {top5:>+6.0f} {100*top5/tot:>4.0f}% {tot-top5:>+7.0f}")
hdr=f"{'bot':<22} {'#tr':>4} {'NETO':>7} {'PF':>5} {'3 tercios':>18} {'top5':>6} {'%':>4} {'sinTop5':>7}"
print(hdr); print('-'*len(hdr))
# Trend oro 1h
tr,*_=br.run_trend(); frag("Oro Trend 1h 5x",tr)
# Bollinger oro 15m
bg=br._import_bollinger(); (O,H,L,C,T),_=br._fetch_15m("GOLD","GC=F")
frag("Oro Bollinger 15m 5x",br.simulate_bollinger(O,H,L,C,T,bg,bg.TRAIL_ATR))
# FVG oro 15m
fv=br._import_fvg(); frag("Oro FVG 15m",br.simulate_fvg(O,H,L,C,T,fv))
# SP500
import bot_sp500 as sp; O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300)
frag("SP500 v2 15m 4x",br.simulate_bollinger(O,H,L,C,T,sp,sp.TRAIL_ATR))
# US30
import bot_us30 as us; O,H,L,C,T=br.fetch_capital('US30','MINUTE_15',300)
br.SPREAD=1.0; frag("US30 15m 5x",br.simulate_bollinger(O,H,L,C,T,us,us.TRAIL_ATR))
