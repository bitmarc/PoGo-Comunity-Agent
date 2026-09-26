"""Middleware que hace visibles las llamadas a tools en la interfaz.

Vive en `ui/` porque importa Chainlit. El nucleo del agente no sabe que esto existe: se
inyecta por `agent.run(middleware=[...])`, asi que quitarlo o cambiar de UI no toca el
agente.

Que el admin vea "busque esto en estas fuentes" es parte del producto, no decoracion: es
como verifica que el dato sale de una fuente y no de la imaginacion del modelo. Y cuando
una tool produce una pieza grafica, la imagen se muestra: el admin tiene que VER lo que
va a publicar, no leer la ruta de un archivo.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import chainlit as cl
from agent_framework import FunctionInvocationContext, function_middleware

from hxq_agent.ui.acciones import registrar_pendiente

logger = logging.getLogger(__name__)

# Como se le presenta cada tool al admin. Si aparece una sin entrada aqui, se muestra con
# su nombre tecnico: feo, pero nunca oculta una llamada.
_ETIQUETAS: dict[str, str] = {
    "buscar_web": "Buscando en la web",
    "consultar_clima": "Consultando el clima",
    "render_pieza": "Dibujando la pieza",
    "crear_ics": "Preparando el calendario",
    "buscar_en_biblioteca": "Revisando lo ya publicado",
}

_MAX_SALIDA = 4000

# Rutas de archivos generados en la salida de una tool, en formato Windows o POSIX.
_PATRON_ARCHIVO = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s\n]*?\.(?:png|ics)")


def rutas_generadas(texto: str) -> list[Path]:
    """Archivos existentes mencionados en la salida de una tool.

    Se comprueba que existan: el modelo a veces repite una ruta en su propio texto, y
    mostrar dos veces la misma imagen confunde.
    """
    vistas: list[Path] = []
    for bruto in _PATRON_ARCHIVO.findall(texto):
        ruta = Path(bruto.strip().rstrip(".,"))
        if ruta.is_file() and ruta not in vistas:
            vistas.append(ruta)
    return vistas


def _resumir_argumentos(arguments: Any) -> str:
    """Los argumentos en texto corto, para el encabezado del paso."""
    if not isinstance(arguments, dict):
        return str(arguments)[:200]
    partes = [f"{k}: {v}" for k, v in arguments.items() if v not in (None, "")]
    return " · ".join(partes)[:300]


def texto_resultado(resultado: Any) -> str:
    """Texto plano de lo que devolvio una tool.

    MAF entrega el resultado como `list[Content]`, no como `str`. Hacerle `str()`
    directamente produce `[<agent_framework._types.Content object at 0x...>]`, que es
    inservible por partida doble: el panel de la tool muestra ese repr, y el buscador de
    archivos generados no encuentra ninguna ruta, asi que la imagen y el calendario nunca
    se le adjuntan al admin.
    """
    if resultado is None:
        return ""
    if isinstance(resultado, str):
        return resultado
    if isinstance(resultado, list):
        return "\n".join(texto_resultado(x) for x in resultado)
    if (texto := getattr(resultado, "text", None)) is not None:
        return str(texto)
    return str(resultado)


@function_middleware
async def mostrar_tools_en_ui(context: FunctionInvocationContext, call_next: Any) -> None:
    """Envuelve cada invocacion de tool en un `cl.Step` colapsable."""
    nombre = getattr(getattr(context, "function", None), "name", "tool")
    etiqueta = _ETIQUETAS.get(nombre, nombre)
    argumentos = getattr(context, "arguments", None)

    try:
        async with cl.Step(name=etiqueta, type="tool", show_input=False) as paso:
            if resumen := _resumir_argumentos(argumentos):
                paso.input = resumen

            await call_next()

            texto = texto_resultado(getattr(context, "result", None))
            generados = rutas_generadas(texto)

            if len(texto) > _MAX_SALIDA:
                texto = texto[:_MAX_SALIDA] + "\n\n[...truncado]"
            paso.output = texto
    except Exception:
        # La UI nunca debe tumbar una llamada a tool: si el paso falla, se ejecuta igual.
        logger.exception("No se pudo renderizar el paso de la tool %s", nombre)
        await call_next()
        return

    # Fuera del `Step`: lo que va dentro de un paso colapsado se queda oculto, y la
    # pieza y el calendario son justo lo que el admin tiene que ver y descargar.
    for ruta in generados:
        if ruta.suffix == ".png":
            # Se anota para poder ofrecer "Aprobar" al cerrar el turno, cuando ya exista
            # el copy que acompana a la pieza.
            if nombre == "render_pieza":
                titulo = _titulo_de(texto) or ruta.stem
                registrar_pendiente(ruta, _plantilla_de(argumentos), titulo)
            elemento = cl.Image(path=str(ruta), size="large", name=ruta.name)
        else:
            elemento = cl.File(path=str(ruta), name=ruta.name, display="inline")
        await cl.Message(content="", elements=[elemento]).send()


def _titulo_de(texto: str) -> str:
    """Titulo que reporta `render_pieza` en su salida."""
    for linea in texto.splitlines():
        if linea.startswith("Titulo:"):
            return linea.partition(":")[2].strip()
    return ""


def _plantilla_de(argumentos: Any) -> str:
    if isinstance(argumentos, dict):
        return str(argumentos.get("plantilla") or "pieza")
    return "pieza"
