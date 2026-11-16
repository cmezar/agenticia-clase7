"""Herramientas de consulta del catálogo para el agente de preventa."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

from .a2a_redes import preguntar_redes
from .catalogo import CATALOGO_NO_DISPONIBLE, consultar_catalogo, serializar_filas
from .postventa_data import buscar_pedido, leer_politica
from .reclamos import crear_reclamo as guardar_reclamo, current_thread_id


logger = logging.getLogger(__name__)


@tool
def buscar_productos(
    consulta: str,
    categoria: str | None = None,
    marca: str | None = None,
    precio_max: int | None = None,
) -> str:
    """Busca hasta cinco productos cuyo nombre contenga todas las palabras de la consulta."""
    palabras = [palabra.lower() for palabra in consulta.split() if palabra.strip()]
    if not palabras:
        return "No encontré productos porque falta una consulta."

    condiciones = [" AND ".join("LOWER(nombre) LIKE %s" for _ in palabras)]
    params: list[Any] = [f"%{palabra}%" for palabra in palabras]
    if categoria:
        condiciones.append("LOWER(categoria) = LOWER(%s)")
        params.append(categoria)
    if marca:
        condiciones.append(
            "(LOWER(COALESCE(marca, '')) LIKE LOWER(%s) OR LOWER(nombre) LIKE LOWER(%s))"
        )
        params.extend([f"%{marca}%", f"%{marca}%"])
    if precio_max is not None:
        condiciones.append("precio_internet <= %s")
        params.append(precio_max)

    sql = """
        SELECT sku_id, nombre, marca, precio_internet, descuento_pct, rating
        FROM catalogo.productos_unicos
        WHERE {where}
        ORDER BY rating IS NULL, rating DESC, nombre
        LIMIT 5
    """.format(where=" AND ".join(condiciones))
    return serializar_filas(consultar_catalogo(sql, params))


@tool
def ver_producto(sku_id: str) -> str:
    """Devuelve todos los datos del producto identificado por su SKU."""
    sql = """
        SELECT sku_id, nombre, marca, categoria, subcategoria, precio_normal,
               precio_internet, descuento_pct, rating, tienda_oficial, link, imagen
        FROM catalogo.productos_unicos
        WHERE sku_id = %s
        LIMIT 1
    """
    resultado = consultar_catalogo(sql, [sku_id])
    if resultado == CATALOGO_NO_DISPONIBLE:
        return resultado
    if not resultado:
        return "No encontré un producto con ese SKU."
    return serializar_filas(resultado)


@tool
def mejores_ofertas(categoria: str | None = None, limite: int = 5) -> str:
    """Devuelve los productos con mayor descuento, opcionalmente filtrados por categoría."""
    limite_seguro = max(1, min(int(limite), 5))
    condiciones: list[str] = []
    params: list[Any] = []
    if categoria:
        condiciones.append("LOWER(categoria) = LOWER(%s)")
        params.append(categoria)

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    sql = f"""
        SELECT sku_id, nombre, marca, categoria, subcategoria, precio_normal,
               precio_internet, descuento_pct, rating, tienda_oficial, link, imagen
        FROM catalogo.productos_unicos
        {where}
        ORDER BY descuento_pct IS NULL, descuento_pct DESC, rating IS NULL, rating DESC
        LIMIT %s
    """
    params.append(limite_seguro)
    return serializar_filas(consultar_catalogo(sql, params))


@tool
def consultar_redes(tema: str) -> str:
    """Consulta qué se comenta en redes y noticias sobre una marca o producto."""
    try:
        respuesta = asyncio.run(preguntar_redes(tema, current_thread_id()))
        if not respuesta:
            return "el agente de redes no está disponible"
        return respuesta[:1500]
    except Exception:
        logger.exception("No se pudo consultar el agente de redes por A2A")
        return "el agente de redes no está disponible"


@tool
def estado_pedido(numero: str) -> str:
    """Devuelve los datos del pedido indicado o informa que no existe."""
    pedido = buscar_pedido(numero)
    if pedido is None:
        return "no existe"
    return serializar_filas([pedido])


@tool
def politica(tema: str) -> str:
    """Devuelve la sección solicitada de las políticas de postventa."""
    return leer_politica(tema)


@tool
def crear_reclamo(numero_pedido: str, motivo: str, detalle: str) -> str:
    """Guarda un reclamo y devuelve su número de ticket."""
    return guardar_reclamo(numero_pedido, motivo, detalle)
