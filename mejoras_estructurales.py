#!/usr/bin/env python3
"""Dos ideas estructurales sobre datos reales congelados:
 (1) BREAK-EVEN: en los bots de trailing puro (Bollinger oro, SP500, US30), mover el stop a la
     entrada (+spread) cuando la ganancia flotante supera k x ATR. Se mantiene el trailing.
 (2) FVG (617 trades, el de mayor n): barrido de TP_R, FILL_WIN, MIN_GAP y EMA_TREND por
     monkeypatch del modulo real."""
import sys; sys.argv=['x','--source','capital']
import backtest_real as br

def sim_be(O,H,L,C,T,mod,trail,SPREAD,be_k,WIN=300):
    n=len(C); sig=[None]*n; atrs=[None]*n
    for t in range(WIN,n):
        lo=t-WIN+1; s=mod.signal_last(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1]); sig[t]=s['side']; atrs[t]=s['atr']
    def run(be):
        tr=[]; pos=None
        for t in range(WIN,n):
            if pos:
                s=pos['side']; ex=None
                if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
                elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
                if ex is not None:
                    g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex); tr.append({'net':g-2*SPREAD}); pos=None
                else:
                    if s=='long':
                        pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                        if be and C[t]-pos['entry']>=be*pos['atr']: pos['stop']=max(pos['stop'],pos['entry']+2*SPREAD)
                    else:
                        pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
                        if be and pos['entry']-C[t]>=be*pos['atr']: pos['stop']=min(pos['stop'],pos['entry']-2*SPREAD)
                continue
            sd=sig[t]; a=atrs[t]
            if not sd or not a: continue
            s='long' if sd=='BUY' else 'short'; d=trail*a; c=C[t]
            pos={'side':s,'entry':c,'dist':d,'extreme':c,'atr':a,'stop':c-d if s=='long' else c+d}
        return tr
    return {be:run(be) for be in be_k}

hdr=f"{'bot / break-even':<34} {'#tr':>4} {'NETO':>7} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>20} {'ROB':>3}"
def show(name,tr):
    tot,wr,pf,mdd,terc,rob=br.stats(tr,'net'); print(f"{name:<34} {len(tr):>4} {tot:>+7.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} {rob:>3}")
print("=== (1) BREAK-EVEN tras k x ATR de ganancia (0 = como esta hoy) ==="); print(hdr); print('-'*len(hdr))
bg=br._import_bollinger(); (O,H,L,C,T),_=br._fetch_15m("GOLD","GC=F")
for be,tr in sim_be(O,H,L,C,T,bg,bg.TRAIL_ATR,0.3,(0,1.0,2.0,3.0)).items(): show(f"Bollinger oro 5x / BE {be}xATR",tr)
import bot_sp500 as sp; O,H,L,C,T=br.fetch_capital('US500','MINUTE_15',300)
for be,tr in sim_be(O,H,L,C,T,sp,sp.TRAIL_ATR,0.3,(0,1.0,2.0,3.0)).items(): show(f"SP500 4x / BE {be}xATR",tr)
import bot_us30 as us; O,H,L,C,T=br.fetch_capital('US30','MINUTE_15',300)
for be,tr in sim_be(O,H,L,C,T,us,us.TRAIL_ATR,1.0,(0,1.0,2.0,3.0)).items(): show(f"US30 5x / BE {be}xATR",tr)

print("\n=== (2) FVG oro 15m 300d — barrido de parametros NO testeados (motor real) ===")
fv=br._import_fvg(); (O,H,L,C,T),_=br._fetch_15m("GOLD","GC=F")
base=dict(TP_R=fv.TP_R,FILL_WIN=fv.FILL_WIN,MIN_GAP=fv.MIN_GAP,EMA_TREND=fv.EMA_TREND,SL_MULT=fv.SL_MULT)
hdr2=f"{'variante':<30} {'#tr':>4} {'NETO':>6} {'PF':>5} {'acc':>4} {'maxDD':>6} {'3 tercios':>18} {'ROB':>3}"; print(hdr2); print('-'*len(hdr2))
def fvg(name,**kw):
    for k,v in base.items(): setattr(fv,k,v)
    for k,v in kw.items(): setattr(fv,k,v)
    tr=br.simulate_fvg(O,H,L,C,T,fv); tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
    print(f"{name:<30} {len(tr):>4} {tot:>+6.0f} {pf:>5.2f} {wr:>3.0f}% {mdd:>+6.0f} {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} {rob:>3}")
fvg("ACTUAL (SL1.5 TP1.0 vida20 min0.4 EMA50)")
for v in (0.75,1.25,1.5,2.0): fvg(f"TP_R {v}",TP_R=v)
for v in (10,30,40): fvg(f"FILL_WIN {v}",FILL_WIN=v)
for v in (0.2,0.6,0.8): fvg(f"MIN_GAP {v}",MIN_GAP=v)
for v in (20,100,200): fvg(f"EMA_TREND {v}",EMA_TREND=v)
for sl,tp in ((1.0,1.5),(2.0,1.5),(1.5,1.25)): fvg(f"SL {sl} / TP {tp}",SL_MULT=sl,TP_R=tp)
for k,v in base.items(): setattr(fv,k,v)
