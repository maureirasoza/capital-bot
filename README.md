# Capital.com — esqueleto DEMO

Cliente mínimo para practicar con la API de capital.com en **entorno demo** (dinero ficticio).
Las credenciales viven solo en tu `.env` local; nunca en el código ni en el repo.

## Pasos

1. **Genera una API key NUEVA de demo** en capital.com → *Settings → API integrations*.
   Al crearla defines una "custom password" para la key: guárdala.

2. **Configura tus credenciales** (edita el `.env`, ya creado a partir de la plantilla):
   ```
   CAPITAL_IDENTIFIER=tu-correo@ejemplo.com
   CAPITAL_API_PASSWORD=la-custom-password-de-la-key
   CAPITAL_API_KEY=tu-api-key-de-demo
   CAPITAL_ENV=demo
   ```

3. **Prueba el login** (las deps ya están instaladas en ./venv):
   ```bash
   ./venv/bin/python capital_client.py login
   ```

## Comandos

```bash
./venv/bin/python capital_client.py account        # saldo y cuentas
./venv/bin/python capital_client.py search plata    # buscar instrumentos (epics)
./venv/bin/python capital_client.py price SILVER    # precio de un epic
./venv/bin/python capital_client.py buy  SILVER 1   # compra demo tamaño 1
./venv/bin/python capital_client.py sell SILVER 1   # venta demo tamaño 1
./venv/bin/python capital_client.py positions       # posiciones abiertas
./venv/bin/python capital_client.py close <dealId>  # cerrar posición
```

## Seguridad

- `CAPITAL_ENV=live` está **bloqueado** por defecto. Operar en real es bajo tu
  responsabilidad y exige que TÚ pongas `CAPITAL_ALLOW_LIVE=1`.
- El `.env` está en `.gitignore`: no se sube a git.
- Si alguna credencial se expone, revócala/regenérala en capital.com.
