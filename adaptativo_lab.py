#!/usr/bin/env python3
"""BOT ADAPTATIVO (pedido 10-oct-2026): cada dia elige, entre un MENU de formas de operar, la que mejor rindio en los
ultimos N dias, y opera con ella al dia siguiente. Prueba WALK-FORWARD honesta: la eleccion del dia d solo usa
operaciones CERRADAS antes de que empiece d (sin mirar el futuro). Se compara contra los bots actuales (fijos).

Menu por mercado (todo causal, mismo simulador/costos que github_lab.py):
  - Reversion BB+RSI (cruce de la condicion, como nuestros bots): (20,2,35/65) trail 2/3/4/5/6, (20,2,30/70) trail 3/4/5,
    (26,1.75,30/70) trail 2/4  -> velas 15m
  - Tendencia Donchian 15/8 y 30/15 + EMA200, trailing 5xATR  -> velas 1h
  - Impulso AO+MACD largo (AwesomeMacd) y su espejo corto  -> velas 1h
  - "No operar" (si ninguna rindio > 0 en la ventana)
Uso: python adaptativo_lab.py"""
import sys
from datetime import timedelta
import github_lab as g

def reversion(b, n, k, lo_, hi_, trail):
    C = b["C"]; m, up, lo = g.bb(C, n, k)
    sd = [None] * len(C)
    for i in range(n - 1, len(C)):                         # desviacion POBLACIONAL (como nuestros bots)
        w = C[i - n + 1:i + 1]; mu = sum(w) / n; sd[i] = (sum((v - mu) ** 2 for v in w) / n) ** .5
    up = [None if m[i] is None else m[i] + k * sd[i] for i in range(len(C))]
    lo = [None if m[i] is None else m[i] - k * sd[i] for i in range(len(C))]
    r = g.rsi(C, 14); a = g.atr(b["H"], b["L"], C, 14); N = len(C)
    cl = [g.ok(lo[i], r[i]) and C[i] < lo[i] and r[i] < lo_ for i in range(N)]
    cs = [g.ok(up[i], r[i]) and C[i] > up[i] and r[i] > hi_ for i in range(N)]
    el = [i > 0 and cl[i] and not cl[i - 1] for i in range(N)]; es = [i > 0 and cs[i] and not cs[i - 1] for i in range(N)]
    return dict(el=el, es=es, dist=[None if x is None else trail * x for x in a])

def donchian(b, ent, ext):
    H, L, C = b["H"], b["L"], b["C"]; N = len(C); e200 = g.ema(C, 200); a = g.atr(H, L, C, 14)
    el = [False] * N; es = [False] * N; xl = [False] * N; xs = [False] * N
    for i in range(max(ent, 200), N):
        hh, ll = max(H[i - ent:i]), min(L[i - ent:i]); xh, xlw = max(H[i - ext:i]), min(L[i - ext:i])
        el[i] = C[i] > hh and C[i] > e200[i]; es[i] = C[i] < ll and C[i] < e200[i]
        xl[i] = C[i] < xlw; xs[i] = C[i] > xh
    return dict(el=el, es=es, xl=xl, xs=xs, dist=[None if x is None else 5 * x for x in a])

def ao_macd(b, corto=False):
    H, L, C = b["H"], b["L"], b["C"]; hl = [(h + l) / 2 for h, l in zip(H, L)]; f, s = g.sma(hl, 5), g.sma(hl, 34)
    ao = [None if not g.ok(x, y) else x - y for x, y in zip(f, s)]; m, _ = g.macd(C); N = len(C)
    up = [i > 0 and g.ok(ao[i], ao[i - 1]) and ao[i] > 0 and ao[i - 1] < 0 for i in range(N)]
    dn = [i > 0 and g.ok(ao[i], ao[i - 1]) and ao[i] < 0 and ao[i - 1] > 0 for i in range(N)]
    if not corto:
        return dict(el=[up[i] and m[i] > 0 for i in range(N)], xl=[dn[i] and m[i] < 0 for i in range(N)], roi={0: .10}, sl=-.10)
    return dict(el=[False] * N, es=[dn[i] and m[i] < 0 for i in range(N)], xs=[up[i] and m[i] > 0 for i in range(N)], roi={0: .10}, sl=-.10)

def menu(M15, M1h):
    c = {}
    for tr in (2, 3, 4, 5, 6): c[f"rev 20/2 35-65 t{tr}"] = (M15, reversion(M15, 20, 2, 35, 65, tr))
    for tr in (3, 4, 5): c[f"rev 20/2 30-70 t{tr}"] = (M15, reversion(M15, 20, 2, 30, 70, tr))
    for tr in (2, 4): c[f"rev 26/1.75 30-70 t{tr}"] = (M15, reversion(M15, 26, 1.75, 30, 70, tr))
    c["tend Donchian 15/8"] = (M1h, donchian(M1h, 15, 8)); c["tend Donchian 30/15"] = (M1h, donchian(M1h, 30, 15))
    c["impulso AO-MACD largo"] = (M1h, ao_macd(M1h)); c["impulso AO-MACD corto"] = (M1h, ao_macd(M1h, True))
    return c

