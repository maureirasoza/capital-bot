#!/usr/bin/env python3
"""Tracker de trades: clasifica cada operacion por bot (segun instrumento y tamano)
y muestra el P&L acumulado de cada estrategia. Uso: python tracker.py [dias]"""
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import capital_client as cc

# Corte "inicio limpio": ignora trades anteriores a esta fecha (pruebas/historico revuelto).
# Cambiable con:  python tracker.py --desde 2026-08-12T13:00
DESDE = "2026-08-12T13:00"
if "--desde" in sys.argv:
    DESDE = sys.argv[sys.argv.index("--desde") + 1]

DAYS = 14
for a in sys.argv[1:]:
    if a.isdigit():
        DAYS = int(a)
h = cc.login()
now = datetime.now(timezone.utc)

# 1) mapa dealId -> {epic,size,dir,open} desde activity (en chunks diarios: ventanas anchas fallan)
dealmap = {}
for d in range(DAYS):
    a0 = (now - timedelta(days=d + 1)).strftime('%Y-%m-%dT%H:%M:%S')
    a1 = (now - timedelta(days=d)).strftime('%Y-%m-%dT%H:%M:%S')
    r = cc.get(h, f'/api/v1/history/activity?from={a0}&to={a1}&detailed=true')
    if r.status_code != 200:
        continue
    for act in r.json().get('activities', []):
        det = act.get('details') or {}
        if det.get('openPrice') is not None and det.get('size') is not None:
            dealmap[act['dealId']] = {'epic': act.get('epic'), 'size': float(det['size']),
                                      'dir': det.get('direction'), 'open': det.get('openPrice')}

# 2) transactions = cierres con P&L (el P&L viene en el campo 'size' de la tx)
frm = (now - timedelta(days=DAYS)).strftime('%Y-%m-%dT%H:%M:%S')
txs = cc.get(h, f'/api/v1/history/transactions?from={frm}').json().get('transactions', [])


def bot_de(epic, size):
    if epic == 'BTCUSD':
        if size is not None and abs(size - 0.05) < 0.005:
            return 'BTC Bollinger (0.05)'
        return f'BTC pruebas/historico (size {size})'
    if epic == 'GOLD':
        if size is None:
            return 'ORO (sin dato de tamano)'
        if abs(size - 2.0) < 0.05:
            return 'ORO Bollinger (2.0)'
        if abs(size - 0.3) < 0.05:
            return 'ORO FVG (0.3)'
        if abs(size - 0.2) < 0.03:
            return 'ORO Trend 2-lados (0.2)'
        return f'ORO pruebas/historico (size {size})'
    if epic == 'COPPER':
        if size is not None and abs(size - 100) < 5:
            return 'COBRE trend (100)'
        return f'COBRE pruebas/historico (size {size})'
    return f'otro ({epic})'


stats = defaultdict(lambda: {'n': 0, 'w': 0, 'l': 0, 'pnl': 0.0})
detalle = []
for t in txs:
    if t.get('transactionType') != 'TRADE':
        continue
    if (t.get('dateUtc', '') or '') < DESDE:      # ignora lo anterior al inicio limpio
        continue
    try:
        pnl = float(t.get('size'))
    except (TypeError, ValueError):
        continue
    info = dealmap.get(t.get('dealId'))
    epic = info['epic'] if info else t.get('instrumentName')
    size = info['size'] if info else None
    bot = bot_de(epic, size)
    s = stats[bot]
    s['n'] += 1
    s['pnl'] += pnl
    if pnl > 0:
        s['w'] += 1
    elif pnl < -0.001:
        s['l'] += 1
    detalle.append((t.get('dateUtc', '')[:16], bot, pnl))

print(f"=== TRACKER DE TRADES (inicio limpio desde {DESDE}) ===\n")
orden = ['BTC Bollinger (0.05)', 'ORO Bollinger (2.0)', 'ORO FVG (0.3)']
for bot in orden + [b for b in stats if b not in orden]:
    if bot not in stats:
        continue
    s = stats[bot]
    wr = 100 * s['w'] / s['n'] if s['n'] else 0
    print(f"{bot:<26} | {s['n']:>2} trades | {s['w']}G {s['l']}P ({wr:.0f}% acierto) | P&L {s['pnl']:+.2f} USD")

# saldo
acc = cc.get(h, '/api/v1/accounts').json()['accounts'][0]['balance']
print(f"\nSaldo demo actual: {acc['balance']:.2f} USD")

if '--detalle' in sys.argv or '-d' in sys.argv:
    print("\n--- detalle cronologico ---")
    for dt, bot, pnl in sorted(detalle):
        print(f"  {dt}  {bot:<26} {pnl:+.2f}")
