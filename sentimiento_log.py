#!/usr/bin/env python3
"""Imprime UNA linea JSON con el sentimiento de clientes de capital.com (% comprados) de los mercados de los bots.
capital.com no da historico de este dato -> lo guardamos nosotros cada 15 min (paso del workflow del SP500, rama
'datos-sentimiento', archivo sentimiento.jsonl) para poder probar en unas semanas si sirve como filtro."""
import json
from datetime import datetime, timezone
import capital_client as cc

EPICS = ["US500", "US30", "US100", "RTY", "NL25", "GOLD", "BTCUSD", "ETHUSD"]

h = cc.login()
d = cc.get(h, "/api/v1/clientsentiment?marketIds=" + ",".join(EPICS)).json()
fila = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
for s in d.get("clientSentiments", []):
    fila[s["marketId"]] = s.get("longPositionPercentage")
print(json.dumps(fila))
