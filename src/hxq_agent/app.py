"""Entrypoint de Chainlit.

Unico archivo (junto con `auth.py` y `ui/`) que conoce Chainlit. Su trabajo es traducir
entre la UI y el agente; ninguna regla de negocio vive aqui.

Correr en local:
    python -m uv run chainlit run src/hxq_agent/app.py -w
"""

from __future__ import annotations

import logging

import chainlit as cl

import hxq_agent.auth  # noqa: F401  # importarlo registra el @cl.oauth_callback
from hxq_agent.agent.factory import ConfigError, build_agent
from hxq_agent.ui.starters import build_starters

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
    logger.info("Conversacion iniciada")


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
        stream = agent.run(message.content, stream=True, session=session)
        async for update in stream:
            if update.text:
                await reply.stream_token(update.text)
    except Exception:
        logger.exception("Fallo al ejecutar el agente")
        await reply.stream_token(
            "\n\n_Algo fallo al generar la respuesta. Intenta de nuevo; si sigue, revisa los logs._"
        )

    await reply.update()
