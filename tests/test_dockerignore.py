"""Los archivos que la app necesita en ejecucion tienen que llegar a la imagen.

Es la tercera vez que aparece este fallo: primero `chainlit.md` (la pantalla de
bienvenida), luego `public/` con un glob que fallaba en CI, y ahora `prompt.md`, que ES
el system prompt. Todos se detectaron tarde porque en local el archivo esta ahi y solo
falta dentro del contenedor.

Se usa `pathspec`, que implementa la misma semantica de patrones que Docker, en vez de
aproximarla con fnmatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

RAIZ = Path(__file__).parent.parent

# Archivos sin los cuales la app no funciona dentro del contenedor.
IMPRESCINDIBLES = [
    "src/hxq_agent/agent/prompt.md",
    "src/hxq_agent/app.py",
    "src/hxq_agent/brand/tokens.css",
    "src/hxq_agent/brand/fonts/Baloo2.ttf",
    "src/hxq_agent/brand/fonts/Nunito.ttf",
    "src/hxq_agent/brand/templates/base.html.j2",
    "src/hxq_agent/brand/templates/quedada.html.j2",
    "src/hxq_agent/brand/templates/infografia_raid.html.j2",
    "src/hxq_agent/brand/assets/logo_hxq_transparente.png",
    "chainlit.md",
    ".chainlit/config.toml",
    "public/theme.json",
    "public/logo_dark.png",
    "public/logo_light.png",
    "public/avatars/huixquigo_agent.png",
    "public/favicon.png",
    "pyproject.toml",
    "uv.lock",
]

# Lo que NO debe entrar nunca.
PROHIBIDOS = [
    ".env",
    "client_secret_algo.apps.googleusercontent.com.json",
    "infra/main.parameters.json",
    ".venv/lib/algo.py",
    "tests/test_prompt.py",
]


@pytest.fixture(scope="module")
def spec() -> PathSpec:
    lineas = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return PathSpec.from_lines(GitWildMatchPattern, lineas)


@pytest.mark.parametrize("ruta", IMPRESCINDIBLES)
def test_los_archivos_necesarios_llegan_a_la_imagen(spec: PathSpec, ruta: str) -> None:
    assert not spec.match_file(ruta), (
        f"{ruta} esta excluido por .dockerignore. La app funcionara en local y "
        "fallara dentro del contenedor."
    )


@pytest.mark.parametrize("ruta", PROHIBIDOS)
def test_lo_sensible_y_lo_inutil_se_queda_fuera(spec: PathSpec, ruta: str) -> None:
    assert spec.match_file(ruta), f"{ruta} NO esta excluido y deberia estarlo."


def test_los_imprescindibles_existen_de_verdad(spec: PathSpec) -> None:
    """Si alguien renombra o mueve uno, que este test deje de mentir."""
    faltan = [r for r in IMPRESCINDIBLES if not (RAIZ / r).exists()]
    assert not faltan, f"La lista apunta a archivos que ya no existen: {faltan}"
