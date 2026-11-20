"""Servicios modulares para herramientas adicionales de PDF (unir, dividir, rotar, proteger, limpiar metadatos, img2pdf)."""

import asyncio
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pypdf
from PIL import Image
from app.services.ghostscript import inspect_pdf_pages
from app.services.watermark import parse_page_ranges


@dataclass
class ExtraResult:
    success: bool
    original_size: int
    final_size: int
    pages: int
    duration_ms: int
    output_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None


# ==========================================
# 1. UNIR PDFs (MERGE)
# ==========================================
def _merge_pdfs_sync(input_paths: list[Path], output_path: Path) -> tuple[int, int]:
    """Une múltiples archivos PDF en el orden recibido."""
    writer = pypdf.PdfWriter()
    total_pages = 0
    total_orig_size = 0

    for path in input_paths:
        total_orig_size += path.stat().st_size
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            try:
                res = reader.decrypt("")
                if res == 0:
                    raise ValueError("ENCRYPTED_PDF")
            except Exception:
                raise ValueError("ENCRYPTED_PDF")

        for page in reader.pages:
            writer.add_page(page)
            total_pages += 1

    with open(output_path, "wb") as f_out:
        writer.write(f_out)

    return total_pages, total_orig_size


async def merge_pdfs(input_paths: list[Path], output_path: Path) -> ExtraResult:
    start_time = time.perf_counter()
    try:
        pages, orig_size = await asyncio.to_thread(_merge_pdfs_sync, input_paths, output_path)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        final_size = output_path.stat().st_size if output_path.exists() else 0
        return ExtraResult(
            success=True,
            original_size=orig_size,
            final_size=final_size,
            pages=pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )
    except ValueError as ve:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        code = str(ve)
        return ExtraResult(
            success=False,
            original_size=sum(p.stat().st_size for p in input_paths if p.exists()),
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code=code,
            error_message="Uno de los archivos PDF está protegido con contraseña o dañado.",
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=sum(p.stat().st_size for p in input_paths if p.exists()),
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code="MERGE_ERROR",
            error_message=f"Error al unir los PDFs: {str(ex)}",
        )


# ==========================================
# 2. DIVIDIR PDF (SPLIT)
# ==========================================
def _split_pdf_sync(input_path: Path, pages_range: str, output_path: Path) -> int:
    """Extrae las páginas seleccionadas de un PDF."""
    reader = pypdf.PdfReader(str(input_path))
    writer = pypdf.PdfWriter()
    total_pages = len(reader.pages)
    selected_indices = parse_page_ranges(pages_range, total_pages)

    if not selected_indices:
        raise ValueError("NO_PAGES_SELECTED")

    # Mantener el orden numérico de las páginas seleccionadas
    for idx in sorted(selected_indices):
        writer.add_page(reader.pages[idx])

    with open(output_path, "wb") as f_out:
        writer.write(f_out)

    return len(selected_indices)


async def split_pdf(input_path: Path, pages_range: str, output_path: Path) -> ExtraResult:
    start_time = time.perf_counter()
    orig_size = input_path.stat().st_size
    try:
        inspect_pdf_pages(input_path)
        extracted_pages = await asyncio.to_thread(_split_pdf_sync, input_path, pages_range, output_path)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        final_size = output_path.stat().st_size if output_path.exists() else 0
        return ExtraResult(
            success=True,
            original_size=orig_size,
            final_size=final_size,
            pages=extracted_pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )
    except ValueError as ve:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        code = str(ve)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code=code,
            error_message="El PDF está protegido con contraseña o el rango de páginas es inválido.",
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code="SPLIT_ERROR",
            error_message=f"Error al dividir el PDF: {str(ex)}",
        )


# ==========================================
# 3. ROTAR PÁGINAS (ROTATE)
# ==========================================
def _rotate_pdf_sync(input_path: Path, angle: int, pages_range: str, output_path: Path) -> int:
    """Rota las páginas especificadas (90, 180 o 270 grados en sentido horario)."""
    reader = pypdf.PdfReader(str(input_path))
    writer = pypdf.PdfWriter()
    total_pages = len(reader.pages)
    target_pages = parse_page_ranges(pages_range, total_pages)

    # Normalizar ángulo a múltiplos de 90
    valid_angle = angle % 360
    if valid_angle not in (90, 180, 270):
        valid_angle = 90

    for idx, in_page in enumerate(reader.pages):
        page = writer.add_page(in_page)
        if idx in target_pages:
            page.rotate(valid_angle)

    with open(output_path, "wb") as f_out:
        writer.write(f_out)

    return total_pages


