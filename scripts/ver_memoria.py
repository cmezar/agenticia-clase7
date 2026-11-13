"""Consulta los hilos y mensajes guardados por el checkpointer de Postgres."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.graph import create_persistence  # noqa: E402


def _thread_id(config: dict) -> str:
    return str(config.get("configurable", {}).get("thread_id", ""))


def _contenido(message: object) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
        role = message.get("type", message.get("role", "mensaje"))
    else:
        content = getattr(message, "content", "")
        role = getattr(message, "type", message.__class__.__name__)
    return f"{role}: {content}"


def main() -> None:
    load_dotenv(ROOT / ".env")
    persistence = create_persistence()
    try:
        if persistence.memory_type != "postgres":
            print("No hay memoria Postgres disponible; no se pueden consultar hilos persistidos.")
            return

        checkpointer = persistence.checkpointer
        thread_filter = sys.argv[1] if len(sys.argv) > 1 else None
        if thread_filter:
            latest = checkpointer.get_tuple(
                {"configurable": {"thread_id": thread_filter}}
            )
            if latest is None:
                print(f"No existe el hilo: {thread_filter}")
                return
            messages = latest.checkpoint.get("channel_values", {}).get("messages", [])
            print(f"Hilo: {thread_filter}")
            for message in messages:
                print(_contenido(message))
            return

        resumen: dict[str, dict[str, object]] = defaultdict(
            lambda: {"checkpoints": 0, "ultimo": ""}
        )
        for item in checkpointer.list(None):
            thread_id = _thread_id(item.config)
            if not thread_id:
                continue
            resumen[thread_id]["checkpoints"] = int(resumen[thread_id]["checkpoints"]) + 1
            timestamp = item.checkpoint.get("ts", "")
            if timestamp > str(resumen[thread_id]["ultimo"]):
                resumen[thread_id]["ultimo"] = timestamp

        if not resumen:
            print("No hay hilos guardados.")
            return
        print(f"{'Hilo':<30} {'Checkpoints':>12}  Último")
        print("-" * 70)
        for thread_id, data in sorted(resumen.items()):
            print(f"{thread_id:<30} {data['checkpoints']:>12}  {data['ultimo']}")
    finally:
        persistence.close()


if __name__ == "__main__":
    main()
