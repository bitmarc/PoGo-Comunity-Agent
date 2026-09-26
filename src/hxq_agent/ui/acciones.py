"""Controles de aprobacion sobre una pieza generada.

Las acciones se ofrecen al FINAL del turno, no cuando la tool termina. El motivo es que
los bloques de copy los escribe el agente despues de dibujar la imagen: si el boton
apareciera junto a la imagen, aprobar archivaria la pieza sin el texto que la acompana,
que es la mitad de lo que hace util la biblioteca.

Solo se archiva lo aprobado. Guardar cada borrador llenaria la tabla de ruido.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import chainlit as cl

from hxq_agent.storage.biblioteca import BibliotecaNoDisponible, Pieza, archivar

logger = logging.getLogger(__name__)

# Piezas generadas en el turno actual, aun sin copy.
CLAVE_TURNO = "hxq_piezas_turno"
# Piezas ya ofrecidas, indexadas por id. Sobreviven al turno porque la accion se dispara
# despues: el admin puede tardar minutos en decidir, o revisar antes otra conversacion.
CLAVE_OFRECIDAS = "hxq_piezas_ofrecidas"


def registrar_pendiente(ruta: Path, plantilla: str, titulo: str) -> None:
    """Anota una pieza recien dibujada. La llama el middleware de tools."""
    piezas = cl.user_session.get(CLAVE_TURNO) or []
    piezas.append({"ruta": str(ruta), "plantilla": plantilla, "titulo": titulo})
    cl.user_session.set(CLAVE_TURNO, piezas)


def tomar_pendientes() -> list[dict[str, Any]]:
    """Devuelve y limpia las piezas del turno."""
    piezas = cl.user_session.get(CLAVE_TURNO) or []
    cl.user_session.set(CLAVE_TURNO, [])
    return piezas


async def ofrecer_acciones(pendientes: list[dict[str, Any]], copy: str) -> None:
    """Ofrece aprobar o descartar cada pieza del turno.

    `copy` es la respuesta completa del agente: lleva los bloques por canal, y es la
    mitad de lo que hace util la biblioteca.
    """
    ofrecidas = cl.user_session.get(CLAVE_OFRECIDAS) or {}

    for pieza in pendientes:
        # Id propio en vez de indice: la accion se dispara despues, cuando la lista del
        # turno ya se limpio, y un indice apuntaria a otra pieza o a nada.
        pieza_id = uuid.uuid4().hex[:12]
        # El copy va en sesion y no en el payload: el payload viaja al navegador y los
        # bloques pueden ser largos.
        ofrecidas[pieza_id] = {**pieza, "copy": copy}
        cl.user_session.set(CLAVE_OFRECIDAS, ofrecidas)

        await cl.Message(
            content=f"**{pieza['titulo']}** — ¿la archivo en la biblioteca?",
            actions=[
                cl.Action(
                    name="aprobar_pieza",
                    payload={"id": pieza_id},
                    label="Aprobar y archivar",
                    icon="check",
                ),
                cl.Action(
                    name="descartar_pieza",
                    payload={"id": pieza_id},
                    label="Descartar",
                    icon="x",
                ),
            ],
        ).send()


def _bloques_por_canal(copy: str) -> dict[str, str]:
    """Parte la respuesta del agente en sus bloques de canal.

    El agente separa con encabezados markdown (## Campfire, ## WhatsApp...). Si el
    formato cambia, se guarda el texto completo en vez de perderlo.
    """
    bloques: dict[str, str] = {}
    actual: str | None = None
    lineas: list[str] = []

    for linea in copy.splitlines():
        if linea.startswith("## "):
            if actual:
                bloques[actual] = "\n".join(lineas).strip()
            actual = linea[3:].strip().lower()
            lineas = []
        elif actual:
            lineas.append(linea)
    if actual:
        bloques[actual] = "\n".join(lineas).strip()

    return bloques or {"completo": copy.strip()}


@cl.action_callback("aprobar_pieza")
async def aprobar_pieza(action: cl.Action) -> None:
    """Sube la imagen a Blob y guarda la fila en la biblioteca."""
    ofrecidas = cl.user_session.get(CLAVE_OFRECIDAS) or {}
    pieza = ofrecidas.get(action.payload.get("id"))
    if pieza is None:
        await cl.Message(content="Esa pieza ya no esta disponible en esta sesion.").send()
        return

    copy = pieza.get("copy", "")
    usuario = cl.user_session.get("user")
    correo = getattr(usuario, "identifier", None) or "desconocido"

    try:
        pieza_id = await archivar(
            Pieza(
                tipo=pieza["plantilla"],
                titulo=pieza["titulo"],
                creado_por=correo,
                contenido=_bloques_por_canal(copy),
                evento_fecha=pieza.get("evento_fecha") or date.today(),
                imagen=Path(pieza["ruta"]) if Path(pieza["ruta"]).is_file() else None,
                prompt=pieza.get("prompt"),
                thread_id=cl.context.session.thread_id,
            )
        )
    except BibliotecaNoDisponible as exc:
        await cl.Message(content=f"No pude archivarla: {exc}").send()
        return
    except Exception:
        logger.exception("Fallo al archivar la pieza")
        await cl.Message(
            content="No pude archivarla. La imagen sigue arriba; revisa los logs."
        ).send()
        return

    await action.remove()
    await cl.Message(
        content=f"Archivada en la biblioteca. La imagen queda guardada. `{pieza_id[:8]}`"
    ).send()


@cl.action_callback("descartar_pieza")
async def descartar_pieza(action: cl.Action) -> None:
    """No archiva nada. La imagen sigue visible en el chat por si se quiere usar igual."""
    await action.remove()
    await cl.Message(content="Descartada. No la guardo en la biblioteca.").send()
