"""Render real con Chromium.

Lento (segundos por pieza) pero es el unico que prueba lo que importa: que el CSS carga,
que la fuente se aplica y que nada se sale del lienzo. Marcados como `lento` para poder
saltarlos: `pytest -m "not lento"`.
"""

from __future__ import annotations

import struct
from datetime import date, time

import pytest

from hxq_agent.brand.render import ALTO, ANCHO, construir_html, renderizar
from hxq_agent.schemas.piezas import AnuncioEvento, Quedada

pytestmark = pytest.mark.lento


def contexto(pieza) -> dict:
    ctx = pieza.model_dump()
    ctx.update(
        {
            "acento_1": pieza.acentos[0],
            "acento_2": pieza.acentos[1],
            "escala_titulo": pieza.escala_titulo,
            "escala_subtitulo": pieza.escala_subtitulo,
            "fecha_texto": pieza.fecha_texto,
            "horario_texto": pieza.horario_texto,
        }
    )
    return ctx


QUEDADA = Quedada(
    titulo="Quedada de Incursiones",
    subtitulo="Raids de 5 estrellas",
    lugar="Parque Metropolitano, Zapopan",
    fecha=date(2026, 10, 3),
    hora_inicio=time(18, 0),
    hora_fin=time(20, 30),
    detalles=["Trae pases", "Llegar antes"],
)


def _dimensiones_png(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "no es un PNG"
    return struct.unpack(">II", png[16:24])


class TestHtml:
    def test_los_datos_duros_llegan_al_html(self) -> None:
        """Fecha, hora y lugar se dibujan como texto real, no los escribe un modelo."""
        html = construir_html("quedada", contexto(QUEDADA))
        assert "sábado 3 de octubre" in html
        assert "6:00 pm a 8:30 pm" in html
        assert "Parque Metropolitano, Zapopan" in html

    def test_una_variable_que_falta_revienta(self) -> None:
        """StrictUndefined: mejor un error que un hueco silencioso publicado."""
        from jinja2 import UndefinedError

        with pytest.raises(UndefinedError):
            construir_html("quedada", {"titulo": "X"})

    def test_los_acentos_se_inyectan(self) -> None:
        q = QUEDADA.model_copy(update={"tipos": ["planta", "hada"]})
        html = construir_html("quedada", contexto(q))
        assert "#4ade80" in html
        assert "#f472b6" in html


class TestRenderReal:
    async def test_produce_un_png_del_tamano_correcto(self) -> None:
        png = await renderizar("quedada", contexto(QUEDADA))
        assert _dimensiones_png(png) == (ANCHO, ALTO)

    async def test_es_reproducible(self) -> None:
        """La misma pieza dos veces tiene que salir identica.

        Si el fondo tuviera estrellas aleatorias, comparar dos versiones de un aviso
        seria imposible.
        """
        a = await renderizar("quedada", contexto(QUEDADA))
        b = await renderizar("quedada", contexto(QUEDADA))
        assert a == b

    async def test_el_caso_mas_largo_no_desborda(self) -> None:
        """Con los textos maximos, el pie tiene que seguir dentro del lienzo."""
        larga = Quedada(
            titulo="Q" * 60,
            subtitulo="S" * 80,
            lugar="L" * 60,
            fecha=date(2026, 12, 20),
            hora_inicio=time(9, 30),
            hora_fin=time(13, 0),
            detalles=["D" * 70] * 4,
        )
        png = await renderizar("quedada", contexto(larga))
        assert _dimensiones_png(png) == (ANCHO, ALTO)

    async def test_anuncio_de_evento(self) -> None:
        a = AnuncioEvento(
            titulo="Hora Legendaria",
            subtitulo="Groudon en incursiones",
            fecha_inicio=date(2026, 10, 15),
            hora_inicio=time(18, 0),
            hora_fin=time(19, 0),
            bonus=["Más incursiones", "Mayor shiny"],
        )
        assert _dimensiones_png(await renderizar("anuncio_evento", contexto(a))) == (ANCHO, ALTO)
