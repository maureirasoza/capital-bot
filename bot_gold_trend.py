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

MEJORAS 2-oct-2026 (validadas en GOLD 1h 1000d REALES de capital.com, con 2024 FUERA DE MUESTRA;
scripts trend_filtros_oos.py / trend_mejora2.py / trend_piramide.py):
  1) FILTRO DE TENDENCIA: solo rupturas a favor de la EMA200 de 1h (largo si close > EMA, corto si
     close < EMA). PF sube en ambos tramos con 6 de 7 largos de EMA probados (50-400).
  2) PIRAMIDE: con la operacion ya ganando PYR_STEP x ATR(entrada), se agrega UNA segunda unidad
     (tamano SIZE_PYR) con el mismo trailing. Se evalua al CIERRE de cada vela 1h (cron horario).
     Nunca se agrega a una perdedora. Las dos unidades salen juntas por canal o cada una por su stop.
  1000d: actual +2490 PF1.36 DD-460 -> filtro +2714 PF1.54 DD-506 -> filtro+piramide +4335 PF1.66
  DD-651 (2024 no visto: +409/1.32 -> +441/1.41 -> +676/1.49). OJO: la piramide gana mas sobre todo
  porque EXPONE mas (~80% del neto de duplicar tamano con 64% de su DD); peor trade -168 pts vs -88.
  Descartado con datos: entrar en el retroceso, ADX, horario, salida por tiempo, canal 80/5.

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
ATR_STOP = 5.0           # distancia del trailing nativo = 5.0 x ATR. Elegido 18-sep tras el
                         # BACKTEST REAL (backtest_real.py --sweep, mismo codigo del bot sobre
                         # GC=F 1h): el 0.5x que corria antes daba ROB1 debil (+598 pts, PF 1.13,
                         # los 2 primeros tercios en perdida). El barrido mostro una MESETA robusta
                         # de 4x a 10x (todo ROB3, ~+2600/+2800 pts, PF ~1.5); 5x es el pico
                         # (+2812 pts, PF 1.50, maxDD -324). Trend-following NECESITA stop ancho.
                         # Se usa ATR (no pts fijos) para adaptarse a la volatilidad.
BAR_MIN  = 60            # velas de 1 hora
EMA_TREND = 200          # filtro de tendencia: EMA de 200 velas 1h (0 = sin filtro). Meseta 150-250.
N_CANDLES = 600          # velas que baja el bot (y ventana del backtest): la EMA200 necesita historia
PYR_STEP = 2.0           # piramide: agregar cuando el cierre 1h supera entrada + PYR_STEP x ATR(entrada)
PYR_MAX  = 2             # unidades maximas por operacion (1 = sin piramide). El codigo soporta 1 o 2.
SIZE_PYR = round(SIZE + 0.01, 2)   # la unidad piramidada usa un tamano 0.01 mayor SOLO para poder
                         # distinguirla sin guardar estado: si la base ya salio por su stop y queda
                         # la piramidada sola, el bot NO vuelve a piramidar. El tracker las suma igual.


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


def ema_last(s, k):
    """EMA de periodo k al final de la serie (semilla = primer valor). Con N_CANDLES=600 la
    semilla pesa <2% en una EMA200 -> estable, y el backtest usa exactamente la misma ventana."""
    a = 2 / (k + 1); e = s[0]
    for x in s[1:]:
        e = x * a + e * (1 - a)
    return e


def _mid(x):
    return (x["bid"] + x["ask"]) / 2 if isinstance(x, dict) else x


