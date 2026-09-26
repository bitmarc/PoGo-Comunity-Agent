"""Archivo `.ics` para agendar una quedada.

Un `.ics` y no la API de Google Calendar: no exige credenciales, funciona con Google,
Apple y Outlook por igual, y se puede reenviar por WhatsApp como cualquier adjunto. La
integracion con Google Calendar queda para cuando duela lo suficiente.

La zona horaria es la de la comunidad, no la del servidor. Un evento creado en un
contenedor en UTC que se agenda seis horas tarde es peor que no tener calendario.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from agent_framework import tool
from pydantic import Field

from hxq_agent.config import get_settings

logger = logging.getLogger(__name__)

DIR_SALIDA = Path.cwd() / "out" / "calendario"

# Duracion por defecto cuando no se da hora de fin. Dos horas es lo que suele durar una
# quedada; dejarlo sin fin hace que algunos calendarios lo muestren como evento de dia
# completo, que no es lo que se quiere.
DURACION_POR_DEFECTO = timedelta(hours=2)


def nombre_archivo(titulo: str) -> str:
    """Titulo -> nombre de archivo seguro, sin acentos ni caracteres raros."""
    limpio = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9]+", "-", limpio).strip("-").lower()
    return (limpio or "quedada")[:60]


def construir_ics(
    *,
    titulo: str,
    lugar: str,
    inicio: datetime,
    fin: datetime,
    descripcion: str = "",
) -> bytes:
    """Genera el contenido del `.ics`.

    Separado de la tool para poder probarlo sin pasar por el agente.
    """
    from icalendar import Calendar, Event

    cal = Calendar()
    # PRODID es obligatorio en RFC 5545; sin el, algunos clientes rechazan el archivo.
    cal.add("prodid", "-//HuixquiGo//Agente de comunidad//ES")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")

    evento = Event()
    evento.add("summary", titulo)
    evento.add("dtstart", inicio)
    evento.add("dtend", fin)
    evento.add("dtstamp", datetime.now(inicio.tzinfo))
    evento.add("location", lugar)
    if descripcion:
        evento.add("description", descripcion)
    # UID unico: sin el, importar dos quedadas distintas puede sobrescribir una.
    evento.add("uid", f"{uuid.uuid4()}@huixquigo")

    cal.add_component(evento)
    return cal.to_ical()


@tool
async def crear_ics(
    titulo: Annotated[
        str, Field(description="Nombre del evento tal como aparecera en el calendario.")
    ],
    lugar: Annotated[str, Field(description="Donde es. Aparece en el campo de ubicacion.")],
    fecha: Annotated[
        str, Field(description="Fecha en formato aaaa-mm-dd. Resuelvela tu antes de llamar.")
    ],
    hora_inicio: Annotated[
        str, Field(description="Hora de inicio en formato HH:MM de 24 horas, por ejemplo 18:00.")
    ],
    hora_fin: Annotated[
        str,
        Field(
            description=(
                "Hora de fin en HH:MM de 24 horas. Dejala vacia si no se sabe: se asumen "
                "dos horas de duracion."
            )
        ),
    ] = "",
    descripcion: Annotated[
        str, Field(description="Detalle que vera quien agende: que llevar, punto de reunion.")
    ] = "",
) -> str:
    """Genera un archivo .ics para agendar la quedada en cualquier calendario.

    Sirve para Google, Apple y Outlook, y se puede reenviar por WhatsApp. Usalo cuando la
    quedada ya tenga fecha, hora y lugar confirmados.
    """
    settings = get_settings()

    try:
        dia = date.fromisoformat(fecha.strip())
    except ValueError:
        return f"La fecha {fecha!r} no es valida. Mandala como aaaa-mm-dd, por ejemplo 2026-10-04."

    def _hora(texto: str) -> time | None:
        try:
            return time.fromisoformat(texto.strip())
        except ValueError:
            return None

    inicio_t = _hora(hora_inicio)
    if inicio_t is None:
        return (
            f"La hora {hora_inicio!r} no es valida. "
            "Mandala como HH:MM de 24 horas, por ejemplo 18:00."
        )

    tz = ZoneInfo(settings.hxq_timezone)
    inicio = datetime.combine(dia, inicio_t, tzinfo=tz)

    if hora_fin.strip():
        fin_t = _hora(hora_fin)
        if fin_t is None:
            return f"La hora de fin {hora_fin!r} no es valida. Usa HH:MM de 24 horas."
        fin = datetime.combine(dia, fin_t, tzinfo=tz)
        # Una quedada que cruza medianoche: el fin cae al dia siguiente.
        if fin <= inicio:
            fin += timedelta(days=1)
    else:
        fin = inicio + DURACION_POR_DEFECTO

    contenido = construir_ics(
        titulo=titulo, lugar=lugar, inicio=inicio, fin=fin, descripcion=descripcion
    )

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    destino = DIR_SALIDA / f"{nombre_archivo(titulo)}-{dia.isoformat()}.ics"
    destino.write_bytes(contenido)
    logger.info("ICS generado: %s", destino.name)

    return (
        f"Archivo de calendario generado: {destino}\n"
        f"Evento: {titulo} | {lugar} | {dia.isoformat()} {inicio_t.strftime('%H:%M')}"
        f"-{fin.strftime('%H:%M')} ({settings.hxq_timezone})\n\n"
        "Ya se le ofrece al admin para descargar. Mencionalo en una linea; no expliques "
        "que es un archivo .ics."
    )
