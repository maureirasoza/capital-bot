#!/usr/bin/env python3
"""Prueba de filtros de CONTEXTO sobre la cartera de 5 bots de reversion de indices (600d, 15m mid, senal real):
  1) TIPO DE DIA: no comprar si el indice ya cayo > X x rango diario medio en las ultimas N horas (y simetrico
     para ventas); variante 'desde el inicio de la sesion'.
  2) MAXIMO DE BOTS EN LA MISMA DIRECCION: no abrir si ya hay >= K bots de indices de EE.UU. abiertos en ese lado.
  4) MARCO MAYOR: no comprar bajo la EMA larga (1h) ni vender sobre ella.
Simulacion conjunta (reloj comun), salida = trailing real de cada bot. Mitades + 6 tramos, por bot y cartera."""
import sys, math
from datetime import timedelta
from ctx_base import BOTS, W, load, signals
S = signals()
D = {}
for name, mod, epic, cost, usd, gaps in BOTS:
    O, H, L, C, T = load(epic); n = len(C)
    # rango diario medio (dias UTC, ultimos 14 dias completos) -> escala del "cuanto se movio hoy"
    day_rng = {}; 
    for i in range(n):
        k = T[i].date(); r = day_rng.get(k)
        day_rng[k] = (max(r[0], H[i]), min(r[1], L[i])) if r else (H[i], L[i])
    days = sorted(day_rng); rng = {d: day_rng[d][0] - day_rng[d][1] for d in days}
    datr = {}
    for j, d in enumerate(days):
        prev = [rng[x] for x in days[max(0, j-14):j]]; datr[d] = sum(prev) / len(prev) if prev else None
    DA = [datr[T[i].date()] for i in range(n)]
    # inicio de sesion: EE.UU. 22:00 UTC (rollover CFD); NL25 primera vela del dia
    sess = [0] * n; s0 = 0
    for i in range(n):
        if i and ((T[i] - T[i-1]).total_seconds() > 3600 or (not gaps and T[i].hour == 22 and T[i].minute == 0)
                  or (gaps and T[i].date() != T[i-1].date())):
            s0 = i
        sess[i] = s0
    D[name] = dict(O=O, H=H, L=L, C=C, T=T, n=n, DA=DA, sess=sess, cost=cost, usd=usd, gaps=gaps,
                   trail=mod.TRAIL_ATR, sig=S[name]["sig"], atr=S[name]["atr"], idx={t: i for i, t in enumerate(T)}, ema={})
def ema(name, per):
    d = D[name]
    if per not in d["ema"]:
        a = 2 / (per + 1); e = d["C"][0]; out = []
        for c in d["C"]: e = e + a * (c - e); out.append(e)
        d["ema"][per] = out
    return d["ema"][per]
CLOCK = sorted(set(t for d in D.values() for t in d["T"]))
US = ("SP500", "US30", "US100", "RTY")

def run(f_dia=None, f_ema=None, max_lado=None, orden=("SP500", "RTY", "US30", "US100", "NL25"), bloquear=None):
    pos = {k: None for k in D}; trades = {k: [] for k in D}
    for ts in CLOCK:
        # 1) salidas de todos
        for k in orden:
            d = D[k]; i = d["idx"].get(ts); p = pos[k]
            if i is None or p is None or i <= p["i"]: continue
            sg = p["sg"]; ex = None
            if sg == 1 and d["L"][i] <= p["stop"]: ex = min(p["stop"], d["O"][i]) if d["gaps"] else p["stop"]
            elif sg == -1 and d["H"][i] >= p["stop"]: ex = max(p["stop"], d["O"][i]) if d["gaps"] else p["stop"]
            if ex is not None:
                trades[k].append({"t": d["T"][p["i"]], "tout": ts, "net": (sg * (ex - p["e"]) - d["cost"]) * d["usd"]}); pos[k] = None
            else:
                p["x"] = max(p["x"], d["H"][i]) if sg == 1 else min(p["x"], d["L"][i])
                p["stop"] = max(p["stop"], p["x"] - p["dist"]) if sg == 1 else min(p["stop"], p["x"] + p["dist"])
        # 2) entradas (al cierre de la vela de senal)
        for k in orden:
            d = D[k]; i = d["idx"].get(ts)
            if i is None or i < W or pos[k] is not None or not d["sig"][i]: continue
            if d["gaps"] and (i + 1 >= d["n"] or (d["T"][i+1] - d["T"][i]).total_seconds() > 1350): continue
            sg = 1 if d["sig"][i] == "BUY" else -1; C = d["C"]
            if f_dia and d["DA"][i]:
                modo, N, X = f_dia
                j = d["sess"][i] if modo == "sesion" else max(0, i - 4 * N)
                ref = d["O"][j] if modo == "sesion" else C[j]
                mv = (C[i] - ref) / d["DA"][i]
                if (sg == 1 and mv < -X) or (sg == -1 and mv > X): continue
            if f_ema:
                e = ema(k, f_ema)[i]
                if (sg == 1 and C[i] < e) or (sg == -1 and C[i] > e): continue
            if bloquear and bloquear(k, ts, sg): continue
            if max_lado and k in US and sum(1 for q in US if q != k and pos[q] and pos[q]["sg"] == sg) >= max_lado: continue
            dist = d["trail"] * d["atr"][i]
            pos[k] = {"i": i, "sg": sg, "e": C[i], "x": C[i], "dist": dist, "stop": C[i] - sg * dist}
    return trades

