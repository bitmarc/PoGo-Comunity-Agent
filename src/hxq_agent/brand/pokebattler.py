"""Datos de incursiones desde Pokebattler.

Se usa la API HTTP y no su servidor MCP, al reves de lo que sugeria el primer analisis.
El MCP optimiza el tamano de respuesta (1-5 KB frente a 1,7 MB) porque asume que el
MODELO consume los datos. Aqui no: el modelo pide "la infografia de Xerneas" y es la tool
quien construye la pieza, asi que los 1,7 MB se parsean en el servidor y nunca llegan al
contexto. A cambio evitamos depender de una cuenta y controlamos nosotros la cache.

Condiciones de uso de Pokebattler, que se respetan aqui:
- Atribucion obligatoria al publicar datos derivados. La plantilla la lleva.
- Cache agresiva en vez de repetir consultas.
- Identificar el cliente por User-Agent.
- No recorrer el espacio combinatorio atacante x defensor x moveset.

Pokebattler es un proyecto de fans sin relacion con Niantic, Nintendo, Creatures, GAME
FREAK ni The Pokemon Company.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

import httpx

from hxq_agent.config import get_settings

logger = logging.getLogger(__name__)

BASE = "https://fight.pokebattler.com"
UA = "hxq-agent (comunidad HuixquiGo; github.com/bitmarc/hxq-agent)"
ATRIBUCION = "Datos de counters: Pokébattler"

_TIMEOUT = httpx.Timeout(90.0, connect=15.0)

# El pokedex son 7 MB y cambia con cada actualizacion del juego; un dia es de sobra.
# La rotacion de incursiones cambia mas a menudo, pero no cada hora.
TTL_POKEDEX = 24 * 3600
TTL_RAIDS = 3 * 3600
TTL_COUNTERS = 12 * 3600

# Multiplicadores de PC de Pokemon GO en los niveles de captura de incursion.
# Verificados contra una infografia publicada de la comunidad: Groudon da 2260-2351
# normal y 2825-2939 potenciado, exactamente lo que muestra la pieza original.
CPM = {20: 0.5974, 25: 0.667934}

# Las capturas de incursion tienen suelo de IV 10/10/10.
IV_MIN = 10
IV_MAX = 15


class PokebattlerError(RuntimeError):
    """No se pudieron obtener los datos."""


def _dir_cache():
    return get_settings().subdir("cache_pokebattler")


def _leer_cache(nombre: str, ttl: int) -> Any | None:
    archivo = _dir_cache() / f"{nombre}.json"
    if not archivo.exists():
        return None
    if time.time() - archivo.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _escribir_cache(nombre: str, datos: Any) -> None:
    (_dir_cache() / f"{nombre}.json").write_text(
        json.dumps(datos, ensure_ascii=False), encoding="utf-8"
    )


async def _traer(ruta: str, nombre_cache: str, ttl: int) -> Any:
    if (cacheado := _leer_cache(nombre_cache, ttl)) is not None:
        logger.info("Pokebattler: cache hit (%s)", nombre_cache)
        return cacheado

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as cliente:
            resp = await cliente.get(f"{BASE}{ruta}", headers={"User-Agent": UA})
            resp.raise_for_status()
            datos = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Pokebattler fallo (%s): %s", nombre_cache, exc)
        raise PokebattlerError(f"Pokebattler no respondio: {exc}") from exc

    _escribir_cache(nombre_cache, datos)
    logger.info("Pokebattler: %s descargado (%d KB)", nombre_cache, len(str(datos)) // 1024)
    return datos


# --------------------------------------------------------------------------- #
# Pokedex con stats de Pokemon GO
# --------------------------------------------------------------------------- #


async def pokedex() -> dict[str, dict[str, Any]]:
    """Indice por id de Pokebattler con stats de GO, tipos y numero de Pokedex.

    El numero de Pokedex es lo que resuelve el arte: evita tener que mapear
    `ZAMAZENTA_CROWNED_SHIELD_FORM` a un nombre de PokeAPI, porque el arte oficial se
    indexa por numero de especie.
    """
    datos = await _traer("/pokemon", "pokedex", TTL_POKEDEX)
    return {p["pokemonId"]: p for p in datos.get("pokemon", [])}


def tipos_de(entrada: dict[str, Any]) -> list[str]:
    """Tipos en minusculas y en ingles, como los devuelve PokeAPI.

    Pokebattler los da como POKEMON_TYPE_FAIRY; se normalizan para que
    `brand.tipos` los traduzca igual que los de PokeAPI.
    """
    crudos = [entrada.get("type"), entrada.get("type2")]
    return [t.replace("POKEMON_TYPE_", "").lower() for t in crudos if t]


def numero_pokedex(entrada: dict[str, Any]) -> int | None:
    return (entrada.get("pokedex") or {}).get("pokemonNum")


# --------------------------------------------------------------------------- #
# Puntos de combate
# --------------------------------------------------------------------------- #


def calcular_pc(stats: dict[str, int], nivel: int, iv: int) -> int:
    """PC de Pokemon GO para unas stats, nivel e IV planos."""
    ataque = stats["baseAttack"] + iv
    defensa = stats["baseDefense"] + iv
    aguante = stats["baseStamina"] + iv
    m = CPM[nivel]
    return max(10, math.floor(ataque * math.sqrt(defensa) * math.sqrt(aguante) * m * m / 10))


def rango_captura(stats: dict[str, int], nivel: int) -> tuple[int, int]:
    """PC minimo y maximo al capturar, con el suelo de IV de incursion."""
    return calcular_pc(stats, nivel, IV_MIN), calcular_pc(stats, nivel, IV_MAX)


# --------------------------------------------------------------------------- #
# Incursiones
# --------------------------------------------------------------------------- #


async def rotacion() -> dict[str, list[str]]:
    """Jefes de incursion activos, agrupados por nivel."""
    datos = await _traer("/raids", "raids", TTL_RAIDS)
    salida: dict[str, list[str]] = {}
    for tier in datos.get("tiers", []):
        jefes = [r["pokemon"] for r in (tier.get("raids") or []) if r.get("pokemon")]
        if jefes:
            salida[tier.get("tier", "?")] = jefes
    return salida


async def counters(
    jefe: str,
    *,
    tier: str = "RAID_LEVEL_5",
    nivel_atacante: int = 40,
    cuantos: int = 6,
) -> list[dict[str, str]]:
    """Los mejores counters del jefe, con su mejor moveset.

    Una sola consulta por jefe, cacheada. No se recorre el espacio de movesets: se pide
    el ranking por defecto y se toma la cola, que es donde estan los mejores.
    """
    ruta = (
        f"/raids/defenders/{jefe}/levels/{tier}/attackers/levels/{nivel_atacante}"
        f"/strategies/CINEMATIC_ATTACK_WHEN_POSSIBLE/DEFENSE_RANDOM_MC"
        f"?sort=ESTIMATOR&weatherCondition=NO_WEATHER"
        f"&dodgeStrategy=DODGE_REACTION_TIME&aggregation=AVERAGE"
    )
    datos = await _traer(ruta, f"counters_{jefe}_{tier}_{nivel_atacante}", TTL_COUNTERS)

    atacantes = datos.get("attackers") or []
    if not atacantes:
        raise PokebattlerError(f"Pokebattler no devolvio counters para {jefe}.")

    # La lista viene de peor a mejor, asi que los mejores estan al final.
    defensores = (atacantes[0].get("randomMove") or {}).get("defenders") or []
    mejores = list(reversed(defensores))[:cuantos]

    salida = []
    for d in mejores:
        moveset = (d.get("byMove") or [{}])[-1]
        salida.append(
            {
                "id": d.get("pokemonId", "?"),
                "move1": moveset.get("move1", ""),
                "move2": moveset.get("move2", ""),
            }
        )
    return salida
