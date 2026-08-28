#!/usr/bin/env python3
"""
Bot ORO TREND-FOLLOWING de DOS LADOS (largo + corto) — 1h — capital.com DEMO.
Reemplaza al bot de cobre (retirado 26-ago). Reusa el repo/infra del cobre.

POR QUE: el resto de los bots son largo-sesgados / reversion y NO ganan cuando el
oro CAE. Este es trend-following puro de DOS LADOS: acompana la tendencia en ambas
direcciones (gana en subidas Y en bajadas) -> cubre el hueco del lineup.

ESTRATEGIA (Donchian breakout de dos lados, velas 1h):
  - LARGO  si el cierre supera el maximo de las ultimas ENT velas.
  - CORTO  si el cierre cae bajo el minimo de las ultimas ENT velas.
  - Stop TRAILING NATIVO de capital.com: distancia = ATR_STOP x ATR (fija al entrar); lo mueve
    capital.com en TIEMPO REAL, cada tick (28-ago: se descubrio que la API acepta trailingStop
    pese a que dealingRules dice NOT_AVAILABLE). El bot ya no ajusta el stop cada corrida.
  - Salida adicional: largo cierra si close < min(EXIT); corto si close > max(EXIT).

Validado (GC=F 1h, 2 anos, Donchian 15/8, stop 4xATR, robusto 3-TERCIOS +231/+592/+1589):
+2389 puntos, ~0.7 trades/dia, 41% acierto. Trend-following = pocas ganadoras grandes
(acierto bajo por diseno, el payoff lo compensa). El edge esta cargado al periodo reciente
de alta volatilidad -> vigilar si la volatilidad del oro baja.

REQUIERE trigger HORARIO (cron-job.org crontab '1 * * * *', 1 min tras el cierre 1h).

Uso: python bot_gold_trend.py [--status] [--dry-run]
"""
import sys
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC     = "GOLD"
SIZE     = 0.5           # Subido de 0.2 a 0.5 el 28-ago (a pedido, opcion moderada elegida
                         # sobre 1.5 que era muy agresiva). Riesgo ~$28/trade (stop 2xATR ~57pts,
                         # ~3% de $1000). Distinto de Bollinger (2.0) y FVG (1.0) para el tracker.
ENT      = 15            # Donchian entrada: max/min de las ultimas 15 velas 1h
EXIT     = 8             # Donchian salida: min/max de las ultimas 8 velas 1h
ATR_LEN  = 14
ATR_STOP = 0.5           # distancia del trailing nativo = 0.5 x ATR (~15 pts con ATR ~28).
                         # Bajado a 0.5 el 28-ago A PEDIDO del usuario (achico el SL a ~15 pts
                         # en la app para bloquear ganancia antes). OJO: mas apretado aun que 1.0
                         # -> el backtest lo da perdedor; override informado del usuario. Se usa
                         # ATR (no un 15 fijo) para que se adapte a la volatilidad. Revertir=4.0.
BAR_MIN  = 60            # velas de 1 hora


def _rma(s, k):
    out = [None] * len(s)
    if len(s) < k:
        return out
    p = sum(s[:k]) / k; out[k-1] = p
    for i in range(k, len(s)):
        p = (p * (k-1) + s[i]) / k; out[i] = p
    return out


