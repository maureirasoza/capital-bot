#!/usr/bin/env python3
"""Meseta alrededor de los dos escenarios positivos: (A) 4h borde SL x TP; (B) confirmacion + estructural."""
import sys; sys.argv=['x']
src=open('fvg_escenarios.py').read(); exec(src[:src.index("# verificacion del detector")])
print(f"{'escenario':<48} | {'2024: tr neto PF acc':^26} | {'600d: tr neto PF acc DD':^32}")
print("-- (A) 4h, borde: malla SL x TP --")
for sl_ in (0.75,1.0,1.25,1.5):
    for tp_ in (1.5,2.0,2.5,3.0): row(f"  4h SL{sl_}/TP{tp_}",make(sl=sl_,tp=tp_),d240,240)
print("-- (A') 4h con vida de orden distinta y 1h --")
for w in (10,40):
    fv.FILL_WIN=w; row(f"  4h SL1.0/TP2.0 vida {w}",make(sl=1.0,tp=2.0),d240,240); fv.FILL_WIN=20
for sl_,tp_ in ((1.0,2.0),(1.0,3.0),(0.75,2.0)): row(f"  1h SL{sl_}/TP{tp_}",make(sl=sl_,tp=tp_),d60,60)
print("-- (B) confirmacion + stop estructural: malla de TP en R y variantes --")
for rr in (1.0,1.25,1.5,2.0,2.5,3.0): row(f"  conf + estructural TP {rr}R",make(conf=True,mode="estructura",rr=rr))
row("  conf + estructural 1.5R + impulso>=1.5",make(conf=True,mode="estructura",rr=1.5,imp=1.5))
row("  conf + estructural 1.5R, huecos>=0.6",make(conf=True,mode="estructura",rr=1.5,min_gap=0.6))
row("  conf + estructural 1.5R, EMA20",make(conf=True,mode="estructura",rr=1.5,ema_len=20))
row("  conf + estructural 1.5R, EMA200",make(conf=True,mode="estructura",rr=1.5,ema_len=200))
row("  1h conf + estructural 1.5R",make(conf=True,mode="estructura",rr=1.5),d60,60)
row("  1h conf + estructural 2R",make(conf=True,mode="estructura",rr=2.0),d60,60)
