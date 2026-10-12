#!/usr/bin/env python3
"""RE-TEST HONESTO de TODOS los bots (12-oct-2026), pedido tras 6 semanas de perdidas en demo.

Reglas del test (para no repetir los errores anteriores):
  1) Ejecucion FIEL sobre velas de 5 MINUTOS bid/ask reales de capital.com (1000 dias, desde ene-2024): compras al
     ask, ventas al bid; el stop se revisa ANTES de mover el extremo dentro de cada vela (pesimista); gaps al precio
     de apertura. Financiamiento nocturno de largos aproximado (0.02%/noche indices/oro, 0.0616%/dia cripto).
  2) Cada bot opera EXACTAMENTE como en vivo: su senal real (funcion del bot, misma ventana de velas), orden LIMITE al
     cierre valida hasta el cierre de la vela siguiente (bots de reversion 15m) o a MERCADO 1 min tras el cierre
     (1h/4h), trailing nativo desde el llenado, piramides, apriete tras ganancia, salidas por senal, stops/objetivos fijos.
  3) Resultado separado en periodo FUERA DE MUESTRA (datos que NO se miraron para elegir sus parametros) y periodo de
     seleccion. Solo lo fuera de muestra es evidencia honesta.
Uso: python retest.py [bot ...]   (sin argumentos: todos)"""
import json, os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gold-bot"))
import bot_sp500 as sp, bot_us30 as us, bot_us100 as nq, bot_rty as rt, bot_nl25 as nl, bot_us30_rf as rf
import bot_gold_trend as bt, bot_gold_ao as ao, bot_crypto as bc
import bot_gold as bg

FIN_NOCHE = 0.0002          # financiamiento aprox de largos por noche (indices/oro)
FIN_CRIPTO = 0.000616       # por dia, largos cripto

def cargar5(epic):
    d = json.load(open(f"data/capital_{epic}_MINUTE_5_1000d_bidask.json"))
    T = [datetime.fromisoformat(t) for t in d["T"]]
    mid = lambda a, b: [(x + y) / 2 for x, y in zip(d[a], d[b])]
    return {"T": T, "Ob": d["Ob"], "Hb": d["Hb"], "Lb": d["Lb"], "Cb": d["Cb"], "Oa": d["Oa"], "Ha": d["Ha"], "La": d["La"], "Ca": d["Ca"],
            "O": mid("Ob", "Oa"), "H": mid("Hb", "Ha"), "L": mid("Lb", "La"), "C": mid("Cb", "Ca")}

