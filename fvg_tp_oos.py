#!/usr/bin/env python3
"""FVG TP_R fuera de muestra: baja GOLD 15m 600d y evalua la malla TP_R x FILL_WIN SOLO en la
mitad antigua (dias 600->300), que ningun ajuste previo vio. Luego el total."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br
fv=br._import_fvg(); base=dict(TP_R=fv.TP_R,FILL_WIN=fv.FILL_WIN)
O,H,L,C,T=br.fetch_capital('GOLD','MINUTE_15',600)
print(f"{len(C)} velas | {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}")
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=300)
segs={'FUERA DE MUESTRA (antigua, 600->300d)':(O[:cut],H[:cut],L[:cut],C[:cut],T[:cut]),'conocida (300d)':(O[cut-300:],H[cut-300:],L[cut-300:],C[cut-300:],T[cut-300:]),'TOTAL 600d':(O,H,L,C,T)}
for name,(o,h,l,c,t) in segs.items():
    print(f"\n=== {name}: {t[300]:%Y-%m-%d} -> {t[-1]:%Y-%m-%d} ===")
    print(f"{'TP|vida':>8} "+' '.join(f"{w:>22}" for w in (10,20,40)))
    for tp in (0.75,1.0,1.25,1.5,1.75,2.0):
        row=[]
        for w in (10,20,40):
            fv.TP_R=tp; fv.FILL_WIN=w; tr=br.simulate_fvg(o,h,l,c,t,fv); tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
            row.append(f"{tot:>+6.0f} PF{pf:4.2f} {wr:3.0f}% R{rob} DD{mdd:>+4.0f}")
        print(f"{tp:>8} "+' '.join(f"{r:>22}" for r in row))
for k,v in base.items(): setattr(fv,k,v)
