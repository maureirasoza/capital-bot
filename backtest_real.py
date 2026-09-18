#!/usr/bin/env python3
"""
Backtest REAL de los bots — usa el MISMO codigo que corre en vivo (importa las
funciones de senal de cada bot), NO una copia traducida. Asi es imposible que el
test se desincronice del bot que opera de verdad.

Por ahora: bot TREND (Donchian 15/8, stop trailing 0.5xATR, size 0.5).

Datos: oro 1h de Yahoo (GC=F, futuro COMEX) como proxy del GOLD de capital.com.
  - GC=F es cercano al spot pero NO identico (sin financiacion overnight, niveles
    algo distintos). Es el proxy estandar para validar la LOGICA de la estrategia.
Costos: se modela un medio-spread SPREAD por lado (entrada y salida) para acercarlo
  al neto real de capital.com. Se reporta bruto y neto.

Metodologia anti-trampa:
  - Ventana movil de 200 velas (lo que ve el bot en vivo con max=200) -> mismo ATR/canales.
  - En cada vela: primero se chequea si el STOP (fijado con velas PREVIAS) fue tocado,
    LUEGO se sube el trailing con el maximo de la vela actual. Sin look-ahead.

Uso: ./venv/bin/python backtest_real.py
"""
import sys
import json
import urllib.request
from datetime import datetime, timezone
import bot_gold_trend as bt      # <-- codigo REAL del bot en vivo (signal_at, params)

WIN     = 200      # velas que ve el bot en vivo (capital.com max=200)
SPREAD  = 0.3      # medio-spread por lado en puntos (aprox capital.com GOLD)
DOLLAR_PER_PT = 1.0  # $ por punto por unidad de tamano (size 1.0 -> $1/pt, verificado)


