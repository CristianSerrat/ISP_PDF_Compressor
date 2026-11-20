"""Punto de entrada principal de la aplicación FastAPI."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.core.storage import storage
from app.database.usage_repo import usage_repo
from app.routers import admin, compress, download, health, watermark

# Configuración básica de logging técnico a stdout
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pdf_app")


async def periodic_cleaner_task() -> None:
    """Tarea periódica en segundo plano para limpiar archivos temporales expirados por TTL."""
    while True:
        try:
            await asyncio.sleep(300)  # Cada 5 minutos
            deleted = storage.cleanup_expired()
            if deleted > 0:
                logger.info(f"Limpieza periódica ejecutada: {deleted} archivos temporales expirados eliminados.")
            # Ejecutar purga de retención de registros
            purged = await usage_repo.cleanup_retention()
            if purged > 0:
                logger.info(f"Purga de registros antiguos ejecutada: {purged} filas eliminadas.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en tarea periódica de limpieza: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización
    logger.info("Iniciando aplicación de herramientas PDF...")
    settings.setup_directories()
    storage.init_storage()
    usage_repo.init_db()

    cleaner_task = asyncio.create_task(periodic_cleaner_task())
    yield
    # Apagado
    cleaner_task.cancel()
    try:
        await cleaner_task
    except asyncio.CancelledError:
        pass
    logger.info("Aplicación detenida correctamente.")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras de seguridad HTTP básicas sin telemetría ni llamadas externas."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


app = FastAPI(
    title="Herramientas PDF Locales",
    description="Servicio interno 100% local para procesamiento seguro de documentos PDF",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # Desactivado en entorno interno por privacidad/seguridad o configurable
    redoc_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)

# Rutas de API
app.include_router(health.router)
app.include_router(compress.router)
app.include_router(watermark.router)
app.include_router(download.router)
app.include_router(admin.router)

# Servir archivos estáticos del frontend (HTML, CSS, JS vanilla)
STATIC_DIR = Path(__file__).parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    """Sirve la interfaz web principal."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Servidor PDF activo. Interfaz no disponible aún."}
