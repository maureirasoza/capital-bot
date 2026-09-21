#!/usr/bin/env python3
"""
Bot SP500 (US500) — reversion Bollinger de DOS LADOS — 15m — capital.com DEMO. EXPERIMENTAL (4o bot).

POR QUE: el SP500 REVIERTE, no tendencia (el Donchian del oro es malo aqui). Objetivo del usuario:
~6-7 entradas/semana -> solo se logra en 15m; en 1h el edge robusto es de ~2.4/sem.

ESTADO 19-sep-2026 (tarde): **REACTIVADO con ESTRATEGIA v2** (cron-job 8473633 re-habilitado).
  Busqueda sobre 300d REALES de US500 (capital-demo/sp500_mejora.py: 329 variantes = 10 motores de
  entrada reales x lado x salida): el BB puro (v1) NO es robusto; SI lo es el motor BB26/1.75+RSI del
  bot de oro con RSI 30/70 SIN filtro, 2 lados, trailing 3-5x (meseta ROB3):
    trail3.0 +1133 PF1.42 6.9/sem | trail4.0 +1931 PF1.84 maxDD-310 4.9/sem (+25/+937/+970) |
    trail5.0 +1597 PF1.76 maxDD-192 3.8/sem | trail6.0 ROB2. Vecinos (RSI35/65 sin filtro, solo
    largo, 4-5x) tambien ROB3 -> region robusta. Elegido 4.0x (centro, mejor neto, ~5 entradas/sem
    para validar rapido). CAVEAT: primer tercio apenas positivo (+25): el edge se concentra en
    mar-sep 2026 -> la validacion en vivo (demo) es la que manda. Size 1.0 a pedido (maxDD ~30%
    de la cuenta; 0.5 lo dejaria en 15%). Historia de la pausa de la manana:
  v1 PAUSADA por evidencia real. Reactivar SOLO si se re-disena y pasa ROB3 sobre 300d REALES.

Validacion inicial 18-sep (sp500_screen.py + backtest_real --sp500, ventana movil 300):
  - Yahoo ES=F 15m, 60 dias (tope de Yahoo): 73 trades (7-8/sem), +480 pts, PF 1.79, acierto 40%,
    maxDD -202, tercios -6/+247/+238 (ROB2). La misma logica ROB3 en 1h/2.4 anos (PF 1.59) ->
    se creyo "robustez cruzada de timeframes". Se prefirio sobre BB20/1.5 por eso.
RE-VALIDACION 19-sep sobre el INSTRUMENTO REAL (backtest_real --sp500 --source capital: US500 15m
de la propia capital.com, 300 dias, 20121 velas, nov-2025 -> sep-2026):
  - 3.5x: 379 trades, +40 pts, PF 1.01, maxDD -803, tercios -437/-102/+579 -> ROB1 (breakeven).
  - Barrido 2.5x-4x: NINGUN ROB3; todos con el primer tercio muy negativo (-327 a -529).
  => El +480/PF 1.79 de 60 dias era un ARTEFACTO del regimen reciente (jul-sep 2026), no un edge.
     El chequeo cruzado en 1h dio falsa confianza. LECCION: 60d de 15m NO alcanzan para validar;
     usar siempre --source capital (datos reales, ~300d) antes de desplegar.
  - Patron que si se sostiene: la robustez (cuando existe) vive en el trailing ANCHO (3-3.5xATR).

ESTRATEGIA v2 (19-sep, validada en 300d REALES): motor BB+RSI del bot de oro, RSI EXTREMO, sin filtro.
  - LARGO  si el cierre 15m esta bajo la banda inferior (BB26/1.75) Y RSI(14) < 30, y esa
           condicion NO se cumplia en la vela anterior (cruce). CORTO simetrico: sobre la banda
           superior Y RSI > 70. Sin filtro direccional ADX/EMA (con filtro empeora en US500).
  - Salida UNICA: trailing = TRAIL_ATR x ATR(14) = 4.0x, fijo al entrar. SIN TP.
  - Una posicion a la vez; candado: max 1 orden por vela 15m.
TRAILING: intenta NATIVO (trailingStop) como el oro. US500 figura trailingStopsPreference
  NOT_AVAILABLE (el oro tambien y lo acepto igual) -> si lo rechaza, entra con stop FIJO y el bot
  lo va subiendo cada corrida (trailing manual a 15m). PENDIENTE verificar al abrir el mercado.
Datos: precios US500 15m de la propia capital.com (mismo instrumento que operamos).
REQUIERE cron cada 15 min: crontab '1,16,31,46 * * * *' (1 min tras cada cierre 15m).

Uso: python bot_sp500.py [--status] [--dry-run]
"""
import sys, math
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC      = "US500"
SIZE      = 1.0            # a pedido (19-sep). $1/pt por unidad (lotSize 1, USD) -> riesgo inicial
                           # ~27 pts = ~$27/trade con ATR ~7.7; margen 5% ~= $383. Unico bot en US500
                           # -> el tamano identifica al bot para el candado y el tracker.
