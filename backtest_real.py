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
import os
import json
import urllib.request
from datetime import datetime, timezone
import bot_gold_trend as bt      # <-- codigo REAL del bot en vivo (signal_at, params)

WIN     = 200      # velas que ve el bot en vivo (capital.com max=200)
SPREAD  = 0.3      # medio-spread por lado en puntos (aprox capital.com GOLD)
DOLLAR_PER_PT = 1.0  # $ por punto por unidad de tamano (size 1.0 -> $1/pt, verificado)


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_yahoo(symbol="GC=F", interval="1h", rng="730d"):
    """OHLC desde el chart API de Yahoo (solo urllib), CONGELADO en disco.
    La primera bajada se guarda en data/<symbol>_<interval>_<rng>.json y las siguientes la leen:
    asi cada re-corrida del backtest es REPRODUCIBLE (mismo dataset), no depende de que Yahoo
    este disponible, y el rango rodante ('60d') no cambia los numeros con el paso de los dias.
    (Nota 19-sep: se verifico que Yahoo SI es determinista entre llamadas seguidas; una
    discrepancia 91 vs 73 trades fue por correr el SP500 sobre el default GC=F, no por Yahoo.)
    Para actualizar a proposito: pasar --refresh."""
    os.makedirs(DATA_DIR, exist_ok=True)
    safe = symbol.replace("=", "_").replace("^", "")
    path = os.path.join(DATA_DIR, f"{safe}_{interval}_{rng}.json")
    if os.path.exists(path) and "--refresh" not in sys.argv:
        with open(path) as f:
            d = json.load(f)
        T = [datetime.fromisoformat(t) for t in d["T"]]
        print(f"[datos congelados] {path.split(os.sep)[-1]}: {len(d['C'])} velas "
              f"(bajado {d.get('fetched','?')[:16]}). --refresh para actualizar.")
        return d["O"], d["H"], d["L"], d["C"], T
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
    with open(path, "w") as f:
        json.dump({"O": O, "H": H, "L": L, "C": C, "T": [t.isoformat() for t in T],
                   "fetched": datetime.now(timezone.utc).isoformat()}, f)
    print(f"[datos bajados y congelados] {path.split(os.sep)[-1]}: {len(C)} velas")
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


# ----------------------- BOLLINGER (reversion 15m) -----------------------
import os
WIN_BOLL = 300     # velas que ve el bot Bollinger en vivo (capital.com max=300)


def _import_bollinger():
    d = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-bot"))
    if d not in sys.path:
        sys.path.insert(0, d)
    import bot_gold as bg
    return bg


def simulate_bollinger(O, H, L, C, T, bg, trail_mult):
    """Bollinger reversion: entra por signal_last (BB+RSI+filtro ADX/EMA200), UNICA salida
    trailing = trail_mult x ATR (sin TP, como en vivo). Sin look-ahead."""
    n = len(C)
    trades = []
    pos = None
    for t in range(WIN_BOLL, n):
        lo = t - WIN_BOLL + 1
        if pos is None:
            sig = bg.signal_last(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1])
            if sig["side"] and sig["atr"]:
                d = trail_mult * sig["atr"]
                if sig["side"] == "BUY":
                    pos = {"side": "long", "entry": C[t], "dist": d,
                           "stop": C[t] - d, "extreme": C[t], "t_in": T[t]}
                else:
                    pos = {"side": "short", "entry": C[t], "dist": d,
                           "stop": C[t] + d, "extreme": C[t], "t_in": T[t]}
        else:
            side = pos["side"]; exit_px = None
            if side == "long" and L[t] <= pos["stop"]:
                exit_px = pos["stop"]
            elif side == "short" and H[t] >= pos["stop"]:
                exit_px = pos["stop"]
            if exit_px is not None:
                gross = (exit_px - pos["entry"]) if side == "long" else (pos["entry"] - exit_px)
                trades.append({"side": side, "entry": pos["entry"], "exit": exit_px,
                               "t_in": pos["t_in"], "t_out": T[t], "gross": gross,
                               "net": gross - 2 * SPREAD})
                pos = None
            else:
                if side == "long":
                    pos["extreme"] = max(pos["extreme"], H[t])
                    pos["stop"] = max(pos["stop"], pos["extreme"] - pos["dist"])
                else:
                    pos["extreme"] = min(pos["extreme"], L[t])
                    pos["stop"] = min(pos["stop"], pos["extreme"] + pos["dist"])
    return trades


