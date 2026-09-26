"""Motor de render: datos validados -> HTML -> PNG.

No importa `chainlit` ni `agent_framework`: es una libreria pura que se puede probar
sola. La tool que lo expone al agente vive en `agent/tools/rendering.py`.

Por que Playwright y no un modelo de imagen: la fecha, la hora y el lugar tienen que
salir exactos. Un modelo de imagen los escribe mal lo suficientemente a menudo como para
que no sirva, y una pieza con la hora equivocada llega a toda la comunidad.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

logger = logging.getLogger(__name__)

DIR_BRAND = Path(__file__).parent
DIR_PLANTILLAS = DIR_BRAND / "templates"

# Cuadrado, como las piezas ya publicadas (~1240x1240). No 1080x1350: el formato
# vertical de Instagram no es lo que usa la comunidad.
ANCHO = 1240
ALTO = 1240

_entorno: Environment | None = None


def entorno_jinja() -> Environment:
    """Entorno de plantillas con `StrictUndefined`.

    Una variable que falta tiene que reventar al renderizar, no dibujar un hueco
    silencioso que acabe publicado.
    """
    global _entorno
    if _entorno is None:
        _entorno = Environment(
            loader=FileSystemLoader(DIR_PLANTILLAS),
            undefined=StrictUndefined,
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _entorno


def construir_html(plantilla: str, contexto: dict[str, Any]) -> str:
    """Renderiza la plantilla a HTML."""
    tpl = entorno_jinja().get_template(f"{plantilla}.html.j2")
    return tpl.render(ancho=ANCHO, alto=ALTO, **contexto)


async def _capturar(html: str, ancho: int, alto: int) -> bytes:
    """HTML -> PNG con Chromium headless.

    Async y no sync porque las tools del agente corren dentro de un bucle asyncio, y la
    API sincrona de Playwright se niega a arrancar ahi ("It looks like you are using
    Playwright Sync API inside the asyncio loop").

    El HTML se escribe dentro de `brand/templates/`, el mismo directorio que las
    plantillas, para que los `../tokens.css` y `../assets/...` que escriben resuelvan
    igual que si la plantilla se abriera directamente. Escribirlo en `brand/` los manda
    un nivel por encima del paquete y la hoja no carga: el sintoma es una pieza en
    blanco con el texto invisible, porque solo sobrevive el `<style>` inline.
    """
    from playwright.async_api import async_playwright

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", dir=DIR_PLANTILLAS, delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        ruta = Path(f.name)

    try:
        async with async_playwright() as p:
            navegador = await p.chromium.launch(args=["--force-color-profile=srgb"])
            try:
                pagina = await navegador.new_page(
                    viewport={"width": ancho, "height": alto},
                    # 1 y no 2: a 1240px ya supera de sobra lo que pide Instagram, y
                    # duplicarlo cuadruplica el peso del PNG.
                    device_scale_factor=1,
                )
                await pagina.goto(ruta.as_uri(), wait_until="load")
                # Las fuentes cargan de forma asincrona: sin esperarlas, la captura sale
                # con la fuente de sistema y el texto ocupa otro ancho.
                await pagina.evaluate("document.fonts.ready")
                await pagina.wait_for_timeout(120)
                elemento = await pagina.query_selector(".lienzo")
                if elemento is None:
                    raise RuntimeError("La plantilla no tiene un elemento .lienzo")
                return await elemento.screenshot(type="png")
            finally:
                await navegador.close()
    finally:
        ruta.unlink(missing_ok=True)


async def renderizar(plantilla: str, contexto: dict[str, Any]) -> bytes:
    """Renderiza una pieza y devuelve el PNG."""
    html = construir_html(plantilla, contexto)
    png = await _capturar(html, ANCHO, ALTO)
    logger.info("Pieza '%s' renderizada: %d KB", plantilla, len(png) // 1024)
    return png


def renderizar_sync(plantilla: str, contexto: dict[str, Any]) -> bytes:
    """Version sincrona, para scripts y tests. No usar desde codigo async."""
    import asyncio

    return asyncio.run(renderizar(plantilla, contexto))
