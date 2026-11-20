"""Endpoint para descarga segura de archivos con borrado inmediato."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.core.storage import storage

router = APIRouter(prefix="/api", tags=["download"])


@router.get("/download/{token}")
async def download_file(token: str):
    """
    Descarga el archivo asociado al token generado y lo borra físicamente
    del disco tras completar la respuesta.
    """
    item = storage.consume_download(token)
    if not item or not item.file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="El archivo solicitado no existe o ha expirado. Por favor, vuelve a procesarlo."
        )

    return FileResponse(
        path=str(item.file_path),
        filename=item.download_filename,
        media_type=item.content_type,
        background=BackgroundTask(storage.remove_file, item.file_path),
    )
