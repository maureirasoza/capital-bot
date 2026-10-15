#!/usr/bin/env python3
"""¿Que habria ganado en el ULTIMO MES y aguanta en el historial largo? (15-oct-2026)
1) Mercado del ultimo mes por instrumento: retorno 30d, eficiencia de tendencia, volatilidad vs el anio.
2) Menu de 14 formas de operar (adaptativo_lab.menu) sobre datos FRESCOS: resultado de las ops que entraron en los ultimos 30 dias.
3) Las mejores del mes se prueban en el historial largo (600d) con el mismo simulador: si pierden ahi, se descartan."""
import sys; sys.argv = sys.argv[:1] + ['--source', 'capital', '--refresh']
from datetime import datetime, timedelta
import backtest_real as br, github_lab as g, adaptativo_lab as ad
USD = {"US500": 1.0, "US30": 0.1, "US100": 0.1, "RTY": 1.0, "NL25": 5.4, "GOLD": 0.5}
hoy = datetime.utcnow(); D0 = hoy - timedelta(days=30)
M = None; filas = []
for e, usd in USD.items():
    O, H, L, C, T = br.fetch_capital(e, "MINUTE_15", 75); b = {"O": O, "H": H, "L": L, "C": C, "T": [t.replace(tzinfo=None) for t in T]}
    d = g.agg(b, 1440); i0 = next(i for i, t in enumerate(d["T"]) if t >= D0)
    ret = 100 * (d["C"][-1] - d["C"][i0]) / d["C"][i0]; mov = sum(abs(d["C"][k] - d["C"][k - 1]) for k in range(i0 + 1, len(d["C"])))
    er = abs(d["C"][-1] - d["C"][i0]) / mov if mov else 0; rng = sum(h - l for h, l in zip(d["H"][i0:], d["L"][i0:])) / len(d["H"][i0:]) / d["C"][-1] * 100
    print(f"{e:<6} ultimo mes: {ret:+5.1f}% | tendencia (0=lateral,1=recta) {er:.2f} | rango diario medio {rng:.2f}% del precio", flush=True)
    c = ad.menu(b, g.agg(b, 60)); ops = ad.operaciones(e, c)
    for k, trs in ops.items():
        v = [x["r"] / 100 * C[-1] * usd for x in trs if x["t"] >= D0]
        filas.append((sum(v), e, k, len(v)))
print("\nLAS 10 FORMAS DE OPERAR QUE MAS GANARON EL ULTIMO MES (en $ con el tamano de nuestros bots):")
top = sorted(filas, reverse=True)[:10]
M = g.mercados()
for v, e, k, n in top:
    c = ad.menu(M[e]["15m"], M[e]["1h"]); trs = ad.operaciones(e, {k: c[k]})[k]
    px = M[e]["15m"]["C"][-1]; mid = M[e]["15m"]["T"][len(M[e]["15m"]["T"]) // 2]
    h1 = sum(x["r"] for x in trs if x["t"] < mid) / 100 * px * USD[e]; h2 = sum(x["r"] for x in trs if x["t"] >= mid) / 100 * px * USD[e]
    ok = "AGUANTA" if h1 > 0 and h2 > 0 else "NO aguanta"
    print(f"  {e:<6} {k:<26} ultimo mes ${v:+7.0f} ({n} ops) | historial 600d: 1a mitad ${h1:+6.0f}, 2a mitad ${h2:+6.0f} -> {ok}", flush=True)
