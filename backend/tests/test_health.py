from fastapi.testclient import TestClient

from app.main import app


def test_liveness_is_independent_of_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
