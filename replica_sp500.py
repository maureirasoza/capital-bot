#!/usr/bin/env python3
"""REPLICA del motor SP500 v2 (BB+RSI de 2 lados, sin filtro, salida trailing x ATR) en otros
instrumentos, datos REALES 15m/300d de capital.com. Para cada uno: la config EXACTA del SP500
(BB26/1.75 RSI30/70 trail 4x) y una malla 4 params x 4 trailings para ver si hay meseta ROB3.
Uso: python replica_sp500.py EPIC:MEDIO_SPREAD [EPIC:MEDIO_SPREAD ...] [--res HOUR --days 600]"""
import sys
import backtest_real as br, bot_sp500 as sp
RES='MINUTE_15'; DAYS=300
args=[a for a in sys.argv[1:]]
if '--res' in args: RES=args[args.index('--res')+1]
if '--days' in args: DAYS=int(args[args.index('--days')+1])
items=[a for a in args if ':' in a]
PARAMS=((26,1.75,30,70),(26,1.75,35,65),(20,2.0,30,70),(20,2.0,35,65)); TRAILS=(3.0,4.0,5.0,6.0); WIN=300
def sim(O,H,L,C,sig,atrs,trail,SPREAD):
    n=len(C); tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD,'atr':pos['atr'],'side':s}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
        pos={'side':s,'entry':c,'dist':d,'atr':a,'extreme':c,'stop':c-d if s=='long' else c+d}
    return tr
for it in items:
    epic,spr=it.split(':'); spr=float(spr)
    try: O,H,L,C,T=br.fetch_capital(epic,RES,DAYS)
    except SystemExit as e: print(f"{epic}: sin datos ({e})"); continue
    n=len(C); weeks=(T[-1]-T[WIN]).days/7
    print(f"\n=== {epic} {RES} | {n} velas | {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem | spread {2*spr} ===")
    print(f"{'params':<20} {'trail':>5} {'tr/s':>5} {'NETO pts':>9} {'en ATRs':>8} {'PF':>5} {'acc':>4} {'maxDD':>7} {'3 tercios':>24} {'ROB':>3}")
    rob3=0; tot_c=0
    for bl,bm,rlo,rhi in PARAMS:
        sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=bl,bm,rlo,rhi
        sig=[None]*n; atrs=[None]*n
        for t in range(WIN,n):
            lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
        for trail in TRAILS:
            tr=sim(O,H,L,C,sig,atrs,trail,spr)
            if len(tr)<30: continue
            tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); tot_c+=1; rob3+=rob==3
            atr_m=sum(x['atr'] for x in tr)/len(tr)
            mark=' <== config SP500' if (bl,bm,rlo,rhi,trail)==(26,1.75,30,70,4.0) else ''
            print(f"BB{bl}/{bm} RSI{rlo}/{rhi:<4} {trail:>5} {len(tr)/weeks:>5.1f} {tot:>+9.0f} {tot/atr_m:>+8.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+7.0f} {terc[0]:>+7.0f}/{terc[1]:>+7.0f}/{terc[2]:>+7.0f} {rob:>3}{mark}")
    print(f"   -> ROB3: {rob3}/{tot_c} celdas")
sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=26,1.75,30,70
