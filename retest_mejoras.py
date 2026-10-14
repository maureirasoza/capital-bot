#!/usr/bin/env python3
"""Mejoras pensadas para el mercado de oct-2026 (caidas sostenidas), probadas con el motor fiel 5m (14-oct-2026).
  V1 CONFIRMACION: en vez de comprar cuando el cierre ESTA bajo la banda (y RSI extremo), comprar cuando la vela anterior
     estaba fuera de la banda con RSI extremo y la actual CIERRA DE VUELTA DENTRO (el rebote ya empezo). Venta simetrica.
  V2 TENDENCIA en indices: Donchian 15/8 + EMA200 1h, trailing 5xATR, dos lados (el motor del Trend oro).
Entrenamiento 2024-01 -> 2025-06 / prueba 2025-07 -> hoy. Solo cuenta si gana en AMBOS y supera a la version actual."""
import sys, json
from datetime import datetime
import retest as R, github_lab as g
CORTE = datetime(2025, 7, 1)

def sen_confirmacion(mod, b, W=300):
    C = b["C"]; n = len(C); m = g.sma(C, mod.BB_LEN); out = {}
    sd = [None] * n
    for i in range(mod.BB_LEN - 1, n):
        w = C[i - mod.BB_LEN + 1:i + 1]; mu = sum(w) / len(w); sd[i] = (sum((x - mu) ** 2 for x in w) / len(w)) ** .5
    r = g.rsi(C, mod.RSI_LEN if hasattr(mod, "RSI_LEN") else 14); a = g.atr(b["H"], b["L"], C, 14)
    for i in range(W, n):
        lo1, up1 = m[i - 1] - mod.BB_MULT * sd[i - 1], m[i - 1] + mod.BB_MULT * sd[i - 1]
        lo, up = m[i] - mod.BB_MULT * sd[i], m[i] + mod.BB_MULT * sd[i]
        if r[i - 1] is None or a[i] is None: continue
        if C[i - 1] < lo1 and r[i - 1] < mod.RSI_LOW and C[i] > lo: out[i] = {"side": "BUY", "nivel": C[i], "atr": a[i]}
        elif C[i - 1] > up1 and r[i - 1] > mod.RSI_HIGH and C[i] < up: out[i] = {"side": "SELL", "nivel": C[i], "atr": a[i]}
    return out

def bot_confirmacion(m, mod, trail, gaps=False):
    orig = R.sen_reversion
    R.sen_reversion = lambda mod_, b, W=300: sen_confirmacion(mod_, b, W)
    try: return R.bot_reversion(m, mod, trail, gaps=gaps)
    finally: R.sen_reversion = orig

def st(tr, usd):
    v = [x["pts"] * usd for x in tr]; gw = sum(x for x in v if x > 0); gl = -sum(x for x in v if x < 0)
    return f"${sum(v):+6.0f} PF{(gw / gl if gl else 9):.2f} ({len(v)})", sum(v)

CASOS = [("SP500", R.sp, "US500", 1.0, False), ("US30 bandas", R.us, "US30", 0.1, False), ("Holanda", R.nl, "NL25", 5.4, True),
         ("Bollinger oro", R.bg, "GOLD", 0.8, False)]
if __name__ == "__main__":
    for nombre, mod, epic, usd, gaps in CASOS:
        m = R.cargar5(epic)
        act = json.load(open(f"data/retest_{nombre.replace(' ', '_')}.json"))
        act = [{**x, "t_in": datetime.fromisoformat(x["t_in"])} for x in act]
        print(f"\n===== {nombre} =====", flush=True)
        a1, a1v = st([x for x in act if x["t_in"] < CORTE], usd); a2, a2v = st([x for x in act if x["t_in"] >= CORTE], usd)
        print(f"  ACTUAL (compra mientras cae):        entrenamiento {a1} | prueba {a2}", flush=True)
        for k in (3.0, 4.0, 5.0):
            tr = R.simular(m, bot_confirmacion(m, mod, k, gaps))
            b1, b1v = st([x for x in tr if x["t_in"] < CORTE], usd); b2, b2v = st([x for x in tr if x["t_in"] >= CORTE], usd)
            ok = "  <- MEJOR EN AMBOS" if (b1v > a1v and b2v > a2v and b1v > 0 and b2v > 0) else ""
            print(f"  CONFIRMACION trailing {k}xATR:       entrenamiento {b1} | prueba {b2}{ok}", flush=True)
    print("\n===== V2: seguir la TENDENCIA en indices (Donchian 15/8 + EMA200 1h, trailing 5xATR, dos lados) =====")
    for nombre, epic, usd in (("SP500", "US500", 1.0), ("US30", "US30", 0.1), ("Holanda", "NL25", 5.4), ("US100", "US100", 0.1), ("Russell", "RTY", 1.0)):
        m = R.cargar5(epic); tr = R.simular(m, R.bot_trend(m, pyr=(2.0, 1), tight=(99, 2.5)))
        b1, _ = st([x for x in tr if x["t_in"] < CORTE], usd); b2, _ = st([x for x in tr if x["t_in"] >= CORTE], usd)
        print(f"  {nombre:<8} entrenamiento {b1} | prueba {b2}", flush=True)
