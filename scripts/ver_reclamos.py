"""Lista los reclamos guardados en Postgres."""

from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.reclamos import create_claim_resources  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    resources = create_claim_resources()
    try:
        reclamos = resources.store.list_all()
        if not reclamos:
            print("No hay reclamos guardados.")
            return
        for reclamo in reclamos:
            print(
                f"{reclamo['ticket']} | pedido: {reclamo['numero_pedido']} | "
                f"motivo: {reclamo['motivo']} | creado: {reclamo['creado_en']} | "
                f"detalle: {reclamo['detalle']}"
            )
    finally:
        resources.close()


if __name__ == "__main__":
    main()
