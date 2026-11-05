"""Punto de entrada para ejecutar agentes desde la raíz del proyecto."""

import argparse
import importlib
import sys
from pathlib import Path

from dotenv import load_dotenv


def _agentes_disponibles() -> list[str]:
    src = Path(__file__).parent / "src"
    return sorted(
        item.name
        for item in src.iterdir()
        if item.is_dir() and item.name != "__pycache__" and (item / "graph.py").exists()
    ) if src.exists() else []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ejecuta un agente LangGraph.")
    parser.add_argument("agente", help="Nombre de la carpeta dentro de src/")
    parser.add_argument("mensaje", nargs="?", help="Mensaje inicial del agente")
    parser.add_argument("--mensaje", dest="mensaje_flag", help="Mensaje inicial alternativo")
    parser.add_argument("--thread-id", default="cli", help="Identificador de memoria del hilo")
    parser.add_argument("--saltos", action="store_true", help="Muestra los nodos visitados")
    parser.add_argument("--diagrama", action="store_true", help="Muestra el grafo como Mermaid")
    return parser


def _imprimir_tool_calls(update: object) -> None:
    """Muestra tool calls encontrados en una actualización del grafo."""
    if not isinstance(update, dict):
        return
    for message in update.get("messages", []):
        for call in getattr(message, "tool_calls", []) or []:
            name = call.get("name", "desconocida")
            args = str(call.get("args", {}))[:200]
            print(f"   tool: {name}({args})")


def main() -> None:
    load_dotenv()
    args = _parser().parse_args()
    if args.saltos and args.diagrama:
        print("Error: --saltos y --diagrama son mutuamente excluyentes.", file=sys.stderr)
        raise SystemExit(2)

    try:
        module = importlib.import_module(f"src.{args.agente}.graph")
    except ModuleNotFoundError as error:
        if error.name == f"src.{args.agente}" or error.name == f"src.{args.agente}.graph":
            disponibles = ", ".join(_agentes_disponibles()) or "ninguno"
            print(f"Agente no encontrado. Disponibles: {disponibles}", file=sys.stderr)
            raise SystemExit(2) from error
        raise

    graph = module.build_graph()
    if args.diagrama:
        print(graph.get_graph().draw_mermaid())
        return

    mensaje = args.mensaje_flag if args.mensaje_flag is not None else args.mensaje
    if mensaje is None:
        mensaje = input("Mensaje: ")
    input_dict = {"mensaje": mensaje, "messages": [("user", mensaje)]}
    config = {"configurable": {"thread_id": args.thread_id}}

    if args.saltos:
        final = None
        for chunk in graph.stream(input_dict, config=config, stream_mode="updates"):
            final = chunk
            for node_name, update in chunk.items():
                print(f"-> nodo: {node_name}")
                if node_name == "router" and isinstance(update, dict):
                    print(f"   ruta: {update.get('ruta')}")
                    print(f"   motivo: {update.get('motivo')}")
                _imprimir_tool_calls(update)
        print("OK")
        return

    result = graph.invoke(input_dict, config=config)
    print(result)


if __name__ == "__main__":
    main()
