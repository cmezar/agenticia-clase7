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
