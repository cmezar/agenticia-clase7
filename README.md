# Ecommerce Router

Proyecto Python 3.12 con LangGraph, FastAPI y Gemini. El agente `router`
clasifica cada mensaje del chat de la tienda en una de tres rutas:

- `preventa`: productos, precios, tallas, stock, promociones y pagos antes de comprar.
- `postventa`: pedidos existentes, reclamos, devoluciones, cambios, garantías y daños.
- `generica`: saludos o preguntas que no corresponden al ecommerce.

La memoria conversacional se conserva por `thread_id`. En la API, `user_id` se
usa como `thread_id`.

## Configuración local

Usa Python 3.12 y crea el entorno virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` y completa `GOOGLE_API_KEY`. No subas `.env` a GitHub.

## Correr el router en local

Desde la raíz del proyecto:

```powershell
python main.py router "¿tienen la polera azul en talla M?"
python main.py router --saltos "mi pedido 4521 llegó roto"
python main.py router --diagrama
```

Puedes cambiar el hilo de memoria con `--thread-id`:

```powershell
python main.py router --thread-id usuario-123 "¿cuánto cuesta el envío?"
```

## Levantar la API

```powershell
uvicorn api.app:app --reload --port 8000
```

La documentación interactiva está en <http://localhost:8000/docs>.

Health check:

```powershell
curl http://localhost:8000/health
```

Ejemplo de chat:

```powershell
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"user_id":"usuario-123","texto":"¿Tienen la polera azul en talla M?"}'
```

El endpoint `/chat` devuelve `ruta`, `motivo` y `respuesta`. Un body sin
`texto` recibe `422`; si falla el proveedor del modelo, la API responde `502`.

## Pruebas

Ejecuta toda la suite:

```powershell
python -m pytest -q
```

Evalúa los 15 casos del router y muestra una tabla con motivos:

```powershell
python scripts/test_router.py
```

## Despliegue en Heroku

El proyecto incluye `Procfile`, `.python-version` y `requirements.txt`.
Después de instalar y autenticar Heroku:

```powershell
heroku login
heroku create NOMBRE-DE-TU-APP
heroku config:set GOOGLE_API_KEY=TU_CLAVE MODELO=gemini-3.5-flash-lite TELEGRAM_TOKEN=TU_TOKEN TELEGRAM_SECRET=TU_SECRETO PUBLIC_URL=https://NOMBRE-DE-TU-APP.herokuapp.com
git push heroku main
heroku open
```

No pongas la clave real en archivos del proyecto ni en commits; usa variables
de configuración de Heroku.

## Conectar Telegram

Tras desplegar la API y configurar `TELEGRAM_TOKEN`, `TELEGRAM_SECRET` y
`PUBLIC_URL`, registra el webhook con Bot API:

```powershell
curl -X POST "https://api.telegram.org/bot$env:TELEGRAM_TOKEN/setWebhook" -d "url=$env:PUBLIC_URL/telegram" -d "secret_token=$env:TELEGRAM_SECRET"
```

En PowerShell, si las variables aún no están definidas en la sesión:

```powershell
$env:TELEGRAM_TOKEN = "TU_TOKEN"
$env:TELEGRAM_SECRET = "TU_SECRETO"
$env:PUBLIC_URL = "https://NOMBRE-DE-TU-APP.herokuapp.com"
```

El endpoint `/telegram` está preparado como cascarón y actualmente responde
`{"ok":true}` a cualquier JSON. La recepción, verificación del secreto y el
envío de respuestas a Telegram se completarán en la siguiente parte.

## Bruno

La colección está en `bruno/` e incluye `health`, `chat-preventa`,
`chat-postventa` y `chat-generica`. Selecciona el entorno `local` o `heroku`;
ambos usan la variable `baseUrl`, por lo que puedes cambiar entre
`http://localhost:8000` y la URL pública sin editar las peticiones.
