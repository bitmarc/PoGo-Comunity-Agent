"""Colores de acento por tipo de Pokemon.

En las piezas publicadas el acento no es fijo: sale de los tipos del Pokemon
protagonista. Cottonee (Planta/Hada) va en verde y rosa; Deino (Siniestro/Dragon) en
morado y azul. Replicar eso es la mitad de lo que hace que una pieza se vea de la
comunidad.

Los valores NO son los colores canonicos de los tipos: son versiones neon, subidas de
luminosidad y saturacion, porque los canonicos (apagados y terrosos) no brillan sobre
fondo oscuro. Comparados contra las piezas reales.
"""

from __future__ import annotations

# Nombres en espanol porque es como los escribe el agente y como los lee el admin.
COLORES_TIPO: dict[str, str] = {
    "normal": "#c9c9a8",
    "fuego": "#ff8a3d",
    "agua": "#4da6ff",
    "electrico": "#ffe14d",
    "planta": "#4ade80",
    "hielo": "#7dd3fc",
    "lucha": "#ff5c57",
    "veneno": "#c96bff",
    "tierra": "#e8c468",
    "volador": "#a5b4fc",
    "psiquico": "#ff6bb3",
    "bicho": "#b9e34d",
    "roca": "#d6c26b",
    "fantasma": "#a78bfa",
    "dragon": "#7c6bff",
    "siniestro": "#a855f7",
    "acero": "#a8c7e0",
    "hada": "#f472b6",
}

# Sinonimos y variantes que el modelo puede escribir. Sin esto, un "eléctrico" con
# tilde o un "dark" en ingles caerian al acento por defecto sin avisar.
_ALIAS: dict[str, str] = {
    "eléctrico": "electrico",
    "electrik": "electrico",
    "psíquico": "psiquico",
    "psiquico": "psiquico",
    "dark": "siniestro",
    "fairy": "hada",
    "grass": "planta",
    "fire": "fuego",
    "water": "agua",
    "dragon": "dragon",
    "ghost": "fantasma",
    "steel": "acero",
    "rock": "roca",
    "bug": "bicho",
    "ground": "tierra",
    "flying": "volador",
    "poison": "veneno",
    "fighting": "lucha",
    "ice": "hielo",
    "electric": "electrico",
    "psychic": "psiquico",
    "planta/hada": "planta",
}

# Cian y magenta: el par por defecto de las piezas sin Pokemon protagonista
# (quedadas, anuncios). Es el que mas aparece en las infografias existentes.
ACENTO_1_POR_DEFECTO = "#22d3ee"
ACENTO_2_POR_DEFECTO = "#e879f9"


def normalizar_tipo(tipo: str) -> str | None:
    """Devuelve el tipo canonico, o None si no se reconoce."""
    clave = tipo.strip().lower()
    clave = _ALIAS.get(clave, clave)
    return clave if clave in COLORES_TIPO else None


def acentos_desde_tipos(tipos: list[str] | None) -> tuple[str, str]:
    """Par de acentos para una pieza, a partir de los tipos del Pokemon.

    - Dos tipos reconocidos: un color por tipo, como en las piezas reales.
    - Un solo tipo: ese color mas el magenta por defecto, para que el titulo
      conserve el contraste de dos tonos.
    - Ninguno reconocido: el par por defecto.
    """
    if not tipos:
        return ACENTO_1_POR_DEFECTO, ACENTO_2_POR_DEFECTO

    colores = [COLORES_TIPO[t] for t in (normalizar_tipo(x) for x in tipos) if t]

    if len(colores) >= 2:
        return colores[0], colores[1]
    if len(colores) == 1:
        # Si el unico tipo ya es rosado, el segundo acento seria casi el mismo:
        # se usa el cian para garantizar contraste entre los dos tonos del titulo.
        segundo = (
            ACENTO_1_POR_DEFECTO if colores[0] == COLORES_TIPO["hada"] else ACENTO_2_POR_DEFECTO
        )
        return colores[0], segundo
    return ACENTO_1_POR_DEFECTO, ACENTO_2_POR_DEFECTO
