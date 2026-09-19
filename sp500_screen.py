#!/usr/bin/env python3
"""
SCREENING de estrategias para SP500 (capital.com US500) — velas 1h de Yahoo ES=F (~2.4 anos).
Objetivo: ~6-7 entradas/semana, robusto por tercios (ROB3), neto con spread.

Familias:
  - RSI reversion  (cruce RSI bajo umbral -> largo; sobre 100-umbral -> corto). Solo-largo y 2 lados.
  - BB reversion   (cierre cruza banda inferior -> largo; superior -> corto). Solo-largo y 2 lados.
  - Donchian       (ruptura de canal 2 lados, salida canal opuesto), como el trend del oro.
Salida comun: trailing = mult x ATR (fijo al entrar), sin TP. Sin look-ahead.

NOTA: indicadores calculados sobre la serie completa (rapido, exploratorio). La config ganadora
se re-valida despues con ventana movil exacta (como el bot en vivo) antes de desplegar.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-bot")))
import backtest_real as br
import bot_gold as bg          # rsi_series, atr_series, sma, stdev_pop (identicos a Pine)

SPREAD = 0.3                    # medio-spread US500 (spread total 0.6)
SIZE_REF = 1.0                  # US500: $1/pt por unidad (referencia)
WARM = 210                      # velas de calentamiento de indicadores


def trades_stats(tr):
    if not tr:
        return None
    tot, wr, pf, mdd, terc, rob = br.stats(tr, "net")
    return tot, wr, pf, mdd, terc, rob


def simulate(sig_fn, H, L, C, T, atr, mult, exit_fn=None):
    """sig_fn(t)->'long'|'short'|None en la vela t (ya cerrada). exit_fn(t,side)->bool salida extra."""
    trades = []; pos = None
    for t in range(WARM, len(C)):
        exited = False
        if pos:
            s = pos["side"]; ex = None
            if s == "long" and L[t] <= pos["stop"]:
                ex = pos["stop"]
            elif s == "short" and H[t] >= pos["stop"]:
                ex = pos["stop"]
            elif exit_fn and exit_fn(t, s):
                ex = C[t]
            if ex is not None:
                g = (ex - pos["entry"]) if s == "long" else (pos["entry"] - ex)
                trades.append({"gross": g, "net": g - 2 * SPREAD, "t_in": pos["t_in"], "t_out": T[t]})
                pos = None; exited = True
            else:
                if s == "long":
                    pos["extreme"] = max(pos["extreme"], H[t]); pos["stop"] = max(pos["stop"], pos["extreme"] - pos["dist"])
                else:
                    pos["extreme"] = min(pos["extreme"], L[t]); pos["stop"] = min(pos["stop"], pos["extreme"] + pos["dist"])
        if pos is None and not exited:
            s = sig_fn(t)
            if s and atr[t]:
                d = mult * atr[t]
                pos = {"side": s, "entry": C[t], "dist": d, "t_in": T[t],
                       "stop": C[t] - d if s == "long" else C[t] + d, "extreme": C[t]}
    return trades


def main():
    interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
    rng = sys.argv[2] if len(sys.argv) > 2 else "730d"
    O, H, L, C, T = br.fetch_yahoo("ES=F", interval, rng)
    weeks = (T[-1] - T[0]).days / 7
    n = len(C)
    atr = bg.atr_series(H, L, C, 14)
    rsi = bg.rsi_series(C, 14)
    print(f"ES=F {interval} | {n} velas | {T[0]:%Y-%m-%d} -> {T[-1]:%Y-%m-%d} | {weeks:.0f} semanas | spread {SPREAD}x2")
    print("Objetivo: 5-8 trades/semana y ROB3.  (<< = en banda y robusto)\n")
    hdr = f"{'estrategia':<34} {'tr/sem':>6} {'#tr':>5} {'NETO':>7} {'PF':>5} {'acc%':>5} {'maxDD':>6}  {'3 tercios':>19}  ROB"
    print(hdr); print("-" * len(hdr))
    rows = []

    def emit(name, tr):
        st = trades_stats(tr)
        if not st:
            return
        tot, wr, pf, mdd, terc, rob = st
        tpw = len(tr) / weeks
        flag = "  <<" if (5 <= tpw <= 8 and rob == 3) else ("   *" if rob == 3 else "")
        rows.append((name, tpw, len(tr), tot, pf, wr, mdd, terc, rob))
        print(f"{name:<34} {tpw:>6.1f} {len(tr):>5} {tot:>+7.0f} {pf:>5.2f} {wr:>4.1f}% {mdd:>+6.0f}  "
              f"{terc[0]:>+5.0f}/{terc[1]:>+5.0f}/{terc[2]:>+5.0f}  ROB{rob}{flag}")

    # ---- RSI reversion (cruce) ----
    for thr in (30, 35, 40):
        hi = 100 - thr
        def rsi_long(t, thr=thr):
            return "long" if (rsi[t] is not None and rsi[t-1] is not None and rsi[t] < thr <= rsi[t-1]) else None
        def rsi_both(t, thr=thr, hi=hi):
            if rsi[t] is None or rsi[t-1] is None:
                return None
            if rsi[t] < thr <= rsi[t-1]:
                return "long"
            if rsi[t] > hi >= rsi[t-1]:
                return "short"
            return None
        for mult in (1.0, 1.5, 2.0, 3.0):
            emit(f"RSI<{thr} solo-largo trail{mult}", simulate(rsi_long, H, L, C, T, atr, mult))
            emit(f"RSI<{thr}/>{hi} 2lados trail{mult}", simulate(rsi_both, H, L, C, T, atr, mult))

    # ---- Bollinger reversion (cruce de banda) ----
    for bb_len, bb_mult in ((20, 2.0), (20, 1.5), (26, 1.75)):
        def bands(t):
            b = bg.sma(C, bb_len, t); d = bb_mult * bg.stdev_pop(C, bb_len, t)
            return b - d, b + d
        def bb_long(t):
            lo0, _ = bands(t); lo1, _ = bands(t-1)
            return "long" if (C[t] < lo0 and C[t-1] >= lo1) else None
        def bb_both(t):
            lo0, up0 = bands(t); lo1, up1 = bands(t-1)
            if C[t] < lo0 and C[t-1] >= lo1:
                return "long"
            if C[t] > up0 and C[t-1] <= up1:
                return "short"
            return None
        for mult in (1.5, 2.0, 3.0):
            emit(f"BB{bb_len}/{bb_mult} solo-largo trail{mult}", simulate(bb_long, H, L, C, T, atr, mult))
            emit(f"BB{bb_len}/{bb_mult} 2lados trail{mult}", simulate(bb_both, H, L, C, T, atr, mult))

    # ---- Donchian 2 lados (salida canal opuesto + trailing) ----
    for ent in (10, 15, 20):
        ex_n = max(4, ent // 2)
        def don_sig(t, ent=ent):
            hh = max(H[t-ent:t]); ll = min(L[t-ent:t])
            return "long" if C[t] > hh else ("short" if C[t] < ll else None)
        def don_exit(t, side, ex_n=ex_n):
            return (C[t] < min(L[t-ex_n:t])) if side == "long" else (C[t] > max(H[t-ex_n:t]))
        for mult in (2.0, 4.0, 6.0):
            emit(f"Donchian {ent}/{ex_n} 2lados trail{mult}", simulate(don_sig, H, L, C, T, atr, mult, don_exit))

    print("\n== Mejores en banda 5-8/sem y ROB3, por neto ==")
    best = sorted([r for r in rows if 5 <= r[1] <= 8 and r[8] == 3], key=lambda r: -r[3])
    for r in best[:8]:
        print(f"  {r[0]:<34} {r[1]:.1f}/sem  {r[3]:+.0f} pts  PF {r[4]:.2f}  acc {r[5]:.0f}%  DD {r[6]:+.0f}")
    if not best:
        print("  (ninguna en banda; ver las ROB3 marcadas con *)")


if __name__ == "__main__":
    main()
