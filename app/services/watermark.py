"""Servicio para aplicar marcas de agua (texto, imagen o PDF) sobre documentos PDF."""

import asyncio
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pypdf
from PIL import Image
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from app.services.ghostscript import inspect_pdf_pages


@dataclass
class WatermarkResult:
    success: bool
    original_size: int
    final_size: int
    pages: int
    duration_ms: int
    output_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None


def parse_page_ranges(range_str: str, total_pages: int) -> set[int]:
    """
    Parsea una expresión de rangos de páginas (ej. '1', '1-3', '1, 4, 6-8', 'all').
    Retorna un conjunto de índices base 0.
    """
    if not range_str or range_str.strip().lower() in ("all", "todas", "*"):
        return set(range(total_pages))

    selected = set()
    parts = range_str.replace(";", ",").split(",")

    for part in parts:
        clean = part.strip()
        if not clean:
            continue
        if "-" in clean:
            sub = clean.split("-", 1)
            try:
                start = max(1, int(sub[0].strip()))
                end = min(total_pages, int(sub[1].strip()))
                for p in range(start, end + 1):
                    selected.add(p - 1)
            except ValueError:
                continue
        else:
            try:
                p = int(clean)
                if 1 <= p <= total_pages:
                    selected.add(p - 1)
            except ValueError:
                continue

    return selected if selected else set(range(total_pages))


def _calculate_coordinates(
    position: str,
    page_width: float,
    page_height: float,
) -> list[tuple[float, float]]:
    """Calcula las coordenadas (x, y) según la posición solicitada."""
    pos = position.lower().strip()
    if pos == "top-left":
        return [(page_width * 0.22, page_height * 0.78)]
    if pos == "top-right":
        return [(page_width * 0.78, page_height * 0.78)]
    if pos == "bottom-left":
        return [(page_width * 0.22, page_height * 0.22)]
    if pos == "bottom-right":
        return [(page_width * 0.78, page_height * 0.22)]
    if pos == "tile":
        # Patrón en mosaico que cubre toda la página
        coords = []
        step_x = max(140.0, page_width / 3)
        step_y = max(140.0, page_height / 4)
        x = step_x / 2
        while x < page_width:
            y = step_y / 2
            while y < page_height:
                coords.append((x, y))
                y += step_y
            x += step_x
        return coords
    # Por defecto: "center"
    return [(page_width / 2, page_height / 2)]