def atr_series(h, l, c, k):
    tr = [h[0] - l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    return _rma(tr, k)


def _mid(x):
    return (x["bid"] + x["ask"]) / 2 if isinstance(x, dict) else x


def current_bar_start():
    """Inicio de la vela 1h en curso (UTC, naive) = cierre de la ultima vela cerrada."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=0, second=0, microsecond=0)


def fetch_closed(h):
    r = cc.get(h, f"/api/v1/prices/{EPIC}?resolution=HOUR&max=200")
    if r.status_code != 200:
        sys.exit(f"No se pudo bajar precios ({r.status_code}): {r.text}")
    bar0 = current_bar_start()
    O, H, L, C = [], [], [], []
    for p in r.json().get("prices", []):
        t = (p.get("snapshotTimeUTC") or p.get("snapshotTime") or "").replace("Z", "")
        try:
            bt = datetime.fromisoformat(t)
        except ValueError:
            continue
        if bt >= bar0:              # vela en curso -> fuera
            continue
        O.append(_mid(p["openPrice"])); H.append(_mid(p["highPrice"]))
        L.append(_mid(p["lowPrice"]));  C.append(_mid(p["closePrice"]))
    return O, H, L, C


def evaluate(h):
    O, H, L, C = fetch_closed(h)
    if len(C) < ENT + ATR_LEN + 2:
        sys.exit("Pocas velas para calcular.")
    i = len(C) - 1
    atr = atr_series(H, L, C, ATR_LEN)[i]
    close = C[i]
    hh = max(H[i-ENT:i])           # canal de entrada (excluye la vela de decision)
    ll = min(L[i-ENT:i])
    ex_hh = max(H[i-EXIT:i])        # canal de salida
    ex_ll = min(L[i-EXIT:i])
    return {"close": round(close, 2), "atr": round(atr, 2),
            "hh": round(hh, 2), "ll": round(ll, 2),
            "ex_hh": round(ex_hh, 2), "ex_ll": round(ex_ll, 2),
            "long_break": close > hh, "short_break": close < ll,
            "exit_long": close < ex_ll, "exit_short": close > ex_hh}


def _mysize(v):
    try:
        return abs(float(v) - SIZE) < 1e-9
    except (TypeError, ValueError):
        return False


def get_position(h):
    """Devuelve (dealId, direction, level, stopLevel) de la posicion de ESTE bot, o None."""
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        if p["market"]["epic"] == EPIC and _mysize(p["position"]["size"]):
            pp = p["position"]
            return pp["dealId"], pp.get("direction"), pp.get("level"), pp.get("stopLevel")
    return None


def acted_this_bar(h, bar0):
    """True si ya se ABRIO una posicion de este bot en la vela 1h actual. Evita re-entrar
    varias veces en la misma vela cuando el cron corre seguido (el backtest entra 1 vez por
    ruptura -> este candado lo replica). Aperturas: openPrice None; cierres: con valor."""
    frm = (bar0 - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cc.get(h, f"/api/v1/history/activity?from={frm}")
    if r.status_code != 200:
        return False
    for a in r.json().get("activities", []):
        if a.get("epic") != EPIC or a.get("type") != "POSITION":
            continue
        det = a.get("details") or {}
        if det.get("openPrice") is not None:
            continue
        if not _mysize(det.get("size")):
            continue
        try:
            d = datetime.strptime(a["dateUTC"], "%Y-%m-%dT%H:%M:%S.%f")
        except (KeyError, ValueError):
            continue
        if d >= bar0:
            return True
    return False


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    ev = evaluate(h)
    print(f"[ORO TREND 1h GOLD] close={ev['close']} ATR={ev['atr']} "
          f"canal[{ev['ll']}..{ev['hh']}] salida[{ev['ex_ll']}..{ev['ex_hh']}]")
    pos = get_position(h)

    if pos:
        deal_id, direction, level, cur_stop = pos
        snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
        is_long = (direction == "BUY")
        price = snap.get("bid") if is_long else snap.get("offer")
        print(f"  Posicion ABIERTA ({'largo' if is_long else 'corto'}) "
              f"dealId={deal_id} entrada={level} stop={cur_stop} precio={price}")
        # 1) salida por canal Donchian opuesto
        if (is_long and ev["exit_long"]) or (not is_long and ev["exit_short"]):
            print("  >> SALIDA por canal Donchian opuesto -> cierro posicion.")
            if not (dry or status):
                r = cc.requests.delete(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h, timeout=30)
                print(f"     cierre -> {r.status_code} {r.text}")
            return
        # 2) el trailing lo maneja capital.com NATIVAMENTE (trailingStop en la entrada).
        #    El bot ya NO ajusta el stop cada corrida -> se mueve en tiempo real, cada tick.
        print(f"  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real). stopLevel actual={cur_stop}")
        return

    # sin posicion -> buscar entrada (dos lados)
    if ev["long_break"]:
        side, entry_key = "BUY", "offer"
    elif ev["short_break"]:
        side, entry_key = "SELL", "bid"
    else:
        print("  >> sin ruptura de canal (ni alcista ni bajista) -> no entro."); return
    print(f"  >> RUPTURA {'ALCISTA' if side=='BUY' else 'BAJISTA'} "
          f"(close {ev['close']} {'>' if side=='BUY' else '<'} {ev['hh'] if side=='BUY' else ev['ll']}) "
          f"-> senal {side}")
    if status or dry:
        print("  [status/dry-run] No coloco la orden."); return
    bar0 = current_bar_start()
    if acted_this_bar(h, bar0):
        print(f"  Ya se entro en esta vela 1h ({bar0}Z) -> candado, no re-entro."); return
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    entry = snap.get(entry_key)
    if entry is None:
        print("  Sin precio actual -> no entro."); return
    stop_dist = round(ATR_STOP * ev["atr"], 2)   # distancia del trailing en puntos (ATR_STOP x ATR)
    body = {"epic": EPIC, "direction": side, "size": SIZE,
            "trailingStop": True, "stopDistance": stop_dist}
    r = cc.post(h, "/api/v1/positions", body)
    if r.status_code not in (200, 201):
        # FALLBACK: si el trailing nativo en la entrada falla, entrar con stop FIJO
        # (mejor entrar que quedarse afuera; se veria en el log y se corrige).
        print(f"  Trailing POST fallo ({r.status_code}): {r.text} -> reintento con stop fijo")
        sl = round(entry - stop_dist, 2) if side == "BUY" else round(entry + stop_dist, 2)
        r = cc.post(h, "/api/v1/positions",
                    {"epic": EPIC, "direction": side, "size": SIZE, "stopLevel": sl})
        if r.status_code not in (200, 201):
            print(f"  Orden NO colocada ({r.status_code}): {r.text}"); return
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA: {side} {SIZE} {EPIC} @ {entry} TRAILING nativo dist={stop_dist}pts "
          f"ref={ref} status={conf.get('dealStatus')}")


if __name__ == "__main__":
    main()
