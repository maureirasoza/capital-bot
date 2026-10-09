#!/usr/bin/env python3
"""MODO SOMBRA LOCAL (9-oct-2026): la misma prueba que sombra_ia.py, pero sin API de Anthropic.

Una tarea programada de la app Claude (Mac) corre cada 15 min:
  1) `python sombra_local.py pendientes`  -> JSON con las entradas NUEVAS de los bots (aun no evaluadas), cada una
     con la logica del bot y las ultimas 24 velas HASTA la vela de la senal (nada posterior a la entrada).
  2) Claude busca el contexto/noticias de ese momento y decide ENTRAR / NO_ENTRAR.
  3) `python sombra_local.py registrar '<json>'` -> agrega el veredicto a data/sombra_local.jsonl.
Solo registra: no abre, cierra ni modifica operaciones. sombra_eval.py lo cruza con el P&L real.
Solo evalua entradas BASE (no unidades de piramide) abiertas despues de 'desde' (inicio de la prueba)."""
import sys, os, json, time
from datetime import datetime, timedelta, timezone
import capital_client as cc
from sombra_ia import BOTS as LOGICA

DIR = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(DIR, "data", "sombra_local.jsonl")
EST = os.path.join(DIR, "data", "sombra_local_estado.json")
# (epic, size) de la unidad BASE -> bot
BOT_DE = {("US500", 1.0): "sp500", ("US30", 0.1): "us30", ("US30", 0.12): "us30rf", ("US100", 0.1): "us100",
          ("RTY", 1.0): "rty", ("NL25", 5.0): "nl25", ("GOLD", 0.8): "bollinger_oro", ("GOLD", 0.33): "ao_oro", ("GOLD", 0.5): "trend",
          ("BTCUSD", 0.013): "crypto", ("ETHUSD", 0.41): "crypto"}
BAR_MIN = {"MINUTE_15": 15, "HOUR": 60, "HOUR_4": 240}


def estado():
    if os.path.exists(EST):
        return json.load(open(EST))
    e = {"desde": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(os.path.dirname(EST), exist_ok=True)
    json.dump(e, open(EST, "w"))
    return e


def evaluados():
    if not os.path.exists(REG):
        return set()
    return {json.loads(l).get("dealId") for l in open(REG) if l.strip()}


def velas_hasta(h, epic, res, t_entrada, n=24):
    m = BAR_MIN[res]
    t = t_entrada.replace(second=0, microsecond=0)
    t = t - timedelta(minutes=(t.hour * 60 + t.minute) % m)          # inicio de la vela en que se entro
    frm = t - timedelta(minutes=m * n * 4)
    r = cc.get(h, f"/api/v1/prices/{epic}?resolution={res}&from={frm:%Y-%m-%dT%H:%M:%S}&to={t:%Y-%m-%dT%H:%M:%S}&max=1000")
    mid = lambda x: round((x["bid"] + x["ask"]) / 2, 2)
    out = [f"{p['snapshotTimeUTC']} O{mid(p['openPrice'])} H{mid(p['highPrice'])} L{mid(p['lowPrice'])} C{mid(p['closePrice'])}"
           for p in r.json().get("prices", []) if p["snapshotTimeUTC"].replace("Z", "") < t.strftime("%Y-%m-%dT%H:%M:%S")]
    return out[-n:]


def sentimiento(h, epic):
    """% de clientes de capital.com comprados/vendidos en ese mercado (valor ACTUAL, minutos despues de la entrada;
    la API no da historico). Suele leerse al reves: si la gran mayoria esta comprada, el mercado tiende a bajar."""
    try:
        d = cc.get(h, f"/api/v1/clientsentiment/{epic}").json()
        return {"comprados_pct": d.get("longPositionPercentage"), "vendidos_pct": d.get("shortPositionPercentage")}
    except Exception:
        return None


def pendientes():
    e = estado(); desde = datetime.fromisoformat(e["desde"]); ya = evaluados()
    h = cc.login(); now = datetime.now(timezone.utc).replace(tzinfo=None)
    acts = []
    for d in range(2):
        a0 = now - timedelta(days=d + 1); a1 = now - timedelta(days=d)
        r = cc.get(h, f"/api/v1/history/activity?from={a0:%Y-%m-%dT%H:%M:%S}&to={a1:%Y-%m-%dT%H:%M:%S}&detailed=true")
        acts += r.json().get("activities", []) if r.status_code == 200 else []
        time.sleep(0.1)
    out = []
    for a in acts:
        det = a.get("details") or {}
        if a.get("type") != "POSITION" or det.get("size") is None or det.get("openPrice") is not None:
            continue
        key = (a.get("epic"), round(float(det["size"]), 4)); bot = BOT_DE.get(key)
        t = datetime.strptime(a["dateUTC"][:19], "%Y-%m-%dT%H:%M:%S")
        if not bot or t < desde or a["dealId"] in ya or a["dealId"] in {o["dealId"] for o in out}:
            continue
        _, res, logica = LOGICA[bot]
        out.append({"dealId": a["dealId"], "bot": bot, "epic": key[0], "size": key[1], "side": det.get("direction"),
                    "precio": float(det["level"]), "t_entrada_utc": t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "minutos_desde_entrada": round((now - t).total_seconds() / 60), "logica_bot": logica,
                    "velas_previas": velas_hasta(h, key[0], res, t), "resolucion": res,
                    "sentimiento_clientes_capital": sentimiento(h, key[0])})
    print(json.dumps(sorted(out, key=lambda x: x["t_entrada_utc"]), ensure_ascii=False, indent=1))


def registrar(js):
    d = json.loads(js)
    falta = [k for k in ("dealId", "veredicto", "confianza", "motivo") if k not in d]
    if falta or d["veredicto"] not in ("ENTRAR", "NO_ENTRAR"):
        sys.exit(f"registro invalido (faltan {falta} o veredicto distinto de ENTRAR/NO_ENTRAR)")
    d["t_veredicto_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    d["fuente"] = "sesion_local"
    with open(REG, "a") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print("registrado", d["dealId"], d["veredicto"])


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "pendientes":
        pendientes()
    elif len(sys.argv) >= 3 and sys.argv[1] == "registrar":
        registrar(sys.argv[2])
    else:
        sys.exit("uso: python sombra_local.py pendientes | registrar '<json>'")
