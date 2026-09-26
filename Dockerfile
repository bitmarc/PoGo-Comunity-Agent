# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Etapa 1: dependencias
# Se instalan en una etapa aparte para que el layer no se invalide al cambiar codigo.
# ---------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Solo los manifiestos: mientras no cambien, este layer se reutiliza.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Ahora el codigo, y el proyecto en si.
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ---------------------------------------------------------------------------
# Etapa 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

# tzdata es obligatorio: zoneinfo no trae base de datos propia y
# ZoneInfo("America/Mexico_City") falla sin ella. Sin tzdata el agente no puede
# resolver "el sabado" a una fecha, que es la mitad de su trabajo.
# ca-certificates para TLS hacia Azure, Tavily y Open-Meteo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Chromium para renderizar las piezas graficas.
#
# chromium-headless-shell y no chromium completo: ~120 MB en vez de ~400 MB, y no hace
# falta nada de lo que aporta el navegador entero para tomar una captura.
#
# PLAYWRIGHT_BROWSERS_PATH fuera de $HOME para que el binario lo instale root una sola
# vez y el usuario sin privilegios pueda ejecutarlo. Con la ruta por defecto
# (~/.cache/ms-playwright) el usuario hxq no lo encontraria.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Usuario sin privilegios. El contenedor no necesita root para nada.
RUN useradd --create-home --uid 10001 hxq
WORKDIR /app

COPY --from=builder --chown=hxq:hxq /app/.venv /app/.venv

# Con --with-deps para que apt instale las librerias de sistema que pide chromium
# (fuentes, libnss, libdrm...). Sin ellas el binario existe pero no arranca.
RUN /app/.venv/bin/python -m playwright install --with-deps chromium-headless-shell     && rm -rf /var/lib/apt/lists/*     && chmod -R a+rX /opt/playwright
COPY --chown=hxq:hxq src ./src
COPY --chown=hxq:hxq .chainlit ./.chainlit
COPY --chown=hxq:hxq chainlit.md ./
# public/ lleva el logo, favicon y tema de Chainlit. Se copia explicitamente:
# un glob (public*) falla en un checkout limpio si el directorio no existe.
COPY --chown=hxq:hxq public ./public

# Chainlit escribe en tiempo de ejecucion: .files para elementos cuando no hay storage
# client, y .chainlit/translations. El usuario sin privilegios no puede crear
# directorios en /app (es de root), asi que se crean aqui con el dueno correcto.
# Sin esto el contenedor muere al arrancar con PermissionError en /app/.files.
RUN mkdir -p /app/.files /app/.chainlit/translations     && chown -R hxq:hxq /app/.files /app/.chainlit

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Mexico_City \
    PORT=8000

USER hxq
EXPOSE 8000

# --host 0.0.0.0 es obligatorio: el default escucha en localhost y el router de
# Container Apps no lo alcanza (el clasico "funciona en local, 502 en produccion").
# --headless evita que intente abrir un navegador que no existe en el contenedor.
CMD ["chainlit", "run", "src/hxq_agent/app.py", "--host", "0.0.0.0", "--port", "8000", "--headless"]
