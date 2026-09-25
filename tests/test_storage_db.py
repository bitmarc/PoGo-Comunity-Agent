"""Persistencia: normalizacion del DSN y degradacion cuando no hay base de datos.

El caso importante no es el feliz: es que la app siga viva sin base de datos, porque un
despliegue al que se le cayo Neon debe seguir respondiendo aunque pierda el historial.
"""

from __future__ import annotations

import pytest

from hxq_agent.config import Settings
from hxq_agent.storage import db


@pytest.fixture(autouse=True)
def _limpiar_cache():
    db.reset_para_tests()
    yield
    db.reset_para_tests()


class TestNormalizarDsn:
    def test_quita_el_dialecto_de_sqlalchemy(self) -> None:
        """El data layer usa asyncpg crudo y no entiende 'postgresql+asyncpg://'."""
        assert db.normalizar_dsn("postgresql+asyncpg://u:p@h/d") == "postgresql://u:p@h/d"

    def test_tambien_la_variante_postgres(self) -> None:
        assert db.normalizar_dsn("postgres+asyncpg://u:p@h/d") == "postgresql://u:p@h/d"

    def test_quita_channel_binding_que_neon_incluye(self) -> None:
        """Neon lo pone en su cadena y asyncpg no lo soporta."""
        salida = db.normalizar_dsn(
            "postgresql://u:p@ep.neon.tech/neondb?sslmode=require&channel_binding=require"
        )
        assert "channel_binding" not in salida
        assert "sslmode=require" in salida, "sslmode SI hace falta, no se toca"

    def test_si_channel_binding_era_el_unico_parametro_no_deja_interrogacion_suelta(self) -> None:
        assert db.normalizar_dsn("postgresql://u:p@h/d?channel_binding=require") == (
            "postgresql://u:p@h/d"
        )

    def test_un_dsn_limpio_no_se_toca(self) -> None:
        original = "postgresql://u:p@h/d?sslmode=require"
        assert db.normalizar_dsn(original) == original

    def test_recorta_espacios(self) -> None:
        assert db.normalizar_dsn("  postgresql://u:p@h/d  ") == "postgresql://u:p@h/d"


class TestDataLayerSinBaseDeDatos:
    def test_sin_database_url_devuelve_none(self) -> None:
        assert db.build_data_layer(Settings(_env_file=None, database_url="")) is None

    def test_solo_espacios_cuenta_como_vacio(self) -> None:
        assert db.build_data_layer(Settings(_env_file=None, database_url="   ")) is None

    def test_un_dsn_invalido_no_tumba_la_app(self, monkeypatch) -> None:
        """Preferimos perder el historial antes que no arrancar."""

        def explota(*args, **kwargs):
            raise RuntimeError("dsn invalido")

        import chainlit.data.chainlit_data_layer as cdl

        monkeypatch.setattr(cdl, "ChainlitDataLayer", explota)
        assert db.build_data_layer(Settings(_env_file=None, database_url="basura")) is None


class TestCacheDelDataLayer:
    def test_no_se_reconstruye_en_cada_llamada(self, monkeypatch) -> None:
        """Chainlit invoca el callback por conexion; un pool por usuario agotaria Neon."""
        llamadas = []

        class Falso:
            def __init__(self, **kwargs):
                llamadas.append(kwargs)

        import chainlit.data.chainlit_data_layer as cdl

        monkeypatch.setattr(cdl, "ChainlitDataLayer", Falso)
        s = Settings(_env_file=None, database_url="postgresql://u:p@h/d")

        db.build_data_layer(s)
        db.build_data_layer(s)
        db.build_data_layer(s)
        assert len(llamadas) == 1

    def test_el_dsn_llega_normalizado_al_data_layer(self, monkeypatch) -> None:
        recibido = {}

        class Falso:
            def __init__(self, **kwargs):
                recibido.update(kwargs)

        import chainlit.data.chainlit_data_layer as cdl

        monkeypatch.setattr(cdl, "ChainlitDataLayer", Falso)
        db.build_data_layer(
            Settings(
                _env_file=None,
                database_url="postgresql+asyncpg://u:p@h/d?channel_binding=require",
            )
        )
        assert recibido["database_url"] == "postgresql://u:p@h/d"


class TestStorageClient:
    def test_sin_cuenta_configurada_devuelve_none(self) -> None:
        """En local no hay Blob; el historial de texto funciona igual."""
        assert db.build_storage_client(Settings(_env_file=None, azure_storage_account="")) is None

    def test_cuenta_sin_contenedor_tampoco(self) -> None:
        s = Settings(_env_file=None, azure_storage_account="cuenta", azure_storage_container="")
        assert db.build_storage_client(s) is None

    def test_configurado_construye_el_cliente_de_managed_identity(self) -> None:
        s = Settings(
            _env_file=None, azure_storage_account="cuenta", azure_storage_container="media"
        )
        cliente = db.build_storage_client(s)
        assert cliente is not None
        assert cliente.account == "cuenta"
        assert cliente.container == "media"
        assert cliente._account_url == "https://cuenta.blob.core.windows.net"
