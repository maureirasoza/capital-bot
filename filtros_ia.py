#!/usr/bin/env python3
"""Filtros sacados de los MOTIVOS de la IA en modo sombra (23-oct-2026), probados en el motor fiel 5m (retest.py).
  ACELERACION: no comprar si la vela de la senal es bajista con cuerpo > k x ATR (y no vender si es alcista grande).
  MAXIMOS DECRECIENTES: no comprar si los maximos de las ultimas N velas 15m bajan una tras otra (minimos crecientes
  para no vender). El umbral se ELIGE con 2024-01 -> 2025-06 y se MIDE en 2025-07 -> hoy."""
import sys
from datetime import datetime
import retest as R
A = datetime(2025, 7, 1)
ORIG = R.sen_reversion

def con_filtro(tipo, p):
    def sen(mod, b, W=300):
        S = ORIG(mod, b, W); O, H, L, C = b["O"], b["H"], b["L"], b["C"]; out = {}
        for k, s in S.items():
            sg = 1 if s["side"] == "BUY" else -1
            if tipo == "acel":
                cuerpo = sg * (O[k] - C[k])            # >0 si la vela va EN CONTRA de la entrada
                if cuerpo > p * s["atr"]: continue
            elif tipo == "maximos":
                if sg == 1 and all(H[k - j] < H[k - j - 1] for j in range(p - 1)): continue
                if sg == -1 and all(L[k - j] > L[k - j - 1] for j in range(p - 1)): continue
            out[k] = s
        return out
    return sen

def tot(tr, usd):
    a = sum(x["pts"] for x in tr if x["t_in"] < A) * usd; b = sum(x["pts"] for x in tr if x["t_in"] >= A) * usd
    return a, b, sum(1 for x in tr if x["t_in"] < A), sum(1 for x in tr if x["t_in"] >= A)

CASOS = {"SP500": ("US500", R.sp, 1.0, {}), "Bollinger oro": ("GOLD", R.bg, 0.8, {"piramide": (R.bg.PYR_STEP, R.bg.PYR_MAX)}),
         "US30 bandas": ("US30", R.us, 0.1, {})}
if __name__ == "__main__":
    for nombre in (sys.argv[1:] or CASOS):
        epic, mod, usd, kw = CASOS[nombre]; m = R.cargar5(epic)
        R.sen_reversion = ORIG; base = tot(R.simular(m, R.bot_reversion(m, mod, mod.TRAIL_ATR, **kw)), usd)
        print(f"\n===== {nombre} =====  SIN FILTRO: entrenamiento ${base[0]:+.0f} ({base[2]} ops) | prueba ${base[1]:+.0f} ({base[3]} ops)", flush=True)
        filas = []
        for tipo, params in (("acel", (0.5, 0.8, 1.0, 1.5, 2.0)), ("maximos", (3, 4, 5, 6))):
            for p in params:
                R.sen_reversion = con_filtro(tipo, p)
                r = tot(R.simular(m, R.bot_reversion(m, mod, mod.TRAIL_ATR, **kw)), usd); filas.append((tipo, p, r))
                print(f"  {('aceleracion cuerpo>' + str(p) + 'xATR') if tipo == 'acel' else ('maximos decrecientes ' + str(p) + ' velas'):<34} "
                      f"entren ${r[0]:+6.0f} ({r[2]}) | prueba ${r[1]:+6.0f} ({r[3]})", flush=True)
        R.sen_reversion = ORIG
        mejor = max(filas, key=lambda f: f[2][0])
        if mejor[2][0] <= base[0]:
            print("  VEREDICTO: ningun filtro mejora el ENTRENAMIENTO -> no se elige ninguno")
        else:
            print(f"  VEREDICTO: elegido con entrenamiento {mejor[0]} {mejor[1]} -> prueba ${mejor[2][1]:+.0f} vs sin filtro ${base[1]:+.0f} -> "
                  f"{'SIRVE' if mejor[2][1] > base[1] else 'NO SIRVE'}")
