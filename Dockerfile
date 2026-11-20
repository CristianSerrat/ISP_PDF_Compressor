# Dockerfile para Herramientas PDF (Entorno de Producción CasaOS / Linux)
FROM python:3.12-slim-bookworm

LABEL maintainer="Centro Educativo"
LABEL description="Herramientas PDF 100% locales, seguras y privadas para la red interna"

# Variables de entorno de Python y de la aplicación
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    DATA_DIR=/app/data \
    TMP_DIR=/app/tmp

# Instalar dependencias del sistema requeridas:
# - ghostscript: motor de compresión segura de PDF
# - curl: utilizado por el HEALTHCHECK del contenedor
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Crear usuario sin privilegios root (UID 1000 para compatibilidad con el usuario estándar de Ubuntu / CasaOS)
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -d /app -s /bin/bash appuser

WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY app ./app

# Crear directorios para base de datos persistente y archivos temporales, y ajustar permisos
RUN mkdir -p /app/data /app/tmp && \
    chown -R appuser:appuser /app

# Ejecutar como usuario sin privilegios
USER appuser

# Exponer el puerto del servicio
EXPOSE 8000

# Monitoreo de salud nativo de Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Comando de arranque del servidor ASGI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
