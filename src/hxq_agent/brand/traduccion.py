"""Traduccion al espanol de nombres y movimientos, y debilidades por tipo.

Pokebattler habla en ingles y en mayusculas (`ZAMAZENTA_CROWNED_SHIELD_FORM`,
`METAL_CLAW_FAST`). PokeAPI tiene las traducciones oficiales, y el puente entre ambos es
el numero de Pokedex, que Pokebattler ya incluye. Eso evita mantener un diccionario de
nombres a mano, que era lo que hacia caro este trabajo.

Todo se cachea en disco sin caducidad: ni el nombre en espanol de un Pokemon ni el de un
movimiento cambian.
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from hxq_agent.config import get_settings

logger = logging.getLogger(__name__)

API = "https://pokeapi.co/api/v2"
UA = "hxq-agent (comunidad HuixquiGo)"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Sufijos que Pokebattler anade y PokeAPI no conoce.
_SUFIJOS_MOVIMIENTO = ("_FAST", "_PLUS", "_BLASTOISE", "_V2")


def _dir_cache():
    return get_settings().subdir("cache_traduccion")


def _cacheado(clave: str) -> dict | None:
    archivo = _dir_cache() / f"{clave}.json"
    if archivo.exists():
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _guardar(clave: str, datos: dict) -> None:
    (_dir_cache() / f"{clave}.json").write_text(
        json.dumps(datos, ensure_ascii=False), encoding="utf-8"
    )


def slug_movimiento(nombre_pb: str) -> str:
    """`METAL_CLAW_FAST` -> `metal-claw`, que es como lo indexa PokeAPI."""
    n = nombre_pb.strip().upper()
    for sufijo in _SUFIJOS_MOVIMIENTO:
        if n.endswith(sufijo):
            n = n[: -len(sufijo)]
    return re.sub(r"[^A-Z0-9]+", "-", n).strip("-").lower()


# Formas que Pokebattler distingue y PokeAPI no separa por numero de Pokedex.
# Sin esto, METAGROSS y METAGROSS_MEGA salen los dos como "Metagross" y la lista de
# counters muestra el mismo Pokemon dos veces, que es justo lo que las infografias de la
# comunidad si distinguen.
#
# El orden importa: los sufijos mas largos primero, o `_ALOLA_SHADOW_FORM` se detectaria
# como `_SHADOW_FORM` y perderia la region.
_FORMAS: tuple[tuple[str, str], ...] = (
    ("_ALOLA_SHADOW_FORM", "{n} de Alola oscuro"),
    ("_CROWNED_SHIELD_FORM", "{n} Escudo Supremo"),
    ("_CROWNED_SWORD_FORM", "{n} Espada Suprema"),
    ("_DUSK_MANE_FORM", "{n} Melena Crepuscular"),
    ("_DAWN_WINGS_FORM", "{n} Alas del Alba"),
    ("_INCARNATE_FORM", "{n} Avatar"),
    ("_THERIAN_FORM", "{n} Tótem"),
    ("_GALARIAN_FORM", "{n} de Galar"),
    ("_HISUIAN_FORM", "{n} de Hisui"),
    ("_PALDEAN_FORM", "{n} de Paldea"),
    ("_ALOLA_FORM", "{n} de Alola"),
    ("_SHADOW_FORM", "{n} oscuro"),
    ("_BLACK_FORM", "{n} Negro"),
    ("_WHITE_FORM", "{n} Blanco"),
    ("_ORIGIN_FORM", "{n} Origen"),
    ("_ATTACK_FORM", "{n} Ataque"),
    ("_DEFENSE_FORM", "{n} Defensa"),
    ("_SPEED_FORM", "{n} Velocidad"),
    ("_GIGANTAMAX", "Gigamax {n}"),
    ("_PRIMAL", "{n} primigenio"),
    ("_MEGA_X", "Mega {n} X"),
    ("_MEGA_Y", "Mega {n} Y"),
    ("_MEGA", "Mega {n}"),
)


def separar_forma(id_pb: str) -> tuple[str, str | None]:
    """Separa el id de Pokebattler en (base, plantilla de forma)."""
    pid = id_pb.strip().upper()
    for sufijo, plantilla in _FORMAS:
        if pid.endswith(sufijo):
            return pid[: -len(sufijo)], plantilla
    return pid, None


def aplicar_forma(nombre: str, plantilla: str | None) -> str:
    """Decora el nombre en espanol con su forma."""
    return plantilla.format(n=nombre) if plantilla else nombre


def es_mega(id_pb: str) -> bool:
    """Las megas van en su propia seccion en las piezas de la comunidad."""
    pid = id_pb.strip().upper()
    return pid.endswith(("_MEGA", "_MEGA_X", "_MEGA_Y", "_PRIMAL"))


def _bonito(nombre_pb: str) -> str:
    """Ultimo recurso si PokeAPI no conoce el nombre: al menos que se lea.

    Pasa con movimientos y formas exclusivas de Pokemon GO.
    """
    limpio = slug_movimiento(nombre_pb).replace("-", " ")
    return limpio.title()


async def _pedir(cliente: httpx.AsyncClient, url: str) -> dict | None:
    resp = await cliente.get(url, headers={"User-Agent": UA})
    if resp.status_code != 200:
        return None
    return resp.json()


def _nombre_es(datos: dict, respaldo: str) -> str:
    for n in datos.get("names", []):
        if n["language"]["name"] == "es":
            return n["name"]
    return respaldo


# Pokemon GO desglosa Poder Oculto por tipo; PokeAPI solo tiene la entrada generica.
_PODER_OCULTO = re.compile(r"^HIDDEN_POWER(?:_([A-Z]+))?_FAST$")


def _poder_oculto(nombre_pb: str) -> str | None:
    """'HIDDEN_POWER_WATER_FAST' -> 'Poder Oculto (Agua)'."""
    m = _PODER_OCULTO.match(nombre_pb.strip().upper())
    if not m:
        return None
    if not m.group(1):
        return "Poder Oculto"
    from hxq_agent.brand.tipos import normalizar_tipo

    tipo = normalizar_tipo(m.group(1).lower())
    return f"Poder Oculto ({tipo.capitalize()})" if tipo else "Poder Oculto"


async def nombre_movimiento(nombre_pb: str) -> str:
    """Nombre del movimiento en espanol."""
    if not nombre_pb.strip():
        return ""
    if (especial := _poder_oculto(nombre_pb)) is not None:
        return especial
    clave = f"mov_{slug_movimiento(nombre_pb)}"
    if (c := _cacheado(clave)) is not None:
        return c["nombre"]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cliente:
            datos = await _pedir(cliente, f"{API}/move/{slug_movimiento(nombre_pb)}")
    except httpx.HTTPError:
        datos = None

    nombre = _nombre_es(datos, _bonito(nombre_pb)) if datos else _bonito(nombre_pb)
    _guardar(clave, {"nombre": nombre})
    return nombre


async def nombre_y_arte(numero: int, respaldo: str = "") -> tuple[str, int]:
    """Nombre en espanol de una especie por su numero de Pokedex.

    Devuelve tambien el numero, para que quien llama pueda componer la URL del arte sin
    volver a consultar.
    """
    clave = f"esp_{numero}"
    if (c := _cacheado(clave)) is not None:
        return c["nombre"], numero

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cliente:
            datos = await _pedir(cliente, f"{API}/pokemon-species/{numero}")
    except httpx.HTTPError:
        datos = None

    nombre = _nombre_es(datos, respaldo or str(numero)) if datos else (respaldo or str(numero))
    _guardar(clave, {"nombre": nombre})
    return nombre, numero


async def debilidades(tipos: list[str]) -> list[str]:
    """Tipos que hacen dano aumentado, en espanol.

    Se combinan las relaciones de los dos tipos y se descuentan las resistencias: un
    Acero/Hada no es debil a Siniestro aunque Hada sola lo sea. La lista final es la que
    de verdad le sirve a quien va a la incursion.
    """
    if not tipos:
        return []

    clave = "deb_" + "_".join(sorted(t.lower() for t in tipos))
    if (c := _cacheado(clave)) is not None:
        return c["tipos"]

    multiplicadores: dict[str, float] = {}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cliente:
            for tipo in tipos:
                datos = await _pedir(cliente, f"{API}/type/{tipo.lower()}")
                if not datos:
                    continue
                rel = datos.get("damage_relations", {})
                for t in rel.get("double_damage_from", []):
                    multiplicadores[t["name"]] = multiplicadores.get(t["name"], 1.0) * 2
                for t in rel.get("half_damage_from", []):
                    multiplicadores[t["name"]] = multiplicadores.get(t["name"], 1.0) / 2
                for t in rel.get("no_damage_from", []):
                    multiplicadores[t["name"]] = 0.0
    except httpx.HTTPError:
        return []

    # Solo lo que acaba siendo superefectivo tras combinar ambos tipos.
    debiles = sorted(
        (t for t, m in multiplicadores.items() if m > 1.0),
        key=lambda t: -multiplicadores[t],
    )

    from hxq_agent.brand.tipos import normalizar_tipo

    en_espanol: list[str] = []
    for t in debiles:
        canonico = normalizar_tipo(t)
        if canonico:
            en_espanol.append(canonico)

    _guardar(clave, {"tipos": en_espanol})
    return en_espanol
