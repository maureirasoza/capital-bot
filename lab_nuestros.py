#!/usr/bin/env python3
"""NUESTROS bots en el MISMO laboratorio que las estrategias de GitHub (github_lab.py): mismo simulador (entrada en la
apertura siguiente, costos reales, % del precio), mismos 8 mercados, mismas pruebas (ROB, peor MAE, % del tiempo
en mercado, ventaja sobre 'estar comprado'). Version NUCLEO de cada bot: su senal real + su trailing k x ATR, SIN
piramide ni apriete (las estrategias de GitHub tampoco los tienen). Senales cacheadas en data/lab_nuestros_sig.json.
Uso: python lab_nuestros.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gold-bot"))
import github_lab as g
import bot_sp500 as sp, bot_us30 as us, bot_nl25 as nl, bot_us30_rf as rf, bot_gold_trend as bt, bot_crypto as bc
import bot_gold as bg

CACHE = "data/lab_nuestros_sig.json"

def sig_reversion(mod, b, W=300):
    O, H, L, C = b["O"], b["H"], b["L"], b["C"]; n = len(C); side = [None] * n; atr = [None] * n
    for i in range(W, n):
        s = mod.signal_last(O[i - W + 1:i + 1], H[i - W + 1:i + 1], L[i - W + 1:i + 1], C[i - W + 1:i + 1])
        side[i] = s.get("side") if s.get("atr") else None; atr[i] = s.get("atr")
    return {"side": side, "atr": atr}

def sig_trend(b, W=600):
    O, H, L, C = b["O"], b["H"], b["L"], b["C"]; n = len(C); out = {"el": [False] * n, "es": [False] * n, "xl": [False] * n, "xs": [False] * n, "atr": [None] * n}
    for i in range(W, n):
        s = bt.signal_at(O[i - W + 1:i + 1], H[i - W + 1:i + 1], L[i - W + 1:i + 1], C[i - W + 1:i + 1], W - 1)
        out["el"][i], out["es"][i], out["xl"][i], out["xs"][i], out["atr"][i] = s["long_break"], s["short_break"], s["exit_long"], s["exit_short"], s["atr"]
    return out

def sig_at(mod, b, W):
    O, H, L, C = b["O"], b["H"], b["L"], b["C"]; n = len(C); side = [None] * n; atr = [None] * n
    for i in range(W, n):
        s = mod.signal_at(O[i - W + 1:i + 1], H[i - W + 1:i + 1], L[i - W + 1:i + 1], C[i - W + 1:i + 1], W - 1)
        side[i] = s.get("side"); atr[i] = s.get("atr")
    return {"side": side, "atr": atr}

# motor -> (marco, funcion de senal, trailing k)
MOTORES = {
    "SP500 (BB+RSI 30/70)":     ("15m", lambda b: sig_reversion(sp, b), sp.TRAIL_ATR),
    "US30/US100 (BB+RSI35/65)": ("15m", lambda b: sig_reversion(us, b), us.TRAIL_ATR),
    "Russell (= motor US30)":   ("15m", "US30/US100 (BB+RSI35/65)", 4.0),
    "Holanda (BB26/1.75)":      ("15m", lambda b: sig_reversion(nl, b), nl.TRAIL_ATR),
    "Bollinger oro":            ("15m", lambda b: sig_reversion(bg, b), bg.TRAIL_ATR),
    "US30 ruptura fallida":     ("1h",  lambda b: sig_at(rf, b, 200), rf.TRAIL_ATR),
    "Trend oro":                ("1h",  sig_trend, bt.ATR_STOP),
    "Cripto ATR-breakout":      ("4h",  lambda b: sig_at(bc, b, 600), bc.TRAIL_ATR),
}
PROPIO = {"SP500 (BB+RSI 30/70)": "US500", "US30/US100 (BB+RSI35/65)": "US30", "Russell (= motor US30)": "RTY",
          "Holanda (BB26/1.75)": "NL25", "Bollinger oro": "GOLD", "US30 ruptura fallida": "US30", "Trend oro": "GOLD",
          "Cripto ATR-breakout": "BTCUSD"}

def correr(nombre, b, epic, S):
    tf, fn, k = MOTORES[nombre]; n = len(b["C"])
    if "el" in S:
        el, es, xl, xs = S["el"], S["es"], S["xl"], S["xs"]
    else:
        el = [x == "BUY" for x in S["side"]]; es = [x == "SELL" for x in S["side"]]; xl = xs = None
    dist = [None if a is None else k * a for a in S["atr"]]
    return g.simular(b, epic, el, es, xl, xs, dist=dist)

def resumen(tr, b):
    s = g.stats(tr)
    if not s: return None
    expo = sum(x["barras"] for x in tr) / len(b["C"]); net_long = sum(x["barras"] * x["sg"] for x in tr) / len(b["C"])
    bh = 100 * (b["C"][-1] - b["C"][300]) / b["C"][300]
    s.update(mae=min(x["mae"] for x in tr), expo=expo, beta=bh * net_long, alfa=s["tot"] - bh * net_long)
    return s

if __name__ == "__main__":
    M = g.mercados()
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    filas = []
    for nombre, (tf, fn, k) in MOTORES.items():
        for e in M:
            key = f"{fn if isinstance(fn, str) else nombre}|{e}|{tf}"
            if key not in cache:
                cache[key] = (MOTORES[fn][1] if isinstance(fn, str) else fn)(M[e][tf])
                json.dump(cache, open(CACHE, "w")); print(f"  senal {key}", file=sys.stderr, flush=True)
            tr = correr(nombre, M[e][tf], e, cache[key]); filas.append((nombre, tf, e, resumen(tr, M[e][tf])))
    print(f"{'NUESTRO motor':<26}{'tf':>4} {'mercado':<7}{'ops':>5}{'neto %':>8}{'PF':>6}{'DD %':>7}{'MAE %':>7}{'tiempo':>7}{'ventaja':>8}   tercios %          ROB")
    for nombre, tf, e, s in filas:
        prop = " <- su mercado" if PROPIO[nombre] == e else ""
        if not s: print(f"{nombre:<26}{tf:>4} {e:<7} sin operaciones{prop}"); continue
        print(f"{nombre:<26}{tf:>4} {e:<7}{s['n']:>5}{s['tot']:>+8.1f}{s['pf']:>6.2f}{s['dd']:>+7.1f}{s['mae']:>+7.1f}{100*s['expo']:>6.0f}%{s['alfa']:>+8.1f}   "
              f"{s['ter'][0]:>+5.1f}/{s['ter'][1]:>+5.1f}/{s['ter'][2]:>+5.1f}  {'ROB' if s['rob'] else '   '}{prop}")
