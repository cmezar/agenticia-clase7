"""Consulta rápida del catálogo desde la terminal."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.catalogo import consultar_catalogo  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    consulta = " ".join(sys.argv[1:]).strip()
    if consulta:
        filas = consultar_catalogo(
            """
            SELECT sku_id, nombre, precio_internet, rating
            FROM catalogo.productos_unicos
            WHERE LOWER(nombre) LIKE LOWER(%s)
            ORDER BY rating IS NULL, rating DESC, nombre
            LIMIT 10
            """,
            [f"%{consulta}%"],
        )
        if isinstance(filas, str):
            print(filas)
            return
        for fila in filas:
            print(
                f"{fila['sku_id']} | {fila['nombre']} | "
                f"${fila['precio_internet']:,} | rating: {fila['rating'] or 'sin dato'}"
            )
        return

    filas = consultar_catalogo(
        """
        SELECT categoria, COUNT(*) AS cantidad
        FROM catalogo.productos_unicos
        GROUP BY categoria
        ORDER BY categoria
        """
    )
    if isinstance(filas, str):
        print(filas)
        return
    for fila in filas:
        print(f"{fila['categoria']}: {fila['cantidad']}")


if __name__ == "__main__":
    main()