def current_bar_start():
    """Inicio de la vela 1h en curso (UTC, naive) = cierre de la ultima vela cerrada."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=0, second=0, microsecond=0)


def fetch_closed(h):
    r = cc.get(h, f"/api/v1/prices/{EPIC}?resolution=HOUR&max={N_CANDLES}")
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


def signal_at(O, H, L, C, i):
    """Senal Donchian en la vela de indice i. PURA (sin red): misma logica que usa el
    bot en vivo. El backtester importa ESTA funcion -> el test es identico al bot real."""
    atr = atr_series(H, L, C, ATR_LEN)[i]
    close = C[i]
    hh = max(H[i-ENT:i])           # canal de entrada (excluye la vela de decision)
    ll = min(L[i-ENT:i])
    ex_hh = max(H[i-EXIT:i])        # canal de salida
    ex_ll = min(L[i-EXIT:i])
    raw_long, raw_short = close > hh, close < ll
    ema = ema_last(C[:i+1], EMA_TREND) if EMA_TREND else None
    # filtro de tendencia: la ruptura solo vale si va A FAVOR de la EMA
    ok_long = raw_long and (ema is None or close > ema)
    ok_short = raw_short and (ema is None or close < ema)
    return {"close": round(close, 2), "atr": round(atr, 2),
            "hh": round(hh, 2), "ll": round(ll, 2),
            "ex_hh": round(ex_hh, 2), "ex_ll": round(ex_ll, 2),
            "ema": round(ema, 2) if ema is not None else None,
            "raw_long": raw_long, "raw_short": raw_short,
            "long_break": ok_long, "short_break": ok_short,
            "exit_long": close < ex_ll, "exit_short": close > ex_hh}


def evaluate(h):
    O, H, L, C = fetch_closed(h)
    if len(C) < max(ENT + ATR_LEN + 2, 2 * EMA_TREND):
        sys.exit("Pocas velas para calcular.")
    return signal_at(O, H, L, C, len(C) - 1)


def _is(v, size):
    try:
        return abs(float(v) - size) < 1e-9
    except (TypeError, ValueError):
        return False


def _mysize(v):
    """True si el tamano es de ESTE bot: unidad base (SIZE) o unidad piramidada (SIZE_PYR)."""
    return _is(v, SIZE) or _is(v, SIZE_PYR)


def get_positions(h):
    """Posiciones de ESTE bot: lista de dicts {dealId, direction, level, stop, dist, base}.
    'dist' = distancia del trailing nativo (trailingStopDistance) = ATR_STOP x ATR de la entrada."""
    out = []
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        pp = p["position"]
        if p["market"]["epic"] == EPIC and _mysize(pp["size"]):
            out.append({"dealId": pp["dealId"], "direction": pp.get("direction"),
                        "level": pp.get("level"), "stop": pp.get("stopLevel"),
                        "dist": pp.get("trailingStopDistance"), "base": _is(pp["size"], SIZE)})
    return out


def cancel_working_orders(h):
    """Borra ordenes limite pendientes de este bot (al salir por canal no debe quedar una piramide viva)."""
    r = cc.get(h, "/api/v1/workingorders")
    if r.status_code != 200:
        return
    for w in r.json().get("workingOrders", []):
        d = w.get("workingOrderData", {})
        if d.get("epic") == EPIC and _mysize(d.get("orderSize")):
            x = cc.requests.delete(f"{cc.BASE}/api/v1/workingorders/{d.get('dealId')}", headers=h, timeout=30)
            print(f"     orden pendiente {d.get('dealId')} borrada -> {x.status_code}")


def place_order(h, side, size, level, stop_dist, bar0, etiqueta):
    """Entrada por LIMITE al cierre de la senal (o a MERCADO si el precio ya es igual o mejor),
    con trailing nativo. Devuelve True si quedo colocada. Usada por la entrada y por la piramide."""
    es_buy = (side == "BUY")
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    entry = snap.get("offer" if es_buy else "bid")
    if entry is None:
        print("  Sin precio actual -> no entro."); return False
    if not ((es_buy and entry <= level) or ((not es_buy) and entry >= level)):
        expiry = (bar0 + timedelta(minutes=BAR_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        rl = cc.post(h, "/api/v1/workingorders",
                     {"epic": EPIC, "direction": side, "size": size, "level": level,
                      "type": "LIMIT", "trailingStop": True, "stopDistance": stop_dist,
                      "goodTillDate": expiry})
        if rl.status_code in (200, 201):
            ref = rl.json().get("dealReference")
            conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
            print(f"  ORDEN LIMITE ({etiqueta}): {side} {size} {EPIC} @ {level} (mercado {entry}) "
                  f"TRAILING {stop_dist}pts vence {expiry} ref={ref} status={conf.get('dealStatus')}")
            return True
        print(f"  Orden limite fallo ({rl.status_code}): {rl.text[:120]} -> entro a MERCADO")
    r = cc.post(h, "/api/v1/positions", {"epic": EPIC, "direction": side, "size": size,
                                         "trailingStop": True, "stopDistance": stop_dist})
    if r.status_code not in (200, 201):
        # FALLBACK: si el trailing nativo en la entrada falla, entrar con stop FIJO
        print(f"  Trailing POST fallo ({r.status_code}): {r.text} -> reintento con stop fijo")
        sl = round(entry - stop_dist, 2) if es_buy else round(entry + stop_dist, 2)
        r = cc.post(h, "/api/v1/positions",
                    {"epic": EPIC, "direction": side, "size": size, "stopLevel": sl})
        if r.status_code not in (200, 201):
            print(f"  Orden NO colocada ({r.status_code}): {r.text}"); return False
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA ({etiqueta}): {side} {size} {EPIC} @ {entry} TRAILING nativo "
          f"dist={stop_dist}pts ref={ref} status={conf.get('dealStatus')}")
    return True


def has_working_order(h):
    """True si ya hay una orden LIMITE pendiente de este bot (evita duplicarla). El candado
    acted_this_bar solo mira POSITION, asi que una orden pendiente necesita su propia guarda."""
    r = cc.get(h, "/api/v1/workingorders")
    if r.status_code != 200:
        return False
    for w in r.json().get("workingOrders", []):
        d = w.get("workingOrderData", {})
        if d.get("epic") == EPIC and _mysize(d.get("orderSize")):
            return True
    return False


def acted_this_bar(h, bar0):
    """True si ya se ABRIO una posicion de este bot en la vela 1h actual. Evita re-entrar
    varias veces en la misma vela cuando el cron corre seguido (el backtest entra 1 vez por
    ruptura -> este candado lo replica). Aperturas: openPrice None; cierres: con valor."""
    frm = (bar0 - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    # OJO: detailed=true es OBLIGATORIO -> sin el, la API no manda 'details' (size/openPrice)
    # y el candado no puede filtrar por tamano -> quedaba ciego y nunca bloqueaba (bug 01-sep).
    r = cc.get(h, f"/api/v1/history/activity?from={frm}&detailed=true")
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
    print(f"[ORO TREND 1h GOLD] close={ev['close']} ATR={ev['atr']} EMA{EMA_TREND}={ev['ema']} "
          f"canal[{ev['ll']}..{ev['hh']}] salida[{ev['ex_ll']}..{ev['ex_hh']}]")
    poss = get_positions(h)
    bar0 = current_bar_start()

    if poss:
        is_long = (poss[0]["direction"] == "BUY")
        for p in poss:
            print(f"  Posicion ABIERTA ({'largo' if is_long else 'corto'}, {'base' if p['base'] else 'PIRAMIDE'}) "
                  f"dealId={p['dealId']} entrada={p['level']} stop={p['stop']} trailing={p['dist']}pts")
        # 1) salida por canal Donchian opuesto -> salen TODAS las unidades juntas
        if (is_long and ev["exit_long"]) or (not is_long and ev["exit_short"]):
            print("  >> SALIDA por canal Donchian opuesto -> cierro todas las unidades.")
            if not (dry or status):
                for p in poss:
                    r = cc.requests.delete(f"{cc.BASE}/api/v1/positions/{p['dealId']}", headers=h, timeout=30)
                    print(f"     cierre {p['dealId']} -> {r.status_code} {r.text}")
                cancel_working_orders(h)
            return
        # 2) PIRAMIDE: solo si esta la unidad base sola. Nivel = entrada base +/- PYR_STEP x ATR(entrada),
        #    con ATR(entrada) = distancia del trailing / ATR_STOP. Se decide con el CIERRE 1h (como el backtest).
        base = [p for p in poss if p["base"]]
        if PYR_MAX >= 2 and len(poss) == 1 and base and base[0]["dist"]:
            b = base[0]
            atr_e = float(b["dist"]) / ATR_STOP
            lvl = round(b["level"] + (1 if is_long else -1) * PYR_STEP * atr_e, 2)
            hit = (ev["close"] >= lvl) if is_long else (ev["close"] <= lvl)
            print(f"  Piramide: nivel {lvl} (entrada {b['level']} {'+' if is_long else '-'} {PYR_STEP}x{atr_e:.2f}) "
                  f"cierre {ev['close']} -> {'ALCANZADO' if hit else 'aun no'}")
            if hit:
                if status or dry:
                    print("  [status/dry-run] No agrego la unidad."); return
                if acted_this_bar(h, bar0):
                    print(f"  Ya se abrio una posicion en esta vela 1h ({bar0}Z) -> candado."); return
                if has_working_order(h):
                    print("  Ya hay orden limite pendiente -> no coloco otra."); return
                place_order(h, b["direction"], SIZE_PYR, ev["close"], round(float(b["dist"]), 2), bar0, "PIRAMIDE")
                return
        elif len(poss) == 1 and not base:
            print("  Queda solo la unidad piramidada (la base ya salio) -> no vuelvo a piramidar.")
        # 3) el trailing lo maneja capital.com NATIVAMENTE (trailingStop en la entrada).
        print("  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real).")
        return

    # sin posicion -> buscar entrada (dos lados, a favor de la EMA)
    if ev["long_break"]:
        side = "BUY"
    elif ev["short_break"]:
        side = "SELL"
    else:
        if ev["raw_long"] or ev["raw_short"]:
            print(f"  >> ruptura {'alcista' if ev['raw_long'] else 'bajista'} CONTRA la tendencia "
                  f"(close {ev['close']} vs EMA{EMA_TREND} {ev['ema']}) -> filtrada, no entro.")
        else:
            print("  >> sin ruptura de canal (ni alcista ni bajista) -> no entro.")
        return
    print(f"  >> RUPTURA {'ALCISTA' if side=='BUY' else 'BAJISTA'} a favor de la EMA{EMA_TREND} "
          f"(close {ev['close']} {'>' if side=='BUY' else '<'} {ev['hh'] if side=='BUY' else ev['ll']}) "
          f"-> senal {side}")
    if status or dry:
        print("  [status/dry-run] No coloco la orden."); return
    if acted_this_bar(h, bar0):
        print(f"  Ya se entro en esta vela 1h ({bar0}Z) -> candado, no re-entro."); return
    if has_working_order(h):
        print("  Ya hay orden limite pendiente -> no coloco otra."); return
    stop_dist = round(ATR_STOP * ev["atr"], 2)   # distancia del trailing en puntos (ATR_STOP x ATR)
    # ENTRADA POR LIMITE AL CIERRE DE LA SENAL (21-sep-2026): entrar a MERCADO ~1 min tras el cierre
    # cuesta +0.4 a +1.1 pts de desliz que el backtest no modelaba (limite_vs_mercado.py).
    place_order(h, side, SIZE, ev["close"], stop_dist, bar0, "ENTRADA")


if __name__ == "__main__":
    main()
