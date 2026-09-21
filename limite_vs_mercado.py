#!/usr/bin/env python3
"""
LIMITE vs MERCADO para los bots de entrada a mercado.
Idea: en vez de comprar a mercado ~1 min despues del cierre (pagando el desliz medido de
~1-2 pts), colocar una orden LIMITE al precio de cierre de la vela de senal (o con descuento),
valida K velas. Si el precio vuelve, entras sin desliz; si se escapa, te pierdes la operacion.
Mide el trade-off real: ahorro de desliz vs operaciones perdidas (y si las perdidas son
justamente las buenas).
OJO: distinto de pre-cargar en la banda (ya probado y descartado: -513 vs +545); aqui la senal
SIGUE confirmandose con el cierre, solo cambia COMO se ejecuta la entrada.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-bot")))
import backtest_real as br
import bot_gold_trend as bt, bot_gold as bg

def sim(O,H,L,C,T, sig_fn, trail, modo, slip=0.0, disc=0.0, K=2, spread=0.25, WIN=300):
    """modo: 'mercado' (entra en C[t] + slip) | 'limite' (orden en C[t]-/+disc*ATR, vence en K velas)"""
    n=len(C); trades=[]; pos=None; orden=None
    for t in range(WIN, n):
        if pos:
            s=pos['side']; ex=None
            if s=='long' and L[t]<=pos['stop']: ex=pos['stop']
            elif s=='short' and H[t]>=pos['stop']: ex=pos['stop']
            if ex is not None:
                g=(ex-pos['entry']) if s=='long' else (pos['entry']-ex)
                trades.append({'gross':g,'net':g-2*spread-(slip if modo=='mercado' else 0.0)}); pos=None
            else:
                if s=='long': pos['extreme']=max(pos['extreme'],H[t]); pos['stop']=max(pos['stop'],pos['extreme']-pos['dist'])
                else: pos['extreme']=min(pos['extreme'],L[t]); pos['stop']=min(pos['stop'],pos['extreme']+pos['dist'])
            continue
        if orden:
            s,lvl,dist,exp = orden
            hit = (s=='long' and L[t]<=lvl) or (s=='short' and H[t]>=lvl)
            if hit:
                pos={'side':s,'entry':lvl,'dist':dist,'extreme':lvl,'stop':lvl-dist if s=='long' else lvl+dist}
                orden=None; continue
            elif t>=exp: orden=None
        if pos is None and orden is None:
            lo=t-WIN+1
            side,atr = sig_fn(O[lo:t+1],H[lo:t+1],L[lo:t+1],C[lo:t+1])
            if side and atr:
                s='long' if side=='BUY' else 'short'; d=trail*atr; c=C[t]
                if modo=='mercado':
                    e=c+slip if s=='long' else c-slip   # entras peor
                    pos={'side':s,'entry':e,'dist':d,'extreme':e,'stop':e-d if s=='long' else e+d}
                else:
                    lvl = c-disc*atr if s=='long' else c+disc*atr
                    orden=(s,lvl,d,t+K)
    return trades

def sig_boll(o,h,l,c):
    s=bg.signal_last(o,h,l,c); return s['side'], s['atr']
def sig_trend(o,h,l,c):
    s=bt.signal_at(o,h,l,c,len(c)-1)
    return ('BUY' if s['long_break'] else ('SELL' if s['short_break'] else None)), s['atr']

for nombre, epic, res, dias, sig_fn, trail, WIN, spread, slip_real in (
    ('Oro Bollinger 15m','GOLD','MINUTE_15',300, sig_boll, bg.TRAIL_ATR, 300, 0.25, 1.5),
    ('Oro Trend 1h',     'GOLD','HOUR',     600, sig_trend, bt.ATR_STOP, 200, 0.25, 0.8)):
    O,H,L,C,T = br.fetch_capital(epic,res,dias)
    print(f"\n{'='*92}\n### {nombre}  (desliz real medido ~{slip_real} pts)\n{'='*92}")
    print(f"  {'variante':<34} {'#tr':>4} {'NETO':>8} {'PF':>5} {'acc%':>5} {'3 tercios':>22} ROB")
    print("  "+"-"*84)
    base=None
    for etiq, modo, kw in (
        ('MERCADO sin desliz (ideal)','mercado',{'slip':0.0}),
        (f'MERCADO con desliz {slip_real}','mercado',{'slip':slip_real}),
        ('LIMITE al cierre, vence 1v','limite',{'disc':0.0,'K':1}),
        ('LIMITE al cierre, vence 2v','limite',{'disc':0.0,'K':2}),
        ('LIMITE al cierre, vence 4v','limite',{'disc':0.0,'K':4}),
        ('LIMITE -0.25xATR, vence 4v','limite',{'disc':0.25,'K':4}),
        ('LIMITE -0.50xATR, vence 8v','limite',{'disc':0.50,'K':8}),
    ):
        tr=sim(O,H,L,C,T,sig_fn,trail,modo,spread=spread,WIN=WIN,**kw)
        if not tr: print(f"  {etiq:<34}  sin trades"); continue
        tot,wr,pf,mdd,terc,rob=br.stats(tr,'net')
        if base is None: base=tot
        print(f"  {etiq:<34} {len(tr):>4} {tot:>+8.0f} {pf:>5.2f} {wr:>4.1f}% {terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} ROB{rob}{' <<' if rob==3 else ''}")
