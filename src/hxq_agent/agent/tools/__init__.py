"""Tools del agente.

Cada tool es una funcion decorada con `@agent_framework.tool`: el docstring se vuelve su
descripcion y las anotaciones `Annotated[..., Field(description=...)]` describen cada
parametro. Eso es lo que el modelo lee para decidir cuando llamarla, asi que esos textos
son parte del prompt, no comentarios.
"""

from __future__ import annotations

from agent_framework import FunctionTool

from hxq_agent.agent.tools.search import buscar_web
from hxq_agent.agent.tools.weather import consultar_clima

__all__ = ["buscar_web", "build_tools", "consultar_clima"]


def build_tools() -> list[FunctionTool]:
    """Las tools disponibles en la Fase 1."""
    return [buscar_web, consultar_clima]
