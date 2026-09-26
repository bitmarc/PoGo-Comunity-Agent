"""Datos de entrada de cada plantilla grafica.

Estos modelos son el contrato entre el agente y el motor de render. Validan antes de
dibujar, asi que un dato que falta se convierte en una pregunta al admin y no en una
pieza con un hueco publicada a toda la comunidad.

Los limites de longitud no son arbitrarios: salen de cuanto cabe en cada zona de la
plantilla sin desbordar ni encogerse hasta ser ilegible.
"""

from __future__ import annotations

from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from hxq_agent.brand.tipos import acentos_desde_tipos

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def fecha_larga(f: date) -> str:
    """'sabado 4 de octubre', como se escribe en los avisos de la comunidad."""
    return f"{_DIAS[f.weekday()]} {f.day} de {_MESES[f.month - 1]}"


def hora_12h(t: time) -> str:
    """'7:00 pm'. En Mexico los avisos van en 12 horas, no en 24."""
    sufijo = "am" if t.hour < 12 else "pm"
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {sufijo}"


class _PiezaBase(BaseModel):
    """Lo comun a todas las piezas."""

    titulo: Annotated[str, Field(min_length=3, max_length=60)]
    subtitulo: Annotated[str, Field(max_length=80)] = ""

    # Tipos del Pokemon protagonista, si lo hay. De aqui salen los acentos.
    tipos: Annotated[list[str], Field(max_length=2)] = []

    # Arte central como data URI. Lo rellena el motor tras generarlo o cargarlo; el
    # agente no lo escribe a mano. Sin el, la pieza se ve correcta pero rala: el arte
    # es lo que llena el centro en las piezas publicadas.
    imagen_hero: str | None = None

    @field_validator("titulo", "subtitulo")
    @classmethod
    def _sin_espacios_raros(cls, v: str) -> str:
        return " ".join(v.split())

    @property
    def acentos(self) -> tuple[str, str]:
        return acentos_desde_tipos(self.tipos)

    @property
    def escala_titulo(self) -> int:
        """Cuerpo del titulo segun su largo.

        Sin esto, un titulo largo desborda el lienzo o se parte en cuatro lineas.
        Los cortes salen de probar con los titulos reales de las piezas existentes.
        """
        n = len(self.titulo)
        if n <= 16:
            return 108
        if n <= 24:
            return 92
        if n <= 34:
            return 76
        if n <= 46:
            return 64
        return 54

    @property
    def escala_subtitulo(self) -> int:
        n = len(self.subtitulo)
        if n <= 24:
            return 46
        if n <= 44:
            return 38
        return 32


class Quedada(_PiezaBase):
    """Una quedada de la comunidad: lugar, fecha y hora concretos.

    Es la pieza con datos duros: si la hora sale mal, la gente llega tarde. Por eso
    fecha y hora son tipos de fecha reales y no texto libre.
    """

    plantilla: Literal["quedada"] = "quedada"

    lugar: Annotated[str, Field(min_length=3, max_length=60)]
    fecha: date
    hora_inicio: time
    hora_fin: time | None = None

    # Hasta cuatro puntos sueltos: que llevar, que se va a hacer, etc.
    detalles: Annotated[list[Annotated[str, Field(max_length=70)]], Field(max_length=4)] = []

    @field_validator("lugar")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        return " ".join(v.split())

    @property
    def fecha_texto(self) -> str:
        return fecha_larga(self.fecha)

    @property
    def horario_texto(self) -> str:
        if self.hora_fin:
            return f"{hora_12h(self.hora_inicio)} a {hora_12h(self.hora_fin)}"
        return hora_12h(self.hora_inicio)


class AnuncioEvento(_PiezaBase):
    """Anuncio de un evento oficial: fechas, horario y bonificaciones."""

    plantilla: Literal["anuncio_evento"] = "anuncio_evento"

    fecha_inicio: date
    fecha_fin: date | None = None
    hora_inicio: time | None = None
    hora_fin: time | None = None

    # Los bonus del evento, que es lo que la gente busca de un vistazo.
    bonus: Annotated[list[Annotated[str, Field(max_length=90)]], Field(max_length=5)] = []

    @property
    def fecha_texto(self) -> str:
        if self.fecha_fin and self.fecha_fin != self.fecha_inicio:
            return f"{fecha_larga(self.fecha_inicio)} al {fecha_larga(self.fecha_fin)}"
        return fecha_larga(self.fecha_inicio)

    @property
    def horario_texto(self) -> str:
        if self.hora_inicio and self.hora_fin:
            return f"{hora_12h(self.hora_inicio)} a {hora_12h(self.hora_fin)}"
        if self.hora_inicio:
            return f"desde las {hora_12h(self.hora_inicio)}"
        return "todo el dia"


class Dinamica(_PiezaBase):
    """Una dinamica o concurso de la comunidad.

    El premio y la fecha limite son obligatorios a proposito: una dinamica sin premio
    claro o sin fecha de cierre genera discusiones que acaban en el chat de admins.
    """

    plantilla: Literal["dinamica"] = "dinamica"

    premio: Annotated[str, Field(min_length=2, max_length=40)]
    fecha_limite: date

    # Entre dos y cinco reglas. Con una no es una dinamica; con mas de cinco nadie las
    # lee y la pieza desborda.
    reglas: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=90)]],
        Field(min_length=2, max_length=5),
    ]

    # Que pasa si hay empate. No es opcional por experiencia: el empate siempre llega.
    desempate: Annotated[str, Field(max_length=120)] = ""

    @property
    def fecha_texto(self) -> str:
        return fecha_larga(self.fecha_limite)

    @property
    def horario_texto(self) -> str:
        """Las dinamicas no tienen horario; la plantilla base lo pide igual."""
        return ""


# Registro de plantillas: el nombre que usa el agente -> el modelo que valida.
PLANTILLAS: dict[str, type[_PiezaBase]] = {
    "quedada": Quedada,
    "anuncio_evento": AnuncioEvento,
    "dinamica": Dinamica,
}
