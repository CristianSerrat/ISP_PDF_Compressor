"""Endpoint de verificación de estado del servicio."""

import shutil
from fastapi import APIRouter
from app.config import settings
from app.services.ghostscript import find_ghostscript_binary

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Devuelve el estado operativo de la aplicación y dependencias locales."""
    settings.setup_directories()
    gs_path = find_ghostscript_binary()
    total, used, free = shutil.disk_usage(str(settings.DATA_DIR))

    return {
        "status": "ok",
        "ghostscript_available": gs_path is not None,
        "ghostscript_path": gs_path,
        "disk_free_mb": round(free / (1024 * 1024), 2),
        "data_dir": str(settings.DATA_DIR),
        "tmp_dir": str(settings.TMP_DIR),
        "enabled_modules": list(settings.enabled_modules_set),
    }
