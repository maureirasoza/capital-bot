#!/usr/bin/env python3
"""Busqueda de mejoras HONESTA (walk-forward) para los bots de reversion de indices y Bollinger oro (12-oct-2026).
Se ELIGE la configuracion con el periodo de entrenamiento (2024-01 -> 2025-06) y se MIDE en prueba (2025-07 -> hoy),
que la eleccion no vio. Motor fiel 5m de retest.py. Una mejora vale solo si gana en PRUEBA a la config actual."""
import sys
from datetime import datetime
import retest as R
CORTE = datetime(2025, 7, 1)
GRID = [(bl, bm, lo, hi, tr) for bl, bm in ((20, 2.0), (26, 1.75)) for lo, hi in ((30, 70), (35, 65)) for tr in (3.0, 4.0, 5.0)]
BOTS = {"SP500": (R.sp, "US500", 1.0, {}), "US30 bandas": (R.us, "US30", 0.1, {}), "US100": (R.nq, "US100", 0.1, {}),
        "Russell": (R.rt, "RTY", 1.0, {"tight": (R.rt.TIGHT_AT, R.rt.TIGHT_K)}), "Holanda": (R.nl, "NL25", 5.4, {"gaps": True}),
        "Bollinger oro": (R.bg, "GOLD", 0.8, {"piramide": (R.bg.PYR_STEP, R.bg.PYR_MAX)})}
def st(tr, usd):
    v = [x["pts"] * usd for x in tr]; gw = sum(x for x in v if x > 0); gl = -sum(x for x in v if x < 0)
    return sum(v), (gw / gl if gl else 9), len(v)
for nombre in (sys.argv[1:] or BOTS):
    mod, epic, usd, kw = BOTS[nombre]; m = R.cargar5(epic)
    orig = {k: getattr(mod, k) for k in ("BB_LEN", "BB_MULT", "RSI_LOW", "RSI_HIGH")}
    actual = (orig["BB_LEN"], orig["BB_MULT"], orig["RSI_LOW"], orig["RSI_HIGH"], mod.TRAIL_ATR)
    filas = []
    for cfg in GRID + ([actual] if actual not in GRID else []):
        bl, bm, lo, hi, tr_ = cfg
        mod.BB_LEN, mod.BB_MULT, mod.RSI_LOW, mod.RSI_HIGH = bl, bm, lo, hi
        trs = R.simular(m, R.bot_reversion(m, mod, tr_, **kw))
        a = st([x for x in trs if x["t_in"] < CORTE], usd); b = st([x for x in trs if x["t_in"] >= CORTE], usd)
        filas.append((cfg, a, b))
    for k, v in orig.items(): setattr(mod, k, v)
    elegida = max((f for f in filas if f[1][2] >= 80), key=lambda f: f[1][0])
    act = next(f for f in filas if f[0] == actual)
    print(f"\n== {nombre}: ENTRENAMIENTO 2024-01->2025-06 | PRUEBA 2025-07->hoy (en $) ==", flush=True)
    for cfg, a, b in sorted(filas, key=lambda f: -f[1][0]):
        tag = (" <- ACTUAL" if cfg == actual else "") + (" <- ELEGIDA con entrenamiento" if cfg == elegida[0] else "")
        print(f"  BB{cfg[0]}/{cfg[1]} RSI{cfg[2]}/{cfg[3]} t{cfg[4]}: entren ${a[0]:+6.0f} PF{a[1]:.2f} ({a[2]}) | prueba ${b[0]:+6.0f} PF{b[1]:.2f} ({b[2]}){tag}", flush=True)
    print(f"  VEREDICTO: elegida en prueba ${elegida[2][0]:+.0f} vs actual ${act[2][0]:+.0f} -> {'MEJORA' if elegida[2][0] > act[2][0] else 'NO mejora'}", flush=True)
