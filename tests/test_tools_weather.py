"""La tool de clima.

El valor aqui esta en los limites: fechas fuera del horizonte de pronostico, fechas
pasadas y lugares inexistentes tienen que devolver un texto que impida al modelo inventar
un pronostico.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from hxq_agent.agent.tools import weather
from hxq_agent.config import Settings

HOY = date(2026, 9, 24)


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(_env_file=None, hxq_timezone="America/Mexico_City")
    monkeypatch.setattr(weather, "get_settings", lambda: s)


async def _llamar(**kwargs) -> str:
    resultado = await weather.consultar_clima.invoke(arguments=kwargs)
    if isinstance(resultado, list):
        return "\n".join(c.text or "" for c in resultado)
    return str(resultado)


class TestParsearFecha:
    def test_iso(self) -> None:
        assert weather.parsear_fecha("2026-10-04", HOY) == date(2026, 10, 4)

    @pytest.mark.parametrize("texto", ["04/10/2026", "04-10-2026"])
    def test_formatos_con_ano(self, texto: str) -> None:
        assert weather.parsear_fecha(texto, HOY) == date(2026, 10, 4)

    def test_sin_ano_toma_el_proximo_que_ocurra(self) -> None:
        assert weather.parsear_fecha("04/10", HOY) == date(2026, 10, 4)

    def test_sin_ano_ya_pasado_salta_al_siguiente(self) -> None:
        """01/01 consultado en septiembre es el del ano que viene, no el que ya paso."""
        assert weather.parsear_fecha("01/01", HOY) == date(2027, 1, 1)

    @pytest.mark.parametrize("texto", ["el sabado", "manana", "", "32/13/2026"])
    def test_ilegibles(self, texto: str) -> None:
        assert weather.parsear_fecha(texto, HOY) is None


class TestCodigosWmo:
    def test_traduce_a_algo_publicable(self) -> None:
        assert weather.describir_codigo(95) == "tormenta electrica"
        assert weather.describir_codigo(0) == "despejado"

    def test_codigo_desconocido_no_revienta(self) -> None:
        assert "codigo 1234" in weather.describir_codigo(1234)

    def test_sin_dato(self) -> None:
        assert weather.describir_codigo(None) == "sin dato"


class TestLimites:
    async def test_fecha_pasada(self) -> None:
        ayer = (date.today() - timedelta(days=1)).isoformat()
        assert "ya paso" in await _llamar(lugar="Guadalajara", fecha=ayer)

    async def test_fuera_del_horizonte_prohibe_opinar(self) -> None:
        lejos = (date.today() + timedelta(days=40)).isoformat()
        salida = await _llamar(lugar="Guadalajara", fecha=lejos)
        assert "no hay" in salida.lower()
        assert "no afirmes nada del clima" in salida

    async def test_fecha_ilegible_pide_el_formato(self) -> None:
        salida = await _llamar(lugar="Guadalajara", fecha="el sabado")
        assert "aaaa-mm-dd" in salida

    async def test_el_horizonte_es_de_16_dias(self) -> None:
        assert weather.HORIZONTE_DIAS == 16


class TestConsultaReal:
    def _handler(self, con_resultados: bool = True, dias: int = 3):
        objetivo = (date.today() + timedelta(days=dias)).isoformat()

        def handler(req: httpx.Request) -> httpx.Response:
            if "geocoding" in str(req.url):
                if not con_resultados:
                    return httpx.Response(200, json={})
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "name": "Guadalajara",
                                "admin1": "Estado de Jalisco",
                                "latitude": 20.67,
                                "longitude": -103.35,
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "time": [objetivo],
                        "weather_code": [95],
                        "temperature_2m_max": [28.4],
                        "temperature_2m_min": [17.1],
                        "precipitation_probability_max": [80],
                        "precipitation_sum": [12.5],
                    }
                },
            )

        return handler

    async def test_pronostico_completo_con_fuente(self, mock_httpx) -> None:
        mock_httpx.usar(self._handler())
        objetivo = (date.today() + timedelta(days=3)).isoformat()
        salida = await _llamar(lugar="Guadalajara", fecha=objetivo)

        assert "Guadalajara, Estado de Jalisco" in salida
        assert "tormenta electrica" in salida
        assert "80%" in salida
        assert "Open-Meteo" in salida, "toda afirmacion lleva fuente"

    async def test_usa_la_timezone_de_la_comunidad(self, mock_httpx) -> None:
        mock_httpx.usar(self._handler())
        objetivo = (date.today() + timedelta(days=3)).isoformat()
        await _llamar(lugar="Guadalajara", fecha=objetivo)

        forecast = [r for r in mock_httpx.peticiones if "geocoding" not in str(r.url)][0]
        assert "America%2FMexico_City" in str(forecast.url)

    async def test_lugar_inexistente(self, mock_httpx) -> None:
        mock_httpx.usar(self._handler(con_resultados=False))
        objetivo = (date.today() + timedelta(days=3)).isoformat()
        salida = await _llamar(lugar="Xyzqw", fecha=objetivo)
        assert "No encontre el lugar" in salida

    async def test_fallo_de_red_no_deja_inventar(self, mock_httpx) -> None:
        def explota(req):
            raise httpx.ConnectError("sin red")

        mock_httpx.usar(explota)
        objetivo = (date.today() + timedelta(days=3)).isoformat()
        salida = await _llamar(lugar="Guadalajara", fecha=objetivo)
        assert "no inventes el pronostico" in salida
