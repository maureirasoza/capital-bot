#!/usr/bin/env python3
"""Trend oro, 2a pasada: palancas de OTRO tipo, cada una evaluada en ANTIGUO (2024, no visto) y
RECIENTE (600d) por separado sobre GOLD 1h 1000d reales. Base = Donchian 15/8 stop 5xATR 2 lados,
sin filtro y con filtro EMA200. Una palanca 'sirve' solo si mejora en los DOS tramos."""
import statistics
import backtest_real as br, bot_gold_trend as bt
O,H,L,C,T=br.fetch_capital('GOLD','HOUR',1000); n=len(C); WIN=400; SPREAD=0.3
TR=[H[0]-L[0]]+[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]; ATR=bt._rma(TR,14)
def ema(s,k):
    out=[s[0]]; a=2/(k+1)
    for x in s[1:]: out.append(x*a+out[-1]*(1-a))
    return out
E200=ema(C,200)
# ADX(14) Wilder
pdm=[0.0]; mdm=[0.0]
for i in range(1,n):
    up=H[i]-H[i-1]; dn=L[i-1]-L[i]; pdm.append(up if up>dn and up>0 else 0.0); mdm.append(dn if dn>up and dn>0 else 0.0)
sp_=bt._rma(pdm,14); sm_=bt._rma(mdm,14); dx=[0.0]*n
for i in range(n):
    if ATR[i] and sp_[i] is not None:
        pdi=100*sp_[i]/ATR[i]; mdi=100*sm_[i]/ATR[i]; dx[i]=100*abs(pdi-mdi)/(pdi+mdi) if pdi+mdi>0 else 0.0
ADX=bt._rma(dx[14:],14); ADX=[None]*14+ADX
HOUR=[t.hour for t in T]
cut=next(i for i,t in enumerate(T) if (T[-1]-t).days<=600)

