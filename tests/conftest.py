"""Fixtures compartidas.

`FakeChatClient` permite probar el agente y el bucle de streaming sin tocar Azure
ni gastar tokens.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from agent_framework import ChatResponse, ChatResponseUpdate, Content, Message
from agent_framework._types import ResponseStream

from hxq_agent.config import Settings

# Prefijos de variables que configuran la app. Importar chainlit ejecuta load_dotenv(),
# asi que el `.env` del desarrollador acaba en os.environ y `Settings(_env_file=None)`
# lo sigue viendo. Sin aislarlo, la suite pasa o falla segun la maquina.
_PREFIJOS_PROPIOS = (
    "HXQ_",
    "AZURE_",
    "TAVILY_",
    "DATABASE_URL",
    "APPLICATIONINSIGHTS_",
    "OAUTH_",
    "CHAINLIT_",
)


@pytest.fixture(autouse=True)
def _entorno_aislado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quita la configuracion real del entorno antes de cada test.

    Los tests deben depender solo de lo que declaran, nunca del `.env` local.
    """
    for nombre in list(os.environ):
        if nombre.upper().startswith(_PREFIJOS_PROPIOS):
            monkeypatch.delenv(nombre, raising=False)

    # `get_settings` cachea por proceso: sin limpiarla, un test que cambia el entorno
    # seguiria viendo la configuracion del anterior.
    from hxq_agent.config import get_settings

    get_settings.cache_clear()


class FakeChatClient:
    """Cliente de chat que devuelve un texto fijo, troceado como si fuera streaming."""

    def __init__(self, reply: str = "Listo. Aqui va el aviso.") -> None:
        self.reply = reply
        self.calls: list[Sequence[Message]] = []
        self.options: list[Any] = []

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: Any = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append(list(messages))
        self.options.append(options)
        chunks = self.reply.split(" ")

        async def _updates() -> AsyncIterator[ChatResponseUpdate]:
            for i, chunk in enumerate(chunks):
                text = chunk if i == 0 else f" {chunk}"
                yield ChatResponseUpdate(
                    contents=[Content.from_text(text)],
                    role="assistant",
                )

        if stream:
            return ResponseStream(
                _updates(),
                finalizer=lambda updates: ChatResponse.from_updates(updates),
            )

        async def _single() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", [Content.from_text(self.reply)])])

        return _single()


@pytest.fixture
def fake_client() -> FakeChatClient:
    return FakeChatClient()


@pytest.fixture
def settings() -> Settings:
    """Settings deterministas, sin leer `.env` del disco."""
    return Settings(
        _env_file=None,
        azure_openai_endpoint="https://fake.openai.azure.com/",
        azure_openai_api_key="fake-key",
        hxq_admin_emails="admin@hxq.test, otro@hxq.test",
        hxq_community_name="HXQ",
        hxq_community_city="Guadalajara",
        hxq_timezone="America/Mexico_City",
    )


@pytest.fixture
def mock_httpx(monkeypatch: pytest.MonkeyPatch):
    """Intercepta las llamadas HTTP de las tools sin dependencias extra.

    `usar(handler)` instala el handler; `peticiones` acumula lo que salio, para poder
    afirmar sobre el cuerpo enviado (por ejemplo, que la busqueda 'oficial' realmente
    restringe dominios).
    """
    import httpx as _httpx

    real_client = _httpx.AsyncClient

    class Registro:
        def __init__(self) -> None:
            self.peticiones: list[_httpx.Request] = []

        def usar(self, handler) -> None:
            def envoltura(request: _httpx.Request) -> _httpx.Response:
                self.peticiones.append(request)
                return handler(request)

            def factory(*args, **kwargs):
                kwargs["transport"] = _httpx.MockTransport(envoltura)
                return real_client(*args, **kwargs)

            monkeypatch.setattr(_httpx, "AsyncClient", factory)

    return Registro()
