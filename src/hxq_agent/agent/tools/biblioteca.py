"""Consulta de la biblioteca de contenido.

Lo que el agente puede saber de lo que la comunidad ya publico. Sirve sobre todo para no
repetirse: proponer la misma dinamica que se hizo hace un mes es peor que no proponer
nada, porque quema la idea y desgasta a la gente.

Solo ve piezas APROBADAS. Los borradores que el admin descarto no deberian influir en lo
que el agente propone despues.
"""

from __future__ import annotations

import logging
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from hxq_agent.storage.biblioteca import BibliotecaNoDisponible, buscar

logger = logging.getLogger(__name__)

_MAX = 8


@tool
async def buscar_en_biblioteca(
    consulta: Annotated[
        str,
        Field(
            description=(
                "Que buscar entre lo ya publicado, en lenguaje natural. Dejala vacia "
                "para ver lo mas reciente."
            )
        ),
    ] = "",
    tipo: Annotated[
        str,
        Field(
            description=(
                "Filtrar por tipo: 'quedada', 'anuncio_evento', 'dinamica'. Vacio para no filtrar."
            )
        ),
    ] = "",
) -> str:
    """Consulta que ha publicado ya la comunidad.

    Usala ANTES de proponer una dinamica o un concurso, para no repetir algo reciente.
    Tambien sirve para mantener el estilo: mirar como se redactaron avisos parecidos.
    """
    try:
        filas = await buscar(consulta, tipo=tipo.strip() or None, limite=_MAX)
    except BibliotecaNoDisponible as exc:
        return (
            f"La biblioteca no esta disponible: {exc} "
            "Sigue adelante sin consultarla, pero avisa de que no pudiste comprobar "
            "si algo se repite."
        )
    except Exception as exc:
        logger.exception("Fallo al consultar la biblioteca")
        return f"No pude consultar la biblioteca: {exc}"

    if not filas:
        if consulta.strip():
            return (
                f"No hay nada archivado que coincida con '{consulta}'. "
                "Es tema nuevo: no hay riesgo de repetirse."
            )
        return (
            "La biblioteca esta vacia todavia. Se llena cuando el admin aprueba una "
            "pieza; no hay historico contra el que comparar."
        )

    lineas = [f"{len(filas)} pieza(s) en la biblioteca:", ""]
    for f in filas:
        fecha = f["evento_fecha"] or f["creado_en"].date()
        lineas.append(f"## {f['titulo']}")
        lineas.append(f"Tipo: {f['tipo']} · Fecha: {fecha} · Por: {f['creado_por']}")
        contenido = f["contenido"]
        if isinstance(contenido, str):
            import json

            contenido = json.loads(contenido)
        for canal, texto in (contenido or {}).items():
            lineas.append(f"- {canal}: {' '.join(str(texto).split())[:160]}")
        lineas.append("")

    return "\n".join(lineas).strip()
