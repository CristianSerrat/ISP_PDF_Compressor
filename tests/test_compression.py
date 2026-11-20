"""Tests unitarios y de integración para compresión de PDF."""

import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.core.security import sanitize_filename, validate_pdf_magic_bytes
from app.main import app

client = TestClient(app)


def test_sanitize_filename():
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("informe anual 2024.pdf") == "informe_anual_2024.pdf"
    assert sanitize_filename("") == "documento.pdf"
    assert sanitize_filename("..") == "documento.pdf"


def test_validate_pdf_magic_bytes(sample_pdf_bytes):
    assert validate_pdf_magic_bytes(sample_pdf_bytes) is True
    assert validate_pdf_magic_bytes(b"NOT_A_PDF_FILE_HEADER") is False


def test_compress_invalid_magic_bytes():
    response = client.post(
        "/api/compress",
        files={"file": ("fake.pdf", b"Contenido de texto plano", "application/pdf")},
    )
    assert response.status_code == 400
    assert "no es un documento PDF válido" in response.json()["detail"]


def test_compress_encrypted_pdf(encrypted_pdf_bytes):
    response = client.post(
        "/api/compress",
        files={"file": ("cifrado.pdf", encrypted_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 422
    assert "protegido con contraseña" in response.json()["detail"]


def test_compress_corrupt_pdf(corrupt_pdf_bytes):
    response = client.post(
        "/api/compress",
        files={"file": ("danado.pdf", corrupt_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 422
    assert "dañado o es inválido" in response.json()["detail"]


def test_compress_success_flow(sample_pdf_bytes):
    """Simula una compresión exitosa con Ghostscript mockeado para entornos de test."""
    def fake_run_gs(*args, **kwargs):
        # Escribe un archivo más pequeño simulando compresión exitosa
        out_path = kwargs.get("output_path") or args[2]
        with open(out_path, "wb") as f:
            f.write(sample_pdf_bytes[:len(sample_pdf_bytes) // 2])

    with patch("app.services.ghostscript.find_ghostscript_binary", return_value="/usr/bin/gs"):
        with patch("app.services.ghostscript._run_ghostscript_sync", side_effect=fake_run_gs):
            response = client.post(
                "/api/compress",
                data={"preset": "ebook"},
                files={"file": ("documento_original.pdf", sample_pdf_bytes, "application/pdf")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["token"] is not None
            assert data["saved_bytes"] > 0
            assert data["saved_pct"] > 0
            assert data["returned_original"] is False
            assert data["pages"] == 2

            # Probar descarga del archivo
            dl_resp = client.get(data["download_url"])
            assert dl_resp.status_code == 200
            assert "comprimido_documento_original.pdf" in dl_resp.headers.get("content-disposition", "")

            # Comprobar que tras la descarga el token ya fue consumido
            second_dl = client.get(data["download_url"])
            assert second_dl.status_code == 404


def test_compress_when_result_larger_than_original(sample_pdf_bytes):
    """Si el archivo generado es mayor que el original, devuelve el original intacto."""
    def fake_run_gs_larger(*args, **kwargs):
        out_path = kwargs.get("output_path") or args[2]
        with open(out_path, "wb") as f:
            # Archivo inflado
            f.write(sample_pdf_bytes + b"\x00" * 1000)

    with patch("app.services.ghostscript.find_ghostscript_binary", return_value="/usr/bin/gs"):
        with patch("app.services.ghostscript._run_ghostscript_sync", side_effect=fake_run_gs_larger):
            response = client.post(
                "/api/compress",
                data={"preset": "printer"},
                files={"file": ("pesado.pdf", sample_pdf_bytes, "application/pdf")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["returned_original"] is True
            assert data["final_size"] == data["original_size"]
            assert data["saved_bytes"] == 0
