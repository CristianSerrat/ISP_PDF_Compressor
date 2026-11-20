"""Endpoints para herramientas modulares adicionales de PDF."""

from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
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
from app.services.pdf_extras import (
    images_to_pdf,
    merge_pdfs,
    modify_pdf_metadata,
    protect_pdf,
    read_pdf_metadata,
    rotate_pdf,
    split_pdf,
    strip_metadata_pdf,
)

router = APIRouter(prefix="/api/extras", tags=["extras"])


def check_module_enabled(module_name: str) -> None:
    """Verifica si el módulo está habilitado en la configuración."""
    if module_name not in settings.enabled_modules_set:
        raise HTTPException(
            status_code=403,
            detail=f"El módulo '{module_name}' está deshabilitado por el administrador.",
        )


# ==========================================
# 1. UNIR PDFs (MERGE)
# ==========================================
@router.post("/merge")
async def api_merge_pdfs(
    request: Request,
    files: list[UploadFile] = File(...),
):
    check_module_enabled("merge")
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Debes proporcionar al menos 2 archivos PDF para unir.")
    if len(files) > settings.MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo {settings.MAX_FILES} archivos permitidos.")

    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)
    input_paths: list[Path] = []
    total_bytes = 0
    max_bytes = settings.MAX_FILE_MB * 1024 * 1024

    try:
        for f in files:
            header = await f.read(1024)
            if not validate_pdf_magic_bytes(header):
                raise HTTPException(status_code=400, detail=f"Uno de los archivos no es un PDF válido.")
            _, temp_p = storage.create_temp_path(suffix="_merge_in.pdf")
            input_paths.append(temp_p)
            with open(temp_p, "wb") as out_f:
                out_f.write(header)
                while chunk := await f.read(65536):
                    total_bytes += len(chunk)
                    if total_bytes > (max_bytes * len(files)):
                        raise HTTPException(status_code=413, detail="El conjunto de archivos supera el límite de tamaño.")
                    out_f.write(chunk)

        token, output_path = storage.create_temp_path(suffix="_unido.pdf")
        semaphore = get_concurrency_semaphore()
        async with semaphore:
            result = await merge_pdfs(input_paths, output_path)

        await usage_repo.log_operation(
            operation="merge",
            params={"file_count": len(files)},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al unir PDFs.")

        download_name = "documentos_unidos.pdf"
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
    finally:
        for p in input_paths:
            storage.remove_file(p)


# ==========================================
# 2. DIVIDIR PDF (SPLIT)
# ==========================================
@router.post("/split")
async def api_split_pdf(
    request: Request,
    file: UploadFile = File(...),
    pages_range: str = Form(...),
):
    check_module_enabled("split")
    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)

    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_split_in.pdf")
    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            f.write(chunk)

    token, output_path = storage.create_temp_path(suffix="_dividido.pdf")
    semaphore = get_concurrency_semaphore()

    try:
        async with semaphore:
            result = await split_pdf(input_path, pages_range, output_path)

        await usage_repo.log_operation(
            operation="split",
            params={"pages_range": pages_range},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al dividir el PDF.")

        clean_orig = sanitize_filename(file.filename or "doc.pdf")
        download_name = f"dividido_{clean_orig}"
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
    finally:
        storage.remove_file(input_path)


# ==========================================
# 3. ROTAR PÁGINAS (ROTATE)
# ==========================================
@router.post("/rotate")
async def api_rotate_pdf(
    request: Request,
    file: UploadFile = File(...),
    angle: int = Form(90),
    pages_range: str = Form("all"),
):
    check_module_enabled("rotate")
    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)

    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_rotate_in.pdf")
    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            f.write(chunk)

    token, output_path = storage.create_temp_path(suffix="_rotado.pdf")
    semaphore = get_concurrency_semaphore()

    try:
        async with semaphore:
            result = await rotate_pdf(input_path, angle, pages_range, output_path)

        await usage_repo.log_operation(
            operation="rotate",
            params={"angle": angle, "pages_range": pages_range},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al rotar páginas.")

        clean_orig = sanitize_filename(file.filename or "doc.pdf")
        download_name = f"rotado_{clean_orig}"
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
    finally:
        storage.remove_file(input_path)


# ==========================================
# 4. PROTEGER CON CONTRASEÑA (PROTECT)
# ==========================================
@router.post("/protect")
async def api_protect_pdf(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
):
    check_module_enabled("protect")
    if not password or len(password.strip()) < 1:
        raise HTTPException(status_code=400, detail="Debes proporcionar una contraseña válida.")

    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)

    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_protect_in.pdf")
    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            f.write(chunk)

    token, output_path = storage.create_temp_path(suffix="_protegido.pdf")
    semaphore = get_concurrency_semaphore()

    try:
        async with semaphore:
            result = await protect_pdf(input_path, password, output_path)

        # Privacidad: NUNCA se registra la contraseña del usuario en base de datos
        await usage_repo.log_operation(
            operation="protect",
            params={"encrypted": True},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al proteger el PDF.")

        clean_orig = sanitize_filename(file.filename or "doc.pdf")
        download_name = f"protegido_{clean_orig}"
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
    finally:
        storage.remove_file(input_path)


# ==========================================
# 5. ELIMINAR METADATOS (STRIP METADATA)
# ==========================================
@router.post("/strip-metadata")
async def api_strip_metadata(
    request: Request,
    file: UploadFile = File(...),
):
    check_module_enabled("strip_metadata")
    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)

    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_strip_in.pdf")
    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            f.write(chunk)

    token, output_path = storage.create_temp_path(suffix="_limpio.pdf")
    semaphore = get_concurrency_semaphore()

    try:
        async with semaphore:
            result = await strip_metadata_pdf(input_path, output_path)

        await usage_repo.log_operation(
            operation="strip_metadata",
            params={},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al limpiar metadatos.")

        clean_orig = sanitize_filename(file.filename or "doc.pdf")
        download_name = f"sin_metadatos_{clean_orig}"
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
    finally:
        storage.remove_file(input_path)


# ==========================================
# 6. CONVERTIR IMÁGENES A PDF (IMG2PDF)
# ==========================================
@router.post("/img2pdf")
async def api_images_to_pdf(
    request: Request,
    files: list[UploadFile] = File(...),
):
    check_module_enabled("img2pdf")
    if not files:
        raise HTTPException(status_code=400, detail="Debes proporcionar al menos una imagen.")
    if len(files) > settings.MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo {settings.MAX_FILES} imágenes permitidas.")

    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)
    input_paths: list[Path] = []

    try:
        for f in files:
            header = await f.read(1024)
            fmt = validate_image_magic_bytes(header)
            if not fmt:
                raise HTTPException(status_code=400, detail=f"El archivo '{f.filename}' no es una imagen válida (PNG, JPG, WebP).")
            _, temp_p = storage.create_temp_path(suffix=f".{fmt}")
            input_paths.append(temp_p)
            with open(temp_p, "wb") as out_f:
                out_f.write(header)
                while chunk := await f.read(65536):
                    out_f.write(chunk)

        token, output_path = storage.create_temp_path(suffix="_imagenes.pdf")
        semaphore = get_concurrency_semaphore()
        async with semaphore:
            result = await images_to_pdf(input_paths, output_path)

        await usage_repo.log_operation(
            operation="img2pdf",
            params={"image_count": len(files)},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al convertir imágenes.")

        download_name = "imagenes_convertidas.pdf"
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
    finally:
        for p in input_paths:
            storage.remove_file(p)


# ==========================================
# 7. MODIFICAR METADATOS (EDIT METADATA)
# ==========================================
@router.post("/read-metadata")
async def api_read_metadata(
    file: UploadFile = File(...),
):
    """Lee y devuelve los metadatos actuales del PDF para precargar el formulario."""
    check_module_enabled("edit_metadata")
    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_read_meta.pdf")
    try:
        with open(input_path, "wb") as f:
            f.write(header)
            while chunk := await file.read(65536):
                f.write(chunk)

        metadata = read_pdf_metadata(input_path)
        return metadata
    finally:
        storage.remove_file(input_path)


@router.post("/edit-metadata")
async def api_edit_metadata(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    subject: str = Form(""),
    keywords: str = Form(""),
    creator: str = Form(""),
):
    """Modifica los metadatos del PDF conservando el contenido del documento."""
    check_module_enabled("edit_metadata")
    client_id = get_client_identifier(request, settings.LOG_CLIENT_MODE, settings.TRUST_PROXY, settings.HASH_SALT)

    header = await file.read(1024)
    if not validate_pdf_magic_bytes(header):
        raise HTTPException(status_code=400, detail="El archivo no es un documento PDF válido.")

    _, input_path = storage.create_temp_path(suffix="_edit_meta_in.pdf")
    with open(input_path, "wb") as f:
        f.write(header)
        while chunk := await file.read(65536):
            f.write(chunk)

    token, output_path = storage.create_temp_path(suffix="_meta_editado.pdf")
    semaphore = get_concurrency_semaphore()

    fields_to_update = {
        "title": title.strip(),
        "author": author.strip(),
        "subject": subject.strip(),
        "keywords": keywords.strip(),
        "creator": creator.strip(),
    }

    try:
        async with semaphore:
            result = await modify_pdf_metadata(input_path, fields_to_update, output_path)

        # Privacidad: NUNCA se registran los valores de título/autor en los logs de uso
        updated_keys = [k for k, v in fields_to_update.items() if v]
        await usage_repo.log_operation(
            operation="edit_metadata",
            params={"updated_fields": updated_keys},
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
            raise HTTPException(status_code=422, detail=result.error_message or "Error al modificar metadatos.")

        clean_orig = sanitize_filename(file.filename or "doc.pdf")
        download_name = f"metadatos_{clean_orig}"
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
    finally:
        storage.remove_file(input_path)
