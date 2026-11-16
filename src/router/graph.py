"""Grafo LangGraph que enruta mensajes del ecommerce."""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.message import add_messages
from langgraph.graph import END, START, StateGraph
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .prompts import (
    AGENTE_POSTVENTA_PROMPT,
    AGENTE_PREVENTA_PROMPT,
    ROUTER_PROMPT,
    RESPUESTA_GENERICA_PROMPT,
)
from .reclamos import (
    ClaimStore,
    MemoryClaimStore,
    configure_claim_store,
    create_claim_store,
    reset_thread_id,
    set_thread_id,
)
from .tools import (
    buscar_productos,
    mejores_ofertas,
    ver_producto,
    crear_reclamo,
    estado_pedido,
    politica,
)


logger = logging.getLogger(__name__)

TIENDA_CONTEXT = (Path(__file__).resolve().parents[2] / "data" / "tienda.md").read_text(
    encoding="utf-8"
)
GENERICA_FALLBACK = "Este chat es para ayudarte con nuestra tienda y sus productos."


def _contenido_mensaje(message: object) -> str:
    """Convierte contenido textual o bloques de contenido en texto plano."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ).strip()
    return str(content).strip()


def _historial_visible(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Conserva la conversación visible y excluye turnos internos de herramientas."""
    conversacion = [
        message
        for message in messages
        if getattr(message, "type", "") != "tool"
        and not getattr(message, "tool_calls", None)
    ]
    while conversacion and getattr(conversacion[0], "type", "") != "human":
        conversacion.pop(0)
    return conversacion


