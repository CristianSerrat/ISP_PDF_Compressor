"""Tests unitarios y de integración para el módulo de Marca de Agua."""

import io
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pypdf import PdfReader
from app.database.usage_repo import usage_repo
from app.main import app
from app.services.watermark import parse_page_ranges

client = TestClient(app)


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Genera una imagen PNG de prueba en memoria."""
    img = Image.new("RGBA", (150, 80), color=(255, 0, 0, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def test_parse_page_ranges():
    assert parse_page_ranges("all", 5) == {0, 1, 2, 3, 4}
    assert parse_page_ranges("1-3, 5", 5) == {0, 1, 2, 4}
    assert parse_page_ranges("2", 5) == {1}
    assert parse_page_ranges("invalido", 3) == {0, 1, 2}
    assert parse_page_ranges("", 4) == {0, 1, 2, 3}


def test_watermark_text_success(sample_pdf_bytes):
    """Estampado de texto en todas las páginas."""
    response = client.post(
        "/api/watermark",
        data={
            "wm_type": "text",
            "wm_text": "BORRADOR PRIVADO",
            "position": "center",
            "opacity": "0.35",
            "rotation": "45",
            "scale": "1.2",
            "pages_range": "all",
        },
        files={"file": ("informe.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] is not None
    assert data["pages"] == 2
    assert "marca_agua_informe.pdf" in data["filename"]

    # Descarga del PDF estampado
    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert len(reader.pages) == 2


def test_watermark_image_tile(sample_pdf_bytes, sample_png_bytes):
    """Estampado de imagen en mosaico."""
    response = client.post(
        "/api/watermark",
        data={
            "wm_type": "image",
            "position": "tile",
            "opacity": "0.25",
            "rotation": "0",
            "scale": "0.8",
            "pages_range": "1",
        },
        files={
            "file": ("doc_para_imagen.pdf", sample_pdf_bytes, "application/pdf"),
            "wm_file": ("logo.png", sample_png_bytes, "image/png"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] is not None

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200


def test_watermark_pdf_overlay(sample_pdf_bytes):
    """Uso de un archivo PDF como marca de agua."""
    response = client.post(
        "/api/watermark",
        data={
            "wm_type": "pdf",
            "position": "center",
            "pages_range": "all",
        },
        files={
            "file": ("base.pdf", sample_pdf_bytes, "application/pdf"),
            "wm_file": ("plantilla_marca.pdf", sample_pdf_bytes, "application/pdf"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] is not None


def test_watermark_preview_first_page(sample_pdf_bytes):
    """Generación de vista previa de la primera página como stream PDF."""
    response = client.post(
        "/api/watermark/preview",
        data={
            "wm_type": "text",
            "wm_text": "VISTA PREVIA",
            "position": "center",
            "opacity": "0.4",
            "rotation": "30",
            "scale": "1.0",
        },
        files={"file": ("documento.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/pdf"
    # Debe ser un PDF válido de exactamente 1 página
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 1


def test_watermark_encrypted_pdf(encrypted_pdf_bytes):
    """Error al intentar estampar un PDF cifrado sin contraseña."""
    response = client.post(
        "/api/watermark",
        data={"wm_type": "text", "wm_text": "TEST"},
        files={"file": ("cifrado.pdf", encrypted_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 422
    assert "protegido con contraseña" in response.json()["detail"]


def test_watermark_invalid_image_magic_bytes(sample_pdf_bytes):
    """Rechazo si la supuesta imagen no tiene magic bytes reales."""
    response = client.post(
        "/api/watermark",
        data={"wm_type": "image"},
        files={
            "file": ("doc.pdf", sample_pdf_bytes, "application/pdf"),
            "wm_file": ("falsa_imagen.png", b"ESTO NO ES UN PNG", "image/png"),
        },
    )
    assert response.status_code == 400
    assert "formato válido" in response.json()["detail"]


def test_watermark_usage_logging_privacy(sample_pdf_bytes):
    """Verifica que el registro de uso guarde la operación pero NUNCA el texto de la marca ni nombres."""
    secret_text = "TEXTO_SECRETO_DE_EXAMEN_123"
    secret_filename = "archivo_secreto_colegio.pdf"

    resp = client.post(
        "/api/watermark",
        data={
            "wm_type": "text",
            "wm_text": secret_text,
            "position": "tile",
            "opacity": "0.2",
            "rotation": "45",
            "scale": "1.0",
            "pages_range": "all",
        },
        files={"file": (secret_filename, sample_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200

    with usage_repo.get_connection() as conn:
        rows = conn.execute("SELECT * FROM usage_logs WHERE operation = 'watermark' ORDER BY id DESC LIMIT 1").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["operation"] == "watermark"
        assert row["status"] == "ok"

        # Privacidad: comprobar que el texto de la marca NO está en params ni en ninguna columna
        for col in row.keys():
            val = str(row[col])
            assert secret_text not in val, f"Fuga de texto sensible en columna {col}"
            assert secret_filename not in val, f"Fuga de nombre de archivo en columna {col}"

        params = json.loads(row["params"])
        assert params["wm_type"] == "text"
        assert params["position"] == "tile"
        assert "wm_text" not in params
        assert "text" not in params
