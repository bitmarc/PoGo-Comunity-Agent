"""Data layer: historial de conversaciones persistido en Postgres.

Se usa `ChainlitDataLayer`, el data layer OFICIAL de Chainlit (asyncpg), contra Neon. El
esquema vive en `infra/db/` y sale de las migraciones del upstream: los nombres de tabla
y columna se consultan literalmente, asi que no se tocan.

Sin `DATABASE_URL` la app corre igual, sin historial. Eso es deliberado: desarrollar no
deberia exigir una base de datos, y un despliegue al que se le cayo la base debe seguir
respondiendo aunque pierda la persistencia.
"""

from __future__ import annotations

import logging

from chainlit.data.base import BaseDataLayer

from hxq_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)

# El data layer se construye una vez por proceso: abre un pool de conexiones.
_data_layer: BaseDataLayer | None = None
_intentado = False


def normalizar_dsn(url: str) -> str:
    """Convierte el DSN al dialecto que espera asyncpg.

    Neon y muchas guias entregan la cadena en formato SQLAlchemy
    (`postgresql+asyncpg://`), que asyncpg no entiende. Tambien se le quita el
    `channel_binding`, que Neon incluye y asyncpg no soporta.
    """
    url = url.strip()
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    url = url.replace("postgres+asyncpg://", "postgresql://", 1)

    if "channel_binding" in url:
        base, _, query = url.partition("?")
        parametros = [p for p in query.split("&") if p and not p.startswith("channel_binding")]
        url = f"{base}?{'&'.join(parametros)}" if parametros else base

    return url


class BaseNoDisponible(RuntimeError):
    """No hay base de datos configurada."""


async def conectar(settings: Settings):
    """Conexion asyncpg suelta para las tablas propias (biblioteca, comunidad).

    Una conexion por operacion y no un pool: son escrituras y lecturas esporadicas de un
    puñado de admins, y un pool abierto contaria contra los limites del plan de Neon.
    """
    import asyncpg

    if not settings.database_url.strip():
        raise BaseNoDisponible("No hay DATABASE_URL configurada.")
    return await asyncpg.connect(normalizar_dsn(settings.database_url))


def build_storage_client(settings: Settings | None = None):
    """Cliente de Blob para los archivos, o None si no esta configurado.

    Sin el, el historial de texto funciona pero los elementos (imagenes, adjuntos) no se
    guardan. Es una degradacion aceptable en local; en produccion se configura.
    """
    settings = settings or get_settings()
    if not (settings.azure_storage_account.strip() and settings.azure_storage_container.strip()):
        return None

    from hxq_agent.storage.blob import ManagedIdentityBlobStorageClient

    logger.info(
        "Blob Storage: cuenta=%s contenedor=%s (Managed Identity)",
        settings.azure_storage_account,
        settings.azure_storage_container,
    )
    return ManagedIdentityBlobStorageClient(
        account=settings.azure_storage_account.strip(),
        container=settings.azure_storage_container.strip(),
    )


def build_data_layer(settings: Settings | None = None) -> BaseDataLayer | None:
    """Data layer de Chainlit, o None si no hay `DATABASE_URL`.

    Cachea el resultado: Chainlit llama al callback en cada conexion y no queremos abrir
    un pool nuevo por usuario.
    """
    global _data_layer, _intentado

    if _intentado:
        return _data_layer
    _intentado = True

    settings = settings or get_settings()
    if not settings.database_url.strip():
        logger.warning(
            "Sin DATABASE_URL: la app corre sin historial. Las conversaciones se pierden "
            "al recargar."
        )
        return None

    from chainlit.data.chainlit_data_layer import ChainlitDataLayer

    try:
        _data_layer = ChainlitDataLayer(
            database_url=normalizar_dsn(settings.database_url),
            storage_client=build_storage_client(settings),
        )
    except Exception:
        logger.exception("No se pudo construir el data layer; se sigue sin historial")
        return None

    logger.info("Historial persistente activo (Postgres)")
    return _data_layer


def reset_para_tests() -> None:
    """Limpia la cache del modulo. Solo para tests."""
    global _data_layer, _intentado
    _data_layer = None
    _intentado = False
