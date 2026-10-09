#!/usr/bin/env python3
"""
Bot ORO AWESOME-MACD (epic GOLD) — impulso alcista en velas de 1 hora — DEMO.

ORIGEN (9-oct-2026): estrategia publica 'AwesomeMacd' de freqtrade/freqtrade-strategies (berlinguyinca), reglas
leidas del codigo y re-implementadas (github_lab.py). Fue la UNICA de ~30 estrategias publicas probadas (22 generales
+ 7 de oro) que paso la prueba pareja contra nuestros bots:
  - Ejecucion FIEL 1m bid/ask, 1000d (gold_lab_1m.py): +74.3% del precio, PF 2.65, DD -7.1%, 96 ops, ROB3
    (Trend oro nucleo en el mismo test: +71.6%, PF 1.50, DD -13.2%, 405 ops).
  - 5.5 anios (GOLD 1h bid/ask 2021-04 -> 2026-10, mismo simulador): +75.8%, DD -17.7%; por anio 2021 -10.2,
    2022 +2.4, 2023 +8.8, 2024 +21.3, 2025 +35.8, 2026 +17.8 (Trend nucleo: +46.8%, DD -33.0%).
  - Vecinos (AO 4-6/28-40 x MACD 10-14/22-30): los 15 positivos. Correlacion mensual con Trend oro +0.47.
DEBILIDAD: solo compra -> en un oro lateral/bajista gana poco o pierde (2021 -10%).

ESTRATEGIA (velas 1h cerradas, precio medio):
  AO = SMA5((H+L)/2) - SMA34((H+L)/2);  MACD(12, 26, 9).
  - ENTRADA (compra a mercado 1 min tras el cierre): MACD > 0  y  AO cruza de negativo a positivo.
  - SALIDA por senal (cierre a mercado): MACD < 0  y  AO cruza de positivo a negativo.
  - Del original: objetivo +10% (profitLevel). Stop del original -25%; aqui -10% como seguro de catastrofe
    (peor caida abierta historica -8.2% en 5.5 anios -> no habria cambiado ninguna operacion).
  - Una posicion a la vez; candado 1 orden por vela 1h.
SIZE 0.33 (unico en GOLD: Trend 0.5/0.51, Bollinger 0.8/0.81) -> identifica al bot en candado y tracker.
Riesgo: DD historico ~17.7% del precio en 5.5 anios -> ~$240 a size 0.33 con oro ~$4.100; margen ~$14.
Corre en el MISMO workflow horario que el Trend oro (bot-bollinger.yml, cron-job.org '1 * * * *').
Uso: python bot_gold_ao.py [--status] [--dry-run]
"""
import sys
from datetime import datetime, timezone, timedelta
import capital_client as cc

EPIC      = "GOLD"
SIZE      = 0.33
AO_FAST   = 5
AO_SLOW   = 34
MACD_F, MACD_S, MACD_SIG = 12, 26, 9
TP_PCT    = 0.10           # objetivo del original (+10%)
SL_PCT    = 0.10           # seguro de catastrofe (original -25%; nunca tocado en la historia con -10%)
N_CANDLES = 300            # velas 1h (EMA26 sin efecto de semilla: (25/27)^300 ~ 0)


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


def _sma(x, n):
    out = [None] * len(x); s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n: s -= x[i - n]
        if i >= n - 1: out[i] = s / n
    return out


def _ema(x, n):
    out = []; a = 2 / (n + 1); e = None
    for v in x:
        e = v if e is None else e + a * (v - e); out.append(e)
    return out


