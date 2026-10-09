#!/usr/bin/env python3
"""Estrategias PUBLICAS de GitHub re-implementadas (sin ejecutar codigo ajeno) y probadas con datos REALES de capital.com.

Fuentes (reglas leidas del codigo fuente, 9-oct-2026):
  A = freqtrade/freqtrade-strategies (la coleccion mas usada, ~5.500 estrellas)
  B = je-suis-tm/quant-trading (~11.000 estrellas)
Ejecucion estilo freqtrade: senal al cierre de la vela, entrada en la APERTURA de la siguiente; salidas por senal
(siguiente apertura), tabla ROI por minutos, stoploss % y trailing % (chequeados con el maximo/minimo de cada vela;
si en la misma vela tocan stop y objetivo se asume el STOP = pesimista). Costos: spread real ida+vuelta; en cripto
ademas financiamiento de largos 0.0616%/dia. Resultado en % del precio por operacion (nocional fijo), sumado.
Robustez: positivo en los 3 tercios cronologicos + PF >= 1.2 + >= 30 operaciones.
Adaptaciones: estrategias de 1m/5m se corren en 15m; condiciones de VOLUMEN se omiten (capital.com no da volumen
real); Dual Thrust y London Breakout (FX) se adaptan a la sesion de cada mercado.
Uso: python github_lab.py"""
import json, math, os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

D = "data"
COST = {"US500": 0.6, "US30": 2.0, "US100": 1.8, "RTY": 0.5, "NL25": 0.1, "GOLD": 0.6, "BTCUSD": 50.0, "ETHUSD": 1.75}
FIN_LONG = {"BTCUSD": 0.000616, "ETHUSD": 0.000616}          # por dia, solo largos
SESION = {"US500": ("America/New_York", (9, 30), (16, 0)), "US30": ("America/New_York", (9, 30), (16, 0)),
          "US100": ("America/New_York", (9, 30), (16, 0)), "RTY": ("America/New_York", (9, 30), (16, 0)),
          "NL25": ("Europe/Amsterdam", (9, 0), (17, 30)), "GOLD": ("Europe/London", (8, 0), (17, 0)),
          "BTCUSD": ("UTC", (0, 0), (23, 45)), "ETHUSD": ("UTC", (0, 0), (23, 45))}

# ---------------------------------------------------------------- datos
def _bidask(path):
    d = json.load(open(path)); m = lambda a, b: [(x + y) / 2 for x, y in zip(d[a], d[b])]
    return {"O": m("Ob", "Oa"), "H": m("Hb", "Ha"), "L": m("Lb", "La"), "C": m("Cb", "Ca"),
            "T": [datetime.fromisoformat(t) for t in d["T"]]}

def _mid(path):
    d = json.load(open(path))
    return {"O": d["O"], "H": d["H"], "L": d["L"], "C": d["C"], "T": [datetime.fromisoformat(t).replace(tzinfo=None) for t in d["T"]]}

def agg(b, minutes):
    out = {"O": [], "H": [], "L": [], "C": [], "T": []}; key = None
    for o, h, l, c, t in zip(b["O"], b["H"], b["L"], b["C"], b["T"]):
        if minutes >= 1440: k = t.replace(hour=0, minute=0)
        else:
            m = (t.hour * 60 + t.minute) // minutes * minutes; k = t.replace(hour=m // 60, minute=m % 60)
        if k != key:
            key = k; out["O"].append(o); out["H"].append(h); out["L"].append(l); out["C"].append(c); out["T"].append(k)
        else:
            out["H"][-1] = max(out["H"][-1], h); out["L"][-1] = min(out["L"][-1], l); out["C"][-1] = c
    return out

def mercados():
    M = {}
    for e in ("US500", "US30", "US100", "RTY", "NL25", "GOLD"):
        b = _bidask(f"{D}/capital_{e}_MINUTE_15_600d_bidask.json")
        M[e] = {"15m": b, "1h": agg(b, 60), "4h": agg(b, 240), "1d": agg(b, 1440)}
    for e in ("BTCUSD", "ETHUSD"):
        h = _bidask(f"{D}/capital_{e}_HOUR_1100d_bidask.json")
        M[e] = {"15m": _mid(f"{D}/capital_{e}_MINUTE_15_300d.json"), "1h": h, "4h": agg(h, 240), "1d": agg(h, 1440)}
    return M

# ---------------------------------------------------------------- indicadores (listas; None mientras calientan)
def sma(x, n):
    out = [None] * len(x); s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n: s -= x[i - n]
        if i >= n - 1: out[i] = s / n
    return out

