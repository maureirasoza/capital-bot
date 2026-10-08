#!/usr/bin/env python3
"""
Bot RTY (US Russell 2000, capital.com epic RTY) — reversion Bollinger+RSI de DOS LADOS — 15m — DEMO.

POR QUE RTY (2-oct-2026): replica del motor BB+RSI de bot_sp500/bot_us30 a indices no probados
(capital-demo/replica_sp500.py, malla 4 params x trailing 3-6x sobre 15m/300d REALES): el motor es
un fenomeno de indices de EE.UU. (Europa y Japon 0-2 celdas ROB3 de 16); RTY fue el MAS ancho:
12/16 ROB3 y las 16 positivas (US500/US30/US100: 7/16). asset_screen + strategy_zoo (1.504
variantes) confirman la familia 2 lados trailing 4-6x y no hallan nada mejor.

ESTRATEGIA (motor identico a bot_us30, mismos params de entrada):
  - LARGO  si el cierre 15m esta bajo la banda inferior (BB20/2.0) Y RSI(14) < 35, y esa condicion
           NO se cumplia en la vela anterior (cruce). CORTO simetrico (sobre la banda Y RSI > 65).
  - Salida UNICA: trailing = TRAIL_ATR x ATR(14) = 4.0x, fijo al entrar. SIN TP.
  - Una posicion a la vez; candado max 1 orden por vela 15m. Entrada por LIMITE al cierre de la senal.
Validacion (backtest_real.py --rty --source capital, RTY 15m real 300d, mismo signal_last):
  trail 4x: +893 pts PF 1.51 acc 40% maxDD -277 tercios +193/+361/+340 ROB3, 6.4 tr/sem; top5 = 64%
  del neto (el menos concentrado de los bots de trailing); meses+ 8/10; ROB3 incluso con desliz 1.0.
  Vecinos ROB3: trail 3x/5x/6x de la misma fila, y BB26/1.75 RSI35/65 trail 4x (+996 PF1.55).
DEBILIDADES (rty_profundo.py): NO cruza a 1h/600d (-181); cortos flojos (PF 1.31 vs largos 1.70);
  sin las entradas 20-23h UTC baja a +422 PF1.23; correlacion semanal +0.34 con el bot SP500
  (34% de sus trades abren con el SP500 ya en el mismo lado) -> en parte duplica esa apuesta.
Riesgo (RTY $1/pt/unidad, lotSize 1, margen real 1%, precio ~2830, spread 0.5): a size 1.0 stop
  inicial ~19.5 pts = ~$20/trade, maxDD ~$277, margen ~$28, ~+$21/sem esperado en backtest.
TRAILING: intenta NATIVO (trailingStop); si lo rechaza, stop FIJO + trailing manual cada corrida.
Datos: precios RTY 15m de la propia capital.com. REQUIERE cron cada 15 min ('1,16,31,46 * * * *').
Uso: python bot_rty.py [--status] [--dry-run]
"""
import sys, math
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC      = "RTY"
SIZE      = 1.0            # unico en RTY -> identifica al bot en candado y tracker
BB_LEN    = 20
BB_MULT   = 2.0
RSI_LEN   = 14
RSI_LOW   = 35
RSI_HIGH  = 65
ATR_LEN   = 14
TRAIL_ATR = 4.0            # fila BB20/2.0 RSI35/65 ROB3 en 3-6x; 4.0 = mejor neto/PF
BAR_MIN   = 15
RESOLUTION = "MINUTE_15"
TIGHT_AT  = 14.0           # 8-oct-2026: cuando la ganancia maxima llega a TIGHT_AT x ATR(entrada), el trailing
TIGHT_K   = 2.0            # pasa de 4.0 a TIGHT_K x ATR. rty_prog_zoom.py 300d: +896 -> +1074 (+20%), 6/6 tramos;
                           # meseta 12-15 x 1.5-3.5 (21/35 celdas mejoran en ambas mitades).
TIGHT_LOOKBACK_D = 6       # dias de velas para recalcular el ATR de la vela de senal


def _mid(x):
    return (x["bid"] + x["ask"]) / 2 if isinstance(x, dict) else x


