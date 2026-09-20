#!/usr/bin/env python3
"""
ZOO DE ESTRATEGIAS: familias NO cubiertas por los bots actuales, sobre datos REALES congelados.
Uso: python strategy_zoo.py EPIC RESOLUCION DIAS MEDIO_SPREAD   (ej: ETHUSD HOUR 600 0.875)

Familias (senal en la vela t, ya cerrada; indicadores sobre la serie completa = exploratorio;
la ganadora se re-valida con ventana movil como el bot en vivo):
  EMAX   cruce de EMAs rapida/lenta (momentum)           params (f,s): 9/21, 12/26, 20/50, 50/200
  MACD   cruce de linea MACD con su senal                  params (12,26,9), (8,17,9)
  PULL   pullback EN tendencia: sobre EMA200 y RSI<X -> largo; bajo EMA200 y RSI>100-X -> corto  X: 35,40,45
  ATRBK  ruptura por volatilidad: close > close[t-1] + k*ATR -> largo (simetrico)             k: 1.0,1.5,2.0
  SQZ    squeeze Bollinger: ancho de banda en minimo de N velas y cierre rompe banda          N: 20,50
  ZS     reversion por z-score: (close-SMA(n))/stdev < -z -> largo; > z -> corto              (n,z): (20,2),(50,2),(50,2.5),(100,2)
  RSI    RSI puro: cruce bajo X -> largo; sobre 100-X -> corto                                 X: 25,30,35
  DONF   Donchian ENT con filtro EMA200 (solo a favor de la tendencia mayor)                   ENT: 10,20,30
Salidas: trailing 2/3/4/6/8 x ATR | SL/TP fijo (1,2),(1.5,3),(2,3) | TIEMPO N velas (8,24,48) con SL 2xATR.
Lados: 2 lados | largo | corto. Criterio: ROB3 + meseta; * si >=3 tr/sem.
"""
import sys, math, time
import backtest_real as br

EPIC = sys.argv[1]; RES = sys.argv[2]; DAYS = int(sys.argv[3]); SPREAD = float(sys.argv[4])
O, H, L, C, T = br.fetch_capital(EPIC, RES, DAYS)
n = len(C); WARM = 210; weeks = (T[-1] - T[WARM]).days / 7
print(f"{EPIC} {RES} REAL | {n} velas | {T[WARM]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem | spread {SPREAD}x2")


# ---------- indicadores (serie completa) ----------
def ema(s, k):
    out = [s[0]]; a = 2 / (k + 1)
    for i in range(1, len(s)): out.append(s[i] * a + out[-1] * (1 - a))
    return out
def rma(s, k):
    out = [None] * len(s)
    if len(s) < k: return out
    p = sum(s[:k]) / k; out[k-1] = p
    for i in range(k, len(s)): p = (p * (k-1) + s[i]) / k; out[i] = p
    return out
def atr_series(h, l, c, k):
    tr = [h[0]-l[0]] + [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))]
    return rma(tr, k)
def rsi_series(c, k):
    g, l = [0.0], [0.0]
    for i in range(1, len(c)):
        d = c[i]-c[i-1]; g.append(max(d, 0.0)); l.append(max(-d, 0.0))
    ag, al = rma(g, k), rma(l, k)
    return [None if ag[i] is None else (100.0 if al[i] == 0 else 100 - 100/(1 + ag[i]/al[i])) for i in range(len(c))]
def sma_series(s, k):
    out = [None] * len(s); acc = 0.0
    for i in range(len(s)):
        acc += s[i]
        if i >= k: acc -= s[i-k]
        if i >= k-1: out[i] = acc / k
    return out
def std_series(s, k):
    out = [None] * len(s)
    for i in range(k-1, len(s)):
        w = s[i-k+1:i+1]; m = sum(w) / k
        out[i] = math.sqrt(sum((x-m)**2 for x in w) / k)
    return out

ATR = atr_series(H, L, C, 14)
RSI = rsi_series(C, 14)
EMA200 = ema(C, 200)


# ---------- motores: devuelven lista sig[t] = 'long'|'short'|None ----------
def eng_emax(f, s):
    ef, es = ema(C, f), ema(C, s)
    return [None if t == 0 else ('long' if ef[t] > es[t] and ef[t-1] <= es[t-1] else ('short' if ef[t] < es[t] and ef[t-1] >= es[t-1] else None)) for t in range(n)]
