"""Tests para la gestión y limpieza de archivos temporales (TTL y borrado inmediato)."""

import os
import time
from pathlib import Path
from app.core.storage import StorageManager


def test_storage_create_and_consume(tmp_path):
    mgr = StorageManager(tmp_dir=tmp_path)
    mgr.init_storage()

    token, file_path = mgr.create_temp_path()
    file_path.write_bytes(b"test pdf content")

    mgr.register_download(token, file_path, "test.pdf")

    # Item registrado existe
    item = mgr.get_download_item(token)
    assert item is not None
    assert item.file_path == file_path

    # Consumir descarga
    consumed = mgr.consume_download(token)
    assert consumed is not None

    # Ya no debe estar en el registro
    assert mgr.get_download_item(token) is None

    # Borrar físicamente
    mgr.remove_file(consumed.file_path)
    assert not file_path.exists()


def test_storage_cleanup_expired(tmp_path):
    mgr = StorageManager(tmp_dir=tmp_path)
    mgr.init_storage()

    # Archivo 1: reciente
    token1, path1 = mgr.create_temp_path()
    path1.write_bytes(b"recent file")
    mgr.register_download(token1, path1, "recent.pdf")

    # Archivo 2: simulando antigüedad de 60 minutos
    token2, path2 = mgr.create_temp_path()
    path2.write_bytes(b"expired file")
    mgr.register_download(token2, path2, "expired.pdf")
    mgr._registry[token2].created_at = time.time() - 3600
    os.utime(path2, (time.time() - 3600, time.time() - 3600))

    # Ejecutar limpieza con TTL de 30 minutos
    deleted = mgr.cleanup_expired(ttl_minutes=30)
    assert deleted >= 1
    assert not path2.exists()
    assert token2 not in mgr._registry

    # El reciente debe seguir existiendo
    assert path1.exists()
    assert token1 in mgr._registry
