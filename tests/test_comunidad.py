"""Datos de la comunidad: esquemas, busqueda, cambios propuestos y su integracion.

La base se sustituye por un dict en memoria: lo que importa aqui es que un dato mal
formado nunca llegue al boton de confirmar, que "el quiosco" encuentre el punto real, y
que los codigos de jugadores lleven siempre su aviso de uso interno.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from hxq_agent.agent.tools import calendario as cal
from hxq_agent.agent.tools import comunidad as tools
from hxq_agent.config import Settings
from hxq_agent.schemas.comunidad import (
    CodigoJugador,
    PuntoReunion,
    buscar_en,
    normalizar,
)
from hxq_agent.storage import comunidad as almacen
from hxq_agent.storage.comunidad import ComunidadNoDisponible

PALACIO = {
    "nombre": "Palacio Municipal",
    "sede": True,
    "concurrencia": "alta",
    "variantes": ["explanada", "presidencia", "palacio", "quiosco"],
    "latitud": 19.3601509,
    "longitud": -99.351957,
    "zona": "centro",
}
JARDIN = {
    "nombre": "Jardín",
    "sede": False,
    "concurrencia": "alta",
    "variantes": ["jardin de la cultura"],
    "latitud": 19.357882,
    "longitud": -99.341181,
    "zona": "san juan",
}
MARCO = {
    "alias": "Marco",
    "nombre_jugador": "HermusHero",
    "codigo": "123456789012",
    "equipo": "instinct",
}


@pytest.fixture
def base(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Sustituye la tabla por un dict tema -> registros."""
    datos: dict[str, list[dict[str, Any]]] = {
        "puntos_reunion": [dict(PALACIO), dict(JARDIN)],
        "codigos_jugadores": [dict(MARCO)],
    }

    async def listar(tema: str, **_: Any) -> list[dict[str, Any]]:
        return [dict(f) for f in datos.get(tema, [])]

    # `obtener` es el real: se apoya en `listar`, y su comparacion sin acentos es parte
    # de lo que se prueba.
    monkeypatch.setattr(almacen, "listar", listar)
    return datos


