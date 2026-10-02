#!/usr/bin/env python3
"""
Bot NL25 (Netherlands 25 / AEX, capital.com epic NL25) — reversion Bollinger+RSI de DOS LADOS — 15m — DEMO.

POR QUE NL25 (2-oct-2026): barrido completo de 6 mercados nuevos (asset_screen + strategy_zoo,
~1.350 variantes, 15m/300d REALES): NL25 fue el unico con amplitud real, 280 ROB3 (21%) contra
2-9% del resto (DE40, FR40, UK100, J225, RTY). Y es el unico candidato nuevo que CRUZA a 1h/600d.

ESTRATEGIA (entrada identica a bot_sp500 v2; lo que cambia es el stop, mas CORTO):
  - LARGO  si el cierre 15m esta bajo la banda inferior (BB26/1.75) Y RSI(14) < 30, y esa condicion
           NO se cumplia en la vela anterior (cruce). CORTO simetrico (sobre la banda Y RSI > 70).
  - Salida UNICA: trailing = TRAIL_ATR x ATR(14) = 2.0x, fijo al entrar. SIN TP. (Con 4-5x, que
    es lo que funciona en indices de EE.UU., aqui rinde bastante menos.)
  - Una posicion a la vez; candado max 1 orden por vela 15m. Entrada por LIMITE al cierre de la senal.
SESION: NL25 opera 06:00-20:00 UTC lun-vie (cierre nocturno = salto de apertura diario). Por eso:
  - NO entra si el mercado no esta TRADEABLE ni si la ultima vela cerrada NO es la que acaba de
    cerrar (senal vieja de ayer / del viernes). Es lo mismo que asume la validacion.
  - El stop puede ejecutarse en la APERTURA si el mercado abre mas alla del nivel (gap).
Validacion con simulador REALISTA para gaps (backtest_real.py --nl25 --source capital, y
nl25_realista.py: stop en la apertura si hay gap; sin entrada si la vela siguiente no es contigua):
  15m/300d: +145 pts PF 1.56 acc 40% maxDD -34 tercios +47/+26/+72 ROB3, 5.1 tr/sem, meses+ 9/11;
  ROB3 hasta desliz 0.2 pts. 16/40 celdas ROB3 en 15m y 15/40 en 1h/600d (BB26 trail 3x +152 PF1.65).
  Spread medido con bid/ask historicos: 0.10 FIJO durante toda la sesion (tambien en la apertura).
DEBILIDADES: top5 = 80-87% del neto; el 77-84% de la ganancia sale de entradas 06-08h UTC (reversion
  del salto de apertura) -> una sola idea concentrada en dos horas del dia.
Riesgo (NL25 EUR 1/pt/unidad, lotSize 1, margen real 1%, precio ~1113, ATR15m ~1.7): a size 5.0 stop
  inicial ~3.4 pts = ~EUR 17/trade, maxDD ~EUR 170, margen ~EUR 56, ~EUR 17/sem esperado en backtest.
TRAILING: intenta NATIVO (trailingStop); si lo rechaza, stop FIJO + trailing manual cada corrida.
Datos: precios NL25 15m de la propia capital.com. Cron cada 15 min ('1,16,31,46 * * * *'); fuera
de sesion el bot sale sin hacer nada.
Uso: python bot_nl25.py [--status] [--dry-run]
"""
import sys, math
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC      = "NL25"
SIZE      = 5.0            # unico en NL25 -> identifica al bot en candado y tracker
BB_LEN    = 26
BB_MULT   = 1.75
RSI_LEN   = 14
RSI_LOW   = 30
RSI_HIGH  = 70
ATR_LEN   = 14
TRAIL_ATR = 2.0            # trailing CORTO: ROB3 a 2x (y 4x); en 1h/600d el mejor es 3x
BAR_MIN   = 15
DEC       = 2              # NL25 cotiza con 2 decimales (ATR ~1.7): redondear a 0.1 seria grosero


def _mid(x):
    return (x["bid"] + x["ask"]) / 2 if isinstance(x, dict) else x