def velas(m, minutos):
    """Velas del marco (medio) desde 5m; 'fin' = momento de cierre; 'j' = indice 5m de la primera vela POSTERIOR al cierre."""
    out = {"O": [], "H": [], "L": [], "C": [], "T": [], "fin": [], "j": []}; key = None
    for i, t in enumerate(m["T"]):
        mm = (t.hour * 60 + t.minute) // minutos * minutos if minutos < 1440 else 0
        k = t.replace(hour=mm // 60, minute=mm % 60)
        if k != key:
            if key is not None: out["j"].append(i)
            key = k
            for f in ("O", "H", "L", "C"): out[f].append(m[f][i])
            out["T"].append(k); out["fin"].append(k + timedelta(minutes=minutos))
        else:
            out["H"][-1] = max(out["H"][-1], m["H"][i]); out["L"][-1] = min(out["L"][-1], m["L"][i]); out["C"][-1] = m["C"][i]
    out["j"].append(len(m["T"]))
    return out

# ------------------------------------------------------------------ senales de cada bot (sus funciones reales)
def sen_reversion(mod, b, W=300):
    O, H, L, C = b["O"], b["H"], b["L"], b["C"]; out = {}
    for k in range(W, len(C)):
        s = mod.signal_last(O[k - W + 1:k + 1], H[k - W + 1:k + 1], L[k - W + 1:k + 1], C[k - W + 1:k + 1])
        if s.get("side") and s.get("atr"): out[k] = {"side": s["side"], "nivel": s["close"], "atr": s["atr"]}
    return out

def sen_at(fn, b, W, **extra):
    O, H, L, C = b["O"], b["H"], b["L"], b["C"]; out = {}
    for k in range(W, len(C)):
        out[k] = fn(O[k - W + 1:k + 1], H[k - W + 1:k + 1], L[k - W + 1:k + 1], C[k - W + 1:k + 1], W - 1, **extra) if extra else \
                 fn(O[k - W + 1:k + 1], H[k - W + 1:k + 1], L[k - W + 1:k + 1], C[k - W + 1:k + 1], W - 1)
    return out

# ------------------------------------------------------------------ motor
class Pos:
    def __init__(s, sg, e, dist, atr_e, t, sl=None, tp=None):
        s.sg, s.e, s.d, s.atr, s.t = sg, e, dist, atr_e, t
        s.ext = e; s.stop = (e - sg * dist) if dist else sl; s.sl, s.tp = sl, tp; s.tight = False
        if sl is not None and dist: s.stop = max(s.stop, sl) if sg == 1 else min(s.stop, sl)

def simular(m, decidir, cripto=False):
    """Bucle principal. `decidir(t_cierre, estado)` se llama en cada cierre de vela del bot y devuelve acciones.
    estado = {'pos': [Pos], 'orden': dict|None}. Se ejecuta en las velas 5m siguientes."""
    Ob, Hb, Lb, Oa, Ha, La, T = m["Ob"], m["Hb"], m["Lb"], m["Oa"], m["Ha"], m["La"], m["T"]; n = len(T)
    est = {"pos": [], "orden": None}; trades = []
    eventos = decidir.eventos            # {j5: [callable]} : en el indice 5m j5 se llama a la decision
    for j in range(n):
        for fn in eventos.get(j, ()):    # decisiones del bot al empezar esta vela 5m (= 1 min tras el cierre)
            for acc in fn(est, j) or ():
                if acc["tipo"] == "salir" and est["pos"]:
                    for p in est["pos"]:
                        px = Ob[j] if p.sg == 1 else Oa[j]; trades.append(_cerrar(p, px, T[j], cripto))
                    est["pos"] = []
                elif acc["tipo"] == "apretar":
                    for p in est["pos"]:
                        p.d = acc["k"] * p.atr; p.tight = True
                        ts = p.ext - p.sg * p.d; p.stop = max(p.stop, ts) if p.sg == 1 else min(p.stop, ts)
                elif acc["tipo"] == "piramide" and est["pos"]:
                    sg = est["pos"][0].sg; e = Oa[j] if sg == 1 else Ob[j]
                    est["pos"].append(Pos(sg, e, acc["dist"], acc["atr"], T[j]))
                elif acc["tipo"] in ("limite", "mercado") and not est["pos"] and est["orden"] is None:
                    est["orden"] = dict(acc, primera=True)
        o = est["orden"]
        if o and not est["pos"]:
            sg = o["sg"]; fill = None
            if o["tipo"] == "mercado": fill = Oa[j] if sg == 1 else Ob[j]
            else:
                if T[j] >= o["valido_hasta"]: est["orden"] = None
                else:
                    op = Oa[j] if sg == 1 else Ob[j]
                    if o["primera"] and ((sg == 1 and op <= o["nivel"]) or (sg == -1 and op >= o["nivel"])): fill = op
                    elif (sg == 1 and La[j] <= o["nivel"]) or (sg == -1 and Hb[j] >= o["nivel"]): fill = o["nivel"]
                    o["primera"] = False
            if fill is not None:
                sl = fill * (1 - sg * o["sl_pct"]) if o.get("sl_pct") else None
                tp = fill * (1 + sg * o["tp_pct"]) if o.get("tp_pct") else None
                est["pos"] = [Pos(sg, fill, o.get("dist"), o.get("atr"), T[j], sl, tp)]; est["orden"] = None
        if est["pos"]:
            quedan = []
            for p in est["pos"]:
                lo, hi, op = (Lb[j], Hb[j], Ob[j]) if p.sg == 1 else (La[j], Ha[j], Oa[j])
                ex = None
                if p.stop is not None and ((p.sg == 1 and lo <= p.stop) or (p.sg == -1 and hi >= p.stop)):
                    ex = (min(op, p.stop) if p.sg == 1 else max(op, p.stop))
                elif p.tp is not None and ((p.sg == 1 and hi >= p.tp) or (p.sg == -1 and lo <= p.tp)):
                    ex = (max(op, p.tp) if p.sg == 1 else min(op, p.tp))
                if ex is not None: trades.append(_cerrar(p, ex, T[j], cripto)); continue
                p.ext = max(p.ext, hi) if p.sg == 1 else min(p.ext, lo)
                if p.d:
                    ts = p.ext - p.sg * p.d; p.stop = max(p.stop, ts) if p.sg == 1 else min(p.stop, ts)
                quedan.append(p)
            est["pos"] = quedan
    return trades

def _cerrar(p, px, t, cripto):
    pts = p.sg * (px - p.e)
    if p.sg == 1:
        if cripto: pts -= p.e * FIN_CRIPTO * (t - p.t).total_seconds() / 86400
        else:
            noches = sum(1 for d in range((t.date() - p.t.date()).days) )
            pts -= p.e * FIN_NOCHE * noches
    return {"t_in": p.t, "t_out": t, "pts": pts, "e": p.e, "sg": p.sg}

# ------------------------------------------------------------------ envoltorios por bot (logica en vivo)
class Decisor:
    def __init__(s): s.eventos = {}
    def en(s, j, fn): s.eventos.setdefault(j, []).append(fn)

def bot_reversion(m, mod, trail, tight=None, W=300, gaps=False, piramide=None):
    """15m: orden LIMITE al cierre de la senal, valida hasta el cierre de la vela siguiente; trailing desde el llenado.
    tight=(M,k) apretar tras ganancia (revisado en cada cierre 15m); piramide=(step,max) para Bollinger oro."""
    b = velas(m, 15); S = sen_reversion(mod, b, W); D = Decisor()
    for k in range(W, len(b["C"])):
        j = b["j"][k]
        if j >= len(m["T"]): break
        if gaps and (m["T"][j] - b["fin"][k]).total_seconds() > 600: continue      # mercado cerrado tras la senal
        s = S.get(k); cierre = b["C"][k]; fin = b["fin"][k]
        def f(est, j, s=s, cierre=cierre, fin=fin):
            acc = []
            if est["pos"]:
                p0 = est["pos"][0]; g = p0.sg * (p0.ext - p0.e)
                if tight and not p0.tight and g >= tight[0] * p0.atr: acc.append({"tipo": "apretar", "k": tight[1]})
                if piramide and len(est["pos"]) < piramide[1]:
                    lvl = est["pos"][-1].e + p0.sg * piramide[0] * p0.atr
                    if (p0.sg == 1 and cierre >= lvl) or (p0.sg == -1 and cierre <= lvl):
                        acc.append({"tipo": "piramide", "dist": trail * p0.atr, "atr": p0.atr})
            elif s:
                acc.append({"tipo": "limite", "sg": 1 if s["side"] == "BUY" else -1, "nivel": s["nivel"],
                            "valido_hasta": fin + timedelta(minutes=15), "dist": trail * s["atr"], "atr": s["atr"]})
            return acc
        D.en(j, f)
    return D

def bot_rf(m, trail=rf.TRAIL_ATR, tight=(rf.TIGHT_AT, rf.TIGHT_K)):
    b = velas(m, 60); W = 200; S = sen_at(rf.signal_at, b, W); D = Decisor()
    for k in range(W, len(b["C"])):
        j = b["j"][k]
        if j >= len(m["T"]): break
        s = S[k]
        def f(est, j, s=s):
            if est["pos"]:
                p0 = est["pos"][0]
                if tight and not p0.tight and p0.sg * (p0.ext - p0.e) >= tight[0] * p0.atr: return [{"tipo": "apretar", "k": tight[1]}]
                return []
            if s["side"] and s["atr"]:
                return [{"tipo": "mercado", "sg": 1 if s["side"] == "BUY" else -1, "dist": trail * s["atr"], "atr": s["atr"]}]
        D.en(j, f)
    return D

def bot_trend(m, stop=bt.ATR_STOP, pyr=(bt.PYR_STEP, bt.PYR_MAX), tight=(bt.TIGHT_AT, bt.TIGHT_K)):
    b = velas(m, 60); W = bt.N_CANDLES; S = sen_at(bt.signal_at, b, W); D = Decisor()
    for k in range(W, len(b["C"])):
        j = b["j"][k]
        if j >= len(m["T"]): break
        s = S[k]; cierre = b["C"][k]
        def f(est, j, s=s, cierre=cierre):
            if est["pos"]:
                p0 = est["pos"][0]
                if (p0.sg == 1 and s["exit_long"]) or (p0.sg == -1 and s["exit_short"]): return [{"tipo": "salir"}]
                acc = []
                if tight and not p0.tight and p0.sg * (p0.ext - p0.e) >= tight[0] * p0.atr: acc.append({"tipo": "apretar", "k": tight[1]})
                if pyr[1] > 1 and len(est["pos"]) < pyr[1]:
                    lvl = p0.e + p0.sg * pyr[0] * p0.atr
                    if (p0.sg == 1 and cierre >= lvl) or (p0.sg == -1 and cierre <= lvl):
                        acc.append({"tipo": "piramide", "dist": (tight[1] if p0.tight else stop) * p0.atr, "atr": p0.atr})
                return acc
            if s["long_break"]: return [{"tipo": "mercado", "sg": 1, "dist": stop * s["atr"], "atr": s["atr"]}]
            if s["short_break"]: return [{"tipo": "mercado", "sg": -1, "dist": stop * s["atr"], "atr": s["atr"]}]
        D.en(j, f)
    return D

def bot_ao(m):
    b = velas(m, 60); W = ao.N_CANDLES; S = sen_at(ao.signal_at, b, W); D = Decisor()
    for k in range(W, len(b["C"])):
        j = b["j"][k]
        if j >= len(m["T"]): break
        s = S[k]
        def f(est, j, s=s):
            if est["pos"]: return [{"tipo": "salir"}] if s["sale"] else []
            if s["entra"]: return [{"tipo": "mercado", "sg": 1, "dist": None, "atr": None, "sl_pct": ao.SL_PCT, "tp_pct": ao.TP_PCT}]
        D.en(j, f)
    return D

def bot_crypto(m):
    b = velas(m, 240); W = bc.N_CANDLES; S = sen_at(bc.signal_at, b, W); D = Decisor()
    for k in range(W, len(b["C"])):
        j = b["j"][k]
        if j >= len(m["T"]): break
        s = S[k]; cierre = b["C"][k]
        def f(est, j, s=s, cierre=cierre):
            if est["pos"]:
                p0 = est["pos"][0]
                if len(est["pos"]) < 2:
                    lvl = p0.e + p0.sg * bc.PYR_STEP * p0.atr
                    if (p0.sg == 1 and cierre >= lvl) or (p0.sg == -1 and cierre <= lvl):
                        return [{"tipo": "piramide", "dist": bc.TRAIL_ATR * p0.atr, "atr": p0.atr}]
                return []
            if s["side"] and s["atr"]:
                return [{"tipo": "mercado", "sg": 1 if s["side"] == "BUY" else -1, "dist": bc.TRAIL_ATR * s["atr"], "atr": s["atr"]}]
        D.en(j, f)
    return D

# bot: (epic, $ por punto con su size, constructor, inicio del periodo usado para ELEGIR sus parametros)
BOTS = {
    "SP500":          ("US500", sp.SIZE,  lambda m: bot_reversion(m, sp, sp.TRAIL_ATR), datetime(2025, 12, 15)),
    "US30 bandas":    ("US30",  us.SIZE,  lambda m: bot_reversion(m, us, us.TRAIL_ATR), datetime(2025, 2, 10)),
    "US100":          ("US100", nq.SIZE,  lambda m: bot_reversion(m, nq, nq.TRAIL_ATR), datetime(2025, 12, 15)),
    "Russell":        ("RTY",   rt.SIZE,  lambda m: bot_reversion(m, rt, rt.TRAIL_ATR, tight=(rt.TIGHT_AT, rt.TIGHT_K)), datetime(2025, 12, 15)),
    "Holanda":        ("NL25",  nl.SIZE * 1.08, lambda m: bot_reversion(m, nl, nl.TRAIL_ATR, gaps=True), datetime(2025, 12, 15)),
    "US30 ruptura f.":("US30",  rf.SIZE,  lambda m: bot_rf(m), datetime(2025, 2, 10)),
    "Bollinger oro":  ("GOLD",  bg.SIZE,  lambda m: bot_reversion(m, bg, bg.TRAIL_ATR, piramide=(bg.PYR_STEP, bg.PYR_MAX)), datetime(2025, 11, 27)),
    "Trend oro":      ("GOLD",  bt.SIZE,  lambda m: bot_trend(m), datetime(2024, 1, 1)),
    "AwesomeMacd oro":("GOLD",  ao.SIZE,  lambda m: bot_ao(m), datetime(2099, 1, 1)),
    "Cripto BTC":     ("BTCUSD", 0.013,   lambda m: bot_crypto(m), datetime(2020, 1, 1)),
    "Cripto ETH":     ("ETHUSD", 0.41,    lambda m: bot_crypto(m), datetime(2020, 1, 1)),
}

def resumen(nombre, tr, usd, corte):
    tr = sorted(tr, key=lambda x: x["t_out"]); fuera = [x for x in tr if x["t_in"] < corte]; dentro = [x for x in tr if x["t_in"] >= corte]
    def st(v):
        if not v: return "      sin ops"
        tot = sum(x["pts"] for x in v) * usd; w = sum(x["pts"] for x in v if x["pts"] > 0); l = -sum(x["pts"] for x in v if x["pts"] <= 0)
        eq = pk = dd = 0
        for x in v: eq += x["pts"] * usd; pk = max(pk, eq); dd = min(dd, eq - pk)
        dias = max(1, (v[-1]["t_out"] - v[0]["t_in"]).days)
        return f"{len(v):>4} ops ${tot:>+8.0f} (${tot / dias * 30.4:>+5.0f}/mes) PF {w / l if l else 9:4.2f} DD ${dd:>6.0f}"
    por = {}
    for x in tr: por[x["t_in"].year] = por.get(x["t_in"].year, 0) + x["pts"] * usd
    print(f"{nombre:<16} FUERA DE MUESTRA: {st(fuera)} | SELECCION: {st(dentro)} | por anio: "
          + " ".join(f"{y}:${v:+.0f}" for y, v in sorted(por.items())), flush=True)
    return tr

if __name__ == "__main__":
    quien = sys.argv[1:] or list(BOTS)
    cache = {}
    for nombre in quien:
        epic, usd, ctor, corte = BOTS[nombre]
        if epic not in cache: cache[epic] = cargar5(epic)
        m = cache[epic]; tr = simular(m, ctor(m), cripto=epic in ("BTCUSD", "ETHUSD"))
        json.dump([{**x, "t_in": str(x["t_in"]), "t_out": str(x["t_out"])} for x in tr], open(f"data/retest_{nombre.replace(' ', '_')}.json", "w"))
        resumen(nombre, tr, usd, corte)
