#!/usr/bin/env python3
"""FVG con salida por TRAILING: meseta del multiplicador, filtros, y 6 tramos de ~165d. Ejecucion fiel 1m."""
import sys
from datetime import datetime
sys.argv=['x']
import backtest_real as br, fvg_sim1m as s1
exec(open('fvg_ultima_ronda.py').read().split("def row(")[0])   # reutiliza sim(), agg(), d15, d60, setp
def seg6(tr):
    if not tr: return []
    t0=tr[0]["t_in"]; t1=tr[-1]["t_in"]; span=(t1-t0)/6; out=[0.0]*6
    for x in tr: out[min(5,int((x["t_in"]-t0)/span))]+=x["net"]
    return out
def row(name,dS,bar_min,trail,**kw):
    setp(**kw); full=sim(dS,bar_min,trail)
    a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut]); c=s1.stats(full); s6=seg6(full)
    print(f"{name:<40} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['dd']:>+5.0f} | {c['tot']:>+6.0f} {c['pf']:>5.2f} | "+' '.join(f"{v:>+5.0f}" for v in s6)+f" | {sum(1 for v in s6 if v>0)}/6")
print(f"{'variante':<40} | {'2024: tr neto PF':^19} | {'600d: tr neto PF DD':^26} | {'TOTAL':^12} | {'6 tramos':^35} | pos")
print("-- 15m: meseta del trailing x ATR --")
for k in (3.0,4.0,5.0,6.0,7.0,8.0,10.0): row(f"15m trailing {k}xATR",d15,15,("atr",k))
print("-- 15m, trailing 5-6x: filtros --")
for k in (5.0,6.0):
    for e in (20,100,200): row(f"15m trailing {k}x, EMA{e}",d15,15,("atr",k),EMA_TREND=e)
    for mg in (0.2,0.8): row(f"15m trailing {k}x, MIN_GAP {mg}",d15,15,("atr",k),MIN_GAP=mg)
    row(f"15m trailing {k}x, vida 40",d15,15,("atr",k),FILL_WIN=40)
print("-- 1h: meseta --")
for k in (1.5,2.0,2.5): row(f"1h trailing {k}xhueco",d60,60,("gap",k))
for k in (4.0,5.0,6.0,8.0): row(f"1h trailing {k}xATR",d60,60,("atr",k))
