#!/usr/bin/env python3
"""Chequeo REALISTA para instrumentos con cierre nocturno (NL25 y otros): el stop se ejecuta en
la APERTURA si la vela abre mas alla del stop (gap), y no se entra si la vela siguiente a la senal
no es contigua (mercado cerrado -> la orden limite de 15 min expira).
Uso: python nl25_realista.py EPIC MEDIO_SPREAD [RES DIAS]"""
import sys, statistics
import backtest_real as br, bot_sp500 as sp
EPIC=sys.argv[1]; SPR=float(sys.argv[2]); RES=sys.argv[3] if len(sys.argv)>3 else 'MINUTE_15'; DAYS=int(sys.argv[4]) if len(sys.argv)>4 else 300
BARMIN=15 if RES=='MINUTE_15' else 60; WIN=300
O,H,L,C,T=br.fetch_capital(EPIC,RES,DAYS); n=len(C); weeks=(T[-1]-T[WIN]).days/7
gaps=sum(1 for i in range(1,n) if (T[i]-T[i-1]).total_seconds()>BARMIN*60*1.5)
print(f"{EPIC} {RES} | {n} velas | {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem | saltos de sesion: {gaps} | velas/dia habil ~{n/(weeks*5+60):.0f}")
def cache(bl,bm,rlo,rhi):
    sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=bl,bm,rlo,rhi
    sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    return sig,atrs
def sim(sig,atrs,trail,sides,real=True,slip=0.0):
    tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=min(pos['stop'],O[t]) if real else pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=max(pos['stop'],O[t]) if real else pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPR-slip,'side':s,'t_in':T[pos['t0']],'h':T[pos['t0']].hour}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        s='long' if sd=='BUY' else 'short'
        if s not in sides: continue
        if real and (t+1>=n or (T[t+1]-T[t]).total_seconds()>BARMIN*60*1.5): continue   # mercado cierra: la orden expira
        d=trail*a; c=C[t]
        pos={'side':s,'entry':c,'dist':d,'extreme':c,'t0':t,'stop':c-d if s=='long' else c+d}
    return tr
hdr=f"{'params':<19} {'lado':<6} {'trail':>5} | {'IDEAL neto':>10} {'PF':>5} | {'REAL neto':>9} {'PF':>5} {'acc':>4} {'tr/s':>5} {'maxDD':>6} {'3 tercios':>20} {'ROB':>3}"
print(hdr); print('-'*len(hdr)); rob=0; tot_c=0; keep={}
for bl,bm,rlo,rhi in ((14,2.0,30,70),(14,2.0,40,60),(20,2.0,35,65),(26,1.75,30,70),(26,1.75,40,60)):
    sig,atrs=cache(bl,bm,rlo,rhi)
    for sn,sides in (('2lados',('long','short')),('largo',('long',))):
        for trail in (2.0,3.0,4.0,5.0):
            a=sim(sig,atrs,trail,sides,real=False); b=sim(sig,atrs,trail,sides,real=True)
            if len(b)<30: continue
            ta,_,pfa,*_=br.stats(a,'net'); tb,wr,pfb,mdd,terc,rb=br.stats(b,'net'); tot_c+=1; rob+=rb==3
            print(f"BB{bl}/{bm} RSI{rlo}/{rhi:<3} {sn:<6} {trail:>5} | {ta:>+10.1f} {pfa:>5.2f} | {tb:>+9.1f} {pfb:>5.2f} {wr:>3.0f}% {len(b)/weeks:>5.1f} {mdd:>+6.1f} {terc[0]:>+6.1f}/{terc[1]:>+6.1f}/{terc[2]:>+6.1f} {rb:>3}")
            keep[(bl,bm,rlo,rhi,sn,trail)]=(sig,atrs,sides)
print(f"   -> REAL ROB3: {rob}/{tot_c}")
if RES=='MINUTE_15':
    for key in ((26,1.75,30,70,'2lados',2.0),(14,2.0,30,70,'2lados',2.0),(26,1.75,40,60,'largo',3.0)):
        if key not in keep: continue
        sig,atrs,sides=keep[key]; b=sim(sig,atrs,key[5],sides)
        tot,wr,pf,mdd,terc,rb=br.stats(b,'net'); nets=sorted([x['net'] for x in b],reverse=True)
        ms={}; [ms.__setitem__(x['t_in'].strftime('%Y-%m'),ms.get(x['t_in'].strftime('%Y-%m'),0)+x['net']) for x in b]
        by={}; [by.setdefault(x['h'],[]).append(x['net']) for x in b]
        print(f"\n## {key}: neto {tot:+.1f} | top5 {100*sum(nets[:5])/tot:.0f}% sinTop5 {tot-sum(nets[:5]):+.1f} | meses+ {sum(1 for v in ms.values() if v>0)}/{len(ms)} | largos {sum(x['net'] for x in b if x['side']=='long'):+.1f} cortos {sum(x['net'] for x in b if x['side']=='short'):+.1f}")
        print("   por hora UTC: "+' '.join(f"{h}h:{sum(v):+.0f}({len(v)})" for h,v in sorted(by.items())))
        for sl in (0.05,0.1,0.2,0.4):
            r=br.stats(sim(sig,atrs,key[5],sides,slip=sl),'net'); print(f"   desliz {sl}: {r[0]:+.1f} PF{r[2]:.2f} R{r[5]}")
sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=26,1.75,30,70
