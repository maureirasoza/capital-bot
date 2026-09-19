#!/usr/bin/env python3
"""
Bot SP500 (US500) — reversion Bollinger de DOS LADOS — 15m — capital.com DEMO. EXPERIMENTAL (4o bot).

POR QUE: el SP500 REVIERTE, no tendencia (el Donchian del oro es malo aqui). Objetivo del usuario:
~6-7 entradas/semana -> solo se logra en 15m; en 1h el edge robusto es de ~2.4/sem.

Validado 18-sep-2026 (sp500_screen.py + re-validacion con ventana movil 300, como corre en vivo):
  - ES=F 15m, 60 dias (tope de Yahoo): 7.3 trades/sem, +480 pts, PF 1.79, acierto 40%, maxDD -202.
  - La MISMA logica es ROB3 en 1h/2.4 anos (PF 1.59): robustez cruzada de timeframes. Se prefirio
    sobre BB20/1.5 (mejor en 15m pero debil en 1h) justamente por eso.
  - CAVEAT: solo 60d de 15m y primer tercio plano -> confianza MEDIA. Demo, acumular trades reales.
  - 4a vez que se repite el patron: la robustez vive en el trailing ANCHO (3-3.5xATR).

ESTRATEGIA (exactamente como se valido: BB26/1.75, dos lados, SIN filtros RSI/ADX):
  - LARGO  si el cierre 15m CRUZA bajo la banda inferior (el cierre anterior estaba dentro).
  - CORTO  si el cierre CRUZA sobre la banda superior.
  - Salida UNICA: trailing = TRAIL_ATR x ATR(14), fijo al entrar. SIN TP.
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
ATR_LEN   = 14
TRAIL_ATR = 3.5            # trailing = 3.5 x ATR (validado: zona robusta 3-3.5x; <=2.5x falla)
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


def signal_last(o, hi, lo, c):
    """Senal en la ULTIMA vela de los arrays dados. PURA (sin red): misma logica que en vivo.
    El backtester (backtest_real.py --sp500) importa ESTA funcion -> test identico al bot real."""
    i = len(c) - 1
    basis = sma(c, BB_LEN, i);   dev = BB_MULT * stdev_pop(c, BB_LEN, i)
    b1    = sma(c, BB_LEN, i-1); d1  = BB_MULT * stdev_pop(c, BB_LEN, i-1)
    upper, lower = basis + dev, basis - dev
    a = atr_series(hi, lo, c, ATR_LEN)[i]
    close = c[i]
    side = None
    if close < lower and c[i-1] >= (b1 - d1):        # CRUCE bajo la banda inferior -> largo
        side = "BUY"
    elif close > upper and c[i-1] <= (b1 + d1):      # CRUCE sobre la banda superior -> corto
        side = "SELL"
    return {"close": round(close, 1), "upper": round(upper, 1), "lower": round(lower, 1),
            "atr": round(a, 2) if a else None, "side": side}


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
    if dry:
        print("  [DRY-RUN] No coloco la orden."); return
    if not sig["atr"]:
        print("  Sin ATR -> no entro."); return
    trail_pts = round(TRAIL_ATR * sig["atr"], 1)
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    entry = snap.get("offer") if sig["side"] == "BUY" else snap.get("bid")
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
