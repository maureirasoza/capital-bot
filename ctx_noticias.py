#!/usr/bin/env python3
"""Punto 3: filtro de CALENDARIO ECONOMICO para los 5 bots de reversion de indices (base ctx_filtros.py).
Eventos de EE.UU. de alto impacto con su fecha REAL de publicacion (bls.gov / federalreserve.gov, incluye los
corrimientos por el cierre del gobierno de oct-nov 2025): empleo (NFP) y IPC 8:30 ET, decision FOMC 14:00 ET.
No se abre posicion desde 'antes' min previos hasta 'despues' min posteriores. La hora de la vela = su inicio,
la entrada ocurre al cierre (+15 min)."""
import sys; sys.argv = sys.argv[:1]
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import ctx_filtros as cf
NFP = "2025-02-07 2025-03-07 2025-04-04 2025-05-02 2025-06-06 2025-07-03 2025-08-01 2025-09-05 2025-11-20 2025-12-16 2026-01-09 2026-02-11 2026-03-06 2026-04-03 2026-05-08 2026-06-05 2026-07-02 2026-08-07 2026-09-04 2026-10-02"
CPI = "2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11 2025-07-15 2025-08-12 2025-09-11 2025-10-24 2025-12-18 2026-01-13 2026-02-13 2026-03-11 2026-04-10 2026-05-12 2026-06-10 2026-07-14 2026-08-12 2026-09-11"
FOMC = "2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10 2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16"
NY = ZoneInfo("America/New_York")
def utc(d, hh, mm):
    return datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=NY).astimezone(timezone.utc).replace(tzinfo=None)
EVT = sorted([("NFP", utc(d, 8, 30)) for d in NFP.split()] + [("IPC", utc(d, 8, 30)) for d in CPI.split()] +
             [("FOMC", utc(d, 14, 0)) for d in FOMC.split()])
def filtro(antes, despues, tipos=("NFP", "IPC", "FOMC")):
    ev = [t for n, t in EVT if n in tipos]
    def bloquear(k, ts, sg):
        te = ts.replace(tzinfo=None) + timedelta(minutes=15)       # momento real de la entrada
        return any(-antes <= (te - t).total_seconds() / 60 <= despues for t in ev)
    return bloquear
if __name__ == "__main__":
    print(f"{len(EVT)} eventos ({EVT[0][1]:%Y-%m-%d} -> {EVT[-1][1]:%Y-%m-%d})")
    print("\n--- no entrar entre X min antes y Y min despues de la noticia ---")
    for a, d in ((30, 30), (60, 60), (0, 60), (0, 120), (60, 180), (120, 360), (0, 1440)):
        cf.linea(f"todas: -{a} / +{d} min", cf.run(bloquear=filtro(a, d)))
    for t in ("NFP", "IPC", "FOMC"):
        cf.linea(f"solo {t}: -60 / +120 min", cf.run(bloquear=filtro(60, 120, (t,))))
    # ops de la BASE que entraron cerca de una noticia
    print("\n--- ops de la base segun cercania a una noticia (entrada entre -60 y +240 min) ---")
    cerca = []; lejos = []
    for k, trs in cf.BASE.items():
        for x in trs:
            te = x["t"].replace(tzinfo=None) + timedelta(minutes=15)
            (cerca if any(-60 <= (te - t).total_seconds() / 60 <= 240 for _, t in EVT) else lejos).append(x["net"])
    for et, v in (("cerca de noticia", cerca), ("resto", lejos)):
        print(f"  {et:<18} {len(v):>5} ops  total ${sum(v):+6.0f}  media ${sum(v)/len(v):+5.2f}/op  aciertos {100*sum(1 for n in v if n>0)/len(v):.0f}%")