def current_bar_start():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=(now.minute // BAR_MIN) * BAR_MIN, second=0, microsecond=0)


def fetch_closed(h):
    """OHLC (mid) SOLO de velas 15m ya cerradas. max=300 = ventana con que se valido."""
    r = cc.get(h, f"/api/v1/prices/{EPIC}?resolution=MINUTE_15&max=300")
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


# ---- indicadores (identicos a bot_gold / bot_sp500) ----
def sma(s, n, i): return sum(s[i-n+1:i+1]) / n
def stdev_pop(s, n, i):
    m = sma(s, n, i); return math.sqrt(sum((x-m)**2 for x in s[i-n+1:i+1]) / n)
def _rma(s, n):
    out = [None]*len(s)
    if len(s) < n: return out
    p = sum(s[:n]) / n; out[n-1] = p
    for i in range(n, len(s)): p = (p*(n-1) + s[i]) / n; out[i] = p
    return out
def atr_series(h, l, c, n):
    tr = [h[0]-l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    return _rma(tr, n)
def rsi_series(c, n):
    g, l = [0.0], [0.0]
    for i in range(1, len(c)):
        d = c[i]-c[i-1]; g.append(max(d, 0.0)); l.append(max(-d, 0.0))
    ag, al = _rma(g, n), _rma(l, n); out = [None]*len(c)
    for i in range(len(c)):
        if ag[i] is None: continue
        out[i] = 100.0 if al[i] == 0 else 100 - 100/(1 + ag[i]/al[i])
    return out


def signal_last(o, hi, lo, c):
    """Senal en la ULTIMA vela. PURA (sin red): misma logica que en vivo; el backtester la importa."""
    i = len(c) - 1
    basis = sma(c, BB_LEN, i); dev = BB_MULT * stdev_pop(c, BB_LEN, i)
    upper, lower = basis + dev, basis - dev
    rsi = rsi_series(c, RSI_LEN)
    a = atr_series(hi, lo, c, ATR_LEN)[i]
    close = c[i]

    def longC(j):
        b = sma(c, BB_LEN, j); d = BB_MULT * stdev_pop(c, BB_LEN, j)
        return c[j] < (b - d) and rsi[j] is not None and rsi[j] < RSI_LOW
    def shortC(j):
        b = sma(c, BB_LEN, j); d = BB_MULT * stdev_pop(c, BB_LEN, j)
        return c[j] > (b + d) and rsi[j] is not None and rsi[j] > RSI_HIGH

    side = None
    if longC(i) and not longC(i-1):
        side = "BUY"
    elif shortC(i) and not shortC(i-1):
        side = "SELL"
    return {"close": round(close, 1), "upper": round(upper, 1), "lower": round(lower, 1),
            "rsi": round(rsi[i], 1) if rsi[i] else None,
            "atr": round(a, 1) if a else None, "side": side}


def evaluate(h):
    o, hi, lo, c = fetch_closed(h)
    if len(c) < BB_LEN + ATR_LEN + 2:
        sys.exit("Pocas velas para calcular.")
    return signal_last(o, hi, lo, c)


def _mysize(v):
    try:
        return abs(float(v) - SIZE) < 1e-9
    except (TypeError, ValueError):
        return False


def get_position(h):
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        if p["market"]["epic"] == EPIC and _mysize(p["position"]["size"]):
            pp = p["position"]
            return (pp["dealId"], pp.get("direction"), pp.get("level"), pp.get("stopLevel"),
                    bool(pp.get("trailingStop")), pp.get("trailingStopDistance"), pp.get("createdDateUTC"))
    return None


def has_working_order(h):
    """True si ya hay una orden LIMITE pendiente de este bot (acted_this_bar solo mira POSITION)."""
    r = cc.get(h, "/api/v1/workingorders")
    if r.status_code != 200:
        return False
    for w in r.json().get("workingOrders", []):
        d = w.get("workingOrderData", {})
        if d.get("epic") == EPIC and _mysize(d.get("orderSize")):
            return True
    return False


def acted_this_bar(h, bar0):
    """Candado: True si ya se ABRIO una posicion de este bot en la vela 15m actual (detailed=true)."""
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
    """FALLBACK si el trailing nativo no esta activo: sube el stop a (precio -/+ TRAIL_ATR x ATR)."""
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
    r = cc.requests.put(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h,
                        json={"stopLevel": new_stop}, timeout=30)
    print(f"     ajuste -> {r.status_code} {r.text[:120]}")


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    sig = evaluate(h)
    print(f"[RTY 15m] close={sig['close']} banda[{sig['lower']}..{sig['upper']}] RSI={sig['rsi']} ATR={sig['atr']}")
    pos = get_position(h)
    if pos:
        deal_id, direction, level, cur_stop, nativo, dist, created = pos
        print(f"  Posicion ABIERTA {direction} dealId={deal_id} entrada={level} stop={cur_stop} trailing_nativo={nativo}")
        if nativo:
            print(f"  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real), distancia {dist}.")
            tighten_if_big_gain(h, deal_id, direction, level, cur_stop, dist, created, dry or status)
        else:
            manual_trail(h, deal_id, direction, cur_stop, sig["atr"], dry or status)
        return
    if sig["side"]:
        print(f"  >> SENAL {sig['side']} (banda+RSI recien cumplidos). Salida: trailing {TRAIL_ATR}xATR sin TP")
    else:
        print("  >> sin senal en la ultima vela cerrada"); return
    if status:
        return
    bar0 = current_bar_start()
    if acted_this_bar(h, bar0):
        print(f"  Ya se opero en esta vela 15m (cierre {bar0}Z) -> candado."); return
    if has_working_order(h):
        print("  Ya hay orden limite pendiente -> no coloco otra."); return
    if dry:
        print("  [DRY-RUN] No coloco la orden."); return
    if not sig["atr"]:
        print("  Sin ATR -> no entro."); return
    trail_pts = round(TRAIL_ATR * sig["atr"], 1)
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    es_buy = sig["side"] == "BUY"
    entry = snap.get("offer") if es_buy else snap.get("bid")
    if entry is None:
        print("  Sin precio de mercado -> no entro."); return
    # ENTRADA POR LIMITE AL CIERRE DE LA SENAL (21-sep-2026). Entrar a mercado ~1 min tras el
    # cierre paga un desliz que el backtest no modelaba. Con orden LIMITE en el cierre exacto
    # (medido en los otros bots con limite_vs_mercado.py; la validacion de RTY asume entrada al cierre).
    # La senal se sigue confirmando con el CIERRE; solo cambia COMO se ejecuta la entrada.
    level = sig["close"]
    # Si el mercado ya esta igual o MEJOR que el cierre, entrar a mercado (precio favorable).
    if not ((es_buy and entry <= level) or ((not es_buy) and entry >= level)):
        expiry = (bar0 + timedelta(minutes=BAR_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        rl = cc.post(h, "/api/v1/workingorders",
                     {"epic": EPIC, "direction": sig["side"], "size": SIZE, "level": level,
                      "type": "LIMIT", "trailingStop": True, "stopDistance": trail_pts,
                      "goodTillDate": expiry})
        if rl.status_code in (200, 201):
            ref = rl.json().get("dealReference")
            conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
            print(f"  ORDEN LIMITE: {sig['side']} {SIZE} {EPIC} @ {level} (mercado {entry}) "
                  f"TRAILING {trail_pts}pts ({TRAIL_ATR}xATR) vence {expiry} "
                  f"ref={ref} status={conf.get('dealStatus')}")
            return
        print(f"  Orden limite fallo ({rl.status_code}): {rl.text[:120]} -> entro a MERCADO")
    body = {"epic": EPIC, "direction": sig["side"], "size": SIZE,
            "trailingStop": True, "stopDistance": trail_pts}
    r = cc.post(h, "/api/v1/positions", body)
    modo = "TRAILING nativo"
    if r.status_code not in (200, 201):
        print(f"  Trailing nativo rechazado ({r.status_code}): {r.text[:120]} -> stop FIJO + trailing manual")
        sl = round(entry - trail_pts, 1) if sig["side"] == "BUY" else round(entry + trail_pts, 1)
        r = cc.post(h, "/api/v1/positions",
                    {"epic": EPIC, "direction": sig["side"], "size": SIZE, "stopLevel": sl})
        modo = "stop FIJO (trailing manual)"
        if r.status_code not in (200, 201):
            print(f"  Orden NO colocada ({r.status_code}): {r.text} -> se reintenta en la proxima vela.")
            return
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA: {sig['side']} {SIZE} {EPIC} @ {entry} {modo} dist={trail_pts}pts "
          f"({TRAIL_ATR}xATR) sin TP ref={ref} status={conf.get('dealStatus')}")


if __name__ == "__main__":
    main()
