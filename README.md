# Herramientas PDF Locales (Alternativa Segura a iLovePDF)

Aplicación web interna, 100% local y auto-contenida para procesar y optimizar documentos PDF en la red de un centro educativo sin enviar ningún archivo ni metadato a servidores externos.

---

## Características Principales (Fase 1)

- **Compresión de PDF con Ghostscript:**
  - Presets disponibles:
    - **Máxima compresión:** ~72 DPI (`/screen`).
    - **Equilibrada (por defecto):** ~150 DPI (`/ebook`).
    - **Alta calidad:** ~300 DPI (`/printer`).
    - **Personalizada:** selección manual de DPI (36-600) y factor de calidad JPEG.
  - Comparación de tamaños (original vs. final) y porcentaje de ahorro.
  - **Protección contra inflación:** si el archivo comprimido resulta más pesado que el original, se devuelve el original intacto y se avisa al usuario.
- **Estampado de Marca de Agua:**
  - Tres modalidades disponibles: **Texto personalizado**, **Imagen (PNG, JPG, WebP)** o **Archivo PDF**.
  - Opciones de personalización:
    - **Posición:** Centro, Esquinas (superior/inferior izq./der.) y patrón en **Mosaico** (repetición en cuadrícula sobre toda la hoja).
    - **Opacidad:** control de transparencia del 5% al 100%.
    - **Rotación:** ángulo libre (de -90° a 90°, 45° por defecto).
    - **Escala:** ajuste de tamaño de la marca.
    - **Rango de páginas:** aplicar a todas (`all`) o páginas seleccionadas (ej. `1-3, 5`).
  - **Previsualización interactiva:** genera la primera página estampada como stream PDF en tiempo real antes de descargar.
- **Herramientas Modulares Extras:**
  - 🔗 **Unir PDFs (Merge):** combina múltiples documentos en un único archivo con reordenado dinámico interactivo (subir/bajar posición).
  - ✂️ **Dividir PDF (Split):** extrae páginas o rangos específicos (ej. `1-3, 5, 8-10`).
  - 🔄 **Rotar Páginas (Rotate):** gira todas las páginas o rangos en 90°, 180° o 270°.
  - 🔒 **Proteger con Contraseña (Protect):** cifra el PDF para exigir contraseña de apertura (la contraseña se procesa en memoria y **NUNCA** se almacena en base de datos ni logs).
  - 🧹 **Eliminar Metadatos (Strip Metadata):** anonimiza por completo el PDF suprimiendo autor, título, software generador, fechas y metadatos XMP.
  - 🖼️ **Imágenes a PDF (Img2pdf):** convierte imágenes PNG, JPG o WebP a un PDF unificado.
  - *Cada módulo se puede activar o desactivar individualmente mediante la variable `ENABLED_MODULES`.*
- **Procesamiento individual y por lotes:** arrastrar y soltar múltiples archivos con descarga individual o en paquete ZIP unificado.
- **Privacidad estricta y seguridad:**
  - Los archivos viven temporalmente con nombres `UUID4` y se eliminan inmediatamente tras ser descargados.
  - Tarea periódica en segundo plano para purgar archivos temporales que superen el TTL configurable.
  - Validación de tipo real mediante **magic bytes** (`%PDF-`).
  - Límite de concurrencia mediante semáforos para no sobrecargar la CPU del servidor.
- **Registro de uso anónimo en SQLite (modo WAL):**
  - Ubicado en `DATA_DIR/usage.db`.
  - Almacena únicamente métricas numéricas agregadas (operación, tamaño, páginas, duración, resultado).
  - **NUNCA** almacena nombres de archivo originales, rutas en disco ni contenidos.
- **Panel de Control y Estadísticas (`/admin/stats`):**
  - Métricas agregadas por período (7, 30, 90 y 365 días): operaciones por día, por tipo, por preset de compresión, picos de uso por franja horaria (00-23h), clientes más activos y códigos de error.
  - Exportación completa del registro a archivo CSV descargable y filtrable por fechas (`/admin/export.csv`).
  - **Control de acceso sin credenciales:** restringido exclusivamente a las redes e IPs configuradas en `ADMIN_ALLOWED_NETWORKS` (por defecto solo `127.0.0.1/32` y `::1/128`), denegando con 403 Forbidden al resto.
