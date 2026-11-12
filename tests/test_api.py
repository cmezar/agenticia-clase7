"""Pruebas de autenticación y contrato del endpoint /chat."""

import importlib

from fastapi.testclient import TestClient


app_module = importlib.import_module("api.app")


def test_chat_sin_clave_responde_401(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "clave-de-prueba")

    response = TestClient(app_module.app).post(
        "/chat",
        json={"user_id": "usuario-123", "texto": "hola"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Falta una clave de API válida"}


def test_chat_con_clave_responde_200(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "clave-de-prueba")

    class FakeGraph:
        def invoke(self, *_args, **_kwargs) -> dict[str, str]:
            return {
                "ruta": "generica",
                "motivo": "Es un saludo.",
                "respuesta": "Hola.",
            }

    monkeypatch.setattr(app_module, "graph", FakeGraph())
    response = TestClient(app_module.app).post(
        "/chat",
        headers={"X-API-Key": "clave-de-prueba"},
        json={"user_id": "usuario-123", "texto": "hola"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ruta": "generica",
        "motivo": "Es un saludo.",
        "respuesta": "Hola.",
    }