def create_text_watermark_layer(
    text: str,
    page_width: float,
    page_height: float,
    opacity: float = 0.3,
    rotation: float = 45.0,
    scale: float = 1.0,
    position: str = "center",
) -> pypdf.PageObject:
    """Genera una página PDF transparente con el texto de la marca de agua."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.saveState()

    font_size = max(12, int(42 * scale))
    if position == "tile":
        font_size = max(10, int(22 * scale))

    c.setFont("Helvetica-Bold", font_size)
    c.setFillColor(Color(0.3, 0.3, 0.3, alpha=max(0.05, min(1.0, opacity))))

    coordinates = _calculate_coordinates(position, page_width, page_height)
    for x, y in coordinates:
        c.saveState()
        c.translate(x, y)
        c.rotate(rotation)
        c.drawCentredString(0, -font_size / 3, text)
        c.restoreState()

    c.restoreState()
    c.save()
    buf.seek(0)
    reader = pypdf.PdfReader(buf)
    return reader.pages[0]


def create_image_watermark_layer(
    image_bytes: bytes,
    page_width: float,
    page_height: float,
    opacity: float = 0.3,
    rotation: float = 0.0,
    scale: float = 1.0,
    position: str = "center",
) -> pypdf.PageObject:
    """Genera una página PDF transparente con una imagen como marca de agua."""
    pil_image = Image.open(io.BytesIO(image_bytes))
    orig_w, orig_h = pil_image.size

    # Calcular dimensiones proporcionales
    base_dim = min(page_width, page_height) * 0.4
    if position == "tile":
        base_dim = min(page_width, page_height) * 0.2

    aspect = orig_h / orig_w
    target_w = base_dim * scale
    target_h = target_w * aspect

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    c.saveState()
    c.setFillAlpha(max(0.05, min(1.0, opacity)))

    img_buf = io.BytesIO()
    pil_image.save(img_buf, format="PNG")
    img_buf.seek(0)
    img_reader = ImageReader(img_buf)

    coordinates = _calculate_coordinates(position, page_width, page_height)
    for x, y in coordinates:
        c.saveState()
        c.translate(x, y)
        c.rotate(rotation)
        c.drawImage(
            img_reader,
            -target_w / 2,
            -target_h / 2,
            width=target_w,
            height=target_h,
            mask="auto",
        )
        c.restoreState()

    c.restoreState()
    c.save()
    buf.seek(0)
    reader = pypdf.PdfReader(buf)
    return reader.pages[0]


def create_pdf_watermark_layer(
    pdf_bytes: bytes,
    page_width: float,
    page_height: float,
) -> pypdf.PageObject:
    """Extrae la primera página de un PDF como capa de marca de agua."""
    wm_reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    if len(wm_reader.pages) == 0:
        raise ValueError("El archivo PDF de marca de agua está vacío.")
    return wm_reader.pages[0]


def _apply_watermark_sync(
    input_path: Path,
    output_path: Path,
    wm_type: str,
    wm_text: str | None,
    wm_file_bytes: bytes | None,
    position: str,
    opacity: float,
    rotation: float,
    scale: float,
    pages_range: str,
) -> int:
    """Proceso síncrono para sobreponer la marca de agua y escribir el PDF final."""
    reader = pypdf.PdfReader(str(input_path))
    writer = pypdf.PdfWriter()
    total_pages = len(reader.pages)
    target_pages = parse_page_ranges(pages_range, total_pages)

    # Cache de capa para tamaños estándar de página
    layer_cache: dict[tuple[float, float], pypdf.PageObject] = {}

    for idx, in_page in enumerate(reader.pages):
        page = writer.add_page(in_page)
        if idx in target_pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            size_key = (w, h)

            if size_key not in layer_cache:
                if wm_type == "text" and wm_text:
                    layer = create_text_watermark_layer(
                        text=wm_text,
                        page_width=w,
                        page_height=h,
                        opacity=opacity,
                        rotation=rotation,
                        scale=scale,
                        position=position,
                    )
                elif wm_type == "image" and wm_file_bytes:
                    layer = create_image_watermark_layer(
                        image_bytes=wm_file_bytes,
                        page_width=w,
                        page_height=h,
                        opacity=opacity,
                        rotation=rotation,
                        scale=scale,
                        position=position,
                    )
                elif wm_type == "pdf" and wm_file_bytes:
                    layer = create_pdf_watermark_layer(
                        pdf_bytes=wm_file_bytes,
                        page_width=w,
                        page_height=h,
                    )
                else:
                    layer = None

                if layer is not None:
                    layer_cache[size_key] = layer

            if size_key in layer_cache:
                page.merge_page(layer_cache[size_key])

    with open(output_path, "wb") as f_out:
        writer.write(f_out)

    return total_pages


async def apply_watermark(
    input_path: Path,
    output_path: Path,
    wm_type: str = "text",
    wm_text: str | None = None,
    wm_file_bytes: bytes | None = None,
    position: str = "center",
    opacity: float = 0.3,
    rotation: float = 45.0,
    scale: float = 1.0,
    pages_range: str = "all",
) -> WatermarkResult:
    """Aplica marca de agua de forma asíncrona sobre un archivo PDF."""
    start_time = time.perf_counter()
    original_size = input_path.stat().st_size

    # Verificar si el archivo es válido o está cifrado
    try:
        pages = inspect_pdf_pages(input_path)
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        code = str(e)
        msg = "El PDF está protegido con contraseña." if code == "ENCRYPTED_PDF" else "El archivo PDF está dañado o es inválido."
        return WatermarkResult(
            success=False,
            original_size=original_size,
            final_size=0,
            pages=0,
            duration_ms=duration_ms,
            error_code=code,
            error_message=msg,
        )

    try:
        total_pages = await asyncio.to_thread(
            _apply_watermark_sync,
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
    except Exception as ex:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return WatermarkResult(
            success=False,
            original_size=original_size,
            final_size=0,
            pages=pages,
            duration_ms=duration_ms,
            error_code="WATERMARK_ERROR",
            error_message=f"Error al estampar marca de agua: {str(ex)}",
        )

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    final_size = output_path.stat().st_size if output_path.exists() else 0

    return WatermarkResult(
        success=True,
        original_size=original_size,
        final_size=final_size,
        pages=total_pages,
        duration_ms=duration_ms,
        output_path=output_path,
    )


async def generate_first_page_preview(
    input_path: Path,
    wm_type: str = "text",
    wm_text: str | None = None,
    wm_file_bytes: bytes | None = None,
    position: str = "center",
    opacity: float = 0.3,
    rotation: float = 45.0,
    scale: float = 1.0,
) -> bytes:
    """
    Genera un PDF de 1 página con la marca de agua aplicada sobre la primera página
    del documento original para previsualización inmediata en el navegador.
    """
    def _preview_sync() -> bytes:
        reader = pypdf.PdfReader(str(input_path))
        if len(reader.pages) == 0:
            raise ValueError("El PDF no contiene páginas.")

        writer = pypdf.PdfWriter()
        first_page = writer.add_page(reader.pages[0])
        w = float(first_page.mediabox.width)
        h = float(first_page.mediabox.height)

        if wm_type == "text" and wm_text:
            layer = create_text_watermark_layer(
                text=wm_text,
                page_width=w,
                page_height=h,
                opacity=opacity,
                rotation=rotation,
                scale=scale,
                position=position,
            )
            first_page.merge_page(layer)
        elif wm_type == "image" and wm_file_bytes:
            layer = create_image_watermark_layer(
                image_bytes=wm_file_bytes,
                page_width=w,
                page_height=h,
                opacity=opacity,
                rotation=rotation,
                scale=scale,
                position=position,
            )
            first_page.merge_page(layer)
        elif wm_type == "pdf" and wm_file_bytes:
            layer = create_pdf_watermark_layer(
                pdf_bytes=wm_file_bytes,
                page_width=w,
                page_height=h,
            )
            first_page.merge_page(layer)

        out_buf = io.BytesIO()
        writer.write(out_buf)
        return out_buf.getvalue()

    return await asyncio.to_thread(_preview_sync)
