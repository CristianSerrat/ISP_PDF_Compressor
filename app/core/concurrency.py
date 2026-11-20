"""Control de concurrencia para evitar saturación de CPU por tareas pesadas de Ghostscript/PDF."""

import asyncio
from app.config import settings

_semaphore: asyncio.Semaphore | None = None


def get_concurrency_semaphore() -> asyncio.Semaphore:
    """Retorna la instancia global del semáforo de concurrencia."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
    return _semaphore
