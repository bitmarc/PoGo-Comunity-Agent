"""Tools del agente.

Cada tool es una funcion decorada con `@agent_framework.tool`: el docstring se vuelve su
descripcion y las anotaciones `Annotated[..., Field(description=...)]` describen cada
parametro. Eso es lo que el modelo lee para decidir cuando llamarla, asi que esos textos
son parte del prompt, no comentarios.
"""

from __future__ import annotations

from agent_framework import FunctionTool

from hxq_agent.agent.tools.biblioteca import buscar_en_biblioteca
from hxq_agent.agent.tools.calendario import crear_ics
from hxq_agent.agent.tools.incursiones import infografia_incursion, jefes_de_incursion
from hxq_agent.agent.tools.rendering import render_pieza
from hxq_agent.agent.tools.search import buscar_web
from hxq_agent.agent.tools.weather import consultar_clima

__all__ = [
    "buscar_en_biblioteca",
    "infografia_incursion",
    "jefes_de_incursion",
    "buscar_web",
    "build_tools",
    "consultar_clima",
    "crear_ics",
    "render_pieza",
]


def build_tools() -> list[FunctionTool]:
    """Las tools disponibles."""
    return [
        buscar_web,
        consultar_clima,
        render_pieza,
        crear_ics,
        buscar_en_biblioteca,
        jefes_de_incursion,
        infografia_incursion,
    ]
