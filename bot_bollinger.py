#!/usr/bin/env python3
"""
Bot Bollinger BTC — reemplaza a TradingView (no requiere plan de pago).

Baja velas 4H de BTC (Kraken), calcula la MISMA estrategia Bollinger validada
(BB20/2 + RSI 35/65, SL 2xATR, TP = banda media) y, si hay señal en la última
vela CERRADA y la cuenta está sin posición, coloca la orden en capital.com DEMO
con su SL/TP. capital.com cierra sola al tocar SL o TP.

Uso:
  ./venv/bin/python bot_bollinger.py            # evalua y opera si hay senal (una vez)
  ./venv/bin/python bot_bollinger.py --dry-run  # solo muestra el estado, NO opera
  ./venv/bin/python bot_bollinger.py --status   # imprime indicadores y senal actual

Pensado para correr 1 vez cada 4 horas (cron / GitHub Actions). Idempotente:
solo abre si NO hay ya una posicion en BTCUSD, y solo en el cruce de la senal.
"""
import sys
import math
from datetime import datetime, timezone, timedelta
import requests
import capital_client as cc

EPIC       = "BTCUSD"          # instrumento en capital.com
# Fuente de velas 4H. Kraken (no Binance) porque los runners de GitHub estan en
# EE.UU. y Binance los bloquea (HTTP 451). Kraken interval=240 = 4 horas.
KRAKEN     = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=240"
SIZE       = 0.05             # tamano de la orden (ajustable) — ~$88 de ganancia por trade ganador
BB_LEN     = 20
BB_MULT    = 2.0
RSI_LEN    = 14
RSI_LOW    = 35
RSI_HIGH   = 65
ATR_LEN    = 14
ATR_MULT   = 2.5             # Stop Loss mas amplio: menos salidas prematuras (75% acierto en sim)


def fetch_closed_candles():
    """Devuelve listas o,h,l,c SOLO de velas cerradas (descarta la vela en curso)."""
    r = requests.get(KRAKEN, timeout=30, headers={"User-Agent": "datika-bot"})
    r.raise_for_status()
    d = r.json()
    if d.get("error"):
        raise RuntimeError(f"Kraken error: {d['error']}")
    res = d["result"]
    key = next(k for k in res if k != "last")   # ej. XXBTZUSD
    rows = res[key][:-1]       # Kraken viene ascendente; la ultima aun no cierra -> fuera
    o = [float(x[1]) for x in rows]
    h = [float(x[2]) for x in rows]
    l = [float(x[3]) for x in rows]
    c = [float(x[4]) for x in rows]
    return o, h, l, c


def sma(series, n, i):
    return sum(series[i-n+1:i+1]) / n


def stdev_pop(series, n, i):
    m = sma(series, n, i)
    var = sum((x-m)**2 for x in series[i-n+1:i+1]) / n   # poblacional, como ta.stdev
    return math.sqrt(var)


def rma_series(series, n):
    """Media movil de Wilder (ta.rma). Devuelve lista alineada con 'series'."""
    out = [None]*len(series)
    if len(series) < n:
        return out
    seed = sum(series[:n]) / n
    out[n-1] = seed
    prev = seed
    for i in range(n, len(series)):
        prev = (prev*(n-1) + series[i]) / n
        out[i] = prev
    return out


def rsi_series(close, n):
    gains, losses = [0.0], [0.0]
    for i in range(1, len(close)):
        d = close[i] - close[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = rma_series(gains, n)
    al = rma_series(losses, n)
    out = [None]*len(close)
    for i in range(len(close)):
        if ag[i] is None or al[i] is None:
            continue
        if al[i] == 0:
            out[i] = 100.0
        else:
            rs = ag[i]/al[i]
            out[i] = 100 - 100/(1+rs)
    return out


def atr_series(high, low, close, n):
    tr = [high[0]-low[0]]
    for i in range(1, len(close)):
        tr.append(max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])))
    return rma_series(tr, n)


