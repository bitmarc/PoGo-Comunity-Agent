"""Entrypoint de Chainlit.

Traduce entre la UI y el agente. Ninguna regla de negocio vive aqui.

Correr en local (PowerShell, desde la raiz del proyecto):
    ./.venv/Scripts/chainlit.exe run src/hxq_agent/app.py -w
"""

from __future__ import annotations

import logging

import chainlit as cl

import hxq_agent.auth  # noqa: F401  # importarlo registra el @cl.oauth_callback
from hxq_agent.agent.factory import ConfigError, build_agent
from hxq_agent.agent.instructions import build_instructions
from hxq_agent.config import get_settings
from hxq_agent.ui.settings import (
    CLAVE_PREFERENCIAS,
    PREFERENCIAS_POR_DEFECTO,
    build_chat_settings,
    describir_preferencias,
)
from hxq_agent.ui.starters import build_starters
from hxq_agent.ui.steps import mostrar_tools_en_ui

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AGENT_KEY = "hxq_agent"
_SESSION_KEY = "hxq_session"


@cl.set_starters
async def set_starters() -> list[cl.Starter]:
    return build_starters()


@cl.on_chat_start
async def on_chat_start() -> None:
    """Un agente y una sesion por conversacion.

    La sesion es la que le da memoria al agente dentro del hilo; sin ella cada turno
    seria independiente.
    """
    try:
        agent = build_agent()
    except ConfigError as exc:
        await cl.Message(
            content=(
                f"**No puedo arrancar todavia.** {exc}\n\n"
                "Revisa el `.env` y vuelve a cargar la pagina."
            )
        ).send()
        return

    cl.user_session.set(_AGENT_KEY, agent)
    cl.user_session.set(_SESSION_KEY, agent.create_session())
    cl.user_session.set(CLAVE_PREFERENCIAS, dict(PREFERENCIAS_POR_DEFECTO))
    await build_chat_settings().send()

    if not get_settings().tavily_api_key.strip():
        await cl.Message(
            content=(
                "Aviso: la busqueda web esta apagada porque falta `TAVILY_API_KEY`. "
                "Puedo redactar y conversar, pero **no puedo verificar fechas ni datos "
                "de eventos oficiales** hasta que la configures "
                "([key gratuita en tavily.com](https://tavily.com))."
            )
        ).send()

    logger.info("Conversacion iniciada")


@cl.on_settings_update
async def on_settings_update(settings: dict[str, str]) -> None:
    """Guarda los controles del chat. Surten efecto en el siguiente turno."""
    preferencias = {**PREFERENCIAS_POR_DEFECTO, **(settings or {})}
    cl.user_session.set(CLAVE_PREFERENCIAS, preferencias)
    logger.info("Preferencias actualizadas: %s", preferencias)


def _instrucciones_del_turno() -> str:
    """Instrucciones base mas las preferencias activas.

    Se reconstruyen en cada turno a proposito: asi las preferencias que el admin cambie a
    mitad de la conversacion aplican de inmediato, y la fecha de hoy se recalcula (importa
    si una sesion queda abierta pasada la medianoche).
    """
    base = build_instructions()
    extra = describir_preferencias(cl.user_session.get(CLAVE_PREFERENCIAS) or {})
    return f"{base}\n\n{extra}" if extra else base


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Pasa el mensaje al agente y transmite la respuesta token a token."""
    agent = cl.user_session.get(_AGENT_KEY)
    session = cl.user_session.get(_SESSION_KEY)

    if agent is None:
        await cl.Message(
            content="La sesion no arranco bien. Recarga la pagina para volver a intentarlo."
        ).send()
        return

    reply = cl.Message(content="")
    await reply.send()

    try:
        stream = agent.run(
            message.content,
            stream=True,
            session=session,
            middleware=[mostrar_tools_en_ui],
            options={"instructions": _instrucciones_del_turno()},
        )
        async for update in stream:
            if update.text:
                await reply.stream_token(update.text)
    except Exception:
        logger.exception("Fallo al ejecutar el agente")
        await reply.stream_token(
            "\n\n_Algo fallo al generar la respuesta. Intenta de nuevo; si sigue, revisa los logs._"
        )

    await reply.update()
