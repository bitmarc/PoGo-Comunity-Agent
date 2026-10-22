"""Boton de confirmacion para los cambios en los datos de la comunidad.

El agente propone y el admin confirma. Mismo criterio que aprobar una pieza: nada que
termine en un aviso a la comunidad se escribe sin un clic humano, y un punto de reunion
o un codigo mal guardado se acaba publicando.

A diferencia de las piezas, el boton sale en cuanto la tool termina y no al cerrar el
turno: aqui no hay copy posterior que esperar.
"""

from __future__ import annotations

import logging
import uuid

import chainlit as cl

from hxq_agent.agent.tools.comunidad import Cambio
from hxq_agent.storage import comunidad as almacen
from hxq_agent.storage.comunidad import ComunidadNoDisponible

logger = logging.getLogger(__name__)

# Cambios ofrecidos, por id. Viven en la sesion porque el admin puede tardar en decidir.
CLAVE_CAMBIOS = "hxq_cambios_comunidad"


async def ofrecer_cambio(cambio: Cambio) -> None:
    """Enseña el cambio con sus botones."""
    cambios = cl.user_session.get(CLAVE_CAMBIOS) or {}
    cambio_id = uuid.uuid4().hex[:12]
    cambios[cambio_id] = cambio
    cl.user_session.set(CLAVE_CAMBIOS, cambios)

    await cl.Message(
        content=f"{cambio.resumen()}\n\n¿Lo aplico?",
        actions=[
            cl.Action(
                name="confirmar_cambio_comunidad",
                payload={"id": cambio_id},
                label="Confirmar",
                icon="check",
            ),
            cl.Action(
                name="cancelar_cambio_comunidad",
                payload={"id": cambio_id},
                label="Cancelar",
                icon="x",
            ),
        ],
    ).send()


@cl.action_callback("confirmar_cambio_comunidad")
async def confirmar_cambio(action: cl.Action) -> None:
    """Escribe el cambio en la base, firmado con el correo del admin."""
    cambios = cl.user_session.get(CLAVE_CAMBIOS) or {}
    cambio: Cambio | None = cambios.pop(action.payload.get("id"), None)
    cl.user_session.set(CLAVE_CAMBIOS, cambios)
    if cambio is None:
        await cl.Message(content="Ese cambio ya no esta disponible en esta sesion.").send()
        return

    usuario = cl.user_session.get("user")
    correo = getattr(usuario, "identifier", None) or "desconocido"

    try:
        if cambio.operacion == "eliminar":
            await almacen.eliminar(cambio.tema, cambio.nombre, por=correo)
        else:
            await almacen.guardar(
                cambio.tema,
                cambio.nombre_actual,
                cambio.despues or {},
                nombre=cambio.nombre,
                por=correo,
            )
    except ComunidadNoDisponible as exc:
        await cl.Message(content=f"No pude aplicarlo: {exc}").send()
        return
    except Exception:
        logger.exception("Fallo al aplicar un cambio de datos de la comunidad")
        await cl.Message(content="No pude aplicar el cambio. Revisa los logs.").send()
        return

    await action.remove()
    hecho = "Eliminado" if cambio.operacion == "eliminar" else "Guardado"
    await cl.Message(content=f"{hecho}: **{cambio.nombre}**.").send()


@cl.action_callback("cancelar_cambio_comunidad")
async def cancelar_cambio(action: cl.Action) -> None:
    cambios = cl.user_session.get(CLAVE_CAMBIOS) or {}
    cambios.pop(action.payload.get("id"), None)
    cl.user_session.set(CLAVE_CAMBIOS, cambios)
    await action.remove()
    await cl.Message(content="Cancelado. No cambie nada.").send()