def stats(tr):
    tr = sorted(tr, key=lambda x: x["tout"]); tot = sum(x["net"] for x in tr); eq = pk = dd = 0
    for x in tr: eq += x["net"]; pk = max(pk, eq); dd = min(dd, eq - pk)
    w = sum(x["net"] for x in tr if x["net"] > 0); l = -sum(x["net"] for x in tr if x["net"] <= 0)
    return tot, (w / l if l else 9), dd, len(tr)
T0 = CLOCK[W * 2]; T1 = CLOCK[-1]; MID = T0 + (T1 - T0) / 2; SPAN = (T1 - T0) / 6
def seg6(tr):
    o = [0.0] * 6
    for x in tr: o[min(5, max(0, int((x["t"] - T0) / SPAN)))] += x["net"]
    return o
BASE = run(); BALL = [x for v in BASE.values() for x in v]; B = stats(BALL); BS = seg6(BALL)
BH = (stats([x for x in BALL if x["t"] < MID])[0], stats([x for x in BALL if x["t"] >= MID])[0])
print(f"Cartera 5 bots {T0:%Y-%m-%d} -> {T1:%Y-%m-%d}: BASE ${B[0]:+.0f} PF {B[1]:.2f} DD ${B[2]:.0f} ({B[3]} ops) | mitades ${BH[0]:+.0f}/${BH[1]:+.0f}")
print("   por bot: " + " | ".join(f"{k} ${stats(v)[0]:+.0f}" for k, v in BASE.items()))
def linea(etq, tr):
    al = [x for v in tr.values() for x in v]; s = stats(al); h1 = stats([x for x in al if x["t"] < MID])[0]; h2 = stats([x for x in al if x["t"] >= MID])[0]
    sg = seg6(al); nseg = sum(1 for a, b in zip(sg, BS) if a > b); botsok = sum(1 for k in tr if stats(tr[k])[0] > stats(BASE[k])[0])
    ok = "*" if (h1 > BH[0] and h2 > BH[1] and nseg >= 4) else " "
    print(f"{etq:<34} ${s[0]:+6.0f} ({100*(s[0]-B[0])/abs(B[0]):+4.0f}%) PF {s[1]:.2f} DD ${s[2]:5.0f} ops {s[3]:>4} | mit {h1-BH[0]:+5.0f}/{h2-BH[1]:+5.0f} | tramos {nseg}/6 | bots mejor {botsok}/5 {ok}")
    return s[0]
if __name__ == "__main__":
    print("\n--- 1) TIPO DE DIA: bloquear compra si cayo > X x rango diario medio (venta simetrica) ---")
    for modo, N in (("ventana", 4), ("ventana", 8), ("ventana", 16), ("sesion", 0)):
        for X in (0.5, 0.75, 1.0, 1.5):
            linea(f"{modo} {N}h X={X}" if modo == "ventana" else f"desde inicio sesion X={X}", run(f_dia=(modo, N, X)))
    print("\n--- 2) MAXIMO DE BOTS DE EE.UU. EN EL MISMO LADO (K = otros ya abiertos) ---")
    for K in (1, 2, 3):
        linea(f"max otros={K} (orden SP500 primero)", run(max_lado=K))
        linea(f"max otros={K} (orden US100 primero)", run(max_lado=K, orden=("US100", "US30", "NL25", "RTY", "SP500")))
    print("\n--- 4) MARCO MAYOR: no comprar bajo la EMA (ni vender sobre ella); EMA de N horas ---")
    for Nh in (12, 24, 50, 100, 200):
        linea(f"EMA {Nh}h", run(f_ema=4 * Nh))