def ema(x, n):
    out = [None] * len(x); a = 2 / (n + 1); e = None
    for i, v in enumerate(x):
        e = v if e is None else e + a * (v - e); out[i] = e
    return out

def std(x, n, ddof=1):
    out = [None] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]; m = sum(w) / n; out[i] = math.sqrt(sum((v - m) ** 2 for v in w) / (n - ddof))
    return out

def wilder(x, n):
    out = [None] * len(x); s = None; acc = []
    for i, v in enumerate(x):
        if s is None:
            acc.append(v)
            if len(acc) == n: s = sum(acc) / n; out[i] = s
        else:
            s = (s * (n - 1) + v) / n; out[i] = s
    return out

def rsi(c, n=14):
    g = [0.0] + [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]; l = [0.0] + [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = wilder(g[1:], n), wilder(l[1:], n); out = [None]
    for a, b in zip(ag, al): out.append(None if a is None else (100.0 if b == 0 else 100 - 100 / (1 + a / b)))
    return out

def trange(H, L, C):
    return [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(C))]

def atr(H, L, C, n=14): return wilder(trange(H, L, C), n)

def dmi(H, L, C, n=14):
    """+DI, -DI, ADX estilo TA-Lib (Wilder)."""
    pdm = [0.0]; mdm = [0.0]
    for i in range(1, len(C)):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if up > dn and up > 0 else 0.0); mdm.append(dn if dn > up and dn > 0 else 0.0)
    tr = wilder(trange(H, L, C), n); sp = wilder(pdm, n); sm = wilder(mdm, n)
    pdi = [None if t is None or t == 0 else 100 * a / t for a, t in zip(sp, tr)]
    mdi = [None if t is None or t == 0 else 100 * b / t for b, t in zip(sm, tr)]
    dx = [None if p is None or m is None or p + m == 0 else 100 * abs(p - m) / (p + m) for p, m in zip(pdi, mdi)]
    first = next((i for i, v in enumerate(dx) if v is not None), len(dx))
    adx = [None] * len(dx)
    for i, v in zip(range(first, len(dx)), wilder(dx[first:], n)): adx[i] = v
    return pdi, mdi, adx

def macd(c, f=12, s=26, sig=9):
    m = [a - b for a, b in zip(ema(c, f), ema(c, s))]; si = ema(m, sig); return m, si

def cci(H, L, C, n=14):
    tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]; m = sma(tp, n); out = [None] * len(C)
    for i in range(n - 1, len(C)):
        md = sum(abs(v - m[i]) for v in tp[i - n + 1:i + 1]) / n; out[i] = 0 if md == 0 else (tp[i] - m[i]) / (0.015 * md)
    return out

def cmo(c, n=14):
    out = [None] * len(c)
    for i in range(n, len(c)):
        up = sum(max(c[j] - c[j - 1], 0) for j in range(i - n + 1, i + 1)); dn = sum(max(c[j - 1] - c[j], 0) for j in range(i - n + 1, i + 1))
        out[i] = 0 if up + dn == 0 else 100 * (up - dn) / (up + dn)
    return out

def bb(x, n, k):
    m = sma(x, n); s = std(x, n)
    return m, [None if a is None else a + k * b for a, b in zip(m, s)], [None if a is None else a - k * b for a, b in zip(m, s)]

