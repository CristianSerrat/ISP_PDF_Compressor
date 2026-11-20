"""Rutas de administración y métricas de uso protegidas por clave de administrador y sesión."""

import hmac
from pathlib import Path
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from app.config import settings
from app.core.security import (
    check_login_rate_limit,
    clear_failed_logins,
    create_admin_session_token,
    extract_client_ip,
    record_failed_login,
)
from app.database.usage_repo import usage_repo
from app.dependencies import verify_admin_access, verify_admin_network

router = APIRouter(prefix="/admin", tags=["admin"])

STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/stats", include_in_schema=False)
async def admin_stats_page(request: Request):
    """
    Sirve la interfaz web del panel de administración.
    La interfaz evalúa en cliente si se requiere mostrar el formulario de acceso.
    """
    verify_admin_network(request)
    admin_html = STATIC_DIR / "admin.html"
    if admin_html.exists():
        return FileResponse(admin_html)
    return {"message": "Panel de administración activo. Interfaz no disponible."}


@router.post("/api/login")
async def admin_login(
    request: Request,
    response: Response,
    password: str = Form(...),
):
    """Autentica al administrador con la clave maestra y genera una cookie de sesión firmada."""
    verify_admin_network(request)
    client_ip = extract_client_ip(request, settings.TRUST_PROXY)

    # 1. Protección contra fuerza bruta
    if not check_login_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Por favor, espera 5 minutos antes de volver a intentarlo.",
        )

    # 2. Validación de contraseña con tiempo constante
    if not hmac.compare_digest(password.encode("utf-8"), settings.ADMIN_PASSWORD.encode("utf-8")):
        record_failed_login(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clave de administrador incorrecta.",
        )

    # 3. Éxito: limpiar intentos y crear sesión
    clear_failed_logins(client_ip)
    token = create_admin_session_token(
        secret_key=settings.SECRET_KEY,
        expires_hours=settings.ADMIN_SESSION_HOURS,
    )

    max_age = settings.ADMIN_SESSION_HOURS * 3600
    response.set_cookie(
        key="admin_session",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )
    return {"status": "ok", "token": token, "expires_in_hours": settings.ADMIN_SESSION_HOURS}


@router.post("/api/logout")
async def admin_logout(response: Response):
    """Cierra la sesión de administrador eliminando la cookie de sesión."""
    response.delete_cookie(key="admin_session")
    return {"status": "ok"}


@router.get("/api/stats", dependencies=[Depends(verify_admin_access)])
async def get_admin_stats(days: int = Query(default=30, ge=1, le=365)):
    """Retorna las métricas agregadas de uso para el período solicitado."""
    return await usage_repo.get_stats(days=days)


@router.get("/export.csv", dependencies=[Depends(verify_admin_access)])
async def export_usage_csv(
    start_date: str | None = Query(default=None, description="Fecha de inicio (YYYY-MM-DD)"),
    end_date: str | None = Query(default=None, description="Fecha de fin (YYYY-MM-DD)"),
):
    """Exporta el registro estructurado de operaciones a formato CSV."""
    csv_content = await usage_repo.export_csv(start_date=start_date, end_date=end_date)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="registro_uso_pdf.csv"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )
