"""Tool de generacion de piezas graficas.

El agente decide QUE dice la pieza; esta tool decide COMO se ve. Los datos pasan por un
modelo Pydantic antes de dibujarse, asi que un campo que falta se convierte en un error
que el agente puede relayar como pregunta, y no en una pieza con un hueco publicada a la
comunidad.

El arte central es opcional y lo dibuja gpt-image. Nunca escribe texto: fecha, hora y
lugar los pone la plantilla HTML.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field, ValidationError

from hxq_agent.brand.arte import ArteError, como_data_uri, generar_arte
from hxq_agent.brand.pokemon import PokemonNoEncontrado, obtener_pokemon
from hxq_agent.brand.render import renderizar
from hxq_agent.schemas.piezas import PLANTILLAS

logger = logging.getLogger(__name__)

# Las piezas se escriben aqui y la UI las recoge. En Fase 4 pasan a Blob Storage al
# aprobarse; mientras tanto viven el tiempo que viva el contenedor.
DIR_SALIDA = Path.cwd() / "out" / "piezas"


def _contexto(pieza: Any) -> dict[str, Any]:
    """Aplana el modelo mas sus propiedades calculadas para la plantilla."""
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
    return ctx


def _explicar_errores(exc: ValidationError) -> str:
    """Convierte los errores de Pydantic en algo que el agente pueda preguntar.

    Un volcado crudo de Pydantic es ilegible para el modelo y acaba en una respuesta
    del tipo "hubo un error"; esto le dice exactamente que campo pedir.
    """
    lineas = []
    for err in exc.errors():
        campo = ".".join(str(x) for x in err["loc"]) or "(raiz)"
        lineas.append(f"- {campo}: {err['msg']}")
    return "\n".join(lineas)


@tool
async def render_pieza(
    plantilla: Annotated[
        str,
        Field(
            description=(
                "Que pieza generar. 'quedada' para una quedada de la comunidad (exige "
                "lugar, fecha y hora). 'anuncio_evento' para un evento oficial (exige "
                "fecha_inicio, y admite bonus)."
            )
        ),
    ],
    datos: Annotated[
        str,
        Field(
            description=(
                "JSON con los datos de la pieza. Comun: titulo, subtitulo, tipos "
                "(lista de tipos del Pokemon protagonista; de ahi salen los colores). "
                "quedada: lugar, fecha (aaaa-mm-dd), hora_inicio (HH:MM), hora_fin, "
                "detalles (lista). anuncio_evento: fecha_inicio, fecha_fin, "
                "hora_inicio, hora_fin, bonus (lista)."
            )
        ),
    ],
    pokemon: Annotated[
        str,
        Field(
            description=(
                "Nombre del Pokemon protagonista, si la pieza tiene uno. Trae su arte "
                "OFICIAL y sus tipos reales de PokeAPI, y de esos tipos salen los "
                "colores de la pieza. Preferible a describir arte: es el Pokemon que "
                "la gente espera ver. Formas especiales: 'charizard-mega-y', "
                "'deoxys-attack'. Dejalo vacio si la pieza no lleva Pokemon."
            )
        ),
    ] = "",
    descripcion_arte: Annotated[
        str,
        Field(
            description=(
                "Escena para la ilustracion central, en una frase. Solo se usa si NO "
                "hay `pokemon`. Dejala vacia si no quieres arte. IMPORTANTE: no "
                "menciones Pokemon ni nombres de Pokemon: "
                "el filtro de Azure rechaza generar propiedad intelectual y la pieza "
                "sale sin arte. Describe la escena de otro modo: entrenadores, amigos "
                "con gorras, criaturas fantasticas, paisajes."
            )
        ),
    ] = "",
) -> str:
    """Genera la imagen de una pieza con el branding de la comunidad.

    Devuelve la ruta del PNG. Los datos duros (fecha, hora, lugar) se dibujan como texto
    real, no los escribe un modelo de imagen, asi que salen siempre exactos.
    """
    modelo = PLANTILLAS.get(plantilla)
    if modelo is None:
        return (
            f"No existe la plantilla '{plantilla}'. Disponibles: {', '.join(sorted(PLANTILLAS))}."
        )

    try:
        crudo = json.loads(datos)
    except json.JSONDecodeError as exc:
        return f"Los datos no son JSON valido: {exc}. Reintenta con un JSON bien formado."

    try:
        pieza = modelo(**crudo)
    except ValidationError as exc:
        return (
            "Faltan datos o son invalidos para esta pieza:\n"
            f"{_explicar_errores(exc)}\n"
            "Preguntale al admin lo que falte antes de reintentar. No lo inventes."
        )

    aviso_arte = ""

    # El arte oficial gana sobre el generado: es el Pokemon que la gente espera ver, y
    # ademas sus tipos reales fijan los colores de la pieza.
    if pokemon.strip():
        try:
            datos_pkmn = await obtener_pokemon(pokemon)
            if datos_pkmn["arte"]:
                pieza.imagen_hero = como_data_uri(datos_pkmn["arte"])
            if datos_pkmn["tipos"] and not pieza.tipos:
                pieza.tipos = datos_pkmn["tipos"][:2]
        except PokemonNoEncontrado as exc:
            return f"{exc}\nPreguntale al admin como se escribe antes de reintentar."
        except Exception as exc:
            logger.warning("Fallo PokeAPI para %s: %s", pokemon, exc)
            aviso_arte = "\n\nNOTA: no se pudo traer el arte oficial; la pieza va sin imagen."
    elif descripcion_arte.strip():
        try:
            png_arte = await generar_arte(descripcion_arte)
            pieza.imagen_hero = como_data_uri(png_arte)
        except ArteError as exc:
            # El arte es opcional: sin el la pieza sigue siendo correcta y publicable.
            logger.warning("Sin arte para la pieza: %s", exc)
            if "moderation" in str(exc):
                aviso_arte = (
                    "\n\nNOTA: el filtro de Azure rechazo la ilustracion, casi seguro por "
                    "mencionar propiedad intelectual. La pieza se genero sin arte. Puedes "
                    "reintentar describiendo la escena sin nombrar Pokemon."
                )
            else:
                aviso_arte = "\n\nNOTA: no se pudo generar la ilustracion; la pieza va sin arte."

    try:
        png = await renderizar(plantilla, _contexto(pieza))
    except Exception as exc:
        logger.exception("Fallo el render de la pieza")
        return f"No se pudo dibujar la pieza: {exc}"

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    destino = DIR_SALIDA / f"{plantilla}_{uuid.uuid4().hex[:8]}.png"
    destino.write_bytes(png)
    logger.info("Pieza generada: %s (%d KB)", destino.name, len(png) // 1024)

    return (
        f"Pieza '{plantilla}' generada: {destino}\n"
        f"Titulo: {pieza.titulo}\n"
        f"Formato: 1240x1240 (cuadrado, como las piezas de la comunidad)"
        f"{aviso_arte}\n\n"
        "La imagen ya se le muestra al admin. Resumele que contiene y preguntale si "
        "quiere cambios; no la describas campo por campo."
    )
