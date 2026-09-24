#!/usr/bin/env python3
"""Perfil horario del SP500 v2 (trail4, entrada limite=close): P&L por hora de ENTRADA (UTC),
exclusiones finas de sesion, y validacion cruzada en 1h/600d."""
import statistics
import backtest_real as br, bot_sp500 as sp

def run(epic,res,days,WIN=300,trail=4.0,SPREAD=0.3):
    O,H,L,C,T=br.fetch_capital(epic,res,days); n=len(C)
    print("   tz de T:",T[0].tzinfo, "| rango", T[WIN].date(),"->",T[-1].date())
    sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=sp.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    weeks=(T[-1]-T[WIN]).days/7
    def sim(allow):
        tr=[]; pos=None
        for t in range(WIN,n):
            if pos:
                s=pos['side']; ex=None
                if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
                elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
                if ex is not None:
                    g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'gross':g,'net':g-2*SPREAD,'h':pos['h'],'side':s,'t':T[pos['t0']]}); pos=None
                else:
                    if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                    else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
                continue
            sd=sig[t]; a=atrs[t]
            if not sd or not a: continue
            h=T[t].hour+T[t].minute/60
            if not allow(h): continue
            s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
            pos={'side':s,'entry':c,'dist':d,'extreme':c,'t0':t,'h':h,'stop':c-d if s=='long' else c+d}
        return tr
    return sim,weeks

print("=== US500 15m 300d ===")
sim,weeks=run('US500','MINUTE_15',300)
base=sim(lambda h:True)
print("\n-- P&L neto por hora de entrada (UTC), config actual --")
by={}
for x in base: by.setdefault(int(x['h']),[]).append(x['net'])
print(f"{'hora':>5} {'n':>4} {'neto':>7} {'media':>7} {'acc':>5}")
for h in sorted(by):
    v=by[h]; print(f"{h:>3}h {len(v):>4} {sum(v):>+7.0f} {statistics.mean(v):>+7.1f} {100*sum(1 for z in v if z>0)/len(v):>4.0f}%")
print("\n-- exclusiones finas (trail 4.0) --")
EX={'ninguna (actual)':lambda h:True,
    'fuera 13:30-20 (WallSt)':lambda h:not(13.5<=h<20),
    'fuera 13:30-16 (apertura)':lambda h:not(13.5<=h<16),
    'fuera 16-20 (tarde/cierre)':lambda h:not(16<=h<20),
    'fuera 13:30-22':lambda h:not(13.5<=h<22),
    'fuera 12-20':lambda h:not(12<=h<20),
    'solo 07-13:30 (Europa)':lambda h:7<=h<13.5,
    'solo 00-07 (Asia)':lambda h:h<7,
    'solo 20-24':lambda h:h>=20}
hdr=f"{'exclusion':<28} {'tr/sem':>6} {'NETO':>6} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>18} {'peor':>6}"; print(hdr); print('-'*len(hdr))
res15={}
for k,f in EX.items():
    tr=sim(f)
    if len(tr)<20: print(f"{k:<28} {len(tr)} trades (pocos)"); continue
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); res15[k]=(tot,pf,terc)
    print(f"{k:<28} {len(tr)/weeks:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {min(terc):>+6.0f}")

print("\n=== VALIDACION CRUZADA: US500 1h 600d (mismo motor, trail 4.0) ===")
sim,weeks=run('US500','HOUR',600)
print(hdr); print('-'*len(hdr))
for k,f in EX.items():
    tr=sim(f)
    if len(tr)<20: print(f"{k:<28} {len(tr)} trades (pocos)"); continue
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
    print(f"{k:<28} {len(tr)/weeks:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {min(terc):>+6.0f}")