def run_bollinger(sweep=False):
    bg = _import_bollinger()
    O, H, L, C, T = fetch_yahoo(interval="15m", rng="60d")  # Yahoo 15m -> max 60 dias
    print("=" * 78)
    print("BACKTEST REAL — bot BOLLINGER (mismo codigo que corre en vivo)")
    print(f"  BB{bg.BB_LEN}/{bg.BB_MULT} RSI {bg.RSI_LOW}/{bg.RSI_HIGH} | filtro ADX>={bg.ADX_MIN}/EMA{bg.EMA_TREND}"
          f" | size {bg.SIZE}")
    print(f"Datos: Yahoo GC=F 15m | {len(C)} velas | {T[WIN_BOLL]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}")
    print(f"Salida: SOLO trailing x ATR, sin TP. Neto = con spread {SPREAD}x2 pts/trade.")
    print("=" * 78)
    usd_pt = bg.SIZE * DOLLAR_PER_PT
    if not sweep:
        tr = simulate_bollinger(O, H, L, C, T, bg, 1.5)
        if not tr:
            print("Sin trades."); return
        for label, key in (("BRUTO", "gross"), ("NETO (con spread)", "net")):
            tot, wr, pf, mdd, terc, rob = stats(tr, key)
            print(f"--- {label} (trailing 1.5xATR) ---  {len(tr)} trades")
            print(f"  Puntos: {tot:+.1f} (~${tot*usd_pt:+.0f})  acierto {wr:.1f}%  PF {pf:.2f}  maxDD {mdd:+.0f}")
            print(f"  3 tercios: {terc[0]:+.0f}/{terc[1]:+.0f}/{terc[2]:+.0f} -> ROB{rob}\n")
        return
    print(f"{'TRAIL':>6} | {'#tr':>4} | {'NETO':>7} | {'PF':>4} | {'acc%':>5} | "
          f"{'maxDD':>6} | {'3 tercios':>20} | ROB")
    print("-" * 78)
    for m in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
        tr = simulate_bollinger(O, H, L, C, T, bg, m)
        if not tr:
            print(f"{m:>5}x |  sin trades"); continue
        tot, wr, pf, mdd, terc, rob = stats(tr, "net")
        star = "  <<" if rob == 3 else ""
        print(f"{m:>5}x | {len(tr):>4} | {tot:>+7.0f} | {pf:>4.2f} | {wr:>4.1f}% | "
              f"{mdd:>+6.0f} | {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} | ROB{rob}{star}")


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


# ----------------------- FVG (orden limite 15m) -----------------------
WIN_FVG = 200      # velas que ve el bot FVG en vivo (capital.com max=200)


def _import_fvg():
    d = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-fvg-bot"))
    if d not in sys.path:
        sys.path.insert(0, d)
    import bot_fvg_limit as fv
    return fv


def _fvg_exit(pos, hi, lo):
    """Precio de salida si la vela toca SL o TP (SL primero = conservador). None si no."""
    if pos["side"] == "BUY":
        if lo <= pos["sl"]:
            return pos["sl"]
        if hi >= pos["tp"]:
            return pos["tp"]
    else:
        if hi >= pos["sl"]:
            return pos["sl"]
        if lo <= pos["tp"]:
            return pos["tp"]
    return None


def simulate_fvg(O, H, L, C, T, fv):
    """FVG: coloca orden LIMITE en el borde del hueco (SL_MULT/TP_R x hueco), se llena si el
    precio vuelve al borde antes de expirar (FILL_WIN velas), sale por SL/TP. Sin look-ahead."""
    n = len(C)
    trades = []
    pos = None
    order = None
    for t in range(WIN_FVG, n):
        if pos:
            ex = _fvg_exit(pos, H[t], L[t])
            if ex is not None:
                g = (ex - pos["entry"]) if pos["side"] == "BUY" else (pos["entry"] - ex)
                trades.append({"side": pos["side"], "entry": pos["entry"], "exit": ex,
                               "t_in": pos["t_in"], "t_out": T[t], "gross": g,
                               "net": g - 2 * SPREAD})
                pos = None
            continue
        if order:
            hit = ((order["side"] == "BUY" and L[t] <= order["level"]) or
                   (order["side"] == "SELL" and H[t] >= order["level"]))
            if hit:
                pos = {"side": order["side"], "entry": order["level"], "sl": order["sl"],
                       "tp": order["tp"], "t_in": T[t]}
                order = None
                ex = _fvg_exit(pos, H[t], L[t])     # mismo-vela: movida rapida puede tocar SL/TP
                if ex is not None:
                    g = (ex - pos["entry"]) if pos["side"] == "BUY" else (pos["entry"] - ex)
                    trades.append({"side": pos["side"], "entry": pos["entry"], "exit": ex,
                                   "t_in": pos["t_in"], "t_out": T[t], "gross": g,
                                   "net": g - 2 * SPREAD})
                    pos = None
                continue
            elif t >= order["expiry"]:
                order = None
        if pos is None and order is None:
            lo = t - WIN_FVG + 1
            sig = fv.find_pending_fvg_ohlc(O[lo:t+1], H[lo:t+1], L[lo:t+1], C[lo:t+1])
            if sig and sig.get("side"):
                order = {"side": sig["side"], "level": sig["level"], "sl": sig["sl"],
                         "tp": sig["tp"], "expiry": t + sig["remaining_bars"]}
    return trades


