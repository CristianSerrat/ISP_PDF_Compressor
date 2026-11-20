"""Fixtures y generadores de PDFs para pruebas automatizadas."""

import io
from pathlib import Path
import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.config import settings


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    """Configura directorios temporales aislados para cada test."""
    test_data = tmp_path / "data"
    test_tmp = tmp_path / "tmp"
    test_data.mkdir(parents=True, exist_ok=True)
    test_tmp.mkdir(parents=True, exist_ok=True)

    settings.DATA_DIR = test_data
    settings.TMP_DIR = test_tmp
    settings.LOG_CLIENT_MODE = "hash"
    settings.HASH_SALT = "test-salt"
    settings.ADMIN_ALLOWED_NETWORKS = "127.0.0.1/32"

    from app.core.storage import storage
    from app.database.usage_repo import usage_repo

    storage.tmp_dir = test_tmp
    usage_repo.db_path = test_data / "usage.db"
    usage_repo.init_db()

    yield


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Genera en memoria un PDF válido de 2 páginas."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 750, "Página 1: Documento de prueba interno.")
    c.showPage()
    c.drawString(100, 750, "Página 2: Otra página para comprobar contador.")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def encrypted_pdf_bytes(sample_pdf_bytes) -> bytes:
    """Genera en memoria un PDF cifrado con contraseña 'secreta'."""
    reader = PdfReader(io.BytesIO(sample_pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("secreta")
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def corrupt_pdf_bytes() -> bytes:
    """Genera un archivo con cabecera PDF pero contenido corrupto/truncado."""
    return b"%PDF-1.4\n%%EOF_CORRUPT_DATA_TRUNCATED_12345"