async def rotate_pdf(input_path: Path, angle: int, pages_range: str, output_path: Path) -> ExtraResult:
    start_time = time.perf_counter()
    orig_size = input_path.stat().st_size
    try:
        pages = inspect_pdf_pages(input_path)
        await asyncio.to_thread(_rotate_pdf_sync, input_path, angle, pages_range, output_path)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        final_size = output_path.stat().st_size if output_path.exists() else 0
        return ExtraResult(
            success=True,
            original_size=orig_size,
            final_size=final_size,
            pages=pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )
    except ValueError as ve:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code=str(ve),
            error_message="El PDF está protegido con contraseña o es inválido.",
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code="ROTATE_ERROR",
            error_message=f"Error al rotar páginas: {str(ex)}",
        )


# ==========================================
# 4. PROTEGER CON CONTRASEÑA (PROTECT)
# ==========================================
def _protect_pdf_sync(input_path: Path, password: str, output_path: Path) -> int:
    """Cifra el PDF con contraseña de usuario utilizando AES-256 o cifrado estándar de 128 bits."""
    reader = pypdf.PdfReader(str(input_path))
    writer = pypdf.PdfWriter(clone_from=reader)
    try:
        writer.encrypt(user_password=password, algorithm="AES-256")
    except Exception:
        # Cifrado estándar compatible nativo sin dependencias externas adicionales
        writer.encrypt(user_password=password)

    with open(output_path, "wb") as f_out:
        writer.write(f_out)

    return len(reader.pages)


async def protect_pdf(input_path: Path, password: str, output_path: Path) -> ExtraResult:
    start_time = time.perf_counter()
    orig_size = input_path.stat().st_size
    try:
        pages = inspect_pdf_pages(input_path)
        await asyncio.to_thread(_protect_pdf_sync, input_path, password, output_path)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        final_size = output_path.stat().st_size if output_path.exists() else 0
        return ExtraResult(
            success=True,
            original_size=orig_size,
            final_size=final_size,
            pages=pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )
    except ValueError as ve:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code=str(ve),
            error_message="El PDF ya está protegido o es inválido.",
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code="PROTECT_ERROR",
            error_message=f"Error al cifrar el PDF: {str(ex)}",
        )


# ==========================================
# 5. ELIMINAR METADATOS (STRIP METADATA)
# ==========================================
def _strip_metadata_sync(input_path: Path, output_path: Path) -> int:
    """Elimina toda información de metadatos (autor, creador, productor, fechas, XMP)."""
    reader = pypdf.PdfReader(str(input_path))
    writer = pypdf.PdfWriter()

    for in_page in reader.pages:
        writer.add_page(in_page)

    # Vaciar diccionario de información y metadatos
    writer.add_metadata({})

    with open(output_path, "wb") as f_out:
        writer.write(f_out)

    return len(reader.pages)


async def strip_metadata_pdf(input_path: Path, output_path: Path) -> ExtraResult:
    start_time = time.perf_counter()
    orig_size = input_path.stat().st_size
    try:
        pages = inspect_pdf_pages(input_path)
        await asyncio.to_thread(_strip_metadata_sync, input_path, output_path)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        final_size = output_path.stat().st_size if output_path.exists() else 0
        return ExtraResult(
            success=True,
            original_size=orig_size,
            final_size=final_size,
            pages=pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )
    except ValueError as ve:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code=str(ve),
            error_message="El PDF está protegido con contraseña o es inválido.",
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code="STRIP_ERROR",
            error_message=f"Error al limpiar metadatos: {str(ex)}",
        )


# ==========================================
# 6. CONVERTIR IMÁGENES A PDF (IMG2PDF)
# ==========================================
def _images_to_pdf_sync(image_paths: list[Path], output_path: Path) -> int:
    """Convierte una o varias imágenes (PNG, JPEG, WebP) a un documento PDF."""
    pil_images: list[Image.Image] = []

    for img_path in image_paths:
        img = Image.open(img_path)
        # Convertir a RGB (eliminando canal alfa para compatibilidad con PDF estándar de Pillow)
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            pil_images.append(bg)
        else:
            pil_images.append(img.convert("RGB"))

    if not pil_images:
        raise ValueError("NO_IMAGES")

    first_image = pil_images[0]
    other_images = pil_images[1:] if len(pil_images) > 1 else []

    first_image.save(
        str(output_path),
        format="PDF",
        save_all=True,
        append_images=other_images,
        resolution=100.0,
    )

    for img in pil_images:
        img.close()

    return len(pil_images)


async def images_to_pdf(image_paths: list[Path], output_path: Path) -> ExtraResult:
    start_time = time.perf_counter()
    orig_size = sum(p.stat().st_size for p in image_paths if p.exists())
    try:
        pages = await asyncio.to_thread(_images_to_pdf_sync, image_paths, output_path)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        final_size = output_path.stat().st_size if output_path.exists() else 0
        return ExtraResult(
            success=True,
            original_size=orig_size,
            final_size=final_size,
            pages=pages,
            duration_ms=duration_ms,
            output_path=output_path,
        )
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ExtraResult(
            success=False,
            original_size=orig_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code="IMG2PDF_ERROR",
            error_message=f"Error al convertir imágenes a PDF: {str(ex)}",
        )
