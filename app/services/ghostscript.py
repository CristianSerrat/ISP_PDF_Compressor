"""Servicio de compresión de PDF utilizando Ghostscript mediante subprocess seguro."""

import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pypdf
from app.config import settings


@dataclass
class CompressionResult:
    success: bool
    original_size: int
    final_size: int
    saved_bytes: int
    saved_pct: float
    returned_original: bool
    pages: int
    duration_ms: int
    output_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None


def find_ghostscript_binary() -> str | None:
    """Busca el ejecutable de Ghostscript disponible en el sistema."""
    for binary in ["gs", "ghostscript", "gswin64c", "gswin32c"]:
        path = shutil.which(binary)
        if path:
            return path
    # Comprobar rutas habituales en macOS si PATH no lo incluye directamente
    for mac_path in ["/opt/homebrew/bin/gs", "/usr/local/bin/gs"]:
        if os.path.exists(mac_path) and os.access(mac_path, os.X_OK):
            return mac_path
    return None


def inspect_pdf_pages(file_path: Path) -> int:
    """Obtiene el número de páginas de un PDF y verifica si está protegido o dañado."""
    try:
        reader = pypdf.PdfReader(str(file_path))
        if reader.is_encrypted:
            # Si tiene contraseña vacía se puede leer, de lo contrario está protegido
            try:
                res = reader.decrypt("")
                if res == 0:  # PasswordType.NOT_DECRYPTED
                    raise ValueError("ENCRYPTED_PDF")
            except (pypdf.errors.FileNotDecryptedError, pypdf.errors.WrongPasswordError):
                raise ValueError("ENCRYPTED_PDF")
        return len(reader.pages)
    except pypdf.errors.FileNotDecryptedError:
        raise ValueError("ENCRYPTED_PDF")
    except ValueError as ve:
        if str(ve) == "ENCRYPTED_PDF":
            raise
        raise ValueError("CORRUPT_PDF")
    except Exception:
        raise ValueError("CORRUPT_PDF")


def _run_ghostscript_sync(
    gs_bin: str,
    input_path: Path,
    output_path: Path,
    preset: str,
    custom_dpi: int | None,
    custom_jpeg_quality: int | None,
    timeout: int,
) -> None:
    """
    Ejecuta Ghostscript utilizando argumentos en lista (shell=False estricto)
    con compatibilidad PDF 1.4 y re-muestreo bicúbico de imágenes.
    """
    # Base command arguments
    args = [
        gs_bin,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dFastWebView=true",
    ]

    # Configuración según preset
    if preset == "screen":
        args.append("-dPDFSETTINGS=/screen")  # ~72 dpi
    elif preset == "printer":
        args.append("-dPDFSETTINGS=/printer")  # ~300 dpi
    elif preset == "custom" and custom_dpi:
        dpi = max(36, min(600, custom_dpi))
        args.extend([
            "-dPDFSETTINGS=/default",
            "-dColorImageDownsampleType=/Bicubic",
            f"-dColorImageResolution={dpi}",
            "-dGrayImageDownsampleType=/Bicubic",
            f"-dGrayImageResolution={dpi}",
            "-dMonoImageDownsampleType=/Bicubic",
            f"-dMonoImageResolution={dpi}",
        ])
        if custom_jpeg_quality:
            # Ghostscript no tiene un flag directo único para JPEG Q, pero se ajusta el DCTEncode
            quality = max(10, min(100, custom_jpeg_quality))
            args.append(f"-dAutoFilterColorImages=false")
            args.append(f"-dColorImageFilter=/DCTEncode")
    else:
        # Por defecto: "ebook" (~150 dpi)
        args.append("-dPDFSETTINGS=/ebook")

    args.extend([
        f"-sOutputFile={output_path}",
        str(input_path),
    ])

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"GS_ERROR: {result.stderr.strip()[:200]}")


async def compress_pdf(
    input_path: Path,
    output_path: Path,
    preset: str = "ebook",
    custom_dpi: int | None = None,
    custom_jpeg_quality: int | None = None,
) -> CompressionResult:
    """
    Comprime un archivo PDF.
    Si el resultado supera en tamaño al original, se devuelve el original y se avisa.
    """
    start_time = time.perf_counter()
    original_size = input_path.stat().st_size

    # 1. Comprobar páginas e integridad previa
    try:
        pages = inspect_pdf_pages(input_path)
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        code = str(e)
        msg = "El PDF está protegido con contraseña." if code == "ENCRYPTED_PDF" else "El archivo PDF está dañado o es inválido."
        return CompressionResult(
            success=False,
            original_size=original_size,
            final_size=0,
            saved_bytes=0,
            saved_pct=0.0,
            returned_original=False,
            pages=0,
            duration_ms=duration_ms,
            error_code=code,
            error_message=msg,
        )

    # 2. Localizar binario de Ghostscript
    gs_bin = find_ghostscript_binary()
    if not gs_bin:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return CompressionResult(
            success=False,
            original_size=original_size,
            final_size=0,
            saved_bytes=0,
            saved_pct=0.0,
            returned_original=False,
            pages=pages,
            duration_ms=duration_ms,
            error_code="GS_NOT_INSTALLED",
            error_message="Ghostscript no se encuentra instalado en el servidor.",
        )

    # 3. Ejecutar Ghostscript en thread asíncrono
    try:
        await asyncio.to_thread(
            _run_ghostscript_sync,
            gs_bin=gs_bin,
            input_path=input_path,
            output_path=output_path,
            preset=preset,
            custom_dpi=custom_dpi,
            custom_jpeg_quality=custom_jpeg_quality,
            timeout=settings.GS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return CompressionResult(
            success=False,
            original_size=original_size,
            final_size=0,
            saved_bytes=0,
            saved_pct=0.0,
            returned_original=False,
            pages=pages,
            duration_ms=duration_ms,
            error_code="TIMEOUT",
            error_message=f"El proceso excedió el tiempo máximo de {settings.GS_TIMEOUT} segundos.",
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return CompressionResult(
            success=False,
            original_size=original_size,
            final_size=0,
            saved_bytes=0,
            saved_pct=0.0,
            returned_original=False,
            pages=pages,
            duration_ms=duration_ms,
            error_code="GS_EXECUTION_ERROR",
            error_message="Ocurrió un error interno durante la compresión del PDF.",
        )

    # 4. Validar resultado generado
    if not output_path.exists() or output_path.stat().st_size == 0:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return CompressionResult(
            success=False,
            original_size=original_size,
            final_size=0,
            saved_bytes=0,
            saved_pct=0.0,
            returned_original=False,
            pages=pages,
            duration_ms=duration_ms,
            error_code="EMPTY_OUTPUT",
            error_message="No se pudo generar el archivo comprimido.",
        )

    compressed_size = output_path.stat().st_size
    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # Regla: si el comprimido es más pesado que el original, devolvemos el original
    if compressed_size >= original_size:
        # Reemplazamos el output con el original
        shutil.copy2(input_path, output_path)
        return CompressionResult(
            success=True,
            original_size=original_size,
            final_size=original_size,
            saved_bytes=0,
            saved_pct=0.0,
            returned_original=True,
            pages=pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )

    saved_bytes = original_size - compressed_size
    saved_pct = round((saved_bytes / original_size) * 100, 2)

    return CompressionResult(
        success=True,
        original_size=original_size,
        final_size=compressed_size,
        saved_bytes=saved_bytes,
        saved_pct=saved_pct,
        returned_original=False,
        pages=pages,
        duration_ms=duration_ms,
        output_path=output_path,
    )
