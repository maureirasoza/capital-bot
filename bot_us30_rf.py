#!/usr/bin/env python3
"""
Bot US30 RUPTURA FALLIDA (Dow Jones, epic US30) — reversion tras ruptura fracasada — velas 1h — DEMO.

POR QUE (3-oct-2026): idea sacada de una entrevista ("el Nasdaq llego a un techo importante, no lo
cruzo, vienen correcciones") y convertida en regla verificable. Screening 1h/600d en 5 indices
(capital-demo/ruptura_fallida.py): US30 fue el unico con senal clara (21% de variantes positivas en
ambas mitades). VALIDADO CON EJECUCION FIEL 1m bid/ask (ruptura_fallida_fiel.py, rf_nativo.py,
datos capital_US30_MINUTE_600d_bidask.json): version ejecutable (senal pura + trailing nativo desde
la entrada) N48 M2 trail3: mitad1 +4231 PF1.69 DD-1385 | mitad2 +4046 PF1.55 DD-2317, 1.5 tr/sem,
acc 47%. Meseta: trail 2.0-3.0 y N 48-96 positivos en ambas mitades; M3+ y trail 4+ se degradan.
Correlacion semanal con el bot US30 actual (bandas+RSI 15m): +0.19 -> conviven como bots distintos.

ESTRATEGIA (velas de 1 hora):
  - RUPTURA: una vela cierra por encima del maximo de las ultimas ENT velas (o bajo el minimo).
  - FALLO: dentro de las CONF velas siguientes, una vela cierra de vuelta DENTRO (bajo ese maximo /
    sobre ese minimo). Esa vela es la senal: VENTA tras ruptura alcista fallida, COMPRA tras bajista.
    Mientras hay una ruptura pendiente, otra ruptura no la reemplaza (igual que la validacion).
  - ENTRADA A MERCADO 1 min tras el cierre de la vela de confirmacion (asi se simulo).
  - SALIDA UNICA: trailing nativo = TRAIL_ATR x ATR(14) desde la entrada. SIN TP.
  - Una posicion a la vez; candado max 1 orden por vela 1h.
Riesgo (US30 $1/pt/unidad, margen real 1%, precio ~51.000, ATR1h ~55): size 0.12 -> trailing ~165 pts
  = ~$20/trade, maxDD ~$280 (mitad peor), margen ~$62, ~+$12/sem esperado en backtest fiel.
SIZE 0.12 (no 0.1) para que tracker y candados lo distingan del bot US30 de bandas (size 0.1).
REQUIERE trigger HORARIO (cron-job.org crontab '1 * * * *', 1 min tras el cierre 1h).
Uso: python bot_us30_rf.py [--status] [--dry-run]
"""
import sys
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC      = "US30"
SIZE      = 0.12           # unico en US30 (el bot de bandas usa 0.1) -> identifica a este bot
ENT       = 48             # ruptura: max/min de las ultimas 48 velas 1h
CONF      = 2              # velas (inclusive) para que la ruptura "falle" (cierre de vuelta adentro)
ATR_LEN   = 14
TRAIL_ATR = 3.0            # trailing nativo = 3.0 x ATR desde la entrada (meseta fiel 2.0-3.0)
BAR_MIN   = 60
RESOLUTION = "HOUR"
TIGHT_AT  = 3.5            # 8-oct-2026: cuando la ganancia maxima llega a TIGHT_AT x ATR(entrada), el trailing
TIGHT_K   = 1.75           # pasa de 3.0 a TIGHT_K x ATR. FIEL 1m bid/ask 600d (rf_prog_fiel.py/2): +8277 -> +12235
                           # (+48%) PF 1.61->1.80, ambas mitades; meseta +3-4 x 1.25-2.0. 1.75 y no 1.5 (+12435): mismo
                           # neto y ningun sexto negativo (el 5o sexto: actual +1415, 1.5x -223, 1.75x +35 -> costo real).
TIGHT_LOOKBACK_D = 30      # dias de velas para recalcular el ATR de la vela de senal
N_CANDLES = 200            # velas que baja el bot = ventana del backtest (WIN)


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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=0, second=0, microsecond=0)


def fetch_closed(h):
    """OHLC (mid) SOLO de velas 1h ya cerradas, en orden."""
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
        if bt >= bar0:
            continue
        O.append(_mid(p["openPrice"])); H.append(_mid(p["highPrice"]))
        L.append(_mid(p["lowPrice"]));  C.append(_mid(p["closePrice"]))
    return O, H, L, C