def operaciones(epic, c):
    out = {}
    for nombre, (b, p) in c.items():
        out[nombre] = g.simular(b, epic, p["el"], p.get("es"), p.get("xl"), p.get("xs"), p.get("roi"), p.get("sl"), dist=p.get("dist"))
    return out

def walk_forward(ops, dias, N, top=1):
    """Cada dia d: puntaje = suma de r de las ops CERRADAS en [d-N, d). Opera con las `top` mejores (si puntaje > 0)."""
    tot = 0.0; elegidas = {}; serie = []
    por_dia = {k: {} for k in ops}
    for k, trs in ops.items():
        for x in trs: por_dia[k].setdefault(x["t"].date(), []).append(x["r"])
    cierres = {k: sorted((x["tout"].date(), x["r"]) for x in trs) for k, trs in ops.items()}
    for d in dias:
        desde = d - timedelta(days=N); pts = []
        for k, cs in cierres.items():
            s = sum(r for dd, r in cs if desde <= dd < d); pts.append((s, k))
        pts.sort(reverse=True); hoy = 0.0
        sel = [k for s, k in pts[:top] if s > 0]
        for k in sel:
            v = sum(por_dia[k].get(d, [])) / top; hoy += v; elegidas[k] = elegidas.get(k, 0) + 1
        tot += hoy; serie.append((d, hoy))
    return tot, elegidas, serie

def resumen_serie(serie):
    eq = pk = dd = 0.0; t0, t1 = serie[0][0], serie[-1][0]; span = (t1 - t0) / 3; ter = [0.0] * 3
    for d, v in serie:
        eq += v; pk = max(pk, eq); dd = min(dd, eq - pk); ter[min(2, int((d - t0) / span))] += v
    return dd, ter

if __name__ == "__main__":
    M = g.mercados()
    ACTUAL = {"US500": "rev 20/2 30-70 t4", "US30": "rev 20/2 35-65 t5", "US100": "rev 20/2 35-65 t5", "RTY": "rev 20/2 35-65 t4",
              "NL25": "rev 26/1.75 30-70 t2", "GOLD": "tend Donchian 15/8"}
    resultados = {}
    for e in ("US500", "US30", "US100", "RTY", "NL25", "GOLD"):
        c = menu(M[e]["15m"], M[e]["1h"]); ops = operaciones(e, c)
        dias = sorted({t.date() for t in M[e]["15m"]["T"]}); dias = [d for d in dias if d >= dias[0] + timedelta(days=130)]
        base = [x for x in ops[ACTUAL[e]] if x["t"].date() >= dias[0]]
        sb = sum(x["r"] for x in base); serie_b = [(d, sum(x["r"] for x in base if x["t"].date() == d)) for d in dias]; ddb, terb = resumen_serie(serie_b)
        print(f"\n===== {e}  ({dias[0]} -> {dias[-1]}, mismo periodo para todos) =====")
        print(f"  {'BOT ACTUAL (fijo): ' + ACTUAL[e]:<44} {sb:>+7.1f}%  DD {ddb:>+6.1f}%  tercios {terb[0]:+.1f}/{terb[1]:+.1f}/{terb[2]:+.1f}")
        resultados.setdefault("ACTUAL", 0); resultados["ACTUAL"] += sb
        for N in (3, 5, 10, 20, 40, 120):
            for top in (1, 3):
                tot, el, serie = walk_forward(ops, dias, N, top); dd, ter = resumen_serie(serie)
                fav = max(el.items(), key=lambda x: x[1])[0] if el else "-"
                print(f"  {'ADAPTATIVO ultimos ' + str(N) + ' dias, top ' + str(top):<44} {tot:>+7.1f}%  DD {dd:>+6.1f}%  tercios {ter[0]:+.1f}/{ter[1]:+.1f}/{ter[2]:+.1f}  (mas elegida: {fav})", flush=True)
                resultados.setdefault((N, top), 0); resultados[(N, top)] += tot
    print("\n===== SUMA de los 6 mercados (% del precio) =====")
    print(f"  BOTS ACTUALES (fijos): {resultados['ACTUAL']:+.1f}%")
    for k, v in resultados.items():
        if k != "ACTUAL": print(f"  adaptativo N={k[0]:>3} dias top {k[1]}: {v:+.1f}%")
