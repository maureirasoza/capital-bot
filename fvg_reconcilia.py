#!/usr/bin/env python3
"""(1) Reconciliacion del simulador 1m contra las operaciones REALES del FVG desde el 24-sep;
(2) comparacion de modelos (15m medio+spread fijo | 15m bid/ask | 1m bid/ask) con la config actual
y la anterior; (3) malla TP x SL con ejecucion 1m en ANTIGUO (2024, no visto) y RECIENTE (600d)."""
import sys, time
from datetime import datetime, timezone, timedelta
import backtest_real as br, fvg_sim1m as s1, fvg_bidask as ba
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,SL_MULT=fv.SL_MULT,FILL_WIN=fv.FILL_WIN,MIN_GAP=fv.MIN_GAP,EMA_TREND=fv.EMA_TREND,MAX_GAP=fv.MAX_GAP)
def setp(**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
t0=time.time(); d15,d1=s1.load(1000); mids=s1.prep(d15); T=d15["T"]; print(f"datos: 15m {len(T)} velas, 1m {len(d1['T'])} velas (cargado en {time.time()-t0:.0f}s)")
cut=datetime(2025,2,9)
# (1) reconciliacion
print("\n== (1) RECONCILIACION 1m desde 24-sep 11:30 UTC (reales: 23 tr, 17G/6P 74%, +5.46 pts, gan 4.85 / perd 12.84) ==")
tr=s1.sim(d15,d1,fv,a=datetime(2026,9,20),mids=mids); rec=[x for x in tr if x["t_in"]>=datetime(2026,9,24,11,30)]
for x in rec: print(f"  {x['t_in']:%m-%d %H:%M} {x['side']:<4} @ {x['entry']:<8.1f} -> {x['t_out']:%m-%d %H:%M} {x['net']:>+6.2f}")
r=s1.stats(rec); print(f"  simulador 1m: {r['n']} tr, {r['acc']:.0f}% acierto, neto {r['tot']:+.1f} pts (gan {r['w']:.2f} / perd {r['l']:.2f})")
# (2) modelos
print("\n== (2) MODELOS sobre los ultimos 600d, config ACTUAL (SL2.0/TP0.75) y ANTERIOR (SL1.5/TP1.0) ==")
Tz=[t.replace(tzinfo=timezone.utc) for t in T]; i600=next(i for i,t in enumerate(T) if t>=cut)
O,H,L,C=mids
for nm,kw in (("ACTUAL SL2.0/TP0.75",{}),("ANTERIOR SL1.5/TP1.0",dict(SL_MULT=1.5,TP_R=1.0))):
    setp(**kw); br.SPREAD=0.3
    m=ba.stats(br.simulate_fvg(O[i600-200:],H[i600-200:],L[i600-200:],C[i600-200:],Tz[i600-200:],fv))
    d15c={k:(v[i600-200:] if k!="T" else v[i600-200:]) for k,v in d15.items()}; b=ba.stats(ba.sim_ba(d15c,fv))
    x=s1.stats(s1.sim(d15,d1,fv,a=cut,mids=mids))
    print(f"  {nm}")
    for lab,rr in (("15m medio + 0.6 fijo",m),("15m bid/ask",b),("1m bid/ask (FIEL)",x)):
        print(f"     {lab:<22} {rr['n']:>5} tr | neto {rr['tot']:>+7.0f} | PF {rr['pf']:.2f} | acierto {rr['acc']:.1f}% | gan {rr['w']:.2f} perd {rr['l']:.2f} | DD {rr['dd']:+.0f} | tercios {rr['seg'][0]:+.0f}/{rr['seg'][1]:+.0f}/{rr['seg'][2]:+.0f}")
# (3) malla TP x SL ejecucion 1m
print("\n== (3) MALLA SL x TP con ejecucion 1m: ANTIGUO 2024-01->2025-02 (no visto) | RECIENTE 600d | TOTAL ==")
print(f"{'SL':>4} {'TP':>5} | {'tr':>4} {'neto':>6} {'PF':>5} {'acc':>4} {'DD':>5} | {'tr':>4} {'neto':>6} {'PF':>5} {'acc':>4} {'DD':>5} | {'tr':>4} {'neto':>6} {'PF':>5} {'acc':>4} {'DD':>5} {'3 tercios':>18}")
for sl in (1.0,1.5,2.0,3.0):
    for tp in (0.5,0.75,1.0,1.5,2.0):
        setp(SL_MULT=sl,TP_R=tp); full=s1.sim(d15,d1,fv,mids=mids)
        a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut]); c=s1.stats(full)
        mark=" <- actual" if (sl,tp)==(2.0,0.75) else (" <- anterior" if (sl,tp)==(1.5,1.0) else "")
        print(f"{sl:>4} {tp:>5} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% {a['dd']:>+5.0f} | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+5.0f} | {c['n']:>4} {c['tot']:>+6.0f} {c['pf']:>5.2f} {c['acc']:>3.0f}% {c['dd']:>+5.0f} {c['seg'][0]:>+5.0f}/{c['seg'][1]:>+5.0f}/{c['seg'][2]:>+5.0f}{mark}")
setp()
