#!/usr/bin/env python3
"""RTY (Russell 2000) a fondo con el motor SP500: fragilidad, lados, horas, desliz, y
correlacion/solape con el bot SP500 (US500) sobre el mismo periodo de 300d reales."""
import statistics
import backtest_real as br, bot_sp500 as sp
WIN=300
def prep(epic,bl,bm,rlo,rhi):
    O,H,L,C,T=br.fetch_capital(epic,'MINUTE_15',300); n=len(C)
    sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=bl,bm,rlo,rhi
    sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    return O,H,L,C,T,sig,atrs
def sim(D,trail,SPREAD,slip=0.0,allow=None):
    O,H,L,C,T,sig,atrs=D; n=len(C); tr=[]; pos=None
    for t in range(WIN,n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex)
                tr.append({'net':g-2*SPREAD-slip,'side':s,'t_in':T[pos['t0']],'t_out':T[t],'h':T[pos['t0']].hour,'risk':pos['dist']}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        sd=sig[t]; a=atrs[t]
        if not sd or not a: continue
        if allow and not allow(T[t].hour): continue
        s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
        pos={'side':s,'entry':c,'dist':d,'extreme':c,'t0':t,'stop':c-d if s=='long' else c+d}
    return tr
def linea(n_,tr,weeks):
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); nets=sorted([x['net'] for x in tr],reverse=True); t5=sum(nets[:5])
    ms={}; [ms.__setitem__(x['t_in'].strftime('%Y-%m'),ms.get(x['t_in'].strftime('%Y-%m'),0)+x['net']) for x in tr]
    print(f"{n_:<38} {len(tr)/weeks:>4.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+5.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} R{rob} top5 {100*t5/tot if tot>0 else 0:>3.0f}% sinTop5 {tot-t5:>+5.0f} meses+ {sum(1 for v in ms.values() if v>0)}/{len(ms)}")
    return tot,mdd
CFG={'SP500-exacta BB26/1.75 30/70 t4':(26,1.75,30,70,4.0),'params US30 BB20/2.0 35/65 t4':(20,2.0,35,65,4.0),'params US30 BB20/2.0 35/65 t5':(20,2.0,35,65,5.0)}
res={}
for name,(bl,bm,rlo,rhi,trail) in CFG.items():
    D=prep('RTY',bl,bm,rlo,rhi); T=D[4]; weeks=(T[-1]-T[WIN]).days/7
    print(f"\n##### RTY — {name} #####")
    print(f"{'':<38} {'tr/s':>4} {'NETO':>6} {'PF':>5} {'acc':>4} {'DD':>5} {'3 tercios':>17}")
    base=sim(D,trail,0.25); tot,mdd=linea("base (spread 0.5)",base,weeks); res[name]=(base,tot,mdd,weeks)
    linea("  solo largos",[x for x in base if x['side']=='long'],weeks); linea("  solo cortos",[x for x in base if x['side']=='short'],weeks)
    linea("  SIN entradas 20-23h UTC",sim(D,trail,0.25,allow=lambda h:not(20<=h<23)),weeks)
    linea("  SIN entradas 13-20h UTC (WallSt)",sim(D,trail,0.25,allow=lambda h:not(13<=h<20)),weeks)
    for sl in (0.25,0.5,1.0): linea(f"  desliz {sl} pts",sim(D,trail,0.25,slip=sl),weeks)
    rk=statistics.mean(x['risk'] for x in base); print(f"  riesgo inicial medio {rk:.1f} pts | perdida media {statistics.mean(-x['net'] for x in base if x['net']<0):.1f} | ganancia media {statistics.mean(x['net'] for x in base if x['net']>0):.1f}")
# correlacion con el bot SP500
D5=prep('US500',26,1.75,30,70); s5=sim(D5,4.0,0.3)
def semanal(tr):
    d={}
    for x in tr: k=x['t_out'].strftime('%G-%V'); d[k]=d.get(k,0)+x['net']
    return d
print("\n##### CORRELACION con el bot SP500 (P&L semanal, mismo periodo) #####")
w5=semanal(s5)
for name,(base,tot,mdd,weeks) in res.items():
    wr_=semanal(base); ks=sorted(set(w5)|set(wr_)); a=[w5.get(k,0) for k in ks]; b=[wr_.get(k,0) for k in ks]
    ma,mb=statistics.mean(a),statistics.mean(b); cov=sum((x-ma)*(y-mb) for x,y in zip(a,b)); corr=cov/((sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))**0.5)
    both_neg=sum(1 for x,y in zip(a,b) if x<0 and y<0); 
    # solape: fraccion de trades RTY que abren mientras SP500 esta en posicion del mismo lado
    same=0
    for x in base:
        for y in s5:
            if y['t_in']<=x['t_in']<=y['t_out']:
                same+= (y['side']==x['side']); break
    print(f"{name:<34} corr semanal {corr:+.2f} | semanas ambos negativos {both_neg}/{len(ks)} | trades RTY abiertos con SP500 ya en el mismo lado: {100*same/len(base):.0f}%")
sp.BB_LEN,sp.BB_MULT,sp.RSI_LOW,sp.RSI_HIGH=26,1.75,30,70