@pytest.fixture
def sin_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configuracion sin DATABASE_URL, ignorando el `.env` local.

    El conftest limpia el entorno, pero `Settings` tambien lee `.env`: con un Postgres
    local configurado ahi, estos tests acabarian hablando con la base de verdad.
    """
    monkeypatch.setattr(almacen, "get_settings", lambda: Settings(_env_file=None))


async def _invocar(herramienta, **kwargs) -> str:
    res = await herramienta.invoke(arguments=kwargs)
    if isinstance(res, list):
        return "\n".join(c.text or "" for c in res)
    return str(res)


class TestEsquemas:
    def test_codigo_con_espacios_se_normaliza(self) -> None:
        """Se acepta tal como lo copia la gente del juego."""
        r = CodigoJugador.model_validate({**MARCO, "codigo": "1234 5678 9012"})
        assert r.codigo == "123456789012"
        assert r.codigo_legible == "1234 5678 9012"

    def test_codigo_conserva_el_cero_inicial(self) -> None:
        assert CodigoJugador.model_validate({**MARCO, "codigo": "012345678901"}).codigo == (
            "012345678901"
        )

    @pytest.mark.parametrize("codigo", ["123543412412412", "1234", "1234abcd9012"])
    def test_codigo_que_no_son_12_digitos_se_rechaza(self, codigo: str) -> None:
        with pytest.raises(ValidationError, match="12 digitos"):
            CodigoJugador.model_validate({**MARCO, "codigo": codigo})

    def test_equipo_desconocido_se_rechaza(self) -> None:
        with pytest.raises(ValidationError):
            CodigoJugador.model_validate({**MARCO, "equipo": "rocket"})

    def test_equipo_en_mayusculas_vale(self) -> None:
        assert CodigoJugador.model_validate({**MARCO, "equipo": "Mystic"}).equipo == "mystic"

    def test_coordenadas_fuera_de_rango(self) -> None:
        with pytest.raises(ValidationError, match="latitud"):
            PuntoReunion.model_validate({**PALACIO, "latitud": 199.36})

    def test_variantes_sin_duplicados_por_acentos(self) -> None:
        r = PuntoReunion.model_validate({**PALACIO, "variantes": ["Quiosco", "quiosco ", "kiosko"]})
        assert r.variantes == ["Quiosco", "kiosko"]

    def test_link_de_maps(self) -> None:
        r = PuntoReunion.model_validate(PALACIO)
        assert r.maps_url.endswith("query=19.3601509,-99.351957")


class TestBusqueda:
    def test_normalizar_quita_acentos_y_mayusculas(self) -> None:
        assert normalizar("  JARDÍN  de la Cultura ") == "jardin de la cultura"

    def test_sin_consulta_devuelve_todo(self) -> None:
        assert len(buscar_en([PALACIO, JARDIN], "")) == 2

    @pytest.mark.parametrize("consulta", ["quiosco", "el quiosco", "Nos vemos en el QUIOSCO"])
    def test_una_variante_encuentra_el_punto(self, consulta: str) -> None:
        assert [f["nombre"] for f in buscar_en([PALACIO, JARDIN], consulta)] == [
            "Palacio Municipal"
        ]

    @pytest.mark.parametrize("consulta", ["jardin", "Jardín", "JARDIN"])
    def test_sin_importar_acentos(self, consulta: str) -> None:
        assert [f["nombre"] for f in buscar_en([PALACIO, JARDIN], consulta)] == ["Jardín"]

    def test_palabras_cortas_o_parciales_no_cuelan_coincidencias(self) -> None:
        """'alta' (concurrencia) no debe coincidir dentro de 'falta'."""
        assert buscar_en([PALACIO, JARDIN], "falta poco") == []


class TestConsultar:
    async def test_puntos_incluye_variantes_coordenadas_y_maps(self, base) -> None:
        salida = await _invocar(tools.consultar_comunidad, tema="puntos_reunion")
        assert "Palacio Municipal (sede)" in salida
        assert "quiosco" in salida
        assert "19.3601509,-99.351957" in salida
        assert "google.com/maps" in salida

    async def test_busqueda_filtra(self, base) -> None:
        salida = await _invocar(
            tools.consultar_comunidad, tema="puntos_reunion", busqueda="el quiosco"
        )
        assert "Palacio Municipal" in salida
        assert "Jardín" not in salida

    async def test_sin_coincidencia_en_puntos_dice_usar_el_lugar_tal_cual(self, base) -> None:
        salida = await _invocar(
            tools.consultar_comunidad, tema="puntos_reunion", busqueda="Plaza Interlomas"
        )
        assert "tal cual" in salida

    async def test_codigos_llevan_aviso_de_uso_interno(self, base) -> None:
        salida = await _invocar(tools.consultar_comunidad, tema="codigos_jugadores")
        assert "1234 5678 9012" in salida
        assert tools.AVISO_PRIVADO in salida

    async def test_los_temas_publicos_no_llevan_el_aviso(self, base) -> None:
        salida = await _invocar(tools.consultar_comunidad, tema="puntos_reunion")
        assert tools.AVISO_PRIVADO not in salida

    async def test_tema_vacio_sugiere_proponer_cambio(self, base) -> None:
        salida = await _invocar(tools.consultar_comunidad, tema="historia")
        assert "proponer_cambio_comunidad" in salida

    async def test_sin_base_de_datos_no_revienta(self, sin_base) -> None:
        """Sin DATABASE_URL se responde, no se lanza."""
        salida = await _invocar(tools.consultar_comunidad, tema="puntos_reunion")
        assert "no estan disponibles" in salida


class TestPrepararCambio:
    async def test_actualizacion_parcial_mezcla_con_lo_guardado(self, base) -> None:
        cambio = await tools.preparar_cambio(
            "puntos_reunion", "guardar", "jardin", json.dumps({"zona": "centro"})
        )
        assert isinstance(cambio, tools.Cambio)
        assert cambio.despues["zona"] == "centro"
        assert cambio.despues["latitud"] == JARDIN["latitud"], "lo no enviado se conserva"
        assert cambio.nombre_actual == "Jardín"
        assert "san juan → centro" in cambio.resumen()

    async def test_nuevo_registro_incompleto_explica_cada_campo(self, base) -> None:
        resultado = await tools.preparar_cambio(
            "puntos_reunion", "guardar", "Deportivo", json.dumps({"zona": "san martin"})
        )
        assert isinstance(resultado, str)
        for campo in ("concurrencia", "latitud", "longitud"):
            assert f"- {campo}:" in resultado

    async def test_nuevo_registro_toma_la_clave_del_nombre(self, base) -> None:
        cambio = await tools.preparar_cambio(
            "codigos_jugadores",
            "guardar",
            "Ana",
            json.dumps({"nombre_jugador": "AnaGO", "codigo": "1111 2222 3333", "equipo": "valor"}),
        )
        assert isinstance(cambio, tools.Cambio)
        assert cambio.antes is None
        assert cambio.despues["alias"] == "Ana"
        assert cambio.despues["codigo"] == "111122223333"

    async def test_sin_cambios_reales_no_propone_nada(self, base) -> None:
        resultado = await tools.preparar_cambio(
            "puntos_reunion", "guardar", "Jardín", json.dumps({"zona": "san juan"})
        )
        assert isinstance(resultado, str)
        assert "nada que cambiar" in resultado

    async def test_no_se_renombra_encima_de_otro(self, base) -> None:
        resultado = await tools.preparar_cambio(
            "puntos_reunion", "guardar", "Jardín", json.dumps({"nombre": "palacio municipal"})
        )
        assert isinstance(resultado, str)
        assert "Ya existe" in resultado

    async def test_eliminar_lo_que_no_existe(self, base) -> None:
        resultado = await tools.preparar_cambio("puntos_reunion", "eliminar", "La Luna")
        assert isinstance(resultado, str)
        assert "No hay nada" in resultado

    async def test_eliminar_usa_el_nombre_guardado(self, base) -> None:
        cambio = await tools.preparar_cambio("puntos_reunion", "eliminar", "jardin")
        assert isinstance(cambio, tools.Cambio)
        assert cambio.nombre == "Jardín"

    async def test_datos_que_no_son_json(self, base) -> None:
        resultado = await tools.preparar_cambio("puntos_reunion", "guardar", "Jardín", "zona=x")
        assert isinstance(resultado, str)
        assert "JSON" in resultado


class TestProponerCambio:
    async def test_no_escribe_y_deja_el_cambio_para_la_ui(self, base, monkeypatch) -> None:
        async def prohibido(*a, **k):
            raise AssertionError("la tool no debe escribir")

        monkeypatch.setattr(almacen, "guardar", prohibido)
        salida = await _invocar(
            tools.proponer_cambio_comunidad,
            tema="puntos_reunion",
            operacion="guardar",
            nombre="Jardín",
            datos=json.dumps({"concurrencia": "media"}),
        )
        assert "NO digas que se guardo" in salida

        cambio = tools.tomar_cambio(salida)
        assert cambio is not None and cambio.despues["concurrencia"] == "media"
        assert tools.tomar_cambio(salida) is None, "se recoge una sola vez"

    async def test_un_cambio_invalido_no_deja_nada_pendiente(self, base) -> None:
        salida = await _invocar(
            tools.proponer_cambio_comunidad,
            tema="codigos_jugadores",
            operacion="guardar",
            nombre="Marco",
            datos=json.dumps({"codigo": "123"}),
        )
        assert "12 digitos" in salida
        assert tools.tomar_cambio(salida) is None

    async def test_sin_base_de_datos_no_revienta(self, sin_base) -> None:
        salida = await _invocar(
            tools.proponer_cambio_comunidad,
            tema="historia",
            operacion="eliminar",
            nombre="Origenes",
        )
        assert "No se pueden cambiar" in salida


class TestAlmacen:
    async def test_sin_database_url_avisa_con_su_excepcion(self, sin_base) -> None:
        with pytest.raises(ComunidadNoDisponible):
            await almacen.listar("puntos_reunion")


class TestCalendarioConCoordenadas:
    async def test_lleva_geo_y_link_de_maps(self) -> None:
        from pathlib import Path

        from icalendar import Calendar

        salida = await _invocar(
            cal.crear_ics,
            titulo="Quedada",
            lugar="Palacio Municipal",
            fecha="2026-10-03",
            hora_inicio="18:00",
            coordenadas="19.3601509,-99.351957",
        )
        ruta = Path(salida.splitlines()[0].partition(": ")[2])
        evento = Calendar.from_ical(ruta.read_bytes()).walk("VEVENT")[0]
        assert evento.get("geo").latitude == pytest.approx(19.3601509)
        assert "google.com/maps" in str(evento.get("description"))

    async def test_coordenadas_invalidas_se_explican(self) -> None:
        salida = await _invocar(
            cal.crear_ics,
            titulo="Q",
            lugar="P",
            fecha="2026-10-03",
            hora_inicio="18:00",
            coordenadas="el quiosco",
        )
        assert "no son validas" in salida
