"""API HTTP del router de ecommerce."""

import logging
import os
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.router.graph import build_graph

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Ecommerce Router API",
    version="1.0.0",
    description=(
        "API para enrutar mensajes de un chat de ecommerce. "
        "Cada mensaje se clasifica como preventa, postventa o generica."
    ),
    openapi_tags=[
        {"name": "salud", "description": "Estado y configuración pública de la API."},
        {"name": "chat", "description": "Clasificación y respuesta del chat ecommerce."},
        {"name": "telegram", "description": "Webhook reservado para la integración con Telegram."},
    ],
)

# El grafo se construye una sola vez al importar la aplicación, no por request.
graph = build_graph()


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


@app.get("/health", tags=["salud"])
def health() -> dict[str, Any]:
    return {"ok": True, "modelo": os.getenv("MODELO", "gemini-3.5-flash-lite")}


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Enruta un mensaje del chat ecommerce",
    responses={
        200: {"description": "Mensaje enrutado y respondido correctamente."},
        422: {"description": "El body no cumple el esquema requerido."},
        502: {
            "description": "El proveedor del modelo no pudo procesar el mensaje.",
            "model": ErrorResponse,
        },
    },
)
def chat(request: ChatRequest) -> ChatResponse:
    try:
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


@app.post("/telegram", include_in_schema=False, tags=["telegram"])
def telegram(payload: Any) -> dict[str, bool]:
    """Endpoint reservado para el webhook de Telegram."""
    return {"ok": True}
