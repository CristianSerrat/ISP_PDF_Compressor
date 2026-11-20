"""Tests para el endpoint de estado /health."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ghostscript_available" in data
    assert "disk_free_mb" in data
    assert "enabled_modules" in data
    assert "compress" in data["enabled_modules"]
