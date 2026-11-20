"""Gestor de almacenamiento temporal con UUIDs, borrado post-descarga y limpieza periódica por TTL."""

import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from app.config import settings


@dataclass
class DownloadItem:
    file_path: Path
    download_filename: str
    created_at: float
    content_type: str = "application/pdf"


class StorageManager:
    """Administra archivos temporales garantizando aislamiento y borrado automático."""

    def __init__(self, tmp_dir: Path | None = None):
        self.tmp_dir = tmp_dir or settings.TMP_DIR
        self._registry: dict[str, DownloadItem] = {}

    def init_storage(self) -> None:
        """Asegura que el directorio temporal exista."""
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def create_temp_path(self, suffix: str = ".pdf") -> tuple[str, Path]:
        """Genera un identificador único (token) y una ruta temporal aleatoria."""
        token = uuid.uuid4().hex
        file_path = self.tmp_dir / f"{token}{suffix}"
        return token, file_path

    def register_download(
        self,
        token: str,
        file_path: Path,
        download_filename: str,
        content_type: str = "application/pdf"
    ) -> None:
        """Registra un archivo disponible para descarga."""
        self._registry[token] = DownloadItem(
            file_path=file_path,
            download_filename=download_filename,
            created_at=time.time(),
            content_type=content_type
        )

    def get_download_item(self, token: str) -> DownloadItem | None:
        """Obtiene la información de un archivo registrado."""
        return self._registry.get(token)

    def consume_download(self, token: str) -> DownloadItem | None:
        """
        Recupera el archivo registrado y lo retira del registro para borrado posterior.
        """
        return self._registry.pop(token, None)

    def remove_file(self, file_path: Path) -> None:
        """Borra de forma segura un archivo físico en disco."""
        try:
            if file_path.is_file():
                file_path.unlink(missing_ok=True)
            elif file_path.is_dir():
                shutil.rmtree(file_path, ignore_errors=True)
        except OSError:
            pass

    def cleanup_expired(self, ttl_minutes: int | None = None) -> int:
        """
        Elimina archivos del directorio temporal y entradas de registro que hayan superado el TTL.
        Devuelve el número de archivos eliminados.
        """
        ttl_seconds = (ttl_minutes or settings.TTL_MINUTES) * 60
        now = time.time()
        deleted_count = 0

        # Limpiar registro en memoria
        expired_tokens = [
            token for token, item in self._registry.items()
            if now - item.created_at > ttl_seconds
        ]
        for token in expired_tokens:
            item = self._registry.pop(token)
            self.remove_file(item.file_path)
            deleted_count += 1

        # Limpiar cualquier archivo huérfano en el directorio temporal
        try:
            for entry in self.tmp_dir.iterdir():
                try:
                    stat = entry.stat()
                    if now - stat.st_mtime > ttl_seconds:
                        self.remove_file(entry)
                        deleted_count += 1
                except OSError:
                    continue
        except OSError:
            pass

        return deleted_count


storage = StorageManager()
