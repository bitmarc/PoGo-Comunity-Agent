"""Piezas graficas: validacion, escalado y colores.

El render real (Chromium) se prueba aparte porque tarda segundos. Aqui se prueba la
logica que decide QUE se dibuja, que es donde estan los errores que acaban publicados.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from hxq_agent.brand.tipos import (
    ACENTO_1_POR_DEFECTO,
    COLORES_TIPO,
    acentos_desde_tipos,
    normalizar_tipo,
)
from hxq_agent.schemas.piezas import PLANTILLAS, AnuncioEvento, Quedada, fecha_larga, hora_12h


class TestFormatoDeFechaYHora:
    def test_fecha_larga_lleva_tilde(self) -> None:
        """Publicar 'sabado' sin tilde se nota; es contenido de cara al publico."""
        assert fecha_larga(date(2026, 10, 3)) == "sábado 3 de octubre"

    def test_miercoles_tambien(self) -> None:
        assert fecha_larga(date(2026, 10, 7)).startswith("miércoles")

    @pytest.mark.parametrize(
        ("t", "esperado"),
        [
            (time(18, 0), "6:00 pm"),
            (time(9, 30), "9:30 am"),
            (time(0, 0), "12:00 am"),
            (time(12, 0), "12:00 pm"),
            (time(23, 59), "11:59 pm"),
        ],
    )
    def test_hora_en_formato_de_12(self, t: time, esperado: str) -> None:
        """En Mexico los avisos van en 12 horas; medianoche y mediodia son los casos
        donde un modulo mal hecho escribe '0:00 am'."""
        assert hora_12h(t) == esperado


class TestValidacionQuedada:
    def _valida(self, **extra):
        base = {
            "titulo": "Quedada de prueba",
            "lugar": "Parque Central",
            "fecha": date(2026, 10, 3),
            "hora_inicio": time(18, 0),
        }
        return Quedada(**{**base, **extra})

    def test_caso_minimo(self) -> None:
        q = self._valida()
        assert q.plantilla == "quedada"
        assert q.horario_texto == "6:00 pm"

    def test_con_hora_de_fin(self) -> None:
        assert self._valida(hora_fin=time(20, 30)).horario_texto == "6:00 pm a 8:30 pm"

    def test_sin_lugar_falla(self) -> None:
        """El lugar es obligatorio: una quedada sin lugar no sirve de nada."""
        with pytest.raises(ValidationError):
            Quedada(titulo="X", fecha=date(2026, 1, 1), hora_inicio=time(1, 0))

    def test_titulo_demasiado_largo_falla(self) -> None:
        """Mejor un error que el agente pueda relayar que una pieza desbordada."""
        with pytest.raises(ValidationError):
            self._valida(titulo="X" * 61)

    def test_mas_de_cuatro_detalles_falla(self) -> None:
        with pytest.raises(ValidationError):
            self._valida(detalles=["a", "b", "c", "d", "e"])

    def test_normaliza_espacios(self) -> None:
        assert self._valida(titulo="  Hola   mundo  ").titulo == "Hola mundo"


class TestEscalaDelTitulo:
    def _q(self, titulo: str) -> Quedada:
        return Quedada(
            titulo=titulo,
            lugar="Parque",
            fecha=date(2026, 1, 1),
            hora_inicio=time(1, 0),
        )

    def test_titulo_corto_usa_el_cuerpo_mayor(self) -> None:
        assert self._q("Quedada").escala_titulo == 108

    def test_titulo_largo_encoge(self) -> None:
        assert self._q("Q" * 55).escala_titulo == 54

    def test_la_escala_nunca_sube_al_alargar(self) -> None:
        """Monotona: si al crecer el titulo la escala subiera, desbordaria."""
        escalas = [self._q("Q" * n).escala_titulo for n in range(3, 61)]
        assert escalas == sorted(escalas, reverse=True)


class TestAcentosPorTipo:
    def test_dos_tipos_dan_un_color_cada_uno(self) -> None:
        """Como en la pieza de Cottonee: Planta verde, Hada rosa."""
        a1, a2 = acentos_desde_tipos(["planta", "hada"])
        assert a1 == COLORES_TIPO["planta"]
        assert a2 == COLORES_TIPO["hada"]

    def test_sin_tipos_usa_el_par_por_defecto(self) -> None:
        assert acentos_desde_tipos([])[0] == ACENTO_1_POR_DEFECTO
        assert acentos_desde_tipos(None)[0] == ACENTO_1_POR_DEFECTO

    def test_un_solo_tipo_conserva_dos_tonos(self) -> None:
        a1, a2 = acentos_desde_tipos(["fuego"])
        assert a1 == COLORES_TIPO["fuego"]
        assert a2 != a1, "el titulo necesita dos tonos distintos"

    def test_hada_sola_no_se_empareja_con_otro_rosa(self) -> None:
        """Rosa sobre rosa deja el titulo sin contraste entre sus dos mitades."""
        a1, a2 = acentos_desde_tipos(["hada"])
        assert a1 == COLORES_TIPO["hada"]
        assert a2 == ACENTO_1_POR_DEFECTO

    def test_tipo_desconocido_cae_al_defecto(self) -> None:
        assert acentos_desde_tipos(["inventado"])[0] == ACENTO_1_POR_DEFECTO

    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("PLANTA", "planta"),
            ("Eléctrico", "electrico"),
            ("dark", "siniestro"),
            ("  hada ", "hada"),
        ],
    )
    def test_normaliza_variantes(self, entrada: str, esperado: str) -> None:
        assert normalizar_tipo(entrada) == esperado

    def test_todos_los_colores_son_hex_valido(self) -> None:
        for tipo, color in COLORES_TIPO.items():
            assert color.startswith("#") and len(color) == 7, tipo
            int(color[1:], 16)


class TestAnuncioEvento:
    def test_rango_de_fechas(self) -> None:
        a = AnuncioEvento(
            titulo="Evento",
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 5),
        )
        assert "al" in a.fecha_texto

    def test_un_solo_dia_no_dice_rango(self) -> None:
        a = AnuncioEvento(titulo="Evento", fecha_inicio=date(2026, 10, 1))
        assert "al" not in a.fecha_texto

    def test_sin_horario_dice_todo_el_dia(self) -> None:
        a = AnuncioEvento(titulo="Evento", fecha_inicio=date(2026, 10, 1))
        assert a.horario_texto == "todo el dia"


def test_el_registro_de_plantillas_coincide_con_los_modelos() -> None:
    for nombre, modelo in PLANTILLAS.items():
        assert modelo.model_fields["plantilla"].default == nombre