def supertrend(H, L, C, mult, period):
    tr = trange(H, L, C); at = sma(tr, period); n = len(C)
    fu = [0.0] * n; fl = [0.0] * n; st = [0.0] * n; d = [None] * n
    for i in range(period, n):
        hl2 = (H[i] + L[i]) / 2; bu = hl2 + mult * at[i]; bl = hl2 - mult * at[i]
        fu[i] = bu if (bu < fu[i - 1] or C[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = bl if (bl > fl[i - 1] or C[i - 1] < fl[i - 1]) else fl[i - 1]
        if st[i - 1] == fu[i - 1]: st[i] = fu[i] if C[i] <= fu[i] else fl[i]
        elif st[i - 1] == fl[i - 1]: st[i] = fl[i] if C[i] >= fl[i] else fu[i]
        if st[i] > 0: d[i] = "down" if C[i] < st[i] else "up"
    return d

def stochf(H, L, C, k=5, dd=3):
    fk = [None] * len(C)
    for i in range(k - 1, len(C)):
        hh, ll = max(H[i - k + 1:i + 1]), min(L[i - k + 1:i + 1]); fk[i] = 50.0 if hh == ll else 100 * (C[i] - ll) / (hh - ll)
    first = k - 1; fd = [None] * len(C)
    for i, v in zip(range(first, len(C)), sma(fk[first:], dd)): fd[i] = v
    return fk, fd

def ok(*v): return all(x is not None for x in v)
def xup(a, b, i): return ok(a[i], b[i], a[i - 1], b[i - 1]) and a[i] > b[i] and a[i - 1] <= b[i - 1]
def xdn(a, b, i): return ok(a[i], b[i], a[i - 1], b[i - 1]) and a[i] < b[i] and a[i - 1] >= b[i - 1]

# ---------------------------------------------------------------- simulador
def simular(b, epic, el, es=None, xl=None, xs=None, roi=None, sl=None, trail=None, profit_only=False, reverse=False,
            minutos=60, fin_dias=None, dist=None):
    """el/es/xl/xs: listas booleanas (senal al CIERRE de la vela i). dist: lista con la distancia del trailing en PRECIO
    fijada en la vela de senal (stop dinamico de nuestros bots: k x ATR desde el extremo). Devuelve operaciones {r, t}."""
    O, H, L, C, T = b["O"], b["H"], b["L"], b["C"], b["T"]; n = len(C); es = es or [False] * n
    xl = xl or [False] * n; xs = xs or [False] * n; cost = COST[epic]; fin = FIN_LONG.get(epic, 0)
    roi_t = sorted((roi or {}).items()); tr = []; pos = None; pend = None; pend_d = None

    def cerrar(px, i):
        nonlocal pos
        g = pos["sg"] * (px - pos["e"]) - cost
        dias = (T[i] - T[pos["i"]]).total_seconds() / 86400 if pos["sg"] == 1 else 0
        adv = (min(pos["lo"], px) - pos["e"]) / pos["e"] if pos["sg"] == 1 else (pos["e"] - max(pos["hi"], px)) / pos["e"]
        tr.append({"r": 100 * g / pos["e"] - 100 * fin * dias, "t": T[pos["i"]], "mae": 100 * adv, "barras": i - pos["i"],
                   "sg": pos["sg"]}); pos = None

    for i in range(1, n):
        if pend is not None and pos is None:                       # entrada en la apertura
            pos = {"sg": pend, "e": O[i], "i": i, "hi": O[i], "lo": O[i], "d": pend_d}; pend = None
        if pos is not None:
            sg, e = pos["sg"], pos["e"]
            mins = (T[i] - T[pos["i"]]).total_seconds() / 60
            stop = None
            if sl is not None: stop = e * (1 + sg * sl)
            if trail:                                               # (positive, offset, only_offset)
                pv, off, only = trail; best = pos["hi"] if sg == 1 else pos["lo"]; gain = sg * (best - e) / e
                if gain >= off:
                    ts = best * (1 - sg * pv); stop = ts if stop is None else (max(stop, ts) if sg == 1 else min(stop, ts))
                elif not only and sl is not None:
                    ts = best * (1 + sg * sl); stop = max(stop, ts) if sg == 1 else min(stop, ts)
            if pos.get("d"):                                        # trailing k x ATR (nuestros bots)
                ts = pos["hi"] - pos["d"] if sg == 1 else pos["lo"] + pos["d"]
                stop = ts if stop is None else (max(stop, ts) if sg == 1 else min(stop, ts))
            tgt = None
            for k, r in roi_t:
                if mins >= k: tgt = r
            hit = None
            if stop is not None and ((sg == 1 and L[i] <= stop) or (sg == -1 and H[i] >= stop)):
                hit = min(O[i], stop) if sg == 1 else max(O[i], stop)
            elif tgt is not None:
                lvl = e * (1 + sg * tgt)
                if (sg == 1 and H[i] >= lvl) or (sg == -1 and L[i] <= lvl):
                    hit = max(O[i], lvl) if sg == 1 else min(O[i], lvl)
            if hit is not None:
                cerrar(hit, i)
            else:
                pos["hi"] = max(pos["hi"], H[i]); pos["lo"] = min(pos["lo"], L[i])
        # senales al cierre de i -> actuan en i+1
        if pos is not None:
            sal = (xl[i] if pos["sg"] == 1 else xs[i]) or (reverse and (es[i] if pos["sg"] == 1 else el[i]))
            if sal and (not profit_only or pos["sg"] * (C[i] - pos["e"]) > 0) and i + 1 < n:
                cerrar(O[i + 1], i + 1)
                if reverse: pend = -1 if el[i] is False and es[i] else (1 if el[i] else None)
        if pos is None and pend is None and i + 1 < n:
            if el[i]: pend = 1
            elif es[i]: pend = -1
            if pend is not None: pend_d = dist[i] if dist else None
    return tr

def sesion_sim(b, epic, nivel_fn, stop_tgt=None):
    """Para Dual Thrust / ORB: nivel_fn(dia) -> (arriba, abajo, inicio_entradas, fin_entradas); cierre al fin de sesion."""
    tz, (h0, m0), (h1, m1) = SESION[epic]; Z = ZoneInfo(tz); cost = COST[epic]; tr = []
    dias = {}
    for i, t in enumerate(b["T"]):
        lt = t.replace(tzinfo=ZoneInfo("UTC")).astimezone(Z); dias.setdefault(lt.date(), []).append((i, lt))
    claves = sorted(dias)
    for j, dkey in enumerate(claves):
        filas = [(i, lt) for i, lt in dias[dkey] if (lt.hour, lt.minute) >= (h0, m0) and (lt.hour, lt.minute) < (h1, m1)]
        if len(filas) < 4: continue
        niv = nivel_fn(b, dias, claves, j, filas)
        if not niv: continue
        up, dn, desde, hasta = niv; pos = None
        for i, lt in filas:
            O, H, L, C = b["O"][i], b["H"][i], b["L"][i], b["C"][i]
            if pos:
                sg, e = pos
                if stop_tgt:
                    s, g = e * (1 - sg * stop_tgt), e * (1 + sg * stop_tgt)
                    if (sg == 1 and L <= s) or (sg == -1 and H >= s):
                        tr.append({"r": 100 * (sg * (s - e) - cost) / e, "t": b["T"][i]}); pos = "fin"; break
                    if (sg == 1 and H >= g) or (sg == -1 and L <= g):
                        tr.append({"r": 100 * (sg * (g - e) - cost) / e, "t": b["T"][i]}); pos = "fin"; break
                if (sg == 1 and C < dn) or (sg == -1 and C > up):          # ruptura contraria -> da vuelta (Dual Thrust)
                    if not stop_tgt:
                        tr.append({"r": 100 * (sg * (C - e) - cost) / e, "t": b["T"][i]}); pos = (-sg, C); continue
            elif desde <= (lt.hour, lt.minute) <= hasta:
                if C > up: pos = (1, C)
                elif C < dn: pos = (-1, C)
        if pos and pos != "fin":
            i = filas[-1][0]; sg, e = pos; tr.append({"r": 100 * (sg * (b["C"][i] - e) - cost) / e, "t": b["T"][i]})
    return tr

# ---------------------------------------------------------------- estrategias
def S_supertrend(b):
    H, L, C = b["H"], b["L"], b["C"]
    bs = [supertrend(H, L, C, m, p) for m, p in ((4, 8), (7, 9), (1, 8))]; ss = [supertrend(H, L, C, m, p) for m, p in ((1, 16), (3, 18), (6, 18))]
    n = len(C); el = [all(x[i] == "up" for x in bs) for i in range(n)]; xl = [all(x[i] == "down" for x in ss) for i in range(n)]
    return dict(el=el, xl=xl, roi={0: .087, 372: .058, 861: .029, 2221: 0}, sl=-.265, trail=(.05, .144, False))

def S_fsupertrend(b):
    H, L, C = b["H"], b["L"], b["C"]
    bs = [supertrend(H, L, C, m, p) for m, p in ((4, 8), (7, 9), (1, 8))]; s2 = supertrend(H, L, C, 3, 18)
    n = len(C); return dict(el=[all(x[i] == "up" for x in bs) for i in range(n)], xl=[s2[i] == "down" for i in range(n)],
                            roi={0: .10, 30: .75, 60: .05, 120: .025}, sl=-.265, trail=(.05, .10, False))

def S_volsystem(b):
    """VolatilitySystem: velas 3h (desde 1h), ATR14x2; senal si el cambio de cierre 3h supera el ATR previo; siempre en mercado."""
    T = b["T"]; n = len(T); blk = {}
    for i, t in enumerate(T): blk.setdefault(t.replace(hour=t.hour // 3 * 3), []).append(i)
    ks = sorted(blk); O3 = [b["O"][blk[k][0]] for k in ks]; H3 = [max(b["H"][j] for j in blk[k]) for k in ks]
    L3 = [min(b["L"][j] for j in blk[k]) for k in ks]; C3 = [b["C"][blk[k][-1]] for k in ks]
    a3 = [None if v is None else 2 * v for v in atr(H3, L3, C3, 14)]; ch = [None] + [C3[j] - C3[j - 1] for j in range(1, len(C3))]
    A = [None] * n; CH = [None] * n
    for j, k in enumerate(ks):                                    # se adjunta a la ultima vela 1h del bloque y se arrastra
        last = blk[k][-1]; A[last] = a3[j]; CH[last] = ch[j]
    for i in range(1, n):
        if A[i] is None: A[i] = A[i - 1]; CH[i] = CH[i - 1] if CH[i] is None else CH[i]
    el = [i > 0 and ok(CH[i], A[i - 1]) and CH[i] > A[i - 1] for i in range(n)]
    es = [i > 0 and ok(CH[i], A[i - 1]) and -CH[i] > A[i - 1] for i in range(n)]
    return dict(el=el, es=es, reverse=True)

def S_fadxsma(b):
    H, L, C = b["H"], b["L"], b["C"]; _, _, adx = dmi(H, L, C, 14); s1, s2 = sma(C, 12), sma(C, 48); n = len(C)
    el = [ok(adx[i]) and adx[i] > 30 and xup(s1, s2, i) for i in range(n)]; es = [ok(adx[i]) and adx[i] > 30 and xdn(s1, s2, i) for i in range(n)]
    x = [ok(adx[i]) and adx[i] < 30 for i in range(n)]
    return dict(el=el, es=es, xl=x, xs=x, roi={0: .05, 30: .10, 60: .075}, sl=-.05)

def S_bbandrsi(b):
    H, L, C = b["H"], b["L"], b["C"]; tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]; _, _, lo = bb(tp, 20, 2); r = rsi(C, 14); n = len(C)
    return dict(el=[ok(r[i], lo[i]) and r[i] < 30 and C[i] < lo[i] for i in range(n)], xl=[ok(r[i]) and r[i] > 70 for i in range(n)],
                roi={0: .10}, sl=-.25)

def S_binhv45(b):
    C, L = b["C"], b["L"]; mid, _, lo = bb(C, 40, 2); n = len(C); el = [False] * n
    for i in range(1, n):
        if not ok(mid[i], lo[i], lo[i - 1]): continue
        bd = abs(mid[i] - lo[i]); cd = abs(C[i] - C[i - 1]); tail = abs(C[i] - L[i])
        el[i] = lo[i - 1] > 0 and bd > C[i] * 7 / 1000 and cd > C[i] * 17 / 1000 and tail < bd * 25 / 1000 and C[i] < lo[i - 1] and C[i] <= C[i - 1]
    return dict(el=el, roi={0: .0125}, sl=-.05)

def S_cluc(b):
    H, L, C = b["H"], b["L"], b["C"]; tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]; mid, _, lo = bb(tp, 20, 2); e50 = ema(C, 50); n = len(C)
    return dict(el=[ok(lo[i]) and C[i] < e50[i] and C[i] < 0.985 * lo[i] for i in range(n)], xl=[ok(mid[i]) and C[i] > mid[i] for i in range(n)],
                roi={0: .01}, sl=-.05)

def S_adxmom(b):
    H, L, C = b["H"], b["L"], b["C"]; _, _, adx = dmi(H, L, C, 14); pdi, mdi, _ = dmi(H, L, C, 25)
    mom = [None] * 14 + [C[i] - C[i - 14] for i in range(14, len(C))]; n = len(C)
    el = [ok(adx[i], pdi[i], mdi[i], mom[i]) and adx[i] > 25 and mom[i] > 0 and pdi[i] > 25 and pdi[i] > mdi[i] for i in range(n)]
    xl = [ok(adx[i], pdi[i], mdi[i], mom[i]) and adx[i] > 25 and mom[i] < 0 and mdi[i] > 25 and pdi[i] < mdi[i] for i in range(n)]
    return dict(el=el, xl=xl, roi={0: .01}, sl=-.25)

def S_macdstrat(b):
    H, L, C = b["H"], b["L"], b["C"]; m, s = macd(C); cc_ = cci(H, L, C, 14); n = len(C)
    return dict(el=[ok(cc_[i]) and m[i] > s[i] and cc_[i] <= -48 for i in range(n)], xl=[ok(cc_[i]) and m[i] < s[i] and cc_[i] >= 687 for i in range(n)],
                roi={0: .05, 20: .04, 30: .03, 60: .01}, sl=-.30)

def S_awesomemacd(b):
    H, L, C = b["H"], b["L"], b["C"]; hl = [(h + l) / 2 for h, l in zip(H, L)]; a, c_ = sma(hl, 5), sma(hl, 34)
    ao = [None if not ok(x, y) else x - y for x, y in zip(a, c_)]; m, _ = macd(C); n = len(C)
    el = [i > 0 and ok(ao[i], ao[i - 1]) and m[i] > 0 and ao[i] > 0 and ao[i - 1] < 0 for i in range(n)]
    xl = [i > 0 and ok(ao[i], ao[i - 1]) and m[i] < 0 and ao[i] < 0 and ao[i - 1] > 0 for i in range(n)]
    return dict(el=el, xl=xl, roi={0: .10}, sl=-.25)

def S_cmcwinner(b):   # sin MFI (volumen)
    H, L, C = b["H"], b["L"], b["C"]; c_ = cci(H, L, C, 14); cm = cmo(C, 14); n = len(C)
    el = [i > 0 and ok(c_[i - 1], cm[i - 1]) and c_[i - 1] < -100 and cm[i - 1] < -50 for i in range(n)]
    xl = [i > 0 and ok(c_[i - 1], cm[i - 1]) and c_[i - 1] > 100 and cm[i - 1] > 50 for i in range(n)]
    return dict(el=el, xl=xl, roi={0: .05, 20: .03, 30: .02, 40: 0}, sl=-.05)

def S_strategy005(b):  # sin filtro de volumen
    H, L, C = b["H"], b["L"], b["C"]; m, _ = macd(C); _, mdi, _ = dmi(H, L, C, 14); r = rsi(C, 14); fk, fd = stochf(H, L, C, 5, 3); s40 = sma(C, 40); n = len(C)
    fr = [None if v is None else 50 * (math.tanh(0.1 * (v - 50)) + 1) for v in r]
    el = [ok(s40[i], fd[i], fk[i], r[i]) and C[i] < s40[i] and fd[i] > fk[i] and r[i] > 26 and fd[i] > 1 and fr[i] < 5 for i in range(n)]
    xl = [i > 0 and ok(r[i], r[i - 1], mdi[i]) and r[i] > 74 and r[i - 1] <= 74 and m[i] < 0 and mdi[i] > 4 for i in range(n)]
    return dict(el=el, xl=xl, roi={0: .05, 20: .04, 40: .03, 80: .02, 1440: .01}, sl=-.10, profit_only=True)

def S_hlhb(b):
    H, L, C, O = b["H"], b["L"], b["C"], b["O"]; hl2 = [(c + o) / 2 for c, o in zip(C, O)]; r = rsi(hl2, 10); e5, e10 = ema(C, 5), ema(C, 10); _, _, adx = dmi(H, L, C, 14)
    fifty = [50.0] * len(C); n = len(C)
    el = [ok(adx[i]) and xup(r, fifty, i) and xup(e5, e10, i) and adx[i] > 25 for i in range(n)]
    xl = [ok(adx[i]) and xdn(r, fifty, i) and xdn(e5, e10, i) and adx[i] > 25 for i in range(n)]
    return dict(el=el, xl=xl, roi={0: .6225, 703: .2187, 2849: .0363, 5520: 0}, sl=-.3211, trail=(.0117, .0186, True))

def S_bandtastic(b):   # salida sin MFI
    H, L, C = b["H"], b["L"], b["C"]; tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]
    _, _, lo1 = bb(tp, 20, 1); _, up2, _ = bb(tp, 20, 2); n = len(C)
    return dict(el=[ok(lo1[i]) and C[i] < lo1[i] for i in range(n)], xl=[ok(up2[i]) and C[i] > up2[i] for i in range(n)],
                roi={0: .162, 69: .097, 229: .061, 566: 0}, sl=-.345, trail=(.01, .058, False))

def S_trendfollow(b):  # cruce EMA20 sin OBV
    C = b["C"]; e = ema(C, 20); n = len(C)
    return dict(el=[i > 0 and C[i] > e[i] and C[i - 1] <= e[i - 1] for i in range(n)], xl=[i > 0 and C[i] < e[i] and C[i - 1] >= e[i - 1] for i in range(n)],
                roi={0: .15, 30: .10, 60: .05}, sl=-.265, trail=(.05, .10, False))

def _estado(b, longf, shortf=None):
    """Repo B: posicion objetivo por vela (long-flat o long-short) -> senales de cambio."""
    n = len(b["C"]); el = [False] * n; es = [False] * n; xl = [False] * n; xs = [False] * n
    for i in range(n):
        lg = longf(i); sh = shortf(i) if shortf else False
        el[i] = bool(lg); es[i] = bool(sh); xl[i] = not lg; xs[i] = not sh
    return dict(el=el, es=es, xl=xl, xs=xs)

def S_heikin(b):
    O, H, L, C = b["O"], b["H"], b["L"], b["C"]; n = len(C); hc = [(o + h + l + c) / 4 for o, h, l, c in zip(O, H, L, C)]
    ho = [O[0]] + [0.0] * (n - 1)
    for i in range(1, n): ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    hh = [max(ho[i], hc[i], H[i], L[i]) for i in range(n)]; hl = [min(ho[i], hc[i], H[i], L[i]) for i in range(n)]
    el = [i > 0 and ho[i] > hc[i] and ho[i] == hh[i] and abs(ho[i] - hc[i]) > abs(ho[i - 1] - hc[i - 1]) and ho[i - 1] > hc[i - 1] for i in range(n)]
    xl = [i > 0 and ho[i] < hc[i] and ho[i] == hl[i] and ho[i - 1] < hc[i - 1] for i in range(n)]
    return dict(el=el, xl=xl)

def S_psar(b):
    H, L, C = b["H"], b["L"], b["C"]; n = len(C); trend = [0] * n; sar = [0.0] * n; ep = [0.0] * n; af = [0.0] * n; real = [None] * n
    trend[1] = 1 if C[1] > C[0] else -1; sar[1] = H[0] if trend[1] > 0 else L[0]; ep[1] = H[1] if trend[1] > 0 else L[1]; af[1] = .02
    for i in range(2, n):
        tmp = sar[i - 1] + af[i - 1] * (ep[i - 1] - sar[i - 1])
        if trend[i - 1] < 0:
            sar[i] = max(tmp, H[i - 1], H[i - 2]); trend[i] = 1 if sar[i] < H[i] else trend[i - 1] - 1
        else:
            sar[i] = min(tmp, L[i - 1], L[i - 2]); trend[i] = -1 if sar[i] > L[i] else trend[i - 1] + 1
        if trend[i] < 0: ep[i] = L[i] if trend[i] == -1 else min(L[i], ep[i - 1])
        else: ep[i] = H[i] if trend[i] == 1 else max(H[i], ep[i - 1])
        if abs(trend[i]) == 1: af[i] = .02; real[i] = ep[i - 1]
        else:
            real[i] = sar[i]; af[i] = af[i - 1] if ep[i] == ep[i - 1] else min(.2, af[i - 1] + .02)
    return _estado(b, lambda i: real[i] is not None and real[i] < C[i])

def S_ao(b):
    hl = [(h + l) / 2 for h, l in zip(b["H"], b["L"])]; a, c_ = sma(hl, 5), sma(hl, 34)
    return _estado(b, lambda i: ok(a[i], c_[i]) and a[i] > c_[i])

def S_macross(b):
    C = b["C"]; a, c_ = sma(C, 10), sma(C, 21)
    return _estado(b, lambda i: ok(a[i], c_[i]) and a[i] >= c_[i])

def S_rsipattern(b):
    r = rsi(b["C"], 14)
    return _estado(b, lambda i: ok(r[i]) and r[i] < 30, lambda i: ok(r[i]) and r[i] > 70)

def N_dualthrust(b, dias, claves, j, filas):
    """Rango con las 5 sesiones ANTERIORES (sin mirar el dia actual); k=0.5; entradas toda la sesion."""
    if j < 5: return None
    prev = []
    for d in claves[j - 5:j]:
        idx = [i for i, lt in dias[d]]
        if idx: prev.append((max(b["H"][i] for i in idx), min(b["L"][i] for i in idx), b["C"][idx[-1]]))
    if len(prev) < 5: return None
    HH = max(p[0] for p in prev); LC = min(p[2] for p in prev); HC = max(p[2] for p in prev); LL = min(p[1] for p in prev)
    rg = max(HH - LC, HC - LL); op = b["O"][filas[0][0]]
    return op + .5 * rg, op - .5 * rg, (0, 0), (23, 59)

def N_orb(b, dias, claves, j, filas):
    """London Breakout adaptado: rango de la PRIMERA hora de sesion, entradas solo los 30 min siguientes."""
    t0 = filas[0][1]; pri = [i for i, lt in filas if lt < t0 + timedelta(hours=1)]
    if len(pri) < 2: return None
    fin_rango = t0 + timedelta(hours=1); a = (fin_rango.hour, fin_rango.minute); z = fin_rango + timedelta(minutes=29)
    return max(b["H"][i] for i in pri), min(b["L"][i] for i in pri), a, (z.hour, z.minute)

ESTRATEGIAS = [  # (codigo, fuente, funcion, marcos a probar)
    ("Supertrend", "A", S_supertrend, ("1h",)), ("FSupertrend", "A", S_fsupertrend, ("1h",)),
    ("VolatilitySystem", "A", S_volsystem, ("1h",)), ("FAdxSma", "A", S_fadxsma, ("1h",)),
    ("BbandRsi", "A", S_bbandrsi, ("1h",)), ("BinHV45*", "A", S_binhv45, ("15m",)), ("ClucMay72018*", "A", S_cluc, ("15m",)),
    ("ADXMomentum", "A", S_adxmom, ("1h",)), ("MACDStrategy*", "A", S_macdstrat, ("15m",)), ("AwesomeMacd", "A", S_awesomemacd, ("1h",)),
    ("CMCWinner(sinMFI)", "A", S_cmcwinner, ("15m",)), ("Strategy005*", "A", S_strategy005, ("15m",)), ("hlhb", "A", S_hlhb, ("4h",)),
    ("Bandtastic(sinMFI)", "A", S_bandtastic, ("15m",)), ("TrendFollow(sinOBV)*", "A", S_trendfollow, ("15m",)),
    ("Heikin-Ashi", "B", S_heikin, ("1d", "1h")), ("ParabolicSAR", "B", S_psar, ("1d", "1h")), ("AwesomeOsc", "B", S_ao, ("1d", "1h")),
    ("MA cross 10/21", "B", S_macross, ("1d", "1h")), ("RSI 30/70", "B", S_rsipattern, ("1h", "15m")),
]

def stats(tr):
    if not tr: return None
    tr = sorted(tr, key=lambda x: x["t"]); v = [x["r"] for x in tr]; tot = sum(v)
    w = sum(x for x in v if x > 0); l = -sum(x for x in v if x <= 0); eq = pk = dd = 0
    for x in v: eq += x; pk = max(pk, eq); dd = min(dd, eq - pk)
    t0, t1 = tr[0]["t"], tr[-1]["t"]; span = (t1 - t0) / 3 if t1 > t0 else timedelta(1)
    ter = [0.0] * 3
    for x in tr: ter[min(2, int((x["t"] - t0) / span))] += x["r"]
    pf = w / l if l else 9.0
    return {"n": len(v), "tot": tot, "pf": pf, "dd": dd, "ter": ter, "rob": all(x > 0 for x in ter) and pf >= 1.2 and len(v) >= 30}

if __name__ == "__main__":
    M = mercados(); filas = []
    for nombre, src, fn, marcos in ESTRATEGIAS:
        for tf in marcos:
            for e in M:
                b = M[e][tf]; p = fn(b); mins = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}[tf]
                tr = simular(b, e, p["el"], p.get("es"), p.get("xl"), p.get("xs"), p.get("roi"), p.get("sl"), p.get("trail"),
                             p.get("profit_only", False), p.get("reverse", False), mins)
                s = stats(tr); filas.append((nombre, src, tf, e, s))
        print(f"listo {nombre}", file=sys.stderr, flush=True)
    for nombre, fn in (("DualThrust(sesion)", N_dualthrust), ("LondonBreakout->ORB", N_orb)):
        for e in M:
            tr = sesion_sim(M[e]["15m"], e, fn, stop_tgt=(0.004 if "ORB" in nombre else None)); filas.append((nombre, "B", "15m", e, stats(tr)))
        print(f"listo {nombre}", file=sys.stderr, flush=True)
    json.dump([(a, b_, c, d, s) for a, b_, c, d, s in filas], open(f"{D}/github_lab_res.json", "w"), default=str)
    print(f"{'estrategia':<22}{'tf':>4} {'mercado':<7}{'ops':>5}{'neto %':>9}{'PF':>6}{'DD %':>8}   tercios %            ROB")
    for nombre, src, tf, e, s in filas:
        if not s: print(f"{nombre:<22}{tf:>4} {e:<7}  sin operaciones"); continue
        print(f"{nombre:<22}{tf:>4} {e:<7}{s['n']:>5}{s['tot']:>+9.1f}{s['pf']:>6.2f}{s['dd']:>+8.1f}   "
              f"{s['ter'][0]:>+6.1f}/{s['ter'][1]:>+6.1f}/{s['ter'][2]:>+6.1f}  {'<< ROB' if s['rob'] else ''}")
