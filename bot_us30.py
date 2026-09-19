#!/usr/bin/env python3
"""
Bot US30 (Dow Jones, capital.com epic US30) — reversion Bollinger+RSI de DOS LADOS — 15m — DEMO.

POR QUE US30: screening de 20 instrumentos por spread/ATR (19-sep-2026) -> US30 es el mas barato de
operar (spread 2 pts ~ 4.5% del ATR 15m). Screening de ~700 variantes por timeframe con los motores
REALES de los bots (asset_screen.py) sobre datos REALES de capital.com: US30 es el UNICO instrumento
con la misma familia robusta en 1h/600d (98 ROB3 de 623) Y en 15m/300d (71 ROB3 de 713) ->
robustez cruzada de timeframes (lo que le falto al SP500 v1). US100 fue 2o candidato (fuerte en
15m, flojo en 1h); OIL cargado a un regimen; COPPER/FX/BTC/ETH descartados (frecuencia o spread).

ESTRATEGIA (motor identico a bot_sp500 v2 = motor BB+RSI del bot de oro, SIN filtro direccional):
  - LARGO  si el cierre 15m esta bajo la banda inferior (BB20/2.0) Y RSI(14) < 35, y esa condicion
           NO se cumplia en la vela anterior (cruce). CORTO simetrico (sobre la banda Y RSI > 65).
  - Salida UNICA: trailing = TRAIL_ATR x ATR(14) = 5.0x, fijo al entrar. SIN TP.
  - Una posicion a la vez; candado max 1 orden por vela 15m.
Validacion (backtest_real.py --us30 --source capital, US30 15m real 300d, 20135 velas, mismo
signal_last): 2 lados trail3 +6166 ROB3 | 4 +7272 ROB3 | **5 +8814 PF1.46 acc38% maxDD-2224
tercios +1560/+3667/+3587 ROB3, 4.5 tr/sem** | 6 +7778 ROB3 | 7 +3712 ROB3 | 8 ROB0. Meseta 3-7x;
5.0 = centro, mejor neto y drawdown. Solo-largo tambien ROB3 3-6x (PF hasta 1.55) pero mas
dependiente del regimen alcista -> se prefiere 2 lados. En 1h/600d la familia es ROB3 con SL/TP
fijo 1.5/3 (PF 1.32) y trailing ancho 6-8x (PF 1.6-2.3).
Riesgo (US30 $1/pt/unidad, lotSize 1, margen 5%, precio ~51700, ATR15m mediano 46 pts): a size 0.1
stop inicial ~$23/trade, maxDD ~$222 (21% de la cuenta ~1047), margen ~$258.
TRAILING: intenta NATIVO (trailingStop); si lo rechaza, stop FIJO + trailing manual cada corrida.
Datos: precios US30 15m de la propia capital.com. REQUIERE cron cada 15 min ('1,16,31,46 * * * *').
Uso: python bot_us30.py [--status] [--dry-run]
"""
import sys, math
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC      = "US30"
SIZE      = 0.1            # unico en US30 -> identifica al bot en candado y tracker
BB_LEN    = 20
BB_MULT   = 2.0
RSI_LEN   = 14
RSI_LOW   = 35
RSI_HIGH  = 65
ATR_LEN   = 14
TRAIL_ATR = 5.0            # centro de la meseta ROB3 3-7x (ver docstring)
BAR_MIN   = 15


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
                    bool(pp.get("trailingStop")))
    return None


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
    print(f"[US30 15m] close={sig['close']} banda[{sig['lower']}..{sig['upper']}] RSI={sig['rsi']} ATR={sig['atr']}")
    pos = get_position(h)
    if pos:
        deal_id, direction, level, cur_stop, nativo = pos
        print(f"  Posicion ABIERTA {direction} dealId={deal_id} entrada={level} stop={cur_stop} trailing_nativo={nativo}")
        if nativo:
            print("  Stop TRAILING NATIVO (capital.com lo mueve en tiempo real). Nada que hacer.")
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
