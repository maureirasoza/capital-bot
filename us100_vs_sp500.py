#!/usr/bin/env python3
"""US100 vs SP500 en DOLARES. Motor sp500 (BB+RSI 2 lados, trailing) sobre US100 15m/300d con
spread REAL (1.8 total -> 0.9 por lado), barrido de BB/RSI/trailing para ver la meseta, chequeo
1h/600d, y conversion a $/semana, maxDD en $ y $/sem por cada $100 de margen (1%)."""
import backtest_real as br, bot_sp500 as sp
PX={'US100':30400,'US500':7692}
def cache(epic,res,days,bl,bm,rlo,rhi,WIN=300):
    O,H,L,C,T=br.fetch_capital(epic,res,days); n=len(C)
    sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=bl,bm,rlo,rhi
    sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    return O,H,L,C,T,sig,atrs,(T[-1]-T[WIN]).days/7
def sim(D,trail,SPREAD,WIN=300):
    O,H,L,C,T,sig,atrs,_=D; n=len(C); tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
        pos={'side':s,'entry':c,'dist':d,'extreme':c,'stop':c-d if s=='long' else c+d}
    return tr
hdr=f"{'params':<26} {'trail':>5} {'tr/s':>5} {'NETO':>7} {'PF':>5} {'maxDD':>6} {'3 tercios':>20} {'ROB':>3}"
print("=== US100 15m 300d, spread real 0.9/lado — barrido ==="); print(hdr); print('-'*len(hdr))
best=[]
for bl,bm,rlo,rhi in ((26,1.75,30,70),(26,1.75,35,65),(20,2.0,30,70),(20,2.0,35,65),(26,2.0,30,70),(30,2.0,30,70)):
    D=cache('US100','MINUTE_15',300,bl,bm,rlo,rhi); weeks=D[7]
    for trail in (3.0,4.0,5.0,6.0,7.0):
        tr=sim(D,trail,0.9)
        if len(tr)<40: continue
        tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); name=f"BB{bl}/{bm} RSI{rlo}/{rhi}"
        print(f"{name:<26} {trail:>5} {len(tr)/weeks:>5.1f} {tot:>+7.0f} {pf:>5.2f} {mdd:>+6.0f} {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} {rob:>3}")
        best.append((rob,min(terc),tot,pf,mdd,len(tr)/weeks,(bl,bm,rlo,rhi,trail),terc))
print("\n=== US100 1h 600d — mismas familias, chequeo cruzado ==="); print(hdr); print('-'*len(hdr))
for bl,bm,rlo,rhi in ((26,1.75,30,70),(20,2.0,35,65)):
    D=cache('US100','HOUR',600,bl,bm,rlo,rhi); weeks=D[7]
    for trail in (3.0,4.0,5.0,6.0):
        tr=sim(D,trail,0.9)
        if len(tr)<30: continue
        tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); name=f"BB{bl}/{bm} RSI{rlo}/{rhi}"
        print(f"{name:<26} {trail:>5} {len(tr)/weeks:>5.1f} {tot:>+7.0f} {pf:>5.2f} {mdd:>+6.0f} {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} {rob:>3}")
# SP500 referencia (spread 0.3/lado)
sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=26,1.75,30,70
D=cache('US500','MINUTE_15',300,26,1.75,30,70); tr=sim(D,4.0,0.3); tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); wk=D[7]
print("\n=== EN DOLARES ($1/pt por unidad; margen 1%) ===")
def dol(name,epic,tot,mdd,weeks,size):
    m=PX[epic]*0.01*size; usd_w=tot*size/weeks; print(f"{name:<40} size {size:<4} margen ${m:>5.0f} | ${usd_w:>+5.1f}/sem | maxDD ${mdd*size:>+6.0f} | ${100*usd_w/m:>5.1f}/sem por cada $100 de margen")
dol("SP500 v2 (actual)",'US500',tot,mdd,wk,1.0)
cands=sorted([b for b in best if b[0]==3],key=lambda b:-b[1])[:3]
for rob,peor,tot2,pf2,mdd2,tpw,p,terc2 in cands:
    name=f"US100 BB{p[0]}/{p[1]} RSI{p[2]}/{p[3]} trail{p[4]}"
    for size in (0.1,0.25): dol(name,'US100',tot2,mdd2,wk,size)
