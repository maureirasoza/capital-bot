#!/usr/bin/env python3
"""
Bot CRIPTO ATR-BREAKOUT (BTC + ETH) — "estallido de volatilidad" — velas 4h — 24/7 — capital.com DEMO.

POR QUE (3-oct-2026): busqueda de un bot cripto 24/7 con costos REALES de capital.com (bid/ask
historico, financiamiento largo -0.0616%/dia, desliz). Familias probadas en 7 anios diarios y 6 anios de
4h (crypto_lab.py, crypto_familias.py): la reversion pierde; la tendencia diaria gana pero es casi toda
"estar largo en el alcista". La UNICA familia robusta: seguir un ESTALLIDO de volatilidad de 4h
(crypto_atrbk.py). Pruebas superadas:
  - Fenomeno real: antes de costos gana en 9-11 de 13 criptos (crypto_cesta.py); despues de costos solo
    BTC y ETH (altcoins: spread historico 1-2.5% por operacion).
  - Gana en 2022 (bajista) en ambas: no depende de que la cripto suba. Compras y ventas aportan.
  - Meseta: k 3.0-3.5 x trailing 2-4 todos PF>1.25 en ambas; filtro EMA 150-400 todos mejoran.
  - EJECUCION FIEL 5m bid/ask (crypto_fiel.py, 2024-01 -> 2026-10): igual o mejor que el modelo 4h.
CONFIG (centro de meseta): k=3.0, trailing 2.0xATR, filtro EMA200 de 4h, piramide +1 unidad a +2xATR.
  6 anios modelo, cartera BTC+ETH: +306% (suma de % por unidad) DD -27%, PF 2.60/3.66, 6/7 anios +,
  2022 +116. Fiel 2.7 anios: BTC 26 ops +28% PF1.89 DD-19 | ETH 26 ops +156% PF6.36 DD-8.
  Version 1h descartada (BTC en empate, 2025 negativo).
FRECUENCIA BAJA: ~10 operaciones/anio por cripto (~0.4/semana entre ambas).

ESTRATEGIA (por cada cripto, al cierre de cada vela de 4h):
  - LARGO si |cierre - cierre previo| > K x ATR(14) de la vela previa, hacia ARRIBA, y cierre > EMA200.
    CORTO simetrico (hacia abajo y cierre < EMA200).
  - ENTRADA A MERCADO (1 min tras el cierre), trailing nativo = TRAIL_ATR x ATR(vela de senal). SIN TP.
  - PIRAMIDE: con la base sola y el cierre 4h a +PYR_STEP x ATR(entrada) a favor, +1 unidad (SIZE_PYR)
    a mercado con la misma distancia de trailing. Si la base ya salio, no se re-piramida.
  - Una operacion por cripto a la vez; candado de 1 orden por vela 4h (el cron puede correr cada hora).
Riesgo: ~1.100 USD nocionales por cripto -> peor caida historica conjunta ~300 USD; margen cripto 5%
  (~55 USD por cripto, ~110 si piramida). Financiamiento de largos incluido en la validacion.
Uso: python bot_crypto.py [--status] [--dry-run]
"""
import sys
from datetime import datetime, timezone, timedelta
import capital_client as cc

MARKETS   = {"BTCUSD": {"size": 0.013, "size_pyr": 0.0131, "dec": 2},
             "ETHUSD": {"size": 0.41,  "size_pyr": 0.411,  "dec": 2}}
K         = 3.0           # estallido: |cierre - cierre previo| > K x ATR previo
TRAIL_ATR = 2.0           # trailing nativo desde la entrada
EMA_LEN   = 200           # filtro de tendencia (velas 4h ~ 33 dias)
PYR_STEP  = 2.0           # piramide a +2 x ATR(entrada)
PYR_MAX   = 2
ATR_LEN   = 14
BAR_H     = 4
N_CANDLES = 600           # velas 4h que baja el bot (semilla de la EMA pesa ~0.25%)


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


def ema_series(s, k):
    out = [s[0]]; a = 2 / (k + 1)
    for x in s[1:]:
        out.append(x * a + out[-1] * (1 - a))
    return out


def signal_at(O, H, L, C, i):
    """Senal en la vela 4h i. PURA (sin red): la misma regla validada (crypto_fiel.atrbk)."""
    atr = atr_series(H, L, C, ATR_LEN); ema = ema_series(C, EMA_LEN)
    a_prev, a = atr[i-1], atr[i]
    side = None
    if a_prev:
        if C[i] - C[i-1] > K * a_prev and C[i] > ema[i]:
            side = "BUY"
        elif C[i-1] - C[i] > K * a_prev and C[i] < ema[i]:
            side = "SELL"
    return {"side": side, "close": C[i], "atr": a, "ema": ema[i],
            "move_atr": (C[i] - C[i-1]) / a_prev if a_prev else None}


def _mid(x):
    return (x["bid"] + x["ask"]) / 2 if isinstance(x, dict) else x


