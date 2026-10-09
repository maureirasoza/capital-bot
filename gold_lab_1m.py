#!/usr/bin/env python3
"""ORO: bots publicos de GitHub vs NUESTROS bots de oro, con la MISMA ejecucion fiel minuto a minuto (bid/ask reales
de capital.com, ~1000 dias). Senal en la vela de su marco (construida desde el 1m medio); la orden se llena en la
APERTURA del minuto siguiente al cierre de esa vela (compra al ask, venta al bid); stops/objetivos/trailing se revisan
minuto a minuto contra bid (largos) / ask (cortos); si en el mismo minuto tocan stop y objetivo -> STOP (pesimista).
Reglas leidas del codigo de cada repo (no se ejecuto codigo ajeno):
  GOLD_ORB (yulz008, 303*), EMA 9/21 + filtros (a1shmuk), Sunrise Ogle pullback (ilahuerta-IA, 77*),
  CRT barrido asiatico (lordgaruda/XAU-60, 58*), Z-score M1 (n30dyn4m1c/gold-pro-scalper)
  NUESTROS: Trend oro (1h, Donchian 15/8 + EMA200, trailing 5xATR) y Bollinger oro (15m, trailing 5xATR) en version
  NUCLEO (sin piramide ni apriete) y COMPLETA.
Uso: python gold_lab_1m.py"""
import json, math, sys, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gold-bot"))
import github_lab as g
import bot_gold_trend as bt, bot_gold as bg

NY = ZoneInfo("America/New_York")

def cargar():
    d = json.load(open("data/capital_GOLD_MINUTE_1000d_bidask.json"))
    T = [datetime.fromisoformat(t) for t in d["T"]]
    m = lambda a, b: [(x + y) / 2 for x, y in zip(d[a], d[b])]
    return {"T": T, "Ob": d["Ob"], "Hb": d["Hb"], "Lb": d["Lb"], "Oa": d["Oa"], "Ha": d["Ha"], "La": d["La"],
            "O": m("Ob", "Oa"), "H": m("Hb", "Ha"), "L": m("Lb", "La"), "C": m("Cb", "Ca")}

