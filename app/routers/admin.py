"""Rutas de administración y métricas de uso con control de acceso por red."""

from pathlib import Path
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from app.database.usage_repo import usage_repo
from app.dependencies import verify_admin_network

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin_network)],
)

STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/stats", include_in_schema=False)
async def admin_stats_page():
    """Sirve la interfaz web del panel de administración."""
    admin_html = STATIC_DIR / "admin.html"
    if admin_html.exists():
        return FileResponse(admin_html)
    return {"message": "Panel de administración activo. Interfaz no disponible."}


@router.get("/api/stats")
async def get_admin_stats(days: int = Query(default=30, ge=1, le=365)):
    """Retorna las métricas agregadas de uso para el período solicitado."""
    return await usage_repo.get_stats(days=days)


@router.get("/export.csv")
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