def _historial_para_router(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Devuelve los últimos cuatro turnos visibles para clasificar la ruta."""
    return _historial_visible(messages)[-4:]


class Decision(BaseModel):
    """Decisión estructurada del router."""

    ruta: Literal["preventa", "postventa", "generica"] = Field(
        description="A qué agente va el mensaje."
    )
    motivo: str = Field(description="Una frase: por qué esa ruta.")


class RouterState(TypedDict, total=False):
    mensaje: str
    ruta: Literal["preventa", "postventa", "generica"]
    motivo: str
    respuesta: str
    messages: Annotated[list[BaseMessage], add_messages]


@dataclass
class PersistenceResources:
    """Checkpointer y recursos que deben vivir mientras vive el proceso."""

    checkpointer: BaseCheckpointSaver
    memory_type: Literal["ram", "postgres"]
    pool: ConnectionPool | None = None
    claim_store: ClaimStore | None = None

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()


def _database_url() -> str:
    """Devuelve DATABASE_URL en el formato aceptado por psycopg."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


def create_persistence() -> PersistenceResources:
    """Abre Postgres si está disponible y degrada a RAM si no lo está."""
    database_url = _database_url()
    if not database_url:
        logger.info("DATABASE_URL no está configurada; usando MemorySaver (ram)")
        logger.warning("No hay Postgres para reclamos; se guardarán en memoria")
        return PersistenceResources(MemorySaver(), "ram", claim_store=MemoryClaimStore())

    pool = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=2,
        open=False,
        check=ConnectionPool.check_connection,
    )
    try:
        pool.open(wait=True)
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
        claim_store = create_claim_store(pool)
        logger.info("Memoria persistente habilitada con Postgres")
        return PersistenceResources(checkpointer, "postgres", pool, claim_store)
    except Exception:
        logger.exception("No se pudo iniciar Postgres; usando MemorySaver (ram)")
        pool.close()
        return PersistenceResources(MemorySaver(), "ram", claim_store=MemoryClaimStore())


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Construye el grafo compilado con memoria por thread_id."""
    router_llm = None
    generica_llm = None
    preventa_agent = None
    postventa_agent = None

    def router(state: RouterState) -> dict:
        nonlocal router_llm
        if router_llm is None:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("Falta GOOGLE_API_KEY en .env")
            llm = ChatGoogleGenerativeAI(
                model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
                google_api_key=api_key,
            )
            router_llm = llm.with_structured_output(Decision)
        historial = _historial_para_router(state.get("messages", []))
        ruta_anterior = state.get("ruta")
        contexto_ruta = (
            f"\nLa ruta anterior fue: {ruta_anterior}. "
            "Las respuestas breves del usuario continúan esa ruta, salvo que haya una intención clara de cambiar."
            if ruta_anterior
            else ""
        )
        decision = router_llm.invoke(
            [SystemMessage(content=ROUTER_PROMPT + contexto_ruta), *historial]
        )
        return {"ruta": decision.ruta, "motivo": decision.motivo}

    def agente_preventa(state: RouterState) -> dict:
        nonlocal preventa_agent
        if preventa_agent is None:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("Falta GOOGLE_API_KEY en .env")
            modelo = ChatGoogleGenerativeAI(
                model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
                google_api_key=api_key,
            )
            preventa_agent = create_agent(
                model=modelo,
                tools=[buscar_productos, ver_producto, mejores_ofertas],
                system_prompt=AGENTE_PREVENTA_PROMPT,
            )

        historial = state.get("messages", [])
        resultado = preventa_agent.invoke({"messages": historial})
        mensajes_agente = resultado.get("messages", [])
        mensajes_nuevos = (
            mensajes_agente[len(historial) :]
            if len(mensajes_agente) >= len(historial)
            else list(mensajes_agente)
        )
        mensaje_final = mensajes_agente[-1] if mensajes_agente else AIMessage(content="")
        respuesta = _contenido_mensaje(mensaje_final)
        if not mensajes_nuevos or mensajes_nuevos[-1] is not mensaje_final:
            mensajes_nuevos.append(mensaje_final)
        return {"respuesta": respuesta, "messages": mensajes_nuevos}

    def agente_postventa(
        state: RouterState,
        config: RunnableConfig | None = None,
    ) -> dict:
        nonlocal postventa_agent
        if postventa_agent is None:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("Falta GOOGLE_API_KEY en .env")
            modelo = ChatGoogleGenerativeAI(
                model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
                google_api_key=api_key,
            )
            postventa_agent = create_agent(
                model=modelo,
                tools=[estado_pedido, politica, crear_reclamo],
                system_prompt=AGENTE_POSTVENTA_PROMPT,
            )

        thread_id = str((config or {}).get("configurable", {}).get("thread_id", "sin-thread"))
        token = set_thread_id(thread_id)
        try:
            historial = _historial_visible(state.get("messages", []))
            resultado = postventa_agent.invoke({"messages": historial})
            mensajes_agente = resultado.get("messages", [])
            mensajes_nuevos = (
                mensajes_agente[len(historial) :]
                if len(mensajes_agente) >= len(historial)
                else list(mensajes_agente)
            )
            mensaje_final = (
                mensajes_agente[-1] if mensajes_agente else AIMessage(content="")
            )
            respuesta = _contenido_mensaje(mensaje_final)
            if not mensajes_nuevos or mensajes_nuevos[-1] is not mensaje_final:
                mensajes_nuevos.append(mensaje_final)
            return {"respuesta": respuesta, "messages": mensajes_nuevos}
        finally:
            reset_thread_id(token)

    def respuesta_generica(state: RouterState) -> dict:
        nonlocal generica_llm
        try:
            if generica_llm is None:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise RuntimeError("Falta GOOGLE_API_KEY en .env")
                generica_llm = ChatGoogleGenerativeAI(
                    model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
                    google_api_key=api_key,
                )
            system_prompt = f"{RESPUESTA_GENERICA_PROMPT}\n\nCONTEXTO DE LA TIENDA:\n{TIENDA_CONTEXT}"
            historial = state.get("messages", [])
            respuesta_modelo = generica_llm.invoke(
                [SystemMessage(content=system_prompt), *historial]
            )
            respuesta = _contenido_mensaje(respuesta_modelo)
            if not respuesta:
                raise RuntimeError("El modelo devolvió una respuesta vacía")
            respuesta = "\n".join(respuesta.splitlines()[:3])
            respuesta_modelo = AIMessage(content=respuesta)
        except Exception:
            logger.exception("Falló el modelo de la ruta generica; usando fallback")
            respuesta = GENERICA_FALLBACK
            respuesta_modelo = AIMessage(content=respuesta)

        return {"respuesta": respuesta, "messages": [respuesta_modelo]}

    def seleccionar_ruta(state: RouterState) -> str:
        return state["ruta"]

    builder = StateGraph(RouterState)
    builder.add_node("router", router)
    builder.add_node("agente_preventa", agente_preventa)
    builder.add_node("agente_postventa", agente_postventa)
    builder.add_node("respuesta_generica", respuesta_generica)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        seleccionar_ruta,
        {
            "preventa": "agente_preventa",
            "postventa": "agente_postventa",
            "generica": "respuesta_generica",
        },
    )
    builder.add_edge("agente_preventa", END)
    builder.add_edge("agente_postventa", END)
    builder.add_edge("respuesta_generica", END)
    return builder.compile(checkpointer=checkpointer or MemorySaver())
