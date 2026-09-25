"""Aplica los archivos .sql de este directorio a la base de datos, en orden.

Deliberadamente tonto: lee los .sql ordenados por nombre y los ejecuta. No es un sistema
de migraciones con historial, y no hace falta todavia: los scripts son idempotentes, asi
que reaplicarlos es seguro.

Cuando haya que cambiar una tabla existente (no solo anadir), esto se queda corto y toca
pasar a Alembic o a las migraciones de Prisma del upstream.

Uso:
    ./.venv/Scripts/python.exe infra/db/apply_schema.py
    ./.venv/Scripts/python.exe infra/db/apply_schema.py --dry-run
    DATABASE_URL=postgresql://... ./.venv/Scripts/python.exe infra/db/apply_schema.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

DIRECTORIO = Path(__file__).parent


def cargar_dsn() -> str:
    """DATABASE_URL del entorno o del .env, normalizado para asyncpg."""
    dsn = os.environ.get("DATABASE_URL", "").strip()

    if not dsn:
        env = DIRECTORIO.parent.parent / ".env"
        if env.exists():
            for linea in env.read_text(encoding="utf-8").splitlines():
                linea = linea.strip()
                if linea.startswith("DATABASE_URL="):
                    dsn = linea.partition("=")[2].strip().strip('"').strip("'")
                    break

    if not dsn:
        sys.exit(
            "Falta DATABASE_URL. Ponla en .env o exportala:\n"
            "  DATABASE_URL=postgresql://usuario:pass@host.neon.tech/neondb?sslmode=require"
        )

    sys.path.insert(0, str(DIRECTORIO.parent.parent / "src"))
    from hxq_agent.storage.db import normalizar_dsn

    return normalizar_dsn(dsn)


def scripts() -> list[Path]:
    return sorted(DIRECTORIO.glob("*.sql"))


async def aplicar(dsn: str, dry_run: bool) -> None:
    archivos = scripts()
    if not archivos:
        sys.exit(f"No hay archivos .sql en {DIRECTORIO}")

    # Nunca imprimir el DSN: lleva la contrasena.
    host = dsn.partition("@")[2].partition("/")[0] or "?"
    print(f"Base de datos: {host}")
    print(f"Scripts: {', '.join(f.name for f in archivos)}")

    if dry_run:
        for archivo in archivos:
            sentencias = [s for s in archivo.read_text(encoding="utf-8").split(";") if s.strip()]
            print(f"  [dry-run] {archivo.name}: ~{len(sentencias)} sentencias")
        return

    import asyncpg

    conexion = await asyncpg.connect(dsn)
    try:
        for archivo in archivos:
            print(f"  aplicando {archivo.name} ...", end=" ", flush=True)
            # El archivo entero en una transaccion: si algo falla, no queda a medias.
            async with conexion.transaction():
                await conexion.execute(archivo.read_text(encoding="utf-8"))
            print("ok")

        tablas = await conexion.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
            """
        )
        print("\nTablas en la base de datos:")
        for fila in tablas:
            print("  -", fila["table_name"])
    finally:
        await conexion.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Solo lista lo que se aplicaria."
    )
    args = parser.parse_args()
    asyncio.run(aplicar(cargar_dsn(), args.dry_run))


if __name__ == "__main__":
    main()
