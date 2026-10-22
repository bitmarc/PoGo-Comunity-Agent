"""Biblioteca de contenido: las piezas que el admin aprobo.

Es el activo que se acumula con el uso. Sirve para tres cosas: recuperar lo que ya se
publico, mantener consistencia de estilo, y que el agente no proponga una dinamica que se
hizo hace un mes.

Solo se guarda lo APROBADO. Archivar cada borrador llenaria la tabla de ruido y volveria
inutil la busqueda.

Los binarios van a Blob Storage y la fila a Postgres con su `object_key`. Meter PNGs de
900 KB en la base seria caro y lento de consultar.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from hxq_agent.config import Settings, get_settings
from hxq_agent.storage.db import BaseNoDisponible, conectar

logger = logging.getLogger(__name__)


@dataclass
class Pieza:
    """Una pieza lista para archivar."""

    tipo: str
    titulo: str
    creado_por: str
    contenido: dict[str, Any] = field(default_factory=dict)
    evento_fecha: date | None = None
    imagen: Path | None = None
    prompt: str | None = None
    thread_id: str | None = None


class BibliotecaNoDisponible(BaseNoDisponible):
    """No hay base de datos configurada."""


async def _conectar(settings: Settings):
    try:
        return await conectar(settings)
    except BaseNoDisponible as exc:
        raise BibliotecaNoDisponible(
            "No hay DATABASE_URL configurada, asi que no se puede archivar nada."
        ) from exc


async def _subir_imagen(ruta: Path, settings: Settings) -> str | None:
    """Sube el PNG a Blob y devuelve su object key, o None si no hay storage.

    Sin Blob la fila se guarda igual, solo que sin imagen. Perder el registro entero
    porque falto configurar el storage seria peor que perder la imagen.
    """
    from hxq_agent.storage.db import build_storage_client

    cliente = build_storage_client(settings)
    if cliente is None:
        logger.warning("Sin Blob Storage: la pieza se archiva sin imagen")
        return None

    # Por fecha, para que el contenedor siga siendo navegable cuando haya cientos.
    key = f"piezas/{date.today():%Y/%m}/{uuid.uuid4().hex[:12]}{ruta.suffix}"
    try:
        await cliente.upload_file(key, ruta.read_bytes(), mime="image/png")
        return key
    except Exception:
        logger.exception("Fallo al subir la imagen a Blob")
        return None
    finally:
        cerrar = getattr(cliente, "close", None)
        if cerrar:
            await cerrar()


async def archivar(pieza: Pieza, *, settings: Settings | None = None) -> str:
    """Guarda una pieza aprobada. Devuelve su id."""
    settings = settings or get_settings()
    object_key = await _subir_imagen(pieza.imagen, settings) if pieza.imagen else None

    conexion = await _conectar(settings)
    try:
        fila_id = await conexion.fetchval(
            """
            INSERT INTO pieza (tipo, titulo, contenido, evento_fecha, imagen_object_key,
                               prompt, creado_por, thread_id, aprobada)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, TRUE)
            RETURNING id
            """,
            pieza.tipo,
            pieza.titulo,
            json.dumps(pieza.contenido, ensure_ascii=False),
            pieza.evento_fecha,
            object_key,
            pieza.prompt,
            pieza.creado_por,
            pieza.thread_id,
        )
    finally:
        await conexion.close()

    logger.info("Pieza archivada: %s (%s) por %s", pieza.titulo, fila_id, pieza.creado_por)
    return str(fila_id)


async def buscar(
    consulta: str = "",
    *,
    tipo: str | None = None,
    limite: int = 5,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Busca en lo ya publicado.

    Usa busqueda de texto en espanol sobre titulo y prompt. Sin consulta, devuelve lo mas
    reciente, que es lo que se quiere para "que publicamos ultimamente".
    """
    settings = settings or get_settings()
    conexion = await _conectar(settings)
    try:
        if consulta.strip():
            filas = await conexion.fetch(
                """
                SELECT id, tipo, titulo, contenido, evento_fecha, creado_en, creado_por
                FROM pieza
                WHERE aprobada
                  AND ($2::text IS NULL OR tipo = $2)
                  AND to_tsvector('spanish', coalesce(titulo,'') || ' ' || coalesce(prompt,''))
                      @@ plainto_tsquery('spanish', $1)
                ORDER BY creado_en DESC
                LIMIT $3
                """,
                consulta.strip(),
                tipo,
                limite,
            )
        else:
            filas = await conexion.fetch(
                """
                SELECT id, tipo, titulo, contenido, evento_fecha, creado_en, creado_por
                FROM pieza
                WHERE aprobada AND ($1::text IS NULL OR tipo = $1)
                ORDER BY creado_en DESC
                LIMIT $2
                """,
                tipo,
                limite,
            )
    finally:
        await conexion.close()

    return [dict(f) for f in filas]
