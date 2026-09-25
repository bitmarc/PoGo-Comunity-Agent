"""Clima via Open-Meteo, para la logistica de quedadas.

Open-Meteo es gratis y no pide API key, lo que encaja con el presupuesto. Son dos llamadas:
geocodificar el lugar y pedir el pronostico diario. El horizonte es de 16 dias; mas alla de
eso se dice que no hay pronostico en vez de devolver un numero inventado.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import httpx
from agent_framework import tool
from pydantic import Field

from hxq_agent.config import get_settings

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
HORIZONTE_DIAS = 16

# Codigos WMO agrupados: al admin le sirve "lluvia fuerte", no el codigo 65.
_CODIGOS_WMO: dict[int, str] = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla con escarcha",
    51: "llovizna ligera",
    53: "llovizna",
    55: "llovizna intensa",
    56: "llovizna helada",
    57: "llovizna helada intensa",
    61: "lluvia ligera",
    63: "lluvia",
    65: "lluvia fuerte",
    66: "lluvia helada",
    67: "lluvia helada fuerte",
    71: "nieve ligera",
    73: "nieve",
    75: "nieve fuerte",
    77: "granizo fino",
    80: "chubascos ligeros",
    81: "chubascos",
    82: "chubascos violentos",
    85: "chubascos de nieve",
    86: "chubascos de nieve fuertes",
    95: "tormenta electrica",
    96: "tormenta con granizo",
    99: "tormenta con granizo fuerte",
}


def describir_codigo(codigo: int | None) -> str:
    """Traduce un codigo WMO a algo publicable."""
    if codigo is None:
        return "sin dato"
    return _CODIGOS_WMO.get(int(codigo), f"condicion no catalogada (codigo {codigo})")


def parsear_fecha(texto: str, hoy: date) -> date | None:
    """Acepta ISO (2026-10-04), dd/mm/aaaa y dd/mm (asumiendo el proximo que ocurra).

    El modelo ya resuelve "el sabado" a una fecha concreta antes de llamar a la tool; esto
    solo tolera los formatos en que puede escribirla.
    """
    texto = texto.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    # dd/mm sin ano: el proximo que caiga.
    # Se parsea a mano porque strptime sin ano usa 1900 por defecto, no soporta 29/02 y
    # su comportamiento cambia en Python 3.15.
    for separador in ("/", "-"):
        partes = texto.split(separador)
        if len(partes) != 2:
            continue
        try:
            dia, mes = int(partes[0]), int(partes[1])
        except ValueError:
            continue
        for ano in (hoy.year, hoy.year + 1):
            try:
                candidato = date(ano, mes, dia)
            except ValueError:
                break  # dia/mes imposible; probar otro separador no ayuda
            if candidato >= hoy:
                return candidato
    return None


async def _geocodificar(lugar: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            GEOCODING_URL,
            params={"name": lugar, "count": 1, "language": "es", "format": "json"},
        )
        resp.raise_for_status()
        resultados = (resp.json() or {}).get("results") or []
    return resultados[0] if resultados else None


@tool
async def consultar_clima(
    lugar: Annotated[
        str,
        Field(
            description=(
                "Ciudad o localidad, no un parque ni una direccion. "
                "Ej: 'Guadalajara', 'Zapopan, Jalisco'."
            )
        ),
    ],
    fecha: Annotated[
        str,
        Field(
            description=(
                "Fecha concreta del evento en formato aaaa-mm-dd. Resuelvela tu antes de "
                "llamar: no mandes 'el sabado'. Maximo 16 dias en el futuro."
            )
        ),
    ],
) -> str:
    """Consulta el pronostico del clima de un dia y lugar, para la logistica de una quedada.

    Usala cuando la fecha de la quedada importe para decidir hora, lugar o plan B por lluvia.
    Si la fecha esta fuera del horizonte de pronostico, lo dice: no inventes el clima.
    """
    settings = get_settings()
    hoy = datetime.now(ZoneInfo(settings.hxq_timezone)).date()

    objetivo = parsear_fecha(fecha, hoy)
    if objetivo is None:
        return (
            f"No pude interpretar la fecha {fecha!r}. Mandala como aaaa-mm-dd, "
            "por ejemplo 2026-10-04."
        )
    if objetivo < hoy:
        return f"La fecha {objetivo.isoformat()} ya paso. No hay pronostico de fechas pasadas."
    if objetivo > hoy + timedelta(days=HORIZONTE_DIAS):
        return (
            f"El {objetivo.isoformat()} esta a mas de {HORIZONTE_DIAS} dias: todavia no hay "
            "pronostico confiable. Vuelve a consultarlo cuando se acerque la fecha y no "
            "afirmes nada del clima por ahora."
        )

    try:
        sitio = await _geocodificar(lugar)
        if sitio is None:
            return (
                f"No encontre el lugar {lugar!r}. Prueba con el nombre de la ciudad, "
                "por ejemplo 'Guadalajara'."
            )

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": sitio["latitude"],
                    "longitude": sitio["longitude"],
                    "daily": (
                        "weather_code,temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max,precipitation_sum"
                    ),
                    "timezone": settings.hxq_timezone,
                    "start_date": objetivo.isoformat(),
                    "end_date": objetivo.isoformat(),
                },
            )
            resp.raise_for_status()
            diario = (resp.json() or {}).get("daily") or {}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("consultar_clima: fallo (%s): %s", lugar, exc)
        return "No pude consultar el clima ahora. Intenta de nuevo; no inventes el pronostico."

    if not diario.get("time"):
        return f"Open-Meteo no devolvio pronostico para {objetivo.isoformat()} en {lugar}."

    def _primero(clave: str) -> Any:
        valores = diario.get(clave) or [None]
        return valores[0]

    nombre = sitio.get("name", lugar)
    region = sitio.get("admin1")
    ubicacion = f"{nombre}, {region}" if region else nombre
    prob = _primero("precipitation_probability_max")
    mm = _primero("precipitation_sum")

    logger.info("consultar_clima: %s %s", ubicacion, objetivo.isoformat())

    return (
        f"Pronostico para {ubicacion} el {objetivo.strftime('%d/%m/%Y')}:\n"
        f"- Condicion: {describir_codigo(_primero('weather_code'))}\n"
        f"- Temperatura: minima {_primero('temperature_2m_min')} C, "
        f"maxima {_primero('temperature_2m_max')} C\n"
        f"- Probabilidad de lluvia: {prob}%\n"
        f"- Precipitacion acumulada estimada: {mm} mm\n"
        f"Fuente: Open-Meteo (open-meteo.com)"
    )