def current_bar_start():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=(now.minute // BAR_MIN) * BAR_MIN, second=0, microsecond=0)


def fetch_closed(h):
    """OHLC (mid) + hora de inicio, SOLO de velas 15m ya cerradas. max=300 = ventana validada."""
    r = cc.get(h, f"/api/v1/prices/{EPIC}?resolution=MINUTE_15&max=300")
    if r.status_code != 200:
        sys.exit(f"No se pudo bajar precios ({r.status_code}): {r.text}")
    bar0 = current_bar_start()
    O, H, L, C, T = [], [], [], [], []
    for p in r.json().get("prices", []):
        t = (p.get("snapshotTimeUTC") or p.get("snapshotTime") or "").replace("Z", "")
        try:
            bt = datetime.fromisoformat(t)
        except ValueError:
            continue
        if bt >= bar0:
            continue
        O.append(_mid(p["openPrice"])); H.append(_mid(p["highPrice"]))
        L.append(_mid(p["lowPrice"]));  C.append(_mid(p["closePrice"])); T.append(bt)
    return O, H, L, C, T


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
    return {"close": round(close, DEC), "upper": round(upper, DEC), "lower": round(lower, DEC),
            "rsi": round(rsi[i], 1) if rsi[i] else None,
            "atr": round(a, DEC) if a else None, "side": side}


def evaluate(h):
    """Devuelve (senal, hora de inicio de la ultima vela cerrada)."""
    o, hi, lo, c, t = fetch_closed(h)
    if len(c) < BB_LEN + ATR_LEN + 2:
        sys.exit("Pocas velas para calcular.")
    return signal_last(o, hi, lo, c), t[-1]


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
                    bool(pp.get("trailingStop")))
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


def manual_trail(h, deal_id, direction, cur_stop, atr, dry):
    """FALLBACK si el trailing nativo no esta activo: sube el stop a (precio -/+ TRAIL_ATR x ATR)."""
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    is_long = (direction == "BUY")
    price = snap.get("bid") if is_long else snap.get("offer")
    if price is None or not atr:
        print("  Sin precio/ATR -> no ajusto stop."); return
    dist = TRAIL_ATR * atr
    new_stop = round(price - dist, DEC) if is_long else round(price + dist, DEC)
    mejora = (cur_stop is None) or (is_long and new_stop > cur_stop + 0.05) or ((not is_long) and new_stop < cur_stop - 0.05)
    if not mejora:
        print(f"  Trailing MANUAL: stop {cur_stop} se mantiene (precio {price})."); return
    print(f"  Trailing MANUAL: stop {cur_stop} -> {new_stop} (precio {price}, dist {dist:.2f})")
    if dry:
        return
    r = cc.requests.put(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h,
                        json={"stopLevel": new_stop}, timeout=30)
    print(f"     ajuste -> {r.status_code} {r.text[:120]}")


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    sig, last_bar = evaluate(h)
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    abierto = snap.get("marketStatus") == "TRADEABLE"
    print(f"[NL25 15m] close={sig['close']} banda[{sig['lower']}..{sig['upper']}] RSI={sig['rsi']} ATR={sig['atr']} "
          f"| ultima vela {last_bar}Z | mercado {snap.get('marketStatus')}")
    pos = get_position(h)
    if pos:
        deal_id, direction, level, cur_stop, nativo = pos
        print(f"  Posicion ABIERTA {direction} dealId={deal_id} entrada={level} stop={cur_stop} trailing_nativo={nativo}")
        if nativo:
            print("  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real). Nada que hacer.")
        elif not abierto:
            print("  Mercado cerrado -> no ajusto el stop manual.")
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
    # GUARDAS DE SESION (NL25 cierra de noche): la validacion NO entra con el mercado cerrado ni con
    # una senal vieja. Sin esto, a las 06:01 UTC se operaria la senal de la ultima vela de AYER.
    if not abierto:
        print("  Mercado cerrado -> no entro (la senal no se arrastra a la proxima sesion)."); return
    if last_bar != bar0 - timedelta(minutes=BAR_MIN):
        print(f"  Senal VIEJA: la ultima vela cerrada es {last_bar}Z, no la que acaba de cerrar "
              f"({bar0 - timedelta(minutes=BAR_MIN)}Z) -> no entro."); return
    if acted_this_bar(h, bar0):
        print(f"  Ya se opero en esta vela 15m (cierre {bar0}Z) -> candado."); return
    if has_working_order(h):
        print("  Ya hay orden limite pendiente -> no coloco otra."); return
    if dry:
        print("  [DRY-RUN] No coloco la orden."); return
    if not sig["atr"]:
        print("  Sin ATR -> no entro."); return
    trail_pts = round(TRAIL_ATR * sig["atr"], DEC)
    es_buy = sig["side"] == "BUY"
    entry = snap.get("offer") if es_buy else snap.get("bid")
    if entry is None:
        print("  Sin precio de mercado -> no entro."); return
    # ENTRADA POR LIMITE AL CIERRE DE LA SENAL (21-sep-2026). Entrar a mercado ~1 min tras el
    # cierre paga un desliz que el backtest no modelaba. Con orden LIMITE en el cierre exacto
    # (medido en los otros bots con limite_vs_mercado.py; la validacion de NL25 asume entrada al cierre).
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
        sl = round(entry - trail_pts, DEC) if sig["side"] == "BUY" else round(entry + trail_pts, DEC)
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
