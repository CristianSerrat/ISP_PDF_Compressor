"""Dependencias comunes para FastAPI, incluyendo verificación de redes permitidas para /admin."""

import ipaddress
import logging
from fastapi import HTTPException, Request, status
from app.config import settings
from app.core.security import extract_client_ip

logger = logging.getLogger("pdf_app")


def verify_admin_network(request: Request) -> None:
    """
    Verifica que la dirección IP del cliente pertenezca a las redes autorizadas
    definidas en ADMIN_ALLOWED_NETWORKS. Devuelve 403 Forbidden si no está permitida.
    """
    client_ip_str = extract_client_ip(request, settings.TRUST_PROXY)

    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        logger.warning(f"Acceso a /admin denegado: IP del cliente no válida '{client_ip_str}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. IP no autorizada."
        )

    allowed = False
    for net_str in settings.admin_networks_list:
        try:
            network = ipaddress.ip_network(net_str, strict=False)
            if client_ip in network:
                allowed = True
                break
        except ValueError:
            logger.error(f"Configuración inválida en ADMIN_ALLOWED_NETWORKS: '{net_str}'")
            continue

    if not allowed:
        # Nota: no registramos la IP en un log público sensible, solo en log técnico si nivel debug/info
        logger.warning(f"Intento de acceso denegado a /admin desde IP no autorizada.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. Tu red no tiene permisos para acceder al panel de administración."
        )