def current_bar_start():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(hour=(now.hour // BAR_H) * BAR_H, minute=0, second=0, microsecond=0)


def fetch_closed(h, epic):
    r = cc.get(h, f"/api/v1/prices/{epic}?resolution=HOUR_4&max={N_CANDLES}")
    if r.status_code != 200:
        print(f"  {epic}: no se pudo bajar precios ({r.status_code})"); return None
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


def _is(v, size):
    try:
        return abs(float(v) - size) < 1e-9
    except (TypeError, ValueError):
        return False


def get_positions(h, epic, m):
    out = []
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        pp = p["position"]
        if p["market"]["epic"] == epic and (_is(pp["size"], m["size"]) or _is(pp["size"], m["size_pyr"])):
            out.append({"dealId": pp["dealId"], "direction": pp.get("direction"), "level": pp.get("level"),
                        "stop": pp.get("stopLevel"), "dist": pp.get("trailingStopDistance"),
                        "trailing": bool(pp.get("trailingStop")), "base": _is(pp["size"], m["size"])})
    return out


def acted_this_bar(h, epic, m, bar0):
    """Candado: True si ya se ABRIO una posicion de este bot en esta cripto durante la vela 4h actual."""
    frm = (bar0 - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    r = cc.get(h, f"/api/v1/history/activity?from={frm}&detailed=true")
    if r.status_code != 200:
        return False
    for a in r.json().get("activities", []):
        if a.get("epic") != epic or a.get("type") != "POSITION":
            continue
        det = a.get("details") or {}
        if det.get("openPrice") is not None:
            continue
        if not (_is(det.get("size"), m["size"]) or _is(det.get("size"), m["size_pyr"])):
            continue
        try:
            d = datetime.strptime(a["dateUTC"], "%Y-%m-%dT%H:%M:%S.%f")
        except (KeyError, ValueError):
            continue
        if d >= bar0:
            return True
    return False


def open_market(h, epic, direction, size, dist, dec, etiqueta):
    r = cc.post(h, "/api/v1/positions", {"epic": epic, "direction": direction, "size": size,
                                         "trailingStop": True, "stopDistance": dist})
    modo = "TRAILING nativo"
    if r.status_code not in (200, 201):
        print(f"  {epic}: trailing rechazado ({r.status_code}): {r.text[:120]} -> stop FIJO")
        snap = cc.get(h, f"/api/v1/markets/{epic}").json().get("snapshot", {})
        px = snap.get("offer") if direction == "BUY" else snap.get("bid")
        if px is None:
            print(f"  {epic}: sin precio -> no opero."); return
        sl = round(px - dist, dec) if direction == "BUY" else round(px + dist, dec)
        r = cc.post(h, "/api/v1/positions", {"epic": epic, "direction": direction, "size": size, "stopLevel": sl})
        modo = "stop FIJO (revisar)"
        if r.status_code not in (200, 201):
            print(f"  {epic}: orden NO colocada ({r.status_code}): {r.text}"); return
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  {epic}: {etiqueta} COLOCADA {direction} {size} a mercado {modo} dist={dist} "
          f"ref={ref} status={conf.get('dealStatus')} nivel={conf.get('level')}")


def run_epic(h, epic, m, dry, status):
    data = fetch_closed(h, epic)
    if not data or len(data[3]) < EMA_LEN + ATR_LEN + 2:
        print(f"  {epic}: pocas velas -> salto."); return
    O, H, L, C = data
    ev = signal_at(O, H, L, C, len(C) - 1)
    print(f"[CRIPTO {epic} 4h] close={ev['close']:.2f} ATR={ev['atr']:.2f} EMA{EMA_LEN}={ev['ema']:.2f} "
          f"mov={ev['move_atr']:+.2f}xATR senal={ev['side'] or 'ninguna'}")
    bar0 = current_bar_start()
    poss = get_positions(h, epic, m)
    if poss:
        long = poss[0]["direction"] == "BUY"
        for p in poss:
            print(f"  Posicion ABIERTA {'largo' if long else 'corto'} ({'base' if p['base'] else 'PIRAMIDE'}) "
                  f"entrada={p['level']} stop={p['stop']} trailing={p['dist']}")
        base = [p for p in poss if p["base"]]
        if PYR_MAX >= 2 and len(poss) == 1 and base and base[0]["dist"]:
            b = base[0]; atr_e = float(b["dist"]) / TRAIL_ATR
            lvl = b["level"] + (1 if long else -1) * PYR_STEP * atr_e
            hit = (ev["close"] >= lvl) if long else (ev["close"] <= lvl)
            print(f"  Piramide: nivel {lvl:.2f} cierre {ev['close']:.2f} -> {'ALCANZADO' if hit else 'aun no'}")
            if hit and not (dry or status):
                if acted_this_bar(h, epic, m, bar0):
                    print("  Ya se opero en esta vela 4h -> candado."); return
                open_market(h, epic, b["direction"], m["size_pyr"], round(float(b["dist"]), m["dec"]), m["dec"], "PIRAMIDE")
        elif len(poss) == 1 and not base:
            print("  Queda solo la unidad piramidada -> no re-piramido.")
        return
    if not ev["side"]:
        return
    print(f"  >> ESTALLIDO {ev['side']} ({ev['move_atr']:+.2f}xATR, a favor de la EMA{EMA_LEN})")
    if dry or status:
        print("  [status/dry-run] No opero."); return
    if acted_this_bar(h, epic, m, bar0):
        print(f"  Ya se entro en esta vela 4h ({bar0}Z) -> candado."); return
    open_market(h, epic, ev["side"], m["size"], round(TRAIL_ATR * ev["atr"], m["dec"]), m["dec"], "ENTRADA")


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    for epic, m in MARKETS.items():
        run_epic(h, epic, m, dry, status)


if __name__ == "__main__":
    main()