def run_fvg(sweep=False):
    fv = _import_fvg()
    O, H, L, C, T = fetch_yahoo(interval="15m", rng="60d")
    print("=" * 78)
    print("BACKTEST REAL — bot FVG (mismo codigo que corre en vivo)")
    print(f"  SL {fv.SL_MULT}x / TP {fv.TP_R}x hueco | EMA{fv.EMA_TREND} | MIN_GAP {fv.MIN_GAP} "
          f"MAX_GAP {fv.MAX_GAP}xATR | vida {fv.FILL_WIN}v | size {fv.SIZE}")
    print(f"Datos: Yahoo GC=F 15m | {len(C)} velas | {T[WIN_FVG]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d}")
    print(f"Entrada: orden LIMITE en el borde. Neto = con spread {SPREAD}x2 pts/trade.")
    print("=" * 78)
    usd_pt = fv.SIZE * DOLLAR_PER_PT
    if not sweep:
        tr = simulate_fvg(O, H, L, C, T, fv)
        if not tr:
            print("Sin trades (ningun hueco se lleno en el periodo)."); return
        for label, key in (("BRUTO", "gross"), ("NETO (con spread)", "net")):
            tot, wr, pf, mdd, terc, rob = stats(tr, key)
            print(f"--- {label} ---  {len(tr)} trades")
            print(f"  Puntos: {tot:+.1f} (~${tot*usd_pt:+.0f})  acierto {wr:.1f}%  PF {pf:.2f}  maxDD {mdd:+.0f}")
            print(f"  3 tercios: {terc[0]:+.0f}/{terc[1]:+.0f}/{terc[2]:+.0f} -> ROB{rob}\n")
        return
    print("Barrido de SL (x hueco), TP fijo en 1.0x:")
    print(f"{'SL':>5} | {'#tr':>4} | {'NETO':>7} | {'PF':>4} | {'acc%':>5} | "
          f"{'maxDD':>6} | {'3 tercios':>20} | ROB")
    print("-" * 78)
    orig = fv.SL_MULT
    for m in (1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
        fv.SL_MULT = m
        tr = simulate_fvg(O, H, L, C, T, fv)
        if not tr:
            print(f"{m:>4}x |  sin trades"); continue
        tot, wr, pf, mdd, terc, rob = stats(tr, "net")
        star = "  <<" if rob == 3 else ""
        print(f"{m:>4}x | {len(tr):>4} | {tot:>+7.0f} | {pf:>4.2f} | {wr:>4.1f}% | "
              f"{mdd:>+6.0f} | {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} | ROB{rob}{star}")
    fv.SL_MULT = orig


# ----------------------- SP500 (reversion BB 15m, US500) -----------------------
def run_sp500(sweep=False):
    """Reusa simulate_bollinger: bot_sp500.signal_last devuelve el mismo dict ({side, atr})."""
    import bot_sp500 as sp     # mismo repo; codigo REAL del bot
    # OJO: pasar symbol EXPLICITO. El default de fetch_yahoo es GC=F (oro): el 19-sep se corrio
    # sin symbol y el backtest del SP500 uso datos de ORO (91 trades/PF 1.36 vs 73/PF 1.79 reales).
    O, H, L, C, T = fetch_yahoo(symbol="ES=F", interval="15m", rng="60d")   # ES=F 15m ~ US500
    weeks = (T[-1] - T[WIN_BOLL]).days / 7
    print("=" * 78)
    print("BACKTEST REAL — bot SP500 (mismo codigo que corre en vivo)")
    print(f"  BB{sp.BB_LEN}/{sp.BB_MULT} 2 lados | trailing {sp.TRAIL_ATR}xATR sin TP | size {sp.SIZE}")
    print(f"Datos: Yahoo ES=F 15m | {len(C)} velas | {T[WIN_BOLL]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} sem")
    print(f"Neto = con spread {SPREAD}x2 pts/trade (US500 spread total 0.6).")
    print("=" * 78)
    usd_pt = sp.SIZE * DOLLAR_PER_PT
    grid = (2.5, 3.0, 3.5, 4.0) if sweep else (sp.TRAIL_ATR,)
    print(f"{'TRAIL':>6} | {'tr/sem':>6} | {'#tr':>4} | {'NETO':>7} | {'PF':>4} | {'acc%':>5} | "
          f"{'maxDD':>6} | {'3 tercios':>20} | ROB")
    print("-" * 78)
    for m in grid:
        tr = simulate_bollinger(O, H, L, C, T, sp, m)
        if not tr:
            print(f"{m:>5}x |  sin trades"); continue
        tot, wr, pf, mdd, terc, rob = stats(tr, "net")
        star = "  <<" if rob == 3 else ""
        print(f"{m:>5}x | {len(tr)/weeks:>6.1f} | {len(tr):>4} | {tot:>+7.0f} | {pf:>4.2f} | {wr:>4.1f}% | "
              f"{mdd:>+6.0f} | {terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f} | ROB{rob}{star}")
        if not sweep:
            print(f"  ~${tot*usd_pt:+.0f} con size {sp.SIZE} | media/trade {tot/len(tr):+.2f} pts")


def main():
    if "--sp500" in sys.argv:
        run_sp500(sweep="--sweep" in sys.argv); return
    if "--fvg" in sys.argv:
        run_fvg(sweep="--sweep" in sys.argv); return
    if "--bollinger" in sys.argv:
        run_bollinger(sweep="--sweep" in sys.argv); return
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
