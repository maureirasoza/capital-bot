# Automatización BTC: TradingView → Make → capital.com (DEMO)

Flujo:
```
TradingView (estrategia_rango_btc.pine)
   │  webhook JSON: {secret, epic, side, entry, sl, tp}
   ▼
Make "Datika BTC TradingView"  (id 5909414)
   1) Webhook   2) Login capital.com demo   3) Coloca la orden con SL/TP
   ▼
capital.com  (entorno DEMO)
```

Webhook URL (va en la alerta de TradingView):
```
https://hook.us2.make.com/2oh8k32c6a4kjsfqisfwnk7wrpeo4v28
```

## Pasos para dejarlo andando

### 1. Encontrar el "epic" de Bitcoin en capital.com
```bash
cd capital-demo && ./venv/bin/python capital_client.py search bitcoin
```
Anota el epic (ej. `BITCOIN`). Ese valor va en el input `epic` del Pine Script.

### 2. Cargar el Pine Script en TradingView
- Abre el gráfico de BTC (4H recomendado) → Pine Editor → pega `estrategia_rango_btc.pine`.
- Ajusta el input `epic` con el de capital.com y deja el `secret` como `datika-btc-2026`.
- "Add to chart". Verás soporte/resistencia y flechas de señal.
- Crea una **alerta** sobre el indicador:
  - Condition: "Datika BTC Rango" → *alert() function calls only*.
  - Notifications → **Webhook URL** = la de arriba.
  - Message: deja vacío (el script ya manda el JSON).

### 3. Completar el escenario de Make (los secretos van en Make, NO en el chat)
En Make → escenario "Datika BTC TradingView" → abre los 2 módulos HTTP y reemplaza:
- `PON_TU_API_KEY_DEMO`  → tu API key **de demo** (en los DOS módulos).
- `PON_TU_CORREO`        → el correo de tu cuenta capital.com.
- `PON_TU_CUSTOM_PASSWORD`→ la custom password de la API key.

Verifica en el módulo 3 que los headers `CST` y `X-SECURITY-TOKEN` tomen el valor
de la respuesta del módulo 2 (login). Ese es el único mapeo delicado. La fórmula
EXACTA (ojo: comillas simples, sin `first()`, keys y nombre en minúscula) es:

```
CST              = {{map(2.headers; "value"; "name"; "cst")}}
X-SECURITY-TOKEN = {{map(2.headers; "value"; "name"; "x-security-token")}}
```

capital.com manda los headers como `CST`/`X-SECURITY-TOKEN` pero Make los guarda en
minúscula dentro del array `2.headers` (por eso `cst`/`x-security-token`). Si tipeas
esto a mano en la UI de Make, revisa que no dupliquen las comillas — ese fue el bug
que rompía todo (`" ""value"""` en vez de `"value"`).

✅ PROBADO 11-ago-2026: webhook → login → orden BUY BTCUSD 0.01 con SL/TP colocada OK.

### 4. Encender y probar
- Activa el escenario (toggle ON).
- En TradingView usa "Send test" en la alerta, o baja la vela para gatillar la señal.
- Debe abrirse una posición en tu cuenta DEMO con su SL/TP. Verifícalo:
```bash
./venv/bin/python capital_client.py positions
```

## Notas
- `size` está fijo en 0.01 en el módulo 3 de Make. Ajústalo a tu gusto.
- Todo apunta al entorno **DEMO** (`demo-api-capital...`). Para live habría que
  cambiar la URL y usar tu key live — eso es decisión y responsabilidad tuya.
- El `secret` evita que cualquiera dispare tu webhook: si no coincide, Make lo descarta.
