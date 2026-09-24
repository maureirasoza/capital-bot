#!/usr/bin/env python3
"""Validacion del hallazgo FVG (TP_R 1.25-1.5 > 1.0 en 300d reales de oro):
 (a) malla TP_R x FILL_WIN en oro; (b) comparacion mes a mes TP1.0 vs TP1.5 (pareada);
 (c) test cruzado: misma direccion del efecto en US500 / US30 / US100 15m (motor FVG real);
 (d) sensibilidad al desliz."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br
fv=br._import_fvg()
base=dict(TP_R=fv.TP_R,FILL_WIN=fv.FILL_WIN,SL_MULT=fv.SL_MULT)
def setp(**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
def st(tr):
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); return tot,wr,pf,mdd,terc,rob
(O,H,L,C,T),_=br._fetch_15m("GOLD","GC=F")
print("=== (a) ORO: malla TP_R x FILL_WIN (neto / PF / ROB) ===")
print(f"{'TP|vida':>8} " + ' '.join(f"{w:>18}" for w in (10,20,30,40)))
for tp in (0.75,1.0,1.25,1.5,1.75,2.0):
    row=[]
    for w in (10,20,30,40):
        setp(TP_R=tp,FILL_WIN=w); tot,wr,pf,mdd,terc,rob=st(br.simulate_fvg(O,H,L,C,T,fv)); row.append(f"{tot:>+6.0f} {pf:4.2f} R{rob} DD{mdd:>+5.0f}")
    print(f"{tp:>8} "+' '.join(f"{r:>18}" for r in row))
print("\n=== (b) ORO mes a mes: TP 1.0 vs TP 1.5 (misma vida 20) ===")
def bym(tr):
    d={}
    for x in tr: k=x['t_in'].strftime('%Y-%m'); d[k]=d.get(k,0)+x['net']
    return d
setp(TP_R=1.0); m10=bym(br.simulate_fvg(O,H,L,C,T,fv)); setp(TP_R=1.5); m15=bym(br.simulate_fvg(O,H,L,C,T,fv))
w=0
for k in sorted(m10): 
    b='<-- 1.5 mejor' if m15.get(k,0)>m10[k] else ''; w+=m15.get(k,0)>m10[k]; print(f"  {k}  TP1.0 {m10[k]:>+6.0f}   TP1.5 {m15.get(k,0):>+6.0f}  {b}")
print(f"  TP1.5 gana en {w}/{len(m10)} meses")
print("\n=== (c) TEST CRUZADO en indices (motor FVG real, 15m 300d): direccion del efecto TP ===")
print(f"{'instrumento':<8} {'TP':>5} {'#tr':>4} {'NETO':>7} {'PF':>5} {'acc':>4} {'3 tercios':>20} {'ROB':>3}")
for epic,sp in (('US500',0.3),('US30',1.0),('US100',0.9)):
    O2,H2,L2,C2,T2=br.fetch_capital(epic,'MINUTE_15',300); br.SPREAD=sp
    for tp in (0.75,1.0,1.25,1.5,2.0):
        setp(TP_R=tp); tr=br.simulate_fvg(O2,H2,L2,C2,T2,fv); tot,wr,pf,mdd,terc,rob=st(tr)
        print(f"{epic:<8} {tp:>5} {len(tr):>4} {tot:>+7.0f} {pf:>5.2f} {wr:>3.0f}% {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} {rob:>3}")
br.SPREAD=0.3
print("\n=== (d) ORO: sensibilidad al desliz (TP 1.0 vs 1.5, vida 20) ===")
for slip in (0.0,0.5,1.0,2.0):
    br.SLIP=slip; out=[]
    for tp in (1.0,1.5):
        setp(TP_R=tp); tot,wr,pf,mdd,terc,rob=st(br.simulate_fvg(O,H,L,C,T,fv)); out.append(f"TP{tp}: {tot:>+6.0f} PF{pf:4.2f} R{rob}")
    print(f"  desliz {slip}: "+' | '.join(out))
br.SLIP=0.0; setp()
