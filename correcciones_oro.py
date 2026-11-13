#!/usr/bin/env python3
"""Correcciones para Bollinger oro y AwesomeMacd en caidas sostenidas del oro (13-nov-2026), motor fiel 5m (retest.py).
  AO-2 lados: ademas de comprar, VENDE con la regla espejo (MACD<0 y AO cruza a negativo; sale MACD>0 y AO cruza a +).
  AO+EMA200: solo compra si el cierre 1h esta sobre la EMA de 200 horas.
  BOLL coordinado: no abre en contra de una posicion abierta del Trend oro (la tendencia manda).
Periodos: entrenamiento 2024-01 -> 2025-06 | prueba 2025-07 -> 2026-10-22 | ultimas semanas 2026-10-23 -> hoy."""
from datetime import datetime, timedelta
import retest as R, github_lab as g
P = [("entren", datetime(2020, 1, 1), datetime(2025, 7, 1)), ("prueba", datetime(2025, 7, 1), datetime(2026, 10, 23)),
     ("ult. semanas", datetime(2026, 10, 23), datetime(2030, 1, 1))]
def linea(etq, tr, usd):
    out = []
    for n, a, b in P:
        v = [x["pts"] * usd for x in tr if a <= x["t_in"] < b]; out.append(f"{n} ${sum(v):+6.0f} ({len(v)})")
    print(f"  {etq:<36} " + " | ".join(out), flush=True)

def bot_ao_var(m, cortos=False, ema_filtro=False):
    b = R.velas(m, 60); W = R.ao.N_CANDLES; D = R.Decisor(); C = b["C"]
    hl = [(h + l) / 2 for h, l in zip(b["H"], b["L"])]; f, s = g.sma(hl, 5), g.sma(hl, 34)
    ao = [None if not g.ok(x, y) else x - y for x, y in zip(f, s)]; mc, _ = g.macd(C); e200 = g.ema(C, 200)
    for k in range(W, len(C)):
        j = b["j"][k]
        if j >= len(m["T"]): break
        if not g.ok(ao[k], ao[k - 1]): continue
        up = mc[k] > 0 and ao[k] > 0 and ao[k - 1] < 0; dn = mc[k] < 0 and ao[k] < 0 and ao[k - 1] > 0
        larga_ok = (not ema_filtro) or C[k] > e200[k]
        def fn(est, j, up=up, dn=dn, larga_ok=larga_ok):
            if est["pos"]:
                sg = est["pos"][0].sg
                if (sg == 1 and dn) or (sg == -1 and up): return [{"tipo": "salir"}]
                return []
            if up and larga_ok: return [{"tipo": "mercado", "sg": 1, "dist": None, "atr": None, "sl_pct": .10, "tp_pct": .10}]
            if dn and cortos: return [{"tipo": "mercado", "sg": -1, "dist": None, "atr": None, "sl_pct": .10, "tp_pct": .10}]
        D.en(j, fn)
    return D

if __name__ == "__main__":
    m = R.cargar5("GOLD"); print(f"ORO 5m {m['T'][0]:%Y-%m-%d} -> {m['T'][-1]:%Y-%m-%d %H:%M}")
    print("\n== AwesomeMacd (size 0.33) ==")
    linea("ACTUAL (solo compra)", R.simular(m, R.bot_ao(m)), 0.33)
    linea("AO de 2 lados (compra y vende)", R.simular(m, bot_ao_var(m, cortos=True)), 0.33)
    linea("AO solo compra sobre EMA200 1h", R.simular(m, bot_ao_var(m, ema_filtro=True)), 0.33)
    linea("AO 2 lados + compra sobre EMA200", R.simular(m, bot_ao_var(m, cortos=True, ema_filtro=True)), 0.33)
    print("\n== Bollinger oro (size 0.8, con piramide) ==")
    trend = R.simular(m, R.bot_trend(m))
    linea("(referencia) Trend oro", trend, 0.5)
    bg = R.bg; kw = {"piramide": (bg.PYR_STEP, bg.PYR_MAX)}
    linea("ACTUAL", R.simular(m, R.bot_reversion(m, bg, bg.TRAIL_ATR, **kw)), 0.8)
    orig = R.sen_reversion; b15 = R.velas(m, 15)
    def coord(mod, b, W=300):
        S = orig(mod, b, W); out = {}
        for k, s in S.items():
            t = b["fin"][k]; sg = 1 if s["side"] == "BUY" else -1
            if any(x["t_in"] <= t < x["t_out"] and x["sg"] == -sg for x in trend): continue
            out[k] = s
        return out
    R.sen_reversion = coord
    linea("COORDINADO con Trend (no en contra)", R.simular(m, R.bot_reversion(m, bg, bg.TRAIL_ATR, **kw)), 0.8)
    R.sen_reversion = orig
