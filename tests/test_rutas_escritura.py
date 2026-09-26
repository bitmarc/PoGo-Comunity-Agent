"""Regresion: nada se escribe donde el contenedor no puede.

En produccion el proceso corre como usuario sin privilegios y `/app` es de root, asi que
cualquier `mkdir` bajo el directorio de trabajo o bajo el codigo revienta con
"Permission denied" — y solo en produccion, nunca en local, donde el desarrollador es
dueno de todo.

Ya paso dos veces: con `/app/.files` de Chainlit y con `/app/out` de las piezas. Este
test existe para que no pase una tercera.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hxq_agent.config import Settings, get_settings

RAIZ_SRC = Path(__file__).parent.parent / "src" / "hxq_agent"

# Patrones que construyen rutas de escritura peligrosas.
_PELIGROSOS = re.compile(
    r"""(
        Path\.cwd\(\)\s*/          # relativo al directorio de trabajo (/app)
      | Path\(__file__\)\.parent\s*/\s*["'](?:cache|out|salida|data)  # dentro del codigo
    )""",
    re.VERBOSE,
)


def test_ningun_modulo_escribe_en_cwd_ni_junto_al_codigo() -> None:
    ofensores: list[str] = []
    for archivo in RAIZ_SRC.rglob("*.py"):
        for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            if linea.lstrip().startswith("#"):
                continue
            if _PELIGROSOS.search(linea):
                ofensores.append(f"{archivo.relative_to(RAIZ_SRC)}:{n}: {linea.strip()}")

    assert not ofensores, (
        "Estas rutas fallan en el contenedor con Permission denied.\n"
        "Usa settings.subdir(...) en su lugar:\n  " + "\n  ".join(ofensores)
    )


class TestDataDir:
    def test_por_defecto_va_al_temporal_del_sistema(self, monkeypatch, tmp_path) -> None:
        import tempfile

        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        get_settings.cache_clear()
        d = Settings(_env_file=None, hxq_data_dir="").data_dir
        assert d.is_relative_to(tmp_path)
        assert d.is_dir(), "se crea al pedirlo"

    def test_se_puede_configurar(self, tmp_path) -> None:
        destino = tmp_path / "elegido"
        assert Settings(_env_file=None, hxq_data_dir=str(destino)).data_dir == destino

    def test_subdir_crea_y_devuelve(self, tmp_path) -> None:
        s = Settings(_env_file=None, hxq_data_dir=str(tmp_path))
        d = s.subdir("piezas")
        assert d == tmp_path / "piezas"
        assert d.is_dir()

    def test_subdir_es_idempotente(self, tmp_path) -> None:
        s = Settings(_env_file=None, hxq_data_dir=str(tmp_path))
        assert s.subdir("piezas") == s.subdir("piezas")

    @pytest.mark.parametrize("nombre", ["piezas", "calendario", "cache_arte", "cache_pokemon"])
    def test_los_subdirectorios_que_usa_la_app(self, tmp_path, nombre: str) -> None:
        """Si alguien renombra uno, que se entere aqui."""
        s = Settings(_env_file=None, hxq_data_dir=str(tmp_path))
        assert s.subdir(nombre).is_dir()
