from fastapi.testclient import TestClient

from api.app import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "modelo": "gemini-3.5-flash-lite"}
