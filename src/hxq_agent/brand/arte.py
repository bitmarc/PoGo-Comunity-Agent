"""Generacion del arte central de las piezas con gpt-image.

Division de trabajo deliberada: el modelo de imagen dibuja SOLO la ilustracion, nunca
texto. Fecha, hora y lugar los escribe la plantilla HTML. Un modelo de imagen escribe mal
lo suficientemente a menudo como para que un aviso con la hora equivocada llegue a toda
la comunidad.

El arte se pide con fondo transparente para poder montarlo sobre el fondo neon de la
pieza sin un recuadro visible.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path

from hxq_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Cache en disco por hash del prompt: regenerar la misma pieza no deberia volver a
# pagar una imagen. Se borra solo cuando el usuario lo pida.
DIR_CACHE = Path(__file__).parent / "cache_arte"

# Cuadrado: el arte va centrado en una pieza cuadrada.
TAMANO = "1024x1024"

_ESTILO = (
    "Ilustracion digital vibrante estilo neon sobre fondo transparente. "
    "Colores saturados, contornos con resplandor luminoso, aspecto de arte de videojuego "
    "moderno. Sin texto, sin letras, sin numeros, sin marcas de agua, sin bordes ni marco. "
    "Sujeto centrado y completo, recortado sobre transparencia."
)


class ArteError(RuntimeError):
    """El arte no se pudo generar."""


def _clave(prompt: str, calidad: str) -> str:
    return hashlib.sha256(f"{calidad}|{prompt}".encode()).hexdigest()[:24]


def construir_prompt(descripcion: str) -> str:
    """Combina lo que pide el admin con las restricciones de estilo.

    La prohibicion de texto va al final y explicita: es la instruccion que el modelo
    mas tiende a ignorar, y un texto dibujado dentro del arte arruina la pieza.
    """
    return f"{descripcion.strip().rstrip('.')}. {_ESTILO}"


async def generar_arte(
    descripcion: str,
    *,
    settings: Settings | None = None,
    calidad: str = "medium",
    usar_cache: bool = True,
) -> bytes:
    """Genera el arte central y devuelve el PNG con fondo transparente."""
    settings = settings or get_settings()
    prompt = construir_prompt(descripcion)

    DIR_CACHE.mkdir(exist_ok=True)
    cacheado = DIR_CACHE / f"{_clave(prompt, calidad)}.png"
    if usar_cache and cacheado.exists():
        logger.info("Arte servido de cache: %s", cacheado.name)
        return cacheado.read_bytes()

    if not settings.azure_openai_endpoint.strip():
        raise ArteError("Falta AZURE_OPENAI_ENDPOINT para generar imagenes.")

    # AsyncOpenAI apuntado a la superficie v1, no AsyncAzureOpenAI: este recurso usa
    # /openai/v1/images/generations, y el cliente de Azure arma la ruta antigua
    # /openai/deployments/<nombre>/images/generations, que responde 404.
    from openai import AsyncOpenAI

    base_url = settings.azure_openai_endpoint.rstrip("/") + "/openai/v1/"

    if settings.uses_managed_identity:
        from azure.identity.aio import DefaultAzureCredential

        credencial = DefaultAzureCredential()
        token = await credencial.get_token("https://cognitiveservices.azure.com/.default")
        await credencial.close()
        cliente = AsyncOpenAI(base_url=base_url, api_key=token.token)
    else:
        # Azure espera la clave en la cabecera `api-key`; la SDK manda `Authorization`.
        clave = settings.azure_openai_api_key
        cliente = AsyncOpenAI(base_url=base_url, api_key=clave, default_headers={"api-key": clave})
    try:
        respuesta = await cliente.images.generate(
            model=settings.hxq_image_deployment,
            prompt=prompt,
            size=TAMANO,
            quality=calidad,
            background="transparent",
            output_format="png",
            n=1,
        )
    except Exception as exc:
        logger.exception("Fallo la generacion de arte")
        raise ArteError(f"No se pudo generar el arte: {exc}") from exc
    finally:
        await cliente.close()

    datos = respuesta.data[0] if respuesta.data else None
    if datos is None or not getattr(datos, "b64_json", None):
        raise ArteError("El modelo no devolvio ninguna imagen.")

    png = base64.b64decode(datos.b64_json)  # type: ignore[arg-type]
    cacheado.write_bytes(png)
    logger.info("Arte generado: %d KB (cache: %s)", len(png) // 1024, cacheado.name)
    return png


def como_data_uri(png: bytes) -> str:
    """PNG -> data URI, para incrustarlo en el HTML sin escribirlo a disco."""
    return "data:image/png;base64," + base64.b64encode(png).decode()
