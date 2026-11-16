"""API HTTP del router de ecommerce."""

import logging
import os
import hmac
import secrets
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException, Security
from pydantic import BaseModel, ConfigDict, Field
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from src.router.graph import PersistenceResources, build_graph, create_persistence
from src.router.reclamos import configure_claim_store

load_dotenv()
logger = logging.getLogger(__name__)

graph = None
_persistence: PersistenceResources | None = None
_memory_type: Literal["ram", "postgres"] = "ram"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _persistence, _memory_type, graph
    _persistence = create_persistence()
    _memory_type = _persistence.memory_type
    if _persistence.claim_store is not None:
        configure_claim_store(_persistence.claim_store)
    graph = build_graph(_persistence.checkpointer)
    try:
        yield
    finally:
        _persistence.close()
        _persistence = None
        graph = None


app = FastAPI(
    title="Ecommerce Router API",
    version="1.0.0",
    description=(
        "API para enrutar mensajes de un chat de ecommerce. "
        "Cada mensaje se clasifica como preventa, postventa o generica."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "salud", "description": "Estado y configuración pública de la API."},
        {"name": "chat", "description": "Clasificación y respuesta del chat ecommerce."},
        {"name": "telegram", "description": "Webhook reservado para la integración con Telegram."},
    ],
)


