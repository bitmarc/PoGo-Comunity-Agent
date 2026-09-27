"""Ensambla los datos de una infografia de incursion.

Junta tres fuentes y devuelve algo que la plantilla pueda pintar sin saber de donde
viene nada:

- Pokebattler: stats de Pokemon GO, counters con su mejor moveset, numero de Pokedex.
- PokeAPI: nombres y movimientos en espanol, debilidades por tipo, arte oficial.
- Calculo propio: el PC de captura, verificado contra una pieza ya publicada.

El numero de Pokedex es lo que une las dos APIs. Sin el habria que mantener a mano un
diccionario de `ZAMAZENTA_CROWNED_SHIELD_FORM` a nombres, que era lo que hacia caro este
trabajo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from hxq_agent.brand import pokebattler as pb
from hxq_agent.brand import traduccion as tr

logger = logging.getLogger(__name__)

# Cuantos counters se piden. Seis caben en la pieza sin que el texto encoja.
COUNTERS = 6
MEGAS = 3


@dataclass
class Counter:
    nombre: str
    movimientos: str
    numero: int | None = None


@dataclass
class DatosIncursion:
    """Todo lo que la plantilla necesita, ya en espanol."""

    nombre: str
    numero: int
    tipos: list[str]
    pc_normal: tuple[int, int]
    pc_potenciado: tuple[int, int]
    debilidades: list[str] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    megas: list[Counter] = field(default_factory=list)
    atribucion: str = pb.ATRIBUCION


class JefeNoEncontrado(LookupError):
    """El nombre no corresponde a ningun jefe conocido."""


def _buscar_id(dex: dict[str, Any], consulta: str) -> str:
    """Encuentra el id de Pokebattler a partir de lo que escriba el admin."""
    pedido = consulta.strip().upper().replace(" ", "_")
    if pedido in dex:
        return pedido

    # Coincidencia por prefijo: "groudon" encuentra GROUDON antes que GROUDON_PRIMAL.
    candidatos = [k for k in dex if k == pedido or k.startswith(f"{pedido}_")]
    if candidatos:
        return min(candidatos, key=len)

    raise JefeNoEncontrado(
        f"No encontre ningun Pokemon llamado '{consulta}' en los datos de incursiones."
    )


async def _traducir(id_pb: str, dex: dict[str, Any]) -> tuple[str, int | None]:
    """Nombre en espanol de un id de Pokebattler, con su forma aplicada."""
    entrada = dex.get(id_pb, {})
    numero = pb.numero_pokedex(entrada)
    base, forma = tr.separar_forma(id_pb)
    if numero:
        nombre, _ = await tr.nombre_y_arte(numero, base.title())
    else:
        nombre = base.title()
    return tr.aplicar_forma(nombre, forma), numero


async def reunir(jefe: str, *, tier: str = "RAID_LEVEL_5") -> DatosIncursion:
    """Reune todo lo necesario para la infografia de un jefe."""
    dex = await pb.pokedex()
    id_jefe = _buscar_id(dex, jefe)
    entrada = dex[id_jefe]

    tipos = pb.tipos_de(entrada)
    nombre, numero = await _traducir(id_jefe, dex)

    # Se piden 20 y no 9: entre megas, formas oscuras y duplicados por forma, con
    # pocos candidatos la lista de counters se quedaba en cuatro.
    crudos = await pb.counters(id_jefe, tier=tier, cuantos=20)

    counters: list[Counter] = []
    megas: list[Counter] = []
    vistos: set[str] = set()

    for c in crudos:
        if c["id"] in vistos:
            continue
        vistos.add(c["id"])

        nom, num = await _traducir(c["id"], dex)
        m1 = await tr.nombre_movimiento(c["move1"])
        m2 = await tr.nombre_movimiento(c["move2"])
        item = Counter(nombre=nom, movimientos=f"{m1} / {m2}".strip(" /"), numero=num)

        if tr.es_mega(c["id"]):
            if len(megas) < MEGAS:
                megas.append(item)
        elif len(counters) < COUNTERS:
            counters.append(item)

        if len(counters) >= COUNTERS and len(megas) >= MEGAS:
            break

    datos = DatosIncursion(
        nombre=nombre,
        numero=numero or 0,
        tipos=tipos,
        pc_normal=pb.rango_captura(entrada["stats"], 20),
        pc_potenciado=pb.rango_captura(entrada["stats"], 25),
        debilidades=await tr.debilidades(tipos),
        counters=counters,
        megas=megas,
    )
    logger.info(
        "Incursion %s: %d counters, %d megas, debilidades %s",
        datos.nombre,
        len(counters),
        len(megas),
        datos.debilidades,
    )
    return datos
