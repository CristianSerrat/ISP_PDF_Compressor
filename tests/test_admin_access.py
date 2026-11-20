"""Tests para el control de acceso por red, estadísticas y exportación CSV del panel /admin."""

import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.database.usage_repo import usage_repo
from app.main import app

client = TestClient(app)


def test_admin_access_allowed_localhost():
    """El acceso desde 127.0.0.1 debe ser permitido con código 200."""
    response = client.get("/admin/stats")
    assert response.status_code == 200
    assert "Panel de Estadísticas" in response.text


def test_admin_api_stats_localhost():
    """El endpoint de datos JSON /admin/api/stats debe responder correctamente."""
    response = client.get("/admin/api/stats?days=30")
    assert response.status_code == 200
    data = response.json()
    assert "total_operations" in data
    assert "saved_pct" in data
    assert "by_day" in data
    assert "hourly" in data
    assert "top_clients" in data


def test_admin_access_forbidden_external_ip():
    """Si la IP del cliente no pertenece a ADMIN_ALLOWED_NETWORKS, debe devolver 403."""
    # TestClient permite especificar el cliente origen
    ext_client = TestClient(app, client=("192.168.1.100", 50000))
    response = ext_client.get("/admin/stats")
    assert response.status_code == 403
    assert "Acceso restringido" in response.json()["detail"]


def test_admin_access_with_trust_proxy_header():
    """Verifica el comportamiento de X-Forwarded-For cuando TRUST_PROXY está activo."""
    # 1. Con TRUST_PROXY=False (por defecto), la cabecera X-Forwarded-For se ignora
    settings.TRUST_PROXY = False
    resp_ignored = client.get("/admin/stats", headers={"x-forwarded-for": "10.200.0.1"})
    assert resp_ignored.status_code == 200  # Pasa porque client.host sigue siendo 127.0.0.1

    # 2. Con TRUST_PROXY=True, la cabecera X-Forwarded-For tiene prioridad
    settings.TRUST_PROXY = True
    try:
        # IP externa no autorizada en X-Forwarded-For
        resp_blocked = client.get("/admin/stats", headers={"x-forwarded-for": "10.200.0.1"})
        assert resp_blocked.status_code == 403

        # IP autorizada en X-Forwarded-For
        resp_allowed = client.get("/admin/stats", headers={"x-forwarded-for": "127.0.0.1"})
        assert resp_allowed.status_code == 200
    finally:
        settings.TRUST_PROXY = False


def test_admin_export_csv(sample_pdf_bytes):
    """Verifica la generación y formato del archivo CSV de registro de uso."""
    # Registrar una operación de prueba
    import asyncio
    asyncio.run(
        usage_repo.log_operation(
            operation="compress",
            params={"preset": "ebook"},
            pages=5,
            original_size=2000,
            final_size=1000,
            duration_ms=250,
            status="ok",
            error_code=None,
            client_id="test_client_hash",
        )
    )

    response = client.get("/admin/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert "registro_uso_pdf.csv" in response.headers.get("content-disposition", "")

    csv_lines = response.text.strip().splitlines()
    assert len(csv_lines) >= 2  # Cabecera + al menos 1 fila

    header = csv_lines[0]
    expected_cols = [
        "timestamp",
        "operation",
        "params",
        "pages",
        "original_size_bytes",
        "final_size_bytes",
        "duration_ms",
        "status",
        "error_code",
        "client_id",
    ]
    for col in expected_cols:
        assert col in header

    # Verificación de privacidad: la fila contiene el client_id y la operación
    assert "compress" in response.text
    assert "test_client_hash" in response.text
