"""Busqueda web via Tavily.

Dos ambitos deliberadamente distintos:

- `oficial`: restringe a las fuentes de Pokemon GO en las que confiamos. Un dato de evento
  mal citado acaba publicado a toda la comunidad, asi que aqui la precision vale mas que
  la cobertura.
- `abierto`: internet entero, para ideas de contenido, tendencias y logistica local.

Tavily da 1.000 creditos al mes gratis y una busqueda `basic` cuesta 1. La cache en memoria
evita gastar dos creditos en la misma pregunta dentro del mismo dia, que es exactamente lo
que pasa desarrollando con recarga en caliente.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any, Literal

import httpx
from agent_framework import tool
from pydantic import Field

from hxq_agent.config import get_settings

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_MAX_RESULTS = 5

# Cache por proceso: (ambito, query_normalizada, dia) -> markdown ya formateado.
# Se pierde al reiniciar, y eso esta bien: en Fase 2 pasa a Postgres.
_cache: dict[tuple[str, str, str], str] = {}
_CACHE_MAX = 256


def _clave_cache(ambito: str, query: str) -> tuple[str, str, str]:
    return (ambito, " ".join(query.lower().split()), date.today().isoformat())


def _formatear(payload: dict[str, Any], ambito: str) -> str:
    """Convierte la respuesta de Tavily en markdown con la fuente pegada a cada dato.

    El formato importa: el modelo tiene que poder citar, y para eso necesita ver la URL
    junto al texto, no en una lista aparte al final.
    """
    resultados = payload.get("results") or []
    if not resultados:
        return (
            f"Sin resultados para esta busqueda (ambito: {ambito}). "
            "No hay informacion que reportar; no inventes una respuesta."
        )

    lineas = [f"Resultados (ambito: {ambito}):", ""]
    for i, r in enumerate(resultados, 1):
        titulo = (r.get("title") or "sin titulo").strip()
        url = (r.get("url") or "").strip()
        contenido = " ".join((r.get("content") or "").split())
        publicado = r.get("published_date")

        lineas.append(f"## {i}. {titulo}")
        lineas.append(f"Fuente: {url}")
        if publicado:
            lineas.append(f"Publicado: {publicado}")
        lineas.append("")
        lineas.append(contenido)
        lineas.append("")

    return "\n".join(lineas).strip()


@tool
async def buscar_web(
    query: Annotated[
        str,
        Field(
            description=(
                "Que buscar, en lenguaje natural. Se especifico: incluye el nombre del "
                "evento, el ano y la ciudad si aplica."
            )
        ),
    ],
    ambito: Annotated[
        Literal["oficial", "abierto"],
        Field(
            description=(
                "'oficial' restringe a fuentes confiables de Pokemon GO "
                "(pokemongolive.com, LeekDuck, Serebii): usalo SIEMPRE para fechas, "
                "horarios, bonus, spawns y cualquier dato de un evento oficial. "
                "'abierto' busca en todo internet: usalo para ideas de contenido, "
                "tendencias, lugares y logistica local."
            )
        ),
    ] = "oficial",
) -> str:
    """Busca informacion en la web y devuelve extractos con la URL de cada fuente.

    Usala siempre antes de afirmar cualquier dato sobre un evento oficial. Si devuelve
    'Sin resultados', di que no encontraste la informacion en vez de deducirla.
    """
    settings = get_settings()

    if not settings.tavily_api_key.strip():
        return (
            "La busqueda web no esta configurada (falta TAVILY_API_KEY). "
            "Dile al admin que hace falta una key gratuita de https://tavily.com "
            "para poder investigar. No intentes responder de memoria datos de eventos."
        )

    clave = _clave_cache(ambito, query)
    if (cacheado := _cache.get(clave)) is not None:
        logger.info("buscar_web: cache hit (%s) %r", ambito, query)
        return cacheado

    cuerpo: dict[str, Any] = {
        "query": query,
        "search_depth": "basic",  # 1 credito; 'advanced' cuesta 2
        "max_results": _MAX_RESULTS,
        "include_answer": False,  # queremos que el modelo razone sobre las fuentes
        "include_published_date": True,  # clave para juzgar si un dato sigue vigente
        "include_usage": True,
    }
    if ambito == "oficial":
        cuerpo["include_domains"] = settings.official_sources
        cuerpo["include_domains_mode"] = "restrict"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                TAVILY_URL,
                json=cuerpo,
                headers={"Authorization": f"Bearer {settings.tavily_api_key.strip()}"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        logger.warning("buscar_web: Tavily respondio %s", codigo)
        if codigo in (401, 403):
            return "La busqueda web fallo: la TAVILY_API_KEY parece invalida o revocada."
        if codigo == 429:
            return (
                "La busqueda web fallo: se agotaron los creditos de Tavily de este mes "
                "(el plan gratuito da 1.000). Avisale al admin."
            )
        return f"La busqueda web fallo con codigo HTTP {codigo}. Intenta de nuevo mas tarde."
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("buscar_web: fallo de red o respuesta invalida: %s", exc)
        return "La busqueda web no respondio. Intenta de nuevo; no inventes el resultado."

    creditos = (payload.get("usage") or {}).get("credits")
    logger.info(
        "buscar_web: ambito=%s resultados=%d creditos=%s query=%r",
        ambito,
        len(payload.get("results") or []),
        creditos,
        query,
    )

    salida = _formatear(payload, ambito)

    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[clave] = salida
    return salida
