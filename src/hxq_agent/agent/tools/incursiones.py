"""Tool de infografias de incursion.

A diferencia de las demas piezas, aqui el agente casi no escribe datos: aporta el titulo,
el horario y las notas, y todo lo demas (PC, debilidades, counters, megas) lo reune
`brand/incursion.py` de Pokebattler y PokeAPI. Eso es deliberado: son datos que el modelo
no puede saber y que, si los inventara, se publicarian a toda la comunidad.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, time
from pathlib import Path
from typing import Annotated

import httpx
from agent_framework import tool
from pydantic import Field, ValidationError

from hxq_agent.brand.arte import como_data_uri
from hxq_agent.brand.incursion import JefeNoEncontrado, reunir
from hxq_agent.brand.pokebattler import PokebattlerError, rotacion
from hxq_agent.brand.pokemon import ARTE, UA
from hxq_agent.brand.render import renderizar
from hxq_agent.config import get_settings
from hxq_agent.schemas.piezas import InfografiaRaid

logger = logging.getLogger(__name__)

# Nombres de tier que entiende Pokebattler, con los alias que usa la gente.
TIERS = {
    "1": "RAID_LEVEL_1",
    "3": "RAID_LEVEL_3",
    "5": "RAID_LEVEL_5",
    "mega": "RAID_LEVEL_MEGA",
    "elite": "RAID_LEVEL_MEGA_5",
}


async def _arte_oficial(numero: int) -> str | None:
    if not numero:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as cliente:
            resp = await cliente.get(ARTE.format(id=numero), headers={"User-Agent": UA})
        return como_data_uri(resp.content) if resp.status_code == 200 else None
    except httpx.HTTPError:
        return None


@tool
async def jefes_de_incursion() -> str:
    """Lista los jefes de incursion activos ahora mismo, por nivel.

    Usala cuando el admin pregunte que hay en incursiones, o si no esta seguro de como
    se escribe un jefe antes de pedir su infografia.
    """
    try:
        rot = await rotacion()
    except PokebattlerError as exc:
        return f"No pude consultar la rotacion de incursiones: {exc}"

    if not rot:
        return "Pokebattler no devolvio ninguna incursion activa."

    lineas = ["Incursiones activas:"]
    for tier, jefes in rot.items():
        etiqueta = tier.replace("RAID_LEVEL_", "Nivel ").replace("_", " ").title()
        nombres = ", ".join(j.replace("_", " ").title() for j in jefes[:10])
        lineas.append(f"- {etiqueta}: {nombres}")
    lineas.append("\nDatos de Pokébattler.")
    return "\n".join(lineas)


@tool
async def infografia_incursion(
    jefe: Annotated[
        str,
        Field(
            description=(
                "Nombre del jefe de incursion, por ejemplo 'Groudon' o 'Xerneas'. "
                "Si no estas seguro de como se escribe, llama antes a "
                "jefes_de_incursion."
            )
        ),
    ],
    titulo: Annotated[
        str,
        Field(
            description=(
                "Titulo de la pieza, por ejemplo 'Hora Legendaria Groudon' o "
                "'Groudon en incursiones'."
            )
        ),
    ],
    subtitulo: Annotated[str, Field(description="Una linea de contexto. Opcional.")] = "",
    nivel: Annotated[
        str, Field(description="Nivel de la incursion: 1, 3, 5, mega. Por defecto 5.")
    ] = "5",
    fecha: Annotated[str, Field(description="Fecha en aaaa-mm-dd. Opcional.")] = "",
    hora_inicio: Annotated[str, Field(description="Hora de inicio en HH:MM. Opcional.")] = "",
    hora_fin: Annotated[str, Field(description="Hora de fin en HH:MM. Opcional.")] = "",
    notas: Annotated[
        str,
        Field(
            description=(
                "Hasta cuatro notas cortas separadas por punto y coma, por ejemplo "
                "'Puede salir variocolor; Mejor en clima soleado'. Opcional."
            )
        ),
    ] = "",
) -> str:
    """Genera la infografia de un jefe de incursion con sus counters y datos reales.

    Los puntos de combate, las debilidades, los counters con sus movimientos y las megas
    recomendadas se traen de Pokébattler y PokéAPI. TU no los escribes ni los estimas:
    son datos que se publican a la comunidad y tienen que ser exactos.
    """
    tier = TIERS.get(nivel.strip().lower(), "RAID_LEVEL_5")

    try:
        datos = await reunir(jefe, tier=tier)
    except JefeNoEncontrado as exc:
        return f"{exc}\nLlama a jefes_de_incursion para ver los nombres exactos."
    except PokebattlerError as exc:
        return (
            f"No pude traer los datos de incursion: {exc}\n"
            "No inventes counters ni puntos de combate; dile al admin que lo reintente."
        )

    def _fecha(txt: str) -> date | None:
        try:
            return date.fromisoformat(txt.strip()) if txt.strip() else None
        except ValueError:
            return None

    def _hora(txt: str) -> time | None:
        try:
            return time.fromisoformat(txt.strip()) if txt.strip() else None
        except ValueError:
            return None

    try:
        pieza = InfografiaRaid(
            titulo=titulo,
            subtitulo=subtitulo,
            tipos=datos.tipos,
            pc_normal=f"{datos.pc_normal[0]} - {datos.pc_normal[1]}",
            pc_potenciado=f"{datos.pc_potenciado[0]} - {datos.pc_potenciado[1]}",
            debilidades=datos.debilidades,
            counters=[{"nombre": c.nombre, "movimientos": c.movimientos} for c in datos.counters],
            megas=[{"nombre": m.nombre} for m in datos.megas],
            atribucion=datos.atribucion,
            fecha=_fecha(fecha),
            hora_inicio=_hora(hora_inicio),
            hora_fin=_hora(hora_fin),
            notas=[n.strip() for n in notas.split(";") if n.strip()][:4],
            imagen_hero=await _arte_oficial(datos.numero),
        )
    except ValidationError as exc:
        return f"Los datos de la pieza no son validos: {exc.errors()[:2]}"

    ctx = pieza.model_dump()
    ctx.update(
        {
            "acento_1": pieza.acentos[0],
            "acento_2": pieza.acentos[1],
            "escala_titulo": pieza.escala_titulo,
            "escala_subtitulo": pieza.escala_subtitulo,
            "fecha_texto": pieza.fecha_texto,
            "horario_texto": pieza.horario_texto,
        }
    )

    try:
        png = await renderizar("infografia_raid", ctx)
    except Exception as exc:
        logger.exception("Fallo el render de la infografia de incursion")
        return f"No se pudo dibujar la infografia: {exc}"

    destino = get_settings().subdir("piezas") / f"infografia_raid_{uuid.uuid4().hex[:8]}.png"
    Path(destino).write_bytes(png)
    logger.info("Infografia de %s generada: %s", datos.nombre, destino.name)

    return (
        f"Infografía de incursión generada: {destino}\n"
        f"Titulo: {titulo}\n"
        f"Jefe: {datos.nombre} · PC {pieza.pc_normal} (potenciado {pieza.pc_potenciado})\n"
        f"Debilidades: {', '.join(datos.debilidades) or 'sin datos'}\n"
        f"Counters: {', '.join(c.nombre for c in datos.counters)}\n\n"
        "La imagen ya se le muestra al admin. Resumele que contiene en dos lineas y "
        "menciona que los datos vienen de Pokébattler."
    )
