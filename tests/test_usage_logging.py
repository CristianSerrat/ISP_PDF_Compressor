"""Tests para el registro de uso estructurado y verificación de privacidad."""

import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.database.usage_repo import usage_repo
from app.main import app

client = TestClient(app)


def test_usage_logging_privacy(sample_pdf_bytes):
    """Verifica que NUNCA se registren nombres de archivo ni rutas en SQLite."""
    unique_secret_filename = "documento_super_secreto_colegio_12345.pdf"

    def fake_run_gs(*args, **kwargs):
        out_path = kwargs.get("output_path") or args[2]
        with open(out_path, "wb") as f:
            f.write(sample_pdf_bytes[:len(sample_pdf_bytes) // 2])

    with patch("app.services.ghostscript.find_ghostscript_binary", return_value="/usr/bin/gs"):
        with patch("app.services.ghostscript._run_ghostscript_sync", side_effect=fake_run_gs):
            resp = client.post(
                "/api/compress",
                data={"preset": "screen"},
                files={"file": (unique_secret_filename, sample_pdf_bytes, "application/pdf")},
            )
            assert resp.status_code == 200

    # Consultar directamente SQLite
    with usage_repo.get_connection() as conn:
        rows = conn.execute("SELECT * FROM usage_logs").fetchall()
        assert len(rows) >= 1
        latest = rows[-1]

        # Comprobar campos registrados
        assert latest["operation"] == "compress"
        assert latest["status"] == "ok"
        assert latest["pages"] == 2
        assert latest["original_size"] > 0
        assert latest["final_size"] > 0

        # Identificador del cliente debe ser un hash de 16 caracteres, no la IP plana
        assert len(latest["client_id"]) == 16
        assert latest["client_id"] != "127.0.0.1"

        # Comprobación de Privacidad Rigurosa: el nombre del archivo NO debe estar en ninguna columna
        for col_name in latest.keys():
            val = str(latest[col_name])
            assert "super_secreto" not in val, f"Fuga de privacidad en columna {col_name}"
            assert unique_secret_filename not in val, f"Fuga de nombre de archivo en columna {col_name}"
            assert "/tmp" not in val and "\\tmp" not in val, f"Ruta detectada en columna {col_name}"

        # Comprobar los parámetros registrados
        params = json.loads(latest["params"])
        assert params.get("preset") == "screen"
        assert "filename" not in params
        assert "path" not in params


def test_usage_retention_purge():
    """Verifica que los registros más antiguos que LOG_RETENTION_DAYS sean purgados."""
    import asyncio
    # Insertar un registro simulando fecha de hace 400 días
    with usage_repo.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO usage_logs (
                timestamp, operation, params, pages,
                original_size, final_size, duration_ms,
                status, error_code, client_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2020-01-01T00:00:00+00:00",
                "compress",
                "{}",
                1,
                100,
                50,
                10,
                "ok",
                None,
                "test-hash",
            ),
        )
        conn.commit()

    deleted = asyncio.run(usage_repo.cleanup_retention(retention_days=365))
    assert deleted >= 1