def sim(a,b,ENT=15,EXIT=8,stop=5.0,emaf=True,adx=None,conf=None,pull=None,hours=None,pyr=None,tstop=None,dyn=False,sides=('long','short')):
    tr=[]; pos=None; pend=None
    def close(t,px):
        nonlocal pos
        sgn=1 if pos['side']=='long' else -1
        net=sum(sgn*(px-e)-2*SPREAD for e in pos['entries']); tr.append({'net':net,'t':t,'h':pos['h'],'side':pos['side'],'u':len(pos['entries'])}); pos=None
    for t in range(max(a,WIN),b):
        hh=max(H[t-ENT:t]); ll=min(L[t-ENT:t]); exited=False
        if pos:
            s=pos['side']
            if s=='long' and L[t]<=pos['stop']: close(t,pos['stop']); exited=True
            elif s=='short' and H[t]>=pos['stop']: close(t,pos['stop']); exited=True
            elif s=='long' and C[t]<min(L[t-EXIT:t]): close(t,C[t]); exited=True
            elif s=='short' and C[t]>max(H[t-EXIT:t]): close(t,C[t]); exited=True
            elif tstop and t-pos['t0']>=tstop and ((C[t]-pos['entries'][0])*(1 if s=='long' else -1))<=0: close(t,C[t]); exited=True
            else:
                if pyr and len(pos['entries'])<pyr[1]:
                    lvl=pos['entries'][-1]+(1 if s=='long' else -1)*pyr[0]*pos['atr']
                    if s=='long' and H[t]>=lvl: pos['entries'].append(max(lvl,O[t]))
                    elif s=='short' and L[t]<=lvl: pos['entries'].append(min(lvl,O[t]))
                d=stop*ATR[t] if dyn else pos['dist']
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-d)
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+d)
        if pos is None and pend and not exited:
            s=pend['side']
            if t>pend['exp']: pend=None
            elif pend['kind']=='pull':
                if s=='long' and L[t]<=pend['lvl']:
                    px=min(pend['lvl'],O[t]); d=stop*pend['atr']; pos={'side':s,'entries':[px],'dist':d,'atr':pend['atr'],'extreme':px,'stop':px-d,'t0':t,'h':HOUR[t]}; pend=None
                    if L[t]<=pos['stop']: close(t,pos['stop'])
                elif s=='short' and H[t]>=pend['lvl']:
                    px=max(pend['lvl'],O[t]); d=stop*pend['atr']; pos={'side':s,'entries':[px],'dist':d,'atr':pend['atr'],'extreme':px,'stop':px+d,'t0':t,'h':HOUR[t]}; pend=None
                    if H[t]>=pos['stop']: close(t,pos['stop'])
                continue
            elif pend['kind']=='hold':
                ok=(C[t]>pend['lvl']) if s=='long' else (C[t]<pend['lvl'])
                if ok:
                    d=stop*ATR[t]; pos={'side':s,'entries':[C[t]],'dist':d,'atr':ATR[t],'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d,'t0':t,'h':HOUR[t]}
                pend=None; continue
        if pos is None and not exited and not pend and ATR[t]:
            s='long' if C[t]>hh else 'short' if C[t]<ll else None
            if not s or s not in sides: continue
            if emaf and ((s=='long' and C[t]<E200[t]) or (s=='short' and C[t]>E200[t])): continue
            if adx and (ADX[t] is None or ADX[t]<adx): continue
            if hours and not hours(HOUR[t]): continue
            if conf and conf[0]=='top':
                rng=H[t]-L[t]; pct=((C[t]-L[t])/rng if s=='long' else (H[t]-C[t])/rng) if rng>0 else 1
                if pct<conf[1]: continue
            if conf and conf[0]=='hold': pend={'kind':'hold','side':s,'lvl':hh if s=='long' else ll,'exp':t+1}; continue
            if pull:
                lvl=(hh if s=='long' else ll) if pull[0]=='nivel' else (C[t]-pull[2]*ATR[t] if s=='long' else C[t]+pull[2]*ATR[t])
                pend={'kind':'pull','side':s,'lvl':lvl,'exp':t+pull[1],'atr':ATR[t]}; continue
            d=stop*ATR[t]; pos={'side':s,'entries':[C[t]],'dist':d,'atr':ATR[t],'extreme':C[t],'stop':C[t]-d if s=='long' else C[t]+d,'t0':t,'h':HOUR[t]}
    return tr
def st(tr):
    if len(tr)<10: return (len(tr),0,0,0)
    tot=sum(x['net'] for x in tr); w=sum(x['net'] for x in tr if x['net']>0); l=-sum(x['net'] for x in tr if x['net']<0); eq=pk=dd=0
    for x in tr: eq+=x['net']; pk=max(pk,eq); dd=min(dd,eq-pk)
    return (len(tr),tot,w/l if l else 9,dd)
BASE={}
def row(name,ref=None,**kw):
    a=st(sim(0,cut,**kw)); b=st(sim(cut,n,**kw)); c=st(sim(0,n,**kw))
    mark=''
    if ref:
        ra,rb=BASE[ref]; mark=' <<< mejora en ambos' if (a[1]>ra[1] and b[1]>rb[1] and a[2]>=ra[2] and b[2]>=rb[2]) else (' (PF mejor en ambos)' if (a[2]>ra[2] and b[2]>rb[2]) else '')
    print(f"{name:<44} | {a[0]:>4} {a[1]:>+6.0f} {a[2]:>5.2f} {a[3]:>+5.0f} | {b[0]:>4} {b[1]:>+6.0f} {b[2]:>5.2f} {b[3]:>+5.0f} | {c[0]:>4} {c[1]:>+6.0f} {c[2]:>5.2f} {c[3]:>+5.0f}{mark}")
    return a,b
print(f"ANTIGUO {T[WIN]:%Y-%m-%d}->{T[cut]:%Y-%m-%d} | RECIENTE ->{T[-1]:%Y-%m-%d}")
print(f"{'variante':<44} | {'ANTIGUO: tr neto PF DD':^23} | {'RECIENTE':^23} | {'TOTAL 1000d':^23}")
BASE['sin']=row("BASE actual (sin filtro)",emaf=False)
BASE['ema']=row("BASE + filtro EMA200")
print("-- fuerza de tendencia (ADX) sobre base+EMA200 --")
for v in (15,20,25,30): row(f"  ADX >= {v}",'ema',adx=v)
print("-- confirmacion de la ruptura --")
for q in (0.5,0.7): row(f"  cierre en el {int(q*100)}% superior de la vela",'ema',conf=('top',q))
row("  esperar 1 vela: sigue fuera del canal",'ema',conf=('hold',))
print("-- entrar en el RETROCESO (orden limite) en vez de al cierre --")
for N in (3,6,12): row(f"  limite en el nivel roto, vida {N} velas",'ema',pull=('nivel',N,0))
for off in (0.25,0.5,1.0): row(f"  limite a cierre -{off}xATR, vida 6 velas",'ema',pull=('off',6,off))
print("-- horario de entrada (UTC) --")
for nm,f in (("Asia 22-06",lambda h:h>=22 or h<6),("Londres 06-12",lambda h:6<=h<12),("NY 12-20",lambda h:12<=h<20),("sin Asia (06-22)",lambda h:6<=h<22),("sin NY (fuera 12-20)",lambda h:not(12<=h<20))):
    row(f"  solo {nm}",'ema',hours=f)
print("-- piramidar: agregar 1 unidad cada k x ATR a favor (stop comun) --")
for k,m in ((1.0,2),(2.0,2),(3.0,2),(2.0,3),(3.0,3)): row(f"  +1 unidad cada {k}xATR, max {m}",'ema',pyr=(k,m))
print("-- salidas --")
for N in (6,12,24): row(f"  salida por tiempo: {N} velas sin ganancia",'ema',tstop=N)
row("  stop dinamico (ATR actual)",'ema',dyn=True)
for ex in (5,10,12,15): row(f"  canal de salida {ex}",'ema',EXIT=ex)
for sm in (4.0,6.0): row(f"  stop {sm}xATR",'ema',stop=sm)
# perfil horario para referencia
print("\nP&L por hora de entrada (base+EMA200): ANTIGUO | RECIENTE")
ta=sim(0,cut); tb=sim(cut,n)
for blk,f in (("22-02",lambda h:h>=22 or h<2),("02-06",lambda h:2<=h<6),("06-09",lambda h:6<=h<9),("09-12",lambda h:9<=h<12),("12-15",lambda h:12<=h<15),("15-18",lambda h:15<=h<18),("18-22",lambda h:18<=h<22)):
    xa=[x['net'] for x in ta if f(x['h'])]; xb=[x['net'] for x in tb if f(x['h'])]
    print(f"  {blk} UTC: {len(xa):>3} tr {sum(xa):>+6.0f} | {len(xb):>3} tr {sum(xb):>+6.0f}")