- **Interfaz 100% offline:** HTML5, CSS y JavaScript vanilla sin fuentes externas ni CDNs.

---

## Requisitos del Sistema

1. **Python 3.12+**
2. **Ghostscript** (motor de compresión seguro).

### Instalación de Ghostscript

- **macOS (con Homebrew):**
  ```bash
  brew install ghostscript
  ```
- **Debian / Ubuntu / Raspberry Pi OS:**
  ```bash
  sudo apt update && sudo apt install -y ghostscript
  ```
- **Windows:** Descargar el instalador de Ghostscript (`gswin64c.exe`) y añadirlo al `PATH`.

---

## Instalación y Puesta en Marcha

1. **Crear y activar el entorno virtual:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecutar la aplicación:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Acceder a la aplicación:**
   Abre tu navegador web en: `http://localhost:8000`

---

## Variables de Entorno de Configuración

Todas las variables son opcionales y cuentan con valores por defecto preparados para entorno local y posterior dockerización:

| Variable | Valor por Defecto | Descripción |
| :--- | :--- | :--- |
| `PORT` | `8000` | Puerto HTTP en el que escucha Uvicorn. |
| `DATA_DIR` | `data` | Directorio de datos persistentes (`usage.db`). |
| `TMP_DIR` | `tmp` | Directorio para procesado temporal de archivos. |
| `MAX_FILE_MB` | `100` | Tamaño máximo permitido por archivo (MB). |
| `MAX_FILES` | `20` | Número máximo de archivos por lote. |
| `TTL_MINUTES` | `30` | Tiempo de vida de los archivos temporales antes de ser purgados. |
| `GS_TIMEOUT` | `120` | Tiempo máximo de ejecución de Ghostscript en segundos. |
| `MAX_CONCURRENT_JOBS`| `2` | Número máximo de procesos de compresión simultáneos. |
| `LOG_CLIENT_MODE` | `hash` | Registro de cliente: `none` (anónimo), `hash` (SHA-256 salado), `ip`. |
| `HASH_SALT` | `pdf-secret-salt-2024` | Sal utilizada para el hashing de IPs en modo `hash`. |
| `LOG_RETENTION_DAYS` | `365` | Días de retención para los registros de uso en SQLite. |
| `LOG_LEVEL` | `INFO` | Nivel de logs técnicos a consola (`DEBUG`, `INFO`, `WARNING`). |
| `ADMIN_PASSWORD` | `admin1234` | Clave maestra para acceder al panel de administración (`/admin/stats`). |
| `ADMIN_SESSION_HOURS`| `8` | Duración en horas de la sesión de administrador. |
| `SECRET_KEY` | `pdf-tools-session-secret-key-2024` | Clave criptográfica para firma HMAC de cookies de sesión. |
| `TRUST_PROXY` | `false` | Respetar cabecera `X-Forwarded-For` detrás de proxy inverso. |
| `ADMIN_ALLOWED_NETWORKS`| `""` | Redes CIDR opcionales (vacío permite cualquier IP con clave). |
| `ENABLED_MODULES` | *(todos)* | Módulos activos separados por coma. |

---

## Nota de Privacidad y RGPD

La dirección IP de los usuarios puede considerarse un dato personal bajo el Reglamento General de Protección de Datos (RGPD / GDPR).

Para cumplir rigurosamente con este principio sin privar a la administración del colegio de conocer el volumen de uso:
1. **Modo por defecto (`LOG_CLIENT_MODE=hash`):** la dirección IP nunca se escribe en la base de datos; se calcula un hash criptográfico SHA-256 salado (`salt + IP`) truncado a 16 caracteres. Esto permite distinguir si múltiples operaciones provienen de un mismo origen recurrente sin revelar la IP física del equipo.
2. **Modo `none`:** no se almacena ningún identificador (se registra siempre `"anon"`).
3. **Cero fugas de información:** los nombres originales de archivo y sus contenidos **jamás** se graban en ninguna tabla ni archivo de registro técnico.

---

## Verificación de Estado y Tests

- Endpoint de comprobación de salud:
  ```bash
  curl http://localhost:8000/health
  ```
- Ejecutar suite de pruebas automáticas con pytest:
  ```bash
  pytest -v
  ```
