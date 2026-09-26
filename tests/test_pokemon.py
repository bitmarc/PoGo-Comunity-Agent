"""Arte oficial y datos de Pokemon desde PokeAPI."""

from __future__ import annotations

import json

import httpx
import pytest

from hxq_agent.brand import pokemon as pk


@pytest.fixture(autouse=True)
def _cache_aislada(tmp_path, monkeypatch):
    """Cache en un directorio temporal: los tests no deben ensuciar el repo."""
    monkeypatch.setenv("HXQ_DATA_DIR", str(tmp_path))


class TestNormalizarNombre:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("Cottonee", "cottonee"),
            ("Mega Charizard Y", "mega-charizard-y"),
            ("  Deoxys  Attack ", "deoxys-attack"),
            ("Pokémon", "pokemon"),
            ("Nidoran♀", "nidoran"),
        ],
    )
    def test_casos(self, entrada: str, esperado: str) -> None:
        assert pk.normalizar_nombre(entrada) == esperado

    def test_vacio_falla(self) -> None:
        with pytest.raises(pk.PokemonNoEncontrado):
            import asyncio

            asyncio.run(pk.obtener_pokemon("   "))


def _handler(con_arte: bool = True, existe: bool = True):
    def h(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "official-artwork" in url:
            return httpx.Response(200, content=b"PNG-FALSO") if con_arte else httpx.Response(404)
        if "/pokemon-species/" in url or "species" in url:
            return httpx.Response(
                200,
                json={
                    "names": [
                        {"language": {"name": "en"}, "name": "Cottonee"},
                        {"language": {"name": "es"}, "name": "Cottonee"},
                    ]
                },
            )
        if "/pokemon/" in url:
            if not existe:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "id": 546,
                    "name": "cottonee",
                    "types": [{"type": {"name": "grass"}}, {"type": {"name": "fairy"}}],
                    "species": {"url": "https://pokeapi.co/api/v2/pokemon-species/546/"},
                },
            )
        return httpx.Response(404)

    return h


class TestObtenerPokemon:
    async def test_devuelve_tipos_y_arte(self, mock_httpx) -> None:
        mock_httpx.usar(_handler())
        d = await pk.obtener_pokemon("cottonee")
        assert d["tipos"] == ["grass", "fairy"]
        assert d["arte"] == b"PNG-FALSO"
        assert d["numero"] == 546

    async def test_los_tipos_alimentan_los_acentos_reales(self, mock_httpx) -> None:
        """El punto de traerlos: los colores salen del Pokemon, no de lo que el modelo
        crea recordar."""
        from hxq_agent.brand.tipos import COLORES_TIPO, acentos_desde_tipos

        mock_httpx.usar(_handler())
        d = await pk.obtener_pokemon("cottonee")
        a1, a2 = acentos_desde_tipos(d["tipos"])
        assert a1 == COLORES_TIPO["planta"]
        assert a2 == COLORES_TIPO["hada"]

    async def test_desconocido_da_un_error_accionable(self, mock_httpx) -> None:
        mock_httpx.usar(_handler(existe=False))
        with pytest.raises(pk.PokemonNoEncontrado, match="inventado"):
            await pk.obtener_pokemon("inventado")

    async def test_sin_arte_no_revienta(self, mock_httpx) -> None:
        """Algunas formas no tienen arte oficial; la pieza debe salir igual."""
        mock_httpx.usar(_handler(con_arte=False))
        d = await pk.obtener_pokemon("cottonee")
        assert d["arte"] == b""
        assert d["tipos"] == ["grass", "fairy"]

    async def test_la_cache_evita_repetir_consultas(self, mock_httpx) -> None:
        """PokeAPI pide cachear en vez de repetir; el arte oficial no cambia."""
        mock_httpx.usar(_handler())
        await pk.obtener_pokemon("cottonee")
        n = len(mock_httpx.peticiones)
        await pk.obtener_pokemon("Cottonee")
        assert len(mock_httpx.peticiones) == n, "la segunda deberia salir de cache"

    async def test_se_identifica_con_user_agent(self, mock_httpx) -> None:
        """PokeAPI y Pokebattler piden identificar el cliente."""
        mock_httpx.usar(_handler())
        await pk.obtener_pokemon("cottonee")
        assert "HuixquiGo" in mock_httpx.peticiones[0].headers["user-agent"]

    async def test_la_cache_guarda_json_valido(self, mock_httpx, tmp_path) -> None:
        mock_httpx.usar(_handler())
        await pk.obtener_pokemon("cottonee")
        archivo = tmp_path / "cache_pokemon" / "cottonee.json"
        assert json.loads(archivo.read_text(encoding="utf-8"))["numero"] == 546
