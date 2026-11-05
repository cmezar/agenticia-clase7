"""Prueba de evaluación del router con los casos JSON."""

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.router.graph import build_graph


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
with (ROOT / "tests" / "casos_router.json").open(encoding="utf-8") as file:
    CASOS = json.load(file)

_resultados: list[bool] = []


@pytest.mark.parametrize("indice,caso", list(enumerate(CASOS)))
def test_router_acierta_al_menos_13_de_15(indice: int, caso: dict[str, str]) -> None:
    graph = build_graph()
    resultado = graph.invoke(
        {"mensaje": caso["mensaje"], "messages": [("user", caso["mensaje"])]},
        config={"configurable": {"thread_id": f"pytest-router-{indice}"}},
    )
    _resultados.append(resultado["ruta"] == caso["esperado"])

    # Se permite variabilidad del modelo: la aserción global se hace al terminar
    # el último caso parametrizado.
    if indice == len(CASOS) - 1:
        aciertos = sum(_resultados)
        assert aciertos >= 13, f"El router acertó {aciertos}/15; se requieren al menos 13"
