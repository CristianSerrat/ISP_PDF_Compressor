"""Endpoints para compresión individual y por lotes de archivos PDF."""

import zipfile
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from app.config import settings
from app.core.concurrency import get_concurrency_semaphore
from app.core.security import (
    get_client_identifier,
    sanitize_filename,
    validate_pdf_magic_bytes,
)
from app.core.storage import storage
from app.database.usage_repo import usage_repo
from app.services.ghostscript import compress_pdf

router = APIRouter(prefix="/api/compress", tags=["compress"])


@router.post("")
async def compress_single_pdf(
    request: Request,
    file: UploadFile = File(...),
    preset: str = Form("ebook"),
    custom_dpi: int | None = Form(None),
    custom_jpeg_quality: int | None = Form(None),
):
    """Comprime un único archivo PDF según el preset o parámetros personalizados."""
    if "compress" not in settings.enabled_modules_set:
        raise HTTPException(status_code=403, detail="El módulo de compresión está deshabilitado.")

    client_id = get_client_identifier(
        request,
        settings.LOG_CLIENT_MODE,
        settings.TRUST_PROXY,
        settings.HASH_SALT,
    )

    # 1. Leer cabecera para verificar magic bytes
    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        await usage_repo.log_operation(
            operation="compress",
            params={"preset": preset},
            pages=0,
            original_size=len(header),
            final_size=0,
            duration_ms=0,
            status="error",
            error_code="INVALID_PDF_HEADER",
            client_id=client_id,
        )
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    # 2. Guardar archivo temporal de entrada con UUID
    _, input_path = storage.create_temp_path(suffix="_input.pdf")
    max_bytes = settings.MAX_FILE_MB * 1024 * 1024
    total_bytes = len(header)

    try:
        with open(input_path, "wb") as f:
            f.write(header)
            while chunk := await file.read(65536):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el tamaño máximo permitido ({settings.MAX_FILE_MB} MB).",
                    )
                f.write(chunk)
    except HTTPException:
        storage.remove_file(input_path)
        await usage_repo.log_operation(
            operation="compress",
            params={"preset": preset},
            pages=0,
            original_size=total_bytes,
            final_size=0,
            duration_ms=0,
            status="error",
            error_code="FILE_TOO_LARGE",
            client_id=client_id,
        )
        raise

    # 3. Preparar ruta temporal de salida
    token, output_path = storage.create_temp_path(suffix="_compressed.pdf")

    # 4. Procesar con control de concurrencia
    semaphore = get_concurrency_semaphore()
    async with semaphore:
        result = await compress_pdf(
            input_path=input_path,
            output_path=output_path,
            preset=preset,
            custom_dpi=custom_dpi,
            custom_jpeg_quality=custom_jpeg_quality,
        )

    # El archivo de entrada ya no es necesario
    storage.remove_file(input_path)

    # 5. Registrar en log de uso (sin nombres ni rutas)
    log_params = {"preset": preset}
    if preset == "custom":
        log_params["dpi"] = custom_dpi
        log_params["jpeg_q"] = custom_jpeg_quality

    await usage_repo.log_operation(
        operation="compress",
        params=log_params,
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
            detail=result.error_message or "Error durante la compresión.",
        )

    # 6. Registrar para descarga segura
    clean_original = sanitize_filename(file.filename or "documento.pdf")
    download_name = f"comprimido_{clean_original}"
    storage.register_download(token, output_path, download_name)

    return {
        "token": token,
        "download_url": f"/api/download/{token}",
        "filename": download_name,
        "original_size": result.original_size,
        "final_size": result.final_size,
        "saved_bytes": result.saved_bytes,
        "saved_pct": result.saved_pct,
        "returned_original": result.returned_original,
        "pages": result.pages,
        "duration_ms": result.duration_ms,
    }


@router.post("/batch")
async def compress_batch_pdfs(
    request: Request,
    files: list[UploadFile] = File(...),
    preset: str = Form("ebook"),
    custom_dpi: int | None = Form(None),
    custom_jpeg_quality: int | None = Form(None),
):
    """Comprime múltiples archivos PDF por lotes y genera descargas individuales y un ZIP."""
    if "compress" not in settings.enabled_modules_set:
        raise HTTPException(status_code=403, detail="El módulo de compresión está deshabilitado.")

    if len(files) > settings.MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Se superó el número máximo de archivos por lote ({settings.MAX_FILES}).",
        )

    client_id = get_client_identifier(
        request,
        settings.LOG_CLIENT_MODE,
        settings.TRUST_PROXY,
        settings.HASH_SALT,
    )

    processed_items = []
    zip_entries: list[tuple[str, str]] = []  # (download_name, file_path_str)
    semaphore = get_concurrency_semaphore()
    max_bytes = settings.MAX_FILE_MB * 1024 * 1024

    for file in files:
        header = await file.read(1024)
        if not validate_pdf_magic_bytes(header):
            processed_items.append({
                "filename": sanitize_filename(file.filename or "doc.pdf"),
                "success": False,
                "error": "Archivo no es un PDF válido",
            })
            continue

        _, input_path = storage.create_temp_path(suffix="_input.pdf")
        total_bytes = len(header)
        is_too_large = False

        with open(input_path, "wb") as f:
            f.write(header)
            while chunk := await file.read(65536):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    is_too_large = True
                    break
                f.write(chunk)

        if is_too_large:
            storage.remove_file(input_path)
            processed_items.append({
                "filename": sanitize_filename(file.filename or "doc.pdf"),
                "success": False,
                "error": f"Supera {settings.MAX_FILE_MB} MB",
            })
            continue

        token, output_path = storage.create_temp_path(suffix="_compressed.pdf")

        async with semaphore:
            result = await compress_pdf(
                input_path=input_path,
                output_path=output_path,
                preset=preset,
                custom_dpi=custom_dpi,
                custom_jpeg_quality=custom_jpeg_quality,
            )

        storage.remove_file(input_path)

        await usage_repo.log_operation(
            operation="compress",
            params={"preset": preset, "batch": True},
            pages=result.pages,
            original_size=result.original_size,
            final_size=result.final_size,
            duration_ms=result.duration_ms,
            status="ok" if result.success else "error",
            error_code=result.error_code,
            client_id=client_id,
        )

        clean_original = sanitize_filename(file.filename or "documento.pdf")
        download_name = f"comprimido_{clean_original}"

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
                "saved_bytes": result.saved_bytes,
                "saved_pct": result.saved_pct,
                "returned_original": result.returned_original,
                "pages": result.pages,
            })
        else:
            storage.remove_file(output_path)
            processed_items.append({
                "filename": clean_original,
                "success": False,
                "error": result.error_message or "Error en compresión",
            })

    # Si hay archivos exitosos, creamos el ZIP de lote
    zip_token = None
    zip_url = None
    if zip_entries:
        z_token, zip_path = storage.create_temp_path(suffix="_lote.zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arcname, filepath in zip_entries:
                zf.write(filepath, arcname=arcname)
        storage.register_download(z_token, zip_path, "comprimidos_lote.zip", content_type="application/zip")
        zip_token = z_token
        zip_url = f"/api/download/{z_token}"

    return {
        "items": processed_items,
        "zip_token": zip_token,
        "zip_url": zip_url,
    }
