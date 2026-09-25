"""Controles por chat: lo que el admin puede ajustar sin escribirlo en cada mensaje.

Las preferencias se guardan en la sesion y se inyectan al agente como contexto por turno.
No van en el system prompt base porque cambian durante la conversacion.
"""

from __future__ import annotations

import chainlit as cl

CLAVE_PREFERENCIAS = "hxq_preferencias"

TONOS = ["Cercano (por defecto)", "Muy informal / con memes", "Neutro y breve"]
CANALES = ["Todos los canales", "Solo WhatsApp", "Solo Instagram/Facebook", "Solo Campfire"]
LONGITUDES = ["Media", "Corta", "Larga"]

PREFERENCIAS_POR_DEFECTO: dict[str, str] = {
    "tono": TONOS[0],
    "canal": CANALES[0],
    "longitud": LONGITUDES[0],
}


def build_chat_settings() -> cl.ChatSettings:
    """Los controles que aparecen en la interfaz."""
    return cl.ChatSettings(
        [
            cl.input_widget.Select(
                id="tono",
                label="Tono del contenido",
                values=TONOS,
                initial_index=0,
            ),
            cl.input_widget.Select(
                id="canal",
                label="Canal destino",
                values=CANALES,
                initial_index=0,
            ),
            cl.input_widget.Select(
                id="longitud",
                label="Longitud del copy",
                values=LONGITUDES,
                initial_index=0,
            ),
        ]
    )


def describir_preferencias(preferencias: dict[str, str]) -> str:
    """Traduce las preferencias a una instruccion que el modelo entienda.

    Se manda como contexto del turno, no en el system prompt, porque el admin las puede
    cambiar a mitad de la conversacion y el cambio tiene que surtir efecto de inmediato.
    """
    tono = preferencias.get("tono", PREFERENCIAS_POR_DEFECTO["tono"])
    canal = preferencias.get("canal", PREFERENCIAS_POR_DEFECTO["canal"])
    longitud = preferencias.get("longitud", PREFERENCIAS_POR_DEFECTO["longitud"])

    partes: list[str] = []

    if tono == TONOS[1]:
        partes.append("Tono muy informal, con humor y referencias de la comunidad.")
    elif tono == TONOS[2]:
        partes.append("Tono neutro y directo, sin emojis salvo que sean imprescindibles.")

    if canal == CANALES[1]:
        partes.append("Genera solo el bloque de WhatsApp.")
    elif canal == CANALES[2]:
        partes.append("Genera solo el bloque de Instagram/Facebook, con hashtags.")
    elif canal == CANALES[3]:
        partes.append("Genera solo el bloque de Campfire, en el formato que pide la app.")

    if longitud == LONGITUDES[1]:
        partes.append("Se lo mas breve posible.")
    elif longitud == LONGITUDES[2]:
        partes.append("Puedes extenderte y dar mas detalle.")

    if not partes:
        return ""
    return "Preferencias activas del admin para este turno: " + " ".join(partes)
