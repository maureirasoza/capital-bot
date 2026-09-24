#!/usr/bin/env python3
"""FVG: meseta del SL con TP 0.75 (¿2.0 es centro o borde?) y combinaciones SL x vida, en las
dos mitades de 600d reales y con desliz 0.5. Riesgo por trade en puntos (SL medio)."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,FILL_WIN=fv.FILL_WIN,SL_MULT=fv.SL_MULT)
O,H,L,C,T=br.fetch_capital('GOLD','MINUTE_15',600)
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=300)
segs={'antigua':(O[:cut],H[:cut],L[:cut],C[:cut],T[:cut]),'reciente':(O[cut-300:],H[cut-300:],L[cut-300:],C[cut-300:],T[cut-300:]),'600d':(O,H,L,C,T)}
def run(seg,slip=0,**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
    br.SLIP=slip; o,h,l,c,t=segs[seg]; tr=br.simulate_fvg(o,h,l,c,t,fv); br.SLIP=0
    loss=[-x['net'] for x in tr if x['net']<0]; return br.stats(tr,'net'),len(tr),(sum(loss)/len(loss) if loss else 0)
hdr=f"{'config':<26} {'antigua':>8} {'reciente':>8} | {'600d':>6} {'PF':>5} {'acc':>4} {'ROB':>3} {'maxDD':>6} {'3 tercios':>18} {'perd.media':>10} {'n':>5} | {'slip0.5':>8}"
print(hdr); print('-'*len(hdr))
def row(name,**kw):
    (ta,*_),_,_=run('antigua',**kw); (tr_,*_),_,_=run('reciente',**kw); (tt,wr,pf,mdd,terc,rob),n,lm=run('600d',**kw); (ts,_,pfs,_,_,robs),_,_=run('600d',slip=0.5,**kw)
    print(f"{name:<26} {ta:>+8.0f} {tr_:>+8.0f} | {tt:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {rob:>3} {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {lm:>10.1f} {n:>5} | {ts:>+5.0f} R{robs}")
row("ACTUAL SL1.5 TP1.0 vida20")
print()
for sl in (1.5,2.0,2.5,3.0,4.0):
    row(f"SL{sl} TP0.75 vida20",SL_MULT=sl,TP_R=0.75)
print()
for sl in (1.5,2.0,2.5,3.0):
    row(f"SL{sl} TP0.75 vida40",SL_MULT=sl,TP_R=0.75,FILL_WIN=40)
print()
row("SL2.0 TP1.0 vida40",SL_MULT=2.0,TP_R=1.0,FILL_WIN=40)
row("SL2.0 TP0.5 vida40",SL_MULT=2.0,TP_R=0.5,FILL_WIN=40)
for k,v in base.items(): setattr(fv,k,v)