def velas(m1, minutos):
    """Velas del marco desde 1m medio + indice del ULTIMO minuto de cada vela (para ejecutar en el siguiente)."""
    out = {"O": [], "H": [], "L": [], "C": [], "T": [], "last": []}; key = None
    for i, t in enumerate(m1["T"]):
        mm = (t.hour * 60 + t.minute) // minutos * minutos if minutos < 1440 else 0
        k = t.replace(hour=mm // 60, minute=mm % 60)
        if k != key:
            key = k; out["O"].append(m1["O"][i]); out["H"].append(m1["H"][i]); out["L"].append(m1["L"][i]); out["C"].append(m1["C"][i])
            out["T"].append(k); out["last"].append(i)
        else:
            out["H"][-1] = max(out["H"][-1], m1["H"][i]); out["L"][-1] = min(out["L"][-1], m1["L"][i]); out["C"][-1] = m1["C"][i]; out["last"][-1] = i
    return out

def servidor(t):   # hora de servidor MT tipica (GMT+2/+3 = Nueva York + 7h)
    return t.replace(tzinfo=timezone.utc).astimezone(NY).replace(tzinfo=None) + timedelta(hours=7)

# ------------------------------------------------------------------ motor de ejecucion 1m
def ejecutar(m1, ordenes):
    """ordenes: dicts {i (indice 1m de llenado), sg, sl, tp, trail (distancia $ desde el extremo), trail_desde ($ de
    ganancia para activar), be (ganancia $ para mover a break-even, offset), t_max (minutos), salida (set de indices 1m
    donde se cierra a mercado), cierre_dt (datetime: cerrar en/tras ese momento), dist_fn}. Una posicion a la vez."""
    Ob, Hb, Lb, Oa, Ha, La, T = m1["Ob"], m1["Hb"], m1["Lb"], m1["Oa"], m1["Ha"], m1["La"], m1["T"]; n = len(T)
    tr = []; libre = 0
    for o in sorted(ordenes, key=lambda x: x["i"]):
        i = o["i"]
        if i < libre or i >= n: continue
        sg = o["sg"]; e = Oa[i] if sg == 1 else Ob[i]
        sl = o.get("sl"); sl = None if sl is None else sl(e) if callable(sl) else sl
        tp = o.get("tp"); tp = None if tp is None else tp(e) if callable(tp) else tp
        stop = sl; ext = e; ex = None; j = i; be_ok = False; sal = o.get("salida") or set()
        while j < n:
            if j > i or True:
                lo, hi, op = (Lb[j], Hb[j], Ob[j]) if sg == 1 else (La[j], Ha[j], Oa[j])
                if j > i and (j in sal or (o.get("t_max") and (T[j] - T[i]).total_seconds() / 60 >= o["t_max"])
                              or (o.get("cierre_dt") and T[j] >= o["cierre_dt"])):
                    ex = op; break
                if stop is not None and ((sg == 1 and lo <= stop) or (sg == -1 and hi >= stop)):
                    ex = (min(op, stop) if sg == 1 else max(op, stop)) if j > i else stop; break
                if tp is not None and ((sg == 1 and hi >= tp) or (sg == -1 and lo <= tp)):
                    ex = (max(op, tp) if sg == 1 else min(op, tp)) if j > i else tp; break
                ext = max(ext, hi) if sg == 1 else min(ext, lo)
                gan = sg * (ext - e)
                if o.get("be") and not be_ok and gan >= o["be"][0]:
                    be_ok = True; nb = e + sg * o["be"][1]; stop = nb if stop is None else (max(stop, nb) if sg == 1 else min(stop, nb))
                if o.get("trail") and gan >= o.get("trail_desde", 0):
                    ts = ext - sg * o["trail"]; stop = ts if stop is None else (max(stop, ts) if sg == 1 else min(stop, ts))
            j += 1
        if ex is None: break
        tr.append({"t": T[i], "r": 100 * sg * (ex - e) / e, "sg": sg, "min": (T[j] - T[i]).total_seconds() / 60})
        libre = j + 1
        if o.get("tras_cierre"): o["tras_cierre"](tr[-1], j)
    return tr

# ------------------------------------------------------------------ estrategias de GitHub
def gold_orb(m1, escalar=False):
    h1 = velas(m1, 60); O, H, L, C = h1["O"], h1["H"], h1["L"], h1["C"]; n = len(C); ords = []
    rh = rl = rbt = rbb = None; ch = cl = 0; dia = None; hecho = set()
    for k in range(1, n):
        s = servidor(h1["T"][k])
        if s.hour == 1:                                   # vela de las 01:00 servidor = rango inicial (se evalua al cerrar)
            hi, lo = H[k], L[k]; bt_, bb_ = max(O[k], C[k]), min(O[k], C[k])
            esc = C[k] / 2000 if escalar else 1.0
            if hi - bt_ > 5 * esc: hi = bt_
            if bb_ - lo > 5 * esc: lo = bb_
            rh, rl, rbt, rbb = hi, lo, bt_, bb_; ch = cl = 1; dia = s.date(); hecho = set(); continue
        if rh is None: continue
        esc = C[k] / 2000 if escalar else 1.0
        bt_, bb_ = max(O[k], C[k]), min(O[k], C[k])
        i1 = h1["last"][k] + 1
        # primero la ENTRADA contra el rango vigente (vela recien cerrada), despues se actualiza el rango
        if ch > 3 and C[k] > O[k] and C[k] > rh and "L" not in hecho:
            hecho.add("L"); ords.append({"i": i1, "sg": 1, "sl": lambda e, x=4 * esc: e - x, "tp": lambda e, x=12 * esc: e + x, "trail": 7 * esc})
        if cl > 3 and C[k] < O[k] and C[k] < rl and "S" not in hecho:
            hecho.add("S"); ords.append({"i": i1, "sg": -1, "sl": lambda e, x=4 * esc: e + x, "tp": lambda e, x=12 * esc: e - x, "trail": 7 * esc})
        if H[k] > rh + 0.1 and bt_ > rbt + 0.1: rh, rbt, ch = H[k], bt_, 1
        else: ch += 1
        if L[k] < rl - 0.1 and bb_ < rbb - 0.1: rl, rbb, cl = L[k], bb_, 1
        else: cl += 1
    return ejecutar(m1, ords)

def ema921(m1):
    h1 = velas(m1, 60); h4 = velas(m1, 240); O, H, L, C = h1["O"], h1["H"], h1["L"], h1["C"]; n = len(C)
    e9, e21 = g.ema(C, 9), g.ema(C, 21); r = g.rsi(C, 14); a = g.atr(H, L, C, 14)
    e50h4 = g.ema(h4["C"], 50); h4map = {}; j = 0
    for k in range(n):                                      # ultima vela 4h CERRADA antes de esta 1h
        while j + 1 < len(h4["T"]) and h4["T"][j + 1] + timedelta(hours=4) <= h1["T"][k] + timedelta(hours=1): j += 1
        h4map[k] = j if h4["T"][j] + timedelta(hours=4) <= h1["T"][k] + timedelta(hours=1) else None
    ords = []; salidas_rsi_l = set(); salidas_rsi_s = set()
    for k in range(1, n):
        if r[k] is None: continue
        if r[k] >= 70: salidas_rsi_l.add(h1["last"][k] + 1)
        if r[k] <= 30: salidas_rsi_s.add(h1["last"][k] + 1)
    for k in range(30, n):
        t = h1["T"][k] + timedelta(hours=1)
        if not (13 <= t.hour <= 21 and t.weekday() < 5) or a[k] is None or h4map[k] is None: continue
        j4 = h4map[k]; up = h4["C"][j4] > e50h4[j4]; dn = h4["C"][j4] < e50h4[j4]
        lo5, hi5 = min(L[k - 4:k + 1]), max(H[k - 4:k + 1]); i1 = h1["last"][k] + 1
        if g.xup(e9, e21, k) and 50 <= r[k] <= 65 and up:
            ords.append({"i": i1, "sg": 1, "sl": lambda e, A=a[k], s=lo5 - .5: max(e - 2 * A, s), "tp": lambda e, A=a[k]: e + 3 * A,
                         "trail": a[k], "trail_desde": .5 * a[k], "salida": salidas_rsi_l})
        elif g.xdn(e9, e21, k) and 35 <= r[k] <= 50 and dn:
            ords.append({"i": i1, "sg": -1, "sl": lambda e, A=a[k], s=hi5 + .5: min(e + 2 * A, s), "tp": lambda e, A=a[k]: e - 3 * A,
                         "trail": a[k], "trail_desde": .5 * a[k], "salida": salidas_rsi_s})
    return ejecutar(m1, ords)

def sunrise(m1):
    m5 = velas(m1, 5); O, H, L, C = m5["O"], m5["H"], m5["L"], m5["C"]; n = len(C)
    e14, e24, e100 = g.ema(C, 14), g.ema(C, 24), g.ema(C, 100); a = g.atr(H, L, C, 10); ords = []; est = "scan"; cnt = 0; top = bot_ = None
    for k in range(101, n):
        cap = 2.0 * C[k] / 2000                              # tope de ATR del autor (2.00 a ~$2000) escalado al precio
        cruza_dn = C[k] < O[k] and any(C[k] < x[k] and C[k - 1] >= x[k - 1] for x in (e14, e24))
        if est != "scan" and cruza_dn: est = "scan"; continue
        if est == "scan":
            if any(C[k] > x[k] and C[k - 1] <= x[k - 1] for x in (e14, e24)) and C[k] > e100[k] and a[k] and 0 < a[k] <= cap:
                est = "pull"; cnt = 0
        elif est == "pull":
            if C[k] < O[k]:
                cnt += 1
                if cnt == 3: rg = H[k] - L[k]; top, bot_ = H[k] + .001 * rg, L[k] - .001 * rg; est = "win"
            else: est = "scan"
        elif est == "win":
            if H[k] >= top and C[k] > e100[k]:
                A = a[k]; ords.append({"i": m5["last"][k] + 1, "sg": 1, "sl": L[k] - 4.5 * A, "tp": H[k] + 6.5 * A}); est = "scan"
            else: est = "pull"; cnt = 0
    return ejecutar(m1, ords)

def crt(m1):
    m5 = velas(m1, 5); O, H, L, C = m5["O"], m5["H"], m5["L"], m5["C"]; n = len(C)
    e50, e21 = g.ema(C, 50), g.ema(C, 21); a = g.atr(H, L, C, 14); ords = []; rango = {}; usados = {}
    for k in range(n):
        t = m5["T"][k]
        if t.hour < 6: r_ = rango.setdefault(t.date(), [H[k], L[k]]); r_[0] = max(r_[0], H[k]); r_[1] = min(r_[1], L[k])
    for k in range(60, n):
        t = m5["T"][k] + timedelta(minutes=5); d = t.date()
        kz = 1 if 7 <= t.hour < 9 else (2 if 13 <= t.hour < 15 else 0)
        if not kz or d not in rango: continue
        ah, al = rango[d]; w = ah - al
        if not (20 <= w <= 100) or (d, kz) in usados or sum(1 for x in usados if x[0] == d) >= 2: continue
        for sg in (1, -1):
            if sg == 1:
                prof = al - min(L[k], L[k - 1]); dentro = C[k] > al and C[k] < ah; ext = min(L[k], L[k - 1]); mecha = (min(O[k], C[k]) - L[k]) / (H[k] - L[k] or 1)
            else:
                prof = max(H[k], H[k - 1]) - ah; dentro = C[k] < ah and C[k] > al; ext = max(H[k], H[k - 1]); mecha = (H[k] - max(O[k], C[k])) / (H[k] - L[k] or 1)
            if not (3 <= prof <= 50 and dentro): continue
            sc = 6 + (2 if prof >= 15 else 1 if prof >= 8 else 0) + (2 if mecha > .6 else 1 if mecha > .4 else 0)
            sesgo = 1 if C[k] > e50[k] and e50[k] > e50[k - 4] else (-1 if C[k] < e50[k] and e50[k] < e50[k - 4] else 0)
            sc += 2 if sesgo != -sg else 0
            sc += 1 if abs(C[k] - O[k]) / (H[k] - L[k] or 1) < .3 else 0
            sc += 1 if a[k] and .8 <= w / a[k] <= 2.5 else 0
            sc += 1 if abs(C[k] - e21[k]) <= 50 else 0
            if sc >= 8:
                usados[(d, kz)] = 1
                ords.append({"i": m5["last"][k] + 1, "sg": sg, "sl": ext - sg * 10, "tp": ah if sg == 1 else al,
                             "cierre_dt": datetime.combine(d, datetime.min.time()) + timedelta(hours=20)})
                break
    return ejecutar(m1, ords)

def zscore_m1(m1, desde_dias=300):
    T = m1["T"]; n = len(T); i0 = max(0, n - desde_dias * 1400)
    C = m1["C"][i0:]; H = m1["H"][i0:]; L = m1["L"][i0:]; m = len(C)
    s20 = g.sma(C, 20); sd = g.std(C, 20); a = g.atr(H, L, C, 14); a50 = g.sma([x or 0 for x in a], 50); _, _, adx = g.dmi(H, L, C, 14)
    h1 = velas({k: (m1[k][i0:]) for k in ("T", "O", "H", "L", "C")}, 60); s50 = g.sma(h1["C"], 50); hk = 0
    zz = [None if not g.ok(s20[i], sd[i]) or sd[i] == 0 else (C[i] - s20[i]) / sd[i] for i in range(m)]
    sal_l = {i0 + i + 1 for i in range(m) if zz[i] is not None and zz[i] >= -.2}; sal_s = {i0 + i + 1 for i in range(m) if zz[i] is not None and zz[i] <= .2}
    ords = []
    for i in range(60, m - 1):
        t = T[i0 + i]; sv = servidor(t)
        while hk + 1 < len(h1["T"]) and h1["T"][hk + 1] + timedelta(hours=1) <= t: hk += 1
        if zz[i] is None or adx[i] is None or not a50[i] or not s50[hk] or not (10 <= sv.hour < 20): continue
        cost = m1["Oa"][i0 + i] - m1["Ob"][i0 + i]
        if cost > .5 or adx[i] > 22 or not (.4 <= a[i] / a50[i] <= 2.0) or sd[i] < 3 * cost or abs(C[i] - s20[i]) < 4 * cost: continue
        if zz[i] <= -2.2 and C[i] >= C[i - 1] and C[i] > s50[hk]: sg = 1
        elif zz[i] >= 2.2 and C[i] <= C[i - 1] and C[i] < s50[hk]: sg = -1
        else: continue
        slx = max(8, 2.5 * a[i])
        ords.append({"i": i0 + i + 1, "sg": sg, "sl": lambda e, x=slx, s=sg: e - s * x, "t_max": 40, "be": (a[i], cost + .02),
                     "salida": sal_l if sg == 1 else sal_s})
    return ejecutar(m1, ords)

# ------------------------------------------------------------------ NUESTROS bots de oro (misma ejecucion)
def trend_nuestro(m1, completo=False):
    h1 = velas(m1, 60); O, H, L, C = h1["O"], h1["H"], h1["L"], h1["C"]; n = len(C); W = 600; ords = []; sal_l = set(); sal_s = set()
    for k in range(W, n):
        s = bt.signal_at(O[k - W + 1:k + 1], H[k - W + 1:k + 1], L[k - W + 1:k + 1], C[k - W + 1:k + 1], W - 1); i1 = h1["last"][k] + 1
        if s["exit_long"]: sal_l.add(i1)
        if s["exit_short"]: sal_s.add(i1)
        if s["long_break"]: ords.append({"i": i1, "sg": 1, "sl": lambda e, d=bt.ATR_STOP * s["atr"]: e - d, "trail": bt.ATR_STOP * s["atr"], "salida": sal_l})
        elif s["short_break"]: ords.append({"i": i1, "sg": -1, "sl": lambda e, d=bt.ATR_STOP * s["atr"]: e + d, "trail": bt.ATR_STOP * s["atr"], "salida": sal_s})
    return ejecutar(m1, ords)

def bollinger_nuestro(m1):
    m15 = velas(m1, 15); O, H, L, C = m15["O"], m15["H"], m15["L"], m15["C"]; n = len(C); W = 300; ords = []
    for k in range(W, n):
        s = bg.signal_last(O[k - W + 1:k + 1], H[k - W + 1:k + 1], L[k - W + 1:k + 1], C[k - W + 1:k + 1])
        if s.get("side") and s.get("atr"):
            d = bg.TRAIL_ATR * s["atr"]; sg = 1 if s["side"] == "BUY" else -1
            ords.append({"i": m15["last"][k] + 1, "sg": sg, "sl": lambda e, d=d, sg=sg: e - sg * d, "trail": d})
    return ejecutar(m1, ords)

def informe(nombre, tr):
    s = g.stats(tr)
    if not s: print(f"{nombre:<34} sin operaciones"); return
    por = {}
    for x in tr: por.setdefault(x["t"].year, 0); por[x["t"].year] += x["r"]
    print(f"{nombre:<34}{s['n']:>5}{s['tot']:>+8.1f}%{s['pf']:>6.2f}{s['dd']:>+7.1f}%   {s['ter'][0]:>+5.1f}/{s['ter'][1]:>+5.1f}/{s['ter'][2]:>+5.1f}  "
          f"{'ROB' if s['rob'] else '   '}  " + " ".join(f"{y}:{v:+.1f}" for y, v in sorted(por.items())), flush=True)

if __name__ == "__main__":
    m1 = cargar(); print(f"ORO 1m bid/ask {m1['T'][0]:%Y-%m-%d} -> {m1['T'][-1]:%Y-%m-%d} ({len(m1['T'])} minutos)")
    print(f"{'estrategia':<34}{'ops':>5}{'neto':>9}{'PF':>6}{'DD':>8}   tercios %           ROB  por anio %")
    informe("NUESTRO Trend oro (nucleo)", trend_nuestro(m1))
    informe("NUESTRO Bollinger oro (nucleo)", bollinger_nuestro(m1))
    informe("GOLD_ORB 303* (fiel, $ fijos)", gold_orb(m1))
    informe("GOLD_ORB (distancias x precio)", gold_orb(m1, escalar=True))
    informe("EMA 9/21 + filtros (a1shmuk)", ema921(m1))
    informe("Sunrise Ogle pullback 77*", sunrise(m1))
    informe("CRT barrido asiatico 58*", crt(m1))
    informe("Z-score M1 (ult. 300d)", zscore_m1(m1))
