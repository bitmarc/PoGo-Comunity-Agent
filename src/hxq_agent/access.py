"""Decision de acceso: quien puede usar el agente.

Modulo deliberadamente puro: no importa `chainlit` ni toca red, para poder probarlo
sin levantar la app ni configurar OAuth. El binding con Chainlit vive en `auth.py`.
"""

from __future__ import annotations

from typing import Any


def extract_email(raw_user_data: dict[str, Any]) -> str | None:
    """Saca el correo del payload del proveedor, normalizado a minusculas.

    El provider de Google en Chainlit pega a `userinfo/v2/me`, que devuelve `email`.
    Se aceptan las variantes OIDC por si el endpoint cambia o se agrega otro proveedor.
    """
    for key in ("email", "preferred_username", "upn"):
        value = raw_user_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def email_is_verified(raw_user_data: dict[str, Any]) -> bool:
    """False solo si el proveedor dice explicitamente que el correo no esta verificado.

    Si el campo no viene, no podemos afirmar lo contrario y no bloqueamos por ello.
    """
    for key in ("verified_email", "email_verified"):
        if key in raw_user_data:
            value = raw_user_data[key]
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes"}
            return bool(value)
    return True


def is_allowed(email: str | None, allowlist: frozenset[str]) -> bool:
    """True si el correo esta en la allowlist.

    Allowlist vacia niega a todos (fail closed): un despliegue mal configurado no debe
    convertirse en barra libre.
    """
    if not email or not allowlist:
        return False
    return email.strip().lower() in allowlist
