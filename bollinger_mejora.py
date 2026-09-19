#!/usr/bin/env python3
"""
Busqueda de la MEJOR MEJORA para el Bollinger de oro, sobre datos REALES (capital.com GOLD 15m,
300d, dataset congelado en data/). Usa el signal_last REAL de gold-bot/bot_gold.py (misma logica
que en vivo) variando SOLO parametros del modulo (monkeypatch) y la mecanica de salida/lado.

Palancas:
  - entrada: RSI (38/62 actual | 35/65 | 30/70) x filtro direccional ADX/EMA200 (on | off)
  - lado:    2 lados | solo largo | solo corto
  - salida:  trailing X x ATR (3..6)  |  SL/TP fijo (SL,TP) x ATR (incl. 1.15/1.5 = config original)
Criterio: ROB3 (positivo en los 3 tercios) sobre 300d reales, buscando MESETA (vecinos tambien ROB3).
"""
import sys, time
import backtest_real as br

WIN = 300; SPREAD = 0.3
bg = br._import_bollinger()
O, H, L, C, T = br.fetch_capital("GOLD", "MINUTE_15", 300)   # lee la cache congelada
n = len(C); weeks = (T[-1] - T[WIN]).days / 7
print(f"GOLD 15m REAL | {n} velas | {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem | spread {SPREAD}x2")


def signals(rsi_lo, rsi_hi, adx_min):
    """Senal REAL del bot por vela (cacheada): (side, atr, close). Filtro off = ADX_MIN enorme."""
    bg.RSI_LOW, bg.RSI_HIGH, bg.ADX_MIN = rsi_lo, rsi_hi, adx_min
    out = [None] * n
    for t in range(WIN, n):
        lo = t - WIN + 1
        s = bg.signal_last(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1])
        out[t] = (s["side"], s["atr"], C[t])
    return out


def sim(sigs, sides, exit_kind, p1, p2=None):
    """exit_kind='trail': p1=mult. 'fixed': p1=SL mult, p2=TP mult. Sin look-ahead; SL primero."""
    trades = []; pos = None
    for t in range(WIN, n):
        if pos:
            s = pos["side"]; ex = None
            if exit_kind == "trail":
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
            elif exit_kind == "trail":
                if s == "long":
                    pos["extreme"] = max(pos["extreme"], H[t]); pos["stop"] = max(pos["stop"], pos["extreme"] - pos["dist"])
                else:
                    pos["extreme"] = min(pos["extreme"], L[t]); pos["stop"] = min(pos["stop"], pos["extreme"] + pos["dist"])
            continue
        side, atr, close = sigs[t]
        if not side or not atr: continue
        s = "long" if side == "BUY" else "short"
        if s not in sides: continue
        if exit_kind == "trail":
            d = p1 * atr
            pos = {"side": s, "entry": close, "dist": d, "extreme": close,
                   "stop": close - d if s == "long" else close + d}
        else:
            pos = {"side": s, "entry": close,
                   "sl": close - p1 * atr if s == "long" else close + p1 * atr,
                   "tp": close + p2 * atr if s == "long" else close - p2 * atr}
    return trades


ENTRIES = [((38, 62), 20), ((38, 62), 1000), ((35, 65), 20), ((35, 65), 1000), ((30, 70), 20), ((30, 70), 1000)]
SIDES = {"2lados": ("long", "short"), "largo": ("long",), "corto": ("short",)}
EXITS = [("trail", 3.0, None), ("trail", 3.5, None), ("trail", 4.0, None), ("trail", 5.0, None), ("trail", 6.0, None),
         ("fixed", 1.15, 1.5), ("fixed", 1.0, 1.5), ("fixed", 1.5, 1.5), ("fixed", 1.0, 2.0), ("fixed", 1.5, 3.0), ("fixed", 2.0, 3.0)]

rows = []
t0 = time.time()
for (rlo, rhi), adx in ENTRIES:
    sg = signals(rlo, rhi, adx)
    print(f"  senales RSI {rlo}/{rhi} filtro {'on' if adx < 999 else 'off'} listas ({time.time()-t0:.0f}s)")
    for sname, sides in SIDES.items():
        for kind, p1, p2 in EXITS:
            tr = sim(sg, sides, kind, p1, p2)
            if len(tr) < 30: continue
            tot, wr, pf, mdd, terc, rob = br.stats(tr, "net")
            ex = f"trail{p1}" if kind == "trail" else f"SL{p1}/TP{p2}"
            rows.append((rob, tot, pf, wr, mdd, terc, len(tr), f"RSI{rlo}/{rhi} f{'on' if adx<999 else 'off'} {sname:<6} {ex}"))

print(f"\n{len(rows)} configs simuladas. ACTUAL EN VIVO = RSI38/62 fon 2lados trail2.0 (no en grid; 3.0 si).\n")
hdr = f"{'config':<40} {'#tr':>4} {'tr/sem':>6} {'NETO':>6} {'PF':>5} {'acc%':>5} {'maxDD':>6}  {'3 tercios':>18}  ROB"
print("== TODAS las ROB3 (ordenadas por neto) =="); print(hdr); print("-" * len(hdr))
rob3 = sorted([r for r in rows if r[0] == 3], key=lambda r: -r[1])
for rob, tot, pf, wr, mdd, terc, ntr, name in rob3:
    print(f"{name:<40} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+6.0f}  {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f}  ROB3")
if not rob3:
    print("  (ninguna ROB3)")
print("\n== Mejores ROB2 (referencia) =="); print(hdr); print("-" * len(hdr))
for rob, tot, pf, wr, mdd, terc, ntr, name in sorted([r for r in rows if r[0] == 2], key=lambda r: -r[1])[:8]:
    print(f"{name:<40} {ntr:>4} {ntr/weeks:>6.1f} {tot:>+6.0f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+6.0f}  {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f}  ROB2")