def eng_macd(f, s, sig_k):
    ef, es = ema(C, f), ema(C, s); m = [ef[i]-es[i] for i in range(n)]; sg = ema(m, sig_k)
    return [None if t == 0 else ('long' if m[t] > sg[t] and m[t-1] <= sg[t-1] else ('short' if m[t] < sg[t] and m[t-1] >= sg[t-1] else None)) for t in range(n)]
def eng_pull(x):
    out = [None] * n
    for t in range(1, n):
        if RSI[t] is None or RSI[t-1] is None: continue
        if C[t] > EMA200[t] and RSI[t] < x <= RSI[t-1]: out[t] = 'long'
        elif C[t] < EMA200[t] and RSI[t] > 100-x >= RSI[t-1]: out[t] = 'short'
    return out
def eng_atrbk(k):
    out = [None] * n
    for t in range(1, n):
        if not ATR[t-1]: continue
        if C[t] > C[t-1] + k * ATR[t-1]: out[t] = 'long'
        elif C[t] < C[t-1] - k * ATR[t-1]: out[t] = 'short'
    return out
def eng_sqz(N, bb=20, mult=2.0):
    sm, sd = sma_series(C, bb), std_series(C, bb)
    width = [None if sm[i] is None else 2*mult*sd[i]/sm[i] for i in range(n)]
    out = [None] * n
    for t in range(bb+N, n):
        w = [x for x in width[t-N:t] if x is not None]
        if not w or width[t-1] is None or width[t-1] > min(w) * 1.05: continue   # venia en squeeze
        up, lo = sm[t] + mult*sd[t], sm[t] - mult*sd[t]
        if C[t] > up: out[t] = 'long'
        elif C[t] < lo: out[t] = 'short'
    return out
def eng_zs(k, z):
    sm, sd = sma_series(C, k), std_series(C, k)
    out = [None] * n
    for t in range(k, n):
        if not sd[t] or not sd[t-1]: continue
        zt, zp = (C[t]-sm[t])/sd[t], (C[t-1]-sm[t-1])/sd[t-1]
        if zt < -z <= zp: out[t] = 'long'
        elif zt > z >= zp: out[t] = 'short'
    return out
def eng_rsi(x):
    out = [None] * n
    for t in range(1, n):
        if RSI[t] is None or RSI[t-1] is None: continue
        if RSI[t] < x <= RSI[t-1]: out[t] = 'long'
        elif RSI[t] > 100-x >= RSI[t-1]: out[t] = 'short'
    return out
def eng_donf(ent):
    out = [None] * n
    for t in range(ent+1, n):
        hh, ll = max(H[t-ent:t]), min(L[t-ent:t])
        if C[t] > hh and C[t] > EMA200[t]: out[t] = 'long'
        elif C[t] < ll and C[t] < EMA200[t]: out[t] = 'short'
    return out


def sim(sig, sides, kind, p1, p2=None):
    """kind: trail(p1=mult) | fixed(p1=SL,p2=TP) | time(p1=N velas, SL 2xATR). SL primero. Sin look-ahead."""
    trades = []; pos = None
    for t in range(WARM, n):
        if pos:
            s = pos['side']; ex = None
            if kind == 'trail':
                if s == 'long' and L[t] <= pos['stop']: ex = pos['stop']
                elif s == 'short' and H[t] >= pos['stop']: ex = pos['stop']
            elif kind == 'fixed':
                if s == 'long':
                    if L[t] <= pos['sl']: ex = pos['sl']
                    elif H[t] >= pos['tp']: ex = pos['tp']
                else:
                    if H[t] >= pos['sl']: ex = pos['sl']
                    elif L[t] <= pos['tp']: ex = pos['tp']
            else:
                if s == 'long' and L[t] <= pos['sl']: ex = pos['sl']
                elif s == 'short' and H[t] >= pos['sl']: ex = pos['sl']
                elif t - pos['t0'] >= p1: ex = C[t]
            if ex is not None:
                g = (ex - pos['entry']) if s == 'long' else (pos['entry'] - ex)
                trades.append({'gross': g, 'net': g - 2*SPREAD}); pos = None
            elif kind == 'trail':
                if s == 'long': pos['extreme'] = max(pos['extreme'], H[t]); pos['stop'] = max(pos['stop'], pos['extreme'] - pos['dist'])
                else: pos['extreme'] = min(pos['extreme'], L[t]); pos['stop'] = min(pos['stop'], pos['extreme'] + pos['dist'])
            continue
        s = sig[t]; a = ATR[t]
        if not s or not a or s not in sides: continue
        c = C[t]
        if kind == 'trail':
            d = p1 * a; pos = {'side': s, 'entry': c, 'dist': d, 'extreme': c, 'stop': c - d if s == 'long' else c + d}
        elif kind == 'fixed':
            pos = {'side': s, 'entry': c, 'sl': c - p1*a if s == 'long' else c + p1*a, 'tp': c + p2*a if s == 'long' else c - p2*a}
        else:
            pos = {'side': s, 'entry': c, 't0': t, 'sl': c - 2*a if s == 'long' else c + 2*a}
    return trades