def fetch_yahoo(symbol="GC=F", interval="1h", rng="730d"):
    """OHLC 1h desde el chart API de Yahoo (sin librerias extra, solo urllib)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval={interval}&range={rng}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.load(r)
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    O, H, L, C, T = [], [], [], [], []
    for i in range(len(ts)):
        o, h_, l_, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h_, l_, c):
            continue
        O.append(o); H.append(h_); L.append(l_); C.append(c)
        T.append(datetime.fromtimestamp(ts[i], tz=timezone.utc))
    return O, H, L, C, T


def simulate(O, H, L, C, T, stop_mult):
    """Simula el bot TREND con un trailing = stop_mult x ATR. Sin look-ahead:
    el stop se chequea con la vela actual ANTES de subirlo con su maximo."""
    n = len(C)
    trades = []
    pos = None
    for t in range(WIN, n):
        lo = t - WIN + 1
        sig = bt.signal_at(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1], WIN - 1)
        exited = False
        if pos:
            side = pos["side"]
            exit_px = None; reason = None
            if side == "long" and L[t] <= pos["stop"]:
                exit_px, reason = pos["stop"], "stop"
            elif side == "short" and H[t] >= pos["stop"]:
                exit_px, reason = pos["stop"], "stop"
            elif side == "long" and sig["exit_long"]:
                exit_px, reason = C[t], "donchian"
            elif side == "short" and sig["exit_short"]:
                exit_px, reason = C[t], "donchian"
            if exit_px is not None:
                gross = (exit_px - pos["entry"]) if side == "long" else (pos["entry"] - exit_px)
                trades.append({"side": side, "entry": pos["entry"], "exit": exit_px,
                               "t_in": pos["t_in"], "t_out": T[t], "gross": gross,
                               "net": gross - 2 * SPREAD, "reason": reason})
                pos = None; exited = True
            else:
                if side == "long":
                    pos["extreme"] = max(pos["extreme"], H[t])
                    pos["stop"] = max(pos["stop"], pos["extreme"] - pos["dist"])
                else:
                    pos["extreme"] = min(pos["extreme"], L[t])
                    pos["stop"] = min(pos["stop"], pos["extreme"] + pos["dist"])
        if pos is None and not exited:
            if sig["long_break"]:
                d = stop_mult * sig["atr"]
                pos = {"side": "long", "entry": C[t], "dist": d,
                       "stop": C[t] - d, "extreme": C[t], "t_in": T[t]}
            elif sig["short_break"]:
                d = stop_mult * sig["atr"]
                pos = {"side": "short", "entry": C[t], "dist": d,
                       "stop": C[t] + d, "extreme": C[t], "t_in": T[t]}
    return trades


def run_trend():
    O, H, L, C, T = fetch_yahoo()
    return simulate(O, H, L, C, T, bt.ATR_STOP), T[WIN], T[-1], len(C)


def stats(trades, key):
    vals = [x[key] for x in trades]
    tot = sum(vals)
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    wr = 100 * len(wins) / len(vals) if vals else 0
    # max drawdown sobre la curva acumulada
    eq = 0; peak = 0; mdd = 0
    for v in vals:
        eq += v; peak = max(peak, eq); mdd = min(mdd, eq - peak)
    # 3 tercios
    k = len(vals) // 3
    t1, t2, t3 = sum(vals[:k]), sum(vals[k:2*k]), sum(vals[2*k:])
    rob = sum(1 for x in (t1, t2, t3) if x > 0)
    return tot, wr, pf, mdd, (t1, t2, t3), rob


def run_sweep():
    O, H, L, C, T = fetch_yahoo()
    grid = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0]
    print("=" * 78)
    print("BARRIDO DE SL (trailing = mult x ATR) — bot TREND, mismo codigo que en vivo")
    print(f"Datos: Yahoo GC=F 1h | {len(C)} velas | {T[WIN]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}")
    print(f"Neto = con spread {SPREAD}x2 pts/trade. Se busca ZONA estable, no el pico.")
    print("=" * 78)
    print(f"{'SL':>5} | {'#tr':>4} | {'NETO':>7} | {'PF':>4} | {'acc%':>5} | "
          f"{'maxDD':>6} | {'3 tercios':>20} | ROB")
    print("-" * 78)
    rows = []
    for m in grid:
        tr = simulate(O, H, L, C, T, m)
        tot, wr, pf, mdd, terc, rob = stats(tr, "net")
        rows.append((m, len(tr), tot, pf, wr, mdd, terc, rob))
        star = "  <<" if rob == 3 else ""
        print(f"{m:>4}x | {len(tr):>4} | {tot:>+7.0f} | {pf:>4.2f} | {wr:>4.1f}% | "
              f"{mdd:>+6.0f} | {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} | ROB{rob}{star}")
    print("-" * 78)
    robustos = [r for r in rows if r[7] == 3]
    if robustos:
        best = max(robustos, key=lambda r: r[2])
        print(f"Mejor ROBUSTO (positivo en los 3 tercios): SL {best[0]}xATR  ->  "
              f"{best[2]:+.0f} pts netos, PF {best[3]:.2f}, acierto {best[4]:.1f}%")
    else:
        print("Ningun SL da ROB3 en este periodo.")


def main():
    if "--sweep" in sys.argv:
        run_sweep(); return
    print("=" * 68)
    print("BACKTEST REAL — bot TREND (mismo codigo que corre en vivo)")
    print(f"  Donchian {bt.ENT}/{bt.EXIT} | trailing {bt.ATR_STOP}xATR | size {bt.SIZE}")
    print("=" * 68)
    trades, t0, t1, nbars = run_trend()
    if not trades:
        print("Sin trades en el periodo."); return
    print(f"Datos: Yahoo GC=F 1h | {nbars} velas | {t0:%Y-%m-%d} -> {t1:%Y-%m-%d}")
    print(f"Trades: {len(trades)} | spread modelado: {SPREAD}x2 pts/trade\n")

    for label, key in (("BRUTO (sin spread)", "gross"), ("NETO  (con spread)", "net")):
        tot, wr, pf, mdd, terc, rob = stats(trades, key)
        usd = tot * bt.SIZE * DOLLAR_PER_PT
        print(f"--- {label} ---")
        print(f"  Puntos totales : {tot:+.1f}   (~${usd:+.0f} con size {bt.SIZE})")
        print(f"  Acierto        : {wr:.1f}%   Profit factor: {pf:.2f}")
        print(f"  Max drawdown   : {mdd:+.1f} pts")
        print(f"  3 tercios      : {terc[0]:+.0f} / {terc[1]:+.0f} / {terc[2]:+.0f}  "
              f"-> ROB{rob} ({'robusto' if rob==3 else 'parcial' if rob==2 else 'debil'})")
        print()


if __name__ == "__main__":
    main()
