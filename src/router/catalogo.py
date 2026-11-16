"""Acceso de solo lectura al catálogo de productos."""

from __future__ import annotations

import logging
import json
import os
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row


logger = logging.getLogger(__name__)
CATALOGO_NO_DISPONIBLE = "catálogo no disponible"


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


def consultar_catalogo(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]] | str:
    """Ejecuta un SELECT parametrizado y cierra la conexión al terminar."""
    consulta = sql.strip()
    if not consulta.lower().startswith("select") or ";" in consulta:
        raise ValueError("El catálogo solo admite una consulta SELECT")

    database_url = _database_url()
    if not database_url:
        logger.warning("DATABASE_URL no está configurada; catálogo no disponible")
        return CATALOGO_NO_DISPONIBLE

    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(consulta, tuple(params))
                return [dict(row) for row in cursor.fetchall()]
    except Exception:
        logger.exception("No se pudo consultar el catálogo")
        return CATALOGO_NO_DISPONIBLE


def serializar_filas(filas: list[dict[str, Any]] | str) -> str:
    """Convierte filas del catálogo a JSON legible por el modelo."""
    if isinstance(filas, str):
        return filas
    return json.dumps(filas, ensure_ascii=False, default=str)
