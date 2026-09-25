"""La tool de busqueda web.

Lo que se prueba no es que Tavily funcione, sino que el ambito 'oficial' realmente
restrinja las fuentes y que los fallos devuelvan un texto que el modelo pueda relayar en
vez de una excepcion que tumbe el turno.
"""

from __future__ import annotations

import json

import httpx
import pytest

from hxq_agent.agent.tools import search
from hxq_agent.config import Settings


@pytest.fixture(autouse=True)
def _limpiar_cache():
    search._cache.clear()
    yield
    search._cache.clear()


@pytest.fixture
def settings_con_tavily(monkeypatch: pytest.MonkeyPatch) -> Settings:
    s = Settings(_env_file=None, tavily_api_key="tvly-test", hxq_timezone="America/Mexico_City")
    monkeypatch.setattr(search, "get_settings", lambda: s)
    return s


def _respuesta_ok(resultados: list[dict] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "query": "x",
            "results": resultados
            if resultados is not None
            else [
                {
                    "title": "Community Day de octubre",
                    "url": "https://pokemongolive.com/post/cday-oct",
                    "content": "El evento es el sabado 4 de octubre de 11:00 a 14:00 hora local.",
                    "score": 0.98,
                    "published_date": "2026-09-15",
                }
            ],
            "usage": {"credits": 1},
        },
    )


async def _llamar(**kwargs) -> str:
    resultado = await search.buscar_web.invoke(arguments=kwargs)
    if isinstance(resultado, list):
        return "\n".join(c.text or "" for c in resultado)
    return str(resultado)


class TestSinConfigurar:
    async def test_sin_api_key_avisa_y_no_deja_inventar(self, monkeypatch) -> None:
        monkeypatch.setattr(search, "get_settings", lambda: Settings(_env_file=None))
        salida = await _llamar(query="Community Day", ambito="oficial")
        assert "TAVILY_API_KEY" in salida
        assert "No intentes responder de memoria" in salida


class TestAmbitos:
    async def test_oficial_restringe_a_las_fuentes_confiables(
        self, settings_con_tavily, mock_httpx
    ) -> None:
        """El punto entero del ambito 'oficial': un dato mal citado se publica a todos."""
        mock_httpx.usar(lambda req: _respuesta_ok())
        await _llamar(query="Community Day octubre 2026", ambito="oficial")

        cuerpo = json.loads(mock_httpx.peticiones[0].content)
        assert cuerpo["include_domains_mode"] == "restrict"
        assert set(cuerpo["include_domains"]) == {
            "pokemongolive.com",
            "leekduck.com",
            "serebii.net",
        }

    async def test_abierto_no_restringe_dominios(self, settings_con_tavily, mock_httpx) -> None:
        mock_httpx.usar(lambda req: _respuesta_ok())
        await _llamar(query="ideas de dinamicas", ambito="abierto")

        cuerpo = json.loads(mock_httpx.peticiones[0].content)
        assert "include_domains" not in cuerpo

    async def test_manda_el_bearer_y_pide_fecha_de_publicacion(
        self, settings_con_tavily, mock_httpx
    ) -> None:
        mock_httpx.usar(lambda req: _respuesta_ok())
        await _llamar(query="x", ambito="oficial")

        req = mock_httpx.peticiones[0]
        assert req.headers["authorization"] == "Bearer tvly-test"
        cuerpo = json.loads(req.content)
        # Sin fecha de publicacion el modelo no puede juzgar si un dato sigue vigente.
        assert cuerpo["include_published_date"] is True
        assert cuerpo["search_depth"] == "basic"  # 1 credito, no 2


class TestFormato:
    async def test_pega_la_url_a_cada_resultado(self, settings_con_tavily, mock_httpx) -> None:
        """El modelo tiene que citar; para eso necesita la URL junto al texto."""
        mock_httpx.usar(lambda req: _respuesta_ok())
        salida = await _llamar(query="x")

        assert "https://pokemongolive.com/post/cday-oct" in salida
        assert "Community Day de octubre" in salida
        assert "Publicado: 2026-09-15" in salida

    async def test_sin_resultados_prohibe_inventar(self, settings_con_tavily, mock_httpx) -> None:
        mock_httpx.usar(lambda req: _respuesta_ok([]))
        salida = await _llamar(query="evento que no existe")

        assert "Sin resultados" in salida
        assert "no inventes" in salida.lower()


class TestFallos:
    @pytest.mark.parametrize(
        ("codigo", "esperado"),
        [(401, "invalida o revocada"), (403, "invalida o revocada"), (429, "creditos")],
    )
    async def test_errores_http_devuelven_texto_no_excepcion(
        self, settings_con_tavily, mock_httpx, codigo: int, esperado: str
    ) -> None:
        """Una excepcion aqui tumba el turno; un texto lo puede relayar el modelo."""
        mock_httpx.usar(lambda req: httpx.Response(codigo, json={"error": "x"}))
        salida = await _llamar(query="x")
        assert esperado in salida

    async def test_fallo_de_red(self, settings_con_tavily, mock_httpx) -> None:
        def explota(req):
            raise httpx.ConnectError("sin red")

        mock_httpx.usar(explota)
        salida = await _llamar(query="x")
        assert "no respondio" in salida
        assert "no inventes" in salida.lower()


class TestCache:
    async def test_la_misma_query_del_mismo_dia_no_gasta_dos_creditos(
        self, settings_con_tavily, mock_httpx
    ) -> None:
        mock_httpx.usar(lambda req: _respuesta_ok())
        a = await _llamar(query="Community Day", ambito="oficial")
        b = await _llamar(query="  community   DAY  ", ambito="oficial")

        assert a == b
        assert len(mock_httpx.peticiones) == 1, "la segunda deberia salir de cache"

    async def test_ambitos_distintos_no_comparten_cache(
        self, settings_con_tavily, mock_httpx
    ) -> None:
        mock_httpx.usar(lambda req: _respuesta_ok())
        await _llamar(query="x", ambito="oficial")
        await _llamar(query="x", ambito="abierto")
        assert len(mock_httpx.peticiones) == 2


class TestFuentesConfigurables:
    def test_se_pueden_cambiar_sin_redeploy(self) -> None:
        s = Settings(_env_file=None, hxq_official_sources="a.com, b.org")
        assert s.official_sources == ["a.com", "b.org"]

    def test_el_default_son_las_tres_fuentes_pogo(self) -> None:
        assert Settings(_env_file=None).official_sources == [
            "pokemongolive.com",
            "leekduck.com",
            "serebii.net",
        ]
