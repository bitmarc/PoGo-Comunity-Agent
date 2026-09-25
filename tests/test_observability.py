"""Telemetria: opcional, y nunca un motivo para que la app no arranque."""

from __future__ import annotations

import pytest

from hxq_agent import observability
from hxq_agent.config import Settings

# Los exportadores de Azure Monitor validan que la key sea un UUID al construirse.
CONEXION = (
    "InstrumentationKey=00000000-0000-0000-0000-000000000001;"
    "IngestionEndpoint=https://example.in.applicationinsights.azure.com/"
)


@pytest.fixture(autouse=True)
def _reset():
    observability._configurado = False
    yield
    observability._configurado = False


def test_sin_connection_string_no_se_activa() -> None:
    assert observability.configurar_telemetria(Settings(_env_file=None)) is False


def test_solo_espacios_cuenta_como_vacio() -> None:
    s = Settings(_env_file=None, applicationinsights_connection_string="   ")
    assert observability.configurar_telemetria(s) is False


def test_un_fallo_al_configurar_no_tumba_la_app(monkeypatch) -> None:
    """Si el exportador revienta, la app tiene que seguir arrancando."""
    import agent_framework.observability as afo

    def explota(**kwargs):
        raise RuntimeError("connection string mal formada")

    monkeypatch.setattr(afo, "configure_otel_providers", explota)
    s = Settings(_env_file=None, applicationinsights_connection_string=CONEXION)
    assert observability.configurar_telemetria(s) is False


def test_los_datos_sensibles_estan_apagados_por_defecto() -> None:
    """Los prompts llevan contenido de la comunidad; no van a telemetria sin pedirlo."""
    assert Settings(_env_file=None).hxq_telemetry_sensitive is False


def test_es_idempotente(monkeypatch) -> None:
    llamadas = []
    import agent_framework.observability as afo

    monkeypatch.setattr(afo, "configure_otel_providers", lambda **kw: llamadas.append(kw))
    monkeypatch.setattr(afo, "enable_instrumentation", lambda **kw: None)
    s = Settings(_env_file=None, applicationinsights_connection_string=CONEXION)
    monkeypatch.setattr(observability, "get_settings", lambda: s)
    assert observability.configurar_telemetria() is True
    assert observability.configurar_telemetria() is True
    assert len(llamadas) == 1, "no debe duplicar spans"
