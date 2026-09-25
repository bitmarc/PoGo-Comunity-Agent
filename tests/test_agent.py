"""El agente: construccion, instrucciones y el bucle de streaming.

El test de streaming es el que de verdad importa en la Fase 0: prueba que la cadena
`Agent.run(stream=True)` -> updates -> texto funciona, que es exactamente lo que `app.py`
transmite a la UI.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from hxq_agent.agent.factory import ConfigError, build_agent, build_chat_client
from hxq_agent.agent.instructions import build_instructions
from hxq_agent.config import Settings


class TestBuildChatClient:
    def test_sin_endpoint_falla_con_mensaje_util(self, settings: Settings) -> None:
        roto = settings.model_copy(update={"azure_openai_endpoint": ""})
        with pytest.raises(ConfigError, match="AZURE_OPENAI_ENDPOINT"):
            build_chat_client(roto)

    def test_con_api_key_construye(self, settings: Settings) -> None:
        assert build_chat_client(settings) is not None


class TestInstructions:
    def test_resuelve_la_fecha_de_hoy(self, settings: Settings) -> None:
        """Sin la fecha inyectada el agente no puede resolver "el sabado"."""
        out = build_instructions(settings, now=datetime(2026, 10, 1, 20, 0))
        assert "01/10/2026" in out
        assert "jueves" in out

    def test_datetime_naive_se_lee_como_hora_de_la_comunidad(self, settings: Settings) -> None:
        """23:30 del 1/10 en Mexico no debe convertirse en el dia 2 por la tz del servidor."""
        out = build_instructions(settings, now=datetime(2026, 10, 1, 23, 30))
        assert "01/10/2026" in out

    def test_incluye_el_contexto_de_la_comunidad(self, settings: Settings) -> None:
        out = build_instructions(settings)
        assert "HXQ" in out
        assert "Guadalajara" in out

    @pytest.mark.parametrize(
        "regla",
        [
            "NUNCA inventes",  # no alucinar fechas de eventos
            "PREGUNTALO",  # pedir datos que faltan
            "Tu no publicas nada",  # human-in-the-loop
            "no tiene API publica",  # limitacion real de Campfire
        ],
    )
    def test_las_reglas_duras_estan_presentes(self, settings: Settings, regla: str) -> None:
        assert regla in build_instructions(settings)


class TestAgentStreaming:
    async def test_transmite_el_texto_por_partes(self, settings: Settings, fake_client) -> None:
        agent = build_agent(settings=settings, client=fake_client)
        session = agent.create_session()

        tokens: list[str] = []
        stream = agent.run("hola", stream=True, session=session)
        async for update in stream:
            if update.text:
                tokens.append(update.text)

        assert len(tokens) > 1, "deberia llegar en varios trozos, no de golpe"
        assert "".join(tokens) == fake_client.reply

    async def test_el_system_prompt_llega_al_cliente(self, settings: Settings, fake_client) -> None:
        """MAF no prepende el prompt como mensaje: lo manda en `options["instructions"]`."""
        agent = build_agent(settings=settings, client=fake_client)
        stream = agent.run("hola", stream=True, session=agent.create_session())
        async for _ in stream:
            pass

        instrucciones = fake_client.options[0]["instructions"]
        assert "Pokemon GO" in instrucciones
        assert "HXQ" in instrucciones

        mensajes = " ".join(m.text or "" for m in fake_client.calls[0])
        assert "hola" in mensajes

    async def test_la_sesion_acumula_el_historial(self, settings: Settings, fake_client) -> None:
        """Sin sesion cada turno seria independiente y el agente perderia el hilo."""
        agent = build_agent(settings=settings, client=fake_client)
        session = agent.create_session()

        for texto in ("primer mensaje", "segundo mensaje"):
            stream = agent.run(texto, stream=True, session=session)
            async for _ in stream:
                pass

        segundo_turno = " ".join(m.text or "" for m in fake_client.calls[1])
        assert "primer mensaje" in segundo_turno, "el turno 2 deberia ver el turno 1"


class TestApiVersion:
    """Regresion: un api-version fijo rompe la Responses API con 400 BadRequest.

    Cada cliente de MAF tiene su propio default correcto segun la superficie
    (Responses -> "preview"). Si se fija uno solo aqui, el que no coincida falla.
    """

    def test_vacio_no_se_manda_al_cliente(self, settings: Settings) -> None:
        sin_version = settings.model_copy(update={"azure_openai_api_version": ""})
        cliente = build_chat_client(sin_version)
        assert "2024-12-01-preview" not in str(getattr(cliente, "base_url", ""))

    def test_solo_espacios_se_trata_como_vacio(self, settings: Settings) -> None:
        build_chat_client(settings.model_copy(update={"azure_openai_api_version": "   "}))

    def test_valor_explicito_se_respeta(self, settings: Settings) -> None:
        """Clavar una version sigue siendo posible cuando es a proposito."""
        build_chat_client(settings.model_copy(update={"azure_openai_api_version": "preview"}))

    def test_el_default_del_proyecto_es_vacio(self) -> None:
        """Si alguien vuelve a poner un default aqui, este test lo caza."""
        assert Settings(_env_file=None).azure_openai_api_version == ""
