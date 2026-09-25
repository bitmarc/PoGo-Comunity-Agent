"""Construccion del agente.

Punto unico de ensamblado. Cuando el system prompt empiece a pelearse consigo mismo
(Fase 5 del plan), `build_agent` se reemplaza por un `HandoffBuilder` de
`agent_framework.orchestrations` sin tocar las tools ni la UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from hxq_agent.agent.instructions import build_instructions
from hxq_agent.config import Settings, get_settings

AGENT_NAME = "HXQ"
AGENT_DESCRIPTION = (
    "Copiloto de comunicacion para administradores de una comunidad local de Pokemon GO."
)


class ConfigError(RuntimeError):
    """Configuracion incompleta o incoherente detectada al arrancar."""


def build_chat_client(settings: Settings | None = None) -> OpenAIChatClient:
    """Cliente de chat apuntado a Azure OpenAI.

    Con `AZURE_OPENAI_API_KEY` presente usa la key (comodo en local).
    Sin ella usa `DefaultAzureCredential`, que es el camino en Azure Container Apps
    via Managed Identity y evita tener secretos del modelo en el entorno.
    """
    settings = settings or get_settings()

    if not settings.azure_openai_endpoint:
        raise ConfigError(
            "Falta AZURE_OPENAI_ENDPOINT. Copia .env.example a .env y rellenalo, "
            "o exportalo en el entorno."
        )

    kwargs: dict[str, Any] = {
        "model": settings.hxq_chat_deployment,
        "azure_endpoint": settings.azure_openai_endpoint,
    }

    # Solo se manda si esta configurada a proposito. Omitirla deja que MAF use el default
    # de la superficie que toca (Responses -> "preview"), que es lo que queremos.
    if settings.azure_openai_api_version.strip():
        kwargs["api_version"] = settings.azure_openai_api_version.strip()

    if settings.uses_managed_identity:
        from azure.identity import DefaultAzureCredential

        kwargs["credential"] = DefaultAzureCredential()
    else:
        kwargs["api_key"] = settings.azure_openai_api_key

    return OpenAIChatClient(**kwargs)


def build_agent(
    *,
    settings: Settings | None = None,
    tools: Sequence[Any] | None = None,
    client: Any | None = None,
) -> Agent:
    """Arma el agente conversacional.

    `client` se puede inyectar para tests: asi el agente se prueba sin tocar Azure.
    """
    settings = settings or get_settings()
    return Agent(
        client or build_chat_client(settings),
        build_instructions(settings),
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        tools=list(tools or []),
    )
