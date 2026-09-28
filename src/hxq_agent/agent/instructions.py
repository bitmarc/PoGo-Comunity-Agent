"""Carga del system prompt.

El prompt vive en `prompt.md`, no aqui. Es contenido, no codigo: son 136 lineas que se
iteran constantemente y que quien ajusta el tono del agente tiene que poder leer y editar
sin abrir un archivo de Python ni preocuparse por comillas y escapes.

Este modulo solo lo lee y sustituye los placeholders.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from hxq_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)

RUTA_PROMPT = Path(__file__).parent / "prompt.md"

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# El comentario HTML de cabecera documenta los placeholders para quien edite el archivo,
# pero no es parte del prompt: gastaria tokens en cada turno sin decirle nada al modelo.
_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.DOTALL)

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class PromptNoDisponible(RuntimeError):
    """No se pudo leer `prompt.md`."""


def leer_prompt(ruta: Path | None = None) -> str:
    """Contenido de `prompt.md`, sin el comentario de cabecera.

    Se lee en cada llamada y no se cachea a proposito: en local con `chainlit run -w`
    eso hace que editar el archivo aplique al siguiente mensaje, sin reiniciar. Son
    unos 6 KB; el coste es irrelevante frente a una llamada al modelo.
    """
    ruta = ruta or RUTA_PROMPT
    try:
        crudo = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptNoDisponible(
            f"No pude leer el system prompt en {ruta}. Sin el, el agente no sabe que hacer."
        ) from exc

    return _COMENTARIO_HTML.sub("", crudo).strip()


def version_prompt(ruta: Path | None = None) -> str:
    """Huella del contenido del prompt.

    Se deriva del texto en vez de mantenerse a mano: un numero de version que hay que
    acordarse de subir acaba mintiendo en cuanto alguien edita el archivo y se olvida.
    Sirve para correlacionar una respuesta rara con la version del prompt que la produjo.
    """
    return hashlib.sha256(leer_prompt(ruta).encode("utf-8")).hexdigest()[:12]


def sustituir(plantilla: str, valores: dict[str, str]) -> str:
    """Sustituye `{{clave}}` por su valor.

    Con `re.sub` y no con `str.format`: el archivo lo edita una persona, y `format`
    revienta con un `KeyError` en cuanto aparece una llave suelta en el texto (un
    ejemplo de JSON, una nota entre llaves). Un placeholder desconocido se deja tal
    cual, visible, en vez de tumbar el agente.
    """
    desconocidos: list[str] = []

    def _reemplazar(m: re.Match[str]) -> str:
        clave = m.group(1)
        if clave in valores:
            return valores[clave]
        desconocidos.append(clave)
        return m.group(0)

    salida = _PLACEHOLDER.sub(_reemplazar, plantilla)
    if desconocidos:
        logger.warning(
            "prompt.md usa placeholders que no existen: %s. Se dejan sin sustituir.",
            ", ".join(sorted(set(desconocidos))),
        )
    return salida


def build_instructions(settings: Settings | None = None, *, now: datetime | None = None) -> str:
    """System prompt listo, con la fecha y el contexto de comunidad resueltos."""
    settings = settings or get_settings()
    tz = ZoneInfo(settings.hxq_timezone)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        # Un datetime sin tz se interpreta como hora local de la comunidad, no del servidor.
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    return sustituir(
        leer_prompt(),
        {
            "community": settings.hxq_community_name,
            "city": settings.hxq_community_city,
            "timezone": settings.hxq_timezone,
            "today": now.strftime("%d/%m/%Y"),
            "weekday": _DIAS[now.weekday()],
        },
    )
