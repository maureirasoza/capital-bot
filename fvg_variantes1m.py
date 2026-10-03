#!/usr/bin/env python3
"""Variantes estructurales del FVG con el simulador FIEL (1m bid/ask), ANTIGUO 2024 | RECIENTE 600d."""
from datetime import datetime
import backtest_real as br, fvg_sim1m as s1
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,SL_MULT=fv.SL_MULT,FILL_WIN=fv.FILL_WIN,MIN_GAP=fv.MIN_GAP,EMA_TREND=fv.EMA_TREND,MAX_GAP=fv.MAX_GAP)
def setp(**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
d15,d1=s1.load(1000); mids=s1.prep(d15); cut=datetime(2025,2,9); HOUR={t:t.hour for t in d15["T"]}
def wrap(depth=0.0, fade=False, sl=None, tp=None):
    """Reescribe nivel/SL/TP del setup real: depth = fraccion del hueco hacia adentro; fade = operar en contra."""
    f=fv.find_pending_fvg_ohlc
    def g(O,H,L,C):
        s=f(O,H,L,C)
        if not s or not s.get("side"): return s
        gap=s["gap_eff"]; SLm=sl if sl is not None else fv.SL_MULT; TPm=tp if tp is not None else fv.TP_R
        if s["side"]=="BUY":
            lvl=s["level"]-depth*gap
            if fade: s=dict(s,side="SELL",level=round(lvl,1),sl=round(lvl+SLm*gap,1),tp=round(lvl-TPm*gap,1))
            else:    s=dict(s,level=round(lvl,1),sl=round(lvl-SLm*gap,1),tp=round(lvl+TPm*gap,1))
        else:
            lvl=s["level"]+depth*gap
            if fade: s=dict(s,side="BUY",level=round(lvl,1),sl=round(lvl-SLm*gap,1),tp=round(lvl+TPm*gap,1))
            else:    s=dict(s,level=round(lvl,1),sl=round(lvl+SLm*gap,1),tp=round(lvl-TPm*gap,1))
        return s
    return g
def row(name,sigfn=None,extra=None,**kw):
    setp(**kw); full=s1.sim(d15,d1,fv,mids=mids,sigfn=sigfn,extra=extra)
    a=s1.stats([x for x in full if x["t_in"]<cut]); b=s1.stats([x for x in full if x["t_in"]>=cut])
    print(f"{name:<46} | {a['n']:>4} {a['tot']:>+6.0f} {a['pf']:>5.2f} {a['acc']:>3.0f}% | {b['n']:>4} {b['tot']:>+6.0f} {b['pf']:>5.2f} {b['acc']:>3.0f}% {b['dd']:>+5.0f}")
print(f"{'variante':<46} | {'ANTIGUO 2024: tr neto PF acc':^30} | {'RECIENTE 600d: tr neto PF acc DD':^34}")
row("ACTUAL (borde, continuacion, SL2/TP0.75)")
print("-- entrar mas ADENTRO del hueco (mejor precio, menos llenados) --")
for dp in (0.25,0.5,1.0): row(f"  nivel a {int(dp*100)}% del hueco, SL2/TP0.75",wrap(depth=dp))
for dp in (0.5,1.0): row(f"  nivel a {int(dp*100)}% del hueco, SL1.5/TP1.5",wrap(depth=dp,sl=1.5,tp=1.5))
print("-- operar EN CONTRA (fade: el retorno al hueco sigue, no rebota) --")
for sl_,tp_ in ((1.0,1.0),(1.0,2.0),(2.0,1.0),(0.75,2.0)): row(f"  fade en el borde, SL{sl_}/TP{tp_}",wrap(fade=True,sl=sl_,tp=tp_))
print("-- filtros sobre la config actual --")
for mg in (0.8,1.2,1.6): row(f"  solo huecos >= {mg}xATR",MIN_GAP=mg)
for e in (0,200): row(f"  EMA_TREND {e if e else 'sin filtro'}",EMA_TREND=e if e else 10**6)
for nm,f in (("Londres+NY 07-20 UTC",lambda s,t:7<=HOUR[d15['T'][t]]<20),("solo NY 12-20 UTC",lambda s,t:12<=HOUR[d15['T'][t]]<20),("sin Asia (06-22)",lambda s,t:6<=HOUR[d15['T'][t]]<22)):
    row(f"  horario {nm}",extra=f)
row("  vida de la orden 8 velas",FILL_WIN=8); row("  vida 40 velas",FILL_WIN=40)
print("-- razon riesgo/beneficio mas amplia --")
for sl_,tp_ in ((1.0,3.0),(1.5,3.0),(2.0,3.0),(1.0,4.0)): row(f"  SL{sl_}/TP{tp_}",SL_MULT=sl_,TP_R=tp_)
setp()