ENGINES = [(f"EMAX {f}/{s}", eng_emax(f, s)) for f, s in ((9, 21), (12, 26), (20, 50), (50, 200))] + \
          [(f"MACD {f}/{s}/{k}", eng_macd(f, s, k)) for f, s, k in ((12, 26, 9), (8, 17, 9))] + \
          [(f"PULL rsi{x}", eng_pull(x)) for x in (35, 40, 45)] + \
          [(f"ATRBK k{k}", eng_atrbk(k)) for k in (1.0, 1.5, 2.0)] + \
          [(f"SQZ N{N}", eng_sqz(N)) for N in (20, 50)] + \
          [(f"ZS {k}/{z}", eng_zs(k, z)) for k, z in ((20, 2.0), (50, 2.0), (50, 2.5), (100, 2.0))] + \
          [(f"RSI {x}", eng_rsi(x)) for x in (25, 30, 35)] + \
          [(f"DONF {e}", eng_donf(e)) for e in (10, 20, 30)]
SIDES = {'2lados': ('long', 'short'), 'largo': ('long',), 'corto': ('short',)}
EXITS = [('trail', m, None) for m in (2.0, 3.0, 4.0, 6.0, 8.0)] + [('fixed', a, b) for a, b in ((1.0, 2.0), (1.5, 3.0), (2.0, 3.0))] + \
        [('time', N, None) for N in (8, 24, 48)]

rows = []; t0 = time.time()
for name, sig in ENGINES:
    for sname, sides in SIDES.items():
        for kind, p1, p2 in EXITS:
            tr = sim(sig, sides, kind, p1, p2)
            if len(tr) < 40: continue
            tot, wr, pf, mdd, terc, rob = br.stats(tr, 'net')
            ex = f"trail{p1}" if kind == 'trail' else (f"SL{p1}/TP{p2}" if kind == 'fixed' else f"t{p1}v")
            rows.append((rob, tot, pf, wr, mdd, terc, len(tr), f"{name} {sname:<6} {ex}"))
hdr = f"{'config':<36} {'#tr':>4} {'tr/sem':>6} {'NETO':>8} {'PF':>5} {'acc%':>5} {'maxDD':>8}  {'3 tercios':>24}  ROB"
print(f"{len(rows)} configs ({time.time()-t0:.0f}s) | familias: {len(ENGINES)}. == ROB3 con >=3 tr/sem (por PF) =="); print(hdr); print("-" * len(hdr))
f3 = sorted([r for r in rows if r[0] == 3 and r[6]/weeks >= 3], key=lambda r: -r[2])
for rob, tot, pf, wr, mdd, terc, ntr, name in f3[:15]:
    print(f"{name:<36} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+8.1f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+8.1f}  {terc[0]:>+7.1f}/{terc[1]:>+7.1f}/{terc[2]:>+7.1f}  ROB3 *")
if not f3: print("  (ninguna)")
print("== otras ROB3 (<3 tr/sem, por PF) ==")
for rob, tot, pf, wr, mdd, terc, ntr, name in sorted([r for r in rows if r[0] == 3 and r[6]/weeks < 3], key=lambda r: -r[2])[:8]:
    print(f"{name:<36} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+8.1f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+8.1f}  {terc[0]:>+7.1f}/{terc[1]:>+7.1f}/{terc[2]:>+7.1f}  ROB3")
print(f"total ROB3: {sum(1 for r in rows if r[0]==3)} de {len(rows)} | por familia: " +
      ", ".join(f"{fam}={sum(1 for r in rows if r[0]==3 and r[7].startswith(fam))}" for fam in ('EMAX','MACD','PULL','ATRBK','SQZ','ZS','RSI','DONF')))
