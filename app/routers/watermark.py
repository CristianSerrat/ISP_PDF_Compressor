"""Endpoints para aplicación de marcas de agua y previsualización interactiva."""

import zipfile
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from app.config import settings
from app.core.concurrency import get_concurrency_semaphore
from app.core.security import (
    get_client_identifier,
    sanitize_filename,
    validate_image_magic_bytes,
    validate_pdf_magic_bytes,
)
from app.core.storage import storage
from app.database.usage_repo import usage_repo
from app.services.watermark import apply_watermark, generate_first_page_preview

router = APIRouter(prefix="/api/watermark", tags=["watermark"])


@router.post("")
async def watermark_single_pdf(
    request: Request,
    file: UploadFile = File(...),
    wm_type: str = Form("text"),
    wm_text: str | None = Form(None),
    wm_file: UploadFile | None = File(None),
    position: str = Form("center"),
    opacity: float = Form(0.3),
    rotation: float = Form(45.0),
    scale: float = Form(1.0),
    pages_range: str = Form("all"),
):
    """Estampa una marca de agua (texto, imagen o PDF) en un documento PDF."""
    if "watermark" not in settings.enabled_modules_set:
        raise HTTPException(status_code=403, detail="El módulo de marca de agua está deshabilitado.")

    client_id = get_client_identifier(
        request,
        settings.LOG_CLIENT_MODE,
        settings.TRUST_PROXY,
        settings.HASH_SALT,
    )

    # 1. Validar PDF objetivo
    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo objetivo no es un PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_wm_input.pdf")
    max_bytes = settings.MAX_FILE_MB * 1024 * 1024
    total_bytes = len(header)

    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                storage.remove_file(input_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_FILE_MB} MB).",
                )
            f.write(chunk)

    # 2. Validar archivo de marca si aplica (imagen o PDF)
    wm_file_bytes = None
    if wm_type in ("image", "pdf"):
        if not wm_file:
            storage.remove_file(input_path)
            raise HTTPException(status_code=400, detail=f"Debes proporcionar un archivo para la marca de agua ({wm_type}).")
        
        wm_file_bytes = await wm_file.read()
        if wm_type == "image":
            img_format = validate_image_magic_bytes(wm_file_bytes)
            if not img_format:
                storage.remove_file(input_path)
                raise HTTPException(status_code=400, detail="La imagen de marca de agua no tiene un formato válido (PNG, JPEG, WebP).")
        elif wm_type == "pdf":
            if not validate_pdf_magic_bytes(wm_file_bytes):
                storage.remove_file(input_path)
                raise HTTPException(status_code=400, detail="El archivo de marca de agua no es un PDF válido.")
    elif wm_type == "text":
        if not wm_text or not wm_text.strip():
            wm_text = "CONFIDENCIAL"

    # 3. Procesar marca de agua
    token, output_path = storage.create_temp_path(suffix="_watermarked.pdf")
    semaphore = get_concurrency_semaphore()

    async with semaphore:
        result = await apply_watermark(
            input_path=input_path,
            output_path=output_path,
            wm_type=wm_type,
            wm_text=wm_text,
            wm_file_bytes=wm_file_bytes,
            position=position,
            opacity=opacity,
            rotation=rotation,
            scale=scale,
            pages_range=pages_range,
        )

    storage.remove_file(input_path)

    # 4. Registrar en log de uso (anónimo, sin textos ni nombres)
    await usage_repo.log_operation(
        operation="watermark",
        params={
            "wm_type": wm_type,
            "position": position,
            "opacity": opacity,
            "rotation": rotation,
            "scale": scale,
            "pages_range": pages_range,
        },
        pages=result.pages,
        original_size=result.original_size,
        final_size=result.final_size,
        duration_ms=result.duration_ms,
        status="ok" if result.success else "error",
        error_code=result.error_code,
        client_id=client_id,
    )

    if not result.success:
        storage.remove_file(output_path)
        raise HTTPException(
            status_code=422 if result.error_code in ("ENCRYPTED_PDF", "CORRUPT_PDF") else 500,
            detail=result.error_message or "Error al estampar marca de agua.",
        )

    # 5. Registrar para descarga
    clean_original = sanitize_filename(file.filename or "documento.pdf")
    download_name = f"marca_agua_{clean_original}"
    storage.register_download(token, output_path, download_name)

    return {
        "token": token,
        "download_url": f"/api/download/{token}",
        "filename": download_name,
        "original_size": result.original_size,
        "final_size": result.final_size,
        "pages": result.pages,
        "duration_ms": result.duration_ms,
    }


