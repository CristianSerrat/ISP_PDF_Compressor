"""Dependencias comunes para FastAPI, incluyendo verificación de redes permitidas para /admin."""

import ipaddress
import logging
from fastapi import HTTPException, Request, status
from app.config import settings
from app.core.security import extract_client_ip, verify_admin_session_token

logger = logging.getLogger("pdf_app")


def verify_admin_network(request: Request) -> None:
    """
    Verifica que la dirección IP del cliente pertenezca a las redes autorizadas
    definidas en ADMIN_ALLOWED_NETWORKS si dicha variable está configurada.
    """
    networks = settings.admin_networks_list
    if not networks:
        # Si la lista está vacía, no se filtra por IP (se confía en la clave de administrador)
        return

    client_ip_str = extract_client_ip(request, settings.TRUST_PROXY)
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        logger.warning(f"Acceso a /admin denegado: IP del cliente no válida '{client_ip_str}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. IP no válida."
        )

    allowed = False
    for net_str in networks:
        try:
            network = ipaddress.ip_network(net_str, strict=False)
            if client_ip in network:
                allowed = True
                break
        except ValueError:
            continue

    if not allowed:
        logger.warning("Intento de acceso denegado a /admin desde IP no autorizada.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. Tu red no tiene permisos para acceder al panel de administración."
        )


def verify_admin_access(request: Request) -> None:
    """
    Verifica que el usuario tenga una sesión activa y válida de administrador
    mediante cookie o cabecera firmada.
    """
    # 1. Verificar red si aplica
    verify_admin_network(request)

    # 2. Verificar token de sesión
    token = request.cookies.get("admin_session")
    if not token:
        # Permitir token en header de autorización o query param para descargas directas
        token = request.headers.get("x-admin-token") or request.query_params.get("admin_token")

    if not token or not verify_admin_session_token(token, settings.SECRET_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso restringido. Se requiere autenticación de administrador."
        )
