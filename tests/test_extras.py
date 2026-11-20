"""Tests unitarios y de integración para herramientas adicionales de PDF (merge, split, rotate, protect, strip, img2pdf)."""

import io
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from app.config import settings
from app.database.usage_repo import usage_repo
from app.main import app

client = TestClient(app)


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Genera una imagen PNG de prueba en memoria."""
    img = Image.new("RGB", (200, 150), color=(0, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def pdf_with_metadata_bytes(sample_pdf_bytes) -> bytes:
    """Genera un PDF con metadatos específicos para probar su eliminación."""
    reader = PdfReader(io.BytesIO(sample_pdf_bytes))
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.add_metadata({
        "/Author": "Profesor Juan Pérez",
        "/Title": "Examen Secreto Trimestral",
        "/Producer": "Software Privado Escolar v1.0",
    })
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.getvalue()


def test_merge_pdfs(sample_pdf_bytes):
    """Une dos archivos PDF (2 + 2 = 4 páginas)."""
    response = client.post(
        "/api/extras/merge",
        files=[
            ("files", ("doc1.pdf", sample_pdf_bytes, "application/pdf")),
            ("files", ("doc2.pdf", sample_pdf_bytes, "application/pdf")),
        ],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pages"] == 4
    assert data["token"] is not None

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert len(reader.pages) == 4


def test_split_pdf(sample_pdf_bytes):
    """Extrae únicamente la página 1 de un PDF de 2 páginas."""
    response = client.post(
        "/api/extras/split",
        data={"pages_range": "1"},
        files={"file": ("completo.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pages"] == 1

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert len(reader.pages) == 1


def test_rotate_pdf(sample_pdf_bytes):
    """Rota las páginas del PDF en 90 grados."""
    response = client.post(
        "/api/extras/rotate",
        data={"angle": "90", "pages_range": "all"},
        files={"file": ("vertical.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pages"] == 2

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert reader.pages[0].rotation == 90


def test_protect_pdf_and_verify_encryption(sample_pdf_bytes):
    """Cifra el PDF con contraseña y comprueba que requiera la clave para leerse."""
    password = "clave-super-secreta-2024"
    response = client.post(
        "/api/extras/protect",
        data={"password": password},
        files={"file": ("abierto.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pages"] == 2

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200

    # Comprobar que está cifrado
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert reader.is_encrypted is True
    # Descifrar con la contraseña
    assert reader.decrypt(password) != 0
    assert len(reader.pages) == 2


def test_protect_pdf_privacy_no_password_in_db(sample_pdf_bytes):
    """Verifica que la contraseña NUNCA se guarde en la base de datos de auditoría."""
    password = "password_que_nunca_debe_aparecer_en_sqlite"
    resp = client.post(
        "/api/extras/protect",
        data={"password": password},
        files={"file": ("confidencial.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200

    with usage_repo.get_connection() as conn:
        rows = conn.execute("SELECT * FROM usage_logs WHERE operation = 'protect' ORDER BY id DESC LIMIT 1").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "ok"
        for col in row.keys():
            val = str(row[col])
            assert password not in val, f"Fuga de contraseña en columna {col}"
        params = json.loads(row["params"])
        assert "password" not in params


def test_strip_metadata(pdf_with_metadata_bytes):
    """Elimina metadatos de autor, software y fechas."""
    # Verificar que el PDF origen tiene metadatos
    reader_orig = PdfReader(io.BytesIO(pdf_with_metadata_bytes))
    assert reader_orig.metadata is not None
    assert "/Author" in reader_orig.metadata

    response = client.post(
        "/api/extras/strip-metadata",
        files={"file": ("con_metadatos.pdf", pdf_with_metadata_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200

    # Verificar que el resultado NO tiene metadatos de autor
    reader_clean = PdfReader(io.BytesIO(dl_resp.content))
    if reader_clean.metadata:
        assert reader_clean.metadata.author is None or reader_clean.metadata.author == ""
        assert reader_clean.metadata.title is None or reader_clean.metadata.title == ""


def test_img2pdf(sample_png_bytes):
    """Convierte imágenes a PDF."""
    response = client.post(
        "/api/extras/img2pdf",
        files=[
            ("files", ("foto1.png", sample_png_bytes, "image/png")),
            ("files", ("foto2.png", sample_png_bytes, "image/png")),
        ],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pages"] == 2

    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert len(reader.pages) == 2


def test_module_disabled_returns_403(sample_pdf_bytes):
    """Si un módulo se desactiva en ENABLED_MODULES, debe retornar 403 Forbidden."""
    original_modules = settings.ENABLED_MODULES
    settings.ENABLED_MODULES = "compress,watermark"  # Sin "split"

    try:
        response = client.post(
            "/api/extras/split",
            data={"pages_range": "1"},
            files={"file": ("doc.pdf", sample_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 403
        assert "deshabilitado" in response.json()["detail"]
    finally:
        settings.ENABLED_MODULES = original_modules


def test_read_and_modify_metadata(pdf_with_metadata_bytes):
    """Prueba la lectura y modificación de campos de metadatos de un PDF."""
    # 1. Probar lectura de metadatos existentes
    read_resp = client.post(
        "/api/extras/read-metadata",
        files={"file": ("orig.pdf", pdf_with_metadata_bytes, "application/pdf")},
    )
    assert read_resp.status_code == 200
    meta_json = read_resp.json()
    assert meta_json["author"] == "Profesor Juan Pérez"
    assert meta_json["title"] == "Examen Secreto Trimestral"

    # 2. Modificar los metadatos
    edit_resp = client.post(
        "/api/extras/edit-metadata",
        data={
            "title": "Nuevo Título Oficial 2024",
            "author": "Departamento de Ciencias",
            "subject": "Física y Química",
            "keywords": "examen, 4eso, ciencias",
            "creator": "Sistema PDF Interno",
        },
        files={"file": ("doc.pdf", pdf_with_metadata_bytes, "application/pdf")},
    )
    assert edit_resp.status_code == 200
    data = edit_resp.json()
    assert data["token"] is not None

    # 3. Descargar y verificar con pypdf
    dl_resp = client.get(data["download_url"])
    assert dl_resp.status_code == 200
    reader = PdfReader(io.BytesIO(dl_resp.content))
    assert reader.metadata.title == "Nuevo Título Oficial 2024"
    assert reader.metadata.author == "Departamento de Ciencias"
    assert reader.metadata.subject == "Física y Química"

    # 4. Privacidad: Comprobar que los valores sensibles NO se registren en SQLite
    with usage_repo.get_connection() as conn:
        rows = conn.execute("SELECT * FROM usage_logs WHERE operation = 'edit_metadata' ORDER BY id DESC LIMIT 1").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "ok"
        for col in row.keys():
            val = str(row[col])
            assert "Nuevo Título Oficial" not in val
            assert "Departamento de Ciencias" not in val
        params = json.loads(row["params"])
        assert "title" not in params
        assert "author" not in params