def signal_at(O, H, L, C, i):
    """Senal de RUPTURA FALLIDA en la vela i. PURA (sin red): maquina de estados sobre la ventana,
    identica a la validacion (rf_nativo.py). Devuelve dict con side ('BUY'/'SELL'/None), nivel roto,
    atr y close. El backtester importa ESTA funcion."""
    atr = atr_series(H, L, C, ATR_LEN)[i]
    pend = None; side = None; lvl = None
    for t in range(ENT + 1, i + 1):
        hh = max(H[t-ENT:t]); ll = min(L[t-ENT:t])
        if pend:
            if t > pend[1] + CONF:
                pend = None
            elif pend[0] == "up" and C[t] < pend[2]:
                if t == i: side, lvl = "SELL", pend[2]
                pend = None; continue
            elif pend[0] == "down" and C[t] > pend[2]:
                if t == i: side, lvl = "BUY", pend[2]
                pend = None; continue
            else:
                continue
        if C[t] > hh: pend = ("up", t, hh)
        elif C[t] < ll: pend = ("down", t, ll)
    return {"side": side, "level": round(lvl, 1) if lvl else None, "atr": round(atr, 1) if atr else None,
            "close": round(C[i], 1), "pend": pend[0] if pend else None}


def signal_last(o, hi, lo, c):
    """Interfaz tipo Bollinger (side/atr/close en la ULTIMA vela) para backtest_real.simulate_bollinger."""
    return signal_at(o, hi, lo, c, len(c) - 1)


def evaluate(h):
    O, H, L, C = fetch_closed(h)
    if len(C) < ENT + ATR_LEN + 2:
        sys.exit("Pocas velas para calcular.")
    return signal_at(O, H, L, C, len(C) - 1)


def _mysize(v):
    try:
        return abs(float(v) - SIZE) < 1e-9
    except (TypeError, ValueError):
        return False


def get_position(h):
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        pp = p["position"]
        if p["market"]["epic"] == EPIC and _mysize(pp["size"]):
            return pp["dealId"], pp.get("direction"), pp.get("level"), pp.get("stopLevel"), bool(pp.get("trailingStop")), pp.get("trailingStopDistance"), pp.get("createdDateUTC")
    return None