def evaluate():
    """Calcula indicadores y devuelve un dict con la senal de la ultima vela cerrada."""
    o, h, l, c = fetch_closed_candles()
    i = len(c) - 1                       # ultima vela CERRADA
    basis = sma(c, BB_LEN, i)
    dev   = BB_MULT * stdev_pop(c, BB_LEN, i)
    upper = basis + dev
    lower = basis - dev
    rsi   = rsi_series(c, RSI_LEN)
    atr   = atr_series(h, l, c, ATR_LEN)
    r_now, r_prev = rsi[i], rsi[i-1]
    a_now = atr[i]

    # condiciones en la vela i y la anterior (para detectar el CRUCE, como en Pine)
    def longC(j):
        b = sma(c, BB_LEN, j); d = BB_MULT*stdev_pop(c, BB_LEN, j)
        return c[j] < (b-d) and rsi[j] is not None and rsi[j] < RSI_LOW
    def shortC(j):
        b = sma(c, BB_LEN, j); d = BB_MULT*stdev_pop(c, BB_LEN, j)
        return c[j] > (b+d) and rsi[j] is not None and rsi[j] > RSI_HIGH

    long_entry  = longC(i)  and not longC(i-1)
    short_entry = shortC(i) and not shortC(i-1)

    side = "BUY" if long_entry else ("SELL" if short_entry else None)
    close = c[i]
    if side == "BUY":
        sl = round(close - ATR_MULT*a_now); tp = round(basis)
    elif side == "SELL":
        sl = round(close + ATR_MULT*a_now); tp = round(basis)
    else:
        sl = tp = None

    return {
        "close": round(close, 1), "basis": round(basis, 1),
        "upper": round(upper, 1), "lower": round(lower, 1),
        "rsi": round(r_now, 1) if r_now else None,
        "atr": round(a_now, 1) if a_now else None,
        "side": side, "sl": sl, "tp": tp,
    }


def has_open_position(h):
    pos = cc.get(h, "/api/v1/positions").json().get("positions", [])
    return any(p["market"]["epic"] == EPIC for p in pos)


def current_bar_close_utc():
    """Inicio de la vela 4H en curso = cierre de la ultima vela cerrada (UTC, naive)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(hour=(now.hour // 4) * 4, minute=0, second=0, microsecond=0)


def acted_this_bar(h, bar_close):
    """True si ya se abrio una posicion de EPIC en esta vela 4H (aunque ya este cerrada).
    Candado de idempotencia: da igual cuantas veces se gatille el bot, abre <=1 por vela."""
    frm = (bar_close - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cc.get(h, f"/api/v1/history/activity?from={frm}")
    if r.status_code != 200:
        # ante la duda, no bloqueo: mejor dejar que el candado 'has_open_position' decida
        return False
    for a in r.json().get("activities", []):
        if a.get("epic") != EPIC or a.get("type") not in ("POSITION", "WORKING_ORDER"):
            continue
        try:
            d = datetime.strptime(a["dateUTC"], "%Y-%m-%dT%H:%M:%S.%f")
        except (KeyError, ValueError):
            continue
        if d >= bar_close:
            return True
    return False


def main():
    dry = "--dry-run" in sys.argv
    status_only = "--status" in sys.argv

    sig = evaluate()
    print(f"[Bollinger 4H {EPIC}] close={sig['close']} banda[{sig['lower']}..{sig['upper']}] "
          f"media={sig['basis']} RSI={sig['rsi']} ATR={sig['atr']}")
    if sig["side"]:
        print(f"  >> SENAL {sig['side']}  SL={sig['sl']}  TP={sig['tp']}")
    else:
        print("  >> sin senal en la ultima vela cerrada")

    if status_only:
        return

    if not sig["side"]:
        return

    h = cc.login()
    if has_open_position(h):
        print("  Ya hay una posicion abierta en", EPIC, "-> no abro otra.")
        return

    bar_close = current_bar_close_utc()
    if acted_this_bar(h, bar_close):
        print(f"  Ya se opero en esta vela 4H (cierre {bar_close}Z) -> no repito (candado).")
        return

    if dry:
        print("  [DRY-RUN] No coloco la orden.")
        return

    body = {"epic": EPIC, "direction": sig["side"], "size": SIZE,
            "stopLevel": sig["sl"], "profitLevel": sig["tp"]}
    r = cc.post(h, "/api/v1/positions", body)
    if r.status_code not in (200, 201):
        sys.exit(f"Orden rechazada ({r.status_code}): {r.text}")
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA: {sig['side']} {SIZE} {EPIC}  ref={ref}  status={conf.get('dealStatus')}")


if __name__ == "__main__":
    main()
