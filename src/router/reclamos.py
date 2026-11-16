"""Persistencia de reclamos en Postgres con fallback controlado a memoria."""

from __future__ import annotations

import logging
import os
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


logger = logging.getLogger(__name__)
RECLAMOS_NO_DISPONIBLES = "reclamos no disponibles"
_thread_id: ContextVar[str] = ContextVar("reclamos_thread_id", default="sin-thread")


def set_thread_id(thread_id: str):
    return _thread_id.set(thread_id)


def reset_thread_id(token: object) -> None:
    _thread_id.reset(token)


def current_thread_id() -> str:
    return _thread_id.get()


class ClaimStore:
    """Interfaz mínima común para los almacenes de reclamos."""

    def create(self, numero_pedido: str, motivo: str, detalle: str, thread_id: str) -> str:
        raise NotImplementedError

    def list_all(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class MemoryClaimStore(ClaimStore):
    def __init__(self) -> None:
        self._claims: list[dict[str, Any]] = []

    def create(self, numero_pedido: str, motivo: str, detalle: str, thread_id: str) -> str:
        ticket = _new_ticket()
        self._claims.append(
            {
                "ticket": ticket,
                "numero_pedido": numero_pedido,
                "motivo": motivo,
                "detalle": detalle,
                "thread_id": thread_id,
                "creado_en": datetime.now(UTC).isoformat(),
            }
        )
        return ticket

    def list_all(self) -> list[dict[str, Any]]:
        return list(reversed(self._claims))


class PostgresClaimStore(ClaimStore):
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def setup(self) -> None:
        with self.pool.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reclamos (
                    ticket TEXT PRIMARY KEY,
                    numero_pedido TEXT NOT NULL,
                    motivo TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def create(self, numero_pedido: str, motivo: str, detalle: str, thread_id: str) -> str:
        ticket = _new_ticket()
        with self.pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO reclamos
                    (ticket, numero_pedido, motivo, detalle, thread_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (ticket, numero_pedido, motivo, detalle, thread_id),
            )
        return ticket

    def list_all(self) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT ticket, numero_pedido, motivo, detalle, thread_id, creado_en
                    FROM reclamos
                    ORDER BY creado_en DESC
                    """
                )
                return [dict(row) for row in cursor.fetchall()]


@dataclass
class ClaimResources:
    store: ClaimStore
    pool: ConnectionPool | None = None

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()


def _new_ticket() -> str:
    return f"REC-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


_store: ClaimStore = MemoryClaimStore()


def configure_claim_store(store: ClaimStore) -> None:
    global _store
    _store = store


def create_claim_store(pool: ConnectionPool | None = None) -> ClaimStore:
    """Crea la tabla usando el pool existente o devuelve memoria como fallback."""
    if pool is None:
        logger.warning("No hay pool de Postgres para reclamos; usando memoria")
        return MemoryClaimStore()
    store = PostgresClaimStore(pool)
    try:
        store.setup()
        return store
    except Exception:
        logger.exception("No se pudo crear la tabla reclamos; usando memoria")
        return MemoryClaimStore()


def create_claim_resources() -> ClaimResources:
    """Abre un pool pequeño para consultar reclamos desde scripts."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if not url:
        logger.warning("DATABASE_URL no está configurada; reclamos en memoria")
        return ClaimResources(MemoryClaimStore())
    pool = ConnectionPool(
        conninfo=url,
        min_size=1,
        max_size=1,
        open=False,
        check=ConnectionPool.check_connection,
    )
    try:
        pool.open(wait=True)
        store = create_claim_store(pool)
        return ClaimResources(store, pool)
    except Exception:
        logger.exception("No se pudo conectar para consultar reclamos; usando memoria")
        pool.close()
        return ClaimResources(MemoryClaimStore())


def crear_reclamo(numero_pedido: str, motivo: str, detalle: str) -> str:
    """Crea un reclamo en el almacén configurado y devuelve su ticket."""
    try:
        return _store.create(numero_pedido, motivo, detalle, current_thread_id())
    except Exception:
        logger.exception("No se pudo guardar el reclamo")
        return RECLAMOS_NO_DISPONIBLES
