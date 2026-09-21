#!/usr/bin/env python3
"""
ANALISIS DE SENSIBILIDAD AL DESLIZ DE EJECUCION.
El backtest solo modelaba el spread. El 21-sep se midio en vivo que las entradas A MERCADO
pagan ademas ~0.4-2.4 pts de desliz (el bot decide con el cierre de la vela y entra ~1 min
despues), mientras la entrada por LIMITE del FVG paga ~0.
Aqui se re-valida cada bot con su codigo REAL sobre datos REALES, barriendo el desliz, para
responder: cuanto coste extra aguanta cada configuracion antes de dejar de ser robusta (ROB3)
y antes de dejar de ganar.
Uso: ./venv/bin/python sensibilidad_desliz.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-bot")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-fvg-bot")))
import backtest_real as br
import bot_gold_trend as bt, bot_gold as bg, bot_fvg_limit as fv
import bot_sp500 as sp, bot_us30 as us

GRID = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
# (nombre, entrada, epic, resolucion, dias, medio-spread, funcion de simulacion)
BOTS = [
    ("Oro Trend 1h",      "MERCADO", "GOLD",  "HOUR",      600, 0.25, lambda d: br.simulate(*d, bt.ATR_STOP)),
    ("Oro Bollinger 15m", "MERCADO", "GOLD",  "MINUTE_15", 300, 0.25, lambda d: br.simulate_bollinger(*d, bg, bg.TRAIL_ATR)),
    ("Oro FVG 15m",       "LIMITE",  "GOLD",  "MINUTE_15", 300, 0.25, lambda d: br.simulate_fvg(*d, fv)),
    ("SP500 v2 15m",      "MERCADO", "US500", "MINUTE_15", 300, 0.30, lambda d: br.simulate_bollinger(*d, sp, sp.TRAIL_ATR)),
    ("US30 15m",          "MERCADO", "US30",  "MINUTE_15", 300, 1.00, lambda d: br.simulate_bollinger(*d, us, us.TRAIL_ATR)),
]

print("=" * 96)
print("SENSIBILIDAD AL DESLIZ — cada bot con su codigo real sobre datos reales de capital.com")
print("Desliz medido en vivo: entradas a MERCADO +0.4 a +2.4 pts | entrada por LIMITE (FVG) ~0")
print("=" * 96)
resumen = []
for nombre, entrada, epic, res, dias, spread, sim in BOTS:
    datos = br.fetch_capital(epic, res, dias)
    br.SPREAD = spread
    print(f"\n### {nombre}  [entrada {entrada}]  {epic} {res} {dias}d  (medio-spread {spread})")
    print(f"  {'desliz':>7} | {'#tr':>4} | {'NETO pts':>9} | {'PF':>5} | {'acc%':>5} | {'3 tercios':>22} | ROB")
    print("  " + "-" * 78)
    rompe_rob3 = None; rompe_ganancia = None
    for slip in GRID:
        br.SLIP = slip
        tr = sim(datos)
        if not tr:
            print(f"  {slip:>6}p |  sin trades"); continue
        tot, wr, pf, mdd, terc, rob = br.stats(tr, "net")
        marca = ""
        if rob == 3: marca = " <<"
        elif rompe_rob3 is None: rompe_rob3 = slip
        if tot <= 0 and rompe_ganancia is None: rompe_ganancia = slip
        print(f"  {slip:>6}p | {len(tr):>4} | {tot:>+9.0f} | {pf:>5.2f} | {wr:>4.1f}% | "
              f"{terc[0]:>+6.0f}/{terc[1]:>+6.0f}/{terc[2]:>+6.0f} | ROB{rob}{marca}")
    resumen.append((nombre, entrada, rompe_rob3, rompe_ganancia))
    br.SLIP = 0.0

print("\n" + "=" * 96)
print("RESUMEN — cuanto desliz aguanta cada bot")
print(f"  {'bot':<20} {'entrada':<9} {'deja de ser ROB3':>18} {'deja de ganar':>16}")
for n, e, r3, rg in resumen:
    print(f"  {n:<20} {e:<9} {(str(r3)+' pts') if r3 else 'aguanta todo':>18} {(str(rg)+' pts') if rg else 'aguanta todo':>16}")
print("\nDesliz REAL medido por bot: Bollinger oro ~1.0-2.4 | Trend ~0.4-1.1 | FVG ~0 (limite)")
print("US30/SP500: muestra insuficiente (2-3 entradas), se asume similar a los de oro a mercado.")
