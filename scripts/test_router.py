"""Evalúa el router contra los casos de tests/casos_router.json."""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.graph import build_graph  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    with (ROOT / "tests" / "casos_router.json").open(encoding="utf-8") as file:
        casos = json.load(file)

    graph = build_graph()
    resultados: list[dict[str, str]] = []
    print(f"{'Mensaje':<48} {'Esperado':<10} {'Obtenido':<10} {'Resultado':<10} Motivo")
    print("-" * 130)

    for index, caso in enumerate(casos, start=1):
        resultado = graph.invoke(
            {"mensaje": caso["mensaje"], "messages": [("user", caso["mensaje"])]},
            config={"configurable": {"thread_id": f"test-router-{index}"}},
        )
        obtenido = resultado["ruta"]
        acierto = obtenido == caso["esperado"]
        resultados.append(
            {
                "mensaje": caso["mensaje"],
                "esperado": caso["esperado"],
                "obtenido": obtenido,
                "motivo": resultado.get("motivo", ""),
            }
        )
        mensaje = caso["mensaje"][:46]
        print(
            f"{mensaje:<48} {caso['esperado']:<10} {obtenido:<10} "
            f"{'✔' if acierto else '✘':<10} {resultado.get('motivo', '')}"
        )

    aciertos = sum(item["esperado"] == item["obtenido"] for item in resultados)
    total = len(resultados)
    print(f"\nAciertos: {aciertos}/{total} ({aciertos / total:.1%})")
    fallados = [item for item in resultados if item["esperado"] != item["obtenido"]]
    if fallados:
        print("Fallados:")
        for item in fallados:
            print(f"- {item['mensaje']} -> esperado {item['esperado']}, obtenido {item['obtenido']}")


if __name__ == "__main__":
    main()
