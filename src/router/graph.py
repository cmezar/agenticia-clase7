"""Grafo LangGraph que enruta mensajes del ecommerce."""

import os
from typing import Annotated, Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .prompts import (
    AGENTE_POSTVENTA_PROMPT,
    AGENTE_PREVENTA_PROMPT,
    ROUTER_PROMPT,
    RESPUESTA_GENERICA_PROMPT,
)


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


def build_graph():
    """Construye el grafo compilado con memoria por thread_id."""
    router_llm = None

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
        decision = router_llm.invoke(
            [
                SystemMessage(content=ROUTER_PROMPT),
                HumanMessage(content=state["mensaje"]),
            ]
        )
        return {"ruta": decision.ruta, "motivo": decision.motivo}

    def agente_preventa(state: RouterState) -> dict:
        _ = AGENTE_PREVENTA_PROMPT
        return {
            "respuesta": (
                f"Soy el agente de preventa. Recibí: {state['mensaje']}. "
                "Pronto podré ayudarte con productos y compras."
            )
        }

    def agente_postventa(state: RouterState) -> dict:
        _ = AGENTE_POSTVENTA_PROMPT
        return {
            "respuesta": (
                f"Soy el agente de postventa. Recibí: {state['mensaje']}. "
                "Pronto podré ayudarte con tu pedido."
            )
        }

    def respuesta_generica(state: RouterState) -> dict:
        _ = RESPUESTA_GENERICA_PROMPT
        return {
            "respuesta": "Este chat es para ayudarte con nuestra tienda y sus productos."
        }

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
    return builder.compile(checkpointer=MemorySaver())
