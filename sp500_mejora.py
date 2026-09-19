#!/usr/bin/env python3
"""
Busqueda de algo BUENO para SP500 (US500) con varias entradas/semana, sobre datos REALES de
capital.com (US500 15m, 300d, dataset congelado). Motores de entrada = codigo REAL de los bots:
  (a) bot_sp500.signal_last  : cruce de banda Bollinger puro, 2 lados (varias BB)
  (b) bot_gold.signal_last   : BB26/1.75 + RSI + filtro direccional ADX/EMA200 (varios RSI, filtro on/off)
x lado (2 lados | largo | corto) x salida (trailing 3-8x ATR | SL/TP fijo x ATR).
Criterio: ROB3 en 300d reales; preferencia >= 3 trades/semana (para validar en vivo rapido).
"""
import sys, os, time
import backtest_real as br

WIN = 300; SPREAD = 0.3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_sp500 as sp
bg = br._import_bollinger()
O, H, L, C, T = br.fetch_capital("US500", "MINUTE_15", 300)
n = len(C); weeks = (T[-1] - T[WIN]).days / 7
print(f"US500 15m REAL | {n} velas | {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem | spread {SPREAD}x2")


def cache(fn):
    out = [None] * n
    for t in range(WIN, n):
        lo = t - WIN + 1
        s = fn(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1])
        out[t] = (s["side"], s["atr"], C[t])
    return out


def sim(sigs, sides, kind, p1, p2=None):
    trades = []; pos = None
    for t in range(WIN, n):
        if pos:
            s = pos["side"]; ex = None
            if kind == "trail":
                if s == "long" and L[t] <= pos["stop"]: ex = pos["stop"]
                elif s == "short" and H[t] >= pos["stop"]: ex = pos["stop"]
            else:
                if s == "long":
                    if L[t] <= pos["sl"]: ex = pos["sl"]
                    elif H[t] >= pos["tp"]: ex = pos["tp"]
                else:
                    if H[t] >= pos["sl"]: ex = pos["sl"]
                    elif L[t] <= pos["tp"]: ex = pos["tp"]
            if ex is not None:
                g = (ex - pos["entry"]) if s == "long" else (pos["entry"] - ex)
                trades.append({"gross": g, "net": g - 2 * SPREAD}); pos = None
            elif kind == "trail":
                if s == "long":
                    pos["extreme"] = max(pos["extreme"], H[t]); pos["stop"] = max(pos["stop"], pos["extreme"] - pos["dist"])
                else:
                    pos["extreme"] = min(pos["extreme"], L[t]); pos["stop"] = min(pos["stop"], pos["extreme"] + pos["dist"])
            continue
        side, atr, close = sigs[t]
        if not side or not atr: continue
        s = "long" if side == "BUY" else "short"
        if s not in sides: continue
        if kind == "trail":
            d = p1 * atr
            pos = {"side": s, "entry": close, "dist": d, "extreme": close, "stop": close - d if s == "long" else close + d}
        else:
            pos = {"side": s, "entry": close,
                   "sl": close - p1 * atr if s == "long" else close + p1 * atr,
                   "tp": close + p2 * atr if s == "long" else close - p2 * atr}
    return trades


SIDES = {"2lados": ("long", "short"), "largo": ("long",), "corto": ("short",)}
EXITS = [("trail", 3.0, None), ("trail", 4.0, None), ("trail", 5.0, None), ("trail", 6.0, None), ("trail", 8.0, None),
         ("fixed", 1.15, 1.5), ("fixed", 1.0, 1.5), ("fixed", 1.5, 1.5), ("fixed", 1.0, 2.0), ("fixed", 1.5, 3.0), ("fixed", 2.0, 3.0)]

engines = []
for bl, bm in ((26, 1.75), (20, 2.0), (20, 1.5), (30, 2.0)):
    def f(o, h, l, c, bl=bl, bm=bm):
        sp.BB_LEN, sp.BB_MULT = bl, bm
        return sp.signal_last(o, h, l, c)
    engines.append((f"BBpuro{bl}/{bm}", f))
for (rlo, rhi) in ((38, 62), (35, 65), (30, 70)):
    for adx in (20, 1000):
        def g(o, h, l, c, rlo=rlo, rhi=rhi, adx=adx):
            bg.RSI_LOW, bg.RSI_HIGH, bg.ADX_MIN = rlo, rhi, adx
            return bg.signal_last(o, h, l, c)
        engines.append((f"BBRSI{rlo}/{rhi}f{'on' if adx < 999 else 'off'}", g))

rows = []; t0 = time.time()
for name, fn in engines:
    sg = cache(fn)
    print(f"  {name} listo ({time.time()-t0:.0f}s)")
    for sname, sides in SIDES.items():
        for kind, p1, p2 in EXITS:
            tr = sim(sg, sides, kind, p1, p2)
            if len(tr) < 40: continue
            tot, wr, pf, mdd, terc, rob = br.stats(tr, "net")
            ex = f"trail{p1}" if kind == "trail" else f"SL{p1}/TP{p2}"
            rows.append((rob, tot, pf, wr, mdd, terc, len(tr), f"{name} {sname:<6} {ex}"))

hdr = f"{'config':<40} {'#tr':>4} {'tr/sem':>6} {'NETO':>6} {'PF':>5} {'acc%':>5} {'maxDD':>6}  {'3 tercios':>18}  ROB"
print(f"\n{len(rows)} configs. == ROB3 (por neto; * = >=3 tr/sem) =="); print(hdr); print("-" * len(hdr))
r3 = sorted([r for r in rows if r[0] == 3], key=lambda r: -r[1])
for rob, tot, pf, wr, mdd, terc, ntr, name in r3:
    print(f"{name:<40} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+6.0f}  {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f}  ROB3{' *' if ntr/weeks >= 3 else ''}")
if not r3: print("  (ninguna ROB3)")
print("\n== Mejores ROB2 (referencia) =="); print(hdr); print("-" * len(hdr))
for rob, tot, pf, wr, mdd, terc, ntr, name in sorted([r for r in rows if r[0] == 2], key=lambda r: -r[1])[:8]:
    print(f"{name:<40} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+6.0f}  {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f}  ROB2")