BB_LEN    = 26
BB_MULT   = 1.75
RSI_LEN   = 14
RSI_LOW   = 30             # 19-sep: entrada = motor BB+RSI del bot de oro con RSI EXTREMO 30/70 y
RSI_HIGH  = 70             # SIN filtro direccional (validado en 300d REALES, ver docstring).
ATR_LEN   = 14
TRAIL_ATR = 4.0            # trailing = 4.0 x ATR. Meseta ROB3 3-5x sobre 300d reales de US500;
                           # 4.0 = centro, mejor neto/PF (+1931, PF 1.84) y ~5 trades/sem.
BAR_MIN   = 15


def _mid(x):
    return (x["bid"] + x["ask"]) / 2 if isinstance(x, dict) else x


def current_bar_start():
    """Inicio de la vela 15m en curso (UTC, naive) = cierre de la ultima vela cerrada."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=(now.minute // BAR_MIN) * BAR_MIN, second=0, microsecond=0)


def fetch_closed(h):
    """OHLC (mid) SOLO de velas 15m ya cerradas, en orden. max=300 = ventana con que se valido."""
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
        if bt >= bar0:      # vela en curso -> fuera
            continue
        O.append(_mid(p["openPrice"])); H.append(_mid(p["highPrice"]))
        L.append(_mid(p["lowPrice"]));  C.append(_mid(p["closePrice"]))
    return O, H, L, C


# ---- indicadores (identicos a Pine ta.* y a bot_gold) ----
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
    """Senal en la ULTIMA vela de los arrays dados. PURA (sin red): misma logica que en vivo.
    Motor = el del bot de oro (gold-bot/bot_gold.py): condicion BB+RSI en la vela i que NO se
    cumplia en la i-1 (cruce), sin filtro direccional. Params RSI 30/70 (validado 300d reales).
    El backtester (backtest_real.py --sp500 --source capital) importa ESTA funcion."""
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
    if longC(i) and not longC(i-1):        # cierre bajo la banda + RSI<30, recien cumplido -> largo
        side = "BUY"
    elif shortC(i) and not shortC(i-1):    # cierre sobre la banda + RSI>70, recien cumplido -> corto
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
    """(dealId, direction, level, stopLevel, trailing_nativo) de la posicion de ESTE bot, o None."""
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
    """True si ya se ABRIO una posicion de este bot en la vela 15m actual (candado).
    detailed=true es OBLIGATORIO: sin el no viene 'details' (size) y el candado queda ciego."""
    frm = (bar0 - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cc.get(h, f"/api/v1/history/activity?from={frm}&detailed=true")
    if r.status_code != 200:
        return False
    for a in r.json().get("activities", []):
        if a.get("epic") != EPIC or a.get("type") != "POSITION":
            continue
        det = a.get("details") or {}
        if det.get("openPrice") is not None:     # cierre -> no cuenta
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


def manual_trail(h, deal_id, direction, cur_stop, atr, dry):
    """FALLBACK si el trailing nativo no esta activo: sube el stop a (precio -/+ TRAIL_ATR x ATR)
    solo si mejora. Aproximacion a 15m del trailing (usa ATR actual)."""
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
    print(f"[SP500 15m US500] close={sig['close']} banda[{sig['lower']}..{sig['upper']}] ATR={sig['atr']}")
    pos = get_position(h)

    if pos:
        deal_id, direction, level, cur_stop, nativo = pos
        print(f"  Posicion ABIERTA {direction} dealId={deal_id} entrada={level} stop={cur_stop} "
              f"trailing_nativo={nativo}")
        if nativo:
            print("  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real). Nada que hacer.")
        else:
            manual_trail(h, deal_id, direction, cur_stop, sig["atr"], dry or status)
        return

    if sig["side"]:
        print(f"  >> SENAL {sig['side']} (cruce de banda). Salida: trailing {TRAIL_ATR}xATR sin TP")
    else:
        print("  >> sin cruce de banda en la ultima vela cerrada"); return
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
    # (limite_vs_mercado.py sobre datos reales 300d): +1521 PF1.60 ROB2 -> LIMITE +1923 PF1.86 ROB3.
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
        # FALLBACK: stop FIJO a la misma distancia; el bot lo trailea manualmente cada corrida.
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
