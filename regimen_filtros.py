#!/usr/bin/env python3
"""¿Por que pierden los bots segun el tipo de mercado, y sirve un filtro de regimen? (13-oct-2026)
Usa las operaciones del motor fiel (data/retest_*.json, 5m bid/ask, ene-2024 -> oct-2026) y mide el mercado del DIA
ANTERIOR a cada entrada (sin mirar el futuro):
  - TENDENCIA: eficiencia de 10 dias = |cierre hoy - cierre hace 10 dias| / suma de movimientos diarios (0 = lateral, 1 = recto)
  - VOLATILIDAD: rango diario medio de 14 dias / precio, como percentil de los 250 dias previos
Filtro honesto: el umbral se ELIGE con 2024-01 -> 2025-06 y se MIDE en 2025-07 -> hoy."""
import json
from datetime import datetime, timedelta
import retest as R
CORTE = datetime(2025, 7, 1)
BOTS = {"SP500": ("US500", 1.0), "US30 bandas": ("US30", 0.1), "Holanda": ("NL25", 5.4), "US30 ruptura f.": ("US30", 0.12),
        "Bollinger oro": ("GOLD", 0.8), "Trend oro": ("GOLD", 0.5), "AwesomeMacd oro": ("GOLD", 0.33)}

def regimen(epic):
    m = R.cargar5(epic); d = R.velas(m, 1440); C, H, L, T = d["C"], d["H"], d["L"], d["T"]; out = {}
    rng = [h - l for h, l in zip(H, L)]
    for i in range(260, len(C)):
        mov = sum(abs(C[k] - C[k - 1]) for k in range(i - 9, i + 1)); er = abs(C[i] - C[i - 10]) / mov if mov else 0
        vol = lambda j: sum(rng[j - 13:j + 1]) / 14 / C[j]
        v = vol(i); hist = sorted(vol(j) for j in range(i - 250, i)); pct = sum(1 for x in hist if x <= v) / len(hist)
        out[T[i].date()] = (er, pct)
    return out, T[-1].date()

def tercil(v, cortes): return 0 if v < cortes[0] else (1 if v < cortes[1] else 2)
if __name__ == "__main__":
    REG = {}; hoy = {}
    for nombre, (epic, usd) in BOTS.items():
        if epic not in REG:
            REG[epic], ult = regimen(epic); hoy[epic] = REG[epic][ult]
        tr = json.load(open(f"data/retest_{nombre.replace(' ', '_')}.json"))
        filas = []
        for x in tr:
            t = datetime.fromisoformat(x["t_in"]); prev = t.date() - timedelta(days=1)
            while prev not in REG[epic] and prev > t.date() - timedelta(days=6): prev -= timedelta(days=1)
            if prev in REG[epic]: filas.append((t, x["pts"] * usd, *REG[epic][prev]))
        ent = [f for f in filas if f[0] < CORTE]; pru = [f for f in filas if f[0] >= CORTE]
        print(f"\n===== {nombre} ({epic}) =====  hoy: tendencia {hoy[epic][0]:.2f}, volatilidad percentil {100*hoy[epic][1]:.0f}")
        for nom, k in (("TENDENCIA 10d", 2), ("VOLATILIDAD", 3)):
            cortes = sorted(f[k] for f in ent); cortes = [cortes[len(cortes) // 3], cortes[2 * len(cortes) // 3]]
            et = ["baja", "media", "alta"]; hk = tercil(hoy[epic][k - 2], cortes)
            linea = []
            for b in range(3):
                e = [f[1] for f in ent if tercil(f[k], cortes) == b]; p = [f[1] for f in pru if tercil(f[k], cortes) == b]
                linea.append(f"{et[b]}{'*' if b == hk else ''}: entren ${sum(e)/max(len(e),1):+5.2f}/op ({len(e)}) prueba ${sum(p)/max(len(p),1):+5.2f}/op ({len(p)})")
            print(f"  {nom:<13} " + " | ".join(linea))
        # filtro: excluir 1 tercil (el peor en ENTRENAMIENTO) de tendencia o de volatilidad
        mejor = None
        for nom, k in (("tendencia", 2), ("volatilidad", 3)):
            cortes = sorted(f[k] for f in ent); cortes = [cortes[len(cortes) // 3], cortes[2 * len(cortes) // 3]]
            for b in range(3):
                g = sum(f[1] for f in ent if tercil(f[k], cortes) != b) - sum(f[1] for f in ent)
                if mejor is None or g > mejor[0]: mejor = (g, nom, k, b, cortes)
        g, nom, k, b, cortes = mejor; et = ["baja", "media", "alta"]
        base = sum(f[1] for f in pru); filt = sum(f[1] for f in pru if tercil(f[k], cortes) != b)
        print(f"  FILTRO elegido con entrenamiento: no entrar con {nom} {et[b]} (en entren +${g:.0f}) -> PRUEBA: sin filtro ${base:+.0f} | con filtro ${filt:+.0f} -> {'SIRVE' if filt > base else 'NO SIRVE'}")
