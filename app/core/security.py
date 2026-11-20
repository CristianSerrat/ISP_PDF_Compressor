"""Funciones de seguridad, validación de archivos e identificación anónima."""

import hashlib
import ipaddress
import re
import unicodedata
from fastapi import Request


def validate_pdf_magic_bytes(header: bytes) -> bool:
    """Verifica que el archivo comience con la cabecera estándar de PDF."""
    # Los PDFs válidos suelen comenzar con %PDF- en los primeros 1024 bytes
    return b"%PDF-" in header[:1024]


def validate_image_magic_bytes(header: bytes) -> str | None:
    """Verifica si los bytes corresponden a una imagen válida (PNG, JPEG, WebP)."""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def sanitize_filename(filename: str, default_name: str = "documento.pdf") -> str:
    """
    Sanitiza un nombre de archivo para evitar Path Traversal y caracteres peligrosos.
    No almacena ni preserva rutas absolutas o relativas.
    """
    if not filename:
        return default_name

    # Normalizar Unicode y quitar componentes de ruta
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.replace("\\", "/").split("/")[-1]

    # Eliminar caracteres no alfanuméricos salvo puntos, guiones y guiones bajos
    clean_name = re.sub(r"[^\w\s\.-]", "", filename).strip()
    clean_name = re.sub(r"\s+", "_", clean_name)

    if not clean_name or clean_name.startswith("."):
        return default_name

    # Limitar longitud razonable
    if len(clean_name) > 100:
        parts = clean_name.rsplit(".", 1)
        if len(parts) == 2:
            clean_name = parts[0][:90] + "." + parts[1]
        else:
            clean_name = clean_name[:100]

    return clean_name


def extract_client_ip(request: Request, trust_proxy: bool) -> str:
    """Extrae la IP del cliente respetando X-Forwarded-For solo si trust_proxy está activo."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Tomar la primera IP de la lista
            ip = forwarded.split(",")[0].strip()
            try:
                ipaddress.ip_address(ip)
                return ip
            except ValueError:
                pass

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            try:
                ipaddress.ip_address(real_ip.strip())
                return real_ip.strip()
            except ValueError:
                pass

    if request.client and request.client.host:
        if request.client.host == "testclient":
            return "127.0.0.1"
        return request.client.host
    return "127.0.0.1"


def get_client_identifier(request: Request, mode: str, trust_proxy: bool, salt: str) -> str:
    """
    Genera el identificador del cliente según el modo de registro configurado:
    - 'none': "anon"
    - 'ip': Dirección IP real
    - 'hash': Hash SHA-256 salado (truncado a 16 caracteres para privacidad)
    """
    if mode == "none":
        return "anon"

    ip = extract_client_ip(request, trust_proxy)
    if mode == "ip":
        return ip

    # Modo 'hash' (por defecto)
    combined = f"{salt}:{ip}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()[:16]
