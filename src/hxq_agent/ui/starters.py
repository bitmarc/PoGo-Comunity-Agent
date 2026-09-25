"""Starters: atajos visibles al abrir el chat, uno por tarea de `uso.txt`.

En Fase 0 y 1 solo siembran la conversacion. A medida que las tools existan, cada uno
acabara disparando su flujo correspondiente.
"""

from __future__ import annotations

import chainlit as cl


def build_starters() -> list[cl.Starter]:
    """Los atajos que ve el admin en pantalla vacia."""
    return [
        cl.Starter(
            label="Armar una quedada",
            message=(
                "Quiero armar una quedada. Te doy los datos y me preparas titulo, "
                "descripcion, lugar y hora listos para Campfire y para WhatsApp."
            ),
        ),
        cl.Starter(
            label="Proximos eventos oficiales",
            message=(
                "Investiga que eventos oficiales de Pokemon GO vienen en las proximas "
                "dos semanas. Dame fechas confirmadas con su fuente."
            ),
        ),
        cl.Starter(
            label="Anuncio de evento",
            message=(
                "Necesito el anuncio de un evento adaptado a cada canal: WhatsApp corto, "
                "Instagram con hashtags y Facebook mas largo."
            ),
        ),
        cl.Starter(
            label="Idea de dinamica o concurso",
            message=(
                "Propon una dinamica o concurso para la comunidad: reglas claras, premio, "
                "duracion y criterio de desempate."
            ),
        ),
        cl.Starter(
            label="Resolver una duda",
            message="Tengo una duda sobre un evento o una mecanica del juego.",
        ),
    ]
