#!/usr/bin/env python3
"""Filtros de CONTEXTO para los 5 bots de reversion de indices (SP500, US30 bandas, US100, RTY, NL25).
Base comun: datos 15m bid/ask 600d (mid), senal REAL de cada bot (signal_last, ventana 300), cacheada.
Usado por ctx_filtros.py (tipo de dia, marco mayor, maximo de bots en la misma direccion)."""
import sys, os, json
from datetime import datetime
sys.argv = sys.argv[:1] + ['--source', 'capital']
import bot_sp500 as sp, bot_us30 as us, bot_us100 as nq, bot_rty as rt, bot_nl25 as nl
CACHE = os.path.join("data", "ctx_signals_600d.json")
# nombre, modulo, epic, costo ida+vuelta (pts), $ por punto (size actual), gaps (sesion cerrada)
BOTS = [("SP500", sp, "US500", 0.6, 1.0, False), ("US30", us, "US30", 2.0, 0.1, False),
        ("US100", nq, "US100", 1.8, 0.1, False), ("RTY", rt, "RTY", 0.5, 1.0, False),
        ("NL25", nl, "NL25", 0.1, 5.0 * 1.08, True)]
W = 300

def load(epic):
    d = json.load(open(f"data/capital_{epic}_MINUTE_15_600d_bidask.json"))
    m = lambda a, b: [(x + y) / 2 for x, y in zip(d[a], d[b])]
    return m("Ob", "Oa"), m("Hb", "Ha"), m("Lb", "La"), m("Cb", "Ca"), [datetime.fromisoformat(t) for t in d["T"]]

def signals():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    out = {}
    for name, mod, epic, *_ in BOTS:
        O, H, L, C, T = load(epic); n = len(C); sig = [None] * n; atr = [None] * n
        for t in range(W, n):
            lo = t - W + 1; s = mod.signal_last(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1])
            atr[t] = s.get("atr"); sig[t] = s.get("side") if s.get("atr") else None
        out[name] = {"sig": sig, "atr": atr}
        print(f"  senales {name}: {sum(1 for x in sig if x)} en {n} velas", flush=True)
    json.dump(out, open(CACHE, "w"))
    return out

if __name__ == "__main__":
    signals()
