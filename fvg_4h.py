#!/usr/bin/env python3
"""FVG 4h (borde, SL 1 x hueco, TP 2-2.5 x hueco): fragilidad. 6 tramos, lados, alineacion de las velas
de 4h (desfase 1h/2h/3h), MAX_GAP/EMA/MIN_GAP, y desglose por anio."""
import sys; sys.argv=['x']
src=open('fvg_escenarios.py').read(); exec(src[:src.index("# verificacion del detector")])
from datetime import timedelta
def agg_off(d,mins,off_min):
    keys=("Ob","Hb","Lb","Cb","Oa","Ha","La","Ca"); out={k:[] for k in keys}; out["T"]=[]; cur=None; off=timedelta(minutes=off_min)
    for i,t in enumerate(d["T"]):
        tt=t-off; b=tt.replace(minute=0,hour=(tt.hour//(mins//60))*(mins//60))+off
        if b!=cur:
            cur=b; out["T"].append(b)
            for k in keys: out[k].append(d[k][i])
        else:
            for s in ("b","a"):
                out["H"+s][-1]=max(out["H"+s][-1],d["H"+s][i]); out["L"+s][-1]=min(out["L"+s][-1],d["L"+s][i]); out["C"+s][-1]=d["C"+s][i]
    return out
def full_stats(name,sigfn,dS):
    tr=sim(dS,240,sigfn); a=s1.stats([x for x in tr if x["t_in"]<cut]); b=s1.stats([x for x in tr if x["t_in"]>=cut]); c=s1.stats(tr)
    t0=tr[0]["t_in"]; t1=tr[-1]["t_in"]; span=(t1-t0)/6; s6=[0.0]*6
    for x in tr: s6[min(5,int((x["t_in"]-t0)/span))]+=x["net"]
    L=[x["net"] for x in tr if x.get("side","")!=""]
    print(f"{name:<40} | {a['tot']:>+5.0f} {a['pf']:>4.2f} | {b['tot']:>+5.0f} {b['pf']:>4.2f} {b['dd']:>+5.0f} | {c['tot']:>+5.0f} {c['pf']:>4.2f} {c['acc']:>3.0f}% | "+' '.join(f"{v:>+4.0f}" for v in s6)+f" | {sum(1 for v in s6 if v>0)}/6 | {len(tr)/((tr[-1]['t_out']-tr[0]['t_in']).days/7):.1f}/sem")
    return tr
print(f"{'variante':<40} | {'2024':^12} | {'600d':^18} | {'TOTAL':^16} | {'6 tramos':^29} | pos | frec")
print("-- alineacion de las velas de 4h (prueba de fragilidad) --")
for off in (0,60,120,180):
    dX=agg_off(d15,240,off)
    for tp_ in (2.0,2.5): full_stats(f"  desfase {off//60}h, SL1.0/TP{tp_}",make(sl=1.0,tp=tp_),dX)
print("-- filtros sobre 4h SL1.0/TP2.0 (alineacion 0h) --")
base=full_stats("  base",make(sl=1.0,tp=2.0),d240)
for mg in (0.2,0.6,0.8): full_stats(f"  MIN_GAP {mg}",make(sl=1.0,tp=2.0,min_gap=mg),d240)
for e in (20,100,200): full_stats(f"  EMA {e}",make(sl=1.0,tp=2.0,ema_len=e),d240)
fv.MAX_GAP=99; full_stats("  sin tope MAX_GAP",make(sl=1.0,tp=2.0),d240); fv.MAX_GAP=3.0
for w in (30,40,60): 
    fv.FILL_WIN=w; full_stats(f"  vida {w} velas 4h",make(sl=1.0,tp=2.0),d240); fv.FILL_WIN=20
# lados y anios
tr=sim(d240,240,make(sl=1.0,tp=2.0))
print("\nbase SL1/TP2 por anio:",{y:round(sum(x['net'] for x in tr if x['t_in'].year==y)) for y in (2024,2025,2026)})
