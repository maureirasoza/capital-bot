#!/usr/bin/env python3
"""
Bot COBRE (COPPER) 4h — capital.com DEMO. Estrategia TREND-FOLLOWING (distinta a los
bots de oro que son reversion): sigue la tendencia con breakouts de Donchian.

  - Entra LARGO cuando el cierre 4h supera el maximo de las ultimas ENT velas (breakout).
  - Solo LARGOS: el lado corto rompe en cobre (drift estructural al alza) -> validado.
  - Stop inicial = ATR_STOP x ATR por debajo de la entrada, y TRAILEA hacia arriba cada
    vela (nunca baja): asi deja correr las ganadoras y corta las perdedoras.
  - Salida adicional: si el cierre cae bajo el minimo de las ultimas EXIT velas -> cierra.

Validado en backtest (cobre 4h, Donchian 40/20, stop 3xATR, split-half robusto):
+6.5R, ~25 trades/año, payoff 2.1. Reemplaza al bot BTC (reversion sobre cripto en
tendencia = sangraba). Diversifica activo (metal industrial, no oro) y estilo (tendencia
vs reversion). Corre en la MISMA cuenta con size unico (100) para el tracker.

Uso: python bot_cobre.py [--status] [--dry-run]
"""
import sys
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC     = "COPPER"
SIZE     = 100          # size unico (tracker lo distingue); riesgo ~$14/trade con stop 3xATR
ENT      = 40           # breakout: maximo de las ultimas 40 velas 4h (~6.7 dias)
EXIT     = 20           # salida: minimo de las ultimas 20 velas 4h
ATR_LEN  = 14
ATR_STOP = 3.0          # stop = 3 x ATR (inicial y trailing)
BAR_MIN  = 240          # velas de 4 horas (240 min)


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
    h = (now.hour // 4) * 4
    return now.replace(hour=h, minute=0, second=0, microsecond=0)


def fetch_closed(h):
    r = cc.get(h, f"/api/v1/prices/{EPIC}?resolution=HOUR_4&max=200")
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
        if bt >= bar0:          # vela en curso -> fuera
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
    # canales Donchian EXCLUYENDO la vela de decision (rompe contra lo previo)
    hh = max(H[i-ENT:i])      # maximo de las ENT velas anteriores
    ll = min(L[i-EXIT:i])     # minimo de las EXIT velas anteriores
    breakout = close > hh                 # senal de entrada larga
    exit_sig = close < ll                 # senal de salida
    return {"close": round(close, 4), "atr": round(atr, 4),
            "hh": round(hh, 4), "ll": round(ll, 4),
            "breakout": breakout, "exit_sig": exit_sig}


def _mysize(v):
    try:
        return abs(float(v) - SIZE) < 1e-6
    except (TypeError, ValueError):
        return False


def get_position(h):
    """Devuelve (dealId, level, stopLevel) de la posicion COBRE de este bot, o None."""
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        if p["market"]["epic"] == EPIC and _mysize(p["position"]["size"]):
            pp = p["position"]
            return pp["dealId"], pp.get("level"), pp.get("stopLevel")
    return None


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    ev = evaluate(h)
    print(f"[COBRE 4h COPPER] close={ev['close']} ATR={ev['atr']} "
          f"maxDonchian({ENT})={ev['hh']} minDonchian({EXIT})={ev['ll']}")
    pos = get_position(h)

    if pos:
        deal_id, level, cur_stop = pos
        snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
        price = snap.get("bid")                 # para largo, se valora al bid
        print(f"  Posicion ABIERTA (largo) dealId={deal_id} entrada={level} stop={cur_stop} precio={price}")
        # 1) salida por Donchian
        if ev["exit_sig"]:
            print("  >> SALIDA: cierre bajo el minimo Donchian -> cierro posicion.")
            if not (dry or status):
                r = cc.requests.delete(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h, timeout=30)
                print(f"     cierre -> {r.status_code} {r.text}")
            return
        # 2) trailing del stop (solo sube)
        if price is not None:
            new_stop = round(price - ATR_STOP * ev["atr"], 4)
            if cur_stop is None or new_stop > cur_stop:
                print(f"  >> TRAILING: subo stop {cur_stop} -> {new_stop}")
                if not (dry or status):
                    r = cc.requests.put(f"{cc.BASE}/api/v1/positions/{deal_id}",
                                        headers=h, json={"stopLevel": new_stop}, timeout=30)
                    print(f"     ajuste -> {r.status_code} {r.text}")
            else:
                print(f"  Stop se mantiene en {cur_stop} (trailing solo sube).")
        return

    # sin posicion -> buscar entrada
    if not ev["breakout"]:
        print("  >> sin breakout en la ultima vela -> no entro."); return
    print(f"  >> BREAKOUT alcista (close {ev['close']} > max {ev['hh']}) -> señal de compra")
    if status or dry:
        print("  [status/dry-run] No coloco la orden."); return
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    entry = snap.get("offer")
    if entry is None:
        print("  Sin precio actual -> no entro."); return
    sl = round(entry - ATR_STOP * ev["atr"], 4)
    body = {"epic": EPIC, "direction": "BUY", "size": SIZE, "stopLevel": sl}
    r = cc.post(h, "/api/v1/positions", body)
    if r.status_code not in (200, 201):
        print(f"  Orden NO colocada ({r.status_code}): {r.text}"); return
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA: BUY {SIZE} {EPIC} @ {entry} SL={sl} ref={ref} status={conf.get('dealStatus')}")


if __name__ == "__main__":
    main()