@router.post("/batch")
async def watermark_batch_pdfs(
    request: Request,
    files: list[UploadFile] = File(...),
    wm_type: str = Form("text"),
    wm_text: str | None = Form(None),
    wm_file: UploadFile | None = File(None),
    position: str = Form("center"),
    opacity: float = Form(0.3),
    rotation: float = Form(45.0),
    scale: float = Form(1.0),
    pages_range: str = Form("all"),
):
    """Estampa marca de agua por lotes sobre múltiples archivos PDF."""
    if "watermark" not in settings.enabled_modules_set:
        raise HTTPException(status_code=403, detail="El módulo de marca de agua está deshabilitado.")

    if len(files) > settings.MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Se superó el límite de archivos por lote ({settings.MAX_FILES}).",
        )

    client_id = get_client_identifier(
        request,
        settings.LOG_CLIENT_MODE,
        settings.TRUST_PROXY,
        settings.HASH_SALT,
    )

    wm_file_bytes = None
    if wm_type in ("image", "pdf") and wm_file:
        wm_file_bytes = await wm_file.read()

    processed_items = []
    zip_entries: list[tuple[str, str]] = []
    semaphore = get_concurrency_semaphore()

    for file in files:
        header = await file.read(1024)
        if not validate_pdf_magic_bytes(header):
            processed_items.append({
                "filename": sanitize_filename(file.filename or "doc.pdf"),
                "success": False,
                "error": "No es un PDF válido",
            })
            continue

        _, input_path = storage.create_temp_path(suffix="_wm_input.pdf")
        with open(input_path, "wb") as f:
            f.write(header)
            while chunk := await file.read(65536):
                f.write(chunk)

        token, output_path = storage.create_temp_path(suffix="_wm_out.pdf")

        async with semaphore:
            result = await apply_watermark(
                input_path=input_path,
                output_path=output_path,
                wm_type=wm_type,
                wm_text=wm_text,
                wm_file_bytes=wm_file_bytes,
                position=position,
                opacity=opacity,
                rotation=rotation,
                scale=scale,
                pages_range=pages_range,
            )

        storage.remove_file(input_path)

        await usage_repo.log_operation(
            operation="watermark",
            params={"wm_type": wm_type, "batch": True, "position": position},
            pages=result.pages,
            original_size=result.original_size,
            final_size=result.final_size,
            duration_ms=result.duration_ms,
            status="ok" if result.success else "error",
            error_code=result.error_code,
            client_id=client_id,
        )

        clean_original = sanitize_filename(file.filename or "documento.pdf")
        download_name = f"marca_agua_{clean_original}"

        if result.success and output_path.exists():
            storage.register_download(token, output_path, download_name)
            zip_entries.append((download_name, str(output_path)))
            processed_items.append({
                "filename": download_name,
                "success": True,
                "token": token,
                "download_url": f"/api/download/{token}",
                "original_size": result.original_size,
                "final_size": result.final_size,
                "pages": result.pages,
            })
        else:
            storage.remove_file(output_path)
            processed_items.append({
                "filename": clean_original,
                "success": False,
                "error": result.error_message or "Error en procesado",
            })

    zip_token = None
    zip_url = None
    if zip_entries:
        z_token, zip_path = storage.create_temp_path(suffix="_marcas_lote.zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arcname, filepath in zip_entries:
                zf.write(filepath, arcname=arcname)
        storage.register_download(z_token, zip_path, "marcas_agua_lote.zip", content_type="application/zip")
        zip_token = z_token
        zip_url = f"/api/download/{z_token}"

    return {
        "items": processed_items,
        "zip_token": zip_token,
        "zip_url": zip_url,
    }


@router.post("/preview")
async def preview_watermark_first_page(
    file: UploadFile = File(...),
    wm_type: str = Form("text"),
    wm_text: str | None = Form(None),
    wm_file: UploadFile | None = File(None),
    position: str = Form("center"),
    opacity: float = Form(0.3),
    rotation: float = Form(45.0),
    scale: float = Form(1.0),
):
    """
    Genera una previsualización interactiva de la primera página estampada
    y la retorna como un stream PDF de 1 página para renderizado nativo.
    """
    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_wm_preview.pdf")
    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            f.write(chunk)

    wm_file_bytes = None
    if wm_type in ("image", "pdf") and wm_file:
        wm_file_bytes = await wm_file.read()

    try:
        preview_pdf_bytes = await generate_first_page_preview(
            input_path=input_path,
            wm_type=wm_type,
            wm_text=wm_text,
            wm_file_bytes=wm_file_bytes,
            position=position,
            opacity=opacity,
            rotation=rotation,
            scale=scale,
        )
    finally:
        storage.remove_file(input_path)

    return Response(
        content=preview_pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=preview.pdf"},
    )
