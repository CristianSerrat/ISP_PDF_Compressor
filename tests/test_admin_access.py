"""Tests para el control de acceso con clave de administrador, sesiones firmadas y exportación CSV."""

import asyncio
import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.core.security import clear_failed_logins
from app.database.usage_repo import usage_repo
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_admin_settings():
    """Restaura la configuración de administrador antes de cada test."""
    settings.ADMIN_PASSWORD = "test-admin-pass"
    settings.ADMIN_ALLOWED_NETWORKS = ""  # Sin filtro IP por defecto para probar clave
    clear_failed_logins("127.0.0.1")
    yield


def test_admin_stats_page_loads_html():
    """La página /admin/stats debe cargar para mostrar la pantalla de clave."""
    response = client.get("/admin/stats")
    assert response.status_code == 200
    assert "Acceso Administrador" in response.text


def test_admin_api_stats_unauthorized_without_cookie():
    """El endpoint /admin/api/stats debe devolver 401 si no hay sesión iniciada."""
    response = client.get("/admin/api/stats")
    assert response.status_code == 401
    assert "Se requiere autenticación" in response.json()["detail"]


def test_admin_login_incorrect_password():
    """Fallo de autenticación con clave incorrecta."""
    response = client.post("/admin/api/login", data={"password": "clave_equivocada"})
    assert response.status_code == 401
    assert "incorrecta" in response.json()["detail"]


def test_admin_login_success_and_access():
    """Inicio de sesión exitoso, obtención de cookie y acceso a estadísticas."""
    # 1. Login exitoso
    resp_login = client.post("/admin/api/login", data={"password": "test-admin-pass"})
    assert resp_login.status_code == 200
    assert "admin_session" in resp_login.cookies

    cookie = resp_login.cookies["admin_session"]

    # 2. Acceso a /admin/api/stats con la cookie
    resp_stats = client.get("/admin/api/stats", cookies={"admin_session": cookie})
    assert resp_stats.status_code == 200
    data = resp_stats.json()
    assert "total_operations" in data

    # 3. Descarga de CSV con la cookie
    resp_csv = client.get("/admin/export.csv", cookies={"admin_session": cookie})
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers.get("content-type", "")

    # 4. Logout
    resp_logout = client.post("/admin/api/logout")
    assert resp_logout.status_code == 200

    # 5. Intentar acceder tras logout sin cookie válida
    resp_after = client.get("/admin/api/stats")
    assert resp_after.status_code == 401


def test_admin_login_rate_limit():
    """Bloqueo temporal por fuerza bruta tras 5 intentos fallidos consecutivos."""
    # 5 intentos fallidos
    for _ in range(5):
        resp = client.post("/admin/api/login", data={"password": "wrong"})
        assert resp.status_code == 401

    # El 6to intento debe recibir 429 Too Many Requests
    blocked_resp = client.post("/admin/api/login", data={"password": "wrong"})
    assert blocked_resp.status_code == 429
    assert "Demasiados intentos fallidos" in blocked_resp.json()["detail"]


def test_admin_access_with_optional_network_restriction():
    """Si se define ADMIN_ALLOWED_NETWORKS, se combina con la verificación de red."""
    settings.ADMIN_ALLOWED_NETWORKS = "10.0.0.0/24"
    # Acceso desde localhost (127.0.0.1) queda bloqueado por red
    resp = client.get("/admin/stats")
    assert resp.status_code == 403
