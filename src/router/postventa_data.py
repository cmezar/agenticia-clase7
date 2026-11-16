"""Datos locales de pedidos y políticas de postventa."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PEDIDOS_PATH = ROOT / "data" / "pedidos.json"
POLITICAS_PATH = ROOT / "data" / "politicas.md"


def buscar_pedido(numero: str) -> dict | None:
    pedidos = json.loads(PEDIDOS_PATH.read_text(encoding="utf-8"))
    numero_normalizado = str(numero).strip().lower()
    return next(
        (pedido for pedido in pedidos if pedido["numero"].lower() == numero_normalizado),
        None,
    )


def leer_politica(tema: str) -> str:
    contenido = POLITICAS_PATH.read_text(encoding="utf-8")
    secciones = contenido.split("\n# ")
    buscado = _normalizar(tema.strip())
    equivalencias = {
        "devolucion": "devoluciones",
        "cambio": "cambios",
        "garantia": "garantia",
    }
    buscado = equivalencias.get(buscado, buscado)
    for seccion in secciones:
        titulo, _, texto = seccion.partition("\n")
        if _normalizar(titulo.lstrip("# ").strip()) == buscado:
            return f"{titulo.lstrip('# ').strip()}\n{texto.strip()}"
    return "No existe esa sección de política. Las secciones disponibles son devoluciones, cambios y garantía."


def _normalizar(texto: str) -> str:
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(caracter) != "Mn"
    )
