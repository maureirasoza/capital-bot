#!/usr/bin/env python3
"""FVG TP 0.75: cruce SL x TP en las dos mitades de 600d reales, y sensibilidad al desliz."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,FILL_WIN=fv.FILL_WIN,SL_MULT=fv.SL_MULT)
O,H,L,C,T=br.fetch_capital('GOLD','MINUTE_15',600)
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=300)
segs={'antigua':(O[:cut],H[:cut],L[:cut],C[:cut],T[:cut]),'reciente':(O[cut-300:],H[cut-300:],L[cut-300:],C[cut-300:],T[cut-300:]),'600d':(O,H,L,C,T)}
def run(seg,**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
    o,h,l,c,t=segs[seg]; tr=br.simulate_fvg(o,h,l,c,t,fv); return br.stats(tr,'net'),len(tr)
print("=== cruce SL x TP (vida 20): neto antigua | reciente | 600d PF ROB DD ===")
for sl in (1.0,1.25,1.5,2.0):
    for tp in (0.5,0.75,1.0):
        (ta,*_),_=run('antigua',SL_MULT=sl,TP_R=tp); (tr_,*_),_=run('reciente',SL_MULT=sl,TP_R=tp); (tt,wr,pf,mdd,terc,rob),n=run('600d',SL_MULT=sl,TP_R=tp)
        print(f"SL {sl:<4} TP {tp:<5} {ta:>+6.0f} | {tr_:>+6.0f} | {tt:>+6.0f} PF{pf:4.2f} {wr:3.0f}% R{rob} DD{mdd:>+5.0f} tercios {terc[0]:+.0f}/{terc[1]:+.0f}/{terc[2]:+.0f} n={n}")
print("\n=== vida de orden con TP 0.75 (SL 1.5) ===")
for w in (10,20,30,40,60):
    (ta,*_),_=run('antigua',TP_R=0.75,FILL_WIN=w); (tr_,*_),_=run('reciente',TP_R=0.75,FILL_WIN=w); (tt,wr,pf,mdd,terc,rob),n=run('600d',TP_R=0.75,FILL_WIN=w)
    print(f"vida {w:<3} {ta:>+6.0f} | {tr_:>+6.0f} | {tt:>+6.0f} PF{pf:4.2f} R{rob} DD{mdd:>+5.0f}")
print("\n=== desliz (600d, vida 20): TP 0.75 vs 1.0 ===")
for slip in (0,0.5,1.0,1.5,2.0):
    br.SLIP=slip; out=[]
    for tp in (0.75,1.0):
        (tt,wr,pf,mdd,terc,rob),n=run('600d',TP_R=tp); out.append(f"TP{tp}: {tt:>+6.0f} PF{pf:4.2f} R{rob}")
    print(f"  desliz {slip}: "+' | '.join(out))
br.SLIP=0
for k,v in base.items(): setattr(fv,k,v)