def signal_at(O, H, L, C, i):
    """Senal en la vela 1h i. PURA (sin red): misma regla que github_lab.S_awesomemacd (validada)."""
    hl = [(a + b) / 2 for a, b in zip(H, L)]
    f, s = _sma(hl, AO_FAST), _sma(hl, AO_SLOW)
    ao = [None if a is None or b is None else a - b for a, b in zip(f, s)]
    m = [a - b for a, b in zip(_ema(C, MACD_F), _ema(C, MACD_S))]
    ok = i > 0 and ao[i] is not None and ao[i - 1] is not None
    entra = ok and m[i] > 0 and ao[i] > 0 and ao[i - 1] < 0
    sale = ok and m[i] < 0 and ao[i] < 0 and ao[i - 1] > 0
    return {"close": round(C[i], 2), "ao": round(ao[i], 3) if ao[i] is not None else None,
            "macd": round(m[i], 3), "entra": entra, "sale": sale}


def _mysize(v):
    try:
        return abs(float(v) - SIZE) < 1e-9
    except (TypeError, ValueError):
        return False


def get_position(h):
    for p in cc.get(h, "/api/v1/positions").json().get("positions", []):
        pp = p["position"]
        if p["market"]["epic"] == EPIC and _mysize(pp["size"]):
            return pp["dealId"], pp.get("direction"), pp.get("level"), pp.get("stopLevel"), pp.get("profitLevel")
    return None


def acted_this_bar(h, bar0):
    """Candado: True si ya se ABRIO una posicion de este bot en la vela 1h actual (detailed=true obligatorio)."""
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


def main():
    dry = "--dry-run" in sys.argv
    status = "--status" in sys.argv
    h = cc.login()
    O, H, L, C = fetch_closed(h)
    if len(C) < AO_SLOW + MACD_S + 5:
        sys.exit("Pocas velas para calcular.")
    s = signal_at(O, H, L, C, len(C) - 1)
    print(f"[ORO AWESOME-MACD 1h] close={s['close']} AO={s['ao']} MACD={s['macd']} entra={s['entra']} sale={s['sale']}")
    pos = get_position(h)
    if pos:
        deal_id, direction, level, stop, tp = pos
        print(f"  Posicion ABIERTA {direction} dealId={deal_id} entrada={level} stop={stop} objetivo={tp}")
        if s["sale"]:
            print("  >> SALIDA por senal (MACD<0 y AO cruzo a negativo) -> cierro a mercado")
            if not (dry or status):
                r = cc.requests.delete(f"{cc.BASE}/api/v1/positions/{deal_id}", headers=h, timeout=30)
                print(f"     cierre {deal_id} -> {r.status_code} {r.text[:120]}")
        else:
            print("  Sin senal de salida: se mantiene (stop/objetivo puestos en capital.com).")
        return
    if not s["entra"]:
        print("  >> sin senal de entrada en la ultima vela cerrada"); return
    print("  >> SENAL DE COMPRA: MACD>0 y AO cruzo de negativo a positivo")
    if status or dry:
        print("  [status/dry-run] No coloco la orden."); return
    bar0 = current_bar_start()
    if acted_this_bar(h, bar0):
        print(f"  Ya se entro en esta vela 1h ({bar0}Z) -> candado."); return
    snap = cc.get(h, f"/api/v1/markets/{EPIC}").json().get("snapshot", {})
    px = snap.get("offer")
    if px is None:
        print("  Sin precio de mercado -> no entro."); return
    sl, tp = round(px * (1 - SL_PCT), 2), round(px * (1 + TP_PCT), 2)
    r = cc.post(h, "/api/v1/positions", {"epic": EPIC, "direction": "BUY", "size": SIZE, "stopLevel": sl, "profitLevel": tp})
    if r.status_code not in (200, 201):
        print(f"  Orden NO colocada ({r.status_code}): {r.text}"); return
    ref = r.json().get("dealReference")
    conf = cc.get(h, f"/api/v1/confirms/{ref}").json()
    print(f"  ORDEN COLOCADA: BUY {SIZE} {EPIC} @ {px} stop {sl} (-{SL_PCT:.0%}) objetivo {tp} (+{TP_PCT:.0%}) "
          f"ref={ref} status={conf.get('dealStatus')} nivel={conf.get('level')}")


if __name__ == "__main__":
    main()
