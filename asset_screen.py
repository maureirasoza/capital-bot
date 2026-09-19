#!/usr/bin/env python3
"""
SCREENING GENERICO de un instrumento de capital.com sobre datos REALES congelados (fetch_capital),
con motores de entrada = codigo REAL de los bots:
  - reversion: gold-bot/bot_gold.signal_last  (BB+RSI+filtro ADX/EMA200)   [BB x RSI x filtro]
  - tendencia: capital-demo/bot_gold_trend.signal_at (Donchian 2 lados)      [ENT/EXIT]
x lado (2 lados | largo | corto) x salida (trailing X x ATR | SL/TP fijo | canal Donchian +/- trailing).
Uso: python asset_screen.py EPIC RESOLUCION DIAS MEDIO_SPREAD   (ej: US30 HOUR 600 1.0)
Criterio: ROB3 + meseta; flag * si >=3 trades/sem.
"""
import sys, time
import backtest_real as br
import bot_gold_trend as bt

EPIC = sys.argv[1]; RES = sys.argv[2]; DAYS = int(sys.argv[3]); SPREAD = float(sys.argv[4])
WIN = 300
bg = br._import_bollinger()
O, H, L, C, T = br.fetch_capital(EPIC, RES, DAYS)
n = len(C); weeks = (T[-1] - T[WIN]).days / 7
print(f"{EPIC} {RES} REAL | {n} velas | {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem | spread {SPREAD}x2")


def cache_rev(bl, bm, rlo, rhi, adx):
    bg.BB_LEN, bg.BB_MULT, bg.RSI_LOW, bg.RSI_HIGH, bg.ADX_MIN = bl, bm, rlo, rhi, adx
    out = [None] * n
    for t in range(WIN, n):
        lo = t - WIN + 1
        s = bg.signal_last(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1])
        out[t] = (s["side"], s["atr"], C[t], None, None)
    return out


def cache_don(ent, ex):
    bt.ENT, bt.EXIT = ent, ex
    out = [None] * n
    for t in range(WIN, n):
        lo = t - WIN + 1
        s = bt.signal_at(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1], WIN - 1)
        side = "BUY" if s["long_break"] else ("SELL" if s["short_break"] else None)
        out[t] = (side, s["atr"], C[t], s["exit_long"], s["exit_short"])
    return out


def sim(sigs, sides, kind, p1, p2=None, chan=False):
    trades = []; pos = None
    for t in range(WIN, n):
        if pos:
            s = pos["side"]; ex = None
            if kind == "trail":
                if s == "long" and L[t] <= pos["stop"]: ex = pos["stop"]
                elif s == "short" and H[t] >= pos["stop"]: ex = pos["stop"]
                elif chan and ((s == "long" and sigs[t][3]) or (s == "short" and sigs[t][4])): ex = C[t]
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
        side, atr, close, _, _ = sigs[t]
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
REV_EXITS = [("trail", m, None, False) for m in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0)] + \
            [("fixed", a, b, False) for a, b in ((1.0, 1.5), (1.0, 2.0), (1.5, 3.0), (2.0, 3.0), (2.0, 4.0))]
DON_EXITS = [("trail", m, None, ch) for m in (2.0, 4.0, 6.0, 8.0) for ch in (True, False)]
MIN_TR = 40

rows = []; t0 = time.time()
for bl, bm in ((26, 1.75), (20, 2.0), (14, 2.0)):
    for rlo, rhi in ((30, 70), (35, 65), (40, 60)):
        for adx in (20, 1000):
            name = f"REV BB{bl}/{bm} RSI{rlo}/{rhi} f{'on' if adx < 999 else 'off'}"
            sg = cache_rev(bl, bm, rlo, rhi, adx)
            for sname, sides in SIDES.items():
                for kind, p1, p2, ch in REV_EXITS:
                    tr = sim(sg, sides, kind, p1, p2, ch)
                    if len(tr) < MIN_TR: continue
                    tot, wr, pf, mdd, terc, rob = br.stats(tr, "net")
                    ex = f"trail{p1}" if kind == "trail" else f"SL{p1}/TP{p2}"
                    rows.append((rob, tot, pf, wr, mdd, terc, len(tr), f"{name} {sname:<6} {ex}"))
for ent in (5, 10, 20, 30, 50):
    ex_n = max(3, ent // 2); name = f"DON {ent}/{ex_n}"
    sg = cache_don(ent, ex_n)
    for sname, sides in SIDES.items():
        for kind, p1, p2, ch in DON_EXITS:
            tr = sim(sg, sides, kind, p1, p2, ch)
            if len(tr) < MIN_TR: continue
            tot, wr, pf, mdd, terc, rob = br.stats(tr, "net")
            rows.append((rob, tot, pf, wr, mdd, terc, len(tr), f"{name} {sname:<6} trail{p1}{'+canal' if ch else ''}"))

hdr = f"{'config':<44} {'#tr':>4} {'tr/sem':>6} {'NETO':>8} {'PF':>5} {'acc%':>5} {'maxDD':>8}  {'3 tercios':>24}  ROB"
print(f"{len(rows)} configs ({time.time()-t0:.0f}s). == ROB3 con >=3 tr/sem (por PF) =="); print(hdr); print("-" * len(hdr))
freq3 = sorted([r for r in rows if r[0] == 3 and r[6] / weeks >= 3], key=lambda r: -r[2])
for rob, tot, pf, wr, mdd, terc, ntr, name in freq3[:15]:
    print(f"{name:<44} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+8.1f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+8.1f}  {terc[0]:>+7.1f}/{terc[1]:>+7.1f}/{terc[2]:>+7.1f}  ROB3 *")
if not freq3: print("  (ninguna)")
print("== otras ROB3 (por neto, <3 tr/sem) ==");
for rob, tot, pf, wr, mdd, terc, ntr, name in sorted([r for r in rows if r[0] == 3 and r[6] / weeks < 3], key=lambda r: -r[1])[:6]:
    print(f"{name:<44} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+8.1f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+8.1f}  {terc[0]:>+7.1f}/{terc[1]:>+7.1f}/{terc[2]:>+7.1f}  ROB3")
print(f"total ROB3: {sum(1 for r in rows if r[0]==3)} de {len(rows)}")
