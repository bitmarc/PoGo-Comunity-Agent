"""Fixtures compartidas.

`FakeChatClient` permite probar el agente y el bucle de streaming sin tocar Azure
ni gastar tokens.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from agent_framework import ChatResponse, ChatResponseUpdate, Content, Message
from agent_framework._types import ResponseStream

from hxq_agent.config import Settings


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
