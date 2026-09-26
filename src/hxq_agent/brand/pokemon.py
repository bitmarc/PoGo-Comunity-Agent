"""Arte oficial y datos basicos de Pokemon, desde PokeAPI.

Por que PokeAPI y no generar el Pokemon con un modelo de imagen: Azure rechaza generar
propiedad intelectual (`moderation_blocked`), y aunque no lo hiciera, un Pokemon dibujado
por IA se nota y no es el que la gente espera ver. Las piezas publicadas usan arte
oficial; esto hace lo mismo.

El arte viene en PNG 512x512 con canal alfa, que es justo lo que necesita el hueco
central de las piezas: se monta sobre el fondo neon sin recuadro.

PokeAPI es gratuita y sin autenticacion, pero pide cachear en vez de repetir consultas.
La cache es en disco y no caduca: el arte oficial de un Pokemon no cambia.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API = "https://pokeapi.co/api/v2"
ARTE = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
    "/other/official-artwork/{id}.png"
)
UA = "hxq-agent (comunidad HuixquiGo)"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _dir_cache() -> Path:
    from hxq_agent.config import get_settings

    return get_settings().subdir("cache_pokemon")


class PokemonNoEncontrado(LookupError):
    """El nombre no corresponde a ningun Pokemon conocido."""


def normalizar_nombre(nombre: str) -> str:
    """'Mega Charizard Y' -> 'charizard-mega-y', que es como lo indexa PokeAPI."""
    n = nombre.strip().lower()
    n = n.replace("é", "e").replace("á", "a").replace("í", "i").replace("ó", "o")
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n


async def _traer_json(cliente: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    resp = await cliente.get(url, headers={"User-Agent": UA})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def obtener_pokemon(nombre: str, *, usar_cache: bool = True) -> dict[str, Any]:
    """Devuelve nombre en espanol, tipos y arte oficial.

    Los tipos vienen en ingles de PokeAPI; `brand.tipos` ya los traduce, asi que los
    acentos de la pieza salen de los tipos reales del Pokemon y no de lo que el modelo
    crea recordar.
    """
    clave = normalizar_nombre(nombre)
    if not clave:
        raise PokemonNoEncontrado("Nombre vacio.")

    cache = _dir_cache()
    meta_cache = cache / f"{clave}.json"
    arte_cache = cache / f"{clave}.png"

    if usar_cache and meta_cache.exists() and arte_cache.exists():
        datos = json.loads(meta_cache.read_text(encoding="utf-8"))
        datos["arte"] = arte_cache.read_bytes()
        logger.info("Pokemon servido de cache: %s", clave)
        return datos

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cliente:
        pkmn = await _traer_json(cliente, f"{API}/pokemon/{clave}")
        if pkmn is None:
            raise PokemonNoEncontrado(
                f"No encontre ningun Pokemon llamado '{nombre}'. Revisa como se escribe; "
                "las formas van como 'charizard-mega-y' o 'deoxys-attack'."
            )

        tipos = [t["type"]["name"] for t in pkmn.get("types", [])]
        numero = pkmn["id"]

        # El nombre en espanol vive en la especie, no en el Pokemon.
        nombre_es = pkmn["name"].replace("-", " ").title()
        especie_url = (pkmn.get("species") or {}).get("url")
        if especie_url:
            especie = await _traer_json(cliente, especie_url)
            if especie:
                for n in especie.get("names", []):
                    if n["language"]["name"] == "es":
                        nombre_es = n["name"]
                        break

        # El arte oficial se indexa por numero de especie, no por el id de la forma.
        resp = await cliente.get(ARTE.format(id=numero), headers={"User-Agent": UA})
        arte = resp.content if resp.status_code == 200 else b""
        if not arte:
            logger.warning("Sin arte oficial para %s (#%s)", clave, numero)

    datos = {"nombre": nombre_es, "tipos": tipos, "numero": numero}
    meta_cache.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    if arte:
        arte_cache.write_bytes(arte)

    logger.info("Pokemon %s: %s, tipos %s, arte %d KB", clave, nombre_es, tipos, len(arte) // 1024)
    datos["arte"] = arte
    return datos
