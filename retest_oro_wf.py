#!/usr/bin/env python3
"""ORO: variantes de Trend oro y Bollinger oro en el motor fiel 5m (15-oct-2026). Entrenamiento 2024-01->2025-06,
prueba 2025-07->hoy, ultimo mes; probabilidad de suerte por bootstrap. Vale solo si gana en ambos periodos."""
import random, sys
from datetime import datetime
import retest as R
random.seed(1); A, B, MES = datetime(2025, 7, 1), datetime(2030, 1, 1), datetime(2026, 9, 13)
def boot(v): return sum(1 for _ in range(1000) if sum(random.choice(v) for _ in range(len(v))) <= 0) / 1000 if v else 1
def res(tr, usd):
    out = []
    for a, b in ((datetime(2020, 1, 1), A), (A, B), (MES, B)):
        v = [x["pts"] * usd for x in tr if a <= x["t_in"] < b]; out.append((sum(v), len(v), boot(v)))
    return out
def linea(etq, r, actual=False):
    ok = r[0][0] > 0 and r[1][0] > 0
    print(f"  {etq:<34} entren ${r[0][0]:+6.0f} ({r[0][1]}, suerte {100*r[0][2]:.0f}%) | prueba ${r[1][0]:+6.0f} ({r[1][1]}, suerte {100*r[1][2]:.0f}%) | ult. mes ${r[2][0]:+5.0f} ({r[2][1]}){'  <- ACTUAL' if actual else ''}{'  AMBOS +' if ok else ''}", flush=True)
m = R.cargar5("GOLD")
quien = sys.argv[1:] or ["trend", "bollinger"]
if "trend" in quien:
    print("== TREND ORO (Donchian entrada/salida, stop x ATR; con EMA200, piramide y apriete actuales) ==")
    bt = R.bt; o = (bt.ENT, bt.EXIT)
    for ent in (10, 15, 20, 30):
        for ex in (5, 8, 12):
            bt.ENT, bt.EXIT = ent, ex
            for st in (3.0, 4.0, 5.0):
                linea(f"Donchian {ent}/{ex} stop {st}x", res(R.simular(m, R.bot_trend(m, stop=st)), bt.SIZE), (ent, ex, st) == (15, 8, 5.0))
    bt.ENT, bt.EXIT = o
if "bollinger" in quien:
    print("== BOLLINGER ORO (bandas/RSI/trailing; con su filtro ADX/EMA200 y piramide) ==")
    bg = R.bg; o = (bg.BB_LEN, bg.BB_MULT, bg.RSI_LOW, bg.RSI_HIGH)
    for bl, bm in ((20, 2.0), (26, 1.75)):
        for lo, hi in ((30, 70), (35, 65), (38, 62)):
            bg.BB_LEN, bg.BB_MULT, bg.RSI_LOW, bg.RSI_HIGH = bl, bm, lo, hi
            for tr_ in (3.0, 4.0, 5.0):
                linea(f"BB{bl}/{bm} RSI{lo}/{hi} t{tr_}", res(R.simular(m, R.bot_reversion(m, bg, tr_, piramide=(bg.PYR_STEP, bg.PYR_MAX))), bg.SIZE),
                      (bl, bm, lo, hi, tr_) == (o[0], o[1], o[2], o[3], bg.TRAIL_ATR))
    bg.BB_LEN, bg.BB_MULT, bg.RSI_LOW, bg.RSI_HIGH = o
