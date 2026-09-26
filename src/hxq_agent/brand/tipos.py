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


def _complemento(color: str) -> str:
    """Segundo acento que contraste con el dado.

    Se elige entre los dos por defecto el que mas se separe en matiz, para que el titulo
    siempre tenga dos tonos distinguibles.
    """
    candidatos = [ACENTO_2_POR_DEFECTO, ACENTO_1_POR_DEFECTO]
    return max(candidatos, key=lambda c: _distancia_matiz(color, c))


def _distancia_matiz(a: str, b: str) -> float:
    d = abs(_matiz(a) - _matiz(b))
    return min(d, 360 - d)


def normalizar_tipo(tipo: str) -> str | None:
    """Devuelve el tipo canonico, o None si no se reconoce."""
    clave = tipo.strip().lower()
    clave = _ALIAS.get(clave, clave)
    return clave if clave in COLORES_TIPO else None


def _matiz(hex_color: str) -> float:
    """Matiz en grados (0-360) de un color hex."""
    import colorsys

    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _contrastan(a: str, b: str, minimo: float = 45.0) -> bool:
    """True si dos colores estan lo bastante separados en matiz.

    El titulo de estas piezas va en dos tonos, y ese contraste es parte de su firma
    visual. Hay pares de tipos que dan colores casi identicos (Dragon y Volador son
    ambos violeta, Roca y Tierra ambos ocre) y la pieza sale monocroma.
    """
    d = abs(_matiz(a) - _matiz(b))
    return min(d, 360 - d) >= minimo


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
        # Dos tipos vecinos en el circulo cromatico dejan el titulo sin contraste
        # (Rayquaza es Dragon/Volador: los dos violeta). Se conserva el primero, que
        # es el tipo principal, y el segundo cede ante un tono que si contraste.
        if _contrastan(colores[0], colores[1]):
            return colores[0], colores[1]
        return colores[0], _complemento(colores[0])
    if len(colores) == 1:
        return colores[0], _complemento(colores[0])
    return ACENTO_1_POR_DEFECTO, ACENTO_2_POR_DEFECTO
