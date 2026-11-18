#!/usr/bin/env python3
"""¿Ganan mas los bots cuando entran CONTRA la mayoria de los clientes de capital.com? (18-nov-2026)
Sentimiento guardado cada 15 min desde 9-oct (data/sentimiento.jsonl, % de clientes comprados por mercado).
Operaciones: las que habrian hecho los motores de nuestros bots en el mismo periodo (backtest, datos frescos).
Para cada entrada: sentimiento del ultimo registro previo, comparado con la MEDIANA de ese mercado en el periodo.
  'contra la mayoria' = comprar cuando los clientes estan MENOS comprados que lo normal, o vender cuando estan MAS."""
import sys, json, bisect
sys.argv = sys.argv[:1] + ['--source', 'capital']; sys.path.insert(0, '../gold-bot')
from datetime import datetime
import backtest_real as br, bot_sp500 as sp, bot_us30 as us, bot_us100 as nq, bot_rty as rt, bot_nl25 as nl, bot_us30_rf as rf, bot_gold_trend as bt
bg = br._import_bollinger()
S = [json.loads(l) for l in open("data/sentimiento.jsonl") if l.strip()]; ST = [datetime.fromisoformat(x["t"]) for x in S]; D0 = ST[0]
med = {e: sorted(x[e] for x in S if x.get(e) is not None)[len(S) // 2] for e in ("US500", "US30", "US100", "RTY", "NL25", "GOLD")}
filas = []
def agregar(fam, epic, trades, usd):
    for x in trades:
        t = x["t_in"].replace(tzinfo=None)
        if t < D0: continue
        i = bisect.bisect_right(ST, t) - 1
        if i < 0 or S[i].get(epic) is None: continue
        sg = 1 if x["side"] in ("long", "BUY") else -1; s = S[i][epic]
        filas.append((fam, epic, sg, s - med[epic], x["net"] * usd, t))
for n, mod, e, hs, gaps, usd in (("SP500", sp, "US500", .3, False, 1.0), ("US30", us, "US30", 1.0, False, .1), ("US100", nq, "US100", .9, False, .1),
                                 ("RTY", rt, "RTY", .25, False, 1.0), ("NL25", nl, "NL25", .05, True, 5.4)):
    O, H, L, C, T = br.fetch_capital(e, "MINUTE_15", 60); br.SPREAD = hs
    agregar("rebote", e, br.simulate_bollinger(O, H, L, C, T, mod, mod.TRAIL_ATR, gaps=gaps), usd)
O, H, L, C, T = br.fetch_capital("GOLD", "MINUTE_15", 60); br.SPREAD = .3; agregar("rebote", "GOLD", br.simulate_bollinger(O, H, L, C, T, bg, bg.TRAIL_ATR), .8)
O, H, L, C, T = br.fetch_capital("GOLD", "HOUR", 90); agregar("tendencia", "GOLD", br.simulate(O, H, L, C, T, bt.ATR_STOP), .5)
O, H, L, C, T = br.fetch_capital("US30", "HOUR", 90); br.SPREAD = 1.0; agregar("ruptura", "US30", br.simulate_bollinger(O, H, L, C, T, rf, rf.TRAIL_ATR), .12)
print(f"Sentimiento {D0:%d-%b} -> {ST[-1]:%d-%b} ({len(S)} registros) | medianas % comprados: " + ", ".join(f"{k} {v:.0f}" for k, v in med.items()))
def resumen(etq, v):
    if not v: print(f"  {etq:<44} sin ops"); return
    print(f"  {etq:<44} {len(v):>4} ops  media ${sum(v)/len(v):+6.2f}/op  ganadas {100*sum(1 for x in v if x>0)/len(v):3.0f}%  total ${sum(v):+7.0f}")
for fam in ("rebote", "tendencia", "ruptura", None):
    F = [f for f in filas if fam is None or f[0] == fam]
    print(f"\n== {'TODOS' if fam is None else fam.upper()} ==")
    resumen("CONTRA la mayoria (contrario)", [f[4] for f in F if f[2] * f[3] < 0])
    resumen("A FAVOR de la mayoria", [f[4] for f in F if f[2] * f[3] >= 0])
    lim = sorted(abs(f[3]) for f in F)[2 * len(F) // 3] if F else 0
    resumen(f"contra la mayoria EXTREMA (desvio >= {lim:.1f} pts)", [f[4] for f in F if f[2] * f[3] < 0 and abs(f[3]) >= lim])
    resumen(f"a favor de la mayoria EXTREMA", [f[4] for f in F if f[2] * f[3] >= 0 and abs(f[3]) >= lim])

MITAD = datetime(2026, 10, 29)
print("\n== REBOTE por mitades (consistencia) ==")
for etq, a, b in (("9-oct -> 28-oct", D0, MITAD), ("29-oct -> hoy", MITAD, datetime(2030, 1, 1))):
    F = [f for f in filas if f[0] == "rebote" and a <= f[5] < b]
    resumen(f"{etq} CONTRA la mayoria", [f[4] for f in F if f[2] * f[3] < 0])
    resumen(f"{etq} A FAVOR de la mayoria", [f[4] for f in F if f[2] * f[3] >= 0])