def acted_this_bar(h, bar0):
    """Candado: True si ya se ABRIO una posicion de este bot en la vela 1h actual."""
    frm = (bar0 - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cc.get(h, f"/api/v1/history/activity?from={frm}&detailed=true")
    if r.status_code != 200:
        return False
    for a in r.json().get("activities", []):
        if a.get("epic") != EPIC or a.get("type") != "POSITION":
            continue
        det = a.get("details") or {}
        if det.get("openPrice") is not None or not _mysize(det.get("size")):
            continue
        try:
            d = datetime.strptime(a["dateUTC"], "%Y-%m-%dT%H:%M:%S.%f")
        except (KeyError, ValueError):
            continue
        if d >= bar0:
            return True
    return False


def atr_vela_senal(h, created_utc):
    """ATR de la vela de senal de la posicion (la vela anterior a su apertura), recalculado desde las velas
    cerradas hasta ella. Solo sirve para saber si el trailing ya se apreto (los dos estados difieren x2)."""
    try:
        t_open = datetime.fromisoformat(str(created_utc)[:19])
    except ValueError:
        return None
    m = t_open.hour * 60 + t_open.minute
    sigbar = t_open.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=(m // BAR_MIN - 1) * BAR_MIN)
    frm = (sigbar - timedelta(days=TIGHT_LOOKBACK_D)).strftime("%Y-%m-%dT%H:%M:%S")
    to = (sigbar + timedelta(minutes=BAR_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cc.get(h, f"/api/v1/prices/{EPIC}?resolution={RESOLUTION}&from={frm}&to={to}&max=1000")
    if r.status_code != 200:
        return None
    H, L, C, TT = [], [], [], []
    for p in r.json().get("prices", []):
        t = (p.get("snapshotTimeUTC") or p.get("snapshotTime") or "").replace("Z", "")
        try:
            bt = datetime.fromisoformat(t)
        except ValueError:
            continue
        TT.append(bt); H.append(_mid(p["highPrice"])); L.append(_mid(p["lowPrice"])); C.append(_mid(p["closePrice"]))
    if sigbar not in TT:
        return None
    return atr_series(H, L, C, ATR_LEN)[TT.index(sigbar)]


def tighten_if_big_gain(h, deal_id, direction, level, cur_stop, dist, created, dry):
    """APRETAR TRAS GANANCIA (8-oct-2026): si la ganancia maxima >= TIGHT_AT x ATR(entrada), el trailing nativo
    pasa de TRAIL_ATR a TIGHT_K x ATR(entrada) (PUT /positions: capital.com lo re-ancla desde el mejor precio).
    Sin estado: distancia original = TRAIL_ATR x ATR(entrada); extremo = stopLevel +/- distancia;
    'ya apretado' si la distancia es claramente menor que TRAIL_ATR x ATR(vela de senal)."""
    if not dist or cur_stop is None or level is None:
        return
    dist = float(dist)
    atr_c = atr_vela_senal(h, created)
    if not atr_c:
        print("  Apretar tras ganancia: no encuentro la vela de senal -> no evaluo."); return
    if dist < 0.75 * TRAIL_ATR * atr_c:
        print(f"  Trailing ya apretado ({dist:.1f} = {dist/atr_c:.1f}xATR)."); return
    atr_e = dist / TRAIL_ATR
    sg = 1 if direction == "BUY" else -1
    mfe = sg * ((float(cur_stop) + sg * dist) - float(level))
    print(f"  Ganancia maxima: {mfe:+.1f} pts = {mfe/atr_e:+.1f}xATR (aprieta al llegar a +{TIGHT_AT}xATR)")
    if mfe < TIGHT_AT * atr_e:
        return
    nueva = round(TIGHT_K * atr_e, 1)
    if dry:
        print(f"  [dry] apretaria el trailing {dist} -> {nueva} ({TIGHT_K}xATR)"); return
    r = cc.requests.put(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h,
                        json={"trailingStop": True, "stopDistance": nueva}, timeout=30)
    print(f"  >> GANANCIA GRANDE: trailing {dist} -> {nueva} ({TIGHT_K}xATR) -> {r.status_code} {r.text[:80]}")


def manual_trail(h, deal_id, direction, cur_stop, atr, dry):
    """FALLBACK si el trailing nativo no esta activo: mueve el stop a precio -/+ TRAIL_ATR x ATR."""
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    is_long = (direction == "BUY")
    price = snap.get("bid") if is_long else snap.get("offer")
    if price is None or not atr:
        print("  Sin precio/ATR -> no ajusto stop."); return
    dist = TRAIL_ATR * atr
    new_stop = round(price - dist, 1) if is_long else round(price + dist, 1)
    mejora = (cur_stop is None) or (is_long and new_stop > cur_stop + 0.1) or ((not is_long) and new_stop < cur_stop - 0.1)
    if not mejora:
        print(f"  Trailing MANUAL: stop {cur_stop} se mantiene (precio {price})."); return
    print(f"  Trailing MANUAL: stop {cur_stop} -> {new_stop} (precio {price}, dist {dist:.1f})")
    if dry:
        return
    r = cc.requests.put(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h, json={"stopLevel": new_stop}, timeout=30)
    print(f"     ajuste -> {r.status_code} {r.text[:120]}")


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    ev = evaluate(h)
    print(f"[US30 RUPTURA FALLIDA 1h] close={ev['close']} ATR={ev['atr']} "
          f"ruptura pendiente={ev['pend'] or 'ninguna'} senal={ev['side'] or 'ninguna'}")
    pos = get_position(h)
    if pos:
        deal_id, direction, level, cur_stop, nativo, dist, created = pos
        print(f"  Posicion ABIERTA {direction} dealId={deal_id} entrada={level} stop={cur_stop} trailing_nativo={nativo}")
        if nativo:
            print(f"  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real), distancia {dist}.")
            tighten_if_big_gain(h, deal_id, direction, level, cur_stop, dist, created, dry or status)
        else:
            manual_trail(h, deal_id, direction, cur_stop, ev["atr"], dry or status)
        return
    if not ev["side"]:
        print("  >> sin ruptura fallida en la ultima vela cerrada -> no entro."); return
    print(f"  >> RUPTURA FALLIDA: cierre {ev['close']} volvio {'bajo' if ev['side']=='SELL' else 'sobre'} el nivel {ev['level']} "
          f"-> senal {ev['side']} (salida: trailing {TRAIL_ATR}xATR sin TP)")
    if status or dry:
        print("  [status/dry-run] No coloco la orden."); return
    bar0 = current_bar_start()
    if acted_this_bar(h, bar0):
        print(f"  Ya se entro en esta vela 1h ({bar0}Z) -> candado."); return
    if not ev["atr"]:
        print("  Sin ATR -> no entro."); return
    trail_pts = round(TRAIL_ATR * ev["atr"], 1)
    # ENTRADA A MERCADO (asi se valido: ask/bid del minuto :01 tras el cierre de confirmacion).
    r = cc.post(h, "/api/v1/positions", {"epic": EPIC, "direction": ev["side"], "size": SIZE,
                                         "trailingStop": True, "stopDistance": trail_pts})
    modo = "TRAILING nativo"
    if r.status_code not in (200, 201):
        print(f"  Trailing nativo rechazado ({r.status_code}): {r.text[:120]} -> stop FIJO + trailing manual")
        snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
        px = snap.get("offer") if ev["side"] == "BUY" else snap.get("bid")
        if px is None:
            print("  Sin precio -> no entro."); return
        sl = round(px - trail_pts, 1) if ev["side"] == "BUY" else round(px + trail_pts, 1)
        r = cc.post(h, "/api/v1/positions", {"epic": EPIC, "direction": ev["side"], "size": SIZE, "stopLevel": sl})
        modo = "stop FIJO (trailing manual)"
        if r.status_code not in (200, 201):
            print(f"  Orden NO colocada ({r.status_code}): {r.text}"); return
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA: {ev['side']} {SIZE} {EPIC} a mercado {modo} dist={trail_pts}pts ({TRAIL_ATR}xATR) "
          f"ref={ref} status={conf.get('dealStatus')} nivel={conf.get('level')}")


if __name__ == "__main__":
    main()
