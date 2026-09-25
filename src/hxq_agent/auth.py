"""Binding de autenticacion con Chainlit.

Importar este modulo REGISTRA el callback de OAuth, y Chainlit exige que al menos un
proveedor este configurado por entorno (`OAUTH_GOOGLE_CLIENT_ID` / `_SECRET`). Si faltan,
falla al arrancar con un mensaje claro, que es el comportamiento que queremos: mejor no
arrancar que arrancar sin puerta.

La logica de quien pasa vive en `hxq_agent.access`, sin dependencia de Chainlit.
"""

from __future__ import annotations

import logging

import chainlit as cl

from hxq_agent.access import email_is_verified, extract_email, is_allowed
from hxq_agent.config import get_settings

logger = logging.getLogger(__name__)


@cl.oauth_callback
async def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict[str, str],
    default_user: cl.User,
    id_token: str | None = None,
) -> cl.User | None:
    """Devuelve el usuario si esta autorizado, o None para rechazar el login."""
    settings = get_settings()
    email = extract_email(raw_user_data)

    if not email_is_verified(raw_user_data):
        logger.warning(
            "Login rechazado: correo sin verificar (%s, provider=%s)", email, provider_id
        )
        return None

    if not is_allowed(email, settings.admin_emails):
        logger.warning("Login rechazado: %s no esta en HXQ_ADMIN_EMAILS", email)
        return None

    default_user.metadata = {
        **(default_user.metadata or {}),
        "email": email,
        "role": "admin",
        "provider": provider_id,
    }
    logger.info("Login autorizado: %s", email)
    return default_user
