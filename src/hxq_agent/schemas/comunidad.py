"""Esquema de cada tema de datos de la comunidad.

En la base todos viven en una tabla con JSONB (`dato_comunidad`); el contrato real esta
aqui. Lo que entra desde el chat pasa por estos modelos antes de escribirse, asi que un
dato mal formado se convierte en una pregunta al admin y no en una coordenada rota que
acaba en un aviso.

Agregar un tema es agregar un modelo y una entrada en `TEMAS`. No hace falta SQL.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

TemaId = Literal["puntos_reunion", "codigos_jugadores", "redes_sociales", "historia"]


def normalizar(texto: str) -> str:
    """Minusculas, sin acentos y sin espacios de sobra. Para comparar, no para mostrar.

    El admin escribe "jardin", "Jardín" o "JARDIN" segun le de; los tres son lo mismo.
    """
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())


class _Registro(BaseModel):
    """Lo comun: textos sin espacios raros."""

    @field_validator("*", mode="before")
    @classmethod
    def _limpiar_textos(cls, v: Any) -> Any:
        return " ".join(v.split()) if isinstance(v, str) else v


class PuntoReunion(_Registro):
    """Un lugar donde la comunidad suele quedar."""

    nombre: Annotated[str, Field(min_length=2, max_length=60)]
    # La sede es el punto por defecto: donde se queda si nadie dice otra cosa.
    sede: bool = False
    concurrencia: Literal["alta", "media", "baja"]
    # Como lo llama la gente. Es lo que permite resolver "en el quiosco" al punto real.
    variantes: list[str] = []
    latitud: Annotated[float, Field(ge=-90, le=90)]
    longitud: Annotated[float, Field(ge=-180, le=180)]
    zona: Annotated[str, Field(min_length=2, max_length=40)]

    @field_validator("variantes")
    @classmethod
    def _variantes_limpias(cls, v: list[str]) -> list[str]:
        vistas: list[str] = []
        for variante in v:
            limpia = " ".join(variante.split())
            if limpia and normalizar(limpia) not in {normalizar(x) for x in vistas}:
                vistas.append(limpia)
        return vistas

    @property
    def coordenadas(self) -> str:
        return f"{self.latitud},{self.longitud}"

    @property
    def maps_url(self) -> str:
        return f"https://www.google.com/maps/search/?api=1&query={self.coordenadas}"


class CodigoJugador(_Registro):
    """El codigo de entrenador de un miembro. Uso interno: no se publica."""

    alias: Annotated[str, Field(min_length=1, max_length=40)]
    nombre_jugador: Annotated[str, Field(min_length=1, max_length=40)]
    # Texto y no numero: un codigo puede empezar por cero.
    codigo: str
    equipo: Literal["instinct", "mystic", "valor"]

    @field_validator("codigo", mode="before")
    @classmethod
    def _doce_digitos(cls, v: Any) -> str:
        # Se acepta como lo copia la gente del juego: "1234 5678 9012" o con guiones.
        limpio = "".join(ch for ch in str(v) if ch not in " -")
        if not (limpio.isdigit() and len(limpio) == 12):
            raise ValueError("el codigo de entrenador son exactamente 12 digitos")
        return limpio

    @field_validator("equipo", mode="before")
    @classmethod
    def _equipo_minusculas(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @property
    def codigo_legible(self) -> str:
        return f"{self.codigo[:4]} {self.codigo[4:8]} {self.codigo[8:]}"


class RedSocial(_Registro):
    """Una cuenta oficial de la comunidad."""

    red: Annotated[str, Field(min_length=2, max_length=30)]
    nombre: Annotated[str, Field(min_length=1, max_length=60)]
    url: HttpUrl

    @field_validator("red", mode="before")
    @classmethod
    def _red_minusculas(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class Historia(_Registro):
    """Un capitulo de la historia de la comunidad."""

    titulo: Annotated[str, Field(min_length=2, max_length=80)]
    tema: Annotated[str, Field(min_length=2, max_length=160)]
    detalle: Annotated[str, Field(min_length=10, max_length=4000)]


@dataclass(frozen=True)
class Tema:
    """Como se guarda y se trata cada tema."""

    modelo: type[_Registro]
    # Campo que identifica al registro dentro del tema. Es lo que el admin nombra.
    clave: str
    # Privado: el agente lo consulta para el admin, pero nunca va en copy publicable.
    privado: bool = False


TEMAS: dict[str, Tema] = {
    "puntos_reunion": Tema(PuntoReunion, "nombre"),
    "codigos_jugadores": Tema(CodigoJugador, "alias", privado=True),
    "redes_sociales": Tema(RedSocial, "red"),
    "historia": Tema(Historia, "titulo"),
}


def _textos(valor: Any) -> list[str]:
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    if isinstance(valor, list):
        return [t for v in valor for t in _textos(v)]
    return [str(valor)]


def buscar_en(filas: list[dict[str, Any]], consulta: str) -> list[dict[str, Any]]:
    """Filtra registros por texto, sin acentos ni mayusculas.

    Coincide si la consulta esta dentro de algun campo, o si algun campo (una variante,
    un nombre) esta dentro de la consulta: "nos vemos en el quiosco" debe encontrar al
    punto cuya variante es "quiosco". En esa segunda direccion se exigen palabras
    completas y al menos 3 letras, o "alta" coincidiria con "falta" y "la" con todo.

    Son decenas de filas por tema: filtrar en Python es mas simple que un indice.
    """
    q = normalizar(consulta)
    if not q:
        return list(filas)

    resultado = []
    for fila in filas:
        textos = [normalizar(t) for t in _textos(fila)]
        if any(q in t or (len(t) >= 3 and f" {t} " in f" {q} ") for t in textos):
            resultado.append(fila)
    return resultado
