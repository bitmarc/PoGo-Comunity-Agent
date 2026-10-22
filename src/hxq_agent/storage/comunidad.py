"""Datos propios de la comunidad en Postgres (tabla `dato_comunidad`).

Este modulo no valida: guarda lo que le dan. La validacion vive en
`schemas/comunidad.py` y la hace quien prepara el cambio, antes de que el admin lo
confirme. Asi lo que se le enseña al admin en el boton es exactamente lo que se escribe.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hxq_agent.config import Settings, get_settings
from hxq_agent.schemas.comunidad import TEMAS, normalizar
from hxq_agent.storage.db import BaseNoDisponible, conectar

logger = logging.getLogger(__name__)


class ComunidadNoDisponible(BaseNoDisponible):
    """No hay base de datos configurada."""


async def _conectar(settings: Settings):
    try:
        return await conectar(settings)
    except BaseNoDisponible as exc:
        raise ComunidadNoDisponible(
            "No hay DATABASE_URL configurada, asi que no hay datos de la comunidad."
        ) from exc


def _datos(valor: Any) -> dict[str, Any]:
    # asyncpg devuelve JSONB como str si no se registro un codec.
    return json.loads(valor) if isinstance(valor, str) else dict(valor or {})


async def listar(tema: str, *, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Los registros vigentes de un tema, por nombre."""
    settings = settings or get_settings()
    conexion = await _conectar(settings)
    try:
        filas = await conexion.fetch(
            """
            SELECT datos FROM dato_comunidad
            WHERE tema = $1 AND eliminado_en IS NULL
            ORDER BY lower(nombre)
            """,
            tema,
        )
    finally:
        await conexion.close()
    return [_datos(f["datos"]) for f in filas]


async def obtener(
    tema: str, nombre: str, *, settings: Settings | None = None
) -> dict[str, Any] | None:
    """Un registro vigente por su nombre, sin distinguir mayusculas ni acentos.

    En Python y no con `lower()` en SQL: el admin escribe "jardin" y el registro se
    llama "Jardín". Son decenas de filas por tema, traerlas todas no cuesta nada.
    """
    clave = TEMAS[tema].clave
    buscado = normalizar(nombre)
    for fila in await listar(tema, settings=settings):
        if normalizar(str(fila.get(clave, ""))) == buscado:
            return fila
    return None


async def guardar(
    tema: str,
    nombre_actual: str | None,
    datos: dict[str, Any],
    *,
    nombre: str,
    por: str,
    settings: Settings | None = None,
) -> None:
    """Crea o actualiza un registro. Si estaba borrado, lo restaura.

    `nombre_actual` es la clave del registro que se edita, o None si es nuevo. Puede
    diferir de `nombre` cuando el cambio es un renombrado.
    """
    settings = settings or get_settings()
    conexion = await _conectar(settings)
    try:
        async with conexion.transaction():
            if nombre_actual and nombre_actual.strip().lower() != nombre.strip().lower():
                # Renombrado: se libera la clave vieja para no dejar el registro duplicado.
                await conexion.execute(
                    """
                    DELETE FROM dato_comunidad
                    WHERE tema = $1 AND lower(nombre) = lower($2)
                    """,
                    tema,
                    nombre_actual.strip(),
                )
            await conexion.execute(
                """
                INSERT INTO dato_comunidad (tema, nombre, datos, actualizado_por)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT (tema, lower(nombre)) DO UPDATE
                SET nombre = EXCLUDED.nombre,
                    datos = EXCLUDED.datos,
                    actualizado_por = EXCLUDED.actualizado_por,
                    actualizado_en = now(),
                    eliminado_en = NULL
                """,
                tema,
                nombre.strip(),
                json.dumps(datos, ensure_ascii=False),
                por,
            )
    finally:
        await conexion.close()
    logger.info("Dato de comunidad guardado: %s/%s por %s", tema, nombre, por)


async def eliminar(tema: str, nombre: str, *, por: str, settings: Settings | None = None) -> bool:
    """Borrado logico. Devuelve False si no habia nada vigente con ese nombre."""
    settings = settings or get_settings()
    conexion = await _conectar(settings)
    try:
        resultado = await conexion.execute(
            """
            UPDATE dato_comunidad
            SET eliminado_en = now(), actualizado_en = now(), actualizado_por = $3
            WHERE tema = $1 AND lower(nombre) = lower($2) AND eliminado_en IS NULL
            """,
            tema,
            nombre.strip(),
            por,
        )
    finally:
        await conexion.close()
    borrado = resultado.endswith(" 1")
    if borrado:
        logger.info("Dato de comunidad eliminado: %s/%s por %s", tema, nombre, por)
    return borrado