WEB_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tienda Horizonte · Chat</title>
  <style>
    :root { font-family: Arial, sans-serif; color: #111b21; background: #d9dbd5; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: linear-gradient(#00a884 0 128px, #d9dbd5 128px); }
    main { max-width: 980px; margin: 0 auto; padding: 24px 16px; }
    .app { height: calc(100vh - 48px); min-height: 560px; display: flex; overflow: hidden; background: #efeae2; border-radius: 8px; box-shadow: 0 8px 28px #0003; }
    .sidebar { width: 285px; background: #fff; border-right: 1px solid #d1d7db; }
    .side-header, .chat-header { height: 64px; display: flex; align-items: center; padding: 10px 16px; background: #f0f2f5; }
    .avatar { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 50%; background: #00a884; color: #fff; font-weight: bold; }
    .side-title { margin-left: 12px; font-weight: 700; }
    .side-content { padding: 20px 16px; color: #667781; font-size: 13px; }
    .side-content button { margin-top: 12px; }
    .chat { flex: 1; min-width: 0; display: flex; flex-direction: column; }
    .chat-header { background: #f0f2f5; border-bottom: 1px solid #d1d7db; }
    .chat-title { margin-left: 12px; line-height: 1.25; }
    .chat-title strong { display: block; }
    .status { color: #667781; font-size: 12px; }
    .messages { flex: 1; overflow-y: auto; padding: 24px 7%; background-color: #efeae2; background-image: radial-gradient(#d8d0c4 1px, transparent 1px); background-size: 18px 18px; }
    .welcome { max-width: 480px; margin: 0 auto 18px; padding: 9px 12px; border-radius: 7px; background: #fff3c4; color: #54656f; text-align: center; font-size: 12px; }
    .bubble { max-width: 78%; margin: 7px 0; padding: 8px 10px 6px; border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere; box-shadow: 0 1px 1px #0001; }
    .bubble.user { margin-left: auto; background: #d9fdd3; border-top-right-radius: 2px; }
    .bubble.bot { margin-right: auto; background: #fff; border-top-left-radius: 2px; }
    .meta { display: block; margin-top: 4px; color: #667781; font-size: 10px; text-align: right; }
    .composer { display: flex; gap: 8px; align-items: end; padding: 9px 12px; background: #f0f2f5; }
    textarea { flex: 1; min-height: 42px; max-height: 120px; resize: none; border: 0; border-radius: 9px; padding: 12px 14px; font: inherit; outline: none; }
    .send, .settings-button { border: 0; cursor: pointer; }
    .send { width: 44px; height: 42px; border-radius: 50%; background: #00a884; color: #fff; font-size: 20px; }
    .send:disabled { opacity: .55; cursor: wait; }
    .settings { display: none; padding: 12px 16px; background: #fff; border-bottom: 1px solid #d1d7db; }
    .settings.open { display: block; }
    label { display: block; margin: 7px 0 4px; color: #54656f; font-size: 12px; }
    input { width: 100%; padding: 9px; border: 1px solid #d1d7db; border-radius: 6px; font: inherit; }
    .settings-button { margin-left: auto; background: transparent; color: #54656f; font-size: 20px; }
    .small-button { padding: 7px 10px; border: 0; border-radius: 6px; background: #00a884; color: #fff; cursor: pointer; }
    @media (max-width: 700px) { body { background: #efeae2; } main { padding: 0; } .app { height: 100vh; min-height: 0; border-radius: 0; } .sidebar { display: none; } .messages { padding: 18px 4%; } .bubble { max-width: 88%; } }
  </style>
</head>
<body>
  <main>
    <section class="app">
      <aside class="sidebar">
        <div class="side-header"><div class="avatar">TH</div><div class="side-title">Tienda Horizonte</div></div>
        <div class="side-content">Chat local para consultar productos, pedidos y reclamos.<br><br><small>La API key se usa solo en esta sesión del navegador.</small><br><button class="small-button" id="clear-chat" type="button">Nuevo chat</button></div>
      </aside>
      <section class="chat">
        <header class="chat-header">
          <div class="avatar">TH</div>
          <div class="chat-title"><strong>Tienda Horizonte</strong><span class="status">en línea · asistente de tienda</span></div>
          <button class="settings-button" id="toggle-settings" type="button" title="Configuración">⚙</button>
        </header>
          <div class="settings open" id="settings">
          <label for="api-key">API key</label>
          <input id="api-key" type="password" autocomplete="off" placeholder="Pega tu API key" required>
          <label for="user-id">Usuario / hilo</label>
          <input id="user-id" value="web-local" required>
        </div>
        <div class="messages" id="messages" aria-live="polite">
          <div class="welcome">Los mensajes están protegidos por tu API key local.</div>
          <div class="bubble bot">¡Hola! Soy el asistente de Tienda Horizonte. ¿En qué puedo ayudarte?<span class="meta">ahora</span></div>
        </div>
        <form class="composer" id="chat-form">
          <textarea id="texto" rows="1" placeholder="Escribe un mensaje" required></textarea>
          <button class="send" id="enviar" type="submit" title="Enviar">➤</button>
        </form>
      </section>
    </section>
  </main>
  <script>
    const form = document.querySelector('#chat-form');
    const button = document.querySelector('#enviar');
    const messages = document.querySelector('#messages');
    const text = document.querySelector('#texto');
    const addMessage = (content, who, meta = '') => {
      const bubble = document.createElement('div');
      bubble.className = `bubble ${who}`;
      bubble.textContent = content;
      if (meta) { const stamp = document.createElement('span'); stamp.className = 'meta'; stamp.textContent = meta; bubble.appendChild(stamp); }
      messages.appendChild(bubble);
      messages.scrollTop = messages.scrollHeight;
    };
    document.querySelector('#toggle-settings').addEventListener('click', () => document.querySelector('#settings').classList.toggle('open'));
    document.querySelector('#clear-chat').addEventListener('click', () => {
      messages.innerHTML = '<div class="welcome">Nuevo hilo iniciado.</div>';
      text.value = '';
    });
    text.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      const question = text.value.trim();
      if (!question) { button.disabled = false; return; }
      addMessage(question, 'user', 'enviando');
      text.value = '';
      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': document.querySelector('#api-key').value
          },
          body: JSON.stringify({
            user_id: document.querySelector('#user-id').value,
            texto: question
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'No se pudo procesar la consulta.');
        addMessage(data.respuesta, 'bot', data.ruta || 'asistente');
      } catch (error) {
        addMessage(`Error: ${error.message}`, 'bot', 'error');
      } finally {
        button.disabled = false;
        text.focus();
      }
    });
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def web_home() -> str:
    """Interfaz web local para probar el chat."""
    return WEB_PAGE

class ChatRequest(BaseModel):
    """Mensaje de un usuario para el router."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "usuario-123",
                "texto": "¿Tienen la polera azul en talla M?",
            }
        }
    )

    user_id: str = Field(
        ...,
        description="Identificador estable del usuario, usado como thread_id de la memoria.",
        examples=["usuario-123"],
    )
    texto: str = Field(
        ...,
        min_length=1,
        description="Mensaje que se desea enrutar.",
        examples=["¿Tienen la polera azul en talla M?"],
    )


class ChatResponse(BaseModel):
    """Resultado del enrutamiento y respuesta del agente destino."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ruta": "preventa",
                "motivo": "El usuario pregunta por un producto antes de comprar.",
                "respuesta": "Soy el agente de preventa. Recibí: ¿Tienen la polera azul en talla M? Pronto podré ayudarte con productos y compras.",
            }
        }
    )

    ruta: Literal["preventa", "postventa", "generica"] = Field(
        description="Ruta elegida: preventa, postventa o generica.",
        examples=["preventa"],
    )
    motivo: str = Field(
        description="Motivo breve por el que el router eligió la ruta.",
        examples=["El usuario pregunta por un producto antes de comprar."],
    )
    respuesta: str = Field(
        description="Respuesta del agente cascarón asociado a la ruta.",
        examples=["Soy el agente de preventa. Recibí: ..."],
    )


class ErrorResponse(BaseModel):
    """Error público sin detalles internos ni secretos."""

    detail: str = Field(
        description="Descripción segura del error.",
        examples=["No se pudo procesar el mensaje en este momento."],
    )


api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Clave configurada en la variable de entorno API_KEY.",
)


@app.get("/health", tags=["salud"])
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "modelo": os.getenv("MODELO", "gemini-3.5-flash-lite"),
        "memoria": _memory_type,
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Enruta un mensaje del chat ecommerce",
    responses={
        200: {"description": "Mensaje enrutado y respondido correctamente."},
        401: {
            "description": "Falta la clave de API o no es válida.",
            "model": ErrorResponse,
        },
        422: {"description": "El body no cumple el esquema requerido."},
        502: {
            "description": "El proveedor del modelo no pudo procesar el mensaje.",
            "model": ErrorResponse,
        },
    },
)
def chat(
    request: ChatRequest,
    api_key: str | None = Security(api_key_header),
) -> ChatResponse:
    expected_api_key = os.getenv("API_KEY", "")
    if not expected_api_key or not api_key or not secrets.compare_digest(
        api_key, expected_api_key
    ):
        raise HTTPException(status_code=401, detail="Falta una clave de API válida")

    try:
        if graph is None:
            raise RuntimeError("El grafo todavía no está iniciado")
        result = graph.invoke(
            {
                "mensaje": request.texto,
                "messages": [("user", request.texto)],
            },
            config={"configurable": {"thread_id": request.user_id}},
        )
        return ChatResponse(
            ruta=result["ruta"],
            motivo=result["motivo"],
            respuesta=result["respuesta"],
        )
    except Exception:
        logger.exception("Error al procesar el chat para user_id=%s", request.user_id)
        raise HTTPException(
            status_code=502,
            detail="No se pudo procesar el mensaje en este momento.",
        )


async def _send_telegram_message(chat_id: int | str, text: str) -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN no está configurado; no se pudo responder a Telegram")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()
    except Exception:
        # No registramos la URL porque contiene el token del bot.
        logger.error("Error enviando respuesta de Telegram a chat_id=%s", chat_id)


@app.post("/telegram", include_in_schema=False, tags=["telegram"])
async def telegram(
    payload: Any = Body(...),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Procesa un Update de Telegram y responde por Bot API."""
    expected_secret = os.getenv("TELEGRAM_SECRET", "")
    if not expected_secret or not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", expected_secret
    ):
        raise HTTPException(status_code=403, detail="Secret token inválido")

    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    if not isinstance(message, dict):
        return {"ok": True}

    chat = message.get("chat", {})
    text = message.get("text")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if chat_id is None or not isinstance(text, str) or not text.strip():
        return {"ok": True}

    try:
        if graph is None:
            raise RuntimeError("El grafo todavía no está iniciado")
        result = await run_in_threadpool(
            graph.invoke,
            {
                "mensaje": text,
                "messages": [("user", text)],
            },
            config={"configurable": {"thread_id": str(chat_id)}},
        )
        logger.info(
            "Telegram chat_id=%s ruta=%s motivo=%s",
            chat_id,
            result.get("ruta"),
            result.get("motivo"),
        )
        await _send_telegram_message(chat_id, result["respuesta"])
    except Exception:
        # Telegram debe recibir 200 para no reintentar indefinidamente el Update.
        logger.exception("Error procesando Update de Telegram para chat_id=%s", chat_id)

    return {"ok": True}
